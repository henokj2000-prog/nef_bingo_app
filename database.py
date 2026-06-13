import os
import psycopg2
import psycopg2.extras
import json

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(DATABASE_URL)

# For compatibility with app.py – some routes use get_db/put_db from a pool
# You can keep using get_conn() directly or implement a simple pool.
def get_db():
    conn = get_conn()
    conn.set_session(autocommit=False)
    return conn

def put_db(conn):
    conn.close()

# ------------------ Initialize all tables ------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Insert defaults if not exists
        for key, val in [
            ('telebirr_number', '0929001000'),
            ('cbe_number', '1000061737212'),
            ('max_balls_per_game', '75'),
            ('bot_enabled', '1'),
            ('bot_target_real_players', '2'),
            ('bot_addition_interval_seconds', '2'),
            ('bot_remove_excess', '1'),
            ('bot_number_to_add', '1'),
            ('owner_cut_percent', '20')
        ]:
            cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))

        # Players
        cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance DOUBLE PRECISION DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                total_won DOUBLE PRECISION DEFAULT 0,
                phone TEXT,
                language TEXT DEFAULT 'en',
                referred_by BIGINT,
                is_banned BOOLEAN DEFAULT FALSE
            )
        """)

        # Referral codes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id BIGINT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL
            )
        """)

        # Games – **with last_draw_time**
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY,
                stake DOUBLE PRECISION,
                prize_pool DOUBLE PRECISION DEFAULT 0,
                created_at DOUBLE PRECISION,
                finished_at DOUBLE PRECISION,
                status TEXT DEFAULT 'waiting',
                drawn_balls JSONB DEFAULT '[]',
                winner_card_numbers JSONB DEFAULT '[]',
                cancelled BOOLEAN DEFAULT FALSE,
                last_draw_time DOUBLE PRECISION
            )
        """)
        # Add column if table already exists but column missing (for existing deployments)
        try:
            cur.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS last_draw_time DOUBLE PRECISION")
        except:
            pass

        # Game cards
        cur.execute("""
            CREATE TABLE IF NOT EXISTS game_cards (
                id SERIAL PRIMARY KEY,
                game_id INTEGER REFERENCES games(id),
                user_id BIGINT,
                card_number INTEGER,
                card_data JSONB,
                marked_numbers JSONB DEFAULT '[]'
            )
        """)
        try:
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS marked_numbers JSONB DEFAULT '[]'")
        except:
            pass

        # Deposits
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                platform TEXT,
                tx_ref TEXT,
                status TEXT DEFAULT 'pending',
                created_at DOUBLE PRECISION
            )
        """)

        # Withdrawals
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                method TEXT,
                account_no TEXT,
                status TEXT DEFAULT 'pending',
                created_at DOUBLE PRECISION
            )
        """)

        # Notifications
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                message TEXT,
                created_at DOUBLE PRECISION,
                is_broadcast INTEGER DEFAULT 0
            )
        """)

        # Inquiries
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inquiries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                subject TEXT,
                message TEXT,
                status TEXT DEFAULT 'open',
                created_at DOUBLE PRECISION
            )
        """)

        # Bonuses (for admin)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonuses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                reason TEXT,
                created_at DOUBLE PRECISION
            )
        """)

        conn.commit()
    finally:
        cur.close()
        put_db(conn)

# ------------------ Helper functions for bot creation / referral ----------
def create_bot_players(count):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
        row = cur.fetchone()
        next_id = row[0] - 1 if row and row[0] else -1
        for i in range(count):
            cur.execute(
                "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000)
            )
            next_id -= 1
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def create_referral_code_for_user(user_id):
    import random, string
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
        if not cur.fetchone():
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            cur.execute("INSERT INTO referral_codes (user_id, code) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (user_id, code))
            conn.commit()
    finally:
        cur.close()
        put_db(conn)

def award_referral_bonus(referrer_id, new_user_id):
    # Example: give 10 ETB to referrer
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET balance = balance + 10 WHERE user_id = %s", (referrer_id,))
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def add_bot_to_game(game_id, stake):
    # Add a bot card to a game (for filler)
    from game.bingo_logic import generate_card
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM players WHERE user_id < 0 ORDER BY random() LIMIT 1")
        bot = cur.fetchone()
        if bot:
            cur.execute("SELECT COALESCE(MAX(card_number), 0)+1 FROM game_cards WHERE game_id = %s", (game_id,))
            card_number = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                (game_id, bot['user_id'], card_number, json.dumps(generate_card()))
            )
            cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
            conn.commit()
    except:
        pass
    finally:
        cur.close()
        put_db(conn)
