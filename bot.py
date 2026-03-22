import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import MenuButtonWebApp, WebAppInfo, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.payload import decode_payload
from aiogram.filters.command import CommandObject
from supabase import create_client, Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "5"))

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

scheduler = AsyncIOScheduler()
router = Router()

@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot):
    if not MINI_APP_URL:
        await message.answer("Ошибка: URL веб-приложения не настроен.")
        return

    # Parse slug from /start <slug>
    slug = command.args or 'chop-pavlodar'
    
    # URL to the actual Railway deployment with slug parameter
    web_app_url = f"{MINI_APP_URL}/static/index.html?slug={slug}"
    if 'index.html' in MINI_APP_URL:
        web_app_url = f"{MINI_APP_URL}?slug={slug}"

    await bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonWebApp(type="web_app", text="Записаться", web_app=WebAppInfo(url=web_app_url))
    )
    
    # Send a button as well
    kb = [[InlineKeyboardButton(text="✂️ Записаться", web_app=WebAppInfo(url=web_app_url))]]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    await message.answer(
        "Жми кнопку — выбери мастера и время 👇",
        reply_markup=reply_markup
    )

@router.message(F.web_app_data)
async def web_app_data(message: types.Message) -> None:
    data = message.web_app_data.data
    logger.info("Received data from web app: %s", data)
    await message.answer(f"Ваша запись подтверждена! Мы получили следующие данные:\n{data}")

local_tz = timezone(timedelta(hours=TIMEZONE_OFFSET))

async def check_and_notify(bot: Bot):
    if not supabase:
        return

    try:
        result = supabase.table('bookings').select('*').eq('status', 'new').execute()
        now = datetime.now(local_tz)
        
        for b in result.data:
            try:
                booking_dt_naive = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                booking_dt = booking_dt_naive.replace(tzinfo=local_tz)
                
                delta = booking_dt - now
                hours = delta.total_seconds() / 3600
                
                if 23.5 <= hours <= 24.5 and not b.get('notified_24h'):
                    try:
                        await bot.send_message(
                            chat_id=b['telegram_id'],
                            text=(
                                f"✂️ Напоминание о записи!\n\n"
                                f"Завтра в {b['time']} вас ждёт мастер {b['master']}.\n"
                                f"Услуга: {b['service']}\n"
                                f"Стоимость: {b['price']}₸\n\n"
                                f"Барбершоп CHOP 💈"
                            )
                        )
                        supabase.table('bookings').update({'notified_24h': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 24h reminder: {e}")

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
                        master = supabase.table('barbers').select('telegram_id').eq('name', b['master']).execute()
                        if master.data and master.data[0].get('telegram_id'):
                            master_tg = master.data[0]['telegram_id']
                            if os.getenv("BARBER_BOT_TOKEN"):
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
                                await barber_bot.session.close()
                        supabase.table('bookings').update({'notified_2h': True}).eq('id', b['id']).execute()
                    except Exception as e:
                        logger.error(f"Failed to send 2h reminder: {e}")

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

                if 0.4 <= hours <= 0.6 and not b.get('notified_30m'):
                    try:
                        master = supabase.table('barbers').select('telegram_id').eq('name', b['master']).execute()
                        if master.data and master.data[0].get('telegram_id'):
                            master_tg = master.data[0]['telegram_id']
                            if os.getenv("BARBER_BOT_TOKEN"):
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
                                await barber_bot.session.close()
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
        now = datetime.now(local_tz)
        
        for b in bookings:
            try:
                booking_dt_naive = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                booking_dt = booking_dt_naive.replace(tzinfo=local_tz)
                
                if now > booking_dt:
                     supabase.table('bookings').update({'status': 'done'}).eq('id', b['id']).execute()
            except Exception as e:
                logger.error(f"Error expiring booking {b.get('id')}: {e}")
                
    except Exception as e:
        logger.error(f"Error in expire_past_bookings: {e}")

async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN must be set in .env file.")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler.add_job(check_and_notify, 'interval', minutes=15, args=[bot])
    scheduler.add_job(expire_past_bookings, 'interval', minutes=15)
    scheduler.start()

    logger.info("Bot started...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
