import os
import threading
import psycopg2
import psycopg2.extensions
import psycopg2.extras
import psycopg2.pool
import json
import random
import string

DATABASE_URL = os.environ.get("DATABASE_URL")

# ------------------ Real connection pool ------------------
_pool = None
_pool_lock = threading.Lock()

def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=int(os.environ.get('DB_POOL_MAX', '10')),
                    dsn=DATABASE_URL
                )
    return _pool

def get_conn():
    conn = _get_pool().getconn()
    conn.autocommit = False
    return conn

def get_db():
    return get_conn()

def put_db(conn):
    if conn is None:
        return
    try:
        if conn.closed == 0:
            if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                conn.rollback()
            _get_pool().putconn(conn)
        else:
            _get_pool().putconn(conn, close=True)
    except Exception as e:
        print(f"Error returning connection to pool: {e}")
        try:
            conn.close()
        except Exception:
            pass

# ------------------ Initialize all tables ------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
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
                language TEXT DEFAULT 'am',
                referred_by BIGINT,
                is_banned BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id BIGINT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_referrals (
                chat_id BIGINT PRIMARY KEY,
                code TEXT,
                created_at DOUBLE PRECISION
            )
        """)
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
        for col in ['last_draw_time', 'countdown_started_at']:
            try:
                cur.execute(f"ALTER TABLE games ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION")
            except:
                pass
        try:
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bonus_balance DOUBLE PRECISION DEFAULT 0")
        except:
            pass
        try:
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bonus_credited_at DOUBLE PRECISION DEFAULT 0")
        except:
            pass
        try:
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bot_started BOOLEAN DEFAULT FALSE")
        except:
            pass
        try:
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS pending_play_bonus DOUBLE PRECISION DEFAULT 0")
        except:
            pass
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
            # Tracks exactly how much of a card's stake came from real
            # (withdrawable) balance vs. bonus (referral) balance, so a
            # released/refunded card returns money to the correct wallet
            # instead of accidentally laundering bonus money into balance.
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS funded_bonus_amt DOUBLE PRECISION DEFAULT 0")
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS funded_real_amt DOUBLE PRECISION DEFAULT 0")
        except:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount DOUBLE PRECISION,
                platform TEXT,
                tx_ref TEXT,
                status TEXT DEFAULT 'pending',
                created_at DOUBLE PRECISION,
                proof_text TEXT
            )
        """)
        try:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_deposits_tx_ref
                ON deposits (tx_ref)
            """)
            conn.commit()
        except Exception as idx_err:
            print(f"Skipping uniq_deposits_tx_ref index (likely existing duplicate tx_ref data): {idx_err}", flush=True)
            conn.rollback()
        try:
            cur.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS proof_text TEXT")
        except:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS unmatched_sms (
                id SERIAL PRIMARY KEY,
                tx_ref TEXT,
                amount DOUBLE PRECISION,
                raw_sms TEXT,
                matched BOOLEAN DEFAULT FALSE,
                created_at DOUBLE PRECISION
            )
        """)
        try:
            cur.execute("ALTER TABLE unmatched_sms ADD COLUMN IF NOT EXISTS raw_sms TEXT")
        except:
            pass
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                message TEXT,
                created_at DOUBLE PRECISION,
                is_broadcast INTEGER DEFAULT 0
            
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inquiries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                subject TEXT,
                message TEXT,
                status TEXT DEFAULT 'open',
                created_at DOUBLE PRECISION,
                admin_reply TEXT
            )
        """)
        try:
            cur.execute("ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS admin_reply TEXT")
        except:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_earnings (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT,
                earning_type TEXT,
                amount DOUBLE PRECISION,
                created_at DOUBLE PRECISION
            )
        """)
        cur.execute("SELECT COUNT(*) FROM settings")
        count = cur.fetchone()[0]
        if count == 0:
            defaults = [
                ('telebirr_number', '0929001000'),
                ('mpesa_number', '0707014437'),
                ('maintenance_mode', '0'),
                ('max_balls_per_game', '75'),
                ('bot_enabled', '1'),
                ('bot_target_real_players', '2'),
                ('bot_addition_interval_seconds', '2'),
                ('bot_remove_excess', '1'),
                ('bot_number_to_add', '1'),
                ('owner_cut_percent', '20'),
                ('referral_bonus_amount', '10'),
                ('referral_commission_percent', '5'),
                ('welcome_bonus_amount', '10')
            ]
            for key, val in defaults:
                cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))

        try:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_referral_bonus_per_referred
                ON referral_earnings (referred_id)
                WHERE earning_type = 'bonus'
            """)
            conn.commit()
        except Exception as idx_err:
            print(f"Skipping uniq_referral_bonus_per_referred index (likely existing duplicate data): {idx_err}", flush=True)
            conn.rollback()

        conn.commit()
    finally:
        cur.close()
        put_db(conn)

# ------------------ Helper functions ------------------

# Mixed pool of authentic Ethiopian first names drawn from across the
# country's major language communities — Amharic, English-transliterated,
# Tigrigna, and Afan Oromo — so bot players read as a realistic cross-section
# of real Ethiopian players rather than one single group.
ETHIOPIAN_MALE_NAMES = [
    # ----- Amharic / English real names (40) -----
    "Abel", "Abraham", "Adane", "Amanuel", "Amsalu", "Anteneh", "Aregawi",
    "Aschalew", "Ashenafi", "Aster", "Ayenew", "Bereket", "Beyene", "Birhanu",
    "Biruk", "Dagnachew", "Daniel", "Dawit", "Debebe", "Demeke", "Desalegn",
    "Elias", "Endalkachew", "Ermias", "Eshetu", "Eyob", "Fikre", "Fisseha",
    "Gashaw", "Gebre", "Gedion", "Getachew", "Getnet", "Girma", "Habtamu",
    "Haile", "Henok", "Hundessa", "Jemberu", "Kassahun", "Kebede", "Kefelegn",
    "Lemma", "Makonnen", "Mathewos", "Melaku", "Mengistu", "Meron", "Mesay",
    "Mesfin", "Michael", "Mulugeta", "Nebiyou", "Nega", "Nigussie", "Rediet",
    "Samuel", "Sisay", "Solomon", "Tadesse", "Tafesse", "Tamirat", "Tarekegn",
    "Tekle", "Tesfaye", "Tewodros", "Tigist", "Tilahun", "Tsegaye", "Tsehay",
    "Wondimu", "Worku", "Yared", "Yemane", "Yonas", "Yosef", "Zelalem", "Zewdu",
    "Abebe", "Alemayehu", "Bekele", "Berhanu", "Desta", "Fekadu", "Gizachew", "Hailu",

    # ----- Amharic real names, Ge'ez script (40) -----
    "አቤል", "አብርሃም", "አዳነ", "አማኑኤል", "አምሳሉ", "አንተነህ",
    "አረጋዊ", "አስቻለው", "አሸናፊ", "አስቴር", "አየነው", "በረከት",
    "ብየነ", "ብርሃኑ", "ብሩክ", "ዳኛቸው", "ዳንኤል", "ዳዊት",
    "ደበበ", "ደመቀ", "ደሳለኝ", "ኤልያስ", "እንዳልካቸው", "ኤርሚያስ",
    "እሸቱ", "ኢዮብ", "ፍቅሬ", "ፍስሃ", "ጋሻው", "ገብረ",
    "ጌድዮን", "ጌታቸው", "ጌትነት", "ግርማ", "ሀብታሙ", "ሃይሌ",
    "ሄኖክ", "ሁንደሳ", "ጀምበሩ", "ካሳሁን", "ከበደ", "ከፈለኝ",
    "ለማ", "መኮንን", "ማቴዎስ", "መላኩ", "መንግስቱ", "ሜሮን",
    "ሜሳይ", "መስፍን", "ሚካኤል", "ሙሉጌታ", "ነቢዩ", "ነጋ",
    "ንጉሴ", "ረድኤት", "ሳሙኤል", "ሲሳይ", "ሰለሞን", "ታደሰ",
    "ታፈሰ", "ታምራት", "ታረቀኝ", "ትክሌ", "ተስፋዬ", "ተወደሮስ",
    "ትግስት", "ትላሁን", "ፀጋዬ", "ፀሀይ", "ወንዲሙ", "ወርቁ",
    "ያሬድ", "የማነ", "ዮናስ", "ዮሴፍ", "ዘላለም", "ዘውዱ",
    "አበበ", "አለማየሁ", "በቀለ", "ብርሃኑ", "ደስታ", "ፍቃዱ", "ግዛቸው", "ሀይሉ",

    # ----- English nicknames (20) -----
    "Abi", "Hennie", "Yoni", "Davi", "Sam", "Danny", "Mick", "Yobi",
    "Biru", "Kebe", "Tes", "Gee", "Mel", "Mengi", "Tadi", "Tam",
    "Tek", "Work", "Yare", "Zewi",

    # ----- Amharic nicknames (20) -----
    "አቤ", "ሄኖ", "ዮና", "ዳዊ", "ሳም", "ዳን", "ሚክ", "ዮቢ",
    "ቢሩ", "ከቤ", "ተስ", "ጊ", "መል", "መን", "ታዲ", "ታም",
    "ትክ", "ወር", "ያሬ", "ዘው",

    # ----- Tigrigna real names (30) -----
    "Tesfay", "Haftom", "Mehari", "Gebremedhin", "Hagos", "Berhane",
    "Weldu", "Ataklti", "Goitom", "Birhane", "Fitsum", "Kbrom",
    "Meles", "Mussie", "Welday", "Yohannes", "Tsegay", "Awet",
    "Hadgu", "Zerit", "Asmelash", "Gebrekidan", "Habtom", "Negusse",
    "Reesom", "Senay", "Teklit", "Yonatan", "Zecharias", "Filimon",

    # ----- Tigrigna real names, Ge'ez script (20) -----
    "ተስፋይ", "ሃፍቶም", "መሓሪ", "ገብረመድህን", "ሓጎስ", "ብርሃነ",
    "ወልዱ", "ኣታክልቲ", "ጎይትኦም", "ፍጹም", "ክብሮም", "መለስ",
    "ሙሴ", "ወልደይ", "ዮውሃንስ", "ጸጋይ", "ኣወት", "ሓድጉ",
    "ሰናይ", "ተኽልት",

    # ----- Afan Oromo real names (30) -----
    "Boru", "Gemechu", "Dabassa", "Wakgari", "Tolera", "Diriba",
    "Guta", "Roba", "Bultum", "Tariku", "Jiregna", "Bayisa",
    "Kenea", "Mulatu", "Tesema", "Wayessa", "Gada", "Galata",
    "Bekan", "Chala", "Dame", "Eshetu", "Gamachu", "Hora",
    "Ijara", "Kiya", "Lalisa", "Negasa", "Obsa", "Wario",

    # ----- Afan Oromo nicknames (10) -----
    "Boruu", "Gammachu", "Dabbasa", "Tolasaa", "Roobaa",
    "Tariikuu", "Keenaa", "Galataa", "Hooraa", "Waaqoo"
]

def create_bot_players(count):
    """Create bot players with authentic Ethiopian names (Amharic, English,
    Tigrigna, and Afan Oromo mix)."""
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
            full_name = name
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
    """Give referral bonus to referrer (amount from settings). Credited to
    bonus_balance — playable but not withdrawable until the referrer has
    made a real deposit, and never withdrawable directly even then."""
    import time
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'")
        row = cur.fetchone()
        bonus = float(row[0]) if row else 10.0

        cur.execute("UPDATE players SET bonus_balance = bonus_balance + %s WHERE user_id = %s", (bonus, referrer_id))
        cur.execute(
            "INSERT INTO referral_earnings (referrer_id, referred_id, earning_type, amount, created_at) VALUES (%s, %s, %s, %s, %s)",
            (referrer_id, new_user_id, 'bonus', bonus, time.time())
        )
        conn.commit()
        print(f"Referral bonus {bonus} ETB awarded (bonus_balance) to user {referrer_id} for referring {new_user_id}")
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
        cur.execute("""
            SELECT user_id FROM players
            WHERE user_id < 0
              AND user_id NOT IN (SELECT user_id FROM game_cards WHERE game_id = %s)
            ORDER BY random() LIMIT 1
        """, (game_id,))
        bot = cur.fetchone()
        if not bot:
            return
        bot_id = bot[0]

        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = {row[0] for row in cur.fetchall()}
        available = [n for n in range(1, 501) if n not in taken]
        if not available:
            return
        card_number = random.choice(available)

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
