#!/usr/bin/env python3
import os
import logging
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from supabase import create_client, Client

load_dotenv()

BARBER_BOT_TOKEN = os.getenv("BARBER_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Connected to Supabase")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")

router = Router()

@router.message(Command("start"))
async def start(message: types.Message):
    """Checks barber authentication and shows main menu."""
    if not supabase:
        await message.answer("Ошибка подключения к базе данных.")
        return

    user_id = str(message.from_user.id)
    
    try:
        result = supabase.table('barbers').select('*').eq('telegram_id', user_id).execute()
        
        if not result.data:
            await message.answer("⛔️ У вас нет доступа. Обратитесь к администратору.")
            return
            
        barber_name = result.data[0]['name']
        
        if not MINI_APP_URL:
            await message.answer("Ошибка: URL приложения не настроен.")
            return

        parsed_url = urlparse(MINI_APP_URL)
        path = parsed_url.path.rstrip('/')
        if not path.endswith('/barber'):
            path += '/barber'
        
        query_params = dict(parse_qsl(parsed_url.query))
        query_params['master_id'] = user_id
        
        new_url_parts = list(parsed_url)
        new_url_parts[2] = path
        new_url_parts[4] = urlencode(query_params)
        app_url = urlunparse(new_url_parts)
        
        logger.info(f"Generated WebApp URL: {app_url}")
        
        kb = [[KeyboardButton(text="✂️ Открыть рабочий стол", web_app=WebAppInfo(url=app_url))]]
        
        await message.answer(
            f"👋 Привет, {barber_name}!\nНажми кнопку ниже, чтобы открыть расписание.",
            reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        )
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        await message.answer("Произошла ошибка при авторизации.")

async def main():
    if not BARBER_BOT_TOKEN:
        logger.error("Error: BARBER_BOT_TOKEN not found in .env")
        return

    bot = Bot(token=BARBER_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Barber Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
