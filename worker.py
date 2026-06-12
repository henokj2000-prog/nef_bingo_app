import time
import json
import threading
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from game.bingo_logic import draw_ball, check_bingo  # reuse from app.py
from config import DATABASE_URL, BOT_TOKEN, ADMIN_IDS

# ---------- DB helpers (same as database.py but here for worker) ----------
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def get_setting(key):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row['value'] if row else None

# ---------- Telegram notification (optional) ----------
def send_telegram_message(chat_id, text):
    import requests
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=2)
    except Exception:
        pass

def notify_players(game_id, message):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Get all user_ids in this game (real users only)
    cur.execute("""
        SELECT DISTINCT p.user_id FROM game_cards gc
        JOIN players p ON p.user_id = gc.user_id
        WHERE gc.game_id = %s AND p.user_id > 0
    """, (game_id,))
    for row in cur.fetchall():
        # In a real system, map user_id -> Telegram chat_id (store in players table)
        # For now, skip or assume chat_id = user_id (if user_id is Telegram ID)
        send_telegram_message(row['user_id'], message)
    cur.close()
    conn.close()

# ---------- Main game loop ----------
def game_loop():
    while True:
        conn = get_conn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            now = time.time()

            # 1. START waiting games whose countdown has expired
            cur.execute("""
                SELECT id, stake, prize_pool, created_at
                FROM games
                WHERE status = 'waiting' AND cancelled = 0
                AND created_at + 30 <= %s
            """, (now,))
            for game in cur.fetchall():
                # Check if at least 2 real players have picked cards
                cur.execute("""
                    SELECT COUNT(DISTINCT gc.user_id) as real_players
                    FROM game_cards gc
                    JOIN players p ON p.user_id = gc.user_id
                    WHERE gc.game_id = %s AND p.user_id > 0 AND p.user_id NOT IN %s
                """, (game['id'], tuple(ADMIN_IDS)))
                real = cur.fetchone()['real_players']
                if real < 2:
                    # Cancel game, refund players
                    cur.execute("""
                        UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    # Refund stakes
                    cur.execute("""
                        UPDATE players SET balance = balance + %s * (
                            SELECT COUNT(*) FROM game_cards WHERE game_id = %s AND user_id = players.user_id
                        )
                        WHERE user_id IN (SELECT user_id FROM game_cards WHERE game_id = %s)
                    """, (game['stake'], game['id'], game['id']))
                    conn.commit()
                else:
                    # Start the game
                    cur.execute("""
                        UPDATE games SET status = 'running', last_draw_time = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    conn.commit()
                    # Notify players (optional)
                    # notify_players(game['id'], "🎲 Game has started! Numbers are being drawn.")

            # 2. Process RUNNING games
            cur.execute("""
                SELECT id, stake, prize_pool, drawn_balls, last_draw_time
                FROM games
                WHERE status = 'running'
            """)
            for game in cur.fetchall():
                draw_interval = 2  # seconds between balls
                if game['last_draw_time'] and (now - game['last_draw_time']) < draw_interval:
                    continue   # not time to draw yet

                drawn = set(json.loads(game['drawn_balls'] or '[]'))
                max_balls = int(get_setting('max_balls_per_game') or 75)

                # Draw a ball
                new_ball = draw_ball(drawn)
                if new_ball:
                    drawn.add(new_ball)
                    cur.execute("""
                        UPDATE games
                        SET drawn_balls = %s, last_draw_time = %s
                        WHERE id = %s
                    """, (json.dumps(list(drawn)), now, game['id']))
                    conn.commit()

                    # Check for winners
                    cur.execute("""
                        SELECT gc.user_id, gc.card_data, gc.card_number
                        FROM game_cards gc
                        WHERE gc.game_id = %s
                    """, (game['id'],))
                    winners = []
                    for row in cur.fetchall():
                        card = json.loads(row['card_data'])
                        if check_bingo(card, drawn):
                            winners.append((row['user_id'], row['card_number']))

                    if winners:
                        # Calculate owner cut (e.g., 20%)
                        owner_cut_pct = int(get_setting('owner_cut_percent') or 20)
                        winners_share = round(game['prize_pool'] * (100 - owner_cut_pct) / 100 / len(winners), 2)
                        winner_card_numbers = [w[1] for w in winners]

                        # Pay winners
                        for uid, _ in winners:
                            cur.execute("""
                                UPDATE players
                                SET balance = balance + %s,
                                    wins = wins + 1,
                                    total_won = total_won + %s
                                WHERE user_id = %s
                            """, (winners_share, winners_share, uid))
                        # Owner profit is automatically the remaining prize_pool - what winners got
                        # (prize_pool - winners_share * len(winners) stays in the game record as house profit)

                        # Finish game
                        cur.execute("""
                            UPDATE games
                            SET status = 'finished',
                                winner_card_numbers = %s,
                                finished_at = %s
                            WHERE id = %s
                        """, (json.dumps(winner_card_numbers), now, game['id']))
                        conn.commit()

                        # Notify players (optional)
                        # for uid, _ in winners:
                        #     send_telegram_message(uid, f"🏆 BINGO! You won {winners_share} ETB!")
                        # notify_players(game['id'], f"Game #{game['id']} ended. Congratulations to the winner(s)!")
                        break   # stop processing this game, it's over

                    elif len(drawn) >= max_balls:
                        # No winner, finish game
                        cur.execute("""
                            UPDATE games
                            SET status = 'finished', winner_card_numbers = '[]', finished_at = %s
                            WHERE id = %s
                        """, (now, game['id']))
                        conn.commit()
                        # notify_players(game['id'], "All numbers drawn. No winner this round.")
                else:
                    # No balls left to draw (shouldn't happen, but finish)
                    cur.execute("""
                        UPDATE games
                        SET status = 'finished', finished_at = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    conn.commit()

            # 3. Clean up empty waiting games older than 30s
            cur.execute("""
                SELECT id FROM games
                WHERE status = 'waiting' AND created_at + 30 <= %s
            """, (now,))
            for row in cur.fetchall():
                cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s", (row['id'],))
                if cur.fetchone()['cnt'] == 0:
                    cur.execute("DELETE FROM games WHERE id = %s", (row['id'],))
                    conn.commit()

        except Exception as e:
            print(f"Worker error: {e}")
        finally:
            cur.close()
            conn.close()

        time.sleep(0.5)   # loop every 500ms for responsiveness

if __name__ == "__main__":
    print("Game engine worker started...")
    game_loop()
