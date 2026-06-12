import time
import json
import threading
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from game.bingo_logic import draw_ball, check_bingo
from config import DATABASE_URL, BOT_TOKEN, ADMIN_IDS, GAME_START_DELAY_SECONDS, BALL_DRAW_INTERVAL_SECONDS, BOT_ENABLED

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
    cur.execute("""
        SELECT DISTINCT p.user_id FROM game_cards gc
        JOIN players p ON p.user_id = gc.user_id
        WHERE gc.game_id = %s AND p.user_id > 0 AND p.bot_started = TRUE
    """, (game_id,))
    for row in cur.fetchall():
        send_telegram_message(row['user_id'], message)
    cur.close()
    conn.close()

def game_loop():
    while True:
        conn = get_conn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            now = time.time()

            # --- Bot addition logic ---
            if BOT_ENABLED:
                bot_enabled_setting = get_setting('bot_enabled')
                if bot_enabled_setting != '0':   # '1' or None → enabled
                    # Find waiting games that need bots
                    cur.execute("""
                        SELECT g.id, g.stake, g.created_at, 
                               (SELECT COUNT(DISTINCT gc2.user_id) FROM game_cards gc2 WHERE gc2.game_id = g.id AND gc2.user_id > 0) as real_players,
                               (SELECT COUNT(*) FROM game_cards gc2 WHERE gc2.game_id = g.id AND gc2.user_id < 0) as bot_players
                        FROM games g
                        WHERE g.status = 'waiting' AND g.cancelled = 0
                        AND g.created_at + 30 > %s
                    """, (now,))
                    for game in cur.fetchall():
                        target_real = int(get_setting('bot_target_real_players') or 2)
                        bot_number_to_add = int(get_setting('bot_number_to_add') or 1)
                        if game['real_players'] < target_real:
                            # Add bots one by one, respecting interval
                            last_bot_time = get_setting('last_bot_time_' + str(game['id']))
                            if last_bot_time:
                                last_bot_time = float(last_bot_time)
                            else:
                                last_bot_time = 0
                            interval = float(get_setting('bot_addition_interval_seconds') or 2)
                            if now - last_bot_time >= interval:
                                # Add a single bot
                                bot_user_id = add_bot_to_game(game['id'])
                                if bot_user_id:
                                    # Record the time
                                    conn2 = get_conn()
                                    cur2 = conn2.cursor()
                                    cur2.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                                                ('last_bot_time_' + str(game['id']), str(now), str(now)))
                                    conn2.commit()
                                    cur2.close()
                                    conn2.close()

            # 1. START waiting games whose countdown has expired
            cur.execute("""
                SELECT id, stake, prize_pool, created_at
                FROM games
                WHERE status = 'waiting' AND cancelled = 0
                AND created_at + %s <= %s
            """, (GAME_START_DELAY_SECONDS, now))
            for game in cur.fetchall():
                # Count real players
                if ADMIN_IDS and len(ADMIN_IDS) > 0:
                    cur.execute("""
                        SELECT COUNT(DISTINCT gc.user_id) as real_players
                        FROM game_cards gc
                        JOIN players p ON p.user_id = gc.user_id
                        WHERE gc.game_id = %s AND p.user_id > 0 AND p.user_id NOT IN %s
                    """, (game['id'], tuple(ADMIN_IDS)))
                else:
                    cur.execute("""
                        SELECT COUNT(DISTINCT gc.user_id) as real_players
                        FROM game_cards gc
                        JOIN players p ON p.user_id = gc.user_id
                        WHERE gc.game_id = %s AND p.user_id > 0
                    """, (game['id'],))
                real = cur.fetchone()['real_players']

                min_players = int(get_setting('min_real_players') or 2)
                if real < min_players:
                    cur.execute("""
                        UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    cur.execute("""
                        UPDATE players SET balance = balance + %s * (
                            SELECT COUNT(*) FROM game_cards WHERE game_id = %s AND user_id = players.user_id
                        )
                        WHERE user_id IN (SELECT user_id FROM game_cards WHERE game_id = %s)
                    """, (game['stake'], game['id'], game['id']))
                    conn.commit()
                else:
                    cur.execute("""
                        UPDATE games SET status = 'running', last_draw_time = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    conn.commit()

            # 2. Process RUNNING games
            cur.execute("""
                SELECT id, stake, prize_pool, drawn_balls, last_draw_time
                FROM games WHERE status = 'running'
            """)
            for game in cur.fetchall():
                if game['last_draw_time'] and (now - game['last_draw_time']) < BALL_DRAW_INTERVAL_SECONDS:
                    continue
                drawn = set(json.loads(game['drawn_balls'] or '[]'))
                max_balls = int(get_setting('max_balls_per_game') or 75)

                new_ball = draw_ball(drawn)
                if new_ball:
                    drawn.add(new_ball)
                    cur.execute("""
                        UPDATE games SET drawn_balls = %s, last_draw_time = %s
                        WHERE id = %s
                    """, (json.dumps(list(drawn)), now, game['id']))
                    conn.commit()

                    cur.execute("""
                        SELECT gc.user_id, gc.card_data, gc.card_number
                        FROM game_cards gc WHERE gc.game_id = %s
                    """, (game['id'],))
                    winners = []
                    for row in cur.fetchall():
                        card = json.loads(row['card_data'])
                        if check_bingo(card, drawn):
                            winners.append((row['user_id'], row['card_number']))
                    if winners:
                        owner_cut_pct = int(get_setting('owner_cut_percent') or 20)
                        share = round(game['prize_pool'] * (100 - owner_cut_pct) / 100 / len(winners), 2)
                        for uid, _ in winners:
                            cur.execute("""
                                UPDATE players SET balance = balance + %s, wins = wins + 1, total_won = total_won + %s
                                WHERE user_id = %s
                            """, (share, share, uid))
                        cur.execute("""
                            UPDATE games SET status = 'finished', winner_card_numbers = %s, finished_at = %s
                            WHERE id = %s
                        """, (json.dumps([w[1] for w in winners]), now, game['id']))
                        conn.commit()
                        break
                    elif len(drawn) >= max_balls:
                        cur.execute("""
                            UPDATE games SET status = 'finished', winner_card_numbers = '[]', finished_at = %s
                            WHERE id = %s
                        """, (now, game['id']))
                        conn.commit()
                else:
                    cur.execute("""
                        UPDATE games SET status = 'finished', finished_at = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    conn.commit()

            # 3. Clean up empty waiting games older than 30s
            cur.execute("""
                SELECT id FROM games
                WHERE status = 'waiting' AND created_at + %s <= %s
            """, (GAME_START_DELAY_SECONDS, now))
            for row in cur.fetchall():
                cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s", (row['id'],))
                if cur.fetchone()['cnt'] == 0:
                    cur.execute("DELETE FROM games WHERE id = %s", (row['id'],))
                    conn.commit()

        except Exception as e:
            print(f"Worker error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
        time.sleep(0.5)

if __name__ == "__main__":
    # Import add_bot_to_game function here to avoid circular import
    from database import add_bot_to_game
    print("Game engine worker started...")
    game_loop()
