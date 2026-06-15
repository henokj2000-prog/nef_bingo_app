import sys
import os
import json
import hmac
import hashlib
import urllib.parse
import time
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.bingo_logic import generate_card
from database import (
    get_db, put_db, init_db, create_bot_players,
    create_referral_code_for_user, award_referral_bonus
)
from config import ADMIN_PASSWORD, ADMIN_IDS, BOT_TOKEN, WEB_APP_URL, GAME_START_DELAY_SECONDS

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)


# ========== Helpers ==========

def serialize_game(game):
    result = dict(game)
    for field in ['created_at', 'started_at', 'finished_at', 'last_draw_time', 'countdown_started_at']:
        if result.get(field) and hasattr(result[field], 'isoformat'):
            result[field] = result[field].isoformat()
    result['drawn_balls'] = json.loads(result.get('drawn_balls') or '[]')
    result['winner_card_numbers'] = json.loads(result.get('winner_card_numbers') or '[]')
    return result


def get_countdown_remaining(game):
    if not game.get('countdown_started_at'):
        return 0
    started = game['countdown_started_at']
    if isinstance(started, str):
        started = datetime.fromisoformat(started)
    elapsed = (datetime.utcnow() - started).total_seconds()
    return max(0, int(GAME_START_DELAY_SECONDS - elapsed))


def admin_auth(req):
    """Check admin password from query args or JSON body."""
    if req.args.get('password') == ADMIN_PASSWORD:
        return True
    if req.is_json and req.json and req.json.get('password') == ADMIN_PASSWORD:
        return True
    return False


# ========== Telegram initData verification ==========

def verify_telegram_init_data(init_data: str, bot_token: str):
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
    except Exception:
        return None
    received_hash = parsed.pop('hash', None)
    if not received_hash:
        return None
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if computed_hash == received_hash:
        return parsed
    return None


# ========== Auth decorator ==========

def require_telegram_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('password') == ADMIN_PASSWORD:
            g.telegram_user_id = int(request.args.get('user_id', 0))
            return f(*args, **kwargs)
        if os.environ.get('FLASK_ENV') == 'development':
            g.telegram_user_id = 99999
            return f(*args, **kwargs)
        init_data = request.headers.get('X-Telegram-Init-Data')
        if not init_data:
            return jsonify({'error': 'Missing Telegram init data'}), 401
        data = verify_telegram_init_data(init_data, BOT_TOKEN)
        if not data:
            return jsonify({'error': 'Invalid Telegram init data'}), 401
        try:
            user_data = json.loads(data.get('user', '{}'))
            g.telegram_user_id = int(user_data['id'])
        except (KeyError, ValueError, json.JSONDecodeError):
            return jsonify({'error': 'Invalid user data'}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.teardown_appcontext
def close_db_connection(exception=None):
    if hasattr(g, 'db_conn'):
        put_db(g.db_conn)


# ========== Routes ==========

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/admin')
def admin():
    return send_from_directory('templates', 'admin.html')


@app.route('/api/player/<int:user_id>')
@require_telegram_auth
def get_player(user_id):
    user_id = g.telegram_user_id
    username = request.args.get('username', 'user')
    full_name = request.args.get('full_name', 'Player')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
    except Exception as e:
        print(f"Error in get_player: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/update_profile', methods=['POST'])
@require_telegram_auth
def update_profile():
    user_id = g.telegram_user_id
    data = request.json
    phone = data.get('phone', '').strip()
    language = data.get('language', '')
    referral_code = data.get('referral_code', '').strip()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
                    cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s",
                                (referrer['user_id'], user_id))
                    award_referral_bonus(referrer['user_id'], user_id)
        conn.commit()
        create_referral_code_for_user(user_id)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_profile: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/reset_player', methods=['POST'])
@require_telegram_auth
def reset_player():
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET phone = NULL, language = 'en' WHERE user_id = %s", (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Account reset.'})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/join_game', methods=['POST'])
@require_telegram_auth
def join_game():
    user_id = g.telegram_user_id
    data = request.json
    stake = data.get('stake')
    if not user_id or not stake:
        return jsonify({'error': 'stake is required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT is_banned, balance FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403

        # Already in a waiting game?
        cur.execute("""
            SELECT g.id FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.stake = %s AND g.status = 'waiting' AND g.cancelled = 0
            ORDER BY g.id DESC LIMIT 1
        """, (user_id, stake))
        existing = cur.fetchone()
        if existing:
            cur.execute("SELECT * FROM games WHERE id = %s", (existing['id'],))
            game = cur.fetchone()
            return jsonify({
                'success': True,
                'game_id': existing['id'],
                'stake': stake,
                'countdown_remaining': get_countdown_remaining(game),
                'already_joined': True
            })

        # Running game? (spectator)
        cur.execute("""
            SELECT id, drawn_balls, prize_pool FROM games
            WHERE stake = %s AND status = 'running'
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        running_game = cur.fetchone()
        if running_game:
            return jsonify({
                'game_in_progress': True,
                'game_id': running_game['id'],
                'stake': stake,
                'drawn_balls': json.loads(running_game['drawn_balls'] or '[]'),
                'prize_pool': running_game['prize_pool']
            })

        # Find or create waiting game
        cur.execute("""
            SELECT id, countdown_started_at FROM games
            WHERE stake = %s AND status = 'waiting' AND cancelled = 0
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        waiting_game = cur.fetchone()
        now = datetime.utcnow()
        if waiting_game:
            game_id = waiting_game['id']
            cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
            game = cur.fetchone()
        else:
            cur.execute("""
                INSERT INTO games (stake, status, created_at, countdown_started_at)
                VALUES (%s, 'waiting', %s, %s) RETURNING id
            """, (stake, now, now))
            game_id = cur.fetchone()['id']
            conn.commit()
            cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
            game = cur.fetchone()

        return jsonify({
            'success': True,
            'game_id': game_id,
            'stake': stake,
            'countdown_remaining': get_countdown_remaining(game)
        })
    except Exception as e:
        conn.rollback()
        print(f"Error in join_game: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/pick_card', methods=['POST'])
@require_telegram_auth
def pick_card():
    """Player picks a card number during countdown. Deducts stake per card."""
    user_id = g.telegram_user_id
    data = request.json
    game_id = data.get('game_id')
    card_number = data.get('card_number')
    if not game_id or not card_number:
        return jsonify({'error': 'game_id and card_number required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Game has already started or finished'}), 400

        stake = game['stake']

        cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s AND user_id = %s",
                    (game_id, user_id))
        if cur.fetchone()['cnt'] >= 4:
            return jsonify({'error': 'Maximum 4 cards per game'}), 400

        cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND card_number = %s",
                    (game_id, card_number))
        existing = cur.fetchone()
        if existing:
            if existing['user_id'] == user_id:
                return jsonify({'error': 'You already have this card'}), 400
            return jsonify({'error': 'Card already taken'}), 400

        cur.execute("SELECT balance, is_banned FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        if player['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403
        if player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        cur.execute("UPDATE players SET balance = balance - %s WHERE user_id = %s", (stake, user_id))
        card = generate_card()
        cur.execute("""
            INSERT INTO game_cards (game_id, user_id, card_number, card, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (game_id, user_id, card_number, json.dumps(card), datetime.utcnow()))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()

        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        new_balance = cur.fetchone()['balance']
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [r['card_number'] for r in cur.fetchall() if r['card_number']]

        return jsonify({'success': True, 'balance': new_balance, 'card_number': card_number, 'taken_cards': taken})
    except Exception as e:
        conn.rollback()
        print(f"Error in pick_card: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/game_state/<int:game_id>')
def get_game_state(game_id):
    """Primary endpoint polled by frontend during gameplay."""
    user_id = request.args.get('user_id', type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)

        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        result['taken_cards'] = [r['card_number'] for r in cur.fetchall() if r['card_number']]

        cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
        result['players'] = cur.fetchone()['cnt']

        cur.execute("SELECT value FROM settings WHERE key = 'owner_cut_percent'")
        row = cur.fetchone()
        owner_cut = int(row['value']) if row else 20
        result['total_winners_prize'] = round((result.get('prize_pool') or 0) * (100 - owner_cut) / 100, 2)

        if user_id:
            cur.execute("""
                SELECT card, marked_numbers, card_number FROM game_cards
                WHERE game_id = %s AND user_id = %s
            """, (game_id, user_id))
            my_cards = []
            for pc in cur.fetchall():
                card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
                marked = pc['marked_numbers']
                if isinstance(marked, str):
                    marked = json.loads(marked or '[]')
                my_cards.append({'card_number': pc['card_number'], 'card': card, 'marked_numbers': marked or []})
            result['my_cards'] = my_cards
        else:
            result['my_cards'] = []

        if result['status'] == 'finished':
            winner_details = []
            for card_num in result.get('winner_card_numbers', []):
                cur.execute("""
                    SELECT p.username, p.full_name, gc.card_number
                    FROM game_cards gc JOIN players p ON p.user_id = gc.user_id
                    WHERE gc.game_id = %s AND gc.card_number = %s
                """, (game_id, card_num))
                w = cur.fetchone()
                if w:
                    winner_details.append({
                        'username': w['full_name'] or w['username'] or 'Player',
                        'card_number': w['card_number']
                    })
            result['winner_details'] = winner_details

        return jsonify(result)
    except Exception as e:
        print(f"Error in get_game_state: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/my_cards/<int:game_id>')
def get_my_cards(game_id):
    user_id = request.args.get('user_id', type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT card, marked_numbers, card_number FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        cards = []
        for pc in cur.fetchall():
            card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
            marked = pc['marked_numbers']
            if isinstance(marked, str):
                marked = json.loads(marked or '[]')
            cards.append({'card_number': pc['card_number'], 'card': card, 'marked_numbers': marked or []})
        return jsonify({'cards': cards})
    except Exception as e:
        print(f"Error in get_my_cards: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/countdown/<int:game_id>')
def get_countdown(game_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT status, countdown_started_at FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'active': False, 'remaining_seconds': 0})
        remaining = get_countdown_remaining(game) if game['status'] == 'waiting' else 0
        return jsonify({'active': remaining > 0, 'remaining_seconds': remaining})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/select_cards/<int:game_id>', methods=['POST'])
@require_telegram_auth
def select_cards(game_id):
    """Mark a called ball on a card."""
    user_id = g.telegram_user_id
    data = request.json
    ball = data.get('ball')
    card_number = data.get('card_number')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT marked_numbers FROM game_cards
            WHERE game_id = %s AND user_id = %s AND card_number = %s
        """, (game_id, user_id, card_number))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Card not found'}), 404
        marked = json.loads(row['marked_numbers'] or '[]') if isinstance(row['marked_numbers'], str) else (row['marked_numbers'] or [])
        if ball and ball not in marked:
            marked.append(ball)
        cur.execute("""
            UPDATE game_cards SET marked_numbers = %s
            WHERE game_id = %s AND user_id = %s AND card_number = %s
        """, (json.dumps(marked), game_id, user_id, card_number))
        conn.commit()
        return jsonify({'success': True, 'marked_numbers': marked})
    except Exception as e:
        print(f"Error in select_cards: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/withdraw_from_game', methods=['POST'])
@require_telegram_auth
def withdraw_from_game():
    """Leave a waiting game and get refunded."""
    user_id = g.telegram_user_id
    data = request.json
    game_id = data.get('game_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT status, stake FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            return jsonify({'error': 'Cannot leave a game that has already started'}), 400
        stake = game['stake']
        cur.execute("SELECT COUNT(*) as cnt FROM game_cards WHERE game_id = %s AND user_id = %s",
                    (game_id, user_id))
        card_count = cur.fetchone()['cnt']
        if card_count == 0:
            return jsonify({'error': 'You are not in this game'}), 400
        refund = stake * card_count
        cur.execute("DELETE FROM game_cards WHERE game_id = %s AND user_id = %s", (game_id, user_id))
        cur.execute("UPDATE games SET prize_pool = GREATEST(0, prize_pool - %s) WHERE id = %s",
                    (refund, game_id))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, user_id))
        conn.commit()
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        new_balance = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': new_balance, 'message': f'Refunded {refund} ETB'})
    except Exception as e:
        conn.rollback()
        print(f"Error in withdraw_from_game: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/game/<int:game_id>')
@require_telegram_auth
def get_game(game_id):
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        cur.execute("""
            SELECT card, marked_numbers, card_number FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)
        result['my_cards'] = []
        for pc in cur.fetchall():
            card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
            marked = pc['marked_numbers']
            if isinstance(marked, str):
                marked = json.loads(marked or '[]')
            result['my_cards'].append({'card_number': pc['card_number'], 'card': card, 'marked_numbers': marked or []})
        return jsonify(result)
    except Exception as e:
        print(f"Error in get_game: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/deposit', methods=['POST'])
@require_telegram_auth
def deposit():
    user_id = g.telegram_user_id
    data = request.json
    amount = float(data.get('amount', 0))
    platform = data.get('platform', '')
    proof = data.get('proof', '').strip()
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    if not proof:
        return jsonify({'error': 'Proof required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at)
            VALUES (%s, %s, %s, %s, 'pending', %s)
        """, (user_id, amount, platform, proof, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': 'Deposit submitted for review'})
    except Exception as e:
        conn.rollback()
        print(f"Error in deposit: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/withdraw', methods=['POST'])
@require_telegram_auth
def withdraw():
    user_id = g.telegram_user_id
    data = request.json
    amount = float(data.get('amount', 0))
    method = data.get('method', '')
    account_no = data.get('account_no', '').strip()
    if amount < 50:
        return jsonify({'error': 'Minimum withdrawal is 50 ETB'}), 400
    if not account_no:
        return jsonify({'error': 'Account number required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < amount:
            return jsonify({'error': 'Insufficient balance'}), 400
        cur.execute("UPDATE players SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
        cur.execute("""
            INSERT INTO withdrawals (user_id, amount, platform, account_no, status, created_at)
            VALUES (%s, %s, %s, %s, 'pending', %s)
        """, (user_id, amount, method, account_no, time.time()))
        conn.commit()
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        new_balance = cur.fetchone()['balance']
        return jsonify({'success': True, 'balance': new_balance, 'message': 'Withdrawal request submitted'})
    except Exception as e:
        conn.rollback()
        print(f"Error in withdraw: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/notifications/latest')
def latest_notification():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT message, created_at FROM notifications ORDER BY created_at DESC LIMIT 1")
        notif = cur.fetchone()
        if notif:
            created = notif['created_at']
            if hasattr(created, 'isoformat'):
                created = created.isoformat()
            return jsonify({'message': notif['message'], 'created_at': created})
        return jsonify({})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/inquiry', methods=['POST'])
@require_telegram_auth
def inquiry():
    user_id = g.telegram_user_id
    data = request.json
    subject = data.get('subject')
    message = data.get('message')
    if not all([subject, message]):
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # created_at is real (unix float) in inquiries table
        cur.execute(
            "INSERT INTO inquiries (user_id, subject, message, status, created_at) VALUES (%s, %s, %s, 'open', %s)",
            (user_id, subject, message, time.time())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Inquiry sent.'})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/referral_stats/<int:user_id>')
@require_telegram_auth
def referral_stats(user_id):
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
        code_row = cur.fetchone()
        return jsonify({'referral_code': code_row['code'] if code_row else None})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/leaderboard')
def leaderboard():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT user_id, username, full_name, balance, total_won, wins
            FROM players WHERE user_id > 0
            ORDER BY total_won DESC LIMIT 50
        """)
        return jsonify([dict(p) for p in cur.fetchall()])
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/recent_games/<int:user_id>')
@require_telegram_auth
def recent_games(user_id):
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT DISTINCT g.* FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s ORDER BY g.id DESC LIMIT 10
        """, (user_id,))
        return jsonify([serialize_game(g) for g in cur.fetchall()])
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/settings/stakes')
def get_stakes():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'allowed_stakes'")
        row = cur.fetchone()
        return jsonify({'stakes': json.loads(row['value']) if row else [10, 20, 50, 100]})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/settings/<string:key>')
def get_setting(key):
    """Generic settings — covers telebirr_number, cbe_number, etc."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        if row:
            return jsonify({'key': key, 'value': row['value']})
        return jsonify({'error': 'Setting not found'}), 404
    finally:
        cur.close()
        put_db(conn)


# ========== Admin Routes ==========

@app.route('/admin/api/overview')
def admin_overview():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id > 0")
        total_players = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) as cnt FROM games WHERE status = 'running'")
        active_games = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) as cnt FROM deposits WHERE status = 'pending'")
        pending_deposits = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) as cnt FROM withdrawals WHERE status = 'pending'")
        pending_withdrawals = cur.fetchone()['cnt']
        cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM deposits WHERE status = 'approved'")
        total_deposited = cur.fetchone()['total']
        cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM withdrawals WHERE status = 'approved'")
        total_withdrawn = cur.fetchone()['total']
        cur.execute("SELECT COALESCE(SUM(balance), 0) as total FROM players WHERE user_id > 0")
        total_balance = cur.fetchone()['total']
        cur.execute("SELECT COUNT(*) as cnt FROM inquiries WHERE status = 'open'")
        open_inquiries = cur.fetchone()['cnt']
        return jsonify({
            'total_players': total_players,
            'active_games': active_games,
            'pending_deposits': pending_deposits,
            'pending_withdrawals': pending_withdrawals,
            'total_deposited': round(float(total_deposited), 2),
            'total_withdrawn': round(float(total_withdrawn), 2),
            'total_balance': round(float(total_balance), 2),
            'open_inquiries': open_inquiries
        })
    except Exception as e:
        print(f"Error in admin_overview: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/players')
def admin_players():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT user_id, username, full_name, phone, balance,
                   wins, total_won, is_banned, language
            FROM players WHERE user_id > 0
            ORDER BY user_id DESC LIMIT 100
        """)
        return jsonify([dict(p) for p in cur.fetchall()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/ban_player', methods=['POST'])
def admin_ban_player():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    user_id = data.get('user_id')
    ban = data.get('ban', True)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET is_banned = %s WHERE user_id = %s", (ban, user_id))
        conn.commit()
        return jsonify({'success': True, 'message': f"Player {'banned' if ban else 'unbanned'}"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/deposits')
def admin_deposits():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT d.id, d.user_id, d.amount, d.platform, d.tx_ref,
                   d.status, d.created_at,
                   p.username, p.full_name, p.phone
            FROM deposits d
            LEFT JOIN players p ON p.user_id = d.user_id
            ORDER BY d.id DESC LIMIT 100
        """)
        result = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                try:
                    row['created_at'] = datetime.utcfromtimestamp(float(row['created_at'])).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass
            result.append(row)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/approve_deposit', methods=['POST'])
def admin_approve_deposit():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    deposit_id = data.get('deposit_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM deposits WHERE id = %s", (deposit_id,))
        dep = cur.fetchone()
        if not dep:
            return jsonify({'error': 'Deposit not found'}), 404
        if dep['status'] != 'pending':
            return jsonify({'error': 'Deposit already processed'}), 400
        cur.execute("UPDATE deposits SET status = 'approved' WHERE id = %s", (deposit_id,))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s",
                    (dep['amount'], dep['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f"{dep['amount']} ETB credited to user {dep['user_id']}"})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/reject_deposit', methods=['POST'])
def admin_reject_deposit():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    deposit_id = data.get('deposit_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE deposits SET status = 'rejected' WHERE id = %s AND status = 'pending'",
                    (deposit_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Deposit rejected'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/withdrawals')
def admin_withdrawals():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT w.id, w.user_id, w.amount, w.platform, w.account_no,
                   w.status, w.created_at,
                   p.username, p.full_name, p.phone
            FROM withdrawals w
            LEFT JOIN players p ON p.user_id = w.user_id
            ORDER BY w.id DESC LIMIT 100
        """)
        result = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                try:
                    row['created_at'] = datetime.utcfromtimestamp(float(row['created_at'])).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass
            result.append(row)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/approve_withdrawal', methods=['POST'])
def admin_approve_withdrawal():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    withdrawal_id = data.get('withdrawal_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM withdrawals WHERE id = %s", (withdrawal_id,))
        wd = cur.fetchone()
        if not wd:
            return jsonify({'error': 'Withdrawal not found'}), 404
        if wd['status'] != 'pending':
            return jsonify({'error': 'Withdrawal already processed'}), 400
        cur.execute("UPDATE withdrawals SET status = 'approved' WHERE id = %s", (withdrawal_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f"Withdrawal of {wd['amount']} ETB approved"})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/reject_withdrawal', methods=['POST'])
def admin_reject_withdrawal():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    withdrawal_id = data.get('withdrawal_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM withdrawals WHERE id = %s", (withdrawal_id,))
        wd = cur.fetchone()
        if not wd:
            return jsonify({'error': 'Withdrawal not found'}), 404
        if wd['status'] != 'pending':
            return jsonify({'error': 'Withdrawal already processed'}), 400
        cur.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = %s", (withdrawal_id,))
        # Refund the player
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s",
                    (wd['amount'], wd['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': 'Withdrawal rejected and balance refunded'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/active_games')
def admin_active_games():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT g.id, g.stake, g.status, g.prize_pool,
                   g.created_at, g.started_at,
                   COUNT(DISTINCT gc.user_id) as player_count
            FROM games g
            LEFT JOIN game_cards gc ON gc.game_id = g.id
            WHERE g.status IN ('waiting', 'running')
            GROUP BY g.id
            ORDER BY g.id DESC
        """)
        games = []
        for g in cur.fetchall():
            row = dict(g)
            for field in ['created_at', 'started_at']:
                if row.get(field) and hasattr(row[field], 'isoformat'):
                    row[field] = row[field].isoformat()
            games.append(row)
        return jsonify(games)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/force_finish', methods=['POST'])
def admin_force_finish():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    game_id = data.get('game_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT status, stake FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404
        cur.execute("""
            UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s
            WHERE id = %s
        """, (datetime.utcnow(), game_id))
        cur.execute("""
            UPDATE players SET balance = balance + %s * (
                SELECT COUNT(*) FROM game_cards
                WHERE game_id = %s AND user_id = players.user_id
            )
            WHERE user_id IN (SELECT user_id FROM game_cards WHERE game_id = %s)
        """, (game['stake'], game_id, game_id))
        conn.commit()
        return jsonify({'success': True, 'message': f'Game #{game_id} force finished and players refunded'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/inquiries')
def admin_inquiries():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT i.id, i.user_id, i.subject, i.message, i.status, i.created_at,
                   p.username, p.full_name, p.phone
            FROM inquiries i
            LEFT JOIN players p ON p.user_id = i.user_id
            ORDER BY i.id DESC LIMIT 100
        """)
        result = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                try:
                    row['created_at'] = datetime.utcfromtimestamp(float(row['created_at'])).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pass
            result.append(row)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/mark_inquiry_read', methods=['POST'])
def admin_mark_inquiry_read():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    inquiry_id = data.get('inquiry_id')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE inquiries SET status = 'resolved' WHERE id = %s", (inquiry_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/get_user_by_phone', methods=['POST'])
def admin_get_user_by_phone():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    phone = data.get('phone', '').strip()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT user_id, username, full_name, phone, balance, wins, total_won, is_banned
            FROM players WHERE phone = %s
        """, (phone,))
        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        return jsonify(dict(player))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/give_bonus_by_phone', methods=['POST'])
def admin_give_bonus_by_phone():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    phone = data.get('phone', '').strip()
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than 0'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id, full_name FROM players WHERE phone = %s", (phone,))
        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s",
                    (amount, player['user_id']))
        conn.commit()
        return jsonify({'success': True, 'message': f"{amount} ETB added to {player['full_name']}"})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/give_bonus_all', methods=['POST'])
def admin_give_bonus_all():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than 0'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id > 0", (amount,))
        affected = cur.rowcount
        conn.commit()
        return jsonify({'success': True, 'message': f"{amount} ETB added to {affected} players"})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/send_notification', methods=['POST'])
def admin_send_notification():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO notifications (message, created_at) VALUES (%s, %s)",
            (message, time.time())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Notification sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/set_max_balls', methods=['POST'])
def admin_set_max_balls():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    max_balls = int(data.get('max_balls', 75))
    if max_balls < 10 or max_balls > 90:
        return jsonify({'error': 'Max balls must be between 10 and 90'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO settings (key, value) VALUES ('max_balls_per_game', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (str(max_balls), str(max_balls)))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/update_bot_settings', methods=['POST'])
def admin_update_bot_settings():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        for key in ['bot_enabled', 'bot_min_players', 'bot_target_real_players', 'bot_remove_excess',
                    'bot_addition_interval_seconds', 'bot_number_to_add']:
            if key in data:
                cur.execute("UPDATE settings SET value = %s WHERE key = %s", (str(data[key]), key))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/bot_count')
def admin_bot_count():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        return jsonify({'count': cur.fetchone()['cnt']})
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/set_bot_count', methods=['POST'])
def admin_set_bot_count():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    target = int(data.get('count', 0))
    if target < 0 or target > 50:
        return jsonify({'error': 'Count must be 0-50'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        current = cur.fetchone()['cnt']
        if target > current:
            cur.execute("SELECT MIN(user_id) as min FROM players WHERE user_id < 0")
            row = cur.fetchone()
            next_id = (row['min'] - 1) if row and row['min'] else -1
            for _ in range(target - current):
                cur.execute(
                    "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                    (next_id, f"bot_{abs(next_id)}", f"Bot {abs(next_id)}", 1000)
                )
                next_id -= 1
        elif target < current:
            cur.execute("SELECT user_id FROM players WHERE user_id < 0 ORDER BY user_id ASC LIMIT %s",
                        (current - target,))
            for row in cur.fetchall():
                cur.execute("DELETE FROM players WHERE user_id = %s", (row['user_id'],))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)


# ========== Telegram Webhook ==========

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=5)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                INSERT INTO players (user_id, username, full_name, balance, bot_started)
                VALUES (%s, %s, %s, 0, TRUE)
                ON CONFLICT (user_id) DO UPDATE SET bot_started = TRUE
            """, (
                chat_id,
                update['message']['from'].get('username', 'user'),
                update['message']['from'].get('first_name', 'Player')
            ))
            conn.commit()
        except Exception as e:
            print(f"Error setting bot_started: {e}")
        finally:
            cur.close()
            put_db(conn)
        if text == '/start':
            send_telegram_message(chat_id,
                f"🎯 Welcome to Nef Bingo!\n\nPlay here: {WEB_APP_URL}\n\nUse /balance to check your balance.")
        elif text == '/balance':
            send_telegram_message(chat_id, "Please log in to the game first to check your balance.")
        else:
            send_telegram_message(chat_id, "Send /start to get the game link.")
    return 'OK', 200


# ========== Start ==========

if __name__ == '__main__':
    init_db()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        if cur.fetchone()['cnt'] == 0:
            create_bot_players(20)
    finally:
        cur.close()
        put_db(conn)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
