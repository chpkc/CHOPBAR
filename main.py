# -*- coding: utf-8 -*-

import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from supabase import create_client, Client
from notifications import setup_scheduler
from partner_bot import router as partner_router

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
PARTNER_BOT_TOKEN = os.getenv("PARTNER_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

async def run_client_bot(supabase: Client):
    """Запуск основного клиентского бота и планировщика"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в .env файле!")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    logger.info("Setting up scheduler...")
    scheduler = setup_scheduler(bot, supabase)
    scheduler.start()

    try:
        logger.info("Client Bot is starting...")
        # Сюда можно добавить подключение роутеров основного бота:
        # dp.include_router(main_bot_router)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down Client Bot...")
        scheduler.shutdown()
        await bot.session.close()

async def run_partner_bot():
    """Запуск бота-партнера"""
    if not PARTNER_BOT_TOKEN:
        logger.error("PARTNER_BOT_TOKEN не найден в .env файле!")
        return

    bot = Bot(token=PARTNER_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(partner_router)

    try:
        logger.info("Partner Bot is starting...")
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down Partner Bot...")
        await bot.session.close()

async def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Ключи Supabase не найдены в .env файле!")
        return

    logger.info("Connecting to database via Supabase client...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Не удалось подключиться к БД: {e}")
        return

    # Запускаем обоих ботов параллельно
    await asyncio.gather(
        run_client_bot(supabase),
        run_partner_bot()
    )

if __name__ == "__main__":
    asyncio.run(main())

