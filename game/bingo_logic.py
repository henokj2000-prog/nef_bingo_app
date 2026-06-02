import random

COLUMN_RANGES = {
    'B': (1, 15),
    'I': (16, 30),
    'N': (31, 45),
    'G': (46, 60),
    'O': (61, 75)
}

def generate_card():
    """Generate a 5x5 bingo card with unique numbers per column, middle cell FREE."""
    card = []
    for col in COLUMN_RANGES:
        low, high = COLUMN_RANGES[col]
        numbers = random.sample(range(low, high+1), 5)
        card.append(numbers)
    # Transpose to 5 rows
    card = list(zip(*card))
    # Free space in the middle
    card[2][2] = 'FREE'
    return card

def draw_ball(drawn_balls):
    """Return a new ball (e.g., 'B12') not already drawn, or None if all 75 drawn."""
    all_balls = []
    for col, (low, high) in COLUMN_RANGES.items():
        for num in range(low, high+1):
            all_balls.append(f"{col}{num}")
    remaining = [b for b in all_balls if b not in drawn_balls]
    return random.choice(remaining) if remaining else None

def check_bingo(card, drawn_set):
    """Return True if the card has a complete line (row, column, or diagonal)."""
    # drawn_set is a set of strings like 'B12', 'I25', etc.
    marked = [[cell in drawn_set or cell == 'FREE' for cell in row] for row in card]

    # Check rows
    for row in marked:
        if all(row):
            return True
    # Check columns
    for col in range(5):
        if all(marked[row][col] for row in range(5)):
            return True
    # Check diagonals
    if all(marked[i][i] for i in range(5)):
        return True
    if all(marked[i][4-i] for i in range(5)):
        return True
    return False	

