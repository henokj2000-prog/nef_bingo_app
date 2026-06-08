import sys
import os

# Ensure the current directory is in sys.path so 'game' module is found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if 'sqlite3' in sys.modules:
    del sys.modules['sqlite3']

from flask import Flask, request, jsonify, send_from_directory, g
import json
import time
import re
import requests
from game.bingo_logic import generate_card, draw_ball, check_bingo
from database import *
from config import ADMIN_PASSWORD, ADMIN_IDS, BOT_TOKEN, BALL_DRAW_INTERVAL_SECONDS, MAX_BALLS_PER_GAME

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- Automatic database connection teardown ----------
@app.teardown_appcontext
def close_db_connection(exception=None):
    """Close the database connection at the end of each request if it exists."""
    if hasattr(g, 'db_conn'):
        g.db_conn.close()

# ---------- Routes ----------
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/admin')
def admin():
    return send_from_directory('templates', 'admin.html')

@app.route('/api/player/<int:user_id>')
def get_player(user_id):
    username = request.args.get('username', 'user')
    full_name = request.args.get('full_name', 'User')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if not p:
            cur.execute("INSERT INTO players (user_id, username, full_name) VALUES (%s, %s, %s)", (user_id, username, full_name))
            conn.commit()
            cur.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            p = cur.fetchone()
            create_referral_code_for_user(user_id)
        result = dict(p)
        cur.execute("""
            SELECT g.id as game_id, g.status, g.stake
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.status IN ('waiting','running')
            ORDER BY g.id DESC LIMIT 1
        """, (user_id,))
        active = cur.fetchone()
        result['active_game'] = dict(active) if active else None
        return jsonify(result)
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    data = request.json
    user_id = data.get('user_id')
    phone = data.get('phone', '').strip()
    language = data.get('language', '')
    referral_code = data.get('referral_code', '').strip()
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        if phone:
            cur.execute("SELECT user_id FROM players WHERE phone = %s AND user_id != %s", (phone, user_id))
            if cur.fetchone():
                return jsonify({'error': 'This phone number is already registered with another account.'}), 400
            cur.execute("UPDATE players SET phone = %s WHERE user_id = %s", (phone, user_id))
        if language and language in ['en','am','om','ti']:
            cur.execute("UPDATE players SET language = %s WHERE user_id = %s", (language, user_id))
        if referral_code:
            cur.execute("SELECT referred_by FROM players WHERE user_id = %s", (user_id,))
            existing_ref = cur.fetchone()
            if not existing_ref or not existing_ref['referred_by']:
                cur.execute("SELECT user_id FROM referral_codes WHERE code = %s", (referral_code,))
                referrer = cur.fetchone()
                if referrer and referrer['user_id'] != user_id:
                    cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s", (referrer['user_id'], user_id))
                    conn.commit()
                    award_referral_bonus(referrer['user_id'], user_id)
        conn.commit()
        create_referral_code_for_user(user_id)
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/reset_player', methods=['POST'])
def reset_player():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET phone = NULL, language = 'en' WHERE user_id = %s", (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Account reset. Please re‑register.'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/join_game', methods=['POST'])
def join_game():
    data = request.json
    user_id = data.get('user_id')
    stake = data.get('stake')
    if not user_id or not stake:
        return jsonify({'error': 'user_id and stake are required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_banned FROM players WHERE user_id=%s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Your account has been suspended. Contact support.'}), 403

        # Look for existing waiting game
        cur.execute("SELECT * FROM games WHERE stake=%s AND status IN ('waiting','running') ORDER BY id DESC LIMIT 1", (stake,))
        game = cur.fetchone()

        # Clean up stale waiting game (older than 30 seconds, no cards)
        if game and game['status'] == 'waiting' and (time.time() - game['created_at']) > 30:
            cur.execute("SELECT COUNT(*) FROM game_cards WHERE game_id=%s", (game['id'],))
            card_cnt = cur.fetchone()[0]
            if card_cnt == 0:
                cur.execute("DELETE FROM games WHERE id=%s", (game['id'],))
                conn.commit()
                game = None

        if not game:
            cur.execute("INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')", (stake, time.time()))
            conn.commit()
            cur.execute("SELECT * FROM games WHERE stake=%s AND status='waiting' ORDER BY id DESC LIMIT 1", (stake,))
            game = cur.fetchone()

        game_id = game['id']
        cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s", (game_id,))
        players = len(cur.fetchall())
        countdown = max(0, int(30 - (time.time() - game['created_at'])))
        return jsonify({
            'game_id': game_id, 'stake': stake, 'prize_pool': game['prize_pool'],
            'players': players, 'taken_cards': taken, 'countdown': countdown, 'status': game['status']
        })
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id, game_id, card_number, stake = data['user_id'], data['game_id'], data['card_number'], data['stake']
    conn = get_db()
    cur = conn.cursor()
    try:
        # Lock the game row to prevent race condition
        cur.execute("SELECT * FROM games WHERE id=%s FOR UPDATE", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game has already started or finished'}), 400
        if game['stake'] != stake:
            return jsonify({'error': f'Stake mismatch. Game stake is {game["stake"]} ETB'}), 400
        
        cur.execute("SELECT balance FROM players WHERE user_id=%s", (user_id,))
        player = cur.fetchone()
        if player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Check if card already taken (within the locked transaction)
        cur.execute("SELECT id FROM game_cards WHERE game_id=%s AND card_number=%s", (game_id, card_number))
        if cur.fetchone():
            return jsonify({'error': 'Card already taken'}), 400
        
        cur.execute("SELECT COUNT(*) as c FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, user_id))
        if cur.fetchone()['c'] >= 4:
            return jsonify({'error': 'Max 4 cards per game'}), 400
        
        cur.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                    (game_id, user_id, card_number, json.dumps(generate_card())))
        cur.execute("UPDATE players SET balance=balance-%s, games_played=games_played+1 WHERE user_id=%s", (stake, user_id))
        cur.execute("UPDATE games SET prize_pool=prize_pool+%s WHERE id=%s", (stake, game_id))
        conn.commit()
        
        cur.execute("SELECT balance FROM players WHERE user_id=%s", (user_id,))
        new_bal = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': new_bal})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/withdraw_from_game', methods=['POST'])
def withdraw_from_game():
    data = request.json
    user_id = data.get('user_id')
    game_id = data.get('game_id')
    if not user_id or not game_id:
        return jsonify({'error': 'user_id and game_id required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status, stake FROM games WHERE id=%s", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'waiting':
            return jsonify({'error': 'Game already started or not found'}), 400
        cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, user_id))
        cards = cur.fetchall()
        if not cards:
            return jsonify({'error': 'No cards found for this user in this game'}), 404
        stake = game['stake']
        refund = stake * len(cards)
        cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (refund, user_id))
        cur.execute("DELETE FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, user_id))
        cur.execute("UPDATE games SET prize_pool=prize_pool-%s WHERE id=%s", (refund, game_id))
        conn.commit()
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s", (game_id,))
        remaining = cur.fetchall()
        real_remaining = [p['user_id'] for p in remaining if p['user_id'] not in ADMIN_IDS and p['user_id'] > 0]
        if not real_remaining:
            cur.execute("DELETE FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
            cur.execute("UPDATE games SET status='finished', cancelled=1, finished_at=%s WHERE id=%s", (time.time(), game_id))
            conn.commit()
            return jsonify({'success': True, 'message': 'Game cancelled because you were the last real player.'})
        else:
            cur.execute("SELECT value FROM settings WHERE key='bot_enabled'")
            bot_enabled_row = cur.fetchone()
            bot_enabled = int(bot_enabled_row['value']) if bot_enabled_row else 1
            cur.execute("SELECT value FROM settings WHERE key='bot_min_players'")
            min_players_row = cur.fetchone()
            min_players_needed = int(min_players_row['value']) if min_players_row else 2
            if bot_enabled and stake == 10 and len(real_remaining) < min_players_needed:
                add_bot_to_game(game_id, stake)
        return jsonify({'success': True, 'message': 'Withdrawn from game.'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    user_id = request.args.get('user_id')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM games WHERE id=%s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        drawn = json.loads(game['drawn_balls'] or '[]')
        cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
        taken = [r['card_number'] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s", (game_id,))
        players = len(cur.fetchall())
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
            return jsonify(result)
        if game['status'] == 'finished':
            winner_card_numbers = json.loads(game['winner_card_numbers'] or '[]')
            if winner_card_numbers:
                placeholders = ','.join(['%s'] * len(winner_card_numbers))
                query = f"""
                    SELECT gc.card_number, p.full_name, p.user_id
                    FROM game_cards gc
                    JOIN players p ON gc.user_id = p.user_id
                    WHERE gc.game_id = %s AND gc.card_number IN ({placeholders})
                """
                params = [game_id] + winner_card_numbers
                cur.execute(query, params)
                winners_raw = cur.fetchall()
            else:
                winners_raw = []
            num_winners = len(winner_card_numbers)
            prize_each = round(winners_share / num_winners, 2) if num_winners > 0 else 0
            result['winners'] = [{'name': w['full_name'], 'card_number': w['card_number'], 'prize': prize_each} for w in winners_raw]
            result['prize_each'] = prize_each
            cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' AND id != %s ORDER BY id DESC LIMIT 1", (game['stake'], game_id))
            next_game = cur.fetchone()
            result['next_game_id'] = next_game['id'] if next_game else None
        return jsonify(result)
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT card_number, card_data FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, user_id))
        cards = cur.fetchall()
        return jsonify({'cards': [{'card_index': c['card_number'], 'card_data': json.loads(c['card_data'])} for c in cards]})
    finally:
        cur.close()
        put_db(conn)

# ---------- Deposit, Withdraw, Inquiry ----------
TELEBIRR_PATTERN = re.compile(r'received ETB\s+([\d,]+\.?\d*)\s+from.*?transaction number is\s+([A-Z0-9]+)', re.IGNORECASE | re.DOTALL)
CBE_PATTERN = re.compile(r'received ETB\s+([\d,]+\.?\d*)\s+from.*?https://Mbreciept\.cbe\.com\.et/[^\s]*([A-Z0-9]+)', re.IGNORECASE | re.DOTALL)

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

def send_telegram_message(chat_id, text):
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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM deposits WHERE tx_ref=%s", (proof,))
        if cur.fetchone():
            return jsonify({'error': 'This transaction reference has already been used.'}), 400
        sms_amount, tx_ref = parse_sms_reference(proof, platform)
        if sms_amount is not None and tx_ref and abs(sms_amount - amount) <= 5:
            cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (amount, user_id))
            cur.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'")
            row = cur.fetchone()
            bonus_percent = float(row['value']) if row else 0
            if bonus_percent > 0:
                bonus_amount = round(amount * bonus_percent / 100, 2)
                cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (bonus_amount, user_id))
                print(f"🎁 Deposit bonus: {bonus_percent}% = +{bonus_amount} ETB for user {user_id}")
            cur.execute("INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                        (user_id, amount, platform, tx_ref, 'approved', time.time()))
            conn.commit()
            cur.execute("SELECT balance FROM players WHERE user_id=%s", (user_id,))
            new_bal = cur.fetchone()['balance']
            return jsonify({'success': True, 'approved': True, 'message': f'✅ {amount} ETB credited!', 'balance': new_bal})
        cur.execute("INSERT INTO deposits(user_id,amount,platform,tx_ref,status,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                    (user_id, amount, platform, proof, 'pending', time.time()))
        conn.commit()
        return jsonify({'success': True, 'approved': False, 'message': '⏳ Deposit submitted for admin review.'})
    finally:
        cur.close()
        put_db(conn)

MIN_WITHDRAWAL = 50
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    amount = data.get('amount', 0)
    if amount < MIN_WITHDRAWAL:
        return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAWAL} ETB'})
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT balance FROM players WHERE user_id=%s", (data['user_id'],))
        player = cur.fetchone()
        if not player or player['balance'] < amount:
            return jsonify({'error': 'Insufficient balance'})
        cur.execute("UPDATE players SET balance=balance-%s WHERE user_id=%s", (amount, data['user_id']))
        cur.execute("INSERT INTO withdrawals(user_id,amount,platform,account_no,created_at) VALUES(%s,%s,%s,%s,%s)",
                    (data['user_id'], amount, data['platform'], data['account_no'], time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': 'Withdrawal requested.'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO inquiries(user_id,subject,message,created_at) VALUES(%s,%s,%s,%s)",
                    (data['user_id'], data['subject'], data['message'], time.time()))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/transactions/<int:user_id>')
def transactions(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 'deposit' as type, amount, platform as detail, status, created_at FROM deposits WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (user_id,))
        deps = cur.fetchall()
        cur.execute("SELECT 'withdrawal' as type, amount, platform as detail, status, created_at FROM withdrawals WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", (user_id,))
        wds = cur.fetchall()
        txs = sorted([dict(d) for d in deps] + [dict(w) for w in wds], key=lambda x: x['created_at'], reverse=True)
        return jsonify({'transactions': txs})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT full_name, wins, total_won, games_played FROM players WHERE is_banned=0 ORDER BY total_won DESC LIMIT 20")
        players = cur.fetchall()
        return jsonify({'leaderboard': [dict(p) for p in players]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/recent_games/<int:user_id>')
def recent_games(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT g.id, g.stake, g.prize_pool, g.status, g.finished_at,
                   CASE WHEN g.winner_card_numbers != '[]' THEN 1 ELSE 0 END as won
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s
            ORDER BY g.id DESC LIMIT 10
        """, (user_id,))
        games = cur.fetchall()
        return jsonify({'games': [dict(g) for g in games]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/referral_stats/<int:user_id>')
def referral_stats(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
        code = cur.fetchone()
        code_val = code['code'] if code else None
        cur.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = %s", (user_id,))
        row = cur.fetchone()
        ref_count = row['count'] if row else 0
        cur.execute("SELECT COALESCE(SUM(amount),0) as pending_total FROM referral_commissions WHERE referrer_id = %s AND status = 'pending'", (user_id,))
        row = cur.fetchone()
        pending_total = row['pending_total'] if row else 0
        cur.execute("SELECT COALESCE(SUM(amount),0) as paid_total FROM referral_commissions_archive WHERE referrer_id = %s", (user_id,))
        row = cur.fetchone()
        paid_total = row['paid_total'] if row else 0
        return jsonify({
            'referral_code': code_val,
            'referral_count': ref_count,
            'pending_commissions': pending_total,
            'total_commissions_paid': paid_total
        })
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/<key>')
def get_setting(key):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        if row:
            return jsonify({key: row['value']})
        return jsonify({key: None}), 404
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/set_chat_id', methods=['POST'])
def set_chat_id():
    data = request.json
    user_id = data.get('user_id')
    chat_id = data.get('chat_id')
    if not user_id or not chat_id:
        return jsonify({'error': 'User ID and Chat ID required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET chat_id = %s WHERE user_id = %s", (chat_id, user_id))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM deposits WHERE tx_ref = %s AND status = 'pending'", (ref,))
        deposit = cur.fetchone()
        if not deposit:
            return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
        if abs(deposit['amount'] - amount) > 5:
            return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {deposit["amount"]}'}), 400
        cur.execute("UPDATE deposits SET status = 'approved' WHERE id = %s", (deposit['id'],))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (deposit['amount'], deposit['user_id']))
        cur.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(deposit['amount'] * bonus_percent / 100, 2)
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (bonus_amount, deposit['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Deposit auto-approved'})
    finally:
        cur.close()
        put_db(conn)

# ---------- Admin routes ----------
def admin_auth(data):
    return data.get('password') == ADMIN_PASSWORD

@app.route('/admin/api/overview')
def admin_overview():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        stats = {
            'total_players': cur.execute("SELECT COUNT(*) FROM players").fetchone()[0],
            'total_deposited': cur.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'").fetchone()[0],
            'total_withdrawn': cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='approved'").fetchone()[0],
            'pending_deposits': cur.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0],
            'pending_withdrawals': cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0],
            'active_games': cur.execute("SELECT COUNT(*) FROM games WHERE status IN ('waiting','running')").fetchone()[0],
        }
        return jsonify(stats)
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/players')
def admin_players():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM players ORDER BY balance DESC")
        players = cur.fetchall()
        return jsonify({'players': [dict(p) for p in players]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/deposits')
def admin_deposits():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT d.*, p.full_name FROM deposits d LEFT JOIN players p ON d.user_id=p.user_id ORDER BY d.id DESC LIMIT 50")
        deps = cur.fetchall()
        return jsonify({'deposits': [dict(d) for d in deps]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/withdrawals')
def admin_withdrawals():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT w.*, p.full_name FROM withdrawals w LEFT JOIN players p ON w.user_id=p.user_id ORDER BY w.id DESC LIMIT 50")
        wds = cur.fetchall()
        return jsonify({'withdrawals': [dict(w) for w in wds]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/active_games')
def admin_active_games():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT g.*, COUNT(gc.id) as card_count FROM games g LEFT JOIN game_cards gc ON gc.game_id=g.id WHERE g.status IN ('waiting','running') GROUP BY g.id ORDER BY g.id DESC")
        games = cur.fetchall()
        return jsonify({'games': [dict(g) for g in games]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/approve_deposit', methods=['POST'])
def approve_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM deposits WHERE id=%s", (data['deposit_id'],))
        dep = cur.fetchone()
        if not dep or dep['status'] == 'approved':
            return jsonify({'error': 'Invalid or already approved'}), 400
        cur.execute("UPDATE deposits SET status='approved' WHERE id=%s", (data['deposit_id'],))
        cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (dep['amount'], dep['user_id']))
        cur.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
            cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (bonus_amount, dep['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f'Approved +{dep["amount"]} ETB'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/reject_deposit', methods=['POST'])
def reject_deposit():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE deposits SET status='rejected' WHERE id=%s", (data['deposit_id'],))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/approve_withdrawal', methods=['POST'])
def approve_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE withdrawals SET status='approved' WHERE id=%s", (data['withdrawal_id'],))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/reject_withdrawal', methods=['POST'])
def reject_withdrawal():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM withdrawals WHERE id=%s", (data['withdrawal_id'],))
        wd = cur.fetchone()
        if not wd:
            return jsonify({'error': 'Not found'}), 404
        cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (wd['amount'], wd['user_id']))
        cur.execute("UPDATE withdrawals SET status='rejected' WHERE id=%s", (data['withdrawal_id'],))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                    (user_id, amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to user {user_id}'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/give_bonus_all', methods=['POST'])
def give_bonus_all():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin bonus')
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM players WHERE is_banned = 0")
        players = cur.fetchall()
        for p in players:
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (amount, p['user_id']))
            cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                        (p['user_id'], amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to all {len(players)} players'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/get_user_by_phone', methods=['POST'])
def get_user_by_phone():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    phone = data.get('phone', '').strip()
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id, full_name FROM players WHERE phone = %s", (phone,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'No player found with that phone number'}), 404
        return jsonify({'user_id': user['user_id'], 'full_name': user['full_name']})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/give_bonus_by_phone', methods=['POST'])
def give_bonus_by_phone():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    phone = data.get('phone', '').strip()
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin bonus')
    if not phone or amount <= 0:
        return jsonify({'error': 'Phone number and valid amount required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM players WHERE phone = %s", (phone,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'Player not found'}), 404
        user_id = user['user_id']
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                    (user_id, amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to player with phone {phone}'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/ban_player', methods=['POST'])
def ban_player():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE players SET is_banned=%s WHERE user_id=%s", (1 if data.get('ban') else 0, data['user_id']))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/force_finish', methods=['POST'])
def force_finish():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    game_id = data['game_id']
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM games WHERE id=%s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s", (game_id,))
        cards = cur.fetchall()
        stake = game['stake']
        for c in cards:
            cur.execute("SELECT COUNT(*) FROM game_cards WHERE game_id=%s AND user_id=%s", (game_id, c['user_id']))
            card_count = cur.fetchone()[0]
            cur.execute("UPDATE players SET balance=balance+%s WHERE user_id=%s", (stake * card_count, c['user_id']))
        cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM deposits WHERE tx_ref = %s AND status = 'pending'", (ref,))
        dep = cur.fetchone()
        if not dep:
            return jsonify({'error': f'No pending deposit with reference {ref}'}), 404
        if abs(dep['amount'] - amount) > 5:
            return jsonify({'error': f'Amount mismatch: SMS {amount}, deposit {dep["amount"]}'}), 400
        cur.execute("UPDATE deposits SET status = 'approved' WHERE id = %s", (dep['id'],))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (dep['amount'], dep['user_id']))
        cur.execute("SELECT value FROM settings WHERE key = 'deposit_bonus_percent'")
        row = cur.fetchone()
        bonus_percent = float(row['value']) if row else 0
        if bonus_percent > 0:
            bonus_amount = round(dep['amount'] * bonus_percent / 100, 2)
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (bonus_amount, dep['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f'Deposit #{dep["id"]} auto-approved.'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/add_admin', methods=['POST'])
def add_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM admins WHERE user_id = %s", (data['admin_user_id'],))
        requester = cur.fetchone()
        if not requester or requester['role'] != 'super_admin':
            return jsonify({'error': 'Only super admin can add admins'}), 403
        new_admin_id = data.get('new_admin_id')
        role = data.get('role', 'admin')
        if not new_admin_id:
            return jsonify({'error': 'user_id required'}), 400
        cur.execute("INSERT INTO admins (user_id, role, added_by, created_at) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                    (new_admin_id, role, data['admin_user_id'], time.time()))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/remove_admin', methods=['POST'])
def remove_admin():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM admins WHERE user_id = %s", (data['admin_user_id'],))
        requester = cur.fetchone()
        if not requester or requester['role'] != 'super_admin':
            return jsonify({'error': 'Only super admin can remove admins'}), 403
        admin_id = data.get('admin_id')
        if admin_id == data['admin_user_id']:
            return jsonify({'error': 'Cannot remove yourself'}), 400
        cur.execute("DELETE FROM admins WHERE user_id = %s", (admin_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/admins')
def get_admins():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM admins")
        admins = cur.fetchall()
        return jsonify({'admins': [dict(a) for a in admins]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_referral_settings', methods=['POST'])
def update_referral_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        if 'commission_percent' in data:
            cur.execute("UPDATE settings SET value = %s WHERE key = 'referral_commission_percent'", (str(data['commission_percent']),))
        if 'bonus_amount' in data:
            cur.execute("UPDATE settings SET value = %s WHERE key = 'referral_bonus_amount'", (str(data['bonus_amount']),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/referral_settings')
def referral_settings():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'referral_commission_percent'")
        percent = cur.fetchone()
        cur.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'")
        bonus = cur.fetchone()
        return jsonify({
            'commission_percent': float(percent['value']) if percent else 5.0,
            'bonus_amount': float(bonus['value']) if bonus else 10.0
        })
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/pending_commissions')
def pending_commissions():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT c.*, p.full_name as referrer_name, p2.full_name as referred_name
            FROM referral_commissions c
            JOIN players p ON c.referrer_id = p.user_id
            JOIN players p2 ON c.referred_id = p2.user_id
            WHERE c.status = 'pending' ORDER BY c.created_at DESC
        """)
        rows = cur.fetchall()
        return jsonify({'commissions': [dict(r) for r in rows]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/revoke_commission', methods=['POST'])
def revoke_commission():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    commission_id = data.get('commission_id')
    if not commission_id:
        return jsonify({'error': 'commission_id required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM referral_commissions WHERE id = %s AND status = 'pending'", (commission_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Commission revoked'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/adjust_commission', methods=['POST'])
def adjust_commission():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    commission_id = data.get('commission_id')
    new_amount = data.get('new_amount')
    if not commission_id or new_amount is None:
        return jsonify({'error': 'commission_id and new_amount required'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE referral_commissions SET amount = %s WHERE id = %s AND status = 'pending'", (new_amount, commission_id))
        conn.commit()
        return jsonify({'success': True, 'message': f'Commission updated to {new_amount} ETB'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/process_weekly_payout', methods=['POST'])
def process_weekly_payout():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM referral_commissions WHERE status = 'pending'")
        pending = cur.fetchall()
        if not pending:
            return jsonify({'success': True, 'message': 'No pending commissions'})
        week_start = time.time() - 7*86400
        week_end = time.time()
        total_paid = 0
        for comm in pending:
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (comm['amount'], comm['referrer_id']))
            cur.execute("UPDATE referral_commissions SET status = 'paid', paid_at = %s WHERE id = %s", (time.time(), comm['id']))
            cur.execute("""
                INSERT INTO referral_commissions_archive
                (referrer_id, referred_id, game_id, amount, paid_at, payment_week_start, payment_week_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (comm['referrer_id'], comm['referred_id'], comm['game_id'], comm['amount'], time.time(), week_start, week_end))
            total_paid += comm['amount']
        conn.commit()
        return jsonify({'success': True, 'total_paid': total_paid, 'count': len(pending)})
    finally:
        cur.close()
        put_db(conn)

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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE settings SET value=%s WHERE key='max_balls_per_game'", (str(max_balls),))
        conn.commit()
        return jsonify({'success': True, 'max_balls': max_balls})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_bot_settings', methods=['POST'])
def update_bot_settings():
    data = request.json
    if not admin_auth(data):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        if 'bot_enabled' in data:
            cur.execute("UPDATE settings SET value=%s WHERE key='bot_enabled'", (str(data['bot_enabled']),))
        if 'bot_cards_per_game' in data:
            cur.execute("UPDATE settings SET value=%s WHERE key='bot_cards_per_game'", (str(data['bot_cards_per_game']),))
        if 'bot_min_players' in data:
            cur.execute("UPDATE settings SET value=%s WHERE key='bot_min_players'", (str(data['bot_min_players']),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/commission_stats')
def commission_stats():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as pending_count, COALESCE(SUM(amount),0) as pending_total FROM referral_commissions WHERE status='pending'")
        pending = cur.fetchone()
        cur.execute("SELECT COUNT(*) as paid_count, COALESCE(SUM(amount),0) as paid_total FROM referral_commissions_archive")
        paid = cur.fetchone()
        cur.execute("""
            SELECT c.*, p.full_name as referrer_name, p2.full_name as referred_name
            FROM referral_commissions c
            JOIN players p ON c.referrer_id = p.user_id
            JOIN players p2 ON c.referred_id = p2.user_id
            WHERE c.status = 'pending'
            ORDER BY c.created_at DESC
        """)
        pending_list = cur.fetchall()
        return jsonify({
            'pending_count': pending['pending_count'],
            'pending_total': pending['pending_total'],
            'paid_count': paid['paid_count'],
            'paid_total': paid['paid_total'],
            'pending_commissions': [dict(row) for row in pending_list]
        })
    finally:
        cur.close()
        put_db(conn)

# ---------- ADDED: Missing notification route ----------
@app.route('/api/notifications/latest')
def latest_notification():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT message, created_at FROM notifications WHERE is_broadcast=1 ORDER BY created_at DESC LIMIT 1")
        notif = cur.fetchone()
        if notif:
            return jsonify({'message': notif['message'], 'created_at': notif['created_at']})
        return jsonify({'message': None})
    finally:
        cur.close()
        put_db(conn)

# ---------- Initialize database at startup (for gunicorn) ----------
with app.app_context():
    init_db()
    create_bot_players()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
