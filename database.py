import os
import json
import time
import random
import string
import secrets
import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Enforce SSL on Render
if "render.com" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

# Connection pooling (fast)
db_pool = None
try:
    db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
except OperationalError:
    db_pool = None

def get_db():
    """Get a database connection from the pool or a new one."""
    if db_pool:
        return db_pool.getconn()
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def put_db(conn):
    """Return connection to pool or close it."""
    if db_pool:
        db_pool.putconn(conn)
    else:
        conn.close()

def init_db():
    """Create all tables and default settings."""
    conn = get_db()
    cur = conn.cursor()
    try:
        # Players
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
            )
        """)
        # Games
        cur.execute("""
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
            )
        """)
        # Game cards
        cur.execute("""
            CREATE TABLE IF NOT EXISTS game_cards (
                id SERIAL PRIMARY KEY,
                game_id INTEGER REFERENCES games(id),
                user_id INTEGER REFERENCES players(user_id),
                card_number INTEGER,
                card_data TEXT,
                marked_numbers TEXT DEFAULT '[]'
            )
        """)
        # Deposits
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES players(user_id),
                amount REAL,
                platform TEXT,
                tx_ref TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at REAL
            )
        """)
        # Withdrawals
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES players(user_id),
                amount REAL,
                method TEXT,
                account_no TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL
            )
        """)
        # Inquiries
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inquiries (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES players(user_id),
                subject TEXT,
                message TEXT,
                status TEXT DEFAULT 'open',
                created_at REAL
            )
        """)
        # Referral codes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id INTEGER PRIMARY KEY REFERENCES players(user_id),
                code TEXT UNIQUE
            )
        """)
        # Referrals
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER REFERENCES players(user_id),
                referred_id INTEGER REFERENCES players(user_id),
                created_at REAL
            )
        """)
        # Referral commissions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_commissions (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER REFERENCES players(user_id),
                referred_id INTEGER REFERENCES players(user_id),
                game_id INTEGER REFERENCES games(id),
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                paid_at REAL
            )
        """)
        # Referral commissions archive
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_commissions_archive (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER,
                referred_id INTEGER,
                game_id INTEGER,
                amount REAL,
                paid_at REAL,
                payment_week_start REAL,
                payment_week_end REAL
            )
        """)
        # Settings table – ensure value is TEXT, not JSON
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # If an old settings table exists with JSON column, alter it to TEXT
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'settings' AND column_name = 'value' AND data_type = 'json'
                ) THEN
                    ALTER TABLE settings ALTER COLUMN value TYPE TEXT USING value::text;
                END IF;
            END $$;
        """)
        # Admins
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'admin',
                added_by INTEGER,
                created_at REAL
            )
        """)
        # Notifications
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                message TEXT,
                created_at REAL,
                is_broadcast INTEGER DEFAULT 0
            )
        """)
        # Bonuses
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonuses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES players(user_id),
                amount REAL,
                reason TEXT,
                created_at REAL
            )
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
    finally:
        cur.close()
        put_db(conn)

def create_bot_players(count=20):
    """Ensure exactly `count` bot accounts exist (user_id < 0)."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        existing = cur.fetchone()['cnt']
        if existing >= count:
            return
        cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
        row = cur.fetchone()
        next_id = (row['min'] - 1) if row and row['min'] else -1
        for _ in range(existing, count):
            cur.execute(
                "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000.0)
            )
            next_id -= 1
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def generate_referral_code():
    """Generate a unique 8-character alphanumeric code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

def create_referral_code_for_user(user_id):
    """Create or update a referral code for a user."""
    conn = get_db()
    cur = conn.cursor()
    try:
        code = generate_referral_code()
        cur.execute(
            "INSERT INTO referral_codes (user_id, code) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET code = EXCLUDED.code",
            (user_id, code)
        )
        conn.commit()
        return code
    finally:
        cur.close()
        put_db(conn)

def award_referral_bonus(referrer_id, referred_id):
    """Award referral bonus to the referrer."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'")
        row = cur.fetchone()
        bonus = float(row['value']) if row else 10.0
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (bonus, referrer_id))
        cur.execute(
            "INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
            (referrer_id, bonus, 'Referral bonus', time.time())
        )
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def add_bot_to_game(game_id, stake, conn=None):
    """
    Add a single bot to the game.
    Returns True if added, False if no bot available.
    """
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    cur = conn.cursor()
    try:
        from game.bingo_logic import generate_card

        cur.execute("SELECT user_id FROM players WHERE user_id < 0")
        all_bots = [row['user_id'] for row in cur.fetchall()]
        if not all_bots:
            return False

        cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        used_bots = [row['user_id'] for row in cur.fetchall()]
        available = [bid for bid in all_bots if bid not in used_bots]
        if not available:
            return False

        bot_id = random.choice(available)

        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        available_cards = [i for i in range(1, 501) if i not in taken]
        if not available_cards:
            return False

        card_num = random.choice(available_cards)
        cur.execute(
            "INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
            (game_id, bot_id, card_num, json.dumps(generate_card()))
        )
        cur.execute("UPDATE players SET balance = balance - %s, games_played = games_played + 1 WHERE user_id = %s", (stake, bot_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))

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
    """Return number of distinct players (real + bot) in the game."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
        return cur.fetchone()['cnt']
    finally:
        cur.close()
        put_db(conn)
