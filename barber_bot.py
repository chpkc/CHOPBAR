#!/usr/bin/env python3
import os
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
BARBER_BOT_TOKEN = os.getenv("BARBER_BOT_TOKEN")
CLIENT_BOT_TOKEN = os.getenv("BOT_TOKEN") # Main bot token to notify clients
MINI_APP_URL = os.getenv("MINI_APP_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- SUPABASE CLIENT ---
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Connected to Supabase")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")

# --- CLIENT BOT INSTANCE ---
client_bot = Bot(token=CLIENT_BOT_TOKEN) if CLIENT_BOT_TOKEN else None

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checks barber authentication and shows main menu."""
    if not supabase:
        await update.message.reply_text("Ошибка подключения к базе данных.")
        return

    user_id = str(update.effective_user.id)
    
    # Check if user is a barber
    try:
        result = supabase.table('barbers').select('*').eq('telegram_id', user_id).execute()
        
        if not result.data:
            await update.message.reply_text("⛔️ У вас нет доступа. Обратитесь к администратору.")
            return
            
        barber_name = result.data[0]['name']
        
        if not MINI_APP_URL:
            await update.message.reply_text("Ошибка: URL приложения не настроен.")
            return

        # Construct Barber App URL
        # Ensure we point to /barber endpoint of our API
        parsed_url = urlparse(MINI_APP_URL)
        path = parsed_url.path.rstrip('/')
        if not path.endswith('/barber'):
            path += '/barber'
        
        # Add master_id query param cleanly
        query_params = dict(parse_qsl(parsed_url.query))
        query_params['master_id'] = user_id
        
        new_url_parts = list(parsed_url)
        new_url_parts[2] = path
        new_url_parts[4] = urlencode(query_params)
        app_url = urlunparse(new_url_parts)
        
        logger.info(f"Generated WebApp URL: {app_url}")
        
        kb = [[KeyboardButton("✂️ Открыть рабочий стол", web_app=WebAppInfo(url=app_url))]]
        
        await update.message.reply_text(
            f"👋 Привет, {barber_name}!\nНажми кнопку ниже, чтобы открыть расписание.",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        await update.message.reply_text("Произошла ошибка при авторизации.")

def main() -> None:
    if not BARBER_BOT_TOKEN:
        print("Error: BARBER_BOT_TOKEN not found in .env")
        return

    application = Application.builder().token(BARBER_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    # application.add_handler(CallbackQueryHandler(button_handler)) # No longer needed

    print("Barber Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
