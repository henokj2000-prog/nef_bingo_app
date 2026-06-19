#!/usr/bin/env python3
import os
import sys
import time
import json
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db, put_db, add_bot_to_game
from game.bingo_logic import generate_card, draw_ball, check_bingo
from config import GAME_START_DELAY_SECONDS, BALL_DRAW_INTERVAL_SECONDS

# ---------- Helper functions ----------
def get_setting_value(key, default=None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        return row['value'] if row else default
    finally:
        cur.close()
        put_db(conn)

def add_bots_to_waiting_game(game_id, stake):
    """Trickle bots into a waiting game like real players arriving:
       - never more than `bot_number_to_add` bots total in the game
       - at most one new bot per `bot_addition_interval_seconds`
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        max_bots = int(get_setting_value('bot_number_to_add', '1'))
        try:
            interval = float(get_setting_value('bot_addition_interval_seconds', '3'))
        except (TypeError, ValueError):
            interval = 3.0

        # How many bots are already in this game?
        cur.execute("SELECT COUNT(DISTINCT user_id) AS cnt FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        bot_count = cur.fetchone()['cnt']
        if bot_count >= max_bots:
            return  # reached the configured cap

        # When was the most recent bot added to this game?
        cur.execute("SELECT MAX(created_at) AS last FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        last = cur.fetchone()['last']
        if last is not None:
            if isinstance(last, str):
                last = float(last)
            if (time.time() - last) < interval:
                return  # not time for the next bot yet

        # Add exactly one bot (one-at-a-time arrival)
        add_bot_to_game(game_id, stake)
    except Exception as e:
        print(f"Error adding bots: {e}")
    finally:
        cur.close()
        put_db(conn)

# ---------- Game progression (no interval anywhere) ----------
def process_waiting_games():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get all waiting games – no interval, use countdown_started_at
        cur.execute("""
            SELECT id, stake, countdown_started_at
            FROM games
            WHERE status = 'waiting' AND cancelled = 0
        """)
        games = cur.fetchall()
        now = time.time()
        bot_enabled = int(get_setting_value('bot_enabled', '1')) == 1

        for game in games:
            game_id = game['id']
            stake = game['stake']
            countdown_started = game['countdown_started_at']
            if isinstance(countdown_started, str):
                countdown_started = float(countdown_started)
            elapsed = now - countdown_started
            remaining = max(0, GAME_START_DELAY_SECONDS - elapsed)

            if bot_enabled and remaining > 0:
                add_bots_to_waiting_game(game_id, stake)

            if remaining <= 0:
                # Count real players (user_id > 0)
                cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s AND user_id > 0", (game_id,))
                real_count = cur.fetchone()['cnt']
                if real_count >= 1:
                    cur.execute("UPDATE games SET status = 'running', last_draw_time = %s WHERE id = %s", (now, game_id))
                    conn.commit()
                    print(f"Game {game_id} started with {real_count} real players.")
                else:
                    # Cancel and refund all participants
                    cur.execute("SELECT user_id, COUNT(*) as cards FROM game_cards WHERE game_id = %s GROUP BY user_id", (game_id,))
                    for p in cur.fetchall():
                        refund = stake * p['cards']
                        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
                    cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s", (now, game_id))
                    conn.commit()
                    print(f"Game {game_id} cancelled (real players: {real_count})")
    except Exception as e:
        print(f"Error in process_waiting_games: {e}")
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

def draw_ball_for_running_game(game_id, max_balls=75):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT drawn_balls, prize_pool FROM games WHERE id = %s AND status = 'running'", (game_id,))
        game = cur.fetchone()
        if not game:
            return
        drawn = json.loads(game['drawn_balls'] or '[]')
        if len(drawn) >= max_balls:
            cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s", (time.time(), game_id))
            conn.commit()
            return
        new_ball = draw_ball(set(drawn))
        if not new_ball:
            return
        drawn.append(new_ball)
        cur.execute("UPDATE games SET drawn_balls = %s, last_draw_time = %s WHERE id = %s",
                    (json.dumps(drawn), time.time(), game_id))
        conn.commit()

        # Check winners
        cur.execute("SELECT user_id, card_data, card_number FROM game_cards WHERE game_id = %s", (game_id,))
        cards = cur.fetchall()
        winners = []
        drawn_set = set(drawn)
        for card in cards:
            card_data = card['card_data']
            if isinstance(card_data, str):
                card_data = json.loads(card_data)
            if check_bingo(card_data, drawn_set):
                winners.append(card['card_number'])
        if winners:
            owner_cut = int(get_setting_value('owner_cut_percent', '20'))
            total_prize = game['prize_pool']
            winners_prize = total_prize * (100 - owner_cut) / 100
            prize_per_winner = winners_prize / len(winners)
            for card_num in winners:
                cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND card_number = %s", (game_id, card_num))
                winner = cur.fetchone()
                if winner:
                    cur.execute("UPDATE players SET balance = balance + %s, wins = wins + 1, total_won = total_won + %s WHERE user_id = %s",
                                (prize_per_winner, prize_per_winner, winner['user_id']))
            cur.execute("UPDATE games SET status = 'finished', finished_at = %s, winner_card_numbers = %s WHERE id = %s",
                        (time.time(), json.dumps(winners), game_id))
            conn.commit()
            print(f"Game {game_id} finished. Winners: {winners}")
    except Exception as e:
        print(f"Error in draw_ball_for_running_game {game_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

def process_running_games():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, last_draw_time FROM games WHERE status = 'running'")
        games = cur.fetchall()
        now = time.time()
        for game in games:
            last_draw = game['last_draw_time']
            if isinstance(last_draw, str):
                last_draw = float(last_draw)
            if last_draw is None or (now - last_draw) >= BALL_DRAW_INTERVAL_SECONDS:
                draw_ball_for_running_game(game['id'])
    except Exception as e:
        print(f"Error in process_running_games: {e}")
    finally:
        cur.close()
        put_db(conn)

def game_loop():
    print("Game loop started in worker.")
    while True:
        try:
            process_waiting_games()
            process_running_games()
        except Exception as e:
            print(f"Game loop error: {e}")
        time.sleep(1)

if __name__ == '__main__':
    game_loop()
