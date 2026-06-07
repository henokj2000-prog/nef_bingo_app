rm database.py
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import time
import json
import secrets
import string
import random
from config import DATABASE_URL, BOT_MIN_PLAYERS

db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)

def get_db():
    return db_pool.getconn()

def put_db(conn):
    db_pool.putconn(conn)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_won REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            phone TEXT UNIQUE,
            language TEXT DEFAULT 'en',
            chat_id TEXT,
            referred_by BIGINT,
            referral_code TEXT UNIQUE,
            referral_bonus_earned REAL DEFAULT 0
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            stake INTEGER,
            status TEXT DEFAULT 'waiting',
            prize_pool REAL DEFAULT 0,
            drawn_balls TEXT DEFAULT '[]',
            winner_card_numbers TEXT DEFAULT '[]',
            created_at REAL,
            started_at REAL,
            finished_at REAL,
            cancelled INTEGER DEFAULT 0
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_cards (
            id SERIAL PRIMARY KEY,
            game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
            user_id BIGINT,
            card_number INTEGER,
            card_data TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            tx_ref TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            platform TEXT,
            account_no TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount REAL,
            reason TEXT,
            admin_note TEXT,
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            message TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_broadcast INTEGER DEFAULT 1
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY,
            role TEXT DEFAULT 'admin',
            added_by BIGINT,
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            created_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_commissions (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            paid_at REAL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referral_commissions_archive (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL,
            game_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            paid_at REAL,
            payment_week_start REAL,
            payment_week_end REAL
        )
    """)
    
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('telebirr_number', '0929 001 000'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('cbe_number', '1000061737212'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('deposit_bonus_percent', '0'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('referral_commission_percent', '5'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('referral_bonus_amount', '10'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('owner_cut_percent', '20'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('max_balls_per_game', '75'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_enabled', '1'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_cards_per_game', '1'))
    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('bot_min_players', '2'))
    
    conn.commit()
    cur.close()
    put_db(conn)
    print("✅ Database initialized (PostgreSQL)")

def create_bot_players():
    bot_names = [
        ("Admasu Kebe", "admasu_k"), ("Yichilal", "yichilal"),
        ("Aradaw Tade", "aradaw_t"), ("Shime Gondar", "shime_g"),
        ("Emu Konjo", "emu_k"), ("Tigist Desta", "tigist_d"),
        ("Biruk Alemu", "biruk_a"), ("Meron Assefa", "meron_a"),
        ("Dawit Mekonnen", "dawit_m"), ("Hana Tesfaye", "hana_t")
    ]
    conn = get_db()
    cur = conn.cursor()
    bot_id = -1
    for full_name, username in bot_names:
        cur.execute("SELECT user_id FROM players WHERE user_id = %s", (bot_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO players (user_id, username, full_name, balance) VALUES (%s, %s, %s, %s)", 
                        (bot_id, username, full_name, 1000))
        bot_id -= 1
    conn.commit()
    cur.close()
    put_db(conn)

def generate_referral_code():
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT code FROM referral_codes WHERE code = %s", (code,))
        existing = cur.fetchone()
        cur.close()
        put_db(conn)
        if not existing:
            return code

def create_referral_code_for_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()
    if not existing:
        code = generate_referral_code()
        cur.execute("INSERT INTO referral_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
        cur.execute("UPDATE players SET referral_code = %s WHERE user_id = %s", (code, user_id))
        conn.commit()
        cur.close()
        put_db(conn)
        return code
    cur.close()
    put_db(conn)
    return existing['code']

def award_referral_bonus(referrer_id, referred_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'referral_bonus_amount'")
    row = cur.fetchone()
    bonus_amt = float(row['value']) if row else 10.0
    cur.execute("UPDATE players SET balance = balance + %s, referral_bonus_earned = referral_bonus_earned + %s WHERE user_id = %s", 
                (bonus_amt, bonus_amt, referrer_id))
    cur.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (%s, %s, %s)", 
                (referrer_id, referred_id, time.time()))
    conn.commit()
    cur.close()
    put_db(conn)
    print(f"🎁 Referral bonus: +{bonus_amt} ETB to user {referrer_id} for referring {referred_id}")

def add_bot_to_game(game_id, stake):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM players WHERE user_id < 0")
    bot_ids = [row['user_id'] for row in cur.fetchall()]
    if not bot_ids:
        cur.close()
        put_db(conn)
        return None
    cur.execute("SELECT DISTINCT user_id FROM game_cards WHERE game_id=%s AND user_id < 0", (game_id,))
    existing_bot_ids = [row['user_id'] for row in cur.fetchall()]
    available_bots = [bid for bid in bot_ids if bid not in existing_bot_ids]
    if not available_bots:
        cur.close()
        put_db(conn)
        return None
    bot_id = random.choice(available_bots)
    cur.execute("SELECT balance FROM players WHERE user_id=%s", (bot_id,))
    bot = cur.fetchone()
    if bot['balance'] < stake:
        cur.execute("UPDATE players SET balance=balance+1000 WHERE user_id=%s", (bot_id,))
    cur.execute("SELECT card_number FROM game_cards WHERE game_id=%s", (game_id,))
    taken = [row['card_number'] for row in cur.fetchall()]
    available_cards = [i for i in range(1, 501) if i not in taken]
    if not available_cards:
        cur.close()
        put_db(conn)
        return None
    card_num = random.choice(available_cards)
    from game.bingo_logic import generate_card
    cur.execute("INSERT INTO game_cards (game_id, user_id, card_number, card_data) VALUES (%s, %s, %s, %s)",
                (game_id, bot_id, card_num, json.dumps(generate_card())))
    cur.execute("UPDATE players SET balance=balance-%s, games_played=games_played+1 WHERE user_id=%s", (stake, bot_id))
    cur.execute("UPDATE games SET prize_pool=prize_pool+%s WHERE id=%s", (stake, game_id))
    conn.commit()
    cur.close()
    put_db(conn)
    return bot_id

def count_players_in_game(game_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM game_cards WHERE game_id=%s", (game_id,))
    row = cur.fetchone()
    cur.close()
    put_db(conn)
    return row['cnt'] if row else 0
