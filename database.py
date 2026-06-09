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

# Connection pooling for speed
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
except OperationalError:
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
    # Tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            phone TEXT UNIQUE,
            language TEXT DEFAULT 'en',
            chat_id TEXT,
            referred_by BIGINT,
            referral_code TEXT UNIQUE,
            referral_bonus_earned REAL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            stake INTEGER,
            status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]',
            created_at REAL,
            started_at REAL,
            finished_at REAL,
            cancelled INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_cards (
            id SERIAL PRIMARY KEY,
            game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
            user_id BIGINT,
            card_number INTEGER,
            card_data TEXT,
            UNIQUE(game_id, card_number)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            tx_ref TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            account_no TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            reason TEXT,
            admin_note TEXT,
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_broadcast INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by BIGINT,
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            created_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_commissions (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_commissions_archive (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            paid_at REAL,
            payment_week_start REAL,
            payment_week_end REAL
        )
    """)
    # Default settings
    default_settings = {
        'telebirr_number': '0929 001 000',
        'cbe_number': '1000061737212',
        'deposit_bonus_percent': '0',
        'referral_commission_percent': '5',
        'referral_bonus_amount': '10',
        'owner_cut_percent': '20',
        'max_balls_per_game': '75',
        'bot_enabled': '1',
        'bot_cards_per_game': '1',
        'bot_min_players': '2',
        'bot_target_real_players': '2',
        'bot_remove_excess': '1',
        'bot_addition_interval_seconds': '2',
    }
    for key, value in default_settings.items():
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, value))
    conn.commit()
    cur.close()
    put_db(conn)
    print("✅ Database initialized (PostgreSQL)")

def create_bot_players():
    bot_names = [
        ("Admasu Kebe", "admasu_k"), ("Yichilal", "yichilal"),
        ("Aradaw Tade", "aradaw_t"), ("Shime Gondar", "shime_g"),
        ("Emu Konjo", "emu_k"), ("Tigist Desta", "tigist_d"),
        ("Biruk Alemu", "biruk_a"), ("Meron Assefa", "meron_a"),
        ("Dawit Mekonnen", "dawit_m"), ("Hana Tesfaye", "hana_t")
    ]
    conn = get_db()
    cur = conn.cursor()
    bot_id = -1
    for full_name, username in bot_names:
        cur.execute("SELECT user_id FROM players WHERE user_id = %s", (bot_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                        (bot_id, username, full_name, 1000))
        bot_id -= 1
    conn.commit()
    cur.close()
    put_db(conn)

def generate_referral_code():
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT code FROM referral_codes WHERE code = %s", (code,))
        existing = cur.fetchone()
        cur.close()
        put_db(conn)
        if not existing:
            return code

def create_referral_code_for_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()
    if not existing:
        code = generate_referral_code()
        cur.execute("INSERT INTO referral_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
        cur.execute("UPDATE players SET referral_code = %s WHERE user_id = %s", (code, user_id))
        conn.commit()
        cur.close()
        put_db(conn)
        return code
    cur.close()
    put_db(conn)
    return existing['code']

def award_referral_bonus(referrer_id, referred_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'")
    row = cur.fetchone()
    bonus_amt = float(row['value']) if row else 10.0
    cur.execute("UPDATE players SET balance = balance + %s, referral_bonus_earned = referral_bonus_earned + %s WHERE user_id = %s",
                (bonus_amt, bonus_amt, referrer_id))
    cur.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (%s, %s, %s)",
                (referrer_id, referred_id, time.time()))
    conn.commit()
    cur.close()
    put_db(conn)
    print(f"🎁 Referral bonus: +{bonus_amt} ETB to user {referrer_id} for referring {referred_id}")

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
