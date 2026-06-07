import time
import json
from database import get_db, put_db, init_db, create_bot_players
from game.bingo_logic import draw_ball, check_bingo
from config import BALL_DRAW_INTERVAL_SECONDS, MAX_BALLS_PER_GAME, ADMIN_IDS, OWNER_CUT_PERCENT

def draw_loop(game_id):
    """Main game loop for a single game"""
    while True:
        time.sleep(BALL_DRAW_INTERVAL_SECONDS)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM games WHERE id = %s", (game_id,))
        game = cur.fetchone()
        if not game or game['status'] != 'running':
            cur.close()
            put_db(conn)
            break
        
        drawn = json.loads(game['drawn_balls'])
        
        # Check if max balls reached
        if len(drawn) >= MAX_BALLS_PER_GAME:
            # End game with no winner (or best match)
            cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
            # Calculate best match winners (same as original logic)
            cur.execute("SELECT * FROM game_cards WHERE game_id=%s", (game_id,))
            cards = cur.fetchall()
            player_matches = {}
            for card in cards:
                card_data = json.loads(card['card_data'])
                numbers = [cell for row in card_data for cell in row if cell != 'FREE']
                matches = sum(1 for num in numbers if num in set(int(b[1:]) for b in drawn))
                player_matches[card['user_id']] = player_matches.get(card['user_id'], 0) + matches
            if player_matches:
                best = max(player_matches.values())
                winner_ids = [uid for uid, m in player_matches.items() if m == best]
                total_pot = game['prize_pool']
                winners_share = round(total_pot * 0.80, 2)
                prize_per_winner = round(winners_share / len(winner_ids), 2) if winner_ids else 0
                for uid in winner_ids:
                    cur.execute("UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s",
                                (prize_per_winner, prize_per_winner, uid))
                cur.execute("UPDATE games SET winner_card_numbers=%s WHERE id=%s", (json.dumps([]), game_id))
                print(f"🏁 Game {game_id} ended after {len(drawn)} balls. Winners: {len(winner_ids)} × {prize_per_winner} ETB")
            conn.commit()
            cur.close()
            put_db(conn)
            break
        
        # Draw next ball
        ball = draw_ball(drawn)
        if ball is None:
            cur.execute("UPDATE games SET status='finished', finished_at=%s WHERE id=%s", (time.time(), game_id))
            conn.commit()
            cur.close()
            put_db(conn)
            print(f"⚠️ Game {game_id}: All 75 balls drawn, no winner.")
            break
        
        drawn.append(ball)
        cur.execute("UPDATE games SET drawn_balls=%s WHERE id=%s", (json.dumps(drawn), game_id))
        conn.commit()
        
        # Check for winners
        cur.execute("SELECT * FROM game_cards WHERE game_id=%s", (game_id,))
        cards = cur.fetchall()
        winners = []
        for c in cards:
            card_data = json.loads(c['card_data'])
            if check_bingo(card_data, set(drawn)):
                winners.append(c)
        
        if winners:
            total_pot = game['prize_pool']
            cur.execute("SELECT value FROM settings WHERE key='owner_cut_percent'")
            row = cur.fetchone()
            owner_cut = float(row['value']) if row else OWNER_CUT_PERCENT
            winner_percent = 100 - owner_cut
            winners_share = round(total_pot * winner_percent / 100, 2)
            
            # Referral commissions
            for winner in winners:
                cur.execute("SELECT referred_by FROM players WHERE user_id=%s", (winner['user_id'],))
                ref_data = cur.fetchone()
                if ref_data and ref_data['referred_by']:
                    cur.execute("SELECT value FROM settings WHERE key='referral_commission_percent'")
                    comm_row = cur.fetchone()
                    comm_percent = float(comm_row['value']) if comm_row else 5.0
                    commission = round(total_pot * (comm_percent / 100), 2)
                    cur.execute("""
                        INSERT INTO referral_commissions (referrer_id, referred_id, game_id, amount, status, created_at)
                        VALUES (%s, %s, %s, %s, 'pending', %s)
                    """, (ref_data['referred_by'], winner['user_id'], game_id, commission, time.time()))
            
            prize_per_winner = round(winners_share / len(winners), 2)
            winner_card_numbers = [w['card_number'] for w in winners]
            for winner in winners:
                cur.execute("UPDATE players SET balance=balance+%s, wins=wins+1, total_won=total_won+%s WHERE user_id=%s",
                            (prize_per_winner, prize_per_winner, winner['user_id']))
            cur.execute("UPDATE games SET status='finished', finished_at=%s, winner_card_numbers=%s WHERE id=%s",
                        (time.time(), json.dumps(winner_card_numbers), game_id))
            conn.commit()
            print(f"✅ Game {game_id} FINISHED! {len(winners)} winner(s) × {prize_per_winner} ETB each")
            cur.close()
            put_db(conn)
            break
        
        cur.close()
        put_db(conn)

def main_loop():
    """Main worker loop - picks up waiting games and runs them"""
    while True:
        conn = get_db()
        cur = conn.cursor()
        now = time.time()
        # Find a game that has been waiting for at least 30 seconds
        cur.execute("""
            SELECT id FROM games 
            WHERE status = 'waiting' AND created_at <= %s 
            ORDER BY id LIMIT 1
        """, (now - 30,))
        game = cur.fetchone()
        cur.close()
        put_db(conn)
        
        if game:
            game_id = game['id']
            # Mark game as running
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE games SET status='running', started_at=%s WHERE id=%s AND status='waiting'", (time.time(), game_id))
            conn2.commit()
            cur2.close()
            put_db(conn2)
            # Run the game engine
            draw_loop(game_id)
        else:
            time.sleep(5)

if __name__ == '__main__':
    init_db()
    create_bot_players()
    print("🚀 Worker started – game engine running (2-second draws)")
    main_loop()
