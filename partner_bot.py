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
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    code = generate_invite_code()
    try:
        supabase.table("invites").insert({"code": code}).execute()
        await message.answer(f"Новый инвайт код создан: `{code}`", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error creating invite: {e}")
        await message.answer("Ошибка при создании инвайта.")

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
async def cmd_start(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пожалуйста, отправь команду с инвайт-кодом. Например: `/start CODE`", parse_mode="Markdown")
        return
        
    code = args[1]
    
    try:
        res = supabase.table("invites").select("*").eq("code", code).execute()
        invites = res.data
        
        if not invites or invites[0].get("used"):
            await message.answer("❌ Инвайт недействителен или уже использован.\nНапиши нам: @chpk")
            return
            
        await state.update_data(invite_id=invites[0]["id"])
        await message.answer("Привет! Давай зарегистрируем твой барбершоп.\n\nКак называется твой барбершоп?")
        await state.set_state(RegisterShop.name)
        
    except Exception as e:
        logger.error(f"Error checking invite: {e}")
        await message.answer("Произошла ошибка при проверке кода. Попробуйте позже.")

@router.message(RegisterShop.name)
async def process_name(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введи название текстом. Как называется твой барбершоп?")
        return
        
    await state.update_data(name=message.text.strip())
    await message.answer("Отлично! В каком городе?")
    await state.set_state(RegisterShop.city)

@router.message(RegisterShop.city)
async def process_city(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введи город текстом. В каком городе находится барбершоп?")
        return
        
    await state.update_data(city=message.text.strip())
    await message.answer("Принято. Напиши номер телефона для связи?")
    await state.set_state(RegisterShop.phone)

@router.message(RegisterShop.phone)
async def process_phone(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, введи номер телефона текстом.")
        return
        
    await state.update_data(phone=message.text.strip())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_instagram")]
    ])
    
    await message.answer("Супер! Отправь ссылку на Instagram или 2GIS (или нажми 'Пропустить')", reply_markup=kb)
    await state.set_state(RegisterShop.instagram)

async def finish_registration(message_or_call, state: FSMContext, instagram_link: str = ""):
    data = await state.get_data()
    name = data['name']
    city = data['city']
    phone = data['phone']
    invite_id = data['invite_id']
    
    telegram_id = message_or_call.from_user.id
    slug = generate_slug(name, city)
    
    # Ensure unique slug
    base_slug = slug
    counter = 1
    while True:
        res = supabase.table("barbershops").select("id").eq("slug", slug).execute()
        if not res.data:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1
        
    try:
        # Insert shop
        shop_data = {
            "name": name,
            "city": city,
            "phone": phone,
            "instagram": instagram_link,
            "slug": slug,
            "owner_telegram_id": telegram_id
        }
        supabase.table("barbershops").insert(shop_data).execute()
        
        # Mark invite used
        supabase.table("invites").update({
            "used": True,
            "used_by": telegram_id
        }).eq("id", invite_id).execute()
        
        success_msg = (
            "✅ Барбершоп подключён к CHOPBAR!\n\n"
            f"💈 Ссылка для клиентов:\n"
            f"t.me/ChopPavlodarBot?start={slug}\n\n"
            f"👨‍💼 Ссылка для мастеров:\n"
            f"t.me/ChopCrewBot?start={slug}\n\n"
            f"⚙️ Твоя админ-панель:\n"
            f"t.me/ChopPavlodarAdminBot?start={slug}\n\n"
            "Сохрани эти ссылки — они твои навсегда."
        )
        
        if isinstance(message_or_call, CallbackQuery):
            await message_or_call.message.answer(success_msg)
            await message_or_call.answer()
        else:
            await message_or_call.answer(success_msg)
            
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error saving shop: {e}")
        error_msg = "Произошла ошибка при сохранении данных. Пожалуйста, обратитесь в поддержку."
        if isinstance(message_or_call, CallbackQuery):
            await message_or_call.message.answer(error_msg)
            await message_or_call.answer()
        else:
            await message_or_call.answer(error_msg)

@router.callback_query(F.data == "skip_instagram", RegisterShop.instagram)
async def skip_instagram(call: CallbackQuery, state: FSMContext):
    await finish_registration(call, state, "")

@router.message(RegisterShop.instagram)
async def process_instagram(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Отправь ссылку текстом или нажми 'Пропустить' на предыдущем сообщении.")
        return
        
    await finish_registration(message, state, message.text.strip())

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