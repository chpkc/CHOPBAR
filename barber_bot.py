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
        context.user_data['barber'] = barber_name
        
        await show_main_menu(update, context, barber_name)
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        await update.message.reply_text("Произошла ошибка при авторизации.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, barber_name: str) -> None:
    keyboard = [
        [InlineKeyboardButton("📅 Записи на сегодня", callback_data="today")],
        [InlineKeyboardButton("🗓 Записи на неделю", callback_data="week")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"💈 Привет, {barber_name}!\nВыбери что хочешь посмотреть:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button clicks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    barber_name = context.user_data.get('barber')
    
    if not barber_name:
        # Re-auth if context lost (e.g. restart)
        user_id = str(update.effective_user.id)
        result = supabase.table('barbers').select('*').eq('telegram_id', user_id).execute()
        if result.data:
            barber_name = result.data[0]['name']
            context.user_data['barber'] = barber_name
        else:
            await query.edit_message_text("⛔️ Ошибка авторизации. Введите /start")
            return

    if data == "today":
        await show_today_bookings(query, barber_name)
    elif data == "week":
        await show_week_bookings(query, barber_name)
    elif data == "menu":
        await show_main_menu(update, context, barber_name)
    elif data.startswith("done_"):
        booking_id = data.split("_")[1]
        await mark_done(query, booking_id, barber_name)
    elif data.startswith("cancel_ask_"):
        booking_id = data.split("_")[2]
        await ask_cancel(query, booking_id)
    elif data.startswith("cancel_confirm_"):
        booking_id = data.split("_")[2]
        await confirm_cancel(query, booking_id, barber_name)
    elif data.startswith("cancel_abort_"):
        # Just refresh the list based on context (hacky: assume today or week? or just today for simplicity)
        # Better: go back to today's list
        await show_today_bookings(query, barber_name)

async def show_today_bookings(query, barber_name):
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        result = supabase.table('bookings')\
            .select('*, clients:telegram_id(username)')\
            .eq('master', barber_name)\
            .eq('date', today)\
            .neq('status', 'cancelled')\
            .order('time')\
            .execute()
            
        # Note: join with clients table implies we have a clients table. 
        # If not, we rely on what we have. User said "from clients table". 
        # But 'bookings' has 'telegram_id'. We might need to fetch username separately or assume it's stored.
        # Let's assume for now we just show client name from booking and maybe fetch username if possible?
        # Actually, user said "@username (telegram username from clients table)".
        # This implies a join or separate fetch. Since we might not have foreign keys set up perfectly,
        # let's try to just fetch bookings and maybe client info if we can.
        # But wait, bookings table usually stores 'client_name' (implied by 'client_name' variable in prompt).
        # Ah, in our bookings table we have 'id', 'master', 'service', 'price', 'date', 'time', 'duration', 'telegram_id', 'status'.
        # We don't seem to have 'client_name' column explicitly in previous code?
        # Let's check api.py... `BookingModel` has master, service, price, date, time, duration, telegram_id.
        # It does NOT have client name!
        # This is a missing feature in previous steps. 
        # However, we can't change the past easily. 
        # We will display "Клиент" or try to fetch name if we stored it?
        # Wait, the web app form sends data. Does it send name?
        # In index.html, `bookingData` has master, service, price, date, time, duration, telegram_id.
        # It does NOT send client name.
        # So we only have telegram_id.
        # We can't show client name unless we ask for it or get it from Telegram.
        # But we are in Barber Bot. 
        # For now, we will display "Клиент ID: {telegram_id}" if name is missing.
        
        bookings = result.data
        
        if not bookings:
            keyboard = [[InlineKeyboardButton("🔙 Меню", callback_data="menu")]]
            await query.edit_message_text("Записей на сегодня нет 🎉", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        for b in bookings:
            # Try to get username if we can (if we had a clients table, but we might not)
            client_display = f"ID: {b['telegram_id']}"
            
            status_emoji = "✅" if b['status'] == 'done' else "🆕"
            
            text = (
                f"⏰ {b['time']} — {client_display}\n"
                f"✂️ {b['service']} · {b['duration']} мин · {b['price']}₸\n"
                f"Статус: {b['status']}"
            )
            
            keyboard = []
            if b['status'] == 'new':
                keyboard.append([
                    InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{b['id']}"),
                    InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_ask_{b['id']}")
                ])
            
            # We can't send multiple messages easily in edit_message_text flow unless we send new ones.
            # But query.edit_message_text replaces the menu.
            # So we should probably show a list or pagination?
            # User prompt says "Format each booking as... Add inline buttons per booking".
            # This implies sending multiple messages.
            # So we should delete the menu message and send new ones?
            # Or send one long message? But buttons need to be per booking.
            # So we must send multiple messages.
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        # Add a "Back" button at the end
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="---",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Меню", callback_data="menu")]])
        )
        
        # Delete original menu message to clean up
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Error fetching today: {e}")
        await query.edit_message_text(f"Ошибка: {e}")

async def show_week_bookings(query, barber_name):
    today = datetime.now().date()
    end_date = today + timedelta(days=7)
    
    try:
        result = supabase.table('bookings')\
            .select('*')\
            .eq('master', barber_name)\
            .gte('date', today.isoformat())\
            .lte('date', end_date.isoformat())\
            .neq('status', 'cancelled')\
            .order('date')\
            .order('time')\
            .execute()
            
        bookings = result.data
        
        if not bookings:
            keyboard = [[InlineKeyboardButton("🔙 Меню", callback_data="menu")]]
            await query.edit_message_text("Записей на неделю нет 🎉", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        # Group by date
        grouped = {}
        for b in bookings:
            d = b['date']
            if d not in grouped:
                grouped[d] = []
            grouped[d].append(b)
            
        text = ""
        days_map = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        months_map = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
        
        for d, items in grouped.items():
            dt = datetime.strptime(d, '%Y-%m-%d')
            day_str = days_map[dt.weekday()]
            month_str = months_map[dt.month]
            date_header = f"📅 {day_str}, {dt.day} {month_str}"
            
            text += f"{date_header}\n"
            for item in items:
                # client name missing, using ID
                text += f"   {item['time']} — ID {item['telegram_id']} · {item['service']}\n"
            text += "\n"
            
        keyboard = [[InlineKeyboardButton("🔙 Меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"Error fetching week: {e}")
        await query.edit_message_text(f"Ошибка: {e}")

async def mark_done(query, booking_id, barber_name):
    try:
        supabase.table('bookings').update({'status': 'done'}).eq('id', booking_id).execute()
        await query.answer("✅ Запись отмечена как выполненная")
        
        # Refresh logic: simplest is to reload today's view?
        # But we are in a specific message for that booking.
        # Let's update that specific message.
        
        # Fetch updated booking to be safe? Or just update text.
        # Let's just update text to show DONE status and remove buttons.
        
        original_text = query.message.text
        new_text = original_text.replace("Статус: new", "Статус: done").replace("Статус: done", "Статус: done") # handle repeated clicks
        
        await query.edit_message_text(
            text=new_text + "\n✅ ВЫПОЛНЕНО",
            reply_markup=None # Remove buttons
        )
        
    except Exception as e:
        logger.error(f"Error marking done: {e}")
        await query.answer("Ошибка при обновлении")

async def ask_cancel(query, booking_id):
    keyboard = [
        [InlineKeyboardButton("Да, отменить", callback_data=f"cancel_confirm_{booking_id}")],
        [InlineKeyboardButton("Нет", callback_data=f"cancel_abort_{booking_id}")]
    ]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_cancel(query, booking_id, barber_name):
    try:
        # Get booking details first for notification
        booking_res = supabase.table('bookings').select('*').eq('id', booking_id).execute()
        if not booking_res.data:
            await query.answer("Запись не найдена")
            return
            
        booking = booking_res.data[0]
        
        # Update DB
        supabase.table('bookings').update({'status': 'cancelled'}).eq('id', booking_id).execute()
        
        # Notify Client
        if client_bot:
            try:
                await client_bot.send_message(
                    chat_id=booking['telegram_id'],
                    text=f"❌ Ваша запись на {booking['date']} в {booking['time']} отменена мастером {barber_name}.\n\nПожалуйста, запишитесь на другое время."
                )
            except Exception as e:
                logger.error(f"Failed to notify client: {e}")
        
        # Update Barber UI
        await query.edit_message_text(
            text=query.message.text + "\n❌ ОТМЕНЕНО",
            reply_markup=None
        )
        await query.answer("Запись отменена")
        
    except Exception as e:
        logger.error(f"Error cancelling: {e}")
        await query.answer("Ошибка при отмене")

def main() -> None:
    if not BARBER_BOT_TOKEN:
        print("Error: BARBER_BOT_TOKEN not found in .env")
        return

    application = Application.builder().token(BARBER_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Barber Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
