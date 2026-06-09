import os
import time
import json
import secrets
import string
import random
import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

if "render.com" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

# Use connection pooling for better performance
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
except OperationalError as e:
    print(f"Failed to create pool: {e}")
    db_pool = None

def get_db():
    if db_pool:
        return db_pool.getconn()
    else:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def put_db(conn):
    if db_pool:
        db_pool.putconn(conn)
    else:
        conn.close()

def init_db():

    conn = get_db()
    cur = conn.cursor()
    # ... (your existing init_db code, unchanged)
    # Add the new settings if not exist
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_target_real_players', '2'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_remove_excess', '1'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_addition_interval_seconds', '2'))
    conn.commit()
    cur.close()
    put_db(conn)

def create_bot_players():
    # ... unchanged
    pass

def generate_referral_code():
    # ... unchanged
    pass

def create_referral_code_for_user(user_id):
    # ... unchanged
    pass

def award_referral_bonus(referrer_id, referred_id):
    # ... unchanged
    pass

def add_bot_to_game(game_id, stake):
    from game.bingo_logic import generate_card

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM players WHERE user_id < 0")
        all_bots = [row['user_id'] for row in cur.fetchall()]
        if not all_bots:
            return None
        cur.execute("SELECT user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
        used_bots = [row['user_id'] for row in cur.fetchall()]
        available_bots = [bid for bid in all_bots if bid not in used_bots]
        if not available_bots:
            return None
        bot_id = random.choice(available_bots)
        cur.execute("SELECT balance FROM players WHERE user_id=%s", (bot_id,))
        bot = cur.fetchone()
        if bot['balance'] < stake:
            cur.execute("UPDATE players SET balance = balance + 1000 WHERE user_id=%s", (bot_id,))

        cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        available_cards = [i for i in range(1, 501) if i not in taken]
        if not available_cards:
            return None
        card_num = random.choice(available_cards)

        cur.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                    (game_id, bot_id, card_num, json.dumps(generate_card())))
        cur.execute("UPDATE players SET balance = balance - %s, games_played = games_played + 1 WHERE user_id=%s", (stake, bot_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id=%s", (stake, game_id))
        conn.commit()
        return bot_id
    except Exception as e:
        print(f"add_bot_to_game error: {e}")
        return None
    finally:
        cur.close()
        put_db(conn)

def remove_bot_from_game(game_id, bot_id):
    """Remove a bot from a game and refund its stake."""

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT stake FROM games WHERE id=%s", (game_id,))
        game = cur.fetchone()
        if not game:
            return
        stake = game['stake']
        cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, bot_id))
        card_count = cur.fetchone()['cnt']
        refund = stake * card_count
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id=%s", (refund, bot_id))
        cur.execute("DELETE FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, bot_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool - %s WHERE id=%s", (refund, game_id))
        conn.commit()
        print(f"Bot {bot_id} removed from game {game_id}, refunded {refund} ETB")
    except Exception as e:
        print(f"remove_bot_from_game error: {e}")
    finally:
        cur.close()
        put_db(conn)

def count_players_in_game(game_id):

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=%s", (game_id,))
        row = cur.fetchone()
        return row['cnt'] if row else 0
    finally:
        cur.close()
        put_db(conn)
