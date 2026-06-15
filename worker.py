import time
import json
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
from game.bingo_logic import draw_ball, check_bingo, generate_card
from config import DATABASE_URL, BOT_TOKEN, ADMIN_IDS, GAME_START_DELAY_SECONDS, BALL_DRAW_INTERVAL_SECONDS

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

def add_bot_to_game(game_id, stake):
    """Add one bot to the given waiting game. Returns True if successful."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Pick a bot not already in this game
        cur.execute("""
            SELECT p.user_id FROM players p
            WHERE p.user_id < 0
              AND NOT EXISTS (
                  SELECT 1 FROM game_cards gc
                  WHERE gc.game_id = %s AND gc.user_id = p.user_id
              )
            ORDER BY p.user_id ASC
            LIMIT 1
        """, (game_id,))
        bot = cur.fetchone()
        if not bot:
            return False
        bot_id = bot['user_id']

        # Find a free card number
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = {row['card_number'] for row in cur.fetchall()}
        import random
        candidate = None
        for _ in range(100):
            candidate = random.randint(1, 500)
            if candidate not in taken:
                break
        if candidate is None:
            return False

        card_data = generate_card()
        cur.execute(
            "INSERT INTO game_cards (game_id, user_id, card_number, card) VALUES (%s, %s, %s, %s)",
            (game_id, bot_id, candidate, json.dumps(card_data))
        )
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Bot add error: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def game_loop():
    print("Worker started – waiting for games...")
    while True:
        conn = get_conn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            now = datetime.utcnow()

            # ---- 1. Add bots to waiting games (only if bot_enabled) ----
            bot_enabled = get_setting('bot_enabled')
            if bot_enabled == '1':
                cur.execute("""
                    SELECT g.id, g.stake,
                           (SELECT COUNT(DISTINCT gc.user_id) FROM game_cards gc WHERE gc.game_id = g.id AND gc.user_id > 0) as real_players
                    FROM games g
                    WHERE g.status = 'waiting' AND g.cancelled = 0
                      AND g.created_at + interval '30 seconds' < %s
                """, (now,))
                for game in cur.fetchall():
                    target_real = int(get_setting('bot_target_real_players') or 2)
                    if game['real_players'] < target_real:
                        bots_to_add = int(get_setting('bot_number_to_add') or 1)
                        for _ in range(bots_to_add):
                            add_bot_to_game(game['id'], game['stake'])

            # ---- 2. Handle expired waiting games (start or cancel) ----
            cur.execute("""
                SELECT id, stake, prize_pool, created_at
                FROM games
                WHERE status = 'waiting' AND cancelled = 0
                  AND created_at + interval '1 second' * %s <= %s
            """, (GAME_START_DELAY_SECONDS, now))

            expired_games = cur.fetchall()
            for game in expired_games:
                # Add bots one last time before deciding
                if bot_enabled == '1':
                    cur.execute("""
                        SELECT COUNT(DISTINCT gc.user_id) as real_players
                        FROM game_cards gc
                        WHERE gc.game_id = %s AND gc.user_id > 0
                    """, (game['id'],))
                    real_now = cur.fetchone()['real_players']
                    target_real = int(get_setting('bot_target_real_players') or 2)
                    if real_now < target_real:
                        bots_to_add = int(get_setting('bot_number_to_add') or 1)
                        for _ in range(bots_to_add):
                            add_bot_to_game(game['id'], game['stake'])

                # Count real players (exclude admins)
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
                print(f"Game #{game['id']} – real players: {real}, min required: {min_players}")

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
                    print(f"Game #{game['id']} cancelled (not enough real players).")
                else:
                    cur.execute("""
                        UPDATE games SET status = 'running', last_draw_time = %s
                        WHERE id = %s
                    """, (now, game['id']))
                    conn.commit()
                    print(f"Game #{game['id']} started!")

            # ---- 3. Process running games (draw balls) ----
            cur.execute("""
                SELECT id, stake, prize_pool, drawn_balls, last_draw_time
                FROM games WHERE status = 'running'
            """)
            for game in cur.fetchall():
                if game['last_draw_time'] and (now - game['last_draw_time']).total_seconds() < BALL_DRAW_INTERVAL_SECONDS:
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
                        SELECT gc.user_id, gc.card, gc.card_number
                        FROM game_cards gc WHERE gc.game_id = %s
                    """, (game['id'],))
                    winners = []
                    for row in cur.fetchall():
                        card = row['card'] if isinstance(row['card'], dict) else json.loads(row['card'])
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

            # ---- 4. Clean up empty waiting games older than delay ----
            cur.execute("""
                SELECT id FROM games
                WHERE status = 'waiting' AND created_at + interval '1 second' * %s <= %s
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
    game_loop()
