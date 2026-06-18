import os
from dotenv import load_dotenv

# Load .env file (only works locally, ignored when not found)
load_dotenv()

# ---------- REQUIRED VARIABLES ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")   # optional, admin routes won't work without it

# ADMIN_IDS: comma-separated Telegram user IDs
admin_ids_str = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

WEB_APP_URL = os.environ.get("WEB_APP_URL", "http://localhost:5000")

# ---------- GAME SETTINGS ----------
STAKE_OPTIONS = [10, 20, 50, 100]
MAX_CARDS_PER_PLAYER = 4
GAME_START_DELAY_SECONDS = 30       # seconds before a waiting game is auto-started
BALL_DRAW_INTERVAL_SECONDS = 2.5    # time between each ball draw (reduced for smoothness)
OWNER_CUT_PERCENT = 20              # percentage of prize pool that goes to the house
MAX_BALLS_PER_GAME = 75

# ---------- BOT SETTINGS ----------
BOT_ENABLED = os.environ.get("BOT_ENABLED", "true").lower() == "true"
BOT_CARDS_PER_GAME = int(os.environ.get("BOT_CARDS_PER_GAME", "1"))
BOT_MIN_PLAYERS = int(os.environ.get("BOT_MIN_PLAYERS", "2"))
