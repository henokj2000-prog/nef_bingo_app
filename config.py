import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8821917141:AAFjvWpUOg7kCmoMBL2canvy1HG_Sdn_pkQ")
ADMIN_IDS = [796811519]
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://nef-bingo.up.railway.app")

PAYMENT_PLATFORMS = {
    "telebirr": {"name": "Telebirr", "number": "0929001000", "enabled": True},
    "cbe": {"name": "CBE Birr", "number": "1000061737212", "enabled": True},
}

STAKE_OPTIONS = [10, 20, 50, 100]
MAX_CARDS_PER_PLAYER = 4
GAME_START_DELAY_SECONDS = 30
BALL_DRAW_INTERVAL_SECONDS = 4
MIN_PLAYERS = 1
DB_PATH = "nef_bingo.db"
OWNER_CUT_PERCENT = 20
