import sys
import time
import json
import random
import traceback
from database import get_db, put_db, init_db, create_bot_players, add_bot_to_game, count_players_in_game
from game.bingo_logic import draw_ball, check_bingo

BALL_DRAW_INTERVAL_SECONDS = 2
MAX_BALLS_PER_GAME = 75
OWNER_CUT_PERCENT = 20

def main_loop():
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

                # 1. Check if there are any cards at all
                cur2.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id=%s", (game_id,))
                if cur2.fetchone()['cnt'] == 0:
                    cur2.execute("UPDATE games SET status='finished', cancelled=1, finished_at=%s WHERE id=%s", (time.time(), game_id))
                    conn2.commit()
                    cur2.close()
                    put_db(conn2)
                    print(f"Game {game_id} cancelled: no players.")
                    continue

                # 2. ADD BOTS FIRST (before checking total players)
                cur2.execute("SELECT value FROM settings WHERE key='bot_enabled'")
                enabled = cur2.fetchone()
                if enabled and enabled['value'] == '1':
                    cur2.execute("SELECT value FROM settings WHERE key='bot_min_players'")
                    min_row = cur2.fetchone()
                    min_players = int(min_row['value']) if min_row else 2
                    cur2.execute("SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id=%s AND user_id > 0", (game_id,))
                    real_count = cur2.fetchone()['count']
                    if real_count < min_players:
                        cur2.execute("SELECT value FROM settings WHERE key='bot_number_to_add'")
                        num_row = cur2.fetchone()
                        bots_to_add = int(num_row['value']) if num_row else 1
                        for _ in range(bots_to_add):
                            add_bot_to_game(game_id, stake)
                        print(f"Added {bots_to_add} bot(s) to game {game_id} (real players: {real_count}, needed: {min_players})")

                # 3. Now check total players (real + bots)
                cur2.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=%s", (game_id,))
                total_players = cur2.fetchone()['cnt']
                if total_players < 2:
                    # REFUND ALL PLAYERS BEFORE CANCELLING
                    cur2.execute("SELECT user_id, COUNT(*) as card_cnt FROM game_cards WHERE game_id=%s GROUP BY user_id", (game_id,))
                    players = cur2.fetchall()
                    for p in players:
                        refund = stake * p['card_cnt']
                        cur2.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
                        print(f"Refunded {refund} ETB to player {p['user_id']} for game {game_id}")
                    cur2.execute("UPDATE games SET status='finished', cancelled=1, finished_at=%s WHERE id=%s", (time.time(), game_id))
                    conn2.commit()
                    cur2.close()
                    put_db(conn2)
                    print(f"Game {game_id} cancelled: only {total_players} player(s), need at least 2. Refunded all.")
                    continue

                # 4. Start the game
                cur2.execute("UPDATE games SET status='running', started_at=%s WHERE id=%s AND status='waiting'", (time.time(), game_id))
                conn2.commit()
                cur2.close()
                put_db(conn2)
                draw_loop(game_id)
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Worker main loop error: {e}")
            traceback.print_exc()
            if conn:
                put_db(conn)
            time.sleep(10)

def draw_loop(game_id):
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
    print("Worker started – game engine running (2-second draws)")
    main_loop()
