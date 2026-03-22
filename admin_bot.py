import os
import logging
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("start"))
async def start(message: types.Message):
    """Sends a message with a button that opens the admin web app."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("⛔️ Доступ запрещен. Вы не являетесь администратором.")
        return
    
    if not ADMIN_BOT_TOKEN:
        await message.answer("Ошибка: Токен бота не настроен.")
        return

    # Parse slug from /start <slug>
    args = message.text.split()
    slug = args[1] if len(args) > 1 else 'chop-pavlodar'
        
    # URL to the actual Railway deployment with slug parameter
    admin_url = f"https://chopbar-production.up.railway.app/static/admin.html?slug={slug}"

    kb = [
        [KeyboardButton(text="🛠 Открыть Админку", web_app=WebAppInfo(url=admin_url))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    await message.answer(
        f"👋 Привет, Админ!\n\nБарбершоп: {slug}\nНажми кнопку ниже, чтобы управлять записями.",
        reply_markup=reply_markup
    )

async def main():
    if not ADMIN_BOT_TOKEN:
        logger.error("Error: ADMIN_BOT_TOKEN not found in .env")
        return

    bot = Bot(token=ADMIN_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info(f"Admin Bot started with URL: {MINI_APP_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
