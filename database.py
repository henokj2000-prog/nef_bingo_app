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

db_pool = None
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
except OperationalError:
    db_pool = None

def get_db():
    if db_pool:
        return db_pool.getconn()
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def put_db(conn):
    if db_pool:
        db_pool.putconn(conn)
    else:
        conn.close()

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            balance REAL DEFAULT 0,
            wins INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            language TEXT DEFAULT 'en',
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            chat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            stake INTEGER,
            prize_pool REAL,
            status TEXT,
            cancelled INTEGER DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]',
            created_at REAL,
            started_at REAL,
            finished_at REAL
        );
        CREATE TABLE IF NOT EXISTS game_cards (
            id SERIAL PRIMARY KEY,
            game_id INTEGER,
            user_id INTEGER,
            card_number INTEGER,
            card_data TEXT,
            FOREIGN KEY(game_id) REFERENCES games(id),
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            platform TEXT,
            tx_ref TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            platform TEXT,
            account_no TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id INTEGER PRIMARY KEY,
            code TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER,
            referred_id INTEGER,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_commissions (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER,
            referred_id INTEGER,
            game_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_commissions_archive (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER,
            referred_id INTEGER,
            game_id INTEGER,
            amount REAL,
            paid_at REAL,
            payment_week_start REAL,
            payment_week_end REAL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by INTEGER,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            message TEXT,
            created_at REAL,
            is_broadcast INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bonuses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            reason TEXT,
            created_at REAL
        );
    """)
    # Insert default settings
    default_settings = [
        ('bot_enabled', '1'),
        ('bot_min_players', '2'),
        ('deposit_bonus_percent', '0'),
        ('referral_commission_percent', '5'),
        ('referral_bonus_amount', '10'),
        ('bot_target_real_players', '2'),
        ('bot_remove_excess', '1'),
        ('bot_addition_interval_seconds', '2'),
        ('bot_number_to_add', '1'),
        ('owner_cut_percent', '20'),
        ('max_balls_per_game', '75'),
        ('telebirr_number', '0929001000'),
        ('cbe_number', '1000061737212')
    ]
    for k, v in default_settings:
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (k, v))
    conn.commit()
    cur.close()
    put_db(conn)

def create_bot_players(count=20):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
    existing = cur.fetchone()['cnt']
    if existing >= count:
        cur.close()
        put_db(conn)
        return
    next_id = -1
    cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
    row = cur.fetchone()
    if row and row['min']:
        next_id = row['min'] - 1
    for i in range(existing, count):
        cur.execute("INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                    (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000))
        next_id -= 1
    conn.commit()
    cur.close()
    put_db(conn)

def generate_referral_code():
    """Generate a unique 8-character referral code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

def create_referral_code_for_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        code = generate_referral_code()
        cur.execute("INSERT INTO referral_codes (user_id, code) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET code = EXCLUDED.code", (user_id, code))
        conn.commit()
        return code
    finally:
        cur.close()
        put_db(conn)

def award_referral_bonus(referrer_id, referred_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key='referral_bonus_amount'")
        row = cur.fetchone()
        bonus = float(row['value']) if row else 10.0
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (bonus, referrer_id))
        cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                    (referrer_id, bonus, 'Referral bonus', time.time()))
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def add_bot_to_game(game_id, stake, conn=None):
    """Add a single bot to the game. Returns True if added."""
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    cur = conn.cursor()
    try:
        from game.bingo_logic import generate_card   # lazy import to avoid circular

        cur.execute("SELECT user_id FROM players WHERE user_id < 0")
        all_bots = [row['user_id'] for row in cur.fetchall()]
        if not all_bots:
            return False
        cur.execute("SELECT user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
        used_bots = [row['user_id'] for row in cur.fetchall()]
        available_bots = [bid for bid in all_bots if bid not in used_bots]
        if not available_bots:
            return False
        bot_id = random.choice(available_bots)
        cur.execute("SELECT balance FROM players WHERE user_id=%s", (bot_id,))
        bot = cur.fetchone()
        if bot['balance'] < stake:
            cur.execute("UPDATE players SET balance=balance+1000 WHERE user_id=%s", (bot_id,))
        cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        available_cards = [i for i in range(1, 501) if i not in taken]
        if not available_cards:
            return False
        card_num = random.choice(available_cards)
        cur.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                    (game_id, bot_id, card_num, json.dumps(generate_card())))
        cur.execute("UPDATE players SET balance=balance-%s, games_played=games_played+1 WHERE user_id=%s", (stake, bot_id))
        cur.execute("UPDATE games SET prize_pool=prize_pool+%s WHERE id=%s", (stake, game_id))
        if close_conn:
            conn.commit()
        return True
    except Exception as e:
        print(f"add_bot_to_game error: {e}")
        return False
    finally:
        cur.close()
        if close_conn:
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
