from flask import Flask, request, jsonify, send_from_directory
import sqlite3, json, time, os, threading, random
from game.bingo_logic import generate_card, draw_ball, check_bingo

app = Flask(__name__, static_folder='static', template_folder='templates')
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bingo.db')

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
            total_won REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stake INTEGER, status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            created_at REAL, started_at REAL
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
            message TEXT, created_at REAL
        );
    ''')
    db.commit()
    db.close()
init_db()

def start_game_engine(game_id):
    def engine():
        time.sleep(30)
        db = get_db()
        game = db.execute('SELECT * FROM games WHERE id=?',(game_id,)).fetchone()
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
            db.close()
            break

        drawn = json.loads(game['drawn_balls'])
        ball = draw_ball(drawn)

        if ball is None:
            db.execute('UPDATE games SET status="finished" WHERE id=?', (game_id,))
            db.commit()
            db.close()
            break

        drawn.append(ball)
        db.execute('UPDATE games SET drawn_balls=? WHERE id=?', (json.dumps(drawn), game_id))
        db.commit()

        # Check for winners
        cards = db.execute('SELECT * FROM game_cards WHERE game_id=?', (game_id,)).fetchall()
        winners = [c for c in cards if check_bingo(json.loads(c['card_data']), drawn)]

        if winners:
            total_pot = game['prize_pool']
            house_commission = round(total_pot * 0.20, 2)
            winners_share = round(total_pot * 0.80, 2)
            prize_per_winner = round(winners_share / len(winners), 2)

            # Give prize to winners
            for winner in winners:
                db.execute('UPDATE players SET balance = balance + ? WHERE user_id = ?',
                           (prize_per_winner, winner['user_id']))

            # Finish current game
            db.execute('''
                UPDATE games 
                SET status = 'finished', 
                    finished_at = ? 
                WHERE id = ?
            ''', (time.time(), game_id))
            db.commit()

            print(f"✅ Game {game_id} finished. {len(winners)} winner(s). Prize: {prize_per_winner} each")

            db.close()

            # Auto start next game after 5 seconds
            time.sleep(5)
            
            db = get_db()
            db.execute('''
                INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls)
                VALUES (?, 0, ?, 'waiting', '[]')
            ''', (game['stake'], time.time()))
            db.commit()
            
            new_game = db.execute('''
                SELECT id FROM games 
                WHERE stake=? AND status='waiting' 
                ORDER BY id DESC LIMIT 1
            ''', (game['stake'],)).fetchone()
            
            if new_game:
                start_game_engine(new_game['id'])
                print(f"New game started for stake {game['stake']}")
            
            db.close()
            break   # Important: Exit the current draw_loop

        db.close()

def is_game_running(db):
    """Check if any game is currently running"""
    result = db.execute('SELECT COUNT(*) FROM games WHERE status="running"').fetchone()
    return result[0] > 0

@app.route('/')
def index():
    return send_from_directory('templates','index.html')

@app.route('/api/player/<int:user_id>')
def get_player(user_id):
    username = request.args.get('username','user')
    full_name = request.args.get('full_name','User')
    db = get_db()
    p = db.execute('SELECT * FROM players WHERE user_id=?',(user_id,)).fetchone()
    if not p:
        db.execute('INSERT INTO players(user_id,username,full_name) VALUES(?,?,?)',
                   (user_id,username,full_name))
        db.commit()
        p = db.execute('SELECT * FROM players WHERE user_id=?',(user_id,)).fetchone()
    result = dict(p)
    db.close()
    return jsonify(result)

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data = request.json
    user_id = data.get('user_id')
    stake = data.get('stake')

    if not user_id or not stake:
        return jsonify({'error': 'user_id and stake are required'}), 400

    db = get_db()

    # Check if there is already a waiting or running game for this stake
    existing_game = db.execute('''
        SELECT * FROM games 
        WHERE stake = ? 
          AND status IN ('waiting', 'running')
        LIMIT 1
    ''', (stake,)).fetchone()

    if existing_game:
        game_id = existing_game['id']
        game = existing_game
    else:
        # Create new game for this stake
        db.execute('''
            INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls)
            VALUES (?, 0, ?, 'waiting', '[]')
        ''', (stake, time.time()))
        db.commit()

        game = db.execute('''
            SELECT * FROM games 
            WHERE stake = ? AND status = 'waiting'
            ORDER BY id DESC LIMIT 1
        ''', (stake,)).fetchone()

        game_id = game['id']
        start_game_engine(game_id)

    # Get current game stats
    taken = [r['card_number'] for r in db.execute(
        'SELECT card_number FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()]

    players = len({r['user_id'] for r in db.execute(
        'SELECT user_id FROM game_cards WHERE game_id=?', (game_id,)
    ).fetchall()})

    countdown = max(0, int(30 - (time.time() - game['created_at'])))

    db.close()

    return jsonify({
        'game_id': game_id,
        'stake': stake,
        'prize_pool': game['prize_pool'],
        'players': players,
        'taken_cards': taken,
        'countdown': countdown,
        'status': game['status']
    })

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id,game_id,card_number,stake = data['user_id'],data['game_id'],data['card_number'],data['stake']
    db = get_db()
    player = db.execute('SELECT * FROM players WHERE user_id=?',(user_id,)).fetchone()
    if player['balance'] < stake:
        db.close(); return jsonify({'error':'Insufficient balance'})
    if db.execute('SELECT id FROM game_cards WHERE game_id=? AND card_number=?',(game_id,card_number)).fetchone():
        db.close(); return jsonify({'error':'Card taken'})
    if db.execute('SELECT COUNT(*) as c FROM game_cards WHERE game_id=? AND user_id=?',(game_id,user_id)).fetchone()['c'] >= 4:
        db.close(); return jsonify({'error':'Max 4 cards'})
    db.execute('INSERT INTO game_cards(game_id,user_id,card_number,card_data) VALUES(?,?,?,?)',
               (game_id,user_id,card_number,json.dumps(generate_card())))
    db.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(stake,user_id))
    db.execute('UPDATE games SET prize_pool=prize_pool+? WHERE id=?',(stake,game_id))
    db.commit()
    new_bal = db.execute('SELECT balance FROM players WHERE user_id=?',(user_id,)).fetchone()['balance']
    db.close()
    return jsonify({'success':True,'balance':new_bal})

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    db = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if not game:
        db.close()
        return jsonify({'error': 'Game not found'}), 404

    drawn = json.loads(game.get('drawn_balls', '[]'))

    result = {
        'status': game['status'],
        'drawn_balls': drawn,
        'prize_pool': game['prize_pool'],
        'stake': game['stake']
    }

    if game['status'] == 'finished':
        winners_raw = db.execute('''
            SELECT gc.*, p.full_name 
            FROM game_cards gc 
            JOIN players p ON gc.user_id = p.user_id 
            WHERE gc.game_id=?
        ''', (game_id,)).fetchall()

        result['winners'] = []
        for w in winners_raw:
            if check_bingo(json.loads(w['card_data']), drawn):
                result['winners'].append({
                    'name': w['full_name'],
                    'card_number': w['card_number']
                })

    db.close()
    return jsonify(result)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    db = get_db()
    cards = db.execute('SELECT card_number,card_data FROM game_cards WHERE game_id=? AND user_id=?',(game_id,user_id)).fetchall()
    db.close()
    return jsonify({'cards':[{'card_index':c['card_number'],'card_data':json.loads(c['card_data'])} for c in cards]})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO deposits(user_id,amount,platform,tx_ref,created_at) VALUES(?,?,?,?,?)',
               (data['user_id'],data['amount'],data['platform'],data['tx_ref'],time.time()))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    db = get_db()
    player = db.execute('SELECT balance FROM players WHERE user_id=?',(data['user_id'],)).fetchone()
    if not player or player['balance'] < data['amount']:

        db.close(); return jsonify({'error':'Insufficient balance'})
    db.execute('UPDATE players SET balance=balance-? WHERE user_id=?',(data['amount'],data['user_id']))
    db.execute('INSERT INTO withdrawals(user_id,amount,platform,account_no,created_at) VALUES(?,?,?,?,?)',
               (data['user_id'],data['amount'],data['platform'],data['account_no'],time.time()))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO inquiries(user_id,subject,message,created_at) VALUES(?,?,?,?)',
               (data['user_id'],data['subject'],data['message'],time.time()))
    db.commit(); db.close()
    return jsonify({'success':True})

@app.route('/admin')
def admin():
    db = get_db()
    deps = db.execute('SELECT d.*,p.full_name FROM deposits d LEFT JOIN players p ON d.user_id=p.user_id ORDER BY d.id DESC LIMIT 30').fetchall()
    wds  = db.execute('SELECT w.*,p.full_name FROM withdrawals w LEFT JOIN players p ON w.user_id=p.user_id ORDER BY w.id DESC LIMIT 30').fetchall()
    plrs = db.execute('SELECT * FROM players ORDER BY balance DESC').fetchall()
    db.close()
    def rows(items):
        return ''.join(f'<tr>{"".join(f"<td>{v}</td>" for v in dict(i).values())}</tr>' for i in items)
    dep_rows = ''.join(f'<tr><td>{d["id"]}</td><td>{d["user_id"]}</td><td>{d["full_name"]}</td><td>{d["amount"]}</td><td>{d["platform"]}</td><td>{d["tx_ref"]}</td><td>{d["status"]}</td><td><button onclick="approve({d["id"]},{d["user_id"]},{d["amount"]})">✅</button></td></tr>' for d in deps)
    return f'''<html><head><style>body{{font-family:monospace;background:#111;color:#eee;padding:20px}}table{{border-collapse:collapse;width:100%;margin-bottom:30px}}th,td{{border:1px solid #444;padding:6px}}th{{background:#222}}h2{{color:gold}}button{{background:#0a0;color:#fff;border:none;padding:4px 8px;cursor:pointer}}</style></head><body>
    <h1 style="color:gold">🎯 NEF BINGO ADMIN</h1>
    <h2>💰 Deposits</h2><table><tr><th>ID</th><th>UserID</th><th>Name</th><th>Amount</th><th>Platform</th><th>TxRef</th><th>Status</th><th>Action</th></tr>{dep_rows}</table>
    <h2>👥 Players</h2><table><tr><th>ID</th><th>Username</th><th>Name</th><th>Balance</th><th>Games</th><th>Wins</th><th>Won</th></tr>{rows(plrs)}</table>
    <script>function approve(id,uid,amt){{fetch('/admin/approve_deposit',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{deposit_id:id,user_id:uid,amount:amt}})}}).then(r=>r.json()).then(d=>{{alert(d.message);location.reload();}})}}</script>
    </body></html>'''

@app.route('/admin/approve_deposit', methods=['POST'])
def approve_deposit():
    data = request.json
    db = get_db()
    db.execute('UPDATE deposits SET status="approved" WHERE id=?',(data['deposit_id'],))
    db.execute('UPDATE players SET balance=balance+? WHERE user_id=?',(data['amount'],data['user_id']))
    db.commit(); db.close()
    return jsonify({'message':f'Approved +{data["amount"]} ETB!'})

if __name__ == '__main__':
    init_db()
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
