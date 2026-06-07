from flask import Flask, request, jsonify, send_from_directory
import sqlite3, json, time, os, threading, re, secrets, string
import requests
import random
from game.bingo_logic import generate_card, draw_ball, check_bingo

app = Flask(__name__, static_folder='static', template_folder='templates')

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'bingo.db')

def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def count_players_in_game(game_id):
    db = get_db()
    players = db.execute('SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=?', (game_id,)).fetchone()
    db.close()
    return players['cnt'] if players else 0

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT, full_name TEXT,
            balance REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            phone TEXT DEFAULT NULL,
            language TEXT DEFAULT "en",
            chat_id TEXT DEFAULT NULL,
            referred_by INTEGER DEFAULT NULL,
            referral_code TEXT UNIQUE DEFAULT NULL,
            referral_bonus_earned REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stake INTEGER, status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]',
            created_at REAL, started_at REAL, finished_at REAL,
            cancelled INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS game_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER, user_id INTEGER,
            card_number INTEGER, card_data TEXT
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            platform TEXT, tx_ref TEXT,
            status TEXT DEFAULT 'pending', created_at REAL
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            platform TEXT, account_no TEXT,
            status TEXT DEFAULT 'pending', created_at REAL
        );
        CREATE TABLE IF NOT EXISTS inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, subject TEXT,
            message TEXT, status TEXT DEFAULT 'open', created_at REAL
        );
        CREATE TABLE IF NOT EXISTS bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            reason TEXT, admin_note TEXT, created_at REAL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_broadcast INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by INTEGER,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        );
        CREATE TABLE IF NOT EXISTS referral_commissions_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            paid_at REAL,
            payment_week_start REAL,
            payment_week_end REAL
        );
    ''')
    for col in ['is_banned','phone','language','chat_id','referred_by','referral_code','referral_bonus_earned']:
        try: db.execute(f'ALTER TABLE players ADD COLUMN {col} DEFAULT NULL'); db.commit()
        except: pass
    try: db.execute('ALTER TABLE games ADD COLUMN winner_card_numbers TEXT DEFAULT "[]"'); db.commit()
    except: pass
    try: db.execute('ALTER TABLE games ADD COLUMN cancelled INTEGER DEFAULT 0'); db.commit()
    except: pass
    try: db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_phone ON players(phone)'); db.commit()
    except: pass
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('telebirr_number', '0929 001 000')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cbe_number', '1000061737212')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deposit_bonus_percent', '0')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_commission_percent', '5')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_bonus_amount', '10')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('owner_cut_percent', '20')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('max_balls_per_game', '75')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_enabled', '1')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_max_bots', '2')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_target_real_players', '3')")
    db.commit()
    db.close()

init_db()

def create_bot_players():
    bot_names = [
        ("Admasu Kebe", "admasu_k"), ("Yichilal", "yichilal"),
        ("Aradaw Tade", "aradaw_t"), ("Shime Gondar", "shime_g"),
        ("Emu Konjo", "emu_k"), ("Tigist Desta", "tigist_d"),
        ("Biruk Alemu", "biruk_a"), ("Meron Assefa", "meron_a"),
        ("Dawit Mekonnen", "dawit_m"), ("Hana Tesfaye", "hana_t")
    ]
    db = get_db()
    bot_id = -1
    for full_name, username in bot_names:
        existing = db.execute("SELECT user_id FROM players WHERE user_id=?", (bot_id,)).fetchone()
        if not existing:
            db.execute("INSERT INTO players (user_id, username, full_name, balance) VALUES (?,?,?,?)",
                       (bot_id, username, full_name, 1000))
        bot_id -= 1
    db.commit()
    db.close()

create_bot_players()

def generate_referral_code():
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        db = get_db()
        existing = db.execute('SELECT code FROM referral_codes WHERE code = ?', (code,)).fetchone()
        db.close()
        if not existing:
            return code

def create_referral_code_for_user(user_id):
    db = get_db()
    existing = db.execute('SELECT code FROM referral_codes WHERE user_id = ?', (user_id,)).fetchone()
    if not existing:
        code = generate_referral_code()
        db.execute('INSERT INTO referral_codes (user_id, code) VALUES (?, ?)', (user_id, code))
        db.execute('UPDATE players SET referral_code = ? WHERE user_id = ?', (code, user_id))
        db.commit()
        db.close()
        return code
    db.close()
    return existing['code']

def award_referral_bonus(referrer_id, referred_id):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'").fetchone()
    bonus_amt = float(row['value']) if row else 10.0
    db.execute('UPDATE players SET balance = balance + ?, referral_bonus_earned = referral_bonus_earned + ? WHERE user_id = ?', (bonus_amt, bonus_amt, referrer_id))
    db.execute('INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)', (referrer_id, referred_id, time.time()))
    db.commit()
    db.close()
    print(f"🎁 Referral bonus: +{bonus_amt} ETB to user {referrer_id} for referring {referred_id}")

# Helper to add a single bot (1 card)
def add_single_bot(game_id, stake):
    db = get_db()
    # Get available bots not already in this game
    all_bots = db.execute("SELECT user_id FROM players WHERE user_id < 0").fetchall()
    bot_ids = [b['user_id'] for b in all_bots]
    if not bot_ids:
        db.close()
        return False
    existing_bots = db.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=? AND user_id < 0", (game_id,)).fetchall()
    existing_bot_ids = [b['user_id'] for b in existing_bots]
    available = [bid for bid in bot_ids if bid not in existing_bot_ids]
    if not available:
        db.close()
        return False
    bot_id = random.choice(available)
    # Ensure balance
    bot = db.execute("SELECT balance FROM players WHERE user_id=?", (bot_id,)).fetchone()
    if bot['balance'] < stake:
        db.execute("UPDATE players SET balance=balance+1000 WHERE user_id=?", (bot_id,))
    # Pick random available card (1-500)
    taken = [r['card_number'] for r in db.execute("SELECT card_number FROM game_cards WHERE game_id=?", (game_id,)).fetchall()]
    available_cards = [i for i in range(1, 501) if i not in taken]
    if not available_cards:
        db.close()
        return False
    card_num = random.choice(available_cards)
    db.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (?,?,?,?)",
               (game_id, bot_id, card_num, json.dumps(generate_card())))
    db.execute("UPDATE players SET balance=balance-?, games_played=games_played+1 WHERE user_id=?", (stake, bot_id))
    db.execute("UPDATE games SET prize_pool=prize_pool+? WHERE id=?", (stake, game_id))
    db.commit()
    bot_name = db.execute("SELECT full_name FROM players WHERE user_id=?", (bot_id,)).fetchone()['full_name']
    print(f"🤖 Bot {bot_name} (ID {bot_id}) joined game {game_id} with card {card_num}")
    db.close()
    return True

# Helper to remove all bots from a game (refund)
def remove_all_bots_from_game(game_id, stake):
    db = get_db()
    bot_cards = db.execute("SELECT id, user_id FROM game_cards WHERE game_id=? AND user_id < 0", (game_id,)).fetchall()
    for card in bot_cards:
        db.execute("DELETE FROM game_cards WHERE id=?", (card['id'],))
        db.execute("UPDATE players SET balance=balance+? WHERE user_id=?", (stake, card['user_id']))
    # Reduce prize pool
    db.execute("UPDATE games SET prize_pool=prize_pool-? WHERE id=?", (stake * len(bot_cards), game_id))
    db.commit()
    print(f"🚫 Removed {len(bot_cards)} bot(s) from game {game_id} (refunded)")
    db.close()

_engine_lock = threading.Lock()
_running_engines = set()

def start_game_engine(game_id):
    with _engine_lock:
        if game_id in _running_engines:
            return
        _running_engines.add(game_id)

    def engine():
        try:
            time.sleep(2)  # allow players to pick initial cards
            db = get_db()
            game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
            if not game or game['status'] != 'waiting':
                db.close()
                return
            stake = game['stake']
            from config import ADMIN_IDS
            bot_enabled = int(db.execute("SELECT value FROM settings WHERE key='bot_enabled'").fetchone()[0])
            max_bots = int(db.execute("SELECT value FROM settings WHERE key='bot_max_bots'").fetchone()[0])
            target_real = int(db.execute("SELECT value FROM settings WHERE key='bot_target_real_players'").fetchone()[0])

            # Only run bot logic for 10 ETB games and if enabled
            if bot_enabled and stake == 10:
                def get_real_count():
                    all_players = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
                    return len([p['user_id'] for p in all_players if p['user_id'] not in ADMIN_IDS and p['user_id'] > 0])

                added_bots = 0
                start_time = time.time()
                # Loop during the 30-second waiting period
                while time.time() - start_time < 30:
                    current_real = get_real_count()
                    # If real players reached target, remove all bots and stop
                    if current_real >= target_real:
                        remove_all_bots_from_game(game_id, stake)
                        break
                    # If we haven't reached max bots and still need to add
                    if added_bots < max_bots:
                        # Check again real count after potential withdrawal
                        if get_real_count() >= target_real:
                            remove_all_bots_from_game(game_id, stake)
                            break
                        success = add_single_bot(game_id, stake)
                        if success:
                            added_bots += 1
                    # Wait 3 seconds before next bot
                    time.sleep(3)
                    # Re-check game status (might have been cancelled)
                    game_check = db.execute('SELECT status FROM games WHERE id=?', (game_id,)).fetchone()
                    if not game_check or game_check['status'] != 'waiting':
                        break
                # End of while loop

            # After bot logic, proceed with original start_game_engine checks
            db = get_db()
            game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
            if not game or game['status'] != 'waiting':
                db.close()
                return
            all_players = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
            real_count = len([p['user_id'] for p in all_players if p['user_id'] not in ADMIN_IDS and p['user_id'] > 0])
            if real_count == 0:
                db.execute('UPDATE games SET status="finished", finished_at=?, cancelled=1, winner_card_numbers="[]" WHERE id=?',
                           (time.time(), game_id))
                card_holders = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
                for player in card_holders:
                    card_count = db.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=? AND user_id=?',
                                            (game_id, player['user_id'])).fetchone()[0]
                    refund = stake * card_count
                    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (refund, player['user_id']))
                db.commit()
                db.close()
                print(f"🚫 Game {game_id} cancelled: no real players. Refunded all.")
                return
            # Start the game
            db.execute('UPDATE games SET status="running", started_at=? WHERE id=?', (time.time(), game_id))
            db.commit()
            db.close()
            draw_loop(game_id)
        finally:
            with _engine_lock:
                _running_engines.discard(game_id)

    threading.Thread(target=engine, daemon=True).start()

def draw_loop(game_id):
    while True:
        time.sleep(1)
        db = get_db()
        game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
        if not game or game['status'] != 'running':
            db.close()
            break
        drawn = json.loads(game['drawn_balls'])
        max_balls = db.execute("SELECT value FROM settings WHERE key='max_balls_per_game'").fetchone()
        max_balls = int(max_balls['value']) if max_balls else 75
        if len(drawn) >= max_balls:
            db.execute('UPDATE games SET status="finished", finished_at=? WHERE id=?', (time.time(), game_id))
            cards = db.execute('SELECT * FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
            if not cards:
                db.commit(); db.close()
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
                    db.execute('UPDATE players SET balance=balance+?, wins=wins+1, total_won=total_won+? WHERE user_id=?',
                               (prize_per_winner, prize_per_winner, uid))
                db.execute('UPDATE games SET winner_card_numbers=? WHERE id=?', (json.dumps([]), game_id))
                db.commit()
                print(f"🏁 Game {game_id} ended after {len(drawn)} balls. Winners: {len(winner_ids)} × {prize_per_winner} ETB (best match: {best})")
            else:
                db.commit()
            db.close()
            schedule_next_game(game['stake'])
            break

        ball = draw_ball(drawn)
        if ball is None:
            db.execute('UPDATE games SET status="finished", finished_at=? WHERE id=?', (time.time(), game_id))
            db.commit()
            db.close()
            print(f"⚠️ Game {game_id}: All 75 balls drawn, no winner. Finishing.")
            schedule_next_game(game['stake'])
            break
        drawn.append(ball)
        db.execute('UPDATE games SET drawn_balls=? WHERE id=?', (json.dumps(drawn), game_id))
        db.commit()
        cards = db.execute('SELECT * FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
        winners = []
        for c in cards:
            card_data = json.loads(c['card_data'])
            if check_bingo(card_data, set(drawn)):
                winners.append(c)
        if winners:
            total_pot = game['prize_pool']
            row = db.execute("SELECT value FROM settings WHERE key='owner_cut_percent'").fetchone()
            owner_cut = float(row['value']) if row else 20
            winner_percent = 100 - owner_cut
            winners_share = round(total_pot * winner_percent / 100, 2)
            total_referral_commission = 0
            for winner in winners:
                ref_data = db.execute('SELECT referred_by FROM players WHERE user_id=?', (winner['user_id'],)).fetchone()
                if ref_data and ref_data['referred_by']:
                    comm_row = db.execute("SELECT value FROM settings WHERE key='referral_commission_percent'").fetchone()
                    comm_percent = float(comm_row['value']) if comm_row else 5.0
                    commission = round(total_pot * (comm_percent / 100), 2)
                    total_referral_commission += commission
                    db.execute('''INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at)
                                  VALUES (?, ?, ?, ?, 'pending', ?)''',
                               (ref_data['referred_by'], winner['user_id'], game_id, commission, time.time()))
            prize_per_winner = round(winners_share / len(winners), 2)
            winner_card_numbers = [w['card_number'] for w in winners]
            for winner in winners:
                db.execute('''UPDATE players SET balance=balance+?, wins=wins+1, total_won=total_won+? WHERE user_id=?''',
                           (prize_per_winner, prize_per_winner, winner['user_id']))
            db.execute('''UPDATE games SET status="finished", finished_at=?, winner_card_numbers=? WHERE id=?''',
                       (time.time(), json.dumps(winner_card_numbers), game_id))
            db.commit()
            print(f"✅ Game {game_id} FINISHED! {len(winners)} winner(s) × {prize_per_winner} ETB each (winners share {winners_share} of {total_pot})")
            db.close()
            schedule_next_game(game['stake'])
            break
        db.close()

def schedule_next_game(stake):
    time.sleep(3)
    db = get_db()
    existing = db.execute("SELECT id FROM games WHERE stake=? AND status IN ('waiting','running') LIMIT 1", (stake,)).fetchone()
    if not existing:
        db.execute("INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (?, 0, ?, 'waiting', '[]')", (stake, time.time()))
        db.commit()
        new_game = db.execute("SELECT id FROM games WHERE stake=? AND status='waiting' ORDER BY id DESC LIMIT 1", (stake,)).fetchone()
        if new_game:
            start_game_engine(new_game['id'])
            print(f"🆕 New game {new_game['id']} for stake {stake}")
    db.close()

# ---------- SMS PARSING (Simplified, keyword-based) ----------
def parse_sms_reference(sms_text, platform):
    import re
    sms_text = sms_text.strip()
    normalized = ' '.join(sms_text.split())
    amount = None
    ref = None
    
    amount_match = re.search(r'ETB\s+([\d,]+\.?\d*)', normalized, re.IGNORECASE)
    ref_match = re.search(r'transaction number is\s+([A-Z0-9]+)', normalized, re.IGNORECASE)
    
    if amount_match and ref_match:
        amount = float(amount_match.group(1).replace(',', ''))
        ref = ref_match.group(1).strip()
        return amount, ref
    
    if amount_match:
        ref_match_cbe = re.search(r'https://[^\s]+/([A-Z0-9]+)', normalized, re.IGNORECASE)
        if ref_match_cbe:
            amount = float(amount_match.group(1).replace(',', ''))
            ref = ref_match_cbe.group(1).strip()
            return amount, ref
    
    return None, sms_text

def send_telegram_message(chat_id, text):
    from config import BOT_TOKEN
    bot_token = BOT_TOKEN
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
    return "Version 2.0 - admin route fixed"

@app.route('/api/player/<int:user_id>')
def get_player(user_id):
    username  = request.args.get('username',  'user')
    full_name = request.args.get('full_name', 'User')
    db = get_db()
    p = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
    if not p:
        db.execute('INSERT INTO players(user_id,username,full_name) VALUES(?,?,?)', (user_id, username, full_name))
        db.commit()
        p = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
        create_referral_code_for_user(user_id)
    result = dict(p)
    active = db.execute('''
        SELECT g.id as game_id, g.status, g.stake
        FROM games g
        JOIN game_cards gc ON gc.game_id = g.id
        WHERE gc.user_id = ? AND g.status IN ('waiting','running')
        ORDER BY g.id DESC LIMIT 1
    ''', (user_id,)).fetchone()
    result['active_game'] = dict(active) if active else None
    db.close()
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
    db = get_db()
    if phone:
        existing = db.execute('SELECT user_id FROM players WHERE phone = ? AND user_id != ? AND phone IS NOT NULL', (phone, user_id)).fetchone()
        if existing:
            db.close()
            return jsonify({'error': 'This phone number is already registered with another account.'}), 400
        db.execute('UPDATE players SET phone = ? WHERE user_id = ?', (phone, user_id))
    if language and language in ['en','am','om','ti']:
        db.execute('UPDATE players SET language = ? WHERE user_id = ?', (language, user_id))
    if referral_code:
        existing_ref = db.execute('SELECT referred_by FROM players WHERE user_id = ?', (user_id,)).fetchone()
        if not existing_ref or not existing_ref['referred_by']:
            referrer = db.execute('SELECT user_id FROM referral_codes WHERE code = ?', (referral_code,)).fetchone()
            if referrer and referrer['user_id'] != user_id:
                db.execute('UPDATE players SET referred_by = ? WHERE user_id = ?', (referrer['user_id'], user_id))
                db.commit()
                award_referral_bonus(referrer['user_id'], user_id)
    db.commit()
    create_referral_code_for_user(user_id)
    db.close()
    return jsonify({'success': True})

@app.route('/api/reset_player', methods=['POST'])
def reset_player():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    db = get_db()
    db.execute('UPDATE players SET phone = NULL, language = "en" WHERE user_id = ?', (user_id,))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': 'Account reset. Please re‑register.'})

_join_lock = threading.Lock()

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data = request.json
    user_id = data.get('user_id')
    stake = data.get('stake')
    if not user_id or not stake:
        return jsonify({'error': 'user_id and stake are required'}), 400
    db = get_db()
    p = db.execute('SELECT is_banned FROM players WHERE user_id=?', (user_id,)).fetchone()
    if p and p['is_banned']:
        db.close()
        return jsonify({'error': 'Your account has been suspended. Contact support.'}), 403
    with _join_lock:
        game = db.execute('''
            SELECT * FROM games WHERE stake=? AND status IN ('waiting','running')
            ORDER BY id DESC LIMIT 1
        ''', (stake,)).fetchone()
        if not game:
            db.execute('''INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls)
                          VALUES (?, 0, ?, 'waiting', '[]')''', (stake, time.time()))
            db.commit()
            game = db.execute('''
                SELECT * FROM games WHERE stake=? AND status='waiting'
                ORDER BY id DESC LIMIT 1
            ''', (stake,)).fetchone()
            start_game_engine(game['id'])
    game_id = game['id']
    taken = [r['card_number'] for r in db.execute('SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)).fetchall()]
    players = len({r['user_id'] for r in db.execute('SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()})
    countdown = max(0, int(30 - (time.time() - game['created_at'])))
    db.close()
    return jsonify({
        'game_id': game_id, 'stake': stake, 'prize_pool': game['prize_pool'],
        'players': players, 'taken_cards': taken, 'countdown': countdown, 'status': game['status']
    })

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id, game_id, card_number, stake = (data['user_id'], data['game_id'], data['card_number'], data['stake'])
    db = get_db()
    game = db.execute('SELECT stake, status FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close(); return jsonify({'error': 'Game not found'}), 404
    if game['status'] != 'waiting':
        db.close(); return jsonify({'error': 'Game has already started or finished'}), 400
    if game['stake'] != stake:
        db.close(); return jsonify({'error': f'Stake mismatch. Game stake is {game["stake"]} ETB'})
    player = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
    if player['balance'] < stake:
        db.close(); return jsonify({'error': 'Insufficient balance'})
    if db.execute('SELECT id FROM game_cards WHERE game_id=? AND card_number=?', (game_id, card_number)).fetchone():
        db.close(); return jsonify({'error': 'Card already taken'})
    if db.execute('SELECT COUNT(*) as c FROM game_cards WHERE game_id=? AND user_id=?', (game_id, user_id)).fetchone()['c'] >= 4:
        db.close(); return jsonify({'error': 'Max 4 cards per game'})
    db.execute('INSERT INTO game_cards(game_id,user_id,card_number,card_data) VALUES(?,?,?,?)',
               (game_id, user_id, card_number, json.dumps(generate_card())))
    db.execute('UPDATE players SET balance=balance-?, games_played=games_played+1 WHERE user_id=?', (stake, user_id))
    db.execute('UPDATE games SET prize_pool=prize_pool+? WHERE id=?', (stake, game_id))
    db.commit()
    new_bal = db.execute('SELECT balance FROM players WHERE user_id=?', (user_id,)).fetchone()['balance']
    db.close()
    return jsonify({'success': True, 'balance': new_bal})

@app.route('/api/withdraw_from_game', methods=['POST'])
def withdraw_from_game():
    data = request.json
    user_id = data.get('user_id')
    game_id = data.get('game_id')
    if not user_id or not game_id:
        return jsonify({'error': 'user_id and game_id required'}), 400
    db = get_db()
    game = db.execute('SELECT status, stake FROM games WHERE id=?', (game_id,)).fetchone()
    if not game or game['status'] != 'waiting':
        db.close()
        return jsonify({'error': 'Game already started or not found'}), 400
    cards = db.execute('SELECT card_number FROM game_cards WHERE game_id=? AND user_id=?', (game_id, user_id)).fetchall()
    if not cards:
        db.close()
        return jsonify({'error': 'No cards found for this user in this game'}), 404
    stake = game['stake']
    refund = stake * len(cards)
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (refund, user_id))
    db.execute('DELETE FROM game_cards WHERE game_id=? AND user_id=?', (game_id, user_id))
    db.execute('UPDATE games SET prize_pool=prize_pool-? WHERE id=?', (refund, game_id))
    db.commit()
    from config import ADMIN_IDS
    remaining = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
    real_remaining = [p['user_id'] for p in remaining if p['user_id'] not in ADMIN_IDS and p['user_id'] > 0]
    if not real_remaining:
        # Remove all bots and cancel game
        remove_all_bots_from_game(game_id, stake)
        db.execute('UPDATE games SET status="finished", cancelled=1, finished_at=? WHERE id=?', (time.time(), game_id))
        db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Game cancelled because you were the last real player.'})
    else:
        # Optionally, we could re-add bots if needed, but the engine will handle it later.
        pass
    db.close()
    return jsonify({'success': True, 'message': 'Withdrawn from game.'})

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    user_id = request.args.get('user_id')
    db = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close()
        return jsonify({'error': 'Game not found'}), 404
    drawn = json.loads(game['drawn_balls'] or '[]')
    taken = [r['card_number'] for r in db.execute('SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)).fetchall()]
    players = len({r['user_id'] for r in db.execute('SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()})
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
        db.close()
        return jsonify(result)
    if game['status'] == 'finished':
        winner_card_numbers = json.loads(game['winner_card_numbers'] or '[]')
        if winner_card_numbers:
            placeholders = ','.join('?' * len(winner_card_numbers))
            winners_raw = db.execute(f'''
                SELECT gc.card_number, p.full_name, p.user_id
                FROM game_cards gc
                JOIN players p ON gc.user_id = p.user_id
                WHERE gc.game_id = ? AND gc.card_number IN ({placeholders})
            ''', [game_id] + winner_card_numbers).fetchall()
        else:
            winners_raw = []
        num_winners = len(winner_card_numbers)
        prize_each = round(winners_share / num_winners, 2) if num_winners > 0 else 0
        result['winners'] = [
            {'name': w['full_name'], 'card_number': w['card_number'], 'prize': prize_each}
            for w in winners_raw
        ]
        result['prize_each'] = prize_each
        next_game = db.execute('''
            SELECT id FROM games
            WHERE stake = ? AND status = 'waiting' AND id != ?
            ORDER BY id DESC LIMIT 1
        ''', (game['stake'], game_id)).fetchone()
        result['next_game_id'] = next_game['id'] if next_game else None
    db.close()
    return jsonify(result)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    db = get_db()
    cards = db.execute('SELECT card_number, card_data FROM game_cards WHERE game_id=? AND user_id=?', (game_id, user_id)).fetchall()
    db.close()
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
    db = get_db()
    dup = db.execute('SELECT id FROM deposits WHERE tx_ref=?', (proof,)).fetchone()
    if dup:
        db.close()
        return jsonify({'error': 'This transaction reference has already been used.'}), 400
    sms_amount, tx_ref = parse_sms_reference(proof, platform)
    if sms_amount is not None and tx_ref and abs(sms_amount - amount) <= 5:
        db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (amount, user_id))
        bonus_percent = db.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'").fetchone()
        bonus_percent = float(bonus_percent['value']) if bonus_percent else 0
        if bonus_percent > 0:
            bonus_amount = round(amount * bonus_percent / 100, 2)
            db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (bonus_amount, user_id))
            print(f"🎁 Deposit bonus: {bonus_percent}% = +{bonus_amount} ETB for user {user_id}")
        db.execute('INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at) VALUES(?,?,?,?,?,?)',
                   (user_id, amount, platform, tx_ref, 'approved', time.time()))
        db.commit()
        new_bal = db.execute('SELECT balance FROM players WHERE user_id=?', (user_id,)).fetchone()['balance']
        db.close()
        return jsonify({'success': True, 'approved': True, 'message': f'✅ {amount} ETB credited!', 'balance': new_bal})
    db.execute('INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at) VALUES(?,?,?,?,?,?)',
               (user_id, amount, platform, proof, 'pending', time.time()))
    db.commit()
    db.close()
    return jsonify({'success': True, 'approved': False, 'message': '⏳ Deposit submitted for admin review.'})

MIN_WITHDRAWAL = 50
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    amount = data.get('amount', 0)
    if amount < MIN_WITHDRAWAL:
        return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAWAL} ETB'})
    db = get_db()
    player = db.execute('SELECT balance FROM players WHERE user_id=?', (data['user_id'],)).fetchone()
    if not player or player['balance'] < amount:
        db.close(); return jsonify({'error': 'Insufficient balance'})
    db.execute('UPDATE players SET balance=balance-? WHERE user_id=?', (amount, data['user_id']))
    db.execute('INSERT INTO withdrawals(user_id,amount,platform,account_no,created_at) VALUES(?,?,?,?,?)',
               (data['user_id'], amount, data['platform'], data['account_no'], time.time()))
    db.commit(); db.close()
    return jsonify({'success': True, 'message': 'Withdrawal requested.'})

@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO inquiries(user_id,subject,message,created_at) VALUES(?,?,?,?)',
               (data['user_id'], data['subject'], data['message'], time.time()))
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/api/transactions/<int:user_id>')
def transactions(user_id):
    db = get_db()
    deps = db.execute('SELECT "deposit" as type, amount, platform as detail, status, created_at FROM deposits WHERE user_id=? ORDER BY created_at DESC LIMIT 20', (user_id,)).fetchall()
    wds = db.execute('SELECT "withdrawal" as type, amount, platform as detail, status, created_at FROM withdrawals WHERE user_id=? ORDER BY created_at DESC LIMIT 20', (user_id,)).fetchall()
    txs = sorted([dict(d) for d in deps] + [dict(w) for w in wds], key=lambda x: x['created_at'], reverse=True)
    db.close()
    return jsonify({'transactions': txs})

@app.route('/api/leaderboard')
def leaderboard():
    db = get_db()
    players = db.execute('SELECT full_name, wins, total_won, games_played FROM players WHERE is_banned=0 ORDER BY total_won DESC LIMIT 20').fetchall()
    db.close()
    return jsonify({'leaderboard': [dict(p) for p in players]})

@app.route('/api/referral_stats/<int:user_id>')
def referral_stats(user_id):
    db = get_db()
    code = db.execute('SELECT code FROM referral_codes WHERE user_id = ?', (user_id,)).fetchone()
    code_val = code['code'] if code else None
    ref_count = db.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,)).fetchone()[0]
    pending_total = db.execute('SELECT COALESCE(SUM(amount),0) FROM referral_commissions WHERE referrer_id = ? AND status = "pending"', (user_id,)).fetchone()[0]
    paid_total = db.execute('SELECT COALESCE(SUM(amount),0) FROM referral_commissions_archive WHERE referrer_id = ?', (user_id,)).fetchone()[0]
    db.close()
    return jsonify({
        'referral_code': code_val,
        'referral_count': ref_count,
        'pending_commissions': pending_total,
        'total_commissions_paid': paid_total
    })

@app.route('/api/settings/<key>')
def get_setting(key):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    db.close()
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
    db = get_db()
    db.execute('UPDATE players SET chat_id = ? WHERE user_id = ?', (chat_id, user_id))
    db.commit()
    db.close()
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
    db = get_db()
    deposit = db.execute('SELECT * FROM deposits WHERE tx_ref = ? AND status = "pending"', (ref,)).fetchone()
    if not deposit:
        db.close()
        return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
    if abs(deposit['amount'] - amount) > 5:
        db.close()
        return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {deposit["amount"]}'}), 400
    db.execute('UPDATE deposits SET status = "approved" WHERE id = ?', (deposit['id'],))
    db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (deposit['amount'], deposit['user_id']))
    bonus_percent = db.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'").fetchone()
    bonus_percent = float(bonus_percent['value']) if bonus_percent else 0
    if bonus_percent > 0:
        bonus_amount = round(deposit['amount'] * bonus_percent / 100, 2)
        db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (bonus_amount, deposit['user_id']))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': 'Deposit auto-approved'})

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "nefbingo2026")

def admin_auth(data):
    return data.get('password') == ADMIN_PASSWORD

@app.route('/admin/api/overview')
def admin_overview():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    stats = {
        'total_players': db.execute('SELECT COUNT(*) FROM players').fetchone()[0],
        'total_deposited': db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'").fetchone()[0],
        'total_withdrawn': db.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'").fetchone()[0],
        'pending_deposits': db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0],
        'pending_withdrawals': db.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
        'active_games': db.execute("SELECT COUNT(*) FROM games WHERE status IN ('waiting','running')").fetchone()[0],
    }
    db.close()
    return jsonify(stats)

@app.route('/admin/api/players')
def admin_players():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    players = db.execute('SELECT * FROM players ORDER BY balance DESC').fetchall()
    db.close()
    return jsonify({'players': [dict(p) for p in players]})

@app.route('/admin/api/deposits')
def admin_deposits():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    deps = db.execute('''SELECT d.*, p.full_name FROM deposits d
                         LEFT JOIN players p ON d.user_id=p.user_id
                         ORDER BY d.id DESC LIMIT 50''').fetchall()
    db.close()
    return jsonify({'deposits': [dict(d) for d in deps]})

@app.route('/admin/api/withdrawals')
def admin_withdrawals():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    wds = db.execute('''SELECT w.*, p.full_name FROM withdrawals w
                        LEFT JOIN players p ON w.user_id=p.user_id
                        ORDER BY w.id DESC LIMIT 50''').fetchall()
    db.close()
    return jsonify({'withdrawals': [dict(w) for w in wds]})

@app.route('/admin/api/active_games')
def admin_active_games():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    games = db.execute('''SELECT g.*, COUNT(gc.id) as card_count
                          FROM games g LEFT JOIN game_cards gc ON gc.game_id=g.id
                          WHERE g.status IN ("waiting","running")
                          GROUP BY g.id ORDER BY g.id DESC''').fetchall()
    db.close()
    return jsonify({'games': [dict(g) for g in games]})

@app.route('/admin/approve_deposit', methods=['POST'])
def approve_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    dep = db.execute('SELECT * FROM deposits WHERE id=?', (data['deposit_id'],)).fetchone()
    if not dep or dep['status'] == 'approved':
        db.close(); return jsonify({'error': 'Invalid or already approved'}), 400
    db.execute('UPDATE deposits SET status="approved" WHERE id=?', (data['deposit_id'],))
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (dep['amount'], dep['user_id']))
    bonus_percent = db.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'").fetchone()
    bonus_percent = float(bonus_percent['value']) if bonus_percent else 0
    if bonus_percent > 0:
        bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
        db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (bonus_amount, dep['user_id']))
        print(f"🎁 Manual approve bonus: {bonus_percent}% = +{bonus_amount} ETB for user {dep['user_id']}")
    db.commit(); db.close()
    return jsonify({'success': True, 'message': f'Approved +{dep["amount"]} ETB'})

@app.route('/admin/reject_deposit', methods=['POST'])
def reject_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    db.execute('UPDATE deposits SET status="rejected" WHERE id=?', (data['deposit_id'],))
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/admin/approve_withdrawal', methods=['POST'])
def approve_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    db.execute('UPDATE withdrawals SET status="approved" WHERE id=?', (data['withdrawal_id'],))
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/admin/reject_withdrawal', methods=['POST'])
def reject_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    wd = db.execute('SELECT * FROM withdrawals WHERE id=?', (data['withdrawal_id'],)).fetchone()
    if not wd:
        db.close(); return jsonify({'error': 'Not found'}), 404
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (wd['amount'], wd['user_id']))
    db.execute('UPDATE withdrawals SET status="rejected" WHERE id=?', (data['withdrawal_id'],))
    db.commit(); db.close()
    return jsonify({'success': True})

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
    db = get_db()
    db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    db.execute('INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)',
               (user_id, amount, reason, time.time()))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': f'Added {amount} ETB to user {user_id}'})

@app.route('/admin/give_bonus_all', methods=['POST'])
def give_bonus_all():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    db = get_db()
    players = db.execute('SELECT user_id FROM players WHERE is_banned = 0').fetchall()
    for p in players:
        db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (amount, p['user_id']))
        db.execute('INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)',
                   (p['user_id'], amount, reason, time.time()))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': f'Added {amount} ETB to all {len(players)} players'})

@app.route('/admin/api/get_user_by_phone', methods=['POST'])
def get_user_by_phone():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    db = get_db()
    user = db.execute('SELECT user_id, full_name FROM players WHERE phone = ?', (phone,)).fetchone()
    db.close()
    if not user:
        return jsonify({'error': 'No player found with that phone number'}), 404
    return jsonify({'user_id': user['user_id'], 'full_name': user['full_name']})

@app.route('/admin/ban_player', methods=['POST'])
def ban_player():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    db.execute('UPDATE players SET is_banned=? WHERE user_id=?', (1 if data.get('ban') else 0, data['user_id']))
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/admin/force_finish', methods=['POST'])
def force_finish():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    game_id = data['game_id']
    db = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close(); return jsonify({'error': 'Game not found'}), 404
    cards = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
    stake = game['stake']
    for c in cards:
        card_count = db.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=? AND user_id=?',
                                 (game_id, c['user_id'])).fetchone()[0]
        db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (stake * card_count, c['user_id']))
    db.execute("UPDATE games SET status='finished', finished_at=? WHERE id=?", (time.time(), game_id))
    db.commit(); db.close()
    return jsonify({'success': True})

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
    db = get_db()
    dep = db.execute('SELECT * FROM deposits WHERE tx_ref = ? AND status = "pending"', (ref,)).fetchone()
    if not dep:
        db.close()
        return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
    if abs(dep['amount'] - amount) > 5:
        db.close()
        return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {dep["amount"]}'}), 400
    db.execute('UPDATE deposits SET status = "approved" WHERE id = ?', (dep['id'],))
    db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (dep['amount'], dep['user_id']))
    bonus_percent = db.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'").fetchone()
    bonus_percent = float(bonus_percent['value']) if bonus_percent else 0
    if bonus_percent > 0:
        bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
        db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (bonus_amount, dep['user_id']))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': f'Deposit #{dep["id"]} auto-approved.'})

# ---------- Admin Settings Endpoints (Deposit Bonus, Max Balls, Bot Settings) ----------
@app.route('/admin/api/set_deposit_bonus', methods=['POST'])
def set_deposit_bonus():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    percent = data.get('percent', 0)
    try:
        percent = float(percent)
        if percent < 0 or percent > 100:
            raise ValueError
    except:
        return jsonify({'error': 'Percentage must be between 0 and 100'}), 400
    db = get_db()
    db.execute("UPDATE settings SET value = ? WHERE key = 'deposit_bonus_percent'", (str(percent),))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': f'Deposit bonus set to {percent}%'})

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
    db = get_db()
    db.execute("UPDATE settings SET value=? WHERE key='max_balls_per_game'", (str(max_balls),))
    db.commit()
    db.close()
    return jsonify({'success': True, 'max_balls': max_balls})

@app.route('/admin/api/update_bot_settings', methods=['POST'])
def update_bot_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    if 'bot_enabled' in data:
        db.execute("UPDATE settings SET value=? WHERE key='bot_enabled'", (str(data['bot_enabled']),))
    if 'bot_max_bots' in data:
        db.execute("UPDATE settings SET value=? WHERE key='bot_max_bots'", (str(data['bot_max_bots']),))
    if 'bot_target_real_players' in data:
        db.execute("UPDATE settings SET value=? WHERE key='bot_target_real_players'", (str(data['bot_target_real_players']),))
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/admin/api/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    telebirr = data.get('telebirr_number', '').strip()
    cbe = data.get('cbe_number', '').strip()
    db = get_db()
    if telebirr:
        db.execute('UPDATE settings SET value = ? WHERE key = "telebirr_number"', (telebirr,))
    if cbe:
        db.execute('UPDATE settings SET value = ? WHERE key = "cbe_number"', (cbe,))
    db.commit()
    db.close()
    return jsonify({'success': True})

# ---------- Multi-Admin ----------
@app.route('/admin/api/add_admin', methods=['POST'])
def add_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    requester = db.execute('SELECT role FROM admins WHERE user_id = ?', (data['admin_user_id'],)).fetchone()
    if not requester or requester['role'] != 'super_admin':
        db.close()
        return jsonify({'error': 'Only super admin can add admins'}), 403
    new_admin_id = data.get('new_admin_id')
    role = data.get('role', 'admin')
    if not new_admin_id:
        return jsonify({'error': 'user_id required'}), 400
    db.execute('INSERT OR IGNORE INTO admins (user_id, role, added_by, created_at) VALUES (?, ?, ?, ?)',
               (new_admin_id, role, data['admin_user_id'], time.time()))
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/admin/api/remove_admin', methods=['POST'])
def remove_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    requester = db.execute('SELECT role FROM admins WHERE user_id = ?', (data['admin_user_id'],)).fetchone()
    if not requester or requester['role'] != 'super_admin':
        db.close()
        return jsonify({'error': 'Only super admin can remove admins'}), 403
    admin_id = data.get('admin_id')
    if admin_id == data['admin_user_id']:
        return jsonify({'error': 'Cannot remove yourself'}), 400
    db.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/admin/api/admins')
def get_admins():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    admins = db.execute('SELECT * FROM admins').fetchall()
    db.close()
    return jsonify({'admins': [dict(a) for a in admins]})

# ---------- Referral Commission Admin ----------
@app.route('/admin/api/update_referral_settings', methods=['POST'])
def update_referral_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    if 'commission_percent' in data:
        db.execute("UPDATE settings SET value = ? WHERE key = 'referral_commission_percent'", (str(data['commission_percent']),))
    if 'bonus_amount' in data:
        db.execute("UPDATE settings SET value = ? WHERE key = 'referral_bonus_amount'", (str(data['bonus_amount']),))
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/admin/api/referral_settings')
def referral_settings():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    percent = db.execute("SELECT value FROM settings WHERE key = 'referral_commission_percent'").fetchone()
    bonus = db.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'").fetchone()
    db.close()
    return jsonify({
        'commission_percent': float(percent['value']) if percent else 5.0,
        'bonus_amount': float(bonus['value']) if bonus else 10.0
    })

@app.route('/admin/api/pending_commissions')
def pending_commissions():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    rows = db.execute('''SELECT c.*, p.full_name as referrer_name, p2.full_name as referred_name
                         FROM referral_commissions c
                         JOIN players p ON c.referrer_id = p.user_id
                         JOIN players p2 ON c.referred_id = p2.user_id
                         WHERE c.status = 'pending' ORDER BY c.created_at DESC''').fetchall()
    db.close()
    return jsonify({'commissions': [dict(r) for r in rows]})

@app.route('/admin/api/revoke_commission', methods=['POST'])
def revoke_commission():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    commission_id = data.get('commission_id')
    if not commission_id:
        return jsonify({'error': 'commission_id required'}), 400
    db = get_db()
    db.execute('DELETE FROM referral_commissions WHERE id = ? AND status = "pending"', (commission_id,))
    db.commit()
    db.close()
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
    db = get_db()
    db.execute('UPDATE referral_commissions SET amount = ? WHERE id = ? AND status = "pending"', (new_amount, commission_id))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': f'Commission updated to {new_amount} ETB'})

@app.route('/admin/api/process_weekly_payout', methods=['POST'])
def process_weekly_payout():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    pending = db.execute('SELECT * FROM referral_commissions WHERE status = "pending"').fetchall()
    if not pending:
        db.close()
        return jsonify({'success': True, 'message': 'No pending commissions'})
    week_start = time.time() - 7*86400
    week_end = time.time()
    total_paid = 0
    for comm in pending:
        db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?', (comm['amount'], comm['referrer_id']))
        db.execute('UPDATE referral_commissions SET status = "paid", paid_at = ? WHERE id = ?', (time.time(), comm['id']))
        db.execute('''INSERT INTO referral_commissions_archive 
                      (referrer_id, referred_id, game_id, amount, paid_at, payment_week_start, payment_week_end)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                   (comm['referrer_id'], comm['referred_id'], comm['game_id'], comm['amount'], time.time(), week_start, week_end))
        total_paid += comm['amount']
    db.commit()
    db.close()
    return jsonify({'success': True, 'total_paid': total_paid, 'count': len(pending)})

if __name__ == '__main__':
    init_db()
    create_bot_players()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
