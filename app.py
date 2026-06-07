from flask import Flask, request, jsonify, send_from_directory
import psycopg2
import psycopg2.extras
import json, time, os, threading, re, secrets, string
import requests
import random
from game.bingo_logic import generate_card, draw_ball, check_bingo

app = Flask(__name__, static_folder='static', template_folder='templates')

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY,
            username TEXT, full_name TEXT,
            balance REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            phone TEXT DEFAULT NULL,
            language TEXT DEFAULT 'en',
            chat_id TEXT DEFAULT NULL,
            referred_by BIGINT DEFAULT NULL,
            referral_code TEXT UNIQUE DEFAULT NULL,
            referral_bonus_earned REAL DEFAULT 0
        )
    ''')
    cur.execute('''
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
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS game_cards (
            id SERIAL PRIMARY KEY,
            game_id INTEGER,
            user_id BIGINT,
            card_number INTEGER,
            card_data TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            tx_ref TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            account_no TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at REAL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bonuses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            reason TEXT,
            admin_note TEXT,
            created_at REAL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_broadcast INTEGER DEFAULT 1
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by BIGINT,
            created_at REAL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            created_at REAL
        )
    ''')
    cur.execute('''
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
    ''')
    cur.execute('''
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
    ''')
    settings_defaults = [
        ('telebirr_number', '0929 001 000'),
        ('cbe_number', '1000061737212'),
        ('deposit_bonus_percent', '0'),
        ('referral_commission_percent', '5'),
        ('referral_bonus_amount', '10'),
        ('owner_cut_percent', '20'),
        ('max_balls_per_game', '75'),
        ('bot_enabled', '1'),
        ('bot_max_bots', '5'),
        ('bot_target_real_players', '3')
    ]
    for key, val in settings_defaults:
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))
    conn.commit()
    cur.close()
    conn.close()

init_db()

def count_players_in_game(game_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id=%s', (game_id,))
    row = cur.fetchone()
    cnt = row['count'] if row else 0
    cur.close()
    conn.close()
    return cnt

def create_bot_players():
    bot_names = [
        ("Admasu Kebe", "admasu_k"), ("Yichilal", "yichilal"),
        ("Aradaw Tade", "aradaw_t"), ("Shime Gondar", "shime_g"),
        ("Emu Konjo", "emu_k"), ("Tigist Desta", "tigist_d"),
        ("Biruk Alemu", "biruk_a"), ("Meron Assefa", "meron_a"),
        ("Dawit Mekonnen", "dawit_m"), ("Hana Tesfaye", "hana_t"),
        ("Abebech Ayele", "abebech_a"), ("Fikru Demissie", "fikru_d"),
        ("Genet Assefa", "genet_a"), ("Habtamu Tadesse", "habtamu_t"),
        ("Ibrahim Jemal", "ibrahim_j"), ("Jember Tefera", "jember_t"),
        ("Kalkidan Alemu", "kalkidan_a"), ("Lemi Hailu", "lemi_h"),
        ("Makeda Seyoum", "makeda_s"), ("Nardos Worku", "nardos_w"),
        ("Oliyad Getachew", "oliyad_g"), ("Peniel Tekle", "peniel_t"),
        ("Qalicha Kebede", "qalicha_k"), ("Rahel Tesfaye", "rahel_t"),
        ("Selamawit Desta", "selamawit_d"), ("Tamrat Girma", "tamrat_g"),
        ("Ura Mulugeta", "ura_m"), ("Vivian Asfaw", "vivian_a"),
        ("Wondwosen Eshetu", "wondwosen_e"), ("Xavier Bekele", "xavier_b"),
        ("Yabets Ayele", "yabets_a"), ("Zebib Assefa", "zebib_a"),
        ("Almaz Gizaw", "almaz_g"), ("Bereket Moges", "bereket_m"),
        ("Chaltu Hussein", "chaltu_h"), ("Diriba Fikre", "diriba_f"),
        ("Eden Muluneh", "eden_m"), ("Fisseha Gebre", "fisseha_g"),
        ("Girma Tekle", "girma_t"), ("Hiwot Berhanu", "hiwot_b"),
        ("Idris Seid", "idris_s"), ("Jemal Ahmed", "jemal_a"),
        ("Kiya Tsegaye", "kiya_t"), ("Leul Mekonnen", "leul_m"),
        ("Mahlet Ayele", "mahlet_a"), ("Natnael Abebe", "natnael_a"),
        ("Obang Olom", "obang_o"), ("Precious Haile", "precious_h"),
        ("Qedamawi Tekle", "qedamawi_t"), ("Ruth Bekele", "ruth_b")
    ]
    conn = get_db_connection()
    cur = conn.cursor()
    bot_id = -1
    for full_name, username in bot_names:
        cur.execute("SELECT user_id FROM players WHERE user_id=%s", (bot_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO players (user_id, username, full_name, balance) VALUES (%s,%s,%s,%s)",
                        (bot_id, username, full_name, 1000))
        bot_id -= 1
    conn.commit()
    cur.close()
    conn.close()

create_bot_players()

def generate_referral_code():
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT code FROM referral_codes WHERE code=%s', (code,))
        existing = cur.fetchone()
        cur.close()
        conn.close()
        if not existing:
            return code

def create_referral_code_for_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT code FROM referral_codes WHERE user_id=%s', (user_id,))
        row = cur.fetchone()
        if row:
            cur.execute('UPDATE players SET referral_code=%s WHERE user_id=%s AND referral_code IS NULL', (row['code'], user_id))
            conn.commit()
            return row['code']
        code = generate_referral_code()
        cur.execute('INSERT INTO referral_codes (user_id, code) VALUES (%s,%s)', (user_id, code))
        cur.execute('UPDATE players SET referral_code=%s WHERE user_id=%s', (code, user_id))
        conn.commit()
        return code
    except Exception as e:
        print(f"Error creating referral code for user {user_id}: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def award_referral_bonus(referrer_id, referred_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='referral_bonus_amount'")
    row = cur.fetchone()
    bonus_amt = float(row['value']) if row else 10.0
    cur.execute('UPDATE players SET balance=balance+%s, referral_bonus_earned=referral_bonus_earned+%s WHERE user_id=%s',
                (bonus_amt, bonus_amt, referrer_id))
    cur.execute('INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (%s,%s,%s)',
                (referrer_id, referred_id, time.time()))
    conn.commit()
    cur.close()
    conn.close()
    print(f"🎁 Referral bonus: +{bonus_amt} ETB to user {referrer_id}")

def add_single_bot(game_id, stake):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM players WHERE user_id < 0")
    bot_ids = [r['user_id'] for r in cur.fetchall()]
    if not bot_ids:
        cur.close()
        conn.close()
        return False
    cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
    existing_bot_ids = [r['user_id'] for r in cur.fetchall()]
    available = [bid for bid in bot_ids if bid not in existing_bot_ids]
    if not available:
        cur.close()
        conn.close()
        return False
    bot_id = random.choice(available)
    cur.execute("SELECT balance FROM players WHERE user_id=%s", (bot_id,))
    bot_balance = cur.fetchone()['balance']
    if bot_balance < stake:
        cur.execute("UPDATE players SET balance=balance+1000 WHERE user_id=%s", (bot_id,))
    cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
    taken = [r['card_number'] for r in cur.fetchall()]
    available_cards = [i for i in range(1, 501) if i not in taken]
    if not available_cards:
        cur.close()
        conn.close()
        return False
    card_num = random.choice(available_cards)
    cur.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s,%s,%s,%s)",
                (game_id, bot_id, card_num, json.dumps(generate_card())))
    cur.execute("UPDATE players SET balance=balance-%s, games_played=games_played+1 WHERE user_id=%s", (stake, bot_id))
    cur.execute("UPDATE games SET prize_pool=prize_pool+%s WHERE id=%s", (stake, game_id))
    conn.commit()
    cur.execute("SELECT full_name FROM players WHERE user_id=%s", (bot_id,))
    bot_name = cur.fetchone()['full_name']
    print(f"🤖 Bot {bot_name} (ID {bot_id}) joined game {game_id} with card {card_num}")
    cur.close()
    conn.close()
    return True

def remove_all_bots_from_game(game_id, stake):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
    bot_cards = cur.fetchall()
    for card in bot_cards:
        cur.execute("DELETE FROM game_cards WHERE id=%s", (card['id'],))
        cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (stake, card['user_id']))
    cur.execute("UPDATE games SET prize_pool=prize_pool-%s WHERE id=%s", (stake * len(bot_cards), game_id))
    conn.commit()
    print(f"🚫 Removed {len(bot_cards)} bot(s) from game {game_id}")
    cur.close()
    conn.close()

_engine_lock = threading.Lock()
_running_engines = set()

def start_game_engine(game_id):
    with _engine_lock:
        if game_id in _running_engines:
            return
        _running_engines.add(game_id)

    def engine():
        try:
            time.sleep(2)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT * FROM games WHERE id=%s', (game_id,))
            game = cur.fetchone()
            if not game or game['status'] != 'waiting':
                cur.close()
                conn.close()
                return
            stake = game['stake']
            from config import ADMIN_IDS
            cur.execute("SELECT value FROM settings WHERE key='bot_enabled'")
            row = cur.fetchone()
            bot_enabled = int(row['value']) if row else 1
            cur.execute("SELECT value FROM settings WHERE key='bot_max_bots'")
            row = cur.fetchone()
            max_bots = int(row['value']) if row else 5
            cur.execute("SELECT value FROM settings WHERE key='bot_target_real_players'")
            row = cur.fetchone()
            target_real = int(row['value']) if row else 3

            if bot_enabled and stake == 10:
                def get_real_count():
                    cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
                    all_players = cur.fetchall()
                    return len([r['user_id'] for r in all_players if r['user_id'] not in ADMIN_IDS and r['user_id'] > 0])
                added_bots = 0
                start_time = time.time()
                while time.time() - start_time < 30:
                    current_real = get_real_count()
                    if current_real >= target_real:
                        remove_all_bots_from_game(game_id, stake)
                        break
                    if added_bots < max_bots:
                        if get_real_count() >= target_real:
                            remove_all_bots_from_game(game_id, stake)
                            break
                        success = add_single_bot(game_id, stake)
                        if success:
                            added_bots += 1
                    time.sleep(1)
                    cur.execute('SELECT status FROM games WHERE id=%s', (game_id,))
                    status = cur.fetchone()
                    if not status or status['status'] != 'waiting':
                        break

            cur.execute('SELECT * FROM games WHERE id=%s', (game_id,))
            game = cur.fetchone()
            if not game or game['status'] != 'waiting':
                cur.close()
                conn.close()
                return
            cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
            all_players = cur.fetchall()
            real_count = len([r['user_id'] for r in all_players if r['user_id'] not in ADMIN_IDS and r['user_id'] > 0])
            if real_count == 0:
                cur.execute('UPDATE games SET status=%s, finished_at=%s, cancelled=1, winner_card_numbers=%s WHERE id=%s',
                            ('finished', time.time(), '[]', game_id))
                cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
                card_holders = cur.fetchall()
                for row in card_holders:
                    cur.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, row['user_id']))
                    card_count = cur.fetchone()['count']
                    refund = stake * card_count
                    cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (refund, row['user_id']))
                conn.commit()
                cur.close()
                conn.close()
                print(f"🚫 Game {game_id} cancelled: no real players. Refunded.")
                return
            cur.execute('UPDATE games SET status=%s, started_at=%s WHERE id=%s', ('running', time.time(), game_id))
            conn.commit()
            cur.close()
            conn.close()
            draw_loop(game_id)
        finally:
            with _engine_lock:
                _running_engines.discard(game_id)

    threading.Thread(target=engine, daemon=True).start()

def draw_loop(game_id):
    while True:
        time.sleep(1)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM games WHERE id=%s', (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'running':
            cur.close()
            conn.close()
            break
        drawn = json.loads(game['drawn_balls'])
        cur.execute("SELECT value FROM settings WHERE key='max_balls_per_game'")
        row = cur.fetchone()
        max_balls = int(row['value']) if row else 75
        if len(drawn) >= max_balls:
            cur.execute('UPDATE games SET status=%s, finished_at=%s WHERE id=%s', ('finished', time.time(), game_id))
            cur.execute('SELECT * FROM game_cards WHERE game_id=%s', (game_id,))
            cards = cur.fetchall()
            if not cards:
                conn.commit()
                cur.close()
                conn.close()
                schedule_next_game(game['stake'])
                break
            player_matches = {}
            for card in cards:
                card_data = json.loads(card['card_data'])
                numbers = [cell for row in card_data for cell in row if cell != 'FREE']
                matches = sum(1 for num in numbers if num in set(int(b[1:]) for b in drawn))
                player_matches[card['user_id']] = player_matches.get(card['user_id'], 0) + matches
            if player_matches:
                best = max(player_matches.values())
                winner_ids = [uid for uid, m in player_matches.items() if m == best]
                total_pot = game['prize_pool']
                winners_share = round(total_pot * 0.80, 2)
                prize_per_winner = round(winners_share / len(winner_ids), 2) if winner_ids else 0
                for uid in winner_ids:
                    cur.execute('UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s',
                                (prize_per_winner, prize_per_winner, uid))
                cur.execute('UPDATE games SET winner_card_numbers=%s WHERE id=%s', (json.dumps([]), game_id))
                conn.commit()
                print(f"🏁 Game {game_id} ended after {len(drawn)} balls. Winners: {len(winner_ids)} × {prize_per_winner} ETB (best match: {best})")
            else:
                conn.commit()
            cur.close()
            conn.close()
            schedule_next_game(game['stake'])
            break

        ball = draw_ball(drawn)
        if ball is None:
            cur.execute('UPDATE games SET status=%s, finished_at=%s WHERE id=%s', ('finished', time.time(), game_id))
            conn.commit()
            cur.close()
            conn.close()
            print(f"⚠️ Game {game_id}: All 75 balls drawn, no winner. Finishing.")
            schedule_next_game(game['stake'])
            break
        drawn.append(ball)
        cur.execute('UPDATE games SET drawn_balls=%s WHERE id=%s', (json.dumps(drawn), game_id))
        conn.commit()
        cur.execute('SELECT * FROM game_cards WHERE game_id=%s', (game_id,))
        cards = cur.fetchall()
        winners = []
        for c in cards:
            card_data = json.loads(c['card_data'])
            if check_bingo(card_data, set(drawn)):
                winners.append(c)
        if winners:
            total_pot = game['prize_pool']
            cur.execute("SELECT value FROM settings WHERE key='owner_cut_percent'")
            row = cur.fetchone()
            owner_cut = float(row['value']) if row else 20
            winner_percent = 100 - owner_cut
            winners_share = round(total_pot * winner_percent / 100, 2)
            card_count_per_user = {}
            for w in winners:
                uid = w['user_id']
                card_count_per_user[uid] = card_count_per_user.get(uid, 0) + 1
            total_winning_cards = sum(card_count_per_user.values())
            prize_per_card = round(winners_share / total_winning_cards, 2) if total_winning_cards > 0 else 0
            winner_card_numbers = [w['card_number'] for w in winners]
            for uid, cnt in card_count_per_user.items():
                prize_amount = round(prize_per_card * cnt, 2)
                cur.execute('UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s',
                            (prize_amount, prize_amount, uid))
            for uid in card_count_per_user.keys():
                cur.execute('SELECT referred_by FROM players WHERE user_id=%s', (uid,))
                ref_row = cur.fetchone()
                if ref_row and ref_row['referred_by']:
                    cur.execute("SELECT value FROM settings WHERE key='referral_commission_percent'")
                    comm_row = cur.fetchone()
                    comm_percent = float(comm_row['value']) if comm_row else 5.0
                    commission = round(total_pot * (comm_percent / 100), 2)
                    cur.execute('''INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at)
                                   VALUES (%s, %s, %s, %s, 'pending', %s)''',
                                (ref_row['referred_by'], uid, game_id, commission, time.time()))
            cur.execute('UPDATE games SET status=%s, finished_at=%s, winner_card_numbers=%s WHERE id=%s',
                        ('finished', time.time(), json.dumps(winner_card_numbers), game_id))
            conn.commit()
            print(f"✅ Game {game_id} FINISHED! {len(card_count_per_user)} winner(s), {total_winning_cards} winning cards, total paid {winners_share} ETB ({winner_percent}% of {total_pot})")
            cur.close()
            conn.close()
            schedule_next_game(game['stake'])
            break
        cur.close()
        conn.close()

def schedule_next_game(stake):
    time.sleep(3)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM games WHERE stake=%s AND status IN ('waiting','running') LIMIT 1", (stake,))
    existing = cur.fetchone()
    if not existing:
        cur.execute("INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')",
                    (stake, time.time()))
        conn.commit()
        cur.execute("SELECT id FROM games WHERE stake=%s AND status='waiting' ORDER BY id DESC LIMIT 1", (stake,))
        new_game = cur.fetchone()
        if new_game:
            start_game_engine(new_game['id'])
            print(f"🆕 New game {new_game['id']} for stake {stake}")
    cur.close()
    conn.close()

TELEBIRR_PATTERN = re.compile(r'received\s+ETB\s+([\d,]+\.?\d*)\s+from.*?transaction number is\s+([A-Z0-9]+)', re.IGNORECASE | re.DOTALL)
CBE_PATTERN = re.compile(r'received\s+ETB\s+([\d,]+\.?\d*)\s+from.*?https://Mbreciept\.cbe\.com\.et/[^\s]*([A-Z0-9]+)', re.IGNORECASE | re.DOTALL)

def parse_sms_reference(sms_text, platform):
    import re
    sms_text = sms_text.strip()
    normalized = ' '.join(sms_text.split())
    amount = None
    ref = None
    amount_match = re.search(r'ETB\s+([\d,]+\.?\d*)', normalized, re.IGNORECASE)
    ref_match = re.search(r'transaction\s+(?:number|no|id|code)\s+is\s+([A-Za-z0-9]+)', normalized, re.IGNORECASE)
    if amount_match and ref_match:
        amount = float(amount_match.group(1).replace(',', ''))
        ref = ref_match.group(1).strip()
        return amount, ref
    if amount_match:
        ref_match_cbe = re.search(r'https://[^\s]+/([A-Za-z0-9]+)', normalized, re.IGNORECASE)
        if ref_match_cbe:
            amount = float(amount_match.group(1).replace(',', ''))
            ref = ref_match_cbe.group(1).strip()
            return amount, ref
    return None, sms_text

def send_telegram_message(chat_id, text):
    from config import BOT_TOKEN
    bot_token = BOT_TOKEN
    if not bot_token:
        print("BOT_TOKEN not set")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': f"📢 *NEF BINGO Announcement*\n\n{text}",
        'parse_mode': 'Markdown'
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        return r.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

# ---------- Flask Routes ----------
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/admin')
def admin():
    return send_from_directory('templates', 'admin.html')

@app.route('/test-version')
def test_version():
    return "PostgreSQL version running"

@app.route('/run-migration')
def run_migration():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('CREATE TABLE IF NOT EXISTS referral_codes (user_id BIGINT PRIMARY KEY, code TEXT UNIQUE NOT NULL)')
        cur.execute('ALTER TABLE players ADD COLUMN IF NOT EXISTS referral_code TEXT UNIQUE DEFAULT NULL')
        cur.execute('''
            INSERT INTO referral_codes (user_id, code)
            SELECT p.user_id, UPPER(SUBSTRING(MD5(RANDOM()::TEXT), 1, 8))
            FROM players p
            WHERE p.user_id NOT IN (SELECT user_id FROM referral_codes)
            ON CONFLICT (user_id) DO NOTHING
        ''')
        cur.execute('''
            UPDATE players
            SET referral_code = rc.code
            FROM referral_codes rc
            WHERE players.user_id = rc.user_id AND players.referral_code IS NULL
        ''')
        conn.commit()
        return "Migration completed successfully"
    except Exception as e:
        return f"Error: {e}"
    finally:
        cur.close()
        conn.close()

@app.route('/api/player/<int:user_id>')
def get_player(user_id):
    username = request.args.get('username', 'user')
    full_name = request.args.get('full_name', 'User')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM players WHERE user_id=%s', (user_id,))
    p = cur.fetchone()
    if not p:
        cur.execute('INSERT INTO players (user_id, username, full_name) VALUES (%s,%s,%s)', (user_id, username, full_name))
        conn.commit()
        cur.execute('SELECT * FROM players WHERE user_id=%s', (user_id,))
        p = cur.fetchone()
    create_referral_code_for_user(user_id)
    result = dict(p)
    cur.execute('''
        SELECT g.id as game_id, g.status, g.stake
        FROM games g
        JOIN game_cards gc ON gc.game_id = g.id
        WHERE gc.user_id = %s AND g.status IN ('waiting','running')
        ORDER BY g.id DESC LIMIT 1
    ''', (user_id,))
    active = cur.fetchone()
    result['active_game'] = dict(active) if active else None
    cur.close()
    conn.close()
    return jsonify(result)

@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    data = request.json
    user_id = data.get('user_id')
    phone = data.get('phone', '').strip()
    language = data.get('language', '')
    referral_code = data.get('referral_code', '').strip()
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    if phone:
        cur.execute('SELECT user_id FROM players WHERE phone=%s AND user_id!=%s AND phone IS NOT NULL', (phone, user_id))
        existing = cur.fetchone()
        if existing:
            cur.close()
            conn.close()
            return jsonify({'error': 'This phone number is already registered with another account.'}), 400
        cur.execute('UPDATE players SET phone=%s WHERE user_id=%s', (phone, user_id))
    if language and language in ['en','am','om','ti']:
        cur.execute('UPDATE players SET language=%s WHERE user_id=%s', (language, user_id))
    if referral_code:
        cur.execute('SELECT referred_by FROM players WHERE user_id=%s', (user_id,))
        existing_ref = cur.fetchone()
        if not existing_ref or not existing_ref['referred_by']:
            cur.execute('SELECT user_id FROM referral_codes WHERE code=%s', (referral_code,))
            referrer = cur.fetchone()
            if referrer and referrer['user_id'] != user_id:
                cur.execute('UPDATE players SET referred_by=%s WHERE user_id=%s', (referrer['user_id'], user_id))
                conn.commit()
                award_referral_bonus(referrer['user_id'], user_id)
    conn.commit()
    create_referral_code_for_user(user_id)
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/reset_player', methods=['POST'])
def reset_player():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE players SET phone=NULL, language="en" WHERE user_id=%s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Account reset. Please re‑register.'})

_join_lock = threading.Lock()

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data = request.json
    user_id = data.get('user_id')
    stake = data.get('stake')
    if not user_id or not stake:
        return jsonify({'error': 'user_id and stake are required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT is_banned FROM players WHERE user_id=%s', (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            cur.close()
            conn.close()
            return jsonify({'error': 'Your account has been suspended. Contact support.'}), 403
        with _join_lock:
            cur.execute('''
                SELECT * FROM games WHERE stake=%s AND status IN ('waiting','running')
                ORDER BY id DESC LIMIT 1
            ''', (stake,))
            game = cur.fetchone()
            if not game:
                cur.execute('''INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls)
                               VALUES (%s, 0, %s, 'waiting', '[]')''', (stake, time.time()))
                conn.commit()
                cur.execute('''
                    SELECT * FROM games WHERE stake=%s AND status='waiting'
                    ORDER BY id DESC LIMIT 1
                ''', (stake,))
                game = cur.fetchone()
                start_game_engine(game['id'])
        game_id = game['id']
        cur.execute('SELECT card_number FROM game_cards WHERE game_id=%s', (game_id,))
        taken = [r['card_number'] for r in cur.fetchall()]
        cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
        players = len({r['user_id'] for r in cur.fetchall()})
        elapsed = time.time() - game['created_at']
        countdown = max(0, min(30, int(30 - elapsed)))
        cur.close()
        conn.close()
        return jsonify({
            'game_id': game_id,
            'stake': stake,
            'prize_pool': game['prize_pool'],
            'players': players,
            'taken_cards': taken,
            'countdown': countdown,
            'status': game['status']
        })
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        print(f"Error in join_game: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id, game_id, card_number, stake = (data['user_id'], data['game_id'], data['card_number'], data['stake'])
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT stake, status FROM games WHERE id=%s', (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game has already started or finished'}), 400
        if game['stake'] != stake:
            return jsonify({'error': f'Stake mismatch. Game stake is {game["stake"]} ETB'})
        cur.execute('SELECT balance FROM players WHERE user_id=%s', (user_id,))
        row = cur.fetchone()
        if not row or row['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'})
        cur.execute('SELECT id FROM game_cards WHERE game_id=%s AND card_number=%s', (game_id, card_number))
        if cur.fetchone():
            return jsonify({'error': 'Card already taken'})
        cur.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, user_id))
        card_count = cur.fetchone()['count']
        if card_count >= 4:
            return jsonify({'error': 'Max 4 cards per game'})
        cur.execute('INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s,%s,%s,%s)',
                    (game_id, user_id, card_number, json.dumps(generate_card())))
        cur.execute('UPDATE players SET balance=balance-%s, games_played=games_played+1 WHERE user_id=%s', (stake, user_id))
        cur.execute('UPDATE games SET prize_pool=prize_pool+%s WHERE id=%s', (stake, game_id))
        conn.commit()
        cur.execute('SELECT balance FROM players WHERE user_id=%s', (user_id,))
        new_bal = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': new_bal})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/withdraw_from_game', methods=['POST'])
def withdraw_from_game():
    data = request.json
    user_id = data.get('user_id')
    game_id = data.get('game_id')
    if not user_id or not game_id:
        return jsonify({'error': 'user_id and game_id required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT status, stake FROM games WHERE id=%s', (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'waiting':
            return jsonify({'error': 'Game already started or not found'}), 400
        stake = game['stake']
        cur.execute('SELECT card_number FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, user_id))
        cards = cur.fetchall()
        if not cards:
            return jsonify({'error': 'No cards found for this user in this game'}), 404
        refund = stake * len(cards)
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (refund, user_id))
        cur.execute('DELETE FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, user_id))
        cur.execute('UPDATE games SET prize_pool=prize_pool-%s WHERE id=%s', (refund, game_id))
        conn.commit()
        from config import ADMIN_IDS
        cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
        remaining = cur.fetchall()
        real_remaining = [r['user_id'] for r in remaining if r['user_id'] not in ADMIN_IDS and r['user_id'] > 0]
        if not real_remaining:
            remove_all_bots_from_game(game_id, stake)
            cur.execute('UPDATE games SET status="finished", cancelled=1, finished_at=%s WHERE id=%s', (time.time(), game_id))
            conn.commit()
            return jsonify({'success': True, 'message': 'Game cancelled because you were the last real player.'})
        return jsonify({'success': True, 'message': 'Withdrawn from game.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    user_id = request.args.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM games WHERE id=%s', (game_id,))
    game = cur.fetchone()
    if not game:
        cur.close()
        conn.close()
        return jsonify({'error': 'Game not found'}), 404
    drawn = json.loads(game['drawn_balls'] or '[]')
    cur.execute('SELECT card_number FROM game_cards WHERE game_id=%s', (game_id,))
    taken = [r['card_number'] for r in cur.fetchall()]
    cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
    players = len({r['user_id'] for r in cur.fetchall()})
    total_pool = game['prize_pool']
    winners_share = round(total_pool * 0.80, 2)
    result = {
        'status': game['status'], 'drawn_balls': drawn, 'prize_pool': total_pool,
        'winners_share': winners_share, 'stake': game['stake'], 'players': players, 'taken_cards': taken,
    }
    if game['status'] == 'finished' and game['cancelled'] == 1:
        result['status'] = 'cancelled'
        result['cancelled_message'] = 'በቂ ተጫዋቾች የሉም። ጨዋታው ተሰርዟል። ገንዘብዎ ተመልሷል። እባክዎ እንደገና ይሞክሩ።'
        result['next_game_id'] = None
        cur.close()
        conn.close()
        return jsonify(result)
    if game['status'] == 'finished':
        winner_card_numbers = json.loads(game['winner_card_numbers'] or '[]')
        if winner_card_numbers:
            placeholders = ','.join(['%s'] * len(winner_card_numbers))
            cur.execute(f'''
                SELECT gc.card_number, p.full_name, p.user_id
                FROM game_cards gc
                JOIN players p ON gc.user_id = p.user_id
                WHERE gc.game_id = %s AND gc.card_number IN ({placeholders})
            ''', [game_id] + winner_card_numbers)
            winners_raw = cur.fetchall()
        else:
            winners_raw = []
        num_winners = len(winner_card_numbers)
        prize_each = round(winners_share / num_winners, 2) if num_winners > 0 else 0
        result['winners'] = [
            {'name': w['full_name'], 'card_number': w['card_number'], 'prize': prize_each}
            for w in winners_raw
        ]
        result['prize_each'] = prize_each
        cur.execute('''
            SELECT id FROM games
            WHERE stake = %s AND status = 'waiting' AND id != %s
            ORDER BY id DESC LIMIT 1
        ''', (game['stake'], game_id))
        next_game = cur.fetchone()
        result['next_game_id'] = next_game['id'] if next_game else None
    cur.close()
    conn.close()
    return jsonify(result)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT card_number, card_data FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, user_id))
    cards = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'cards': [{'card_index': c['card_number'], 'card_data': json.loads(c['card_data'])} for c in cards]})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    platform = data.get('platform', 'telebirr')
    proof = data.get('tx_ref', '').strip()
    if not proof:
        return jsonify({'error': 'Transaction reference is required'}), 400
    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id FROM deposits WHERE tx_ref=%s', (proof,))
        if cur.fetchone():
            return jsonify({'error': 'This transaction reference has already been used.'}), 400
        sms_amount, tx_ref = parse_sms_reference(proof, platform)
        if sms_amount is not None and tx_ref and abs(sms_amount - amount) <= 5:
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (amount, user_id))
            cur.execute("SELECT value FROM settings WHERE key='deposit_bonus_percent'")
            row = cur.fetchone()
            bonus_percent = float(row['value']) if row else 0
            if bonus_percent > 0:
                bonus_amount = round(amount * bonus_percent / 100, 2)
                cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (bonus_amount, user_id))
                print(f"🎁 Deposit bonus: {bonus_percent}% = +{bonus_amount} ETB for user {user_id}")
            cur.execute('INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at) VALUES (%s,%s,%s,%s,%s,%s)',
                        (user_id, amount, platform, tx_ref, 'approved', time.time()))
            conn.commit()
            cur.execute('SELECT balance FROM players WHERE user_id=%s', (user_id,))
            new_bal = cur.fetchone()['balance']
            cur.close()
            conn.close()
            return jsonify({'success': True, 'approved': True, 'message': f'✅ {amount} ETB credited!', 'balance': new_bal})
        cur.execute('INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at) VALUES (%s,%s,%s,%s,%s,%s)',
                    (user_id, amount, platform, proof, 'pending', time.time()))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'approved': False, 'message': '⏳ Deposit submitted for admin review.'})
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

MIN_WITHDRAWAL = 50
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    amount = data.get('amount', 0)
    if amount < MIN_WITHDRAWAL:
        return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAWAL} ETB'})
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT balance FROM players WHERE user_id=%s', (data['user_id'],))
        row = cur.fetchone()
        if not row or row['balance'] < amount:
            return jsonify({'error': 'Insufficient balance'})
        cur.execute('UPDATE players SET balance=balance-%s WHERE user_id=%s', (amount, data['user_id']))
        cur.execute('INSERT INTO withdrawals (user_id, amount, platform, account_no, created_at) VALUES (%s,%s,%s,%s,%s)',
                    (data['user_id'], amount, data['platform'], data['account_no'], time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': 'Withdrawal requested.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO inquiries (user_id, subject, message, created_at) VALUES (%s,%s,%s,%s)',
                (data['user_id'], data['subject'], data['message'], time.time()))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/transactions/<int:user_id>')
def transactions(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT "deposit" as type, amount, platform as detail, status, created_at FROM deposits WHERE user_id=%s ORDER BY created_at DESC LIMIT 20', (user_id,))
    deps = cur.fetchall()
    cur.execute('SELECT "withdrawal" as type, amount, platform as detail, status, created_at FROM withdrawals WHERE user_id=%s ORDER BY created_at DESC LIMIT 20', (user_id,))
    wds = cur.fetchall()
    txs = []
    for d in deps:
        txs.append(dict(d))
    for w in wds:
        txs.append(dict(w))
    txs.sort(key=lambda x: x['created_at'], reverse=True)
    cur.close()
    conn.close()
    return jsonify({'transactions': txs})

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT full_name, wins, total_won, games_played FROM players WHERE is_banned=0 ORDER BY total_won DESC LIMIT 20')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'leaderboard': [dict(r) for r in rows]})

@app.route('/api/referral_stats/<int:user_id>')
def referral_stats(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT code FROM referral_codes WHERE user_id=%s', (user_id,))
    code = cur.fetchone()
    code_val = code['code'] if code else None
    cur.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id=%s', (user_id,))
    ref_count = cur.fetchone()['count']
    cur.execute('SELECT COALESCE(SUM(amount),0) FROM referral_commissions WHERE referrer_id=%s AND status="pending"', (user_id,))
    pending_total = cur.fetchone()['coalesce']
    cur.execute('SELECT COALESCE(SUM(amount),0) FROM referral_commissions_archive WHERE referrer_id=%s', (user_id,))
    paid_total = cur.fetchone()['coalesce']
    cur.close()
    conn.close()
    return jsonify({
        'referral_code': code_val,
        'referral_count': ref_count,
        'pending_commissions': pending_total,
        'total_commissions_paid': paid_total
    })

@app.route('/api/settings/<key>')
def get_setting(key):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT value FROM settings WHERE key=%s', (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return jsonify({key: row['value']})
    return jsonify({key: None}), 404

@app.route('/api/set_chat_id', methods=['POST'])
def set_chat_id():
    data = request.json
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return jsonify({'error': 'User ID and Chat ID required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE players SET chat_id=%s WHERE user_id=%s', (chat_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/sms_webhook', methods=['POST'])
def sms_webhook():
    api_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get('SMS_WEBHOOK_SECRET')
    if expected_key and (not api_key or api_key != expected_key):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'Invalid SMS data'}), 400
    sms_content = data['content']
    amount, ref = parse_sms_reference(sms_content, 'telebirr')
    if not amount:
        amount, ref = parse_sms_reference(sms_content, 'cbe')
    if not amount or not ref:
        return jsonify({'error': 'Could not parse amount/reference from SMS'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM deposits WHERE tx_ref=%s AND status="pending"', (ref,))
        deposit = cur.fetchone()
        if not deposit:
            return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
        if abs(deposit['amount'] - amount) > 5:
            return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {deposit["amount"]}'}), 400
        cur.execute("UPDATE deposits SET status='approved' WHERE id=%s", (deposit['id'],))
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (deposit['amount'], deposit['user_id']))
        cur.execute("SELECT value FROM settings WHERE key='deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(deposit['amount'] * bonus_percent / 100, 2)
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (bonus_amount, deposit['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Deposit auto-approved'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "nefbingo2026")
def admin_auth(data):
    return data.get('password') == ADMIN_PASSWORD

@app.route('/admin/api/overview')
def admin_overview():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM players')
    total_players = cur.fetchone()['count']
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'")
    total_deposited = cur.fetchone()['coalesce']
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'")
    total_withdrawn = cur.fetchone()['coalesce']
    cur.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")
    pending_deposits = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    pending_withdrawals = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) FROM games WHERE status IN ('waiting','running')")
    active_games = cur.fetchone()['count']
    cur.close()
    conn.close()
    return jsonify({
        'total_players': total_players,
        'total_deposited': total_deposited,
        'total_withdrawn': total_withdrawn,
        'pending_deposits': pending_deposits,
        'pending_withdrawals': pending_withdrawals,
        'active_games': active_games
    })

@app.route('/admin/api/players')
def admin_players():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM players ORDER BY balance DESC')
    rows = cur.fetchall()
    players = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'players': players})

@app.route('/admin/api/deposits')
def admin_deposits():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT d.*, p.full_name FROM deposits d
                   LEFT JOIN players p ON d.user_id=p.user_id
                   ORDER BY d.id DESC LIMIT 50''')
    rows = cur.fetchall()
    deposits = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'deposits': deposits})

@app.route('/admin/api/withdrawals')
def admin_withdrawals():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT w.*, p.full_name FROM withdrawals w
                   LEFT JOIN players p ON w.user_id=p.user_id
                   ORDER BY w.id DESC LIMIT 50''')
    rows = cur.fetchall()
    withdrawals = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'withdrawals': withdrawals})

@app.route('/admin/api/active_games')
def admin_active_games():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT g.*, COUNT(gc.id) as card_count
                   FROM games g LEFT JOIN game_cards gc ON gc.game_id=g.id
                   WHERE g.status IN ('waiting','running')
                   GROUP BY g.id ORDER BY g.id DESC''')
    rows = cur.fetchall()
    games = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'games': games})

@app.route('/admin/approve_deposit', methods=['POST'])
def approve_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, user_id, amount, status FROM deposits WHERE id=%s', (data['deposit_id'],))
        dep = cur.fetchone()
        if not dep or dep['status'] != 'pending':
            return jsonify({'error': 'Invalid or already approved'}), 400
        cur.execute("UPDATE deposits SET status='approved' WHERE id=%s", (data['deposit_id'],))
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (dep['amount'], dep['user_id']))
        cur.execute("SELECT value FROM settings WHERE key='deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (bonus_amount, dep['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f'Approved +{dep["amount"]} ETB'})
    except Exception as e:
        conn.rollback()
        print(f"Error in approve_deposit: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/reject_deposit', methods=['POST'])
def reject_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE deposits SET status='rejected' WHERE id=%s", (data['deposit_id'],))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/approve_withdrawal', methods=['POST'])
def approve_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE withdrawals SET status='approved' WHERE id=%s", (data['withdrawal_id'],))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/reject_withdrawal', methods=['POST'])
def reject_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE withdrawals SET status='rejected' WHERE id=%s", (data['withdrawal_id'],))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/give_bonus', methods=['POST'])
def give_bonus():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    user_id = data.get('user_id')
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin bonus')
    if not user_id or amount <= 0:
        return jsonify({'error': 'Invalid user or amount'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (amount, user_id))
        cur.execute('INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s,%s,%s,%s)',
                    (user_id, amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to user {user_id}'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/give_bonus_all', methods=['POST'])
def give_bonus_all():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT user_id FROM players WHERE is_banned=0')
        players = cur.fetchall()
        for p in players:
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (amount, p['user_id']))
            cur.execute('INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s,%s,%s,%s)',
                        (p['user_id'], amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to all {len(players)} players'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/api/get_user_by_phone', methods=['POST'])
def get_user_by_phone():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT user_id, full_name FROM players WHERE phone=%s', (phone,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        return jsonify({'error': 'No player found with that phone number'}), 404
    return jsonify({'user_id': user['user_id'], 'full_name': user['full_name']})

@app.route('/admin/ban_player', methods=['POST'])
def ban_player():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE players SET is_banned=%s WHERE user_id=%s', (1 if data.get('ban') else 0, data['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/force_finish', methods=['POST'])
def force_finish():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    game_id = data['game_id']
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM games WHERE id=%s', (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        stake = game['stake']
        cur.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s', (game_id,))
        card_holders = cur.fetchall()
        for row in card_holders:
            cur.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=%s AND user_id=%s', (game_id, row['user_id']))
            card_count = cur.fetchone()['count']
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (stake * card_count, row['user_id']))
        cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/api/auto_verify_deposit', methods=['POST'])
def auto_verify_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    sms_text = data.get('sms_text', '').strip()
    if not sms_text:
        return jsonify({'error': 'SMS text is required'}), 400
    amount, ref = parse_sms_reference(sms_text, 'telebirr')
    if not amount:
        amount, ref = parse_sms_reference(sms_text, 'cbe')
    if not amount or not ref:
        return jsonify({'error': 'Could not parse amount and reference from SMS'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT * FROM deposits WHERE tx_ref=%s AND status="pending"', (ref,))
        dep = cur.fetchone()
        if not dep:
            return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
        if abs(dep['amount'] - amount) > 5:
            return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {dep["amount"]}'}), 400
        cur.execute("UPDATE deposits SET status='approved' WHERE id=%s", (dep['id'],))
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (dep['amount'], dep['user_id']))
        cur.execute("SELECT value FROM settings WHERE key='deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
            cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (bonus_amount, dep['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f'Deposit #{dep["id"]} auto-approved.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ---------- Multi-Admin ----------
@app.route('/admin/api/add_admin', methods=['POST'])
def add_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT role FROM admins WHERE user_id=%s', (data['admin_user_id'],))
    requester = cur.fetchone()
    if not requester or requester['role'] != 'super_admin':
        cur.close()
        conn.close()
        return jsonify({'error': 'Only super admin can add admins'}), 403
    new_admin_id = data.get('new_admin_id')
    role = data.get('role', 'admin')
    if not new_admin_id:
        return jsonify({'error': 'user_id required'}), 400
    cur.execute('INSERT INTO admins (user_id, role, added_by, created_at) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (new_admin_id, role, data['admin_user_id'], time.time()))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/api/remove_admin', methods=['POST'])
def remove_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT role FROM admins WHERE user_id=%s', (data['admin_user_id'],))
    requester = cur.fetchone()
    if not requester or requester['role'] != 'super_admin':
        cur.close()
        conn.close()
        return jsonify({'error': 'Only super admin can remove admins'}), 403
    admin_id = data.get('admin_id')
    if admin_id == data['admin_user_id']:
        return jsonify({'error': 'Cannot remove yourself'}), 400
    cur.execute('DELETE FROM admins WHERE user_id=%s', (admin_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/api/admins')
def get_admins():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM admins')
    rows = cur.fetchall()
    admins = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'admins': admins})

# ---------- Referral Commission Admin ----------
@app.route('/admin/api/update_referral_settings', methods=['POST'])
def update_referral_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    if 'commission_percent' in data:
        cur.execute("UPDATE settings SET value=%s WHERE key='referral_commission_percent'", (str(data['commission_percent']),))
    if 'bonus_amount' in data:
        cur.execute("UPDATE settings SET value=%s WHERE key='referral_bonus_amount'", (str(data['bonus_amount']),))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/api/referral_settings')
def referral_settings():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='referral_commission_percent'")
    percent = cur.fetchone()
    cur.execute("SELECT value FROM settings WHERE key='referral_bonus_amount'")
    bonus = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({
        'commission_percent': float(percent['value']) if percent else 5.0,
        'bonus_amount': float(bonus['value']) if bonus else 10.0
    })

@app.route('/admin/api/pending_commissions')
def pending_commissions():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT c.*, p.full_name as referrer_name, p2.full_name as referred_name
                   FROM referral_commissions c
                   JOIN players p ON c.referrer_id = p.user_id
                   JOIN players p2 ON c.referred_id = p2.user_id
                   WHERE c.status = 'pending' ORDER BY c.created_at DESC''')
    rows = cur.fetchall()
    commissions = [dict(r) for r in rows]
    cur.close()
    conn.close()
    return jsonify({'commissions': commissions})

@app.route('/admin/api/revoke_commission', methods=['POST'])
def revoke_commission():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    commission_id = data.get('commission_id')
    if not commission_id:
        return jsonify({'error': 'commission_id required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM referral_commissions WHERE id=%s AND status="pending"', (commission_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Commission revoked'})

@app.route('/admin/api/adjust_commission', methods=['POST'])
def adjust_commission():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    commission_id = data.get('commission_id')
    new_amount = data.get('new_amount')
    if not commission_id or new_amount is None:
        return jsonify({'error': 'commission_id and new_amount required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE referral_commissions SET amount=%s WHERE id=%s AND status="pending"', (new_amount, commission_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'message': f'Commission updated to {new_amount} ETB'})

@app.route('/admin/api/process_weekly_payout', methods=['POST'])
def process_weekly_payout():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM referral_commissions WHERE status="pending"')
    pending = cur.fetchall()
    if not pending:
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'No pending commissions'})
    week_start = time.time() - 7*86400
    week_end = time.time()
    total_paid = 0
    for comm in pending:
        cur.execute('UPDATE players SET balance=balance+%s WHERE user_id=%s', (comm['amount'], comm['referrer_id']))
        cur.execute('UPDATE referral_commissions SET status="paid", paid_at=%s WHERE id=%s', (time.time(), comm['id']))
        cur.execute('''INSERT INTO referral_commissions_archive 
                       (referrer_id, referred_id, game_id, amount, paid_at, payment_week_start, payment_week_end)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (comm['referrer_id'], comm['referred_id'], comm['game_id'], comm['amount'], time.time(), week_start, week_end))
        total_paid += comm['amount']
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'total_paid': total_paid, 'count': len(pending)})

# ---------- Max balls and bot settings ----------
@app.route('/admin/api/set_max_balls', methods=['POST'])
def set_max_balls():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    max_balls = data.get('max_balls')
    if max_balls is None:
        return jsonify({'error': 'max_balls required'}), 400
    try:
        max_balls = int(max_balls)
        if max_balls < 0 or max_balls > 75:
            max_balls = 75
    except:
        max_balls = 75
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE settings SET value=%s WHERE key='max_balls_per_game'", (str(max_balls),))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True, 'max_balls': max_balls})

@app.route('/admin/api/update_bot_settings', methods=['POST'])
def update_bot_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    if 'bot_enabled' in data:
        cur.execute("UPDATE settings SET value=%s WHERE key='bot_enabled'", (str(data['bot_enabled']),))
    if 'bot_max_bots' in data:
        cur.execute("UPDATE settings SET value=%s WHERE key='bot_max_bots'", (str(data['bot_max_bots']),))
    if 'bot_target_real_players' in data:
        cur.execute("UPDATE settings SET value=%s WHERE key='bot_target_real_players'", (str(data['bot_target_real_players']),))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/api/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    telebirr = data.get('telebirr_number', '').strip()
    cbe = data.get('cbe_number', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()
    if telebirr:
        cur.execute("UPDATE settings SET value=%s WHERE key='telebirr_number'", (telebirr,))
    if cbe:
        cur.execute("UPDATE settings SET value=%s WHERE key='cbe_number'", (cbe,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    create_bot_players()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
