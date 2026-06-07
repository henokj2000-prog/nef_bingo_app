import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "nefbingo2026")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "796811519").split(",")]
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://your-app.onrender.com")

# Database – Render will set DATABASE_URL automatically
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Game settings
STAKE_OPTIONS = [10, 20, 50, 100]
MAX_CARDS_PER_PLAYER = 4
GAME_START_DELAY_SECONDS = 30
BALL_DRAW_INTERVAL_SECONDS = 2   # Changed from 4 to 2 seconds
OWNER_CUT_PERCENT = 20
MAX_BALLS_PER_GAME = 75

# Bot settings
BOT_ENABLED = True
BOT_CARDS_PER_GAME = 1
BOT_MIN_PLAYERS = 2
