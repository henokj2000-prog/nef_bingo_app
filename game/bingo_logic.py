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
    # drawn_set is a set of strings like {'B12', 'I25', ...}
    # Convert to drawn numbers (integers)
    drawn_numbers = set()
    for ball in drawn_set:
        try:
            num = int(ball[1:])
            drawn_numbers.add(num)
        except:
            pass
    
    # DEBUG: print first few drawn numbers (once)
    if len(drawn_numbers) % 10 == 0:
        print(f"DEBUG: {len(drawn_numbers)} numbers drawn: {sorted(drawn_numbers)[:10]}...")
    
    # Mark card cells
    marked = []
    for row in card:
        marked_row = []
        for cell in row:
            if cell == 'FREE':
                marked_row.append(True)
            elif isinstance(cell, int) and cell in drawn_numbers:
                marked_row.append(True)
            else:
                marked_row.append(False)
        marked.append(marked_row)
    
    # Check for bingo
    # rows
    for i, row in enumerate(marked):
        if all(row):
            print(f"DEBUG: BINGO on row {i}")
            return True
    # columns
    for col in range(5):
        if all(marked[row][col] for row in range(5)):
            print(f"DEBUG: BINGO on column {col}")
            return True
    # diagonals
    if all(marked[i][i] for i in range(5)):
        print("DEBUG: BINGO on main diagonal")
        return True
    if all(marked[i][4-i] for i in range(5)):
        print("DEBUG: BINGO on anti-diagonal")
        return True
    return False
