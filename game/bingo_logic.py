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

        # Check for a running game → spectator mode
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

        # ----- Find or create a VALID waiting room -----
        cur.execute("""
            SELECT id FROM games
            WHERE stake = %s AND status = 'waiting' AND cancelled = 0
              AND created_at + 30 > %s
            ORDER BY id DESC LIMIT 1
        """, (stake, time.time()))
        game_row = cur.fetchone()

        if game_row:
            game_id = game_row['id']
        else:
            # Clean up any stale waiting games for this stake
            cur.execute("DELETE FROM games WHERE stake = %s AND status = 'waiting' AND cancelled = 0", (stake,))
            conn.commit()
            # Create a fresh one
            cur.execute(
                "INSERT INTO games (stake, prize_pool, created_at, status, drawn_balls) VALUES (%s, 0, %s, 'waiting', '[]')",
                (stake, time.time())
            )
            conn.commit()
            cur.execute("SELECT id FROM games WHERE stake = %s AND status = 'waiting' ORDER BY id DESC LIMIT 1", (stake,))
            game_row = cur.fetchone()
            game_id = game_row['id']

        # ----- Return game info -----
        cur.execute("SELECT prize_pool, created_at FROM games WHERE id = %s", (game_id,))
        ginfo = cur.fetchone()
        created_at = ginfo['created_at']
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
            'status': 'waiting',
            'players': players_cnt,
            'taken_cards': taken,
            'countdown': countdown
        })
    finally:
        cur.close()
        put_db(conn)
