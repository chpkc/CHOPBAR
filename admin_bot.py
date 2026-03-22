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
        
    admin_url = MINI_APP_URL
    if admin_url:
        if not admin_url.endswith('/'):
            admin_url += '/'
        if not admin_url.endswith('admin/'):
             if 'admin' not in admin_url:
                 admin_url += 'admin'
    else:
        await message.answer("Ошибка: URL веб-приложения не настроен (MINI_APP_URL).")
        return

    kb = [
        [KeyboardButton(text="🛠 Открыть Админку", web_app=WebAppInfo(url=admin_url))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    await message.answer(
        "👋 Привет, Админ!\n\nНажми кнопку ниже, чтобы управлять записями.",
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
