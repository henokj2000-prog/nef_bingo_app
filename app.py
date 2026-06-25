import sys
import os
import re
import json
import hmac
import hashlib
import urllib.parse
import time
import random
import threading
from threading import Lock  
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.bingo_logic import generate_card, draw_ball, check_bingo
from database import (
    get_db, put_db, init_db, create_bot_players,
    create_referral_code_for_user, award_referral_bonus, add_bot_to_game,
    ETHIOPIAN_MALE_NAMES
)
from config import (
    ADMIN_PASSWORD, ADMIN_IDS, BOT_TOKEN, WEB_APP_URL,
    GAME_START_DELAY_SECONDS, BALL_DRAW_INTERVAL_SECONDS
)

# Global game cache
game_cache = {}
cache_lock = Lock()

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ========== GAME LOOP GLOBALS ==========
game_loop_running = False
game_loop_lock = threading.Lock()

# ========== SETTINGS HELPER ==========
def get_setting_value(key, default=None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cur.fetchone()
        return row['value'] if row else default
    finally:
        cur.close()
        put_db(conn)

def get_player_funds(cur, user_id):
    """Returns (real_balance, bonus_balance, deposit_unlocked) for a player.
    bonus_balance (referral bonus/commission) only becomes usable for
    gameplay once the player has made at least one real, approved deposit
    of 50+ ETB. It can never be withdrawn directly, regardless of unlock
    status — only real_balance (deposits + winnings) is withdrawable."""
    cur.execute("SELECT balance, bonus_balance FROM players WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return 0.0, 0.0, False
    cur.execute("SELECT 1 FROM deposits WHERE user_id = %s AND status = 'approved' AND amount >= 50 LIMIT 1", (user_id,))
    unlocked = cur.fetchone() is not None
    return (row['balance'] or 0.0), (row['bonus_balance'] or 0.0), unlocked

def update_setting(key, value):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                    (key, str(value), str(value)))
        conn.commit()
    finally:
        cur.close()
        put_db(conn)

def add_bots_to_waiting_game(game_id, stake):
    """Add a random number of bots (1..batch_size) at random intervals."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        max_bots = int(get_setting_value('bot_number_to_add', '1'))
        base_interval = float(get_setting_value('bot_addition_interval_seconds', '2'))
        try:
            batch_size = int(get_setting_value('bot_batch_size', '3'))
        except (TypeError, ValueError):
            batch_size = 5
        jitter_factor = float(get_setting_value('bot_random_jitter', '0.5'))
 
        print(f"DEBUG: batch version called, max_bots={max_bots}, batch_size={batch_size}")
 
        cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        bot_count = cur.fetchone()['cnt']
        if bot_count >= max_bots:
            print(f"DEBUG: already at max bots ({bot_count} >= {max_bots})")
            return
 
        cur.execute("SELECT MAX(created_at) as last FROM game_cards WHERE game_id = %s AND user_id < 0", (game_id,))
        last = cur.fetchone()['last']
        if last is not None:
            if isinstance(last, str):
                last = float(last)
            jitter = random.uniform(-jitter_factor, jitter_factor) * base_interval
            actual_interval = max(0.3, base_interval + jitter)
            if (time.time() - last) < actual_interval:
                print(f"DEBUG: interval not reached ({(time.time() - last):.2f}s < {actual_interval:.2f}s)")
                return
 
        to_add = min(max_bots - bot_count, random.randint(1, batch_size))
        print(f"DEBUG: adding {to_add} bots")
        for _ in range(to_add):
            add_bot_to_game(game_id, stake)
 
        print(f"Added {to_add} bots to game {game_id} (total now {bot_count + to_add})")
    except Exception as e:
        print(f"Error adding bots to game {game_id}: {e}")
    finally:
        cur.close()
        put_db(conn)

# ========== GAME STATE CACHE HELPER ==========
def fetch_game_row(cur, game_id):
    """One round trip instead of four: pulls the game row plus taken cards,
    player count, and the owner-cut setting all in a single query. This is
    the hot path hit on basically every poll, so cutting 4 sequential
    queries down to 1 directly cuts the latency players feel."""
    cur.execute("""
        SELECT g.*,
               COALESCE(
                   (SELECT array_agg(card_number) FROM game_cards
                    WHERE game_id = g.id AND card_number IS NOT NULL),
                   ARRAY[]::integer[]
               ) AS taken_cards,
               (SELECT COUNT(DISTINCT user_id) FROM game_cards WHERE game_id = g.id) AS players,
               COALESCE((SELECT value::int FROM settings WHERE key = 'owner_cut_percent'), 20) AS owner_cut
        FROM games g
        WHERE g.id = %s
    """, (game_id,))
    return cur.fetchone()

def update_game_cache(game_id):
    """Refresh cache for a given game_id from DB."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        game = fetch_game_row(cur, game_id)
        if not game:
            with cache_lock:
                game_cache.pop(game_id, None)
            return
        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)
        result['taken_cards'] = list(result.get('taken_cards') or [])
        result['players'] = result.get('players') or 0
        owner_cut = result.pop('owner_cut', 20) or 20
        result['total_winners_prize'] = round((result.get('prize_pool') or 0) * (100 - owner_cut) / 100, 2)

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

        with cache_lock:
            game_cache[game_id] = {'data': result, 'ts': time.time()}
    except Exception as e:
        print(f"Error updating cache for game {game_id}: {e}")
    finally:
        cur.close()
        put_db(conn)

# ========== GAME PROGRESSION ==========
def process_waiting_games():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, stake, countdown_started_at FROM games WHERE status = 'waiting' AND cancelled = 0")
        games = cur.fetchall()
        now = time.time()
        bot_enabled = int(get_setting_value('bot_enabled', '1')) == 1

        for game in games:
            game_id = game['id']
            stake = game['stake']
            countdown_started = game['countdown_started_at']
            if isinstance(countdown_started, str):
                countdown_started = float(countdown_started)
            elapsed = now - countdown_started
            remaining = max(0, GAME_START_DELAY_SECONDS - elapsed)

            if bot_enabled and remaining > 0:
                add_bots_to_waiting_game(game_id, stake)

            if remaining <= 0:
                cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id = %s AND user_id > 0", (game_id,))
                real_count = cur.fetchone()['cnt']
                if real_count >= 1:
                    cur.execute("UPDATE games SET status = 'running', last_draw_time = %s WHERE id = %s", (now, game_id))
                    conn.commit()
                    update_game_cache(game_id)
                    print(f"Game {game_id} started with {real_count} real players.")
                else:
                    # Cancel and refund
                    cur.execute("SELECT user_id, COUNT(*) as cards FROM game_cards WHERE game_id = %s GROUP BY user_id", (game_id,))
                    for p in cur.fetchall():
                        refund = stake * p['cards']
                        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (refund, p['user_id']))
                    cur.execute("UPDATE games SET status = 'finished', cancelled = 1, finished_at = %s WHERE id = %s", (now, game_id))
                    conn.commit()
                    with cache_lock:
                        game_cache.pop(game_id, None)
                    print(f"Game {game_id} cancelled (real players: {real_count})")
    except Exception as e:
        print(f"Error in process_waiting_games: {e}")
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

def draw_ball_for_running_game(game_id, max_balls=75):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT drawn_balls, prize_pool FROM games WHERE id = %s AND status = 'running'", (game_id,))
        game = cur.fetchone()
        if not game:
            return
        drawn = json.loads(game['drawn_balls'] or '[]')
        if len(drawn) >= max_balls:
            cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s", (time.time(), game_id))
            conn.commit()
            with cache_lock:
                game_cache.pop(game_id, None)
            return
        new_ball = draw_ball(set(drawn))
        if not new_ball:
            return
        drawn.append(new_ball)
        cur.execute("UPDATE games SET drawn_balls = %s, last_draw_time = %s WHERE id = %s",
                    (json.dumps(drawn), time.time(), game_id))
        conn.commit()
        update_game_cache(game_id)

        # Check winners
        cur.execute("SELECT user_id, card_data, card_number FROM game_cards WHERE game_id = %s", (game_id,))
        cards = cur.fetchall()
        winners = []
        drawn_set = set(drawn)
        for card in cards:
            card_data = card['card_data']
            if isinstance(card_data, str):
                card_data = json.loads(card_data)
            if check_bingo(card_data, drawn_set):
                winners.append(card['card_number'])
        if winners:
            owner_cut = int(get_setting_value('owner_cut_percent', '20'))
            total_prize = game['prize_pool']
            winners_prize = total_prize * (100 - owner_cut) / 100
            prize_per_winner = winners_prize / len(winners)
            for card_num in winners:
                cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND card_number = %s", (game_id, card_num))
                winner = cur.fetchone()
                if winner:
                    cur.execute("UPDATE players SET balance = balance + %s, wins = wins + 1, total_won = total_won + %s WHERE user_id = %s",
                                (prize_per_winner, prize_per_winner, winner['user_id']))
                    
                    # --- Referral commission on win ---
                    # Credited to bonus_balance (play-only), same as the
                    # registration bonus — never directly withdrawable.
                    commission_percent = float(get_setting_value('referral_commission_percent', '0'))
                    if commission_percent > 0:
                        cur.execute("SELECT referred_by FROM players WHERE user_id = %s", (winner['user_id'],))
                        referrer = cur.fetchone()
                        if referrer and referrer['referred_by']:
                            referrer_id = referrer['referred_by']
                            commission = (prize_per_winner * commission_percent) / 100.0
                            if commission > 0:
                                cur.execute("UPDATE players SET bonus_balance = bonus_balance + %s WHERE user_id = %s", (commission, referrer_id))
                                cur.execute(
                                    "INSERT INTO referral_earnings (referrer_id, referred_id, earning_type, amount, created_at) VALUES (%s, %s, %s, %s, %s)",
                                    (referrer_id, winner['user_id'], 'commission', commission, time.time())
                                )
                                print(f"Commission {commission} ETB awarded (bonus_balance) to referrer {referrer_id} for winner {winner['user_id']}")

            cur.execute("UPDATE games SET status = 'finished', finished_at = %s, winner_card_numbers = %s WHERE id = %s",
                        (time.time(), json.dumps(winners), game_id))
            conn.commit()
            with cache_lock:
                game_cache.pop(game_id, None)
            print(f"Game {game_id} finished. Winners: {winners}")
    except Exception as e:
        print(f"Error in draw_ball_for_running_game {game_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        put_db(conn)

def process_running_games():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, last_draw_time FROM games WHERE status = 'running'")
        games = cur.fetchall()
        now = time.time()
        for game in games:
            last_draw = game['last_draw_time']
            if isinstance(last_draw, str):
                last_draw = float(last_draw)
            if last_draw is None or (now - last_draw) >= BALL_DRAW_INTERVAL_SECONDS:
                draw_ball_for_running_game(game['id'])
    except Exception as e:
        print(f"Error in process_running_games: {e}")
    finally:
        cur.close()
        put_db(conn)

def game_loop():
    global game_loop_running
    while game_loop_running:
        try:
            process_waiting_games()
            process_running_games()
        except Exception as e:
            print(f"Game loop error: {e}")
        time.sleep(1)

def start_game_loop():
    # DISABLED: worker.py (the separate Procfile "worker:" dyno) already runs
    # process_waiting_games()/process_running_games() on its own 1s loop.
    # Running it again here too means two processes hit the same DB rows at
    # the same time -> lock contention -> uneven /api/game_state latency.
    # That uneven latency is what made the countdown number jump unevenly
    # (30, 28, 25, 21, 18, 17, 14...) instead of dropping ~2-3 every poll.
    # If worker.py is ever removed, re-enable the body below.
    print("In-process game loop disabled (worker.py handles ticking).")
    return
    global game_loop_running
    with game_loop_lock:
        if not game_loop_running:
            game_loop_running = True
            thread = threading.Thread(target=game_loop, daemon=True)
            thread.start()
            print("Game loop started.")

# ========== TELEGRAM initData VERIFICATION ==========
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

# ========== AUTH DECORATOR ==========
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

@app.after_request
def add_no_cache_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ============================================================
#                     ORIGINAL ROUTES
# ============================================================

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/admin')
def admin():
    resp = send_from_directory('templates', 'admin.html')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

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
            # No row created here on purpose — opening the Mini App alone
            # should not put anyone in the players table. A real row only
            # gets created once registration actually completes (see
            # update_profile). Just hand back a "not registered yet" shape
            # so the frontend still correctly routes to the registration
            # screen, with nothing persisted in the database.
            return jsonify({
                'user_id': user_id,
                'username': username,
                'full_name': full_name,
                'phone': None,
                'balance': 0,
                'bonus_balance': 0,
                'bonus_unlocked': False,
                'playable_balance': 0,
                'games_played': 0,
                'wins': 0,
                'total_won': 0,
                'language': 'en',
                'referred_by': None,
                'is_banned': False,
                'active_game': None
            })
        result = dict(player)
        real_balance, bonus_balance, unlocked = get_player_funds(cur, user_id)
        result['bonus_balance'] = bonus_balance
        result['bonus_unlocked'] = unlocked
        result['playable_balance'] = real_balance + (bonus_balance if unlocked else 0.0)
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
    username = data.get('username', 'user')
    full_name = data.get('full_name', 'Player')
    print(f"DEBUG update_profile: user_id={user_id}, referral_code='{referral_code}', full_data={data}", flush=True)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT phone, referred_by FROM players WHERE user_id = %s", (user_id,))
        existing = cur.fetchone()
        is_new_player = existing is None
        if is_new_player:
            # This is the actual moment registration happens — create the
            # real row here, not just on opening the Mini App.
            cur.execute(
                "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, 0) ON CONFLICT (user_id) DO NOTHING",
                (user_id, username, full_name)
            )
            conn.commit()
            existing = None  # treat as having no phone/referred_by yet
        # True only the very first time a real phone gets attached to this
        # account — this is the actual "registration completed" moment.
        is_first_registration = bool(phone) and not (existing and existing.get('phone'))

        if phone:
            cur.execute("SELECT user_id FROM players WHERE phone = %s AND user_id != %s", (phone, user_id))
            if cur.fetchone():
                return jsonify({'error': 'Phone number already registered'}), 400
            cur.execute("UPDATE players SET phone = %s WHERE user_id = %s", (phone, user_id))

        if language and language in ['en', 'am', 'om', 'ti']:
            cur.execute("UPDATE players SET language = %s WHERE user_id = %s", (language, user_id))

        # Resolve the referrer — either already linked earlier (e.g. via a
        # /start deep link) or being linked right now via this field.
        referrer_id = existing['referred_by'] if existing else None
        if not referrer_id and referral_code:
            cur.execute("SELECT user_id FROM referral_codes WHERE code = %s", (referral_code,))
            referrer = cur.fetchone()
            if referrer and referrer['user_id'] != user_id:
                referrer_id = referrer['user_id']
                cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s", (referrer_id, user_id))

        conn.commit()

        # Award the referral bonus only once registration is genuinely
        # complete (a real phone number on file) — not for merely clicking
        # a referral link. The referral_earnings check also guards against
        # ever double-paying the same referral.
        if is_first_registration and referrer_id:
            cur.execute("SELECT id FROM referral_earnings WHERE referred_id = %s AND earning_type = 'bonus'", (user_id,))
            if not cur.fetchone():
                award_referral_bonus(referrer_id, user_id)

        create_referral_code_for_user(user_id)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_profile: {e}")
        conn.rollback()
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
        if get_setting_value('maintenance_mode', '0') == '1':
            return jsonify({'error': 'maintenance'}), 503
        cur.execute("SELECT is_banned, balance, phone FROM players WHERE user_id = %s", (user_id,))
        p = cur.fetchone()
        if p and p['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403
        if not p or not p.get('phone'):
            return jsonify({'error': 'Please complete registration first.'}), 403

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

        cur.execute("""
            SELECT id, countdown_started_at FROM games
            WHERE stake = %s AND status = 'waiting' AND cancelled = 0
            ORDER BY id DESC LIMIT 1
        """, (stake,))
        waiting_game = cur.fetchone()
        now = time.time()
        if waiting_game:
            game_id = waiting_game['id']
            cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
            game = cur.fetchone()
            update_game_cache(game_id)
        else:
            cur.execute("""
                INSERT INTO games (stake, status, created_at, countdown_started_at)
                VALUES (%s, 'waiting', %s, %s) RETURNING id
            """, (stake, now, now))
            game_id = cur.fetchone()['id']
            conn.commit()
            cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
            game = cur.fetchone()
            update_game_cache(game_id)

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

        cur.execute("SELECT is_banned FROM players WHERE user_id = %s", (user_id,))
        player = cur.fetchone()
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        if player['is_banned']:
            return jsonify({'error': 'Account suspended'}), 403

        real_balance, bonus_balance, unlocked = get_player_funds(cur, user_id)
        usable_bonus = bonus_balance if unlocked else 0.0
        available = real_balance + usable_bonus
        if available < stake:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Spend bonus (referral) money first, since it's play-only anyway —
        # this preserves the player's real withdrawable balance for longer.
        bonus_used = min(stake, usable_bonus)
        real_used = stake - bonus_used

        if bonus_used > 0:
            cur.execute("UPDATE players SET bonus_balance = bonus_balance - %s WHERE user_id = %s", (bonus_used, user_id))
        if real_used > 0:
            cur.execute("UPDATE players SET balance = balance - %s WHERE user_id = %s", (real_used, user_id))

        card = generate_card()
        cur.execute("""
            INSERT INTO game_cards (game_id, user_id, card_number, card_data, created_at, funded_bonus_amt, funded_real_amt)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (game_id, user_id, card_number, json.dumps(card), time.time(), bonus_used, real_used))
        cur.execute("UPDATE games SET prize_pool = prize_pool + %s WHERE id = %s", (stake, game_id))
        conn.commit()
        update_game_cache(game_id)

        cur.execute("SELECT balance, bonus_balance FROM players WHERE user_id = %s", (user_id,))
        updated = cur.fetchone()
        new_balance = updated['balance']
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [r['card_number'] for r in cur.fetchall() if r['card_number']]

        return jsonify({'success': True, 'balance': new_balance, 'bonus_balance': updated['bonus_balance'], 'card_number': card_number, 'taken_cards': taken})
    except Exception as e:
        conn.rollback()
        print(f"Error in pick_card: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/api/release_card', methods=['POST'])
@require_telegram_auth
def release_card():
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
            return jsonify({'error': 'Game has already started — cards can no longer be changed'}), 400

        cur.execute("SELECT user_id FROM game_cards WHERE game_id = %s AND card_number = %s",
                    (game_id, card_number))
        existing = cur.fetchone()
        if not existing or existing['user_id'] != user_id:
            return jsonify({'error': 'You do not hold this card'}), 400

        stake = game['stake']
        cur.execute("SELECT funded_bonus_amt, funded_real_amt FROM game_cards WHERE game_id = %s AND card_number = %s AND user_id = %s",
                    (game_id, card_number, user_id))
        funding = cur.fetchone()
        bonus_refund = (funding['funded_bonus_amt'] or 0) if funding else 0
        real_refund = (funding['funded_real_amt'] or 0) if funding else stake

        cur.execute("DELETE FROM game_cards WHERE game_id = %s AND card_number = %s AND user_id = %s",
                    (game_id, card_number, user_id))
        # Refund each portion back to the exact wallet it was paid from —
        # never lets bonus money get "laundered" into real balance via a
        # pick-then-release cycle.
        if bonus_refund > 0:
            cur.execute("UPDATE players SET bonus_balance = bonus_balance + %s WHERE user_id = %s", (bonus_refund, user_id))
        if real_refund > 0:
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s", (real_refund, user_id))
        cur.execute("UPDATE games SET prize_pool = prize_pool - %s WHERE id = %s", (stake, game_id))
        conn.commit()
        update_game_cache(game_id)

        cur.execute("SELECT balance, bonus_balance FROM players WHERE user_id = %s", (user_id,))
        updated = cur.fetchone()
        cur.execute("SELECT card_number FROM game_cards WHERE game_id = %s", (game_id,))
        taken = [r['card_number'] for r in cur.fetchall() if r['card_number']]

        return jsonify({'success': True, 'balance': updated['balance'], 'bonus_balance': updated['bonus_balance'], 'released_card': card_number, 'taken_cards': taken})
    except Exception as e:
        conn.rollback()
        print(f"Error in release_card: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)
        
@app.route('/admin/api/delete_player', methods=['POST'])
def admin_delete_player():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    user_id = data.get('id')
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("DELETE FROM game_cards WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM players WHERE user_id = %s", (user_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'Player {user_id} deleted'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/delete_deposit', methods=['POST'])
def admin_delete_deposit():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    deposit_id = data.get('id')
    if not deposit_id:
        return jsonify({'error': 'Missing deposit_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("DELETE FROM deposits WHERE id = %s", (deposit_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'Deposit {deposit_id} deleted'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/delete_withdrawal', methods=['POST'])
def admin_delete_withdrawal():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    withdrawal_id = data.get('id')
    if not withdrawal_id:
        return jsonify({'error': 'Missing withdrawal_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("DELETE FROM withdrawals WHERE id = %s", (withdrawal_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'Withdrawal {withdrawal_id} deleted'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/delete_game', methods=['POST'])
def admin_delete_game():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    game_id = data.get('id')
    if not game_id:
        return jsonify({'error': 'Missing game_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("DELETE FROM game_cards WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM games WHERE id = %s", (game_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'Game {game_id} deleted'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/delete_inquiry', methods=['POST'])
def admin_delete_inquiry():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    inquiry_id = data.get('id')
    if not inquiry_id:
        return jsonify({'error': 'Missing inquiry_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("DELETE FROM inquiries WHERE id = %s", (inquiry_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'Inquiry {inquiry_id} deleted'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

def get_countdown_remaining(game):
    if not game.get('countdown_started_at'):
        return 0
    started = game['countdown_started_at']
    if isinstance(started, str):
        started = float(started)
    elapsed = time.time() - started
    return max(0, int(GAME_START_DELAY_SECONDS - elapsed))

def serialize_game(game):
    result = dict(game)
    for field in ['created_at', 'started_at', 'finished_at', 'last_draw_time', 'countdown_started_at']:
        if result.get(field) and isinstance(result[field], float):
            result[field] = result[field]
    result['drawn_balls'] = json.loads(result.get('drawn_balls') or '[]')
    result['winner_card_numbers'] = json.loads(result.get('winner_card_numbers') or '[]')
    return result

# Cache entries older than this are treated as a miss and rebuilt from the
# DB. This is short on purpose: worker.py runs in a completely separate
# process and has no way to invalidate this in-memory cache directly when it
# changes a game's status/balls/winners, so a short TTL is what keeps this
# cache from ever serving data that's more than ~1 second out of date.
GAME_CACHE_TTL_SECONDS = 2.0

# ========== CACHED GAME STATE ENDPOINT ==========
@app.route('/api/game_state/<int:game_id>')
def get_game_state(game_id):
    user_id = request.args.get('user_id', type=int)

    # Try to serve from cache, but only if it's still fresh
    with cache_lock:
        entry = game_cache.get(game_id)
        if entry and (time.time() - entry['ts']) < GAME_CACHE_TTL_SECONDS:
            # NOTE: my_cards used to be re-queried from the DB here on every
            # single poll for every player, even though the frontend never
            # reads gameState.my_cards from this endpoint (it has its own
            # dedicated /api/my_cards/<game_id> call for that). Dropping it
            # removes one DB round-trip per poll per player.
            return jsonify(entry['data'])

    # Cache miss: fallback to database
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        game = fetch_game_row(cur, game_id)
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)
        result['taken_cards'] = list(result.get('taken_cards') or [])
        result['players'] = result.get('players') or 0
        owner_cut = result.pop('owner_cut', 20) or 20
        result['total_winners_prize'] = round((result.get('prize_pool') or 0) * (100 - owner_cut) / 100, 2)

        # my_cards intentionally not fetched here — the frontend never reads
        # this field from /api/game_state; use /api/my_cards/<game_id> for that.
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

        # Populate cache for next requests
        with cache_lock:
            game_cache[game_id] = {'data': result, 'ts': time.time()}

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
            SELECT card_data, marked_numbers, card_number FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        cards = []
        for pc in cur.fetchall():
            card = pc['card_data'] if isinstance(pc['card_data'], (dict, list)) else json.loads(pc['card_data'] or '[]')
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
            SELECT card_data, marked_numbers, card_number FROM game_cards
            WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        result = serialize_game(game)
        result['countdown_remaining'] = get_countdown_remaining(game)
        result['my_cards'] = []
        for pc in cur.fetchall():
            card = pc['card_data'] if isinstance(pc['card_data'], (dict, list)) else json.loads(pc['card_data'] or '[]')
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
    platform = data.get('platform', '')
    proof = data.get('proof', '').strip()

    if not proof:
        return jsonify({'error': 'Proof required'}), 400

    # ----- Extract transaction reference -----
    # Covers both Telebirr ("...transaction number is DFL45OHUUI...")
    # and M-Pesa ("...Transaction number UFL075K7VK...") wording.
    tx_ref = proof  # fallback
    ref_match = re.search(r'transaction number\s*(?:is)?\s*([A-Z0-9]+)', proof, re.IGNORECASE)
    if ref_match:
        tx_ref = ref_match.group(1).strip()
    elif re.match(r'^[A-Z0-9]{6,}$', proof, re.IGNORECASE):
        tx_ref = proof.upper()
    else:
        # Player may have pasted an Amharic-language SMS (or any other
        # language) — the surrounding phrase won't match "transaction
        # number", but the code itself is always Latin letters+digits
        # regardless of SMS language. Grab that token directly.
        generic_match = re.search(r'\b([A-Z][A-Z0-9]{7,11})\b', proof, re.IGNORECASE)
        if generic_match:
            tx_ref = generic_match.group(1).upper()

    # ----- Reject vague/non-code-like submissions -----
    looks_like_code = bool(re.match(r'^[A-Z0-9]{6,}$', tx_ref, re.IGNORECASE)) and \
                       bool(re.search(r'[A-Za-z]', tx_ref)) and bool(re.search(r'\d', tx_ref))
    if not looks_like_code:
        return jsonify({'error': 'Could not find a valid transaction code in your proof. Please paste the full SMS confirmation message, or just the transaction reference number.'}), 400

    # ----- Extract a "claimed" amount directly from what the player pasted -----
    # This is shown in the admin pending list so deposits never show as a
    # misleading 0 — but it is NEVER trusted for actually crediting the
    # balance. Real crediting always comes from a verified SMS (sms_match
    # below, or sms_webhook later) or an admin manually confirming.
    claimed_amount = 0.0
    amt_match = re.search(r'ETB\s*([\d,]+(?:\.\d{1,2})?)', proof, re.IGNORECASE)
    if not amt_match:
        amt_match = re.search(r'([\d,]+(?:\.\d{1,2})?)\s*Birr', proof, re.IGNORECASE)
    if amt_match:
        try:
            claimed_amount = float(amt_match.group(1).replace(',', ''))
        except ValueError:
            claimed_amount = 0.0

    # ----- Check for duplicate reference -----
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM deposits WHERE tx_ref = %s", (tx_ref,))
        existing = cur.fetchone()
        if existing:
            return jsonify({'error': f'Transaction {tx_ref} already submitted'}), 400

        # Did the matching bank SMS already arrive before this submission?
        # (race condition: SMS forwarder can beat the player to it)
        cur.execute("SELECT id, amount FROM unmatched_sms WHERE tx_ref = %s AND matched = FALSE", (tx_ref,))
        sms_match = cur.fetchone()

        if sms_match:
            MIN_DEPOSIT = 50.0
            if sms_match['amount'] < MIN_DEPOSIT:
                cur.execute("""
                    INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at, proof_text)
                    VALUES (%s, %s, %s, %s, 'rejected', %s, %s)
                """, (user_id, sms_match['amount'], platform, tx_ref, time.time(), proof))
                cur.execute("UPDATE unmatched_sms SET matched = TRUE WHERE id = %s", (sms_match['id'],))
                conn.commit()
                return jsonify({'error': f'Minimum deposit is {MIN_DEPOSIT} ETB. You sent {sms_match["amount"]} ETB — please contact support.'}), 400

            # Auto-approve immediately using the amount from the real SMS
            cur.execute("""
                INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at, proof_text)
                VALUES (%s, %s, %s, %s, 'approved', %s, %s)
            """, (user_id, sms_match['amount'], platform, tx_ref, time.time(), proof))
            cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s",
                        (sms_match['amount'], user_id))
            cur.execute("UPDATE unmatched_sms SET matched = TRUE WHERE id = %s", (sms_match['id'],))
            conn.commit()
            return jsonify({'success': True, 'message': 'Deposit auto-approved (matching SMS already received)', 'amount': sms_match['amount']})

        # No matching SMS yet — insert as pending, using the amount
        # extracted from the player's own pasted text so it shows
        # something real (not 0) while you wait for SMS confirmation
        # or decide to approve it manually.
        cur.execute("""
            INSERT INTO deposits (user_id, amount, platform, tx_ref, status, created_at, proof_text)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s)
        """, (user_id, claimed_amount, platform, tx_ref, time.time(), proof))
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
        real_balance, bonus_balance, unlocked = get_player_funds(cur, user_id)
        if not unlocked:
            return jsonify({'error': 'You must make at least one deposit of 50 ETB before you can withdraw'}), 400
        # Only real (deposit/winnings) balance is withdrawable — bonus_balance
        # from referrals is play-only and never counted here.
        if real_balance < amount:
            return jsonify({'error': 'Insufficient balance'}), 400
        MIN_REMAINING_BALANCE = 50.0
        if (real_balance - amount) < MIN_REMAINING_BALANCE:
            return jsonify({'error': f'You must keep at least {MIN_REMAINING_BALANCE} ETB in your balance after withdrawing'}), 400
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

# ============================================================
#                     ADMIN ROUTES
# ============================================================

def admin_auth(req):
    if req.args.get('password') == ADMIN_PASSWORD:
        return True
    if req.is_json and req.json and req.json.get('password') == ADMIN_PASSWORD:
        return True
    return False

@app.route('/admin/api/reset_all_balances', methods=['POST'])
def admin_reset_all_balances():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json or {}
    if data.get('confirm') != 'YES_RESET_ALL_BALANCES':
        return jsonify({'error': 'Missing confirmation. Pass {"confirm": "YES_RESET_ALL_BALANCES", "password": "..."}'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("UPDATE players SET balance = 0 WHERE user_id > 0")
        affected = cur.rowcount
        conn.commit()
        return jsonify({'success': True, 'message': f'Reset balance to 0 for {affected} players'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)
        
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
        return jsonify({'players': [dict(p) for p in cur.fetchall()]})
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
                    row['created_at'] = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(row['created_at'])))
                except Exception:
                    pass
            result.append(row)
        return jsonify({'deposits': result})
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
                   p.username, p.full_name, p.phone, p.balance AS current_balance
            FROM withdrawals w
            LEFT JOIN players p ON p.user_id = w.user_id
            ORDER BY w.id DESC LIMIT 100
        """)
        result = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                try:
                    row['created_at'] = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(row['created_at'])))
                except Exception:
                    pass
            result.append(row)
        return jsonify({'withdrawals': result})
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
                   g.created_at,
                   COUNT(gc.id) as card_count
            FROM games g
            LEFT JOIN game_cards gc ON gc.game_id = g.id
            WHERE g.status IN ('waiting', 'running')
            GROUP BY g.id
            ORDER BY g.id DESC
        """)
        games = []
        for g in cur.fetchall():
            row = dict(g)
            games.append(row)
        return jsonify({'games': games})
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
        """, (time.time(), game_id))
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
            row['user_name'] = row.get('full_name') or row.get('username') or row.get('user_id')
            result.append(row)
        return jsonify({'inquiries': result})
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
                    'bot_addition_interval_seconds', 'bot_number_to_add',
                    'bot_batch_size', 'bot_random_jitter']:
            if key in data:
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = %s",
                    (key, str(data[key]), str(data[key]))
                )
        conn.commit()
        return jsonify({'success': True})
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/update_owner_cut', methods=['POST'])
def admin_update_owner_cut():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    try:
        owner_cut = int(data.get('owner_cut_percent'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Owner cut must be a number'}), 400
    if owner_cut < 0 or owner_cut > 100:
        return jsonify({'error': 'Owner cut must be between 0 and 100'}), 400
    update_setting('owner_cut_percent', owner_cut)
    return jsonify({'success': True})

@app.route('/admin/api/update_telebirr', methods=['POST'])
def admin_update_telebirr():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    number = str(data.get('telebirr_number', '')).strip()
    if not number:
        return jsonify({'error': 'Telebirr number cannot be empty'}), 400
    update_setting('telebirr_number', number)
    return jsonify({'success': True})

@app.route('/admin/api/update_mpesa', methods=['POST'])
def admin_update_mpesa():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    number = str(data.get('mpesa_number', '')).strip()
    if not number:
        return jsonify({'error': 'M-Pesa number cannot be empty'}), 400
    update_setting('mpesa_number', number)
    return jsonify({'success': True})

@app.route('/admin/api/update_setting', methods=['POST'])
def admin_update_setting():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    key = data.get('key')
    value = data.get('value')
    if not key or value is None:
        return jsonify({'error': 'Missing key or value'}), 400
    update_setting(key, value)
    return jsonify({'success': True})

@app.route('/admin/api/referrals')
def admin_referrals():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        current_bonus = float(get_setting_value('referral_bonus_amount', '10'))

        cur.execute("""
            WITH referred_counts AS (
                SELECT referred_by AS referrer_id, COUNT(*) AS referral_count
                FROM players
                WHERE referred_by IS NOT NULL
                GROUP BY referred_by
            ),
            earnings_agg AS (
                SELECT referrer_id,
                       COALESCE(SUM(CASE WHEN earning_type = 'bonus' THEN amount ELSE 0 END), 0) AS logged_bonus,
                       COUNT(CASE WHEN earning_type = 'commission' THEN 1 END) AS win_count,
                       COALESCE(SUM(CASE WHEN earning_type = 'commission' THEN amount ELSE 0 END), 0) AS total_commission
                FROM referral_earnings
                GROUP BY referrer_id
            )
            SELECT
                ref.user_id AS referrer_id,
                ref.full_name AS referrer_name,
                ref.phone AS referrer_phone,
                rc.referral_count,
                COALESCE(ea.logged_bonus, 0) AS logged_bonus,
                COALESCE(ea.win_count, 0) AS win_count,
                COALESCE(ea.total_commission, 0) AS total_commission
            FROM players ref
            JOIN referred_counts rc ON rc.referrer_id = ref.user_id
            LEFT JOIN earnings_agg ea ON ea.referrer_id = ref.user_id
            ORDER BY total_commission DESC
        """)
        rows = cur.fetchall()

        # For referrers with no logged bonus history (referrals made before
        # the earnings ledger existed), approximate using the current bonus
        # setting × referral count, so the column isn't misleadingly 0.
        for row in rows:
            if row['logged_bonus'] == 0 and row['referral_count'] > 0:
                row['total_bonus'] = row['referral_count'] * current_bonus
                row['bonus_is_estimated'] = True
            else:
                row['total_bonus'] = row['logged_bonus']
                row['bonus_is_estimated'] = False

        return jsonify(rows)
    except Exception as e:
        print(f"Error in admin_referrals: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

@app.route('/admin/api/broadcast_telegram', methods=['POST'])
def admin_broadcast_telegram():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    message = data.get('message', '').strip()
    button_text = data.get('button_text', '').strip()
    button_url = data.get('button_url', '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400

    reply_markup = None
    if button_text and button_url:
        reply_markup = {'inline_keyboard': [[{'text': button_text, 'url': button_url}]]}

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT user_id FROM players WHERE bot_started = TRUE AND user_id > 0")
        chat_ids = [row['user_id'] for row in cur.fetchall()]
    finally:
        cur.close()
        put_db(conn)

    sent = 0
    failed = 0
    for chat_id in chat_ids:
        try:
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            if reply_markup:
                payload['reply_markup'] = reply_markup
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload, timeout=5
            )
            if resp.ok and resp.json().get('ok'):
                sent += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
        time.sleep(0.05)  # ~20 messages/sec, safely under Telegram's rate limit

    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'total': len(chat_ids)})
    
@app.route('/admin/api/weekly_top_winners')
def admin_weekly_top_winners():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        seven_days_ago = time.time() - (7 * 24 * 60 * 60)
        cur.execute("""
            SELECT gc.user_id, p.full_name,
                   SUM(g.prize_pool * 0.8 / NULLIF(jsonb_array_length(g.winner_card_numbers), 0)) AS total_won
            FROM games g
            JOIN game_cards gc ON gc.game_id = g.id
            JOIN players p ON p.user_id = gc.user_id
            WHERE g.status = 'finished'
              AND g.finished_at >= %s
              AND g.winner_card_numbers @> to_jsonb(gc.card_number)
              AND gc.user_id > 0
            GROUP BY gc.user_id, p.full_name
            ORDER BY total_won DESC
            LIMIT 10
        """, (seven_days_ago,))
        return jsonify(cur.fetchall())
    except Exception as e:
        print(f"Error in weekly_top_winners: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)
        
@app.route('/admin/api/delete_referral', methods=['POST'])
def admin_delete_referral():
    if not admin_auth(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    referrer_id = data.get('id')
    if not referrer_id:
        return jsonify({'error': 'Missing referrer_id'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Unlink everyone this person referred, and wipe their earnings ledger
        cur.execute("UPDATE players SET referred_by = NULL WHERE referred_by = %s", (referrer_id,))
        cur.execute("DELETE FROM referral_earnings WHERE referrer_id = %s", (referrer_id,))
        conn.commit()
        return jsonify({'success': True, 'message': f'All referrals reset for referrer {referrer_id}'})
    except Exception as e:
        conn.rollback()

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
    if target < 0 or target > 100:
        return jsonify({'error': 'Count must be 0-100'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        current = cur.fetchone()['cnt']
        if target > current:
            cur.execute("SELECT MIN(user_id) as min FROM players WHERE user_id < 0")
            row = cur.fetchone()
            next_id = (row['min'] - 1) if row and row['min'] else -1
            name_pool = ETHIOPIAN_MALE_NAMES.copy()
            random.shuffle(name_pool)
            for i in range(target - current):
                full_name = name_pool[i % len(name_pool)]
                cur.execute(
                    "INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)",
                    (next_id, f"bot_{abs(next_id)}", full_name, 1000)
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
       
@app.route('/api/sms_webhook', methods=['POST'])
def sms_webhook():
    # Get raw data
    raw = request.get_data(as_text=True)
    print(f"Raw data: {raw}")

    # Try to parse JSON
    try:
        data = request.get_json()
        if data:
            # Look for common keys
            sms_text = data.get('sms') or data.get('message') or data.get('text') or data.get('body')
            if sms_text:
                pass
            else:
                # If none found, use the whole data as string
                sms_text = raw
        else:
            sms_text = raw
    except:
        sms_text = raw

    if not sms_text:
        return jsonify({'error': 'No SMS text found'}), 400

    print(f"Parsed SMS: {sms_text}")

     # ----- Verify sender is genuinely Telebirr or M-Pesa -----
    ALLOWED_SMS_SENDERS = {'127', 'MPESA'}
    sender_match = re.search(r'From:\s*(\S+)', sms_text, re.IGNORECASE)
    sender_id = sender_match.group(1).strip() if sender_match else None
    if not sender_id or sender_id.upper() not in ALLOWED_SMS_SENDERS:
        print(f"Rejected SMS webhook — untrusted sender: {sender_id}", flush=True)
        return jsonify({'error': 'Untrusted sender, message ignored'}), 403
        
    # ----- Parse amount -----
    # Telebirr: "ETB 50.00" (amount after ETB). M-Pesa: "50.00 Birr" (amount before Birr).
    amount_match = re.search(r'ETB\s*([\d,]+(?:\.\d{1,2})?)', sms_text, re.IGNORECASE)
    if not amount_match:
        amount_match = re.search(r'([\d,]+(?:\.\d{1,2})?)\s*Birr', sms_text, re.IGNORECASE)
    if not amount_match:
        return jsonify({'error': 'Amount not found in SMS'}), 400
    amount = float(amount_match.group(1).replace(',', ''))

    # ----- Parse reference -----
    # Covers Telebirr ("transaction number is X") and M-Pesa ("Transaction number X").
    ref_match = re.search(r'transaction number\s*(?:is)?\s*([A-Z0-9]+)', sms_text, re.IGNORECASE)
    if not ref_match:
        return jsonify({'error': 'Transaction reference not found'}), 400

    tx_ref = ref_match.group(1).strip()

  # ----- Find and approve deposit -----
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, user_id, amount FROM deposits WHERE tx_ref = %s AND status = 'pending'", (tx_ref,))
        deposit = cur.fetchone()
        if not deposit:
            # No pending deposit yet — the SMS arrived before the player submitted
            # the form. Save it so the deposit endpoint can match against it later
            # instead of leaving the player stuck pending forever.
            cur.execute("""
                INSERT INTO unmatched_sms (tx_ref, amount, raw_sms, created_at)
                VALUES (%s, %s, %s, %s)
            """, (tx_ref, amount, sms_text, time.time()))
            conn.commit()
            return jsonify({'message': f'No pending deposit yet for reference {tx_ref} — stored for later matching'}), 200

        MIN_DEPOSIT = 50.0
        if amount < MIN_DEPOSIT:
            cur.execute("UPDATE deposits SET status = 'rejected', amount = %s WHERE id = %s", (amount, deposit['id']))
            conn.commit()
            return jsonify({'message': f'Deposit {tx_ref} below minimum ({amount} ETB) — marked rejected, no balance credited'}), 200

        # Always credit the REAL amount confirmed by the SMS, never the
        # amount the player claimed in the form — closes a gap where a
        # player could select/type a higher amount than they actually sent.
        cur.execute("UPDATE deposits SET status = 'approved', amount = %s WHERE id = %s", (amount, deposit['id']))
        cur.execute("UPDATE players SET balance = balance + %s WHERE user_id = %s",
                    (amount, deposit['user_id']))
        conn.commit()
        return jsonify({
            'success': True,
            'message': f'Deposit {tx_ref} approved for user {deposit["user_id"]}',
            'amount': amount
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        put_db(conn)

# ============================================================
#                     TELEGRAM WEBHOOK
# ============================================================
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

            if text.startswith('/start'):
                parts = text.split(maxsplit=1)
                referral_code = parts[1].strip() if len(parts) > 1 else ''
                if referral_code:
                    cur.execute("SELECT referred_by FROM players WHERE user_id = %s", (chat_id,))
                    existing = cur.fetchone()
                    if not existing or not existing['referred_by']:
                        cur.execute("SELECT user_id FROM referral_codes WHERE code = %s", (referral_code,))
                        referrer = cur.fetchone()
                        if referrer and referrer['user_id'] != chat_id:
                            cur.execute("UPDATE players SET referred_by = %s WHERE user_id = %s",
                                        (referrer['user_id'], chat_id))
                            conn.commit()
                            # NOTE: bonus is intentionally NOT awarded here.
                            # Clicking /start only links the referral — the
                            # actual bonus now only fires once the person
                            # completes real registration (see update_profile),
                            # closing a gap where a throwaway account could
                            # farm the bonus without ever registering.
                            print(f"DEBUG webhook: referred_by set for {chat_id} via /start code '{referral_code}'", flush=True)
        except Exception as e:
            print(f"Error setting bot_started: {e}")
        finally:
            cur.close()
            put_db(conn)
        if text.startswith('/start'):
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                'chat_id': chat_id,
                'text': "🎯 Welcome to Nef Bingo!\n\nTap below to play. Use /balance to check your balance.",
                'reply_markup': {
                    'inline_keyboard': [[
                        {'text': '🎮 Play Now', 'web_app': {'url': WEB_APP_URL}}
                    ]]
                }
            }, timeout=5)
        elif text == '/balance':
            send_telegram_message(chat_id, "Please log in to the game first to check your balance.")
        else:
            send_telegram_message(chat_id, "Send /start to get the game link.")
    return 'OK', 200
# ============================================================
#                     START SERVER
# ============================================================
# Run init_db() at import time, not just when executed directly as a
# script — this guarantees tables get created/updated on every deploy,
# regardless of whether Render starts the app via gunicorn or `python app.py`.
#
# Retry a few times — Render's database connection can drop transiently
# right at boot (especially on shared/free Postgres tiers). Without this,
# a single dropped connection crashes the whole app on deploy.
for _attempt in range(5):
    try:
        init_db()
        break
    except Exception as _e:
        print(f"init_db() attempt {_attempt + 1} failed: {_e}", flush=True)
        if _attempt == 4:
            raise
        time.sleep(3)

if __name__ == '__main__':
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM players WHERE user_id < 0")
        if cur.fetchone()['cnt'] == 0:
            create_bot_players(20)
    finally:
        cur.close()
        put_db(conn)
    # NOTE: do NOT call start_game_loop() here.
    # worker.py is the single source of truth for game progression (bots,
    # countdown, ball draws, finishing games). Running it here too caused
    # two processes to race on the same DB rows every second.
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
