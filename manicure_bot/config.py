import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_env_var(name: str, required: bool = True, default: str | None = None) -> str:
    """Завантажує змінну середовища з валідацією."""
    value = os.getenv(name, default)
    if required and not value:
        print(f"[ERROR] Обов'язкова змінна середовища '{name}' не задана!")
        print(f"        Перевірте файл .env і додайте: {name}=ваше_значення")
        sys.exit(1)
    return value or ""


def get_int_env_var(name: str, required: bool = True, default: int | None = None) -> int:
    """Завантажує цілочисельну змінну середовища."""
    raw_value = os.getenv(name)
    if raw_value is None:
        if required and default is None:
            print(f"[ERROR] Обов'язкова змінна середовища '{name}' не задана!")
            sys.exit(1)
        return default if default is not None else 0
    try:
        return int(raw_value)
    except ValueError:
        print(f"[ERROR] Змінна '{name}' має бути числом, отримано: '{raw_value}'")
        sys.exit(1)


# Обов'язкові змінні
BOT_TOKEN = get_env_var("BOT_TOKEN")
ADMIN_ID = get_int_env_var("ADMIN_ID")
CHANNEL_ID = get_env_var("CHANNEL_ID")
CHANNEL_LINK = get_env_var("CHANNEL_LINK")
SCHEDULE_CHANNEL_ID = get_env_var("SCHEDULE_CHANNEL_ID")

# Опційні змінні з дефолтами
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kiev")
DB_PATH = os.getenv("DB_PATH", "data/bot.sqlite3")
SALON_ADDRESS = os.getenv("SALON_ADDRESS", "Адресу уточнюйте у майстра")
MAP_LINK = os.getenv("MAP_LINK", "")
MASTER_USERNAME = os.getenv("MASTER_USERNAME", "").strip().lstrip("@")
MASTER_LINK = os.getenv("MASTER_LINK", "").strip()
if not MASTER_LINK and MASTER_USERNAME:
    MASTER_LINK = f"https://t.me/{MASTER_USERNAME}"

# Створюємо директорію для БД, якщо потрібно
db_dir = Path(DB_PATH).parent
db_dir.mkdir(parents=True, exist_ok=True)
