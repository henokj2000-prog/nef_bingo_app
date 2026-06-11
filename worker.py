import time
import threading
import os
import json
import random
import requests
from datetime import datetime, timedelta
from database import (
    init_db,
    get_game_state, set_game_state,
    get_round_players_count, clear_round_players,
    add_player_to_round,
    get_setting, set_setting,
    get_conn
)

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")          # <-- set in Render / Termux
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==================== BINGO LOGIC ====================
COLUMN_RANGES = {
    'B': (1, 15),
    'I': (16, 30),
    'N': (31, 45),
    'G': (46, 60),
    'O': (61, 75)
}
COL_LETTERS = ['B', 'I', 'N', 'G', 'O']

ALL_BALLS = []
for col, (low, high) in COLUMN_RANGES.items():
    for num in range(low, high + 1):
        ALL_BALLS.append(f"{col}{num}")

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

def draw_ball(drawn_balls_set):
    remaining = [b for b in ALL_BALLS if b not in drawn_balls_set]
    return random.choice(remaining) if remaining else None

def check_bingo(card, drawn_balls_set):
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
                row_marked.append(ball_str in drawn_balls_set)
        marked.append(row_marked)

    for i in range(5):
        if all(marked[i][j] for j in range(5)):
            return True
    for j in range(5):
        if all(marked[i][j] for i in range(5)):
            return True
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4 - i] for i in range(5)):
        return True
    return False

# ==================== BINGO DATABASE TABLES ====================
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

# ==================== SEND MESSAGE ====================
def send_message(user_id, text):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": user_id,
            "text": text
        })
    except Exception as e:
        print(f"Failed to send message to {user_id}: {e}")

# ==================== START GAME ====================
def start_game():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount FROM round_players")
    players = cur.fetchall()
    if not players:
        cur.close()
        conn.close()
        return

    cur.execute(
        "INSERT INTO bingo_round (round_number, next_draw_time, status) VALUES (1, %s, 'PLAYING') RETURNING id",
        (datetime.utcnow() + timedelta(seconds=5),)
    )
    round_id = cur.fetchone()[0]

    for user_id, amount in players:
        card = generate_card()
        cur.execute(
            "INSERT INTO bingo_cards (user_id, round_id, card) VALUES (%s, %s, %s)",
            (user_id, round_id, json.dumps(card))
        )
        send_message(user_id, "🎲 A new Bingo round has started! Your card:")
        lines = ["  " + "  ".join(COL_LETTERS)]
        for i, row in enumerate(card):
            lines.append(f"{i+1} " + " ".join(str(c).rjust(2) if c != 'FREE' else 'FR' for c in row))
        send_message(user_id, "```\n" + "\n".join(lines) + "\n```")

    conn.commit()
    cur.close()
    conn.close()
    print(f"▶️  Bingo round started with {len(players)} players (round {round_id}).")

# ==================== IS GAME OVER? ====================
def is_game_over():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT winner_user_id FROM bingo_round WHERE status = 'PLAYING' ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row and row[0] is not None

# ==================== GAME LOOP ====================
def game_loop():
    while True:
        state = get_game_state()
        now = datetime.utcnow()

        if state["status"] == "COUNTDOWN":
            if state["countdown_end"] and now >= state["countdown_end"]:
                player_count = get_round_players_count()
                min_players = int(get_setting("min_players") or 2)

                if player_count >= min_players:
                    set_game_state("PLAYING")
                    start_game()

                elif player_count > 0:
                    new_countdown = now + timedelta(seconds=30)
                    set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                    print(f"⏳ Waiting for more players ({player_count}/{min_players})")

                else:
                    inactive = state["inactive_cycles"] + 1
                    if inactive >= 4:
                        set_game_state("FROZEN")
                        print("❄️  Game frozen – no activity for 2 minutes.")
                    else:
                        new_countdown = now + timedelta(seconds=30)
                        set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=inactive)
                        print(f"🔄 Empty cycle {inactive}/4")

        elif state["status"] == "PLAYING":
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, drawn_balls, next_draw_time, winner_user_id
                FROM bingo_round
                WHERE status = 'PLAYING'
                ORDER BY id DESC LIMIT 1
            """)
            round_row = cur.fetchone()
            if round_row:
                round_id, drawn_balls_json, next_draw, winner = round_row
                drawn_balls = set(json.loads(drawn_balls_json) if drawn_balls_json else [])

                if winner:
                    cur.execute("UPDATE bingo_round SET status = 'FINISHED' WHERE id = %s", (round_id,))
                    conn.commit()
                    cur.close()
                    conn.close()
                    clear_round_players()
                    new_countdown = now + timedelta(seconds=30)
                    set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                    print(f"🏁 Bingo round {round_id} ended (winner: {winner}).")
                    continue

                if next_draw and now >= next_draw:
                    new_ball = draw_ball(drawn_balls)
                    if new_ball:
                        drawn_balls.add(new_ball)
                        cur.execute("""
                            UPDATE bingo_round
                            SET drawn_balls = %s, next_draw_time = %s
                            WHERE id = %s
                        """, (json.dumps(list(drawn_balls)), now + timedelta(seconds=5), round_id))

                        cur.execute("SELECT user_id, card FROM bingo_cards WHERE round_id = %s", (round_id,))
                        winner_found = False
                        for uid, card_json in cur.fetchall():
                            card = json.loads(card_json)
                            if check_bingo(card, drawn_balls):
                                cur.execute("""
                                    UPDATE bingo_round SET winner_user_id = %s, status = 'FINISHED' WHERE id = %s
                                """, (uid, round_id))
                                send_message(uid, "🎉 BINGO! You won!")
                                cur.execute("SELECT user_id FROM bingo_cards WHERE round_id = %s AND user_id != %s", (round_id, uid))
                                for other in cur.fetchall():
                                    send_message(other[0], f"😞 Player {uid} got BINGO. Better luck next time!")
                                winner_found = True
                                break

                        if not winner_found:
                            cur.execute("SELECT user_id FROM bingo_cards WHERE round_id = %s", (round_id,))
                            for uid in cur.fetchall():
                                send_message(uid[0], f"🔮 New ball: {new_ball}")
                    else:
                        cur.execute("UPDATE bingo_round SET status = 'FINISHED' WHERE id = %s", (round_id,))
                        cur.execute("SELECT user_id FROM bingo_cards WHERE round_id = %s", (round_id,))
                        for uid in cur.fetchall():
                            send_message(uid[0], "🏁 All balls drawn. No winner this round.")
                        print(f"🏁 Bingo round {round_id} ended in a draw.")
                    conn.commit()

            cur.close()
            conn.close()

            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id FROM bingo_round WHERE status = 'PLAYING'")
            active = cur.fetchone()
            cur.close()
            conn.close()
            if not active:
                clear_round_players()
                new_countdown = now + timedelta(seconds=30)
                set_game_state("COUNTDOWN", countdown_end=new_countdown, inactive_cycles=0)
                print("🏁 Game over. New countdown started.")

        time.sleep(1)

# ==================== STAKE CLICK HANDLER ====================
def handle_stake_click(user_id, amount):
    state = get_game_state()
    now = datetime.utcnow()

    if state["status"] == "FROZEN":
        countdown_end = now + timedelta(seconds=30)
        set_game_state("COUNTDOWN", countdown_end=countdown_end, inactive_cycles=0)
        add_player_to_round(user_id, amount)
        send_message(user_id, f"✅ You joined! Game starts in 30 seconds.")

    elif state["status"] == "COUNTDOWN":
        add_player_to_round(user_id, amount)
        seconds_left = (
            int((state["countdown_end"] - now).total_seconds())
            if state["countdown_end"] else 0
        )
        send_message(user_id, f"✅ Joined. Round starts in {seconds_left}s.")

    elif state["status"] == "PLAYING":
        send_message(user_id, "🎮 Game is in progress. Please wait until it ends.")

# ==================== ADMIN COMMAND ====================
def set_min_players(admin_user_id, new_min):
    set_setting("min_players", str(new_min))
    send_message(admin_user_id, f"🔧 Minimum players set to {new_min}.")

# ==================== TELEGRAM BOT ====================
def start_bot():
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler

    async def stake_callback(update, context):
        user_id = update.effective_user.id
        amount = float(update.callback_query.data.split("_")[1])
        handle_stake_click(user_id, amount)
        await update.callback_query.answer()

    async def setmin_command(update, context):
        if not context.args:
            await update.message.reply_text("Usage: /setmin <number>")
            return
        new_min = int(context.args[0])
        set_min_players(update.effective_user.id, new_min)
        await update.message.reply_text(f"Minimum players set to {new_min}")

    async def start_command(update, context):
        await update.message.reply_text("Welcome! Press a stake button to join the next Bingo round.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(stake_callback, pattern="^stake_"))
    app.add_handler(CommandHandler("setmin", setmin_command))
    app.add_handler(CommandHandler("start", start_command))

    print("🤖 Bot polling started...")
    app.run_polling()

# ==================== MAIN ====================
if __name__ == "__main__":
    init_db()
    init_bingo_tables()
    print("🗄️  Database ready.")

    loop_thread = threading.Thread(target=game_loop, daemon=True)
    loop_thread.start()
    print("🚀 Game loop running in background.")

    start_bot()
