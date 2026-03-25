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
APP_URL = os.getenv("APP_URL", "https://your-domain.up.railway.app")

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
        'Р°': 'a', 'Р±': 'b', 'РІ': 'v', 'Рі': 'g', 'Рґ': 'd', 'Рµ': 'e', 'С‘': 'e', 'Р¶': 'zh',
        'Р·': 'z', 'Рё': 'i', 'Р№': 'y', 'Рє': 'k', 'Р»': 'l', 'Рј': 'm', 'РЅ': 'n', 'Рѕ': 'o',
        'Рї': 'p', 'СЂ': 'r', 'СЃ': 's', 'С‚': 't', 'Сѓ': 'u', 'С„': 'f', 'С…': 'h', 'С†': 'ts',
        'С‡': 'ch', 'С€': 'sh', 'С‰': 'shch', 'СЉ': 'shch', 'С‹': 'y', 'СЊ': '', 'СЌ': 'e',
        'СЋ': 'yu', 'СЏ': 'ya', ' ': '-', '_': '-'
    }
    
    text = f"{name} {city}".lower()
    slug = ''.join(translit_map.get(c, c) for c in text)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug

# --- ADMIN COMMANDS ---

@router.message(Command("invite"))
async def cmd_invite(message: Message):
    # РџСЂРѕРІРµСЂРєР°, С‡С‚Рѕ РєРѕРјР°РЅРґСѓ РІС‹Р·РІР°Р» СЃСѓРїРµСЂР°РґРјРёРЅ
    if str(message.from_user.id) != str(SUPER_ADMIN_ID):
        await message.answer("РЈ РІР°СЃ РЅРµС‚ РїСЂР°РІ РґР»СЏ СЃРѕР·РґР°РЅРёСЏ РёРЅРІР°Р№С‚РѕРІ.")
        return
        
    code = generate_invite_code()
    
    try:
        # РЎРѕС…СЂР°РЅСЏРµРј РёРЅРІР°Р№С‚ РІ Р‘Р”
        supabase.table("invites").insert({"code": code}).execute()
        
        from aiogram.types import WebAppInfo
        web_app = WebAppInfo(url=f"{APP_URL}/static/partner_app.html?invite={code}")
        
        await message.answer(
            f"вњ… РќРѕРІС‹Р№ РёРЅРІР°Р№С‚ СЃРѕР·РґР°РЅ: `{code}`\n\nРћС‚РїСЂР°РІСЊ СЃСЃС‹Р»РєСѓ РЅРёР¶Рµ РІР»Р°РґРµР»СЊС†Сѓ Р±Р°СЂР±РµСЂС€РѕРїР°:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="рџљЂ Р—Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°С‚СЊ Р±Р°СЂР±РµСЂС€РѕРї", web_app=web_app)
            ]])
        )
    except Exception as e:
        logger.error(f"Error creating invite: {e}")
        await message.answer("вќЊ РћС€РёР±РєР° РїСЂРё СЃРѕР·РґР°РЅРёРё РёРЅРІР°Р№С‚Р°.")

@router.message(Command("shops"))
async def cmd_shops(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    try:
        res = supabase.table("barbershops").select("*").execute()
        shops = res.data
        if not shops:
            await message.answer("РќРµС‚ Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°РЅРЅС‹С… Р±Р°СЂР±РµСЂС€РѕРїРѕРІ.")
            return
            
        text = "РЎРїРёСЃРѕРє Р±Р°СЂР±РµСЂС€РѕРїРѕРІ:\n\n"
        for shop in shops:
            date_str = shop['created_at'].split('T')[0] if shop.get('created_at') else 'N/A'
            text += f"рџ’€ {shop['name']} ({shop['city']}) - {date_str}\nSlug: {shop['slug']}\n\n"
            
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error fetching shops: {e}")
        await message.answer("РћС€РёР±РєР° РїСЂРё РїРѕР»СѓС‡РµРЅРёРё СЃРїРёСЃРєР°.")

@router.message(Command("revoke"))
async def cmd_revoke(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: /revoke РљРћР”")
        return
        
    code = parts[1]
    try:
        res = supabase.table("invites").update({"used": True}).eq("code", code).execute()
        if res.data:
            await message.answer(f"РРЅРІР°Р№С‚ {code} РѕС‚РѕР·РІР°РЅ (РїРѕРјРµС‡РµРЅ РёСЃРїРѕР»СЊР·РѕРІР°РЅРЅС‹Рј).")
        else:
            await message.answer("РљРѕРґ РЅРµ РЅР°Р№РґРµРЅ.")
    except Exception as e:
        logger.error(f"Error revoking invite: {e}")
        await message.answer("РћС€РёР±РєР° РїСЂРё РѕС‚Р·С‹РІРµ РёРЅРІР°Р№С‚Р°.")

# --- REGISTRATION FSM ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    # If the user passed an invite code via /start CODE
    invite_code = ""
    args = message.text.split()
    if len(args) > 1:
        invite_code = args[1]
        
    # URL to the actual Railway deployment
    base_url = "{APP_URL}/static/partner_app.html"
    web_app_url = base_url
    
    # Append invite code to URL query parameter
    if invite_code:
        if '?' in web_app_url:
            web_app_url += f"&invite={invite_code}"
        else:
            web_app_url += f"?invite={invite_code}"

    from aiogram.types import WebAppInfo
    kb = [
        [InlineKeyboardButton(text="рџљЂ РЈ РјРµРЅСЏ РµСЃС‚СЊ РєРѕРґ", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    await message.answer(
        "рџ‘‹ РџСЂРёРІРµС‚!\n\n"
        "Р­С‚Рѕ Р±РѕС‚ РґР»СЏ РїРѕРґРєР»СЋС‡РµРЅРёСЏ Р±Р°СЂР±РµСЂС€РѕРїР° Рє СЃРёСЃС‚РµРјРµ CHOPBAR.\n\n"
        "Р§С‚РѕР±С‹ РїРѕР»СѓС‡РёС‚СЊ РёРЅРІР°Р№С‚-РєРѕРґ вЂ” РЅР°РїРёС€Рё: @cheepeek_c\n\n"
        "РљРѕРіРґР° РїРѕР»СѓС‡РёС€СЊ РєРѕРґ, РЅР°Р¶РјРё РєРЅРѕРїРєСѓ РЅРёР¶Рµ рџ‘‡",
        reply_markup=reply_markup
    )



async def start_partner_bot():
    if not PARTNER_BOT_TOKEN:
        logger.error("PARTNER_BOT_TOKEN РЅРµ РЅР°Р№РґРµРЅ!")
        return
        
    bot = Bot(token=PARTNER_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    logger.info("Starting Partner Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_partner_bot())


