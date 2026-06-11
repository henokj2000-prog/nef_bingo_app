import os
import sys
import time
import json
import random
import traceback
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from game.bingo_logic import draw_ball, check_bingo
from config import BALL_DRAW_INTERVAL_SECONDS, MAX_BALLS_PER_GAME, OWNER_CUT_PERCENT

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")
if "render.com" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

conn = None

def get_setting(key, default='0'):
    global conn
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        return row['value'] if row else default
    finally:
        cur.close()

def add_bot_to_game_direct(game_id, stake, db_conn):
    cur = db_conn.cursor()
    try:
        from game.bingo_logic import generate_card
        cur.execute("SELECT user_id FROM players WHERE user_id < 0")
        all_bots = [row['user_id'] for row in cur.fetchall()]
        if not all_bots:
            return False
        cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        used_bots = [row['user_id'] for row in cur.fetchall()]
        available = [bid for bid in all_bots if bid not in used_bots]
        if not available:
            return False
        bot_id = random.choice(available)
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        available_cards = [i for i in range(1, 501) if i not in taken]
        if not available_cards:
            return False
        card_num = random.choice(available_cards)
        cur.execute(
            "INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
            (game_id, bot_id, card_num, json.dumps(generate_card()))
        )
        cur.execute("UPDATE players SET balance = balance - %s, games_played = games_played + 1 WHERE user_id = %s", (stake, bot_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        db_conn.commit()
        return True
    except Exception as e:
        print(f"add_bot_to_game error: {e}")
        db_conn.rollback()
        return False
    finally:
        cur.close()

def draw_loop(game_id):
    global conn
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM games WHERE id = %s FOR UPDATE", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'running':
            return
        drawn = json.loads(game['drawn_balls'] or '[]')
        max_balls = int(get_setting('max_balls_per_game', str(MAX_BALLS_PER_GAME)))
        owner_cut = int(get_setting('owner_cut_percent', str(OWNER_CUT_PERCENT)))
        draws_attempted = 0
        while draws_attempted < max_balls:
            time.sleep(BALL_DRAW_INTERVAL_SECONDS)
            draws_attempted += 1
            cur.execute("SELECT * FROM games WHERE id = %s FOR UPDATE", (game_id,))
            game = cur.fetchone()
            if not game or game['status'] != 'running':
                break
            drawn = json.loads(game['drawn_balls'] or '[]')
            if len(drawn) >= max_balls:
                cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id}: max balls reached, no winner")
                ensure_waiting_game(game['stake'])
                return
            ball = draw_ball(drawn)
            if ball is None:
                cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id}: no balls left, finished")
                ensure_waiting_game(game['stake'])
                return
            drawn.append(ball)
            cur.execute("UPDATE games SET drawn_balls=%s WHERE id=%s", (json.dumps(drawn), game_id))
            conn.commit()
            print(f"Game {game_id}: ball {ball} drawn. Total: {len(drawn)}")

            # Bingo check using current drawn balls
            cur.execute("SELECT gc.user_id, gc.card_number, gc.card_data FROM game_cards gc WHERE gc.game_id=%s", (game_id,))
            cards = cur.fetchall()
            drawn_set = set(drawn)
            winners = []
            for card in cards:
                card_data = json.loads(card['card_data'])
                if check_bingo(card_data, drawn_set):
                    if card['user_id'] not in [w['user_id'] for w in winners]:
                        winners.append({'user_id': card['user_id'], 'card_number': card['card_number']})

            if winners:
                total_prize = game['prize_pool']
                owner_amount = total_prize * owner_cut / 100.0
                player_pool = total_prize - owner_amount
                prize_each = player_pool / len(winners)
                winner_card_numbers = [w['card_number'] for w in winners]
                cur.execute("UPDATE games SET winner_card_numbers=%s WHERE id=%s", (json.dumps(winner_card_numbers), game_id))
                for w in winners:
                    cur.execute("UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s", (prize_each, prize_each, w['user_id']))
                    # Referral commission
                    cur.execute("SELECT referred_by FROM players WHERE user_id=%s", (w['user_id'],))
                    ref = cur.fetchone()
                    if ref and ref['referred_by']:
                        comm_percent = int(get_setting('referral_commission_percent', '5'))
                        commission = prize_each * comm_percent / 100.0
                        if commission > 0:
                            cur.execute("INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at) VALUES (%s, %s, %s, %s, 'pending', %s)",
                                        (ref['referred_by'], w['user_id'], game_id, commission, time.time()))
                cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id} finished. Winners: {len(winners)} × {prize_each:.2f} ETB")
                ensure_waiting_game(game['stake'])
                return

        # No winner after max balls
        cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
        conn.commit()
        print(f"Game {game_id}: finished without winner after {max_balls} balls")
        ensure_waiting_game(game['stake'])
    except Exception as e:
        print(f"Error in draw_loop for game {game_id}: {e}")
        traceback.print_exc()
        conn.rollback()
    finally:
        cur.close()

def ensure_waiting_game(stake):
    """Check if there is a waiting game for this stake; if not, create one."""
    global conn
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' AND cancelled = 0 LIMIT 1", (stake,))
        existing = cur.fetchone()
        if not existing:
            cur.execute(
                "INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')",
                (stake, time.time())
            )
            conn.commit()
            print(f"Created a new waiting game for stake {stake} ETB")
    except Exception as e:
        print(f"Error ensuring waiting game: {e}")
        conn.rollback()
    finally:
        cur.close()

def main_loop():
    global conn
    print("Worker main loop started. Opening persistent connection...")
    conn = get_conn()
    last_bot_addition_time = 0
    while True:
        try:
            now = time.time()
            # No need to set autocommit – default is False
            cur = conn.cursor()
            cur.execute("BEGIN")
            cur.execute("""
                SELECT id, stake, created_at
                FROM games
                WHERE status = 'waiting' AND cancelled = 0 AND created_at <= %s
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """, (now - 30,))
            game = cur.fetchone()
            if not game:
                cur.execute("COMMIT")
                cur.close()
                time.sleep(1)
                continue
            game_id = game['id']
            stake = game['stake']
            # Count cards
            cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
            if cur.fetchone()['cnt'] == 0:
                cur.execute("UPDATE games SET status='finished', cancelled=1, finished_at=%s WHERE id=%s", (time.time(), game_id))
                cur.execute("COMMIT")
                cur.close()
                print(f"Game {game_id} cancelled: no players.")
                continue
            # Bot logic
            bot_enabled = get_setting('bot_enabled', '0') == '1'
            if bot_enabled:
                target_real = int(get_setting('bot_target_real_players', '2'))
                add_interval = int(get_setting('bot_addition_interval_seconds', '2'))
                bots_to_add = int(get_setting('bot_number_to_add', '1'))
                cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=%s AND user_id>0", (game_id,))
                real_count = cur.fetchone()['cnt']
                if real_count < target_real and (time.time() - last_bot_addition_time) >= add_interval:
                    added = 0
                    for _ in range(bots_to_add):
                        if add_bot_to_game_direct(game_id, stake, conn):
                            added += 1
                    if added:
                        print(f"Added {added} bot(s) to game {game_id} (real: {real_count}, target: {target_real})")
                    last_bot_addition_time = time.time()
            # Check total players
            cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=%s", (game_id,))
            total_players = cur.fetchone()['cnt']
            if total_players < 2:
                cur.execute("SELECT user_id, COUNT(*) as card_cnt FROM game_cards WHERE game_id=%s AND user_id>0 GROUP BY user_id", (game_id,))
                for p in cur.fetchall():
                    refund = stake * p['card_cnt']
                    cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
                cur.execute("UPDATE games SET status='finished', cancelled=1, finished_at=%s WHERE id=%s", (time.time(), game_id))
                cur.execute("COMMIT")
                cur.close()
                print(f"Game {game_id} cancelled: only {total_players} player(s), need at least 2. Refunded.")
                ensure_waiting_game(stake)
                continue
            # Start game
            cur.execute("UPDATE games SET status='running', started_at=%s WHERE id=%s AND status='waiting'", (time.time(), game_id))
            cur.execute("COMMIT")
            cur.close()
            # Run draw loop in thread
            threading.Thread(target=draw_loop, args=(game_id,), daemon=True).start()
        except Exception as e:
            print(f"Worker main loop error: {e}")
            traceback.print_exc()
            conn.rollback()
            time.sleep(1)

if __name__ == '__main__':
    from database import init_db, create_bot_players
    init_db()
    create_bot_players(20)
    main_loop()
