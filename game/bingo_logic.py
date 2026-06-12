import random

# Standard Bingo ranges: B=1-15, I=16-30, N=31-45, G=46-60, O=61-75
COLUMNS = {
    'B': range(1, 16),
    'I': range(16, 31),
    'N': range(31, 46),
    'G': range(46, 61),
    'O': range(61, 76)
}

def generate_card():
    """
    Returns a 5x5 Bingo card as a list of lists.
    The center cell is 'FREE'.
    """
    card = []
    for col in ['B', 'I', 'N', 'G', 'O']:
        numbers = random.sample(list(COLUMNS[col]), 5)
        card.append(numbers)
    # Transpose so rows are 5x5
    card = list(map(list, zip(*card)))
    card[2][2] = 'FREE'
    return card

def draw_ball(drawn_set):
    """
    Draws a new random ball (e.g., 'B12') that hasn't been drawn yet.
    Returns None if all 75 balls have been drawn.
    """
    all_balls = [f"{letter}{num}" for letter, nums in COLUMNS.items() for num in nums]
    available = [ball for ball in all_balls if ball not in drawn_set]
    if not available:
        return None
    return random.choice(available)

def check_bingo(card, drawn_set):
    """
    Checks whether the given card has a Bingo (any row, column, or diagonal completed).
    'FREE' is treated as already marked.
    """
    drawn_numbers = {int(ball[1:]) for ball in drawn_set if ball[1:].isdigit()}

    def cell_is_marked(cell):
        if cell == 'FREE':
            return True
        return cell in drawn_numbers

    # Check rows
    for row in card:
        if all(cell_is_marked(cell) for cell in row):
            return True

    # Check columns
    for col in range(5):
        if all(cell_is_marked(card[row][col]) for row in range(5)):
            return True

    # Check diagonals
    if all(cell_is_marked(card[i][i]) for i in range(5)):
        return True
    if all(cell_is_marked(card[i][4 - i]) for i in range(5)):
        return True

    return False
