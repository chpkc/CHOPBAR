import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with a button that opens the admin web app."""
    
    # Check Admin ID
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔️ Доступ запрещен. Вы не являетесь администратором.")
        return
    
    # Check config
    if not ADMIN_BOT_TOKEN:
        await update.message.reply_text("Ошибка: Токен бота не настроен.")
        return
        
    # Construct Admin URL
    admin_url = MINI_APP_URL
    if admin_url:
        if not admin_url.endswith('/'):
            admin_url += '/'
        # Check if we need to append 'admin'
        # The main app is served at root, admin at /admin
        # If MINI_APP_URL points to root (e.g. https://example.com), append 'admin'
        if not admin_url.endswith('admin/'):
             # If user set MINI_APP_URL to https://example.com/admin already, don't append
             if 'admin' not in admin_url:
                 admin_url += 'admin'
    else:
        await update.message.reply_text("Ошибка: URL веб-приложения не настроен (MINI_APP_URL).")
        return

    # Create keyboard with Web App button
    keyboard = [
        [KeyboardButton(text="🛠 Открыть Админку", web_app=WebAppInfo(url=admin_url))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Привет, Админ!\n\nНажми кнопку ниже, чтобы управлять записями.",
        reply_markup=reply_markup
    )

def main() -> None:
    """Starts the admin bot."""
    if not ADMIN_BOT_TOKEN:
        print("Error: ADMIN_BOT_TOKEN not found in .env")
        return

    application = Application.builder().token(ADMIN_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    print(f"Admin Bot started with URL: {MINI_APP_URL}")
    application.run_polling()

if __name__ == "__main__":
    main()
