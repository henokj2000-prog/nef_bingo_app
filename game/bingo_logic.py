import random

def generate_card():
    card = []
    ranges = [(1,15),(16,30),(31,45),(46,60),(61,75)]
    for i, (lo, hi) in enumerate(ranges):
        col = random.sample(range(lo, hi+1), 5)
        card.append(col)
    grid = []
    for row in range(5):
        grid.append([card[col][row] for col in range(5)])
    grid[2][2] = 0  # free space
    return grid

def draw_ball(drawn):
    remaining = [n for n in range(1, 76) if n not in drawn]
    if not remaining:
        return None
    return random.choice(remaining)

def ball_letter(ball):
    if ball <= 15: return "B"
    if ball <= 30: return "I"
    if ball <= 45: return "N"
    if ball <= 60: return "G"
    return "O"

def check_bingo(card, drawn):
    drawn_set = set(drawn)
    # Check rows
    for row in card:
        if all(n == 0 or n in drawn_set for n in row):
            return True
    # Check columns
    for col in range(5):
        if all(card[row][col] == 0 or card[row][col] in drawn_set for row in range(5)):
            return True
    # Check diagonals
    if all(card[i][i] == 0 or card[i][i] in drawn_set for i in range(5)):
        return True
    if all(card[i][4-i] == 0 or card[i][4-i] in drawn_set for i in range(5)):
        return True
    return False
