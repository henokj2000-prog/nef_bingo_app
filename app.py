import sys
import os
import json
import time
import random
import hmac
import hashlib
import urllib.parse
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g, render_template
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.bingo_logic import generate_card
from database import (
    get_db, put_db, init_db, create_bot_players,
    create_referral_code_for_user, award_referral_bonus, add_bot_to_game
)
from config import ADMIN_PASSWORD, ADMIN_IDS, BOT_TOKEN, WEB_APP_URL

app = Flask(__name__, static_folder='static', template_folder='templates')

# ---------- Telegram initData verification ----------
def verify_telegram_init_data(init_data: str, bot_token: str):
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
    except:
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

# ---------- Auth decorator ----------
def require_telegram_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('password') == ADMIN_PASSWORD:
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

# ---------- Helper ----------
def is_valid_id(id_val):
    try:
        return int(id_val) > 0
    except (TypeError, ValueError):
        return False

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
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

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
                    cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s", (referrer['user_id'], user_id))
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
        cur.execute("SELECT is_banned FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403

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
                'prize_pool': running_game['prize_pool'],
                'drawn_balls': drawn,
                'status': 'running',
                'message': 'A game is in progress. Watch the current game.'
            })

        cur.execute("SELECT balance FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        cur.execute("""
            SELECT g.id FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s AND g.status IN ('waiting', 'running')
        """, (user_id,))
        if cur.fetchone():
            return jsonify({'error': 'You are already in an active game'}), 400

        # Find or create a VALID waiting game (countdown not expired)
        cur.execute("""
            SELECT id FROM games
            WHERE stake = %s AND status = 'waiting' AND cancelled = 0
              AND created_at + 30 > %s
            ORDER BY id DESC LIMIT 1
        """, (stake, time.time()))
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

        # FALLBACK: if the selected game is already expired, delete it and create new
        cur.execute("SELECT created_at FROM games WHERE id = %s", (game_id,))
        row = cur.fetchone()
        if row and row['created_at'] + 30 <= time.time():
            cur.execute("DELETE FROM games WHERE id = %s", (game_id,))
            conn.commit()
            cur.execute(
                "INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')",
                (stake, time.time())
            )
            conn.commit()
            cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' ORDER BY id DESC LIMIT 1", (stake,))
            game_row = cur.fetchone()
            game_id = game_row['id']

        cur.execute("SELECT prize_pool, status, created_at FROM games WHERE id = %s", (game_id,))
        ginfo = cur.fetchone()
        created_at = ginfo['created_at']
        if created_at > time.time():
            cur.execute("UPDATE games SET created_at = %s WHERE id = %s", (time.time(), game_id))
            conn.commit()
            created_at = time.time()
        countdown = max(0, min(30, 30 - int(time.time() - created_at)))

        cur.execute("SELECT COUNT(DISTINCT user_id) as players FROM game_cards WHERE game_id = %s", (game_id,))
        players_cnt = cur.fetchone()['players']
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]

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
@require_telegram_auth
def pick_card():
    user_id = g.telegram_user_id
    data = request.json
    game_id = data.get('game_id')
    card_number = data.get('card_number')
    stake = data.get('stake')
    if not all([user_id, game_id, card_number, stake]):
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Ensure unique constraint exists
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'unique_game_card'
                ) THEN
                    ALTER TABLE game_cards ADD CONSTRAINT unique_game_card UNIQUE (game_id, card_number);
                END IF;
            END $$;
        """)
        conn.commit()

        cur.execute("BEGIN")
        cur.execute("SELECT status, stake FROM games WHERE id = %s FOR UPDATE", (game_id,))
        game = cur.fetchone()
        if not game:
            cur.execute("ROLLBACK")
            return jsonify({'error': 'Game not found'}), 404
        if game['status'] != 'waiting':
            cur.execute("ROLLBACK")
            return jsonify({'error': 'Game already started'}), 400
        if game['stake'] != stake:
            cur.execute("ROLLBACK")
            return jsonify({'error': f'Stake mismatch. Expected {game["stake"]}'}), 400

        cur.execute("SELECT balance FROM players WHERE user_id = %s FOR UPDATE", (user_id,))
        player = cur.fetchone()
        if not player or player['balance'] < stake:
            cur.execute("ROLLBACK")
            return jsonify({'error': 'Insufficient balance'}), 400

        # FIX: Lock existing cards for this user/game, then count them (avoid aggregate with FOR UPDATE)
        cur.execute("SELECT id FROM game_cards WHERE game_id = %s AND user_id = %s FOR UPDATE", (game_id, user_id))
        existing_cards = cur.fetchall()
        if len(existing_cards) >= 4:
            cur.execute("ROLLBACK")
            return jsonify({'error': 'Maximum 4 cards per player'}), 400

        # Attempt insert – unique constraint prevents duplicates
        try:
            cur.execute(
                "INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                (game_id, user_id, card_number, json.dumps(generate_card()))
            )
        except psycopg2.IntegrityError:
            cur.execute("ROLLBACK")
            return jsonify({'error': 'Card already taken'}), 400

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
@require_telegram_auth
def withdraw_from_game():
    user_id = g.telegram_user_id
    data = request.json
    game_id = data.get('game_id')
    if not user_id or not game_id:
        return jsonify({'error': 'user_id and game_id required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        cur.execute("SELECT value FROM settings WHERE key = 'owner_cut_percent'")
        row = cur.fetchone()
        owner_cut = int(row['value']) if row else 20
        total_winners_prize = round(game['prize_pool'] * (100 - owner_cut) / 100, 2)

        drawn = json.loads(game['drawn_balls'] or '[]')
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [row['card_number'] for row in cur.fetchall()]
        cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id = %s", (game_id,))
        players = len(cur.fetchall())

        result = {
            'status': game['status'],
            'drawn_balls': drawn,
            'prize_pool': game['prize_pool'],
            'total_winners_prize': total_winners_prize,
            'players': players,
            'taken_cards': taken,
        }
        if game['status'] == 'waiting':
            remaining = max(0, 30 - int(time.time() - game['created_at']))
            result['countdown'] = remaining
        if game['status'] == 'finished' and game.get('cancelled') == 1:
            result['status'] = 'cancelled'
            result['cancelled_message'] = 'Not enough players. Game cancelled. Money refunded.'
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

        cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' AND id != %s ORDER BY id DESC LIMIT 1",
                    (game['stake'], game_id))
        next_game = cur.fetchone()
        result['next_game_id'] = next_game['id'] if next_game else None
        return jsonify(result)
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/my_cards/<int:game_id>')
@require_telegram_auth
def my_cards(game_id):
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        try:
            cur.execute("ALTER TABLE game_cards ADD COLUMN IF NOT EXISTS marked_numbers TEXT DEFAULT '[]'")
            conn.commit()
        except Exception:
            pass
        cur.execute("""
            SELECT card_number as card_index, card_data, marked_numbers
            FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        rows = cur.fetchall()
        cards = []
        for row in rows:
            card = dict(row)
            try:
                card['card_data'] = json.loads(card['card_data']) if card.get('card_data') else []
            except:
                card['card_data'] = []
            try:
                card['marked_numbers'] = json.loads(card['marked_numbers']) if card.get('marked_numbers') else []
            except:
                card['marked_numbers'] = []
            cards.append(card)
        return jsonify({'cards': cards})
    except Exception as e:
        return jsonify({'error': str(e), 'cards': []}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/deposit', methods=['POST'])
@require_telegram_auth
def deposit():
    user_id = g.telegram_user_id
    data = request.json
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
@require_telegram_auth
def withdraw():
    user_id = g.telegram_user_id
    data = request.json
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
@require_telegram_auth
def recent_games(user_id):
    user_id = g.telegram_user_id
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT DISTINCT g.id, g.stake, g.prize_pool, g.status, g.finished_at,
                   g.winner_card_numbers,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM game_cards gc2
                       WHERE gc2.game_id = g.id
                         AND gc2.user_id = %s
                         AND gc2.card_number::text IN (
                             SELECT jsonb_array_elements_text(g.winner_card_numbers::jsonb)
                         )
                   ) THEN 1 ELSE 0 END as won
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            WHERE gc.user_id = %s
            ORDER BY g.finished_at DESC
            LIMIT 20
        """, (user_id, user_id))
        games = [dict(row) for row in cur.fetchall()]
        return jsonify(games)
    finally:
        cur.close()
        put_db(conn)

# ---------- Settings endpoints ----------
@app.route('/api/settings/telebirr_number')
def telebirr_number():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'cbe_number'")
        row = cur.fetchone()
        return jsonify({'cbe_number': row['value'] if row else '1000061737212'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/max_balls_per_game')
def get_max_balls_setting():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'max_balls_per_game'")
        row = cur.fetchone()
        return jsonify({'max_balls_per_game': int(row['value']) if row else 75})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/bot_enabled')
def get_bot_enabled():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'bot_enabled'")
        row = cur.fetchone()
        return jsonify({'bot_enabled': row['value'] if row else '1'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/bot_target_real_players')
def get_bot_target_real_players():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'bot_target_real_players'")
        row = cur.fetchone()
        return jsonify({'bot_target_real_players': row['value'] if row else '2'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/bot_addition_interval_seconds')
def get_bot_addition_interval_seconds():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'bot_addition_interval_seconds'")
        row = cur.fetchone()
        return jsonify({'bot_addition_interval_seconds': row['value'] if row else '2'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/bot_remove_excess')
def get_bot_remove_excess():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'bot_remove_excess'")
        row = cur.fetchone()
        return jsonify({'bot_remove_excess': row['value'] if row else '1'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/bot_number_to_add')
def get_bot_number_to_add():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'bot_number_to_add'")
        row = cur.fetchone()
        return jsonify({'bot_number_to_add': row['value'] if row else '1'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/owner_cut_percent')
def get_owner_cut_percent():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'owner_cut_percent'")
        row = cur.fetchone()
        return jsonify({'owner_cut_percent': row['value'] if row else '20'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/settings/stakes')
def get_allowed_stakes():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = 'allowed_stakes'")
        row = cur.fetchone()
        if row:
            stakes = json.loads(row['value'])
        else:
            stakes = [10, 20, 50, 100]
        return jsonify({'stakes': stakes})
    except Exception:
        return jsonify({'stakes': [10, 20, 50, 100]})
    finally:
        cur.close()
        put_db(conn)

# ---------- Admin API endpoints ----------
@app.route('/admin/api/overview')
def admin_overview():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id > 0")
        total_players = cur.fetchone()['cnt']
        cur.execute("SELECT COALESCE(SUM(amount),0) as sum FROM deposits WHERE status='approved'")
        total_deposited = cur.fetchone()['sum']
        cur.execute("SELECT COALESCE(SUM(amount),0) as sum FROM withdrawals WHERE status='approved'")
        total_withdrawn = cur.fetchone()['sum']
        cur.execute("SELECT COUNT(*) as cnt FROM deposits WHERE status='pending'")
        pending_deposits = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) as cnt FROM withdrawals WHERE status='pending'")
        pending_withdrawals = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) as cnt FROM games WHERE status IN ('waiting','running')")
        active_games = cur.fetchone()['cnt']
        return jsonify({
            'total_players': total_players,
            'total_deposited': total_deposited,
            'total_withdrawn': total_withdrawn,
            'pending_deposits': pending_deposits,
            'pending_withdrawals': pending_withdrawals,
            'active_games': active_games
        })
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/players')
def admin_players():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id, username, full_name, balance, wins, games_played, phone, is_banned FROM players WHERE user_id > 0 ORDER BY balance DESC")
        players = cur.fetchall()
        return jsonify({'players': [dict(p) for p in players]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/deposits')
def admin_deposits():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT d.*, p.full_name FROM deposits d
            LEFT JOIN players p ON d.user_id = p.user_id
            ORDER BY d.created_at DESC
        """)
        deposits = cur.fetchall()
        return jsonify({'deposits': [dict(d) for d in deposits]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/withdrawals')
def admin_withdrawals():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT w.*, p.full_name FROM withdrawals w
            LEFT JOIN players p ON w.user_id = p.user_id
            ORDER BY w.created_at DESC
        """)
        withdrawals = cur.fetchall()
        return jsonify({'withdrawals': [dict(w) for w in withdrawals]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/active_games')
def admin_active_games():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT g.*, COUNT(gc.id) as card_count
            FROM games g
            LEFT JOIN game_cards gc ON g.id = gc.game_id
            WHERE g.status IN ('waiting','running')
            GROUP BY g.id
            ORDER BY g.id DESC
        """)
        games = cur.fetchall()
        return jsonify({'games': [dict(g) for g in games]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/inquiries')
def admin_inquiries():
    if request.args.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT i.*, p.full_name as user_name
            FROM inquiries i
            LEFT JOIN players p ON i.user_id = p.user_id
            ORDER BY i.created_at DESC
        """)
        inquiries = cur.fetchall()
        return jsonify({'inquiries': [dict(i) for i in inquiries]})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/mark_inquiry_read', methods=['POST'])
def admin_mark_inquiry_read():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    inquiry_id = data.get('inquiry_id')
    if not inquiry_id:
        return jsonify({'error': 'Missing inquiry_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE inquiries SET status = 'read' WHERE id = %s", (inquiry_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/approve_deposit', methods=['POST'])
def admin_approve_deposit():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    deposit_id = data.get('deposit_id')
    if not deposit_id:
        return jsonify({'error': 'Missing deposit_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id, amount FROM deposits WHERE id = %s AND status = 'pending'", (deposit_id,))
        dep = cur.fetchone()
        if not dep:
            return jsonify({'error': 'Deposit not found or already processed'}), 404
        cur.execute("UPDATE deposits SET status = 'approved' WHERE id = %s", (deposit_id,))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (dep['amount'], dep['user_id']))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/reject_deposit', methods=['POST'])
def admin_reject_deposit():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    deposit_id = data.get('deposit_id')
    if not deposit_id:
        return jsonify({'error': 'Missing deposit_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE deposits SET status = 'rejected' WHERE id = %s", (deposit_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/approve_withdrawal', methods=['POST'])
def admin_approve_withdrawal():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    withdrawal_id = data.get('withdrawal_id')
    if not withdrawal_id:
        return jsonify({'error': 'Missing withdrawal_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE withdrawals SET status = 'approved' WHERE id = %s", (withdrawal_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/reject_withdrawal', methods=['POST'])
def admin_reject_withdrawal():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    withdrawal_id = data.get('withdrawal_id')
    if not withdrawal_id:
        return jsonify({'error': 'Missing withdrawal_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id, amount FROM withdrawals WHERE id = %s AND status = 'pending'", (withdrawal_id,))
        wd = cur.fetchone()
        if wd:
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (wd['amount'], wd['user_id']))
        cur.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = %s", (withdrawal_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/force_finish', methods=['POST'])
def admin_force_finish():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    game_id = data.get('game_id')
    if not game_id:
        return jsonify({'error': 'Missing game_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT stake, status FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] not in ('waiting','running'):
            return jsonify({'error': 'Game not active'}), 400
        cur.execute("SELECT user_id, COUNT(*) as cnt FROM game_cards WHERE game_id = %s GROUP BY user_id", (game_id,))
        players = cur.fetchall()
        for p in players:
            refund = game['stake'] * p['cnt']
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
        cur.execute("DELETE FROM game_cards WHERE game_id = %s", (game_id,))
        cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s", (time.time(), game_id))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/ban_player', methods=['POST'])
def admin_ban_player():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = data.get('user_id')
    ban = data.get('ban', True)
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET is_banned = %s WHERE user_id = %s", (1 if ban else 0, user_id))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/get_user_by_phone', methods=['POST'])
def admin_get_user_by_phone():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Missing phone'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id, full_name, balance FROM players WHERE phone = %s", (phone,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(dict(user))
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/give_bonus_by_phone', methods=['POST'])
def admin_give_bonus_by_phone():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    phone = data.get('phone')
    amount = data.get('amount')
    reason = data.get('reason', 'Admin bonus')
    if not phone or not amount:
        return jsonify({'error': 'Missing phone or amount'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id FROM players WHERE phone = %s", (phone,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (amount, user['user_id']))
        cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) VALUES (%s, %s, %s, %s)",
                    (user['user_id'], amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to user {user["user_id"]}'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/give_bonus_all', methods=['POST'])
def admin_give_bonus_all():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    amount = data.get('amount')
    reason = data.get('reason', 'Admin bonus')
    if not amount:
        return jsonify({'error': 'Missing amount'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id > 0", (amount,))
        cur.execute("INSERT INTO bonuses (user_id, amount, reason, created_at) SELECT user_id, %s, %s, %s FROM players WHERE user_id > 0",
                    (amount, reason, time.time()))
        conn.commit()
        return jsonify({'success': True, 'message': f'Added {amount} ETB to all players'})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/send_notification', methods=['POST'])
def admin_send_notification():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    message = data.get('message')
    if not message:
        return jsonify({'error': 'Missing message'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("INSERT INTO notifications (message, created_at, is_broadcast) VALUES (%s, %s, %s)",
                    (message, time.time(), 1))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_owner_cut', methods=['POST'])
def admin_update_owner_cut():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    owner_cut = data.get('owner_cut_percent')
    if owner_cut is None:
        return jsonify({'error': 'Missing owner_cut_percent'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'owner_cut_percent'", (str(owner_cut),))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_telebirr', methods=['POST'])
def admin_update_telebirr():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    number = data.get('telebirr_number')
    if not number:
        return jsonify({'error': 'Missing telebirr_number'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'telebirr_number'", (number,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_cbe', methods=['POST'])
def admin_update_cbe():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    number = data.get('cbe_number')
    if not number:
        return jsonify({'error': 'Missing cbe_number'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'cbe_number'", (number,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/set_max_balls', methods=['POST'])
def admin_set_max_balls():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    max_balls = data.get('max_balls')
    if not max_balls or not isinstance(max_balls, int) or max_balls < 10:
        return jsonify({'error': 'Invalid max_balls'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'max_balls_per_game'", (str(max_balls),))
        conn.commit()
        return jsonify({'success': True})
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

@app.route('/admin/api/update_stakes', methods=['POST'])
def admin_update_stakes():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Unauthorized'}), 401
    stakes = data.get('stakes')
    if not stakes or not isinstance(stakes, list):
        return jsonify({'error': 'Invalid stakes'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO settings (key, value)
            VALUES ('allowed_stakes', %s)
            ON CONFLICT (key) DO UPDATE SET value = %s
        """, (json.dumps(stakes), json.dumps(stakes)))
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

# ---------- Notification ----------
@app.route('/api/notifications/latest')
def latest_notification():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT message, created_at FROM notifications ORDER BY created_at DESC LIMIT 1")
        notif = cur.fetchone()
        if notif:
            return jsonify({'message': notif['message'], 'created_at': notif['created_at']})
        return jsonify({})
    finally:
        cur.close()
        put_db(conn)

# ---------- Inquiry ----------
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
            (user_id, subject, message, time.time())
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Inquiry sent.'})
    finally:
        cur.close()
        put_db(conn)

# ---------- Referral stats ----------
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

# ========== TELEGRAM WEBHOOK ==========
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
            cur.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS bot_started BOOLEAN DEFAULT FALSE")
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
            send_telegram_message(chat_id, f"🎯 Welcome to Nef Bingo!\n\nPlay here: {WEB_APP_URL}\n\nUse /balance to check your balance (once registered).")
        elif text == '/balance':
            send_telegram_message(chat_id, "Please log in to the game first, then we can link your Telegram account for balance checks.")
        else:
            send_telegram_message(chat_id, "Send /start to get the game link.")
    return 'OK', 200

# ---------- Start ----------
if __name__ == '__main__':
    init_db()
    # Prevent duplicate bot creation
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
