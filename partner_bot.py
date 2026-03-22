import os
import logging
import re
import string
import random
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from supabase import create_client, Client

load_dotenv()

PARTNER_BOT_TOKEN = os.getenv("PARTNER_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

logger = logging.getLogger(__name__)

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

router = Router()

class RegisterShop(StatesGroup):
    name = State()
    city = State()
    phone = State()
    instagram = State()
    invite_id = State()

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_slug(name: str, city: str) -> str:
    # Basic transliteration map
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': 'shch', 'ы': 'y', 'ь': '', 'э': 'e',
        'ю': 'yu', 'я': 'ya', ' ': '-', '_': '-'
    }
    
    text = f"{name} {city}".lower()
    slug = ''.join(translit_map.get(c, c) for c in text)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug

# --- ADMIN COMMANDS ---

@router.message(Command("invite"))
async def cmd_invite(message: Message):
    # Проверка, что команду вызвал суперадмин
    if str(message.from_user.id) != str(SUPER_ADMIN_ID):
        await message.answer("У вас нет прав для создания инвайтов.")
        return
        
    code = generate_invite_code()
    
    try:
        # Сохраняем инвайт в БД
        supabase.table("invites").insert({"code": code}).execute()
        
        from aiogram.types import WebAppInfo
        web_app = WebAppInfo(url=f"https://chopbar-production.up.railway.app/static/partner_app.html?invite={code}")
        
        await message.answer(
            f"✅ Новый инвайт создан: `{code}`\n\nОтправь ссылку ниже владельцу барбершопа:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🚀 Зарегистрировать барбершоп", web_app=web_app)
            ]])
        )
    except Exception as e:
        logger.error(f"Error creating invite: {e}")
        await message.answer("❌ Ошибка при создании инвайта.")

@router.message(Command("shops"))
async def cmd_shops(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    try:
        res = supabase.table("barbershops").select("*").execute()
        shops = res.data
        if not shops:
            await message.answer("Нет зарегистрированных барбершопов.")
            return
            
        text = "Список барбершопов:\n\n"
        for shop in shops:
            date_str = shop['created_at'].split('T')[0] if shop.get('created_at') else 'N/A'
            text += f"💈 {shop['name']} ({shop['city']}) - {date_str}\nSlug: {shop['slug']}\n\n"
            
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error fetching shops: {e}")
        await message.answer("Ошибка при получении списка.")

@router.message(Command("revoke"))
async def cmd_revoke(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /revoke КОД")
        return
        
    code = parts[1]
    try:
        res = supabase.table("invites").update({"used": True}).eq("code", code).execute()
        if res.data:
            await message.answer(f"Инвайт {code} отозван (помечен использованным).")
        else:
            await message.answer("Код не найден.")
    except Exception as e:
        logger.error(f"Error revoking invite: {e}")
        await message.answer("Ошибка при отзыве инвайта.")

# --- REGISTRATION FSM ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    # If the user passed an invite code via /start CODE
    invite_code = ""
    args = message.text.split()
    if len(args) > 1:
        invite_code = args[1]
        
    # URL to the actual Railway deployment
    base_url = "https://chopbar-production.up.railway.app/static/partner_app.html"
    web_app_url = base_url
    
    # Append invite code to start_param so MiniApp can read it
    if invite_code:
        web_app_url += f"?startapp={invite_code}"

    from aiogram.types import WebAppInfo
    kb = [
        [InlineKeyboardButton(text="🚀 У меня есть код", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    await message.answer(
        "👋 Привет!\n\n"
        "Это бот для подключения барбершопа к системе CHOPBAR.\n\n"
        "Чтобы получить инвайт-код — напиши: @cheepeek_c\n\n"
        "Когда получишь код, нажми кнопку ниже 👇",
        reply_markup=reply_markup
    )



async def start_partner_bot():
    if not PARTNER_BOT_TOKEN:
        logger.error("PARTNER_BOT_TOKEN не найден!")
        return
        
    bot = Bot(token=PARTNER_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    logger.info("Starting Partner Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_partner_bot())