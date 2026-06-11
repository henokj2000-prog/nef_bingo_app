import os
import psycopg2
from datetime import datetime, timedelta

# Use your actual environment variable name
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    """Return a new database connection."""
    return psycopg2.connect(DATABASE_URL)

# ------------------ DATABASE INITIALIZATION ------------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 1. Settings table (key-value, plain TEXT)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Insert default min_players if not exists
    cur.execute("""
        INSERT INTO settings (key, value) VALUES ('min_players', '2')
        ON CONFLICT (key) DO NOTHING
    """)

    # 2. Game state table (single row to track FROZEN/COUNTDOWN/PLAYING)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_state (
            id BOOLEAN PRIMARY KEY DEFAULT TRUE,
            status TEXT NOT NULL DEFAULT 'FROZEN',
            countdown_end TIMESTAMPTZ,
            inactive_cycles INTEGER DEFAULT 0,
            CHECK (id = TRUE)
        )
    """)
    cur.execute("""
        INSERT INTO game_state (id, status, countdown_end, inactive_cycles)
        VALUES (TRUE, 'FROZEN', NULL, 0)
        ON CONFLICT (id) DO NOTHING
    """)

    # 3. Round players table (temporary, cleared after each game)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS round_players (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount NUMERIC,
            joined_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

# ------------------ SETTINGS HELPERS ------------------
def get_setting(key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = %s
    """, (key, value, value))
    conn.commit()
    cur.close()
    conn.close()

# ------------------ GAME STATE HELPERS ------------------
def get_game_state():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status, countdown_end, inactive_cycles FROM game_state WHERE id = TRUE")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {
        "status": row[0],
        "countdown_end": row[1],
        "inactive_cycles": row[2]
    }

def set_game_state(status, countdown_end=None, inactive_cycles=None):
    conn = get_conn()
    cur = conn.cursor()
    query = "UPDATE game_state SET status = %s"
    params = [status]
    if countdown_end is not None:
        query += ", countdown_end = %s"
        params.append(countdown_end)
    else:
        query += ", countdown_end = NULL"
    if inactive_cycles is not None:
        query += ", inactive_cycles = %s"
        params.append(inactive_cycles)
    query += " WHERE id = TRUE"
    cur.execute(query, params)
    conn.commit()
    cur.close()
    conn.close()

# ------------------ ROUND PLAYERS HELPERS ------------------
def add_player_to_round(user_id, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO round_players (user_id, amount) VALUES (%s, %s)", (user_id, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_round_players_count():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM round_players")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def clear_round_players():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM round_players")
    conn.commit()
    cur.close()
    conn.close()
