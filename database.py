import os
import time
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone

# Database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL")


# ==================== CONNECTION HELPERS ====================

def get_db():
    """Return a database connection with dictionary cursors."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def put_db(conn):
    """Close the database connection."""
    if conn:
        conn.close()


# ==================== INITIALIZATION ====================

def init_db():
    """Create all tables and insert default settings."""
    conn = get_db()
    cur = conn.cursor()

    # ---------- Players table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance NUMERIC DEFAULT 0,
            wins INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            total_won NUMERIC DEFAULT 0,
            phone TEXT,
            language TEXT DEFAULT 'en',
            is_banned BOOLEAN DEFAULT FALSE,
            referred_by BIGINT,
            created_at NUMERIC DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)

    # ---------- Games table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            stake NUMERIC NOT NULL,
            prize_pool NUMERIC DEFAULT 0,
            status TEXT DEFAULT 'waiting',
            created_at NUMERIC DEFAULT EXTRACT(EPOCH FROM NOW()),
            finished_at NUMERIC,
            cancelled INTEGER DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]'
        )
    """)

    # ---------- Game cards table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_cards (
            id SERIAL PRIMARY KEY,
            game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
            user_id BIGINT REFERENCES players(user_id),
            card_number INTEGER NOT NULL,
            card_data TEXT NOT NULL,
            marked_numbers TEXT DEFAULT '[]'
        )
    """)

    # ---------- Deposits table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES players(user_id),
            amount NUMERIC NOT NULL,
            platform TEXT,
            tx_ref TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at NUMERIC
        )
    """)

    # ---------- Withdrawals table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES players(user_id),
            amount NUMERIC NOT NULL,
            method TEXT,
            account_no TEXT,
            status TEXT DEFAULT 'pending',
            created_at NUMERIC
        )
    """)

    # ---------- Inquiries table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES players(user_id),
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at NUMERIC
        )
    """)

    # ---------- Referral codes table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id BIGINT PRIMARY KEY REFERENCES players(user_id),
            code TEXT UNIQUE NOT NULL,
            created_at NUMERIC
        )
    """)

    # ---------- Bonuses table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES players(user_id),
            amount NUMERIC,
            reason TEXT,
            created_at NUMERIC
        )
    """)

    # ---------- Notifications table ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            message TEXT,
            created_at NUMERIC,
            is_broadcast INTEGER DEFAULT 1
        )
    """)

    # ---------- Settings table (key‑value store) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # ---------- Game state table (for global state machine) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            id BOOLEAN PRIMARY KEY DEFAULT TRUE,
            status TEXT NOT NULL DEFAULT 'FROZEN',
            countdown_end TIMESTAMPTZ,
            inactive_cycles INTEGER DEFAULT 0,
            CHECK (id = TRUE)
        )
    """)
    cur.execute("""
        INSERT INTO game_state (id, status, countdown_end, inactive_cycles)
        VALUES (TRUE, 'FROZEN', NULL, 0)
        ON CONFLICT (id) DO NOTHING
    """)

    # ---------- Round players (temporary, for global round) ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS round_players (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount NUMERIC,
            joined_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ---------- Insert default settings ----------
    default_settings = [
        ('min_players', '2'),
        ('owner_cut_percent', '20'),
        ('telebirr_number', '0929001000'),
        ('cbe_number', '1000061737212'),
        ('max_balls_per_game', '75'),
        ('bot_enabled', '1'),
        ('bot_target_real_players', '2'),
        ('bot_addition_interval_seconds', '2'),
        ('bot_remove_excess', '1'),
        ('bot_number_to_add', '1')
    ]
    for key, value in default_settings:
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING", (key, value))

    conn.commit()
    cur.close()
    put_db(conn)


# ==================== SETTINGS HELPERS ====================

def get_setting(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close()
    put_db(conn)
    return row['value'] if row else None


def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s", (key, value, value))
    conn.commit()
    cur.close()
    put_db(conn)


# ==================== GAME STATE HELPERS (for global round) ====================

def get_game_state():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, countdown_end, inactive_cycles FROM game_state WHERE id = TRUE")
    row = cur.fetchone()
    cur.close()
    put_db(conn)
    return {
        "status": row['status'],
        "countdown_end": row['countdown_end'],
        "inactive_cycles": row['inactive_cycles']
    }


def set_game_state(status, countdown_end=None, inactive_cycles=None):
    conn = get_db()
    cur = conn.cursor()
    query = "UPDATE game_state SET status = %s"
    params = [status]
    if countdown_end is not None:
        query += ", countdown_end = %s"
        params.append(countdown_end)
    else:
        query += ", countdown_end = NULL"
    if inactive_cycles is not None:
        query += ", inactive_cycles = %s"
        params.append(inactive_cycles)
    query += " WHERE id = TRUE"
    cur.execute(query, params)
    conn.commit()
    cur.close()
    put_db(conn)


# ==================== ROUND PLAYERS (global round) ====================

def add_player_to_round(user_id, amount):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO round_players (user_id, amount) VALUES (%s, %s)", (user_id, amount))
    conn.commit()
    cur.close()
    put_db(conn)


def get_round_players_count():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM round_players")
    count = cur.fetchone()['count']
    cur.close()
    put_db(conn)
    return count


def clear_round_players():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM round_players")
    conn.commit()
    cur.close()
    put_db(conn)


# ==================== REFERRAL HELPERS ====================

def create_referral_code_for_user(user_id):
    """Generate a unique referral code for a user if not already present."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
    if not cur.fetchone():
        import random
        code = f"REF{user_id}{random.randint(100, 999)}"
        cur.execute(
            "INSERT INTO referral_codes (user_id, code, created_at) VALUES (%s, %s, %s)",
            (user_id, code, time.time())
        )
        conn.commit()
    cur.close()
    put_db(conn)


def award_referral_bonus(referrer_id, new_user_id):
    """Give 10 ETB bonus to referrer when a new user signs up."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE players SET balance = balance + 10 WHERE user_id = %s", (referrer_id,))
    cur.execute(
        "INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
        (referrer_id, 10, f'Referral bonus for {new_user_id}', time.time())
    )
    conn.commit()
    cur.close()
    put_db(conn)


# ==================== BOT HELPERS ====================

def create_bot_players(count):
    """Create a given number of bot players (negative user_id)."""
    conn = get_db()
    cur = conn.cursor()
    # Find the smallest existing bot ID (most negative)
    cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
    row = cur.fetchone()
    next_id = (row['min'] - 1) if row and row['min'] else -1
    for _ in range(count):
        cur.execute("""
            INSERT INTO players (user_id, username, full_name, balance)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000))
        next_id -= 1
    conn.commit()
    cur.close()
    put_db(conn)


def add_bot_to_game(game_id):
    """(Optional) Add a bot player to a specific game.
       You can implement this later if needed."""
    pass
