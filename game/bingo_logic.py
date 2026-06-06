import random

COLUMN_RANGES = {
    'B': (1, 15),
    'I': (16, 30),
    'N': (31, 45),
    'G': (46, 60),
    'O': (61, 75)
}

def generate_card():
    """Generate a 5x5 bingo card with unique numbers per column, FREE in center."""
    cols = []
    for col in COLUMN_RANGES:
        low, high = COLUMN_RANGES[col]
        cols.append(random.sample(range(low, high+1), 5))
    rows = []
    for i in range(5):
        row = [cols[j][i] for j in range(5)]
        rows.append(row)
    rows[2][2] = 'FREE'
    return rows

def draw_ball(drawn_balls):
    """Return a new ball (e.g., 'B12') not yet drawn, or None if all 75 drawn."""
    all_balls = []
    for col, (low, high) in COLUMN_RANGES.items():
        for num in range(low, high+1):
            all_balls.append(f"{col}{num}")
    remaining = [b for b in all_balls if b not in drawn_balls]
    return random.choice(remaining) if remaining else None

def check_bingo(card, drawn_balls_set):
    """
    card: 5x5 grid, 'FREE' in center.
    drawn_balls_set: set of strings like {'B12', 'I25', ...}
    Returns True if any row, column, or diagonal is fully marked.
    """
    # Build a set of drawn ball strings for O(1) lookup
    drawn_set = set(drawn_balls_set)
    
    # Create a 5x5 boolean grid: True if cell is marked
    marked = []
    for i in range(5):
        row_marked = []
        for j in range(5):
            cell = card[i][j]
            if cell == 'FREE':
                row_marked.append(True)
            else:
                # cell is an integer, e.g., 12
                # Need to check if any drawn ball matches this number AND column letter
                # But careful: column letter is determined by position j (0=B,1=I,2=N,3=G,4=O)
                col_letter = ['B','I','N','G','O'][j]
                ball_str = f"{col_letter}{cell}"
                row_marked.append(ball_str in drawn_set)
        marked.append(row_marked)
    
    # Check rows
    for i in range(5):
        if all(marked[i][j] for j in range(5)):
            return True
    
    # Check columns
    for j in range(5):
        if all(marked[i][j] for i in range(5)):
            return True
    
    # Check main diagonal (top-left to bottom-right)
    if all(marked[i][i] for i in range(5)):
        return True
    
    # Check anti-diagonal (top-right to bottom-left)
    if all(marked[i][4-i] for i in range(5)):
        return True
    
    return False
