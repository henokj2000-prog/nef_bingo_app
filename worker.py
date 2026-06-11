import time
import json
import random
import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL not set")

COLUMN_RANGES = {'B':(1,15),'I':(16,30),'N':(31,45),'G':(46,60),'O':(61,75)}
COL_LETTERS = ['B','I','N','G','O']
ALL_BALLS = [f"{col}{num}" for col,(low,high) in COLUMN_RANGES.items() for num in range(low, high+1)]

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def draw_ball(drawn_set):
    remaining = [b for b in ALL_BALLS if b not in drawn_set]
    return random.choice(remaining) if remaining else None

def check_bingo(card_data, drawn_set):
    marked = []
    for i in range(5):
        row_marked = []
        for j in range(5):
            cell = card_data[i][j]
            if cell == 'FREE':
                row_marked.append(True)
            else:
                ball = f"{COL_LETTERS[j]}{cell}"
                row_marked.append(ball in drawn_set)
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

def get_min_players():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'min_players'")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return int(row['value']) if row else 2

def process_games():
    conn = get_db()
    cur = conn.cursor()
    try:
        # 1. Start waiting games that have reached 30 seconds and enough players
        min_players = get_min_players()
        cur.execute("""
            SELECT g.id, COUNT(gc.id) as player_count
            FROM games g
            LEFT JOIN game_cards gc ON g.id = gc.game_id
            WHERE g.status = 'waiting'
              AND g.created_at <= %s
            GROUP BY g.id
            HAVING COUNT(gc.id) >= %s
        """, (time.time() - 30, min_players))
        ready_games = cur.fetchall()
        for game in ready_games:
            cur.execute("UPDATE games SET status = 'running' WHERE id = %s", (game['id'],))
            print(f"Started game {game['id']} with {game['player_count']} players")

        # 2. Process running games: draw balls and check winners
        cur.execute("SELECT id, drawn_balls, prize_pool FROM games WHERE status = 'running'")
        running_games = cur.fetchall()
        for game in running_games:
            drawn = set(json.loads(game['drawn_balls']) if game['drawn_balls'] else [])
            new_ball = draw_ball(drawn)
            if not new_ball:
                cur.execute("UPDATE games SET status = 'finished', finished_at = %s WHERE id = %s", (time.time(), game['id']))
                print(f"Game {game['id']} finished – no balls left")
                continue

            drawn.add(new_ball)
            cur.execute("UPDATE games SET drawn_balls = %s WHERE id = %s", (json.dumps(list(drawn)), game['id']))

            # Check winners
            cur.execute("SELECT user_id, card_data FROM game_cards WHERE game_id = %s", (game['id'],))
            cards = cur.fetchall()
            winners = []
            for card in cards:
                card_data = json.loads(card['card_data'])
                if check_bingo(card_data, drawn):
                    winners.append(card['user_id'])

            if winners:
                owner_cut = 0.2
                prize_pool = game['prize_pool']
                winners_share = prize_pool * (1 - owner_cut)
                per_winner = winners_share / len(winners)
                for uid in winners:
                    cur.execute("UPDATE players SET balance = balance + %s, total_won = total_won + %s, wins = wins + 1 WHERE user_id = %s", (per_winner, per_winner, uid))
                cur.execute("UPDATE games SET status = 'finished', finished_at = %s, winner_card_numbers = %s WHERE id = %s", (time.time(), json.dumps(winners), game['id']))
                print(f"Game {game['id']} finished. Winners: {winners}")
            else:
                print(f"Game {game['id']}: drew {new_ball} ({len(drawn)}/75)")

        conn.commit()
    except Exception as e:
        print(f"Error in worker: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("Worker started. Scanning for games every 2 seconds...")
    while True:
        process_games()
        time.sleep(2)
