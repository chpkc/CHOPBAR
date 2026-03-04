import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
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

# --- SCHEDULER ---
scheduler = AsyncIOScheduler()

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with a button that opens the web app."""
    # Ensure WebAppInfo URL is valid
    if not MINI_APP_URL:
        await update.message.reply_text("Ошибка: URL веб-приложения не настроен.")
        return

    await update.message.reply_text(
        "Добро пожаловать в наш барбершоп! Нажмите на кнопку ниже, чтобы записаться.",
        reply_markup=context.bot.get_chat_menu_button(chat_id=update.effective_chat.id)
    )

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes data sent from the web app."""
    data = update.message.web_app_data.data
    logger.info("Received data from web app: %s", data)
    await update.message.reply_text(f"Ваша запись подтверждена! Мы получили следующие данные:\n{data}")

# --- NOTIFICATION TASKS ---
async def check_and_notify(bot):
    if not supabase:
        return

    try:
        response = supabase.table('bookings').select('*').eq('status','new').execute()
        bookings = response.data
        
        now = datetime.now()
        
        for b in bookings:
            try:
                # b['date'] is YYYY-MM-DD, b['time'] is HH:MM
                booking_dt = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                delta = booking_dt - now
                hours_left = delta.total_seconds() / 3600
                
                # 24 hour reminder
                if 23.75 <= hours_left <= 24.25:
                    if not b.get('notified_24h'):
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=f"✂️ Напоминание!\n\nЗавтра в {b['time']} вас ждёт мастер {b['master']}.\nУслуга: {b['service']}\nСтоимость: {b['price']}₸\n\nБарбершоп CHOP, Павлодар"
                        )
                        supabase.table('bookings').update({'notified_24h': True}).eq('id', b['id']).execute()
                
                # 2 hour reminder
                if 1.75 <= hours_left <= 2.25:
                    if not b.get('notified_2h'):
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=f"⏰ Через 2 часа!\n\nВас ждёт мастер {b['master']} в {b['time']}.\nУслуга: {b['service']}\n\nДо встречи в CHOP! 💈"
                        )
                        supabase.table('bookings').update({'notified_2h': True}).eq('id', b['id']).execute()
            except Exception as e:
                logger.error(f"Error processing booking {b.get('id')}: {e}")
                
    except Exception as e:
        logger.error(f"Error in check_and_notify: {e}")

async def expire_past_bookings():
    if not supabase:
        return

    try:
        response = supabase.table('bookings').select('*').eq('status','new').execute()
        bookings = response.data
        
        now = datetime.now()
        
        for b in bookings:
            try:
                booking_dt = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                if now > booking_dt:
                    supabase.table('bookings').update({'status': 'done'}).eq('id', b['id']).execute()
            except Exception as e:
                logger.error(f"Error expiring booking {b.get('id')}: {e}")
                
    except Exception as e:
        logger.error(f"Error in expire_past_bookings: {e}")

def main() -> None:
    """Starts the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN must be set in .env file.")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Set the web app button for the bot if URL is present
    if MINI_APP_URL:
        # We can't set chat menu button globally easily without a chat_id in python-telegram-bot v20+ 
        # unless we use bot.set_chat_menu_button() which is async.
        # But we can do it in the start handler or use a job.
        # For now, start handler handles it.
        pass

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    # Add scheduler jobs
    scheduler.add_job(check_and_notify, 'interval', minutes=15, args=[application.bot])
    scheduler.add_job(expire_past_bookings, 'interval', minutes=15)
    scheduler.start()

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
