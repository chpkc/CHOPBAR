#!/usr/bin/env python3
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
BARBER_BOT_TOKEN = os.getenv("BARBER_BOT_TOKEN")
CLIENT_BOT_TOKEN = os.getenv("BOT_TOKEN") # Main bot token to notify clients
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
        
        # Construct Barber App URL
        app_url = MINI_APP_URL
        if app_url:
            if not app_url.endswith('/'): app_url += '/'
            if not app_url.endswith('barber/'): 
                if 'barber' not in app_url: app_url += 'barber'
        
        from telegram import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
        
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
