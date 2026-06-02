import random

COLUMN_RANGES = {
    'B': (1, 15),
    'I': (16, 30),
    'N': (31, 45),
    'G': (46, 60),
    'O': (61, 75)
}

def generate_card():
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
    all_balls = []
    for col, (low, high) in COLUMN_RANGES.items():
        for num in range(low, high+1):
            all_balls.append(f"{col}{num}")
    remaining = [b for b in all_balls if b not in drawn_balls]
    return random.choice(remaining) if remaining else None

def check_bingo(card, drawn_set):
    marked = [[cell in drawn_set or cell == 'FREE' for cell in row] for row in card]
    for row in marked:
        if all(row): return True
    for col in range(5):
        if all(marked[row][col] for row in range(5)): return True
    if all(marked[i][i] for i in range(5)): return True
    if all(marked[i][4-i] for i in range(5)): return True
    return False
