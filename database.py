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

if "render.com" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

db_pool = None
try:
    db_pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
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
    try:
        # --- CRITICAL: Force drop settings table to ensure correct column type ---
        cur.execute("DROP TABLE IF EXISTS settings CASCADE")
        conn.commit()
        print("✅ Dropped old settings table (if existed) to fix JSON type issue")

        # Create settings table with TEXT column
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Create all other tables (keep your existing CREATE statements)
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id INTEGER PRIMARY KEY REFERENCES players(user_id),
                code TEXT UNIQUE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER REFERENCES players(user_id),
                referred_id INTEGER REFERENCES players(user_id),
                created_at REAL
            )
        """)
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'admin',
                added_by INTEGER,
                created_at REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                message TEXT,
                created_at REAL,
                is_broadcast INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonuses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES players(user_id),
                amount REAL,
                reason TEXT,
                created_at REAL
            )
        """)

        # Insert default settings (as TEXT values)
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
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                (k, str(v))
            )
        conn.commit()
        print("✅ Database initialized successfully (settings table with TEXT column)")

    except Exception as e:
        conn.rollback()
        print(f"❌ init_db error: {e}")
        raise
    finally:
        cur.close()
        put_db(conn)

# ... (keep all your other helper functions exactly as before: 
# create_bot_players, generate_referral_code, create_referral_code_for_user, 
# award_referral_bonus, add_bot_to_game, count_players_in_game)
