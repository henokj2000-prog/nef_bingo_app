import random

def generate_card():
    """
    Generate a 5x5 bingo card.
    B: 1-15, I: 16-30, N: 31-45, G: 46-60, O: 61-75
    Center (row 2, col 2) is FREE = 0
    Returns a list of 5 rows, each with 5 values.
    """
    ranges = [(1,15),(16,30),(31,45),(46,60),(61,75)]
    cols = []
    for (lo, hi) in ranges:
        cols.append(random.sample(range(lo, hi + 1), 5))
    grid = []
    for row in range(5):
        grid.append([cols[col][row] for col in range(5)])
    grid[2][2] = 0  # FREE space
    return grid


def draw_ball(drawn):
    """Pick one unused ball from 1-75. Returns None if all drawn."""
    remaining = [n for n in range(1, 76) if n not in drawn]
    if not remaining:
        return None
    return random.choice(remaining)


def ball_letter(ball):
    """Return B/I/N/G/O prefix for a number."""
    if ball <= 15: return "B"
    if ball <= 30: return "I"
    if ball <= 45: return "N"
    if ball <= 60: return "G"
    return "O"


def check_bingo(card, drawn):
    """
    Returns True if the card has at least one complete bingo line.
    FREE space (0) counts as always marked.
    `drawn` can be a list or a set.
    """
    drawn_set = set(drawn)

    def marked(n):
        return n == 0 or n in drawn_set

    # Check rows
    for row in card:
        if all(marked(n) for n in row):
            return True

    # Check columns
    for col in range(5):
        if all(marked(card[row][col]) for row in range(5)):
            return True

    # Check diagonals
    if all(marked(card[i][i]) for i in range(5)):
        return True
    if all(marked(card[i][4 - i]) for i in range(5)):
        return True

    return False


def get_winning_lines(card, drawn):
    """Return list of winning line descriptions for display purposes."""
    drawn_set = set(drawn)

    def marked(n):
        return n == 0 or n in drawn_set

    wins = []

    for row in range(5):
        if all(marked(card[row][col]) for col in range(5)):
            wins.append(f"Row {row + 1}")

    letters = ['B', 'I', 'N', 'G', 'O']
    for col in range(5):
        if all(marked(card[row][col]) for row in range(5)):
            wins.append(f"Column {letters[col]}")

    if all(marked(card[i][i]) for i in range(5)):
        wins.append("Diagonal (↘)")
    if all(marked(card[i][4 - i]) for i in range(5)):
        wins.append("Diagonal (↙)")

    return wins

