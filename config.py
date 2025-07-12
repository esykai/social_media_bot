import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
MAX_MEDIA_FILES = int(os.getenv("MAX_MEDIA_FILES", "10"))
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "2000"))