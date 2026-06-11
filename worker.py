import time
import json
import random
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

# Import your existing database helpers
from database import (
    get_conn,
    get_game_state,
    set_game_state,
    get_round_players_count,
    clear_round_players,
    add_player_to_round,
    get_setting,
    set_setting
)

# ==================== BINGO LOGIC ====================
COLUMN_RANGES = {'B':(1,15),'I':(16,30),'N':(31,45),'G':(46,60),'O':(61,75)}
COL_LETTERS = ['B','I','N','G','O']
ALL_BALLS = [f"{col}{num}" for col,(low,high) in COLUMN_RANGES.items() for num in range(low, high+1)]

def generate_card():
    cols = []
    for col in COLUMN_RANGES:
        low, high = COLUMN_RANGES[col]
        cols.append(random.sample(range(low, high + 1), 5))
    rows = []
    for i in range(5):
        row = [cols[j][i] for j in range(5)]
        rows.append(row)
    rows[2][2] = 'FREE'
    return rows

def draw_ball(drawn_set):
    remaining = [b for b in ALL_BALLS if b not in drawn_set]
    return random.choice(remaining) if remaining else None

def check_bingo(card, drawn_set):
    marked = []
    for i in range(5):
        row_marked = []
        for j in range(5):
            cell = card[i][j]
            if cell == 'FREE':
                row_marked.append(True)
            else:
                col_letter = COL_LETTERS[j]
                ball_str = f"{col_letter}{cell}"
                row_marked.append(ball_str in drawn_set)
        marked.append(row_marked)
    for i in range(5):
        if all(marked[i][j] for j in range(5)):
            return True
    for j in range(5):
        if all(marked[i][j] for i in range(5)):
            return True
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4-i] for i in range(5)):
        return True
    return False

# ==================== BINGO ROUND TABLES (create if not exist) ====================
def init_bingo_tables():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bingo_round (
            id SERIAL PRIMARY KEY,
            round_number INTEGER,
            drawn_balls JSONB DEFAULT '[]'::JSONB,
            next_draw_time TIMESTAMPTZ,
            winner_user_id BIGINT,
            status TEXT DEFAULT 'PLAYING'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bingo_cards (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            round_id INTEGER REFERENCES bingo_round(id),
            card JSONB NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# ==================== START A NEW ROUND ====================
def start_new_round():
    conn = get_conn()
    cur = conn.cursor()
    # Get all players who joined during COUNTDOWN
    cur.execute("SELECT user_id, amount FROM round_players")
    players = cur.fetchall()
    if not players:
        cur.close()
        conn.close()
        return False

    # Create a new bingo round
    cur.execute("""
        INSERT INTO bingo_round (round_number, next_draw_time, status)
        VALUES (COALESCE((SELECT MAX(round_number)+1 FROM bingo_round), 1), %s, 'PLAYING')
        RETURNING id
    """, (datetime.now(timezone.utc) + timedelta(seconds=5),))
    round_id = cur.fetchone()[0]

    # Insert cards for each player
    for user_id, amount in players:
        card = generate_card()
        cur.execute("INSERT INTO bingo_cards (user_id, round_id, card) VALUES (%s, %s, %s)",
                    (user_id, round_id, json.dumps(card)))
    conn.commit()
    cur.close()
    conn.close()
    print(f"🎲 Started new bingo round {round_id} with {len(players)} players.")
    return True

# ==================== MAIN GAME LOOP ====================
def game_loop():
    # Ensure tables exist
    init_bingo_tables()
    
    while True:
        state = get_game_state()
        now = datetime.now(timezone.utc)
        
        # --- FROZEN state ---
        if state["status"] == "FROZEN":
            # Nothing to do; a stake click will change state to COUNTDOWN
            time.sleep(1)
            continue
        
        # --- COUNTDOWN state ---
        if state["status"] == "COUNTDOWN":
            # Check if countdown has ended
            if state["countdown_end"] and now >= state["countdown_end"]:
                player_count = get_round_players_count()
                min_players = int(get_setting("min_players") or 2)
                
                if player_count >= min_players:
                    # Enough players → start the game
                    set_game_state("PLAYING")
                    start_new_round()
                elif player_count > 0:
                    # Not enough players, restart countdown
                    new_countdown = now + timedelta(seconds=30)
                    set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                    print(f"⏳ Not enough players ({player_count}/{min_players}). Countdown restarted.")
                else:
                    # No players at all → increment empty cycle counter
                    inactive = state["inactive_cycles"] + 1
                    if inactive >= 4:
                        # 4 empty cycles → freeze
                        set_game_state("FROZEN")
                        print("❄️ Game frozen – no activity for 2 minutes.")
                    else:
                        new_countdown = now + timedelta(seconds=30)
                        set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=inactive)
                        print(f"🔄 Empty cycle {inactive}/4 – countdown restarted.")
            else:
                # Countdown still running – just wait
                time.sleep(0.5)
            continue
        
        # --- PLAYING state ---
        if state["status"] == "PLAYING":
            conn = get_conn()
            cur = conn.cursor()
            # Get the current active round (the most recent one that is still PLAYING)
            cur.execute("""
                SELECT id, drawn_balls, next_draw_time, winner_user_id
                FROM bingo_round
                WHERE status = 'PLAYING'
                ORDER BY id DESC LIMIT 1
            """)
            round_row = cur.fetchone()
            if not round_row:
                # No active round – should not happen, but fallback
                set_game_state("FROZEN")
                cur.close()
                conn.close()
                continue
            
            round_id, drawn_balls_json, next_draw, winner = round_row
            drawn_balls = set(json.loads(drawn_balls_json) if drawn_balls_json else [])
            
            # If winner already exists, finish the round
            if winner:
                cur.execute("UPDATE bingo_round SET status = 'FINISHED' WHERE id = %s", (round_id,))
                conn.commit()
                cur.close()
                conn.close()
                clear_round_players()
                # Start a new countdown for next round
                new_countdown = datetime.now(timezone.utc) + timedelta(seconds=30)
                set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                print(f"🏁 Round {round_id} finished. Winner: {winner}")
                continue
            
            # Draw a new ball if it's time
            if next_draw and now >= next_draw:
                new_ball = draw_ball(drawn_balls)
                if new_ball is None:
                    # No balls left – end round without winner
                    cur.execute("UPDATE bingo_round SET status = 'FINISHED' WHERE id = %s", (round_id,))
                    conn.commit()
                    cur.close()
                    conn.close()
                    clear_round_players()
                    new_countdown = datetime.now(timezone.utc) + timedelta(seconds=30)
                    set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                    print(f"🏁 Round {round_id} ended – all balls drawn, no winner.")
                    continue
                
                drawn_balls.add(new_ball)
                next_draw_time = now + timedelta(seconds=5)
                cur.execute("""
                    UPDATE bingo_round
                    SET drawn_balls = %s, next_draw_time = %s
                    WHERE id = %s
                """, (json.dumps(list(drawn_balls)), next_draw_time, round_id))
                conn.commit()
                
                # Check for winners
                cur.execute("SELECT user_id, card FROM bingo_cards WHERE round_id = %s", (round_id,))
                cards = cur.fetchall()
                winner_found = False
                for uid, card_json in cards:
                    card = json.loads(card_json)
                    if check_bingo(card, drawn_balls):
                        # Winner found
                        cur.execute("UPDATE bingo_round SET winner_user_id = %s, status = 'FINISHED' WHERE id = %s",
                                    (uid, round_id))
                        conn.commit()
                        winner_found = True
                        print(f"🏆 Winner! User {uid} got BINGO in round {round_id}")
                        # Prize distribution would go here if you have prize pool logic
                        # (You can extend this to update player balances)
                        break
                
                if winner_found:
                    cur.close()
                    conn.close()
                    clear_round_players()
                    new_countdown = datetime.now(timezone.utc) + timedelta(seconds=30)
                    set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                    continue
                else:
                    print(f"🎲 New ball: {new_ball} | Drawn: {len(drawn_balls)}/75")
            
            cur.close()
            conn.close()
            time.sleep(1)
            continue

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    # Initialize database (creates tables if missing)
    from database import init_db
    init_db()          # creates settings, game_state, round_players
    init_bingo_tables() # creates bingo_round, bingo_cards
    
    print("🚀 Game loop running. State machine active.")
    game_loop()
