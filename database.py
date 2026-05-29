import sqlite3
import json
from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        username TEXT, full_name TEXT,
        balance REAL DEFAULT 0,
        total_won REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        stake REAL NOT NULL,
        status TEXT DEFAULT 'waiting',
        prize_pool REAL DEFAULT 0,
        drawn_balls TEXT DEFAULT '[]',
        winners TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now')),
        started_at TEXT, finished_at TEXT
    );
    CREATE TABLE IF NOT EXISTS player_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER, user_id INTEGER,
        card_data TEXT, card_index INTEGER DEFAULT 0,
        is_winner INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS deposits (
        deposit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount REAL, platform TEXT,
        tx_ref TEXT, status TEXT DEFAULT 'pending',
        screenshot TEXT, created_at TEXT DEFAULT (datetime('now')),
        reviewed_at TEXT, reviewed_by INTEGER
    );
    CREATE TABLE IF NOT EXISTS withdrawals (
        wd_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount REAL, platform TEXT,
        account_no TEXT, status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    );
    """)
    conn.commit()
    conn.close()

def upsert_player(user_id, username, full_name):
    conn = get_conn()
    conn.execute("""INSERT INTO players (user_id, username, full_name)
        VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        username=excluded.username, full_name=excluded.full_name""",
        (user_id, username, full_name))
    conn.commit(); conn.close()

def get_player(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_balance(user_id, delta):
    conn = get_conn()
    conn.execute("UPDATE players SET balance=balance+? WHERE user_id=?", (delta, user_id))
    conn.commit(); conn.close()

def get_balance(user_id):
    conn = get_conn()
    row = conn.execute("SELECT balance FROM players WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["balance"] if row else 0

def create_game(stake):
    conn = get_conn()
    cur = conn.execute("INSERT INTO games (stake) VALUES (?)", (stake,))
    game_id = cur.lastrowid
    conn.commit(); conn.close()
    return game_id

def get_game(game_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
    conn.close()
    if not row: return None
    g = dict(row)
    g["drawn_balls"] = json.loads(g["drawn_balls"])
    g["winners"] = json.loads(g["winners"])
    return g

def get_active_game(stake=None):
    conn = get_conn()
    if stake:
        row = conn.execute("SELECT * FROM games WHERE status='waiting' AND stake=? ORDER BY game_id DESC LIMIT 1", (stake,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM games WHERE status='waiting' ORDER BY game_id DESC LIMIT 1").fetchone()
    conn.close()
    if not row: return None
    g = dict(row)
    g["drawn_balls"] = json.loads(g["drawn_balls"])
    g["winners"] = json.loads(g["winners"])
    return g

def update_game(game_id, **kwargs):
    if not kwargs: return
    conn = get_conn()
    for k, v in kwargs.items():
        if isinstance(v, (list, dict)):
            kwargs[k] = json.dumps(v)
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [game_id]
    conn.execute(f"UPDATE games SET {sets} WHERE game_id=?", vals)
    conn.commit(); conn.close()

def save_card(game_id, user_id, card_data, card_index):
    conn = get_conn()
    conn.execute("INSERT INTO player_cards (game_id,user_id,card_data,card_index) VALUES (?,?,?,?)",
        (game_id, user_id, json.dumps(card_data), card_index))
    conn.commit(); conn.close()

def get_player_cards(game_id, user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM player_cards WHERE game_id=? AND user_id=?", (game_id, user_id)).fetchall()
    conn.close()
    cards = []
    for r in rows:
        d = dict(r); d["card_data"] = json.loads(d["card_data"]); cards.append(d)
    return cards

def get_all_cards_for_game(game_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM player_cards WHERE game_id=?", (game_id,)).fetchall()
    conn.close()
    cards = []
    for r in rows:
        d = dict(r); d["card_data"] = json.loads(d["card_data"]); cards.append(d)
    return cards

def count_cards_for_player(game_id, user_id):
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM player_cards WHERE game_id=? AND user_id=?", (game_id, user_id)).fetchone()
    conn.close()
    return row["cnt"] if row else 0

def count_players_in_game(game_id):
    conn = get_conn()
    row = conn.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM player_cards WHERE game_id=?", (game_id,)).fetchone()
    conn.close()
    return row["cnt"] if row else 0

def get_players_in_game(game_id):
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT user_id FROM player_cards WHERE game_id=?", (game_id,)).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]

def create_deposit(user_id, amount, platform, tx_ref=None, screenshot=None):
    conn = get_conn()
    cur = conn.execute("INSERT INTO deposits (user_id,amount,platform,tx_ref,screenshot) VALUES (?,?,?,?,?)",
        (user_id, amount, platform, tx_ref, screenshot))
    dep_id = cur.lastrowid
    conn.commit(); conn.close()
    return dep_id

def get_deposit(deposit_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM deposits WHERE deposit_id=?", (deposit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_deposit(deposit_id, **kwargs):
    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [deposit_id]
    conn.execute(f"UPDATE deposits SET {sets} WHERE deposit_id=?", vals)
    conn.commit(); conn.close()

def pending_deposits():
    conn = get_conn()
    rows = conn.execute("""SELECT d.*, p.full_name, p.username FROM deposits d
        JOIN players p ON d.user_id=p.user_id
        WHERE d.status='pending' ORDER BY d.created_at""").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_withdrawal(user_id, amount, platform, account_no):
    conn = get_conn()
    cur = conn.execute("INSERT INTO withdrawals (user_id,amount,platform,account_no) VALUES (?,?,?,?)",
        (user_id, amount, platform, account_no))
    wd_id = cur.lastrowid
    conn.commit(); conn.close()
    return wd_id

def get_stats():
    conn = get_conn()
    stats = {}
    stats["total_players"] = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    stats["total_games"] = conn.execute("SELECT COUNT(*) FROM games WHERE status='finished'").fetchone()[0]
    stats["total_revenue"] = conn.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='confirmed'").fetchone()[0]
    stats["pending_deposits"] = conn.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0]
    conn.close()
    return stats
