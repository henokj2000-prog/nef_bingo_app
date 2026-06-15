import os
import psycopg2
import psycopg2.extras
import json
import random
import string

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(DATABASE_URL)

# For compatibility with app.py – some routes use get_db/put_db from a pool
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
        # Settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
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
        # Games
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
                last_draw_time DOUBLE PRECISION,
                countdown_started_at DOUBLE PRECISION
            )
        """)
        # Add columns if missing
        for col in ['last_draw_time', 'countdown_started_at']:
            try:
                cur.execute(f"ALTER TABLE games ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION")
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
                marked_numbers JSONB DEFAULT '[]',
                created_at DOUBLE PRECISION
            )
        """)
        try:
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS marked_numbers JSONB DEFAULT '[]'")
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS created_at DOUBLE PRECISION")
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
        # Bonuses
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonuses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                reason TEXT,
                created_at DOUBLE PRECISION
            )
        """)

        # ---------- INSERT DEFAULTS ONLY IF SETTINGS TABLE IS EMPTY ----------
        cur.execute("SELECT COUNT(*) FROM settings")
        count = cur.fetchone()[0]
        if count == 0:
            defaults = [
                ('telebirr_number', '0929001000'),
                ('cbe_number', '1000061737212'),
                ('max_balls_per_game', '75'),
                ('bot_enabled', '1'),
                ('bot_target_real_players', '2'),
                ('bot_addition_interval_seconds', '2'),
                ('bot_remove_excess', '1'),
                ('bot_number_to_add', '1'),
                ('owner_cut_percent', '20')
            ]
            for key, val in defaults:
                cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))

        conn.commit()
    finally:
        cur.close()
        put_db(conn)

# ------------------ Helper functions ------------------

# List of unique Ethiopian male names
ETHIOPIAN_MALE_NAMES = [
    "Abel", "Abiy", "Abraham", "Adane", "Amanuel", "Amsalu", "Anteneh", "Aregawi", "Aschalew", "Ashenafi",
    "Aster", "Ayenew", "Bereket", "Beyene", "Birhanu", "Biruk", "Dagnachew", "Daniel", "Dawit", "Debebe",
    "Demeke", "Desalegn", "Elias", "Endalkachew", "Ermias", "Eshetu", "Eyob", "Fikre", "Fisseha", "Gashaw",
    "Gebre", "Gedion", "Getachew", "Getnet", "Girma", "Habtamu", "Haile", "Henok", "Hundessa", "Jemberu",
    "Kassahun", "Kebede", "Kefelegn", "Lemma", "Makonnen", "Mathewos", "Melaku", "Mengistu", "Meron", "Mesay",
    "Mesfin", "Michael", "Mulugeta", "Nebiyou", "Nega", "Nigussie", "Rediet", "Samuel", "Sisay", "Solomon",
    "Tadesse", "Tafesse", "Tamirat", "Tarekegn", "Tekle", "Tesfaye", "Tewodros", "Tigist", "Tilahun",
    "Tsegaye", "Tsehay", "Wondimu", "Worku", "Yared", "Yemane", "Yonas", "Yosef", "Zelalem", "Zewdu",
    "Abebe", "Alemayehu", "Bekele", "Berhanu", "Desta", "Fekadu", "Gizachew", "Hailu"
]

def create_bot_players(count):
    """Create bot players with real Ethiopian male names."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
        row = cur.fetchone()
        next_id = row[0] - 1 if row and row[0] else -1
        name_pool = ETHIOPIAN_MALE_NAMES.copy()
        random.shuffle(name_pool)
        for i in range(count):
            name = name_pool[i % len(name_pool)]
            full_name = f"{name}_{abs(next_id)}"
            cur.execute(
                "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                (next_id, f"bot_{abs(next_id)}", full_name, 1000)
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
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET balance = balance + 10 WHERE user_id = %s", (referrer_id,))
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def add_bot_to_game(game_id, stake):
    """Add a bot card to a waiting game (for filler)."""
    from game.bingo_logic import generate_card
    import time
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM players WHERE user_id < 0 ORDER BY random() LIMIT 1")
        bot = cur.fetchone()
        if not bot:
            return
        bot_id = bot[0]
        cur.execute("SELECT COALESCE(MAX(card_number), 0)+1 FROM game_cards WHERE game_id = %s", (game_id,))
        card_number = cur.fetchone()[0]
        card = generate_card()
        cur.execute(
            "INSERT INTO game_cards (game_id, user_id, card_number, card_data, created_at) VALUES (%s, %s, %s, %s, %s)",
            (game_id, bot_id, card_number, json.dumps(card), time.time())
        )
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()
    except Exception as e:
        print(f"Error in add_bot_to_game: {e}")
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)
