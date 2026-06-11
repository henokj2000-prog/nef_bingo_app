import sys
import os
import json
import time
import random
from flask import Flask, request, jsonify, send_from_directory, g, render_template
import requests

# Ensure local modules are found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.bingo_logic import generate_card, draw_ball, check_bingo
from database import (
    get_db, put_db, init_db, create_bot_players,
    create_referral_code_for_user, award_referral_bonus, add_bot_to_game
)
from config import ADMIN_PASSWORD, ADMIN_IDS, BOT_TOKEN, WEB_APP_URL

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- Helper: validate user ID ----------
def is_valid_id(id_val):
    try:
        return int(id_val) > 0
    except (TypeError, ValueError):
        return False

# ---------- Helper: get current running game for a stake ----------
def get_current_running_game(stake):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, status, drawn_balls, prize_pool, created_at, winner_card_numbers
            FROM games
            WHERE stake = %s AND status = 'running'
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        game = cur.fetchone()
        return dict(game) if game else None
    finally:
        cur.close()
        put_db(conn)

# ---------- Automatic database connection teardown ----------
@app.teardown_appcontext
def close_db_connection(exception=None):
    if hasattr(g, 'db_conn'):
        put_db(g.db_conn)

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
    full_name = request.args.get('full_name', 'Player')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player:
            cur.execute(
                "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                (user_id, username, full_name, 0)
            )
            conn.commit()
            create_referral_code_for_user(user_id)
            cur.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
            player = cur.fetchone()
        result = dict(player)
        # Check active game
        cur.execute("""
            SELECT g.id as game_id, g.stake, g.status
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.status IN ('waiting', 'running')
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
                return jsonify({'error': 'Phone number already registered'}), 400
            cur.execute("UPDATE players SET phone = %s WHERE user_id = %s", (phone, user_id))
        if language and language in ['en', 'am', 'om', 'ti']:
            cur.execute("UPDATE players SET language = %s WHERE user_id = %s", (language, user_id))
        if referral_code:
            cur.execute("SELECT referred_by FROM players WHERE user_id = %s", (user_id,))
            existing_ref = cur.fetchone()
            if not existing_ref or not existing_ref['referred_by']:
                cur.execute("SELECT user_id FROM referral_codes WHERE code = %s", (referral_code,))
                referrer = cur.fetchone()
                if referrer and referrer['user_id'] != user_id:
                    cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s", (referrer['user_id'], user_id))
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
        return jsonify({'success': True, 'message': 'Account reset.'})
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
        # Check if user is banned
        cur.execute("SELECT is_banned FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403

        # Check if a game is already running for this stake
        running_game = get_current_running_game(stake)
        if running_game:
            drawn = json.loads(running_game['drawn_balls'] or '[]')
            return jsonify({
                'game_in_progress': True,
                'game_id': running_game['id'],
                'stake': stake,
                'prize_pool': running_game['prize_pool'],
                'drawn_balls': drawn,
                'status': 'running',
                'message': 'A game is in progress. Wait for the next game.'
            })

        # Check balance
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Already in an active game?
        cur.execute("""
            SELECT g.id FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.status IN ('waiting', 'running')
        """, (user_id,))
        if cur.fetchone():
            return jsonify({'error': 'You are already in an active game'}), 400

        # Clean up stale waiting games (older than 30 sec, no cards)
        cur.execute("SELECT id, created_at FROM games WHERE stake = %s AND status = 'waiting' AND cancelled = 0", (stake,))
        for old in cur.fetchall():
            if (time.time() - old['created_at']) > 30:
                cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s", (old['id'],))
                if cur.fetchone()['cnt'] == 0:
                    cur.execute("DELETE FROM games WHERE id = %s", (old['id'],))
        conn.commit()

        # Find or create a waiting game
        cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' AND cancelled = 0 ORDER BY id DESC LIMIT 1", (stake,))
        game_row = cur.fetchone()
        if not game_row:
            cur.execute(
                "INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')",
                (stake, time.time())
            )
            conn.commit()
            cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' ORDER BY id DESC LIMIT 1", (stake,))
            game_row = cur.fetchone()
        game_id = game_row['id']

        # Deduct stake and add to prize pool
        cur.execute("UPDATE players SET balance = balance - %s, games_played = games_played + 1 WHERE user_id = %s", (stake, user_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()

        # Return game info
        cur.execute("SELECT prize_pool, status, created_at FROM games WHERE id = %s", (game_id,))
        ginfo = cur.fetchone()
        cur.execute("SELECT COUNT(DISTINCT user_id) as players FROM game_cards WHERE game_id = %s", (game_id,))
        players_cnt = cur.fetchone()['players']
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        countdown = max(0, 30 - int(time.time() - ginfo['created_at']))

        return jsonify({
            'game_in_progress': False,
            'game_id': game_id,
            'stake': stake,
            'prize_pool': ginfo['prize_pool'],
            'status': ginfo['status'],
            'players': players_cnt,
            'taken_cards': taken,
            'countdown': countdown
        })
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/pick_card', methods=['POST'])
def pick_card():
    data = request.json
    user_id = data.get('user_id')
    game_id = data.get('game_id')
    card_number = data.get('card_number')
    stake = data.get('stake')
    if not all([user_id, game_id, card_number, stake]):
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        # Start explicit transaction (PostgreSQL handles concurrency)
        cur.execute("BEGIN")
        cur.execute("SELECT status, stake FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game already started'}), 400
        if game['stake'] != stake:
            return jsonify({'error': f'Stake mismatch. Expected {game["stake"]}'}), 400

        # Check balance
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Card already taken?
        cur.execute("SELECT id FROM game_cards WHERE game_id = %s AND card_number = %s", (game_id, card_number))
        if cur.fetchone():
            return jsonify({'error': 'Card already taken'}), 400

        # Max 4 cards per player
        cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s AND user_id = %s", (game_id, user_id))
        if cur.fetchone()['cnt'] >= 4:
            return jsonify({'error': 'Maximum 4 cards per player'}), 400

        # Insert card
        cur.execute(
            "INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
            (game_id, user_id, card_number, json.dumps(generate_card()))
        )
        cur.execute("UPDATE players SET balance = balance - %s, games_played = games_played + 1 WHERE user_id = %s", (stake, user_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()

        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        new_bal = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': new_bal})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
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
        cur.execute("SELECT status, stake FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'waiting':
            return jsonify({'error': 'Game already started or not found'}), 400
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s AND user_id = %s", (game_id, user_id))
        cards = cur.fetchall()
        if not cards:
            return jsonify({'error': 'No cards found for this user'}), 404
        refund = game['stake'] * len(cards)
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, user_id))
        cur.execute("DELETE FROM game_cards WHERE game_id = %s AND user_id = %s", (game_id, user_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool - %s WHERE id = %s", (refund, game_id))
        conn.commit()
        # Cancel game if only bots remain
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id = %s", (game_id,))
        remaining = [row['user_id'] for row in cur.fetchall()]
        real_remaining = [uid for uid in remaining if uid > 0 and uid not in ADMIN_IDS]
        if not real_remaining:
            cur.execute("DELETE FROM game_cards WHERE game_id = %s", (game_id,))
            cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s", (time.time(), game_id))
            conn.commit()
            return jsonify({'success': True, 'message': 'Game cancelled (only bots left).'})
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        balance = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': balance})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/game_state/<int:game_id>')
def game_state(game_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        drawn = json.loads(game['drawn_balls'] or '[]')
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id = %s", (game_id,))
        players = len(cur.fetchall())
        winners_share = round(game['prize_pool'] * 0.80, 2)

        result = {
            'status': game['status'],
            'drawn_balls': drawn,
            'prize_pool': game['prize_pool'],
            'winners_share': winners_share,
            'players': players,
            'taken_cards': taken,
        }

        if game['status'] == 'finished' and game.get('cancelled') == 1:
            result['status'] = 'cancelled'
            result['cancelled_message'] = 'Not enough players. Game cancelled. Money refunded.'
            result['next_game_id'] = None
            return jsonify(result)

        if game['status'] == 'finished':
            winner_card_numbers = json.loads(game['winner_card_numbers'] or '[]')
            if winner_card_numbers:
                result['winner_card_numbers'] = winner_card_numbers
                result['winner_details'] = []
                for wcard in winner_card_numbers:
                    cur.execute("""
                        SELECT p.user_id, p.username, gc.card_number
                        FROM game_cards gc
                        JOIN players p ON p.user_id = gc.user_id
                        WHERE gc.game_id = %s AND gc.card_number = %s
                    """, (game_id, wcard))
                    winner = cur.fetchone()
                    if winner:
                        result['winner_details'].append(dict(winner))
            else:
                result['message'] = 'No winner this game.'

        # Next waiting game for same stake
        cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' AND id != %s ORDER BY id DESC LIMIT 1",
                    (game['stake'], game_id))
        next_game = cur.fetchone()
        result['next_game_id'] = next_game['id'] if next_game else None
        return jsonify(result)
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/my_cards/<int:game_id>')
def my_cards(game_id):
    user_id = request.args.get('user_id')
    if not is_valid_id(user_id):
        return jsonify({'error': 'Invalid user_id'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT card_number as card_index, card_data, marked_numbers
            FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        cards = [dict(row) for row in cur.fetchall()]
        # Convert card_data from JSON string to object for frontend convenience
        for card in cards:
            if 'card_data' in card and isinstance(card['card_data'], str):
                card['card_data'] = json.loads(card['card_data'])
        return jsonify({'cards': cards})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/deposit', methods=['POST'])
def deposit():
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    platform = data.get('platform')
    proof = data.get('proof')
    if not all([user_id, amount, platform, proof]):
        return jsonify({'error': 'Missing fields'}), 400
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except:
        return jsonify({'error': 'Invalid amount'}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM deposits WHERE tx_ref = %s", (proof,))
        if cur.fetchone():
            return jsonify({'error': 'Transaction reference already used'}), 400
        cur.execute(
            "INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at) VALUES (%s, %s, %s, %s, 'pending', %s)",
            (user_id, amount, platform, proof, time.time())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Deposit recorded. Awaiting admin approval.'})
    finally:
        cur.close()
        put_db(conn)

MIN_WITHDRAWAL = 50

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    method = data.get('method')
    account_no = data.get('account_no')
    if not all([user_id, amount, method, account_no]):
        return jsonify({'error': 'Missing fields'}), 400
    try:
        amount = float(amount)
        if amount < MIN_WITHDRAWAL:
            return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAWAL} ETB'}), 400
    except:
        return jsonify({'error': 'Invalid amount'}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        bal = cur.fetchone()
        if not bal or bal['balance'] < amount:
            return jsonify({'error': 'Insufficient balance'}), 400
        cur.execute(
            "INSERT INTO withdrawals (user_id, amount, method, account_no, status, created_at) VALUES (%s, %s, %s, %s, 'pending', %s)",
            (user_id, amount, method, account_no, time.time())
        )
        cur.execute("UPDATE players SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Withdrawal request submitted.'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT user_id, username, full_name, balance, total_won, wins
            FROM players
            WHERE user_id > 0
            ORDER BY total_won DESC
            LIMIT 20
        """)
        leaders = [dict(row) for row in cur.fetchall()]
        return jsonify(leaders)
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/recent_games/<int:user_id>')
def recent_games(user_id):
    if not is_valid_id(user_id):
        return jsonify({'error': 'Invalid user_id'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT g.id, g.stake, g.prize_pool, g.status, g.finished_at,
                           g.winner_card_numbers,
                           CASE WHEN g.winner_card_numbers != '[]' THEN 1 ELSE 0 END as won
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s
            ORDER BY g.finished_at DESC
            LIMIT 20
        """, (user_id,))
        games = [dict(row) for row in cur.fetchall()]
        return jsonify(games)
    finally:
        cur.close()
        put_db(conn)

# ---------- Settings endpoints (used by frontend) ----------
@app.route('/api/settings/telebirr_number')
def telebirr_number():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'telebirr_number'")
        row = cur.fetchone()
        return jsonify({'telebirr_number': row['value'] if row else '0929001000'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/cbe_number')
def cbe_number():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'cbe_number'")
        row = cur.fetchone()
        return jsonify({'cbe_number': row['value'] if row else '1000061737212'})
    finally:
        cur.close()
        put_db(conn)

# ---------- Admin Endpoints (simplified) ----------
@app.route('/admin/api/set_max_balls', methods=['POST'])
def set_max_balls():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    max_balls = data.get('max_balls')
    if not max_balls or not isinstance(max_balls, int) or max_balls < 10:
        return jsonify({'error': 'Invalid max_balls'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'max_balls_per_game'", (str(max_balls),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_bot_settings', methods=['POST'])
def update_bot_settings():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    try:
        for key in ['bot_enabled', 'bot_min_players', 'bot_max_players', 'bot_remove_excess', 'bot_addition_interval_seconds', 'bot_number_to_add']:
            if key in data:
                cur.execute("UPDATE settings SET value = %s WHERE key = %s", (str(data[key]), key))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/bot_count')
def bot_count():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        cnt = cur.fetchone()['cnt']
        return jsonify({'count': cnt})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/set_bot_count', methods=['POST'])
def set_bot_count():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    target = int(data.get('count', 0))
    if target < 0 or target > 50:
        return jsonify({'error': 'Count must be 0-50'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        current = cur.fetchone()['cnt']
        if target > current:
            cur.execute("SELECT MIN(user_id) FROM players WHERE user_id < 0")
            row = cur.fetchone()
            next_id = (row['min'] - 1) if row and row['min'] else -1
            for _ in range(target - current):
                cur.execute(
                    "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                    (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000)
                )
                next_id -= 1
        elif target < current:
            cur.execute("SELECT user_id FROM players WHERE user_id < 0 ORDER BY user_id ASC LIMIT %s", (current - target,))
            to_delete = [row['user_id'] for row in cur.fetchall()]
            for uid in to_delete:
                cur.execute("DELETE FROM players WHERE user_id = %s", (uid,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

# ---------- Notification routes ----------
@app.route('/api/notifications/latest')
def latest_notification():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT message, created_at FROM notifications ORDER BY created_at DESC LIMIT 1")
        notif = cur.fetchone()
        if notif:
            return jsonify({'message': notif['message'], 'created_at': notif['created_at']})
        return jsonify({})
    finally:
        cur.close()
        put_db(conn)

# ---------- Inquiry endpoint ----------
@app.route('/api/inquiry', methods=['POST'])
def inquiry():
    data = request.json
    user_id = data.get('user_id')
    subject = data.get('subject')
    message = data.get('message')
    if not all([user_id, subject, message]):
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO inquiries (user_id, subject, message, status, created_at) VALUES (%s, %s, %s, 'open', %s)",
            (user_id, subject, message, time.time())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Inquiry sent.'})
    finally:
        cur.close()
        put_db(conn)

# ---------- Referral stats endpoint ----------
@app.route('/api/referral_stats/<int:user_id>')
def referral_stats(user_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
        code_row = cur.fetchone()
        referral_code = code_row['code'] if code_row else None
        return jsonify({'referral_code': referral_code})
    finally:
        cur.close()
        put_db(conn)

if __name__ == '__main__':
    # Initialize database tables (required before first run)
    init_db()
    # Ensure at least some bots exist
    create_bot_players(20)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
