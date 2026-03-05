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

# --- TIMEZONE ---
pavlodar_tz = timezone(timedelta(hours=5))

# --- NOTIFICATION TASKS ---
async def check_and_notify(bot):
    if not supabase:
        return

    try:
        # Fetch active bookings that haven't been completed/cancelled
        result = supabase.table('bookings')\
            .select('*')\
            .eq('status', 'new')\
            .execute()
        
        # Current time in Pavlodar
        now = datetime.now(pavlodar_tz)
        
        for b in result.data:
            try:
                # Parse booking time and make it timezone-aware
                booking_dt_naive = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                booking_dt = booking_dt_naive.replace(tzinfo=pavlodar_tz)
                
                delta = booking_dt - now
                hours = delta.total_seconds() / 3600
                
                # 24h reminder (23.5 to 24.5 hours before)
                if 23.5 <= hours <= 24.5 and not b.get('notified_24h'):
                    try:
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=(
                                f"✂️ Напоминание о записи!\n\n"
                                f"Завтра в {b['time']} вас ждёт мастер {b['master']}.\n"
                                f"Услуга: {b['service']}\n"
                                f"Стоимость: {b['price']}₸\n\n"
                                f"Барбершоп CHOP · Павлодар 💈"
                            )
                        )
                        supabase.table('bookings').update({'notified_24h': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 24h reminder: {e}")

                # 2h reminder (1.5 to 2.5 hours before)
                if 1.5 <= hours <= 2.5 and not b.get('notified_2h'):
                    try:
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=(
                                f"⏰ Через 2 часа стрижка!\n\n"
                                f"Мастер {b['master']} ждёт вас в {b['time']}.\n"
                                f"Услуга: {b['service']}\n\n"
                                f"До встречи в CHOP! 💈"
                            )
                        )
                        # Notify Master
                        master = supabase.table('barbers').select('telegram_id').eq('name', b['master']).execute()
                        if master.data and master.data[0].get('telegram_id'):
                            master_tg = master.data[0]['telegram_id']
                            # Use separate bot instance for master if needed, or same bot if token shared
                            # Assuming master is in same bot for simplicity or use HTTP request to API
                            # But here we have the token.
                            if os.getenv("BARBER_BOT_TOKEN"):
                                from telegram import Bot
                                barber_bot = Bot(token=os.getenv("BARBER_BOT_TOKEN"))
                                await barber_bot.send_message(
                                    chat_id=master_tg,
                                    text=(
                                        f"⏰ Напоминание: через 2 часа запись!\n"
                                        f"Клиент: {b.get('client_name', 'ID: '+str(b['telegram_id']))}\n"
                                        f"Время: {b['time']}\n"
                                        f"Услуга: {b['service']}"
                                    )
                                )
                        
                        supabase.table('bookings').update({'notified_2h': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 2h reminder: {e}")

                # 1h reminder (0.8 to 1.2 hours before) - Requested Feature
                # Note: We need 'notified_1h' column in DB. If not present, this update will fail.
                # Assuming migration is applied.
                if 0.8 <= hours <= 1.2 and not b.get('notified_1h'):
                    try:
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=(
                                f"⏰ Напоминание: через 1 час запись!\n\n"
                                f"Ждем вас в {b['time']} у мастера {b['master']}."
                            )
                        )
                        supabase.table('bookings').update({'notified_1h': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 1h reminder: {e}")

                # 30 min reminder (0.4 to 0.6 hours before)
                if 0.4 <= hours <= 0.6 and not b.get('notified_30m'):
                    try:
                        # Notify Master only (as per original code logic, or maybe client too?)
                        # Original code notified MASTER.
                        master = supabase.table('barbers').select('telegram_id').eq('name', b['master']).execute()
                        if master.data and master.data[0].get('telegram_id'):
                            master_tg = master.data[0]['telegram_id']
                            if os.getenv("BARBER_BOT_TOKEN"):
                                from telegram import Bot
                                barber_bot = Bot(token=os.getenv("BARBER_BOT_TOKEN"))
                                await barber_bot.send_message(
                                    chat_id=master_tg,
                                    text=(
                                        f"⚠️ Через 30 минут запись!\n"
                                        f"Клиент: {b.get('client_name', 'ID: '+str(b['telegram_id']))}\n"
                                        f"Время: {b['time']}\n"
                                        f"Услуга: {b['service']}"
                                    )
                                )
                        supabase.table('bookings').update({'notified_30m': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 30m reminder: {e}")

            except Exception as e:
                logger.error(f"Reminder error for booking {b.get('id')}: {e}")
                
    except Exception as e:
        logger.error(f"Error in check_and_notify: {e}")

async def expire_past_bookings():
    if not supabase:
        return

    try:
        response = supabase.table('bookings').select('*').eq('status','new').execute()
        bookings = response.data
        
        now = datetime.now(pavlodar_tz)
        
        for b in bookings:
            try:
                booking_dt_naive = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                booking_dt = booking_dt_naive.replace(tzinfo=pavlodar_tz)
                
                # If booking time + duration (or just start time) is in past
                # Let's say 1 hour after start time it is 'done' if not updated?
                # Or just strictly after start time? Original code was strict > now.
                if now > booking_dt:
                     # Maybe wait a bit? Like 1 hour after? 
                     # For now, stick to original logic but with correct TZ.
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
