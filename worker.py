import sys
import time
import json
import random
import traceback

# Force stderr to be unbuffered so logs appear immediately
sys.stderr.reconfigure(line_buffering=True)
sys.stdout.reconfigure(line_buffering=True)

try:
    from database import get_db, put_db, init_db, create_bot_players, add_bot_to_game
    from game.bingo_logic import draw_ball, check_bingo
except Exception as import_err:
    print(f"IMPORT ERROR: {import_err}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

BALL_DRAW_INTERVAL_SECONDS = 2
MAX_BALLS_PER_GAME = 75
OWNER_CUT_PERCENT = 20

def ensure_min_players(game_id, stake):
    """Add bots if real players below minimum."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key='bot_enabled'")
        enabled = cur.fetchone()
        if not enabled or enabled['value'] != '1':
            return
        cur.execute("SELECT value FROM settings WHERE key='bot_min_players'")
        min_row = cur.fetchone()
        min_players = int(min_row['value']) if min_row else 2
        cur.execute("SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id=%s AND user_id > 0", (game_id,))
        real_players = cur.fetchone()['count']
        if real_players < min_players:
            add_bot_to_game(game_id, stake)
    except Exception as e:
        print(f"ensure_min_players error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    finally:
        cur.close()
        put_db(conn)

def draw_loop(game_id):
    """Main game loop with row locking and error handling."""
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
                    cur.execute("""
                        UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s
                        WHERE user_id=%s
                    """, (prize_per_winner, prize_per_winner, winner['user_id']))

                winner_card_numbers = [w['card_number'] for w in winners]
                cur.execute("""
                    UPDATE games SET status='finished', finished_at=%s, winner_card_numbers=%s
                    WHERE id=%s
                """, (time.time(), json.dumps(winner_card_numbers), game_id))
                conn.commit()
                print(f"Game {game_id} finished. Winners: {len(winners)} × {prize_per_winner} ETB")
                break
    except Exception as e:
        print(f"Error in game {game_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

def main_loop():
    """Main worker loop – picks up waiting games and runs them."""
    while True:
        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            now = time.time()
            cur.execute("""
                SELECT id, stake FROM games
                WHERE status = 'waiting' AND created_at <= %s
                ORDER BY id LIMIT 1
                FOR UPDATE SKIP LOCKED
            """, (now - 30,))
            game = cur.fetchone()
            cur.close()
            put_db(conn)
            conn = None

            if game:
                game_id = game['id']
                stake = game['stake']
                conn2 = get_db()
                cur2 = conn2.cursor()
                cur2.execute("UPDATE games SET status='running', started_at=%s WHERE id=%s AND status='waiting'", (time.time(), game_id))
                conn2.commit()
                cur2.close()
                put_db(conn2)
                ensure_min_players(game_id, stake)
                draw_loop(game_id)
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Worker main loop error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if conn:
                put_db(conn)
            time.sleep(10)

if __name__ == '__main__':
    try:
        print("Worker: Starting initialization...", file=sys.stderr)
        init_db()
        create_bot_players()
        print("Worker: Database initialized and bots created.", file=sys.stderr)
        print("Worker started – game engine running (2-second draws)", file=sys.stderr)
        main_loop()
    except Exception as e:
        print(f"FATAL: Worker failed to start: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Keep the process alive for a minute so Render logs capture the error
        time.sleep(60)
        sys.exit(1)
