nano static/app.js # paste new app.js → Ctrl+X → Y → Enter
git add app.py static/app.js
git commit -m "Smart deposit: auto-approve, duplicate block, manual fallback"
git push origin mainnano static/app.js # paste new app.js → Ctrl+X → Y → Enter
git add app.py static/app.js
git commit -m "Smart deposit: auto-approve, duplicate block, manual fallback"
git push origin mainfrom flask import Flask, request, jsonify, send_from_directory
import sqlite3, json, time, os, threading, random, re, requests
from game.bingo_logic import generate_card, draw_ball, check_bingo

app = Flask(__name__, static_folder='static', template_folder='templates')
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bingo.db')

# ── CONFIG ────────────────────────────────────────────────────────────────────
ADMIN_BOT_TOKEN = os.environ.get('ADMIN_BOT_TOKEN', '')
ADMIN_CHAT_ID   = os.environ.get('ADMIN_CHAT_ID',   '')
ADMIN_PASSWORD  = os.environ.get('ADMIN_PASSWORD',  'nefbingo2026')

# ── Telegram helpers ──────────────────────────────────────────────────────────
def send_admin_telegram(message):
    if not ADMIN_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage',
            json={'chat_id': ADMIN_CHAT_ID, 'text': message, 'parse_mode': 'HTML'},
            timeout=5
        )
    except Exception as e:
        print(f'Admin Telegram error: {e}')

def send_player_telegram(user_id, message):
    """Send a Telegram message directly to a player."""
    if not ADMIN_BOT_TOKEN:
        return False
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage',
            json={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'},
            timeout=5
        )
        return r.json().get('ok', False)
    except Exception as e:
        print(f'Player Telegram error: {e}')
        return False

# ── Reference validators ──────────────────────────────────────────────────────
def validate_telebirr_ref(ref):
    ref = ref.strip().upper()
    return bool(re.match(r'^[A-Z]{0,3}\d{8,20}$', ref))

def validate_cbe_ref(ref):
    ref = ref.strip()
    return bool(re.match(r'^\d{10,20}$', ref))

def validate_ref(platform, ref):
    ref = ref.strip()
    if len(ref) < 6:
        return False, 'Reference number too short'
    if platform == 'telebirr':
        return (True, 'valid') if validate_telebirr_ref(ref) else (False, 'Invalid Telebirr reference format')
    elif platform == 'cbe':
        return (True, 'valid') if validate_cbe_ref(ref) else (False, 'Invalid CBE reference format')
    return False, 'Unknown platform — needs manual review'

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

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
            is_blocked INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stake INTEGER, status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            created_at REAL, started_at REAL, finished_at REAL
        );
        CREATE TABLE IF NOT EXISTS game_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER, user_id INTEGER,
            card_number INTEGER, card_data TEXT
        );
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL,
            platform TEXT, tx_ref TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_at REAL
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
            message TEXT, created_at REAL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            sent_ok INTEGER DEFAULT 0,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            reason TEXT,
            created_at REAL
        );
    ''')
    # Add is_blocked column if upgrading from old DB
    try:
        db.execute('ALTER TABLE players ADD COLUMN is_blocked INTEGER DEFAULT 0')
        db.commit()
    except:
        pass
    db.commit()
    db.close()
init_db()

# ── GAME ENGINE ───────────────────────────────────────────────────────────────
def start_game_engine(game_id):
    def engine():
        time.sleep(30)
        db = get_db()
        game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
        if not game or game['status'] != 'waiting':
            db.close(); return
        db.execute('UPDATE games SET status="running", started_at=? WHERE id=?',
                   (time.time(), game_id))
        db.commit(); db.close()
        draw_loop(game_id)
    threading.Thread(target=engine, daemon=True).start()

def draw_loop(game_id):
    while True:
        time.sleep(4)
        db = get_db()
        game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
        if not game or game['status'] != 'running':
            db.close(); break

        drawn = json.loads(game['drawn_balls'])
        ball  = draw_ball(drawn)
        if ball is None:
            db.execute('UPDATE games SET status="finished" WHERE id=?', (game_id,))
            db.commit(); db.close(); break

        drawn.append(ball)
        db.execute('UPDATE games SET drawn_balls=? WHERE id=?', (json.dumps(drawn), game_id))
        db.commit()

        cards   = db.execute('SELECT * FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
        winners = [c for c in cards if check_bingo(json.loads(c['card_data']), drawn)]

        if winners:
            total_pot        = game['prize_pool']
            winners_share    = round(total_pot * 0.80, 2)
            prize_per_winner = round(winners_share / len(winners), 2)

            for winner in winners:
                db.execute(
                    'UPDATE players SET balance=balance+?, wins=wins+1, total_won=total_won+? WHERE user_id=?',
                    (prize_per_winner, prize_per_winner, winner['user_id'])
                )

            db.execute('UPDATE games SET status="finished", finished_at=? WHERE id=?',
                       (time.time(), game_id))
            db.commit()
            db.close()

            time.sleep(10)
            db = get_db()
            existing = db.execute(
                'SELECT id FROM games WHERE stake=? AND status IN ("waiting","running") LIMIT 1',
                (game['stake'],)
            ).fetchone()
            if not existing:
                db.execute(
                    'INSERT INTO games (stake,prize_pool,created_at,status,drawn_balls) VALUES (?,0,?,"waiting","[]")',
                    (game['stake'], time.time())
                )
                db.commit()
                new_game = db.execute(
                    'SELECT id FROM games WHERE stake=? AND status="waiting" ORDER BY id DESC LIMIT 1',
                    (game['stake'],)
                ).fetchone()
                if new_game:
                    start_game_engine(new_game['id'])
            db.close()
            break

        db.close()

# ── ROUTES ────────────────────────────────────────────────────────────────────
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
    db.close()
    # Block check
    if result.get('is_blocked'):
        return jsonify({'error': 'blocked', 'message': '🚫 Your account has been blocked. Contact support.'}), 403
    return jsonify(result)

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data    = request.json
    user_id = data.get('user_id')
    stake   = data.get('stake')
    if not user_id or not stake:
        return jsonify({'error': 'user_id and stake are required'}), 400

    db = get_db()
    # Block check
    p = db.execute('SELECT is_blocked FROM players WHERE user_id=?', (user_id,)).fetchone()
    if p and p['is_blocked']:
        db.close()
        return jsonify({'error': '🚫 Your account is blocked.'}), 403

    existing_game = db.execute(
        'SELECT * FROM games WHERE stake=? AND status IN ("waiting","running") ORDER BY id DESC LIMIT 1',
        (stake,)
    ).fetchone()

    if existing_game:
        game_id = existing_game['id']
        game    = existing_game
    else:
        db.execute(
            'INSERT INTO games (stake,prize_pool,created_at,status,drawn_balls) VALUES (?,0,?,"waiting","[]")',
            (stake, time.time())
        )
        db.commit()
        game = db.execute(
            'SELECT * FROM games WHERE stake=? AND status="waiting" ORDER BY id DESC LIMIT 1',
            (stake,)
        ).fetchone()
        game_id = game['id']
        start_game_engine(game_id)

    taken   = [r['card_number'] for r in db.execute(
        'SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()]
    players = len({r['user_id'] for r in db.execute(
        'SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()})
    countdown = max(0, int(30 - (time.time() - game['created_at'])))
    db.close()

    return jsonify({
        'game_id': game_id, 'stake': stake,
        'prize_pool': game['prize_pool'], 'players': players,
        'taken_cards': taken, 'countdown': countdown, 'status': game['status']
    })

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id, game_id, card_number, stake = (
        data['user_id'], data['game_id'], data['card_number'], data['stake']
    )
    db = get_db()
    player = db.execute('SELECT * FROM players WHERE user_id=?', (user_id,)).fetchone()
    if player['is_blocked']:
        db.close(); return jsonify({'error': '🚫 Your account is blocked.'})
    if player['balance'] < stake:
        db.close(); return jsonify({'error': 'Insufficient balance'})
    if db.execute('SELECT id FROM game_cards WHERE game_id=? AND card_number=?',
                  (game_id, card_number)).fetchone():
        db.close(); return jsonify({'error': 'Card taken'})
    if db.execute('SELECT COUNT(*) as c FROM game_cards WHERE game_id=? AND user_id=?',
                  (game_id, user_id)).fetchone()['c'] >= 4:
        db.close(); return jsonify({'error': 'Max 4 cards'})
    db.execute('INSERT INTO game_cards(game_id,user_id,card_number,card_data) VALUES(?,?,?,?)',
               (game_id, user_id, card_number, json.dumps(generate_card())))
    db.execute('UPDATE players SET balance=balance-?, games_played=games_played+1 WHERE user_id=?',
               (stake, user_id))
    db.execute('UPDATE games SET prize_pool=prize_pool+? WHERE id=?', (stake, game_id))
    db.commit()
    new_bal = db.execute('SELECT balance FROM players WHERE user_id=?', (user_id,)).fetchone()['balance']
    db.close()
    return jsonify({'success': True, 'balance': new_bal})

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    db   = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close(); return jsonify({'error': 'Game not found'}), 404

    drawn   = json.loads(game.get('drawn_balls', '[]'))
    taken   = [r['card_number'] for r in db.execute(
        'SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()]
    players = len({r['user_id'] for r in db.execute(
        'SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()})

    result = {
        'status': game['status'], 'drawn_balls': drawn,
        'prize_pool': game['prize_pool'], 'stake': game['stake'],
        'taken_cards': taken, 'players': players
    }

    if game['status'] == 'finished':
        winners_raw = db.execute('''
            SELECT gc.*, p.full_name FROM game_cards gc
            JOIN players p ON gc.user_id=p.user_id WHERE gc.game_id=?
        ''', (game_id,)).fetchall()
        result['winners'] = [
            {'name': w['full_name'], 'card_number': w['card_number']}
            for w in winners_raw
            if check_bingo(json.loads(w['card_data']), drawn)
        ]

    db.close()
    return jsonify(result)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    db      = get_db()
    cards   = db.execute(
        'SELECT card_number, card_data FROM game_cards WHERE game_id=? AND user_id=?',
        (game_id, user_id)
    ).fetchall()
    db.close()
    return jsonify({'cards': [
        {'card_index': c['card_number'], 'card_data': json.loads(c['card_data'])}
        for c in cards
    ]})

# ── DEPOSIT ───────────────────────────────────────────────────────────────────
@app.route('/api/deposit', methods=['POST'])
def deposit():
    data     = request.json
    user_id  = data.get('user_id')
    amount   = data.get('amount')
    platform = data.get('platform', '').lower()
    tx_ref   = (data.get('tx_ref') or '').strip()

    if not tx_ref:
        return jsonify({'error': 'Please enter your transaction reference number'}), 400

    db = get_db()

    # Block check
    p = db.execute('SELECT is_blocked FROM players WHERE user_id=?', (user_id,)).fetchone()
    if p and p['is_blocked']:
        db.close()
        return jsonify({'error': '🚫 Your account is blocked.'}), 403

    # Duplicate check
    existing = db.execute('SELECT id, status FROM deposits WHERE tx_ref=?', (tx_ref,)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': '❌ This reference number has already been used. Please check and try again.'}), 400

    is_valid, reason = validate_ref(platform, tx_ref)

    if is_valid:
        db.execute(
            'INSERT INTO deposits(user_id,amount,platform,tx_ref,status,note,created_at) VALUES(?,?,?,?,?,?,?)',
            (user_id, amount, platform, tx_ref, 'approved', 'Auto-approved', time.time())
        )
        db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (amount, user_id))
        db.commit()
        player = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
        name   = player['full_name'] if player else str(user_id)
        db.close()
        send_admin_telegram(
            f"✅ <b>AUTO-APPROVED DEPOSIT</b>\n👤 {name}\n💰 {amount} ETB\n📱 {platform.upper()}\n🔑 <code>{tx_ref}</code>"
        )
        return jsonify({'success': True, 'approved': True,
                        'message': f'✅ Deposit of {amount} ETB confirmed! Balance updated.'})
    else:
        db.execute(
            'INSERT INTO deposits(user_id,amount,platform,tx_ref,status,note,created_at) VALUES(?,?,?,?,?,?,?)',
            (user_id, amount, platform, tx_ref, 'pending', reason, time.time())
        )
        db.commit()
        player = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
        name   = player['full_name'] if player else str(user_id)
        db.close()
        send_admin_telegram(
            f"⚠️ <b>MANUAL REVIEW NEEDED</b>\n👤 {name}\n💰 {amount} ETB\n📱 {platform.upper()}\n🔑 <code>{tx_ref}</code>\n❓ {reason}"
        )
        return jsonify({'success': True, 'approved': False,
                        'message': '⏳ Deposit under review. Admin will confirm shortly.'})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    db   = get_db()
    player = db.execute('SELECT balance, is_blocked FROM players WHERE user_id=?', (data['user_id'],)).fetchone()
    if not player or player['is_blocked']:
        db.close(); return jsonify({'error': '🚫 Account blocked or not found'})
    if player['balance'] < data['amount']:
        db.close(); return jsonify({'error': 'Insufficient balance'})
    db.execute('UPDATE players SET balance=balance-? WHERE user_id=?', (data['amount'], data['user_id']))
    db.execute(
        'INSERT INTO withdrawals(user_id,amount,platform,account_no,created_at) VALUES(?,?,?,?,?)',
        (data['user_id'], data['amount'], data['platform'], data['account_no'], time.time())
    )
    db.commit(); db.close()
    return jsonify({'success': True})

@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    db   = get_db()
    db.execute('INSERT INTO inquiries(user_id,subject,message,created_at) VALUES(?,?,?,?)',
               (data['user_id'], data['subject'], data['message'], time.time()))
    db.commit(); db.close()
    return jsonify({'success': True})

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/admin')
def admin():
    db   = get_db()
    deps = db.execute('''
        SELECT d.*, p.full_name FROM deposits d
        LEFT JOIN players p ON d.user_id=p.user_id
        ORDER BY d.id DESC LIMIT 50
    ''').fetchall()
    plrs = db.execute('SELECT * FROM players ORDER BY balance DESC').fetchall()
    notifs = db.execute('''
        SELECT n.*, p.full_name FROM notifications n
        LEFT JOIN players p ON n.user_id=p.user_id
        ORDER BY n.id DESC LIMIT 30
    ''').fetchall()
    bonuses = db.execute('''
        SELECT b.*, p.full_name FROM bonuses b
        LEFT JOIN players p ON b.user_id=p.user_id
        ORDER BY b.id DESC LIMIT 30
    ''').fetchall()
    db.close()

    def badge(s):
        c = {'approved':'#1a7a1a','pending':'#7a5500','rejected':'#7a0000','blocked':'#7a0000'}
        return f'<span style="background:{c.get(s,"#444")};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{s}</span>'

    def ts(t):
        try: return time.strftime('%m/%d %H:%M', time.localtime(float(t)))
        except: return '—'

    # ── Deposits table ────────────────────────────────────────────────────────
    dep_rows = ''
    for d in deps:
        actions = ''
        if d['status'] == 'pending':
            actions = (
                f'<button class="btn-g" onclick="approveDeposit({d["id"]},{d["user_id"]},{d["amount"]})">✅ Approve</button> '
                f'<button class="btn-r" onclick="rejectDeposit({d["id"]})">❌ Reject</button>'
            )
        dep_rows += (
            f'<tr><td>{d["id"]}</td><td>{d["user_id"]}</td><td>{d["full_name"] or "?"}</td>'
            f'<td><b>{d["amount"]} ETB</b></td><td>{d["platform"]}</td>'
            f'<td style="font-size:11px;font-family:monospace">{d["tx_ref"]}</td>'
            f'<td>{badge(d["status"])}</td><td style="font-size:11px;color:#aaa">{d["note"] or ""}</td>'
            f'<td>{ts(d["created_at"])}</td><td>{actions}</td></tr>'
        )

    # ── Players table ─────────────────────────────────────────────────────────
    plr_rows = ''
    for p in plrs:
        blocked = p['is_blocked']
        block_btn = (
            f'<button class="btn-g" onclick="unblockPlayer({p["user_id"]})">🔓 Unblock</button>'
            if blocked else
            f'<button class="btn-r" onclick="blockPlayer({p["user_id"]})">🚫 Block</button>'
        )
        plr_rows += (
            f'<tr style="{"opacity:0.5" if blocked else ""}">'
            f'<td>{p["user_id"]}</td>'
            f'<td>{p["username"] or "—"}</td>'
            f'<td>{p["full_name"] or "—"}</td>'
            f'<td><b>{round(p["balance"],2)} ETB</b></td>'
            f'<td>{p["games_played"]}</td><td>{p["wins"]}</td>'
            f'<td>{badge("blocked" if blocked else "active")}</td>'
            f'<td>'
            f'<button class="btn-gold" onclick="giveBonus({p["user_id"]},\'{p["full_name"] or p["username"]}\')">🎁 Bonus</button> '
            f'<button class="btn-blue" onclick="notifyPlayer({p["user_id"]},\'{p["full_name"] or p["username"]}\')">📨 Notify</button> '
            f'{block_btn} '
            f'<button class="btn-r" onclick="deletePlayer({p["user_id"]},\'{p["full_name"] or p["username"]}\')">🗑 Delete</button>'
            f'</td></tr>'
        )

    # ── Notifications log ─────────────────────────────────────────────────────
    notif_rows = ''.join(
        f'<tr><td>{n["id"]}</td><td>{n["user_id"]}</td><td>{n["full_name"] or "?"}</td>'
        f'<td>{n["message"][:60]}...</td>'
        f'<td>{"✅ Sent" if n["sent_ok"] else "❌ Failed"}</td>'
        f'<td>{ts(n["created_at"])}</td></tr>'
        for n in notifs
    )

    # ── Bonus log ─────────────────────────────────────────────────────────────
    bonus_rows = ''.join(
        f'<tr><td>{b["id"]}</td><td>{b["user_id"]}</td><td>{b["full_name"] or "?"}</td>'
        f'<td><b>+{b["amount"]} ETB</b></td><td>{b["reason"] or "—"}</td>'
        f'<td>{ts(b["created_at"])}</td></tr>'
        for b in bonuses
    )

    return f'''<!DOCTYPE html><html><head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>NEF BINGO ADMIN</title>
    <style>
      *{{box-sizing:border-box;margin:0;padding:0}}
      body{{font-family:monospace;background:#0a0a1a;color:#eee;padding:0}}
      .topbar{{background:linear-gradient(135deg,#1a0a3e,#0a0a2e);padding:16px 24px;
               border-bottom:2px solid gold;display:flex;align-items:center;gap:12px}}
      .topbar h1{{color:gold;font-size:20px;letter-spacing:2px}}
      .tabs{{display:flex;background:#0f0f2a;border-bottom:1px solid #333;overflow-x:auto}}
      .tab{{padding:12px 20px;cursor:pointer;font-size:13px;color:#aaa;white-space:nowrap;
            border-bottom:3px solid transparent}}
      .tab.active{{color:gold;border-bottom-color:gold}}
      .tab:hover{{color:#fff}}
      .section{{display:none;padding:20px}}
      .section.active{{display:block}}
      table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:10px}}
      th,td{{border:1px solid #222;padding:7px 9px;text-align:left;vertical-align:middle}}
      th{{background:#111;color:gold;font-size:11px;text-transform:uppercase}}
      tr:hover td{{background:#111}}
      h2{{color:gold;margin:0 0 14px;font-size:15px}}
      .btn-g{{background:#1a6a1a;color:#fff;border:none;padding:4px 9px;border-radius:5px;cursor:pointer;font-size:11px;margin:1px}}
      .btn-r{{background:#6a1a1a;color:#fff;border:none;padding:4px 9px;border-radius:5px;cursor:pointer;font-size:11px;margin:1px}}
      .btn-gold{{background:#6a5000;color:#ffd700;border:none;padding:4px 9px;border-radius:5px;cursor:pointer;font-size:11px;margin:1px}}
      .btn-blue{{background:#0a3a6a;color:#88ccff;border:none;padding:4px 9px;border-radius:5px;cursor:pointer;font-size:11px;margin:1px}}
      .btn-g:hover{{background:#2a9a2a}} .btn-r:hover{{background:#9a2a2a}}
      .btn-gold:hover{{background:#9a7500}} .btn-blue:hover{{background:#1a5a9a}}
      .broadcast-box{{background:#111;border:1px solid #333;border-radius:10px;padding:16px;margin-bottom:20px}}
      .broadcast-box textarea{{width:100%;background:#0a0a1a;border:1px solid #444;
        color:#fff;border-radius:6px;padding:10px;font-size:13px;resize:vertical;min-height:80px}}
      .broadcast-box input{{width:100%;background:#0a0a1a;border:1px solid #444;
        color:#fff;border-radius:6px;padding:8px 10px;font-size:13px;margin-bottom:8px}}
      .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
      .scard{{background:#111;border:1px solid #333;border-radius:8px;padding:12px;text-align:center}}
      .scard-val{{font-size:22px;font-weight:900;color:gold}}
      .scard-lbl{{font-size:10px;color:#888;text-transform:uppercase;margin-top:4px}}
      ::-webkit-scrollbar{{height:4px;width:4px}}
      ::-webkit-scrollbar-thumb{{background:#333;border-radius:2px}}
    </style></head>
    <body>

    <div class="topbar">
      <div style="font-size:28px">🎯</div>
      <h1>NEF BINGO ADMIN</h1>
    </div>

    <div class="tabs">
      <div class="tab active" onclick="showTab('deposits')">💰 Deposits</div>
      <div class="tab" onclick="showTab('players')">👥 Players</div>
      <div class="tab" onclick="showTab('broadcast')">📢 Broadcast</div>
      <div class="tab" onclick="showTab('bonuses')">🎁 Bonus Log</div>
      <div class="tab" onclick="showTab('notifs')">📨 Notify Log</div>
    </div>

    <!-- DEPOSITS -->
    <div class="section active" id="tab-deposits">
      <h2>💰 Deposits (latest 50)</h2>
      <div style="overflow-x:auto">
      <table>
        <tr><th>ID</th><th>UserID</th><th>Name</th><th>Amount</th><th>Platform</th>
            <th>TxRef</th><th>Status</th><th>Note</th><th>Time</th><th>Action</th></tr>
        {dep_rows}
      </table></div>
    </div>

    <!-- PLAYERS -->
    <div class="section" id="tab-players">
      <h2>👥 Players</h2>
      <div style="overflow-x:auto">
      <table>
        <tr><th>UserID</th><th>Username</th><th>Name</th><th>Balance</th>
            <th>Games</th><th>Wins</th><th>Status</th><th>Actions</th></tr>
        {plr_rows}
      </table></div>
    </div>

    <!-- BROADCAST -->
    <div class="section" id="tab-broadcast">
      <h2>📢 Send Notification to All Players</h2>
      <div class="broadcast-box">
        <div style="font-size:12px;color:#aaa;margin-bottom:8px">Message will be sent to ALL players via Telegram</div>
        <textarea id="broadcastMsg" placeholder="Type your message here... e.g. 🎉 Weekend bonus! Deposit now and get 20% extra!"></textarea>
        <br><br>
        <button class="btn-gold" style="padding:10px 24px;font-size:14px" onclick="sendBroadcast()">
          📢 Send to All Players
        </button>
      </div>

      <h2 style="margin-top:24px">📨 Send to Single Player</h2>
      <div class="broadcast-box">
        <input type="number" id="singleUid" placeholder="Player Telegram User ID">
        <textarea id="singleMsg" placeholder="Type your message..."></textarea>
        <br><br>
        <button class="btn-blue" style="padding:10px 24px;font-size:14px" onclick="sendSingle()">
          📨 Send to Player
        </button>
      </div>

      <h2 style="margin-top:24px">🎁 Give Bonus to Single Player</h2>
      <div class="broadcast-box">
        <input type="number" id="bonusUid" placeholder="Player Telegram User ID">
        <input type="number" id="bonusAmt" placeholder="Bonus Amount (ETB)">
        <input type="text"   id="bonusReason" placeholder="Reason (e.g. Welcome bonus, Referral reward...)">
        <br>
        <button class="btn-gold" style="padding:10px 24px;font-size:14px" onclick="giveManualBonus()">
          🎁 Give Bonus
        </button>
      </div>
    </div>

    <!-- BONUS LOG -->
    <div class="section" id="tab-bonuses">
      <h2>🎁 Bonus History</h2>
      <div style="overflow-x:auto">
      <table>
        <tr><th>ID</th><th>UserID</th><th>Name</th><th>Amount</th><th>Reason</th><th>Time</th></tr>
        {bonus_rows if bonus_rows else '<tr><td colspan="6" style="text-align:center;color:#666">No bonuses yet</td></tr>'}
      </table></div>
    </div>

    <!-- NOTIFY LOG -->
    <div class="section" id="tab-notifs">
      <h2>📨 Notification Log</h2>
      <div style="overflow-x:auto">
      <table>
        <tr><th>ID</th><th>UserID</th><th>Name</th><th>Message</th><th>Status</th><th>Time</th></tr>
        {notif_rows if notif_rows else '<tr><td colspan="6" style="text-align:center;color:#666">No notifications sent yet</td></tr>'}
      </table></div>
    </div>

    <script>
    function showTab(name) {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      document.getElementById('tab-' + name).classList.add('active');
      event.target.classList.add('active');
    }}

    function approveDeposit(id, uid, amt) {{
      if(!confirm('Approve ' + amt + ' ETB for user ' + uid + '?')) return;
      fetch('/admin/approve_deposit', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{deposit_id:id,user_id:uid,amount:amt}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}
    function rejectDeposit(id) {{
      if(!confirm('Reject this deposit?')) return;
      fetch('/admin/reject_deposit', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{deposit_id:id}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}

    function blockPlayer(uid) {{
      if(!confirm('Block player ' + uid + '? They will not be able to play or deposit.')) return;
      fetch('/admin/block_player', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:uid,block:true}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}
    function unblockPlayer(uid) {{
      if(!confirm('Unblock player ' + uid + '?')) return;
      fetch('/admin/block_player', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:uid,block:false}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}
    function deletePlayer(uid, name) {{
      if(!confirm('⚠️ PERMANENTLY DELETE player ' + name + ' (' + uid + ')? This cannot be undone!')) return;
      if(!confirm('Are you 100% sure? All data for this player will be deleted.')) return;
      fetch('/admin/delete_player', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:uid}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}

    function giveBonus(uid, name) {{
      const amt = prompt('Give bonus to ' + name + '\\nEnter amount (ETB):');
      if(!amt || isNaN(amt) || parseFloat(amt) <= 0) return;
      const reason = prompt('Reason for bonus (e.g. Welcome bonus):') || 'Admin bonus';
      fetch('/admin/give_bonus', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:uid,amount:parseFloat(amt),reason:reason}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}
    function notifyPlayer(uid, name) {{
      const msg = prompt('Send message to ' + name + ':');
      if(!msg || !msg.trim()) return;
      fetch('/admin/notify_player', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:uid,message:msg}})}})
      .then(r=>r.json()).then(d=>alert(d.message));
    }}

    function sendBroadcast() {{
      const msg = document.getElementById('broadcastMsg').value.trim();
      if(!msg) {{ alert('Please enter a message'); return; }}
      if(!confirm('Send this message to ALL players?')) return;
      fetch('/admin/broadcast', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{message:msg}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);document.getElementById('broadcastMsg').value='';}});
    }}
    function sendSingle() {{
      const uid = document.getElementById('singleUid').value.trim();
      const msg = document.getElementById('singleMsg').value.trim();
      if(!uid || !msg) {{ alert('Please fill in User ID and message'); return; }}
      fetch('/admin/notify_player', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:parseInt(uid),message:msg}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);document.getElementById('singleMsg').value='';}});
    }}
    function giveManualBonus() {{
      const uid    = document.getElementById('bonusUid').value.trim();
      const amt    = document.getElementById('bonusAmt').value.trim();
      const reason = document.getElementById('bonusReason').value.trim() || 'Admin bonus';
      if(!uid || !amt) {{ alert('Please fill in User ID and amount'); return; }}
      fetch('/admin/give_bonus', {{method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{user_id:parseInt(uid),amount:parseFloat(amt),reason:reason}})}})
      .then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}});
    }}
    </script>
    </body></html>'''


# ── ADMIN API ROUTES ──────────────────────────────────────────────────────────
@app.route('/admin/approve_deposit', methods=['POST'])
def approve_deposit():
    data = request.json
    db   = get_db()
    dep  = db.execute('SELECT status FROM deposits WHERE id=?', (data['deposit_id'],)).fetchone()
    if not dep:
        db.close(); return jsonify({'message': '❌ Not found'})
    if dep['status'] == 'approved':
        db.close(); return jsonify({'message': '⚠️ Already approved!'})
    db.execute('UPDATE deposits SET status="approved", note="Manually approved" WHERE id=?', (data['deposit_id'],))
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (data['amount'], data['user_id']))
    db.commit()
    player = db.execute('SELECT full_name FROM players WHERE user_id=?', (data['user_id'],)).fetchone()
    db.close()
    send_admin_telegram(f"✅ Manual approval: {player['full_name'] if player else data['user_id']} +{data['amount']} ETB")
    # Notify player
    send_player_telegram(data['user_id'],
        f"✅ Your deposit of <b>{data['amount']} ETB</b> has been approved!\nYour balance has been updated. Good luck! 🍀")
    return jsonify({'message': f"✅ Approved +{data['amount']} ETB!"})

@app.route('/admin/reject_deposit', methods=['POST'])
def reject_deposit():
    data = request.json
    db   = get_db()
    dep  = db.execute('SELECT status FROM deposits WHERE id=?', (data['deposit_id'],)).fetchone()
    if not dep:
        db.close(); return jsonify({'message': '❌ Not found'})
    if dep['status'] == 'approved':
        db.close(); return jsonify({'message': '⚠️ Cannot reject an approved deposit!'})
    db.execute('UPDATE deposits SET status="rejected", note="Rejected by admin" WHERE id=?', (data['deposit_id'],))
    db.commit(); db.close()
    return jsonify({'message': '❌ Deposit rejected.'})

@app.route('/admin/block_player', methods=['POST'])
def block_player():
    data    = request.json
    user_id = data.get('user_id')
    block   = data.get('block', True)
    db      = get_db()
    db.execute('UPDATE players SET is_blocked=? WHERE user_id=?', (1 if block else 0, user_id))
    db.commit()
    player = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
    name   = player['full_name'] if player else str(user_id)
    db.close()
    action = 'blocked' if block else 'unblocked'
    if block:
        send_player_telegram(user_id,
            "🚫 Your account has been blocked by admin. Please contact support if you think this is a mistake.")
    return jsonify({'message': f'✅ Player {name} has been {action}.'})

@app.route('/admin/delete_player', methods=['POST'])
def delete_player():
    data    = request.json
    user_id = data.get('user_id')
    db      = get_db()
    player  = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
    name    = player['full_name'] if player else str(user_id)
    db.execute('DELETE FROM players WHERE user_id=?',    (user_id,))
    db.execute('DELETE FROM game_cards WHERE user_id=?', (user_id,))
    db.execute('DELETE FROM deposits WHERE user_id=?',   (user_id,))
    db.execute('DELETE FROM withdrawals WHERE user_id=?',(user_id,))
    db.execute('DELETE FROM notifications WHERE user_id=?',(user_id,))
    db.execute('DELETE FROM bonuses WHERE user_id=?',    (user_id,))
    db.commit(); db.close()
    return jsonify({'message': f'🗑 Player {name} permanently deleted.'})

@app.route('/admin/give_bonus', methods=['POST'])
def give_bonus():
    data    = request.json
    user_id = data.get('user_id')
    amount  = float(data.get('amount', 0))
    reason  = data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'message': '❌ Invalid amount'})
    db = get_db()
    player = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
    if not player:
        db.close(); return jsonify({'message': '❌ Player not found'})
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?', (amount, user_id))
    db.execute('INSERT INTO bonuses(user_id,amount,reason,created_at) VALUES(?,?,?,?)',
               (user_id, amount, reason, time.time()))
    db.commit()
    name = player['full_name']
    db.close()
    # Notify player on Telegram
    send_player_telegram(user_id,
        f"🎁 <b>You received a bonus!</b>\n"
        f"💰 Amount: <b>{amount} ETB</b>\n"
        f"📝 Reason: {reason}\n\n"
        f"Your balance has been updated. Enjoy! 🎯")
    send_admin_telegram(f"🎁 Bonus given: {name} +{amount} ETB — {reason}")
    return jsonify({'message': f'🎁 Bonus of {amount} ETB given to {name}!'})

@app.route('/admin/notify_player', methods=['POST'])
def notify_player():
    data    = request.json
    user_id = data.get('user_id')
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'message': '❌ Empty message'})
    db      = get_db()
    player  = db.execute('SELECT full_name FROM players WHERE user_id=?', (user_id,)).fetchone()
    name    = player['full_name'] if player else str(user_id)
    ok      = send_player_telegram(user_id, f"📢 <b>Message from NEF BINGO Admin:</b>\n\n{message}")
    db.execute('INSERT INTO notifications(user_id,message,sent_ok,created_at) VALUES(?,?,?,?)',
               (user_id, message, 1 if ok else 0, time.time()))
    db.commit(); db.close()
    status = f'✅ Sent to {name}' if ok else f'⚠️ Saved but Telegram delivery failed for {name}'
    return jsonify({'message': status})

@app.route('/admin/broadcast', methods=['POST'])
def broadcast():
    data    = request.json
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'message': '❌ Empty message'})
    db      = get_db()
    players = db.execute('SELECT user_id, full_name FROM players WHERE is_blocked=0').fetchall()
    sent, failed = 0, 0
    for p in players:
        ok = send_player_telegram(p['user_id'],
            f"📢 <b>NEF BINGO Announcement:</b>\n\n{message}")
        db.execute('INSERT INTO notifications(user_id,message,sent_ok,created_at) VALUES(?,?,?,?)',
                   (p['user_id'], message, 1 if ok else 0, time.time()))
        if ok: sent += 1
        else:  failed += 1
        time.sleep(0.05)  # avoid Telegram rate limit
    db.commit(); db.close()
    return jsonify({'message': f'📢 Broadcast done! ✅ {sent} sent, ❌ {failed} failed'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
