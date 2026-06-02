from flask import Flask, request, jsonify, send_from_directory
import sqlite3, json, time, os, threading, re
from game.bingo_logic import generate_card, draw_ball, check_bingo

app = Flask(__name__, static_folder='static', template_folder='templates')

# ── Persistent database path ─────────────────────────────
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
            is_banned INTEGER DEFAULT 0
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
    ''')
    # Add missing columns safely
    try:
        db.execute('ALTER TABLE players ADD COLUMN is_banned INTEGER DEFAULT 0')
        db.commit()
    except: pass
    try:
        db.execute('ALTER TABLE games ADD COLUMN winner_card_numbers TEXT DEFAULT "[]"')
        db.commit()
    except: pass
    try:
        db.execute('ALTER TABLE games ADD COLUMN cancelled INTEGER DEFAULT 0')
        db.commit()
    except: pass
    db.commit()
    db.close()

init_db()

# ── Game engine ──────────────────────────────────────────
_engine_lock = threading.Lock()
_running_engines = set()

def start_game_engine(game_id):
    with _engine_lock:
        if game_id in _running_engines:
            return
        _running_engines.add(game_id)

    def engine():
        try:
            time.sleep(30)  # initial waiting for players
            db = get_db()
            game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
            if not game or game['status'] != 'waiting':
                db.close()
                return
            db.close()

            players = count_players_in_game(game_id)
            start_time = time.time()
            max_wait = 300  # 5 minutes total waiting time (including initial 30s)

            while players < 2 and (time.time() - start_time) < max_wait:
                time.sleep(30)
                players = count_players_in_game(game_id)

            if players < 2:
                # Cancel game: refund all players
                db = get_db()
                db.execute('UPDATE games SET status="finished", finished_at=?, cancelled=1, winner_card_numbers="[]" WHERE id=?',
                           (time.time(), game_id))
                card_holders = db.execute('SELECT DISTINCT user_id FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
                stake = game['stake']
                for player in card_holders:
                    card_count = db.execute('SELECT COUNT(*) FROM game_cards WHERE game_id=? AND user_id=?',
                                            (game_id, player['user_id'])).fetchone()[0]
                    refund = stake * card_count
                    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (refund, player['user_id']))
                db.commit()
                db.close()
                print(f"🚫 Game {game_id} cancelled: only {players} player(s). Refunded all.")
                return

            # Enough players – start game
            db = get_db()
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

        if drawn and len(drawn) % 10 == 0:
            print(f"🎲 Game {game_id}: {len(drawn)}/75 balls, {len(cards)} cards, {len(winners)} winners")

        if winners:
            total_pot = game['prize_pool']
            winners_share = round(total_pot * 0.80, 2)
            prize_per_winner = round(winners_share / len(winners), 2)
            winner_card_numbers = [w['card_number'] for w in winners]

            for winner in winners:
                db.execute('''UPDATE players SET balance=balance+?, wins=wins+1,
                              total_won=total_won+? WHERE user_id=?''',
                           (prize_per_winner, prize_per_winner, winner['user_id']))

            db.execute('''UPDATE games SET status="finished", finished_at=?,
                          winner_card_numbers=? WHERE id=?''',
                       (time.time(), json.dumps(winner_card_numbers), game_id))
            db.commit()
            print(f"✅ Game {game_id} FINISHED! {len(winners)} winner(s) × {prize_per_winner} ETB each (80% of {total_pot})")
            print(f"   Winner cards: {winner_card_numbers}")
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

# ── SMS parsing (Telebirr / CBE) ──────────────────────────
TELEBIRR_PATTERN = re.compile(
    r'transferred ETB\s+([\d,]+\.?\d*)\s+to.*?transaction number is\s+([A-Z0-9]+)',
    re.IGNORECASE | re.DOTALL
)
CBE_PATTERN = re.compile(
    r'transfered ETB\s+([\d,]+\.?\d*)\s+to.*?https://apps\.cbe\.com\.et[^\s]*\?id=([A-Z0-9]+)',
    re.IGNORECASE | re.DOTALL
)

def parse_sms_reference(sms_text, platform):
    sms_text = sms_text.strip()
    if platform == 'telebirr':
        m = TELEBIRR_PATTERN.search(sms_text)
        if m:
            amount = float(m.group(1).replace(',', ''))
            ref = m.group(2).strip()
            return amount, ref
    elif platform == 'cbe':
        m = CBE_PATTERN.search(sms_text)
        if m:
            amount = float(m.group(1).replace(',', ''))
            ref = m.group(2).strip()
            return amount, ref
    return None, sms_text

# ──────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/api/player/<int:user_id>')
def get_player(user_id):
    username  = request.args.get('username',  'user')
    full_name = request.args.get('full_name', 'User')
    db = get_db()
    p = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
    if not p:
        db.execute('INSERT INTO players(user_id,username,full_name) VALUES(?,?,?)',
                   (user_id, username, full_name))
        db.commit()
        p = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
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

_join_lock = threading.Lock()

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data    = request.json
    user_id = data.get('user_id')
    stake   = data.get('stake')
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
    taken = [r['card_number'] for r in db.execute(
        'SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()]
    players = len({r['user_id'] for r in db.execute(
        'SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()})
    countdown = max(0, int(30 - (time.time() - game['created_at'])))
    db.close()
    return jsonify({
        'game_id':     game_id,
        'stake':       stake,
        'prize_pool':  game['prize_pool'],
        'players':     players,
        'taken_cards': taken,
        'countdown':   countdown,
        'status':      game['status']
    })

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id, game_id, card_number, stake = (
        data['user_id'], data['game_id'], data['card_number'], data['stake']
    )
    db = get_db()

    # Verify game exists, is waiting, and stake matches
    game = db.execute('SELECT stake, status FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close()
        return jsonify({'error': 'Game not found'}), 404
    if game['status'] != 'waiting':
        db.close()
        return jsonify({'error': 'Game has already started or finished'}), 400
    if game['stake'] != stake:
        db.close()
        return jsonify({'error': f'Stake mismatch. Game stake is {game["stake"]} ETB'})

    player = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
    if player['balance'] < stake:
        db.close()
        return jsonify({'error': 'Insufficient balance'})
    if db.execute('SELECT id FROM game_cards WHERE game_id=? AND card_number=?',
                  (game_id, card_number)).fetchone():
        db.close()
        return jsonify({'error': 'Card already taken'})
    if db.execute('SELECT COUNT(*) as c FROM game_cards WHERE game_id=? AND user_id=?',
                  (game_id, user_id)).fetchone()['c'] >= 4:
        db.close()
        return jsonify({'error': 'Max 4 cards per game'})

    db.execute('INSERT INTO game_cards(game_id,user_id,card_number,card_data) VALUES(?,?,?,?)',
               (game_id, user_id, card_number, json.dumps(generate_card())))
    db.execute('UPDATE players SET balance=balance-?, games_played=games_played+1 WHERE user_id=?',
               (stake, user_id))
    db.execute('UPDATE games SET prize_pool=prize_pool+? WHERE id=?', (stake, game_id))
    db.commit()
    new_bal = db.execute('SELECT balance FROM players WHERE user_id=?',
                         (user_id,)).fetchone()['balance']
    db.close()
    return jsonify({'success': True, 'balance': new_bal})

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    user_id = request.args.get('user_id')
    db = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close()
        return jsonify({'error': 'Game not found'}), 404

    drawn = json.loads(game['drawn_balls'] or '[]')
    taken = [r['card_number'] for r in db.execute(
        'SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()]
    players = len({r['user_id'] for r in db.execute(
        'SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()})

    total_pool = game['prize_pool']
    winners_share = round(total_pool * 0.80, 2)

    result = {
        'status':        game['status'],
        'drawn_balls':   drawn,
        'prize_pool':    total_pool,
        'winners_share': winners_share,
        'stake':         game['stake'],
        'players':       players,
        'taken_cards':   taken,
    }

    # Cancelled game handling
    if game['status'] == 'finished' and game.get('cancelled', 0) == 1:
        result['status'] = 'cancelled'
        result['cancelled_message'] = 'በቂ ተጫዋቾች የሉም። ጨዋታው ተሰርዟል። ገንዘብዎ ተመልሷል።'  # Amharic
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

        # Next waiting game for same stake
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
    cards = db.execute(
        'SELECT card_number, card_data FROM game_cards WHERE game_id=? AND user_id=?',
        (game_id, user_id)
    ).fetchall()
    db.close()
    return jsonify({'cards': [
        {'card_index': c['card_number'], 'card_data': json.loads(c['card_data'])}
        for c in cards
    ]})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    data     = request.json
    user_id  = data.get('user_id')
    amount   = data.get('amount')
    platform = data.get('platform', 'telebirr')
    proof    = data.get('tx_ref', '').strip()

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
        db.execute('''INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at)
                      VALUES(?,?,?,?,?,?)''',
                   (user_id, amount, platform, tx_ref, 'approved', time.time()))
        db.commit()
        new_bal = db.execute('SELECT balance FROM players WHERE user_id=?', (user_id,)).fetchone()['balance']
        db.close()
        return jsonify({'success': True, 'approved': True, 'message': f'✅ {amount} ETB credited!', 'balance': new_bal})

    db.execute('''INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at)
                  VALUES(?,?,?,?,?,?)''',
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
    db.execute('''INSERT INTO withdrawals(user_id,amount,platform,account_no,created_at)
                  VALUES(?,?,?,?,?)''',
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
    deps = db.execute('''SELECT "deposit" as type, amount, platform as detail,
                          status, created_at FROM deposits WHERE user_id=?
                          ORDER BY created_at DESC LIMIT 20''', (user_id,)).fetchall()
    wds  = db.execute('''SELECT "withdrawal" as type, amount, platform as detail,
                          status, created_at FROM withdrawals WHERE user_id=?
                          ORDER BY created_at DESC LIMIT 20''', (user_id,)).fetchall()
    txs  = sorted([dict(d) for d in deps] + [dict(w) for w in wds],
                  key=lambda x: x['created_at'], reverse=True)
    db.close()
    return jsonify({'transactions': txs})

@app.route('/api/leaderboard')
def leaderboard():
    db = get_db()
    players = db.execute('''SELECT full_name, wins, total_won, games_played
                             FROM players WHERE is_banned=0
                             ORDER BY total_won DESC LIMIT 20''').fetchall()
    db.close()
    return jsonify({'leaderboard': [dict(p) for p in players]})

# ── Notifications (Admin broadcast) ─────────────────────
@app.route('/admin/api/send_notification', methods=['POST'])
def send_notification():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    db = get_db()
    db.execute('INSERT INTO notifications (message, created_at) VALUES (?, ?)', (message, time.time()))
    db.commit()
    db.close()
    return jsonify({'success': True, 'message': 'Notification sent to all players'})

@app.route('/admin/api/notifications')
def admin_notifications():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    notes = db.execute('SELECT id, message, created_at FROM notifications ORDER BY created_at DESC LIMIT 50').fetchall()
    db.close()
    return jsonify({'notifications': [dict(n) for n in notes]})

@app.route('/api/notifications/latest')
def latest_notification():
    db = get_db()
    note = db.execute('SELECT message, created_at FROM notifications ORDER BY created_at DESC LIMIT 1').fetchone()
    db.close()
    if note:
        return jsonify({'message': note['message'], 'timestamp': note['created_at']})
    return jsonify({'message': None})

# ═════════════════════════════════════════════════════════
# ADMIN PANEL (unchanged, plus new notification endpoints)
# ═════════════════════════════════════════════════════════
ADMIN_PASSWORD = 'nefbingo2026'

def admin_auth(data):
    return data.get('password') == ADMIN_PASSWORD

@app.route('/admin')
def admin():
    return send_from_directory('templates', 'admin.html')

@app.route('/admin/api/overview')
def admin_overview():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    db = get_db()
    stats = {
        'total_players':    db.execute('SELECT COUNT(*) FROM players').fetchone()[0],
        'total_deposited':  db.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'").fetchone()[0],
        'total_withdrawn':  db.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'").fetchone()[0],
        'pending_deposits': db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0],
        'pending_withdrawals': db.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
        'active_games':     db.execute("SELECT COUNT(*) FROM games WHERE status IN ('waiting','running')").fetchone()[0],
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
    user_id, amount, reason = data['user_id'], data['amount'], data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    db = get_db()
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (amount, user_id))
    db.execute('INSERT INTO bonuses(user_id,amount,reason,created_at) VALUES(?,?,?,?)',
               (user_id, amount, reason, time.time()))
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/admin/give_bonus_all', methods=['POST'])
def give_bonus_all():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    amount, reason = data['amount'], data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    db = get_db()
    players = db.execute('SELECT user_id FROM players WHERE is_banned=0').fetchall()
    for p in players:
        db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (amount, p['user_id']))
        db.execute('INSERT INTO bonuses(user_id,amount,reason,created_at) VALUES(?,?,?,?)',
                   (p['user_id'], amount, reason, time.time()))
    db.commit(); db.close()
    return jsonify({'success': True})

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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
