import sys
import os
import json
import time
import hmac
import hashlib
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

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
    """Convert a game row to JSON-safe dict."""
    result = dict(game)
    for field in ['created_at', 'started_at', 'finished_at', 'last_draw_time', 'countdown_started_at']:
        if result.get(field) and hasattr(result[field], 'isoformat'):
            result[field] = result[field].isoformat()
    result['drawn_balls'] = json.loads(result.get('drawn_balls') or '[]')
    result['winner_card_numbers'] = json.loads(result.get('winner_card_numbers') or '[]')
    return result


def get_countdown_remaining(game):
    """Compute remaining countdown seconds from DB countdown_started_at."""
    if not game.get('countdown_started_at'):
        return 0
    started = game['countdown_started_at']
    if isinstance(started, str):
        started = datetime.fromisoformat(started)
    elapsed = (datetime.utcnow() - started).total_seconds()
    return max(0, int(GAME_START_DELAY_SECONDS - elapsed))


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
        return jsonify({'error': 'user_id and stake are required'}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Check if user is banned
        cur.execute("SELECT is_banned FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403

        # Check balance
        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Check if already in a waiting/running game of same stake
        cur.execute("""
            SELECT g.id, g.status FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.stake = %s AND g.status IN ('waiting', 'running')
            ORDER BY g.id DESC LIMIT 1
        """, (user_id, stake))
        existing = cur.fetchone()
        if existing:
            cur.execute("SELECT * FROM games WHERE id = %s", (existing['id'],))
            game = cur.fetchone()
            remaining = get_countdown_remaining(game)
            return jsonify({
                'success': True,
                'game_id': existing['id'],
                'stake': stake,
                'countdown_remaining': remaining,
                'already_joined': True
            })

        # Check for a running game (spectator mode)
        cur.execute("""
            SELECT id, status, drawn_balls, prize_pool
            FROM games
            WHERE stake = %s AND status = 'running'
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        running_game = cur.fetchone()
        if running_game:
            drawn = json.loads(running_game['drawn_balls'] or '[]')
            return jsonify({
                'game_in_progress': True,
                'game_id': running_game['id'],
                'stake': stake,
                'drawn_balls': drawn,
                'prize_pool': running_game['prize_pool']
            })

        # Find or create waiting game
        cur.execute("""
            SELECT id, stake, status, countdown_started_at
            FROM games
            WHERE stake = %s AND status = 'waiting' AND cancelled = 0
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        waiting_game = cur.fetchone()

        now = datetime.utcnow()

        if waiting_game:
            game_id = waiting_game['id']
        else:
            # Create new game
            cur.execute("""
                INSERT INTO games (stake, status, created_at, countdown_started_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (stake, 'waiting', now, now))
            game_id = cur.fetchone()['id']

        # Deduct stake from balance
        cur.execute("UPDATE players SET balance = balance - %s WHERE user_id = %s", (stake, user_id))

        # Add player card and update prize pool
        card = generate_card()
        cur.execute("""
            INSERT INTO game_cards (game_id, user_id, card, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (game_id, user_id, json.dumps(card), now))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))

        conn.commit()

        # Get updated game for countdown
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        remaining = get_countdown_remaining(game)

        return jsonify({
            'success': True,
            'game_id': game_id,
            'stake': stake,
            'countdown_remaining': remaining
        })
    except Exception as e:
        conn.rollback()
        print(f"Error in join_game: {e}")
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

        # Get all player cards for this game (for this user)
        if user_id:
            cur.execute("""
                SELECT card, marked_numbers, card_number
                FROM game_cards
                WHERE game_id = %s AND user_id = %s
            """, (game_id, user_id))
            rows = cur.fetchall()
            my_cards = []
            for pc in rows:
                card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
                marked = pc['marked_numbers']
                if isinstance(marked, str):
                    marked = json.loads(marked or '[]')
                my_cards.append({
                    'card_number': pc['card_number'],
                    'card': card,
                    'marked_numbers': marked or []
                })
            result['my_cards'] = my_cards
        else:
            result['my_cards'] = []

        # Count players
        cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s", (game_id,))
        result['player_count'] = cur.fetchone()['cnt']

        return jsonify(result)
    except Exception as e:
        print(f"Error in get_game_state: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/my_cards/<int:game_id>')
def get_my_cards(game_id):
    """Return user's cards for a game."""
    user_id = request.args.get('user_id', type=int)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT card, marked_numbers, card_number
            FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        rows = cur.fetchall()
        cards = []
        for pc in rows:
            card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
            marked = pc['marked_numbers']
            if isinstance(marked, str):
                marked = json.loads(marked or '[]')
            cards.append({
                'card_number': pc['card_number'],
                'card': card,
                'marked_numbers': marked or []
            })
        return jsonify({'cards': cards})
    except Exception as e:
        print(f"Error in get_my_cards: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/countdown/<int:game_id>')
def get_countdown(game_id):
    """Get current countdown time for a game (DB-based, no in-memory state)."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT status, countdown_started_at FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'active': False, 'remaining_seconds': 0})
        remaining = get_countdown_remaining(game) if game['status'] == 'waiting' else 0
        return jsonify({
            'active': remaining > 0,
            'remaining_seconds': remaining
        })
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/select_cards/<int:game_id>', methods=['POST'])
@require_telegram_auth
def select_cards(game_id):
    """Player marks numbers on their card (mark a called ball)."""
    user_id = g.telegram_user_id
    data = request.json
    ball = data.get('ball')  # e.g. "B-5"
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


@app.route('/api/game/<int:game_id>')
@require_telegram_auth
def get_game(game_id):
    """Get game details (legacy route)."""
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
        player_cards = cur.fetchall()

        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)
        result['my_cards'] = []
        for pc in player_cards:
            card = pc['card'] if isinstance(pc['card'], (dict, list)) else json.loads(pc['card'] or '[]')
            marked = pc['marked_numbers']
            if isinstance(marked, str):
                marked = json.loads(marked or '[]')
            result['my_cards'].append({
                'card_number': pc['card_number'],
                'card': card,
                'marked_numbers': marked or []
            })

        return jsonify(result)
    except Exception as e:
        print(f"Error in get_game: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/update_bot_settings', methods=['POST'])
def admin_update_bot_settings():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401

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
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        cnt = cur.fetchone()['cnt']
        return jsonify({'count': cnt})
    finally:
        cur.close()
        put_db(conn)


@app.route('/admin/api/set_bot_count', methods=['POST'])
def admin_set_bot_count():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
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
            to_delete = [row['user_id'] for row in cur.fetchall()]
            for uid in to_delete:
                cur.execute("DELETE FROM players WHERE user_id = %s", (uid,))
        conn.commit()
        return jsonify({'success': True})
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
    if not all([user_id, subject, message]):
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO inquiries (user_id, subject, message, status, created_at) VALUES (%s, %s, %s, 'open', %s)",
            (user_id, subject, message, datetime.utcnow())
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
        referral_code = code_row['code'] if code_row else None
        return jsonify({'referral_code': referral_code})
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
            FROM players
            WHERE user_id > 0
            ORDER BY total_won DESC
            LIMIT 50
        """)
        players = cur.fetchall()
        return jsonify([dict(p) for p in players])
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
            WHERE gc.user_id = %s
            ORDER BY g.id DESC
            LIMIT 10
        """, (user_id,))
        games = cur.fetchall()
        return jsonify([serialize_game(g) for g in games])
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
        if row:
            stakes = json.loads(row['value'])
            return jsonify({'stakes': stakes})
        return jsonify({'stakes': [10, 20, 50, 100]})
    finally:
        cur.close()
        put_db(conn)


@app.route('/api/settings/<string:key>')
def get_setting(key):
    """Generic settings endpoint — covers telebirr_number, cbe_number, etc."""
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
            send_telegram_message(chat_id,
                "Please log in to the game first, then we can link your Telegram account.")
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
        bot_count = cur.fetchone()['cnt']
        if bot_count == 0:
            create_bot_players(20)
    finally:
        cur.close()
        put_db(conn)

    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
