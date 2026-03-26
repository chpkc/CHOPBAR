# -*- coding: utf-8 -*-

#!/usr/bin/env python3
import os
import logging
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from supabase import create_client, Client

load_dotenv()

BARBER_BOT_TOKEN = os.getenv("BARBER_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
APP_URL = os.getenv("APP_URL", "https://your-domain.up.railway.app")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

router = Router()

@router.message(Command("start"))
async def start(message: types.Message):
    """Checks barber authentication and shows main menu."""
    if not supabase:
        await message.answer("РћС€РёР±РєР° РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє Р±Р°Р·Рµ РґР°РЅРЅС‹С….")
        return

    user_id = str(message.from_user.id)
    
    try:
        # Get barber and their shop slug
        result = supabase.table('barbers').select('name, barbershop_id').eq('telegram_id', user_id).execute()
        
        if not result.data:
            await message.answer("в›”пёЏ РЈ РІР°СЃ РЅРµС‚ РґРѕСЃС‚СѓРїР°. РћР±СЂР°С‚РёС‚РµСЃСЊ Рє Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.")
            return
            
        barber_name = result.data[0]['name']
        shop_id = result.data[0]['barbershop_id']
        
        # Get slug
        shop_res = supabase.table('barbershops').select('slug').eq('id', shop_id).execute()
        slug = shop_res.data[0]['slug'] if shop_res.data else 'chop-pavlodar'
        
        # URL to the actual Railway deployment with parameters
        app_url = f"{APP_URL}/static/barber.html?master_id={user_id}&slug={slug}"
        
        logger.info(f"Generated WebApp URL: {app_url}")
        
        kb = [[KeyboardButton(text="вњ‚пёЏ РћС‚РєСЂС‹С‚СЊ СЂР°Р±РѕС‡РёР№ СЃС‚РѕР»", web_app=WebAppInfo(url=app_url))]]
        
        await message.answer(
            f"рџ‘‹ РџСЂРёРІРµС‚, {barber_name}!\nРќР°Р¶РјРё РєРЅРѕРїРєСѓ РЅРёР¶Рµ, С‡С‚РѕР±С‹ РѕС‚РєСЂС‹С‚СЊ СЂР°СЃРїРёСЃР°РЅРёРµ.",
            reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        )
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        await message.answer("РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР° РїСЂРё Р°РІС‚РѕСЂРёР·Р°С†РёРё.")

async def main():
    if not BARBER_BOT_TOKEN:
        logger.error("Error: BARBER_BOT_TOKEN not found in .env")
        return

    bot = Bot(token=BARBER_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Barber Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())



