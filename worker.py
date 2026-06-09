import sys
import time
import json
import random
import threading
import traceback
from database import get_db, put_db, init_db, create_bot_players, add_bot_to_game, remove_bot_from_game
from game.bingo_logic import draw_ball, check_bingo

BALL_DRAW_INTERVAL_SECONDS = 2
MAX_BALLS_PER_GAME = 75
OWNER_CUT_PERCENT = 20

def adjust_bots_gradually(game_id, stake, target_real, interval_seconds, stop_event):
    """Add bots one by one every interval_seconds until target is reached or stop_event is set."""
    while not stop_event.is_set():
        conn = get_db()
        cur = conn.cursor()
        try:
            # Check current real player count
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id=%s AND user_id > 0", (game_id,))
            real_count = cur.fetchone()['count']
            if real_count >= target_real:
                print(f"Game {game_id}: target real players ({target_real}) reached. Stopping bot addition.")
                break
            # Add one bot
            added = add_bot_to_game(game_id, stake)
            if added:
                print(f"Game {game_id}: added one bot (real players now {real_count+1}/{target_real})")
            else:
                print(f"Game {game_id}: no bots available to add")
                break
        except Exception as e:
            print(f"Error in gradual bot addition for game {game_id}: {e}")
            traceback.print_exc()
        finally:
            cur.close()
            put_db(conn)
        # Wait for the interval, but check stop_event frequently
        for _ in range(int(interval_seconds * 2)):
            if stop_event.is_set():
                break
            time.sleep(0.5)

def main_loop():
    while True:
        print("Worker main loop running...")
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            # Pick any waiting game, regardless of age (we will handle remaining time internally)
            cur.execute("""
                SELECT id, stake, created_at FROM games
                WHERE status = 'waiting'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
            game = cur.fetchone()
            cur.close()
            put_db(conn)
            conn = None

            if game:
                game_id = game['id']
                stake = game['stake']
                created_at = game['created_at']
                now = time.time()
                remaining = max(0, 30 - (now - created_at))
                print(f"Game {game_id}: remaining countdown: {remaining:.1f} seconds")

                if remaining <= 0:
                    # Immediately start the game (no countdown left)
                    start_game(game_id, stake)
                else:
                    # Wait for the remaining time while adding bots gradually
                    # Get settings
                    conn2 = get_db()
                    cur2 = conn2.cursor()
                    cur2.execute("SELECT value FROM settings WHERE key='bot_target_real_players'")
                    target_row = cur2.fetchone()
                    target_real = int(target_row['value']) if target_row else 2
                    cur2.execute("SELECT value FROM settings WHERE key='bot_addition_interval_seconds'")
                    interval_row = cur2.fetchone()
                    interval = float(interval_row['value']) if interval_row else 2.0
                    cur2.execute("SELECT value FROM settings WHERE key='bot_remove_excess'")
                    remove_excess_row = cur2.fetchone()
                    remove_excess = int(remove_excess_row['value']) if remove_excess_row else 1
                    cur2.close()
                    put_db(conn2)

                    # Start background bot adder
                    stop_event = threading.Event()
                    bot_thread = threading.Thread(target=adjust_bots_gradually, args=(game_id, stake, target_real, interval, stop_event))
                    bot_thread.daemon = True
                    bot_thread.start()

                    # Wait for the remaining countdown
                    time.sleep(remaining)

                    # Stop bot addition
                    stop_event.set()
                    bot_thread.join(timeout=1)

                    # Final adjustment: remove excess bots if configured
                    if remove_excess:
                        # Count real players again
                        conn3 = get_db()
                        cur3 = conn3.cursor()
                        cur3.execute("SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id=%s AND user_id > 0", (game_id,))
                        real_count = cur3.fetchone()['count']
                        if real_count > target_real:
                            # Remove extra bots
                            cur3.execute("SELECT user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
                            bot_ids = [row['user_id'] for row in cur3.fetchall()]
                            for bot_id in bot_ids:
                                if real_count <= target_real:
                                    break
                                remove_bot_from_game(game_id, bot_id)
                                real_count -= 1
                        cur3.close()
                        put_db(conn3)

                    # Start the game
                    start_game(game_id, stake)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"Worker main loop error: {e}")
            traceback.print_exc()
            if conn:
                put_db(conn)
            time.sleep(5)

def start_game(game_id, stake):
    """Mark game as running and start the draw loop."""
    conn = get_db()
    cur = conn.cursor()
    try:
        # Lock and check that game is still waiting
        cur.execute("SELECT status FROM games WHERE id=%s FOR UPDATE", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'waiting':
            return
        cur.execute("UPDATE games SET status='running', started_at=%s WHERE id=%s", (time.time(), game_id))
        conn.commit()
        print(f"Game {game_id} started with {count_players_in_game(game_id)} players.")
    except Exception as e:
        print(f"Error starting game {game_id}: {e}")
        return
    finally:
        cur.close()
        put_db(conn)
    draw_loop(game_id)

def draw_loop(game_id):
    """Main game loop – same as before."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM games WHERE id = %s FOR UPDATE", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'running':
            return
        conn.commit()

        while True:
            time.sleep(BALL_DRAW_INTERVAL_SECONDS)
            cur.execute("SELECT * FROM games WHERE id = %s FOR UPDATE", (game_id,))
            game = cur.fetchone()
            if not game or game['status'] != 'running':
                break

            drawn = json.loads(game['drawn_balls'])
            if len(drawn) >= MAX_BALLS_PER_GAME:
                cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
                conn.commit()
                print(f"Game {game_id}: max balls reached, no winner")
                break

            ball = draw_ball(drawn)
            if ball is None:
                cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
                conn.commit()
                break

            drawn.append(ball)
            cur.execute("UPDATE games SET drawn_balls=%s WHERE id=%s", (json.dumps(drawn), game_id))
            conn.commit()

            cur.execute("SELECT * FROM game_cards WHERE game_id=%s", (game_id,))
            cards = cur.fetchall()
            winners = []
            for c in cards:
                card_data = json.loads(c['card_data'])
                if check_bingo(card_data, set(drawn)):
                    winners.append(c)

            if winners:
                total_pot = game['prize_pool']
                cur.execute("SELECT value FROM settings WHERE key='owner_cut_percent'")
                row = cur.fetchone()
                owner_cut = float(row['value']) if row else OWNER_CUT_PERCENT
                winner_share = round(total_pot * (100 - owner_cut) / 100, 2)
                prize_per_winner = round(winner_share / len(winners), 2)

                for winner in winners:
                    cur.execute("SELECT referred_by FROM players WHERE user_id=%s", (winner['user_id'],))
                    ref = cur.fetchone()
                    if ref and ref['referred_by']:
                        cur.execute("SELECT value FROM settings WHERE key='referral_commission_percent'")
                        comm_row = cur.fetchone()
                        comm_percent = float(comm_row['value']) if comm_row else 5.0
                        commission = round(prize_per_winner * (comm_percent / 100), 2)
                        cur.execute("""
                            INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at)
                            VALUES (%s, %s, %s, %s, 'pending', %s)
                        """, (ref['referred_by'], winner['user_id'], game_id, commission, time.time()))

                for winner in winners:
                    cur.execute("UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s",
                                (prize_per_winner, prize_per_winner, winner['user_id']))

                winner_card_numbers = [w['card_number'] for w in winners]
                cur.execute("UPDATE games SET status='finished', finished_at=%s, winner_card_numbers=%s WHERE id=%s",
                            (time.time(), json.dumps(winner_card_numbers), game_id))
                conn.commit()
                print(f"Game {game_id} finished. Winners: {len(winners)} × {prize_per_winner} ETB")
                break
    except Exception as e:
        print(f"Error in game {game_id}: {e}")
        traceback.print_exc()
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

if __name__ == '__main__':
    init_db()
    create_bot_players()
    print("Worker started – gradual bot addition enabled")
    main_loop()
