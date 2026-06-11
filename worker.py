import os
import sys
import time
import json
import random
import traceback
import threading
from database import get_db, put_db, add_bot_to_game
from game.bingo_logic import draw_ball, check_bingo
from config import BALL_DRAW_INTERVAL_SECONDS, MAX_BALLS_PER_GAME, OWNER_CUT_PERCENT

# ---------- Helper: get a setting value from database ----------
def get_setting(key, default='0'):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        return row['value'] if row else default
    finally:
        cur.close()
        put_db(conn)

# ---------- Main loop: watches for waiting games and starts them ----------
def main_loop():
    print("Worker main loop started.")
    last_bot_addition_time = 0

    while True:
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            now = time.time()

            # Start transaction and lock the oldest waiting game (SKIP LOCKED for concurrency)
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
                time.sleep(5)
                continue

            game_id = game['id']
            stake = game['stake']

            # ----- 1. Check if any cards exist -----
            cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
            if cur.fetchone()['cnt'] == 0:
                cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s",
                            (time.time(), game_id))
                cur.execute("COMMIT")
                print(f"Game {game_id} cancelled: no players.")
                continue

            # ----- 2. Bot logic (only if enabled) -----
            bot_enabled = get_setting('bot_enabled', '0') == '1'
            if bot_enabled:
                # Read settings
                min_players = int(get_setting('bot_min_players', '2'))
                target_real = int(get_setting('bot_target_real_players', '2'))
                add_interval = int(get_setting('bot_addition_interval_seconds', '2'))
                bots_to_add = int(get_setting('bot_number_to_add', '1'))
                remove_excess = get_setting('bot_remove_excess', '1') == '1'

                # Count real players (user_id > 0)
                cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s AND user_id > 0", (game_id,))
                real_count = cur.fetchone()['cnt']

                # Gradual addition of bots (only if we haven't reached target real players)
                if real_count < target_real:
                    if now - last_bot_addition_time >= add_interval:
                        added = 0
                        for _ in range(bots_to_add):
                            if add_bot_to_game(game_id, stake, conn=conn):
                                added += 1
                        if added:
                            print(f"Added {added} bot(s) to game {game_id} (real: {real_count}, target: {target_real})")
                        last_bot_addition_time = now
                # Remove excess bots if target real players reached
                elif remove_excess and real_count >= target_real:
                    cur.execute("SELECT user_id, card_number FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
                    bot_cards = cur.fetchall()
                    for bc in bot_cards:
                        cur.execute("DELETE FROM game_cards WHERE game_id = %s AND user_id = %s AND card_number = %s",
                                    (game_id, bc['user_id'], bc['card_number']))
                    if bot_cards:
                        print(f"Removed {len(bot_cards)} bot card(s) from game {game_id} (real players reached target)")

            # ----- 3. Check total players (real + bots) -----
            cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
            total_players = cur.fetchone()['cnt']

            if total_players < 2:
                # Refund all real players
                cur.execute("SELECT user_id, COUNT(*) as card_cnt FROM game_cards WHERE game_id = %s AND user_id > 0 GROUP BY user_id", (game_id,))
                players = cur.fetchall()
                for p in players:
                    refund = stake * p['card_cnt']
                    cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
                    print(f"Refunded {refund} ETB to player {p['user_id']} for game {game_id}")
                cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s",
                            (time.time(), game_id))
                cur.execute("COMMIT")
                print(f"Game {game_id} cancelled: only {total_players} player(s), need at least 2. Refunded all.")
                continue

            # ----- 4. Start the game -----
            cur.execute("UPDATE games SET status = 'running', started_at = %s WHERE id = %s AND status = 'waiting'",
                        (time.time(), game_id))
            cur.execute("COMMIT")
            cur.close()
            put_db(conn)
            conn = None

            # Run the draw loop for this game (in a separate thread to allow concurrent games)
            threading.Thread(target=draw_loop, args=(game_id,), daemon=True).start()

        except Exception as e:
            print(f"Worker main loop error: {e}")
            traceback.print_exc()
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            if conn:
                put_db(conn)
            time.sleep(10)

# ---------- Draw loop for a single game (runs until finished) ----------
def draw_loop(game_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        # Verify game still exists and is running
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

            # Refresh game status (it may have been finished elsewhere)
            cur.execute("SELECT * FROM games WHERE id = %s FOR UPDATE", (game_id,))
            game = cur.fetchone()
            if not game or game['status'] != 'running':
                break

            drawn = json.loads(game['drawn_balls'] or '[]')
            if len(drawn) >= max_balls:
                # Max balls reached, finish without winner
                cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s",
                            (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id}: max balls reached, no winner")
                return

            # Draw next ball
            ball = draw_ball(drawn)
            if ball is None:
                # No more balls left in the universe
                cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s",
                            (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id}: no balls left, finished without winner")
                return

            drawn.append(ball)
            cur.execute("UPDATE games SET drawn_balls = %s WHERE id = %s", (json.dumps(drawn), game_id))
            conn.commit()
            print(f"Game {game_id}: ball {ball} drawn. Total drawn: {len(drawn)}")

            # ----- Check for bingo -----
            # Get all cards with their marked numbers
            cur.execute("""
                SELECT gc.user_id, gc.card_number, gc.card_data, gc.marked_numbers
                FROM game_cards gc
                WHERE gc.game_id = %s
            """, (game_id,))
            cards = cur.fetchall()

            winners = []
            for card in cards:
                marked = json.loads(card['marked_numbers'] or '[]')
                card_data = json.loads(card['card_data'])
                if check_bingo(card_data, marked):
                    # Only add if not already marked as winner (prevent duplicate)
                    if card['user_id'] not in [w['user_id'] for w in winners]:
                        winners.append({
                            'user_id': card['user_id'],
                            'card_number': card['card_number']
                        })

            if winners:
                # Calculate prizes
                total_prize_pool = game['prize_pool']
                owner_amount = total_prize_pool * owner_cut / 100.0
                player_pool = total_prize_pool - owner_amount
                prize_per_winner = player_pool / len(winners)

                # Record winner card numbers
                winner_card_numbers = [w['card_number'] for w in winners]
                cur.execute("UPDATE games SET winner_card_numbers = %s WHERE id = %s",
                            (json.dumps(winner_card_numbers), game_id))

                # Pay each winner
                for winner in winners:
                    cur.execute("UPDATE players SET balance = balance + %s, wins = wins + 1, total_won = total_won + %s WHERE user_id = %s",
                                (prize_per_winner, prize_per_winner, winner['user_id']))

                    # --- Referral commission for the referrer ---
                    cur.execute("SELECT referred_by FROM players WHERE user_id = %s", (winner['user_id'],))
                    ref = cur.fetchone()
                    if ref and ref['referred_by']:
                        commission_percent = int(get_setting('referral_commission_percent', '5'))
                        commission = prize_per_winner * commission_percent / 100.0
                        if commission > 0:
                            cur.execute("""
                                INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at)
                                VALUES (%s, %s, %s, %s, 'pending', %s)
                            """, (ref['referred_by'], winner['user_id'], game_id, commission, time.time()))
                            print(f"Commission {commission} ETB recorded for referrer {ref['referred_by']}")

                # Mark game as finished
                cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s",
                            (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id} finished. Winners: {len(winners)} × {prize_per_winner:.2f} ETB")
                return

        # If we exit the loop without returning (e.g., max balls reached without bingo)
        cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s",
                    (time.time(), game_id))
        conn.commit()
        print(f"Game {game_id}: finished without winner after {max_balls} balls")

    except Exception as e:
        print(f"Error in draw_loop for game {game_id}: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            put_db(conn)

# ---------- Start the worker if run directly ----------
if __name__ == '__main__':
    # Ensure database tables are initialized (if not already done by Flask)
    from database import init_db, create_bot_players
    init_db()
    create_bot_players(20)
    main_loop()
