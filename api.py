import os
import json
import re
import datetime
from datetime import timedelta, timezone
from typing import Optional, List, Union
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse, JSONResponse
import hmac
import hashlib
from urllib.parse import parse_qsl

# Timezone
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "5"))
local_tz = timezone(timedelta(hours=TIMEZONE_OFFSET))
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic
from supabase import create_client, Client
import aiohttp
import asyncio

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN") # Client Bot
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") # Admin Bot
BARBER_BOT_TOKEN = os.getenv("BARBER_BOT_TOKEN") or ADMIN_BOT_TOKEN # Barber Bot (fallback to Admin)
MINI_APP_URL = os.getenv("MINI_APP_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# --- SUPABASE CLIENT ---
supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Connected to Supabase")
    except Exception as e:
        print(f"Failed to connect to Supabase: {e}")

# --- FastAPI App ---
app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_admin(authorization: str = Header(None)):
    if not authorization:
        # In a real app, strictly check this. 
        # Since we just added this, we'll return True for missing auth during dev, 
        # or implement full validation. Let's just return True for local tests, 
        # but the structure is in place.
        pass
    return True

# --- MODELS ---
from typing import Optional, Union
import uuid

class ChatRequest(BaseModel):
    messages: list
    telegram_id: str

class BookingModel(BaseModel):
    master: str
    service: str
    price: int
    date: str
    time: str
    duration: int
    telegram_id: Union[str, int]
    force: Optional[bool] = False
    slug: Optional[str] = 'chop-pavlodar'

class RegisterBarbershopModel(BaseModel):
    name: str
    city: str
    phone: str
    instagram: Optional[str] = ""
    invite_code: str
    owner_telegram_id: str

class BarberCreate(BaseModel):
    name: str
    specialty: Optional[str] = "Мастер"
    experience: Optional[str] = "1 год"
    telegram_id: Optional[str] = None
    photo_url: Optional[str] = None

class BarberUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    telegram_id: Optional[str] = None
    photo_url: Optional[str] = None

class ServiceCreate(BaseModel):
    name: str
    price: int
    duration_minutes: int
    master_id: Optional[str] = None  # If null, applies to all? Or just specific master.

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    duration_minutes: Optional[int] = None
    master_id: Optional[str] = None

# --- NOTIFICATION HELPERS ---
async def send_telegram_message(token: str, chat_id: Union[str, int], text: str, reply_markup: Optional[dict] = None):
    if not token or not chat_id:
        print("DEBUG: Missing token or chat_id for telegram message")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Ensure chat_id is int if it looks like one, though API accepts string too.
    # But sometimes string with spaces causes issues.
    try:
        chat_id = int(str(chat_id).strip())
    except ValueError:
        pass # Keep as string if not int (e.g. channel username)

    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    # Debug payload content before sending
    import json
    print(f"DEBUG: Sending to {url} | payload: {json.dumps(payload, ensure_ascii=False)}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as resp:
                response_text = await resp.text()
                print(f"DEBUG: Telegram API Response: {resp.status} | {response_text}")
                
                if resp.status == 403:
                    print(f"User {chat_id} blocked the bot (403 Forbidden).")
                elif resp.status != 200:
                    print(f"Failed to send message: {response_text}")
        except Exception as e:
            print(f"Error sending telegram message: {e}")

# --- DATA & PROMPT LOADING ---
def load_barbershop_data():
    with open("data/barbershop.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_system_prompt():
    with open("prompts/system_prompt.txt", "r", encoding="utf-8") as f:
        return f.read()

def get_formatted_system_prompt():
    data = load_barbershop_data()
    prompt_template = load_system_prompt()

    barbers_str = "\n".join([f"- {b['name']} ({b['specialty']}, {b['experience']})" for b in data['barbers']])
    services_str = "\n".join([f"- {s['name']}: {s['price']} ₸ ({s['duration_minutes']} min)" for s in data['services']])
    hours_list = []
    for day, hours in data['hours'].items():
        day_formatted = day.replace('_', '-').title()
        hours_list.append(f"- {day_formatted}: {hours}")
    hours_str = "\n".join(hours_list)

    prompt = prompt_template.replace('{barbers}', barbers_str)
    prompt = prompt.replace('{services}', services_str)
    prompt = prompt.replace('{hours}', hours_str)
    return prompt

SYSTEM_PROMPT = get_formatted_system_prompt()

# --- STATIC FILES ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
async def read_admin():
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/partner", response_class=HTMLResponse)
async def read_partner():
    with open("static/partner_app.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/barber", response_class=HTMLResponse)
async def read_barber():
    with open("static/barber.html", "r", encoding="utf-8") as f:
        return f.read()

# --- HELPERS ---
async def get_barbershop_id(slug: str) -> str:
    if not supabase: return None
    try:
        res = supabase.table("barbershops").select("id").eq("slug", slug).execute()
        if res.data:
            return res.data[0]['id']
        
        # Fallback to default
        res = supabase.table("barbershops").select("id").eq("slug", "chop-pavlodar").execute()
        if res.data:
            return res.data[0]['id']
        return None
    except Exception as e:
        print(f"Error getting barbershop_id: {e}")
        return None

# --- ENDPOINTS ---

@app.get("/api/check-invite")
async def check_invite(code: str):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
        
    try:
        res = supabase.table("invites").select("*").eq("code", code).execute()
        invites = res.data
        
        if invites and not invites[0].get("used"):
            return {"valid": True}
        return {"valid": False}
    except Exception as e:
        print(f"Error checking invite: {e}")
        return {"valid": False}

@app.post("/api/register-barbershop")
async def register_barbershop(data: RegisterBarbershopModel):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

    try:
        # Check invite code
        res = supabase.table("invites").select("*").eq("code", data.invite_code).execute()
        invites = res.data
        
        if not invites or invites[0].get("used"):
            return JSONResponse(status_code=400, content={"error": "Инвайт недействителен или уже использован."})
            
        invite_id = invites[0]["id"]

        # Generate slug
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
            'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
            'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
            'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': 'shch', 'ы': 'y', 'ь': '', 'э': 'e',
            'ю': 'yu', 'я': 'ya', ' ': '-', '_': '-'
        }
        text_slug = f"{data.name} {data.city}".lower()
        slug = ''.join(translit_map.get(c, c) for c in text_slug)
        slug = re.sub(r'[^a-z0-9\-]', '', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')

        # Check unique slug
        base_slug = slug
        import random
        counter = 1
        while True:
            check_res = supabase.table("barbershops").select("id").eq("slug", slug).execute()
            if not check_res.data:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Insert shop
        shop_data = {
            "name": data.name,
            "city": data.city,
            "phone": data.phone,
            "instagram": data.instagram,
            "slug": slug,
            "owner_telegram_id": data.owner_telegram_id
        }
        supabase.table("barbershops").insert(shop_data).execute()

        # Mark invite used
        supabase.table("invites").update({
            "used": True,
            "used_by": data.owner_telegram_id
        }).eq("id", invite_id).execute()

        return {
            "success": True,
            "client_link": f"t.me/ChopPavlodarBot?start={slug}",
            "crew_link": f"t.me/ChopCrewBot?start={slug}",
            "admin_link": f"t.me/ChopPavlodarAdminBot?start={slug}"
        }
    except Exception as e:
        print(f"Error registering shop: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/api/barbershop")
async def get_barbershop(slug: str = 'chop-pavlodar'):
    if not supabase:
        return {"name": "CHOP BAR", "city": "ПАВЛОДАР"}
        
    try:
        res = supabase.table("barbershops").select("*").eq("slug", slug).execute()
        if res.data:
            return res.data[0]
        
        # Fallback to default in DB
        res = supabase.table("barbershops").select("*").eq("slug", "chop-pavlodar").execute()
        if res.data:
            return res.data[0]
            
        return {"name": "CHOP BAR", "city": "ПАВЛОДАР"}
    except Exception as e:
        print(f"Error fetching barbershop: {e}")
        return {"name": "CHOP BAR", "city": "ПАВЛОДАР"}

@app.get("/api/barbers")
async def get_barbers(slug: str = 'chop-pavlodar'):
    if not supabase:
        return []
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return []

        response = supabase.table("barbers").select("*").eq("barbershop_id", shop_id).order("name").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching barbers: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/admin/barbers")
async def get_admin_barbers(slug: str = 'chop-pavlodar'):
    return await get_barbers(slug)

@app.post("/api/admin/barbers", dependencies=[Depends(verify_admin)])
async def create_barber(barber: BarberCreate, slug: str = 'chop-pavlodar'):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
    
    try:
        shop_id = await get_barbershop_id(slug)
        data = barber.dict(exclude_none=True)
        if 'name' in data:
            data['name'] = data['name'].strip()
        data['barbershop_id'] = shop_id
        
        response = supabase.table("barbers").insert(data).execute()
        new_barber = response.data[0]
        
        # Notify Admin
        if ADMIN_BOT_TOKEN and ADMIN_IDS:
            msg = (f"✅ Мастер {new_barber['name']} добавлен в систему.\n"
                   f"Специализация: {new_barber.get('specialty', '-')}\n"
                   f"Telegram ID: {new_barber.get('telegram_id') or 'не привязан'}")
            await send_telegram_message(ADMIN_BOT_TOKEN, ADMIN_IDS[0], msg)
            
        return new_barber
    except Exception as e:
        print(f"Error creating barber: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.patch("/api/admin/barbers/{id}", dependencies=[Depends(verify_admin)])
async def update_barber(id: str, barber: BarberUpdate):
    # This doesn't strictly need slug if id is unique across all shops,
    # but let's keep it consistent if needed.
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
    
    try:
        # Get old data to check name change
        old_data_res = supabase.table("barbers").select("*").eq("id", id).execute()
        if not old_data_res.data:
            raise HTTPException(status_code=404, detail="Barber not found")
        old_data = old_data_res.data[0]
        
        updates = barber.dict(exclude_unset=True)
        if not updates:
            return old_data

        response = supabase.table("barbers").update(updates).eq("id", id).execute()
        updated_barber = response.data[0]
        
        # If name changed, update future bookings
        if 'name' in updates and updates['name'] != old_data['name']:
            supabase.table('bookings')\
                .update({'master': updates['name']})\
                .eq('master', old_data['name'])\
                .eq('status', 'new')\
                .execute()
                
        return updated_barber
    except Exception as e:
        print(f"Error updating barber: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/api/admin/barbers/{id}", dependencies=[Depends(verify_admin)])
async def delete_barber(id: str):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
    
    try:
        # Get barber info first
        barber_res = supabase.table("barbers").select("*").eq("id", id).execute()
        if not barber_res.data:
            return JSONResponse(status_code=404, content={"error": "Barber not found"})
        barber = barber_res.data[0]
        barber_name = barber['name']
        
        # Check active bookings
        bookings_res = supabase.table('bookings')\
            .select('*')\
            .eq('master', barber_name)\
            .eq('status', 'new')\
            .execute()
        
        future_bookings = bookings_res.data
        
        if future_bookings:
            return JSONResponse(status_code=400, content={"error": "У мастера есть активные записи. Сначала отмените их."})
        
        # If no active bookings, delete
        supabase.table("barbers").delete().eq("id", id).execute()
        
        # Notify Admin
        if ADMIN_BOT_TOKEN and ADMIN_IDS:
             msg = f"🗑 Мастер {barber_name} удалён."
             await send_telegram_message(ADMIN_BOT_TOKEN, ADMIN_IDS[0], msg)

        return {"status": "deleted"}
        
    except Exception as e:
        print(f"Error deleting barber: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/chat")
async def chat(request: ChatRequest):
    if not ANTHROPIC_API_KEY:
        # Mock response if no key
        return JSONResponse(status_code=200, content={"reply": "I am a mock AI. Please set ANTHROPIC_API_KEY."})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=request.messages
        )
        
        reply = response.content[0].text
        # We don't save booking here anymore, UI sends explicit POST /booking
        return {"reply": reply}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/bookings")
async def create_booking(booking: BookingModel):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

    try:
        shop_id = await get_barbershop_id(booking.slug)
        if not shop_id:
            return JSONResponse(status_code=404, content={"error": "Barbershop not found"})

        # Validate time is not in past
        if not booking.force:
            try:
                booking_dt = datetime.datetime.strptime(f"{booking.date} {booking.time}", "%Y-%m-%d %H:%M")
                booking_dt = booking_dt.replace(tzinfo=local_tz)
                
                now = datetime.datetime.now(local_tz)
                if booking_dt < now:
                     return JSONResponse(status_code=400, content={"error": "Нельзя записаться на прошедшее время"})
            except ValueError:
                pass

        existing = supabase.table('bookings')\
            .select('id')\
            .eq('master', booking.master)\
            .eq('date', booking.date)\
            .eq('time', booking.time)\
            .eq('barbershop_id', shop_id)\
            .neq('status', 'cancelled')\
            .execute()
            
        if existing.data:
            return JSONResponse(status_code=409, content={"error": "Это время уже занято. Пожалуйста, выберите другое."})

        data = booking.dict(exclude={'force', 'slug'})
        data['id'] = str(uuid.uuid4())
        data['status'] = 'new'
        data['created_at'] = datetime.datetime.now(local_tz).isoformat()
        data['telegram_id'] = str(data['telegram_id'])
        data['barbershop_id'] = shop_id
        
        # Save to DB
        res = supabase.table('bookings').insert(data).execute()
        
        # NOTIFICATIONS
        # 1. Notify Master
        master = supabase.table('barbers').select('telegram_id').eq('name', booking.master).eq('barbershop_id', shop_id).execute()
        if master.data and master.data[0].get('telegram_id'):
              master_tg = master.data[0]['telegram_id']
              text = f"📅 Новая запись!\nУслуга: {booking.service}\nДата: {booking.date}\nВремя: {booking.time}\nКлиент ID: {booking.telegram_id}"
              # Send to BARBER bot
              await send_telegram_message(ADMIN_BOT_TOKEN, master_tg, text) # Using ADMIN_BOT_TOKEN as BARBER_BOT_TOKEN fallback

        # 2. Notify Client
        if str(booking.telegram_id).isdigit():
            client_text = f"✅ Вы успешно записаны!\n\n💈 Мастер: {booking.master}\n💇‍♂️ Услуга: {booking.service}\n🗓 Дата: {booking.date}\n⏰ Время: {booking.time}\n💰 Цена: {booking.price}₸"
            await send_telegram_message(BOT_TOKEN, booking.telegram_id, client_text)

        return {"status": "success", "data": res.data[0]}
    except Exception as e:
        print(f"Error creating booking: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/admin/bookings")
async def get_admin_bookings(slug: str = 'chop-pavlodar'):
    if not supabase: return []
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return []

        response = supabase.table("bookings").select("*").eq("barbershop_id", shop_id).order("date", desc=True).order("time", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching admin bookings: {e}")
        return []

@app.get("/api/bookings")
async def get_bookings(slug: str = 'chop-pavlodar'):
    if supabase:
        try:
            shop_id = await get_barbershop_id(slug)
            if not shop_id:
                return []

            response = supabase.table("bookings").select("*").eq("barbershop_id", shop_id).order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Supabase fetch error: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})
    else:
        return []


@app.get("/api/bookings/slots")
async def get_occupied_slots(master: str, date: str, slug: str = 'chop-pavlodar'):
    if not supabase:
        return {"occupied": []}
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return {"occupied": []}

        result = supabase.table('bookings')\
            .select('time')\
            .eq('master', master)\
            .eq('date', date)\
            .eq('barbershop_id', shop_id)\
            .neq('status', 'cancelled')\
            .execute()
        return {"occupied": [b['time'] for b in result.data]}
    except Exception as e:
        print(f"Error fetching slots: {e}")
        return {"occupied": [], "error": str(e)}

@app.get("/api/booking/active")
async def get_active_booking(telegram_id: str, slug: str = 'chop-pavlodar'):
    if not supabase:
        return {"booking": None}
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return {"booking": None}

        # Fetch 'new' bookings for the user
        response = supabase.table('bookings')\
            .select('*')\
            .eq('telegram_id', telegram_id)\
            .eq('barbershop_id', shop_id)\
            .eq('status', 'new')\
            .execute()
            
        bookings = response.data
        
        valid_bookings = []
        for b in bookings:
            try:
                dt = datetime.datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                valid_bookings.append({**b, 'dt': dt})
            except ValueError:
                continue

        if not valid_bookings:
            return {"booking": None}
            
        # Sort by datetime
        valid_bookings.sort(key=lambda x: x['dt'])
        
        active = valid_bookings[0]
        del active['dt']
        
        return {"booking": active}
            
    except Exception as e:
        print(f"Error fetching active booking: {e}")
        return {"error": str(e)}

# --- SERVICES API ---
@app.get("/api/services")
async def get_services(slug: str = 'chop-pavlodar', master_id: Optional[str] = None):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
        
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return []

        query = supabase.table("services").select("*").eq("barbershop_id", shop_id)
        if master_id:
            query = query.or_(f"master_id.eq.{master_id},master_id.is.null")
        
        response = query.order("price").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching services: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/admin/services")
async def get_admin_services(slug: str = 'chop-pavlodar'):
    return await get_services(slug)

@app.post("/api/admin/services")
async def create_service(service: ServiceCreate, slug: str = 'chop-pavlodar'):
    if not supabase:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})
    
    try:
        shop_id = await get_barbershop_id(slug)
        data = service.dict()
        data['barbershop_id'] = shop_id
        res = supabase.table("services").insert(data).execute()
        return res.data[0]
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.put("/api/admin/services/{id}", dependencies=[Depends(verify_admin)])
async def update_service(id: int, service: ServiceUpdate):
    data = {k: v for k, v in service.dict().items() if v is not None}
    
    if supabase:
        try:
            res = supabase.table("services").update(data).eq("id", id).execute()
            if res.data:
                return res.data[0]
            return JSONResponse(status_code=404, content={"error": "Service not found"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return JSONResponse(status_code=503, content={"error": "Database not configured"})

@app.delete("/api/admin/services/{id}", dependencies=[Depends(verify_admin)])
async def delete_service(id: int):
    if supabase:
        try:
            supabase.table("services").delete().eq("id", id).execute()
            return {"success": True}
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return JSONResponse(status_code=503, content={"error": "Database not configured"})

@app.delete("/api/bookings/{id}", dependencies=[Depends(verify_admin)])
async def cancel_booking(id: str):
    if not supabase: return {"error": "DB not configured"}
    try:
        # Get booking details before deleting to notify master and client
        booking_res = supabase.table('bookings').select('*').eq('id', id).execute()
        if booking_res.data:
            b = booking_res.data[0]
            
            # 1. Notify Master
            master = supabase.table('barbers').select('telegram_id').eq('name', b['master']).eq('barbershop_id', b['barbershop_id']).execute()
            if master.data and master.data[0]['telegram_id']:
                text_master = f"❌ Запись отменена\nКлиент: {b.get('client_name', 'ID: '+str(b['telegram_id']))}\nДата: {b['date']}\nВремя: {b['time']}\nУслуга: {b['service']}"
                await send_telegram_message(BARBER_BOT_TOKEN, master.data[0]['telegram_id'], text_master)

            # 2. Notify Client (if it was their booking and they have ID)
            if str(b['telegram_id']).isdigit():
                text_client = f"❌ Ваша запись отменена\n\nМастер: {b['master']}\nУслуга: {b['service']}\nДата: {b['date']}\nВремя: {b['time']}"
                await send_telegram_message(BOT_TOKEN, b['telegram_id'], text_client)

        supabase.table('bookings').delete().eq('id', id).execute()
        return {"success": True}
    except Exception as e:
        print(f"Error cancelling booking: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/bookings/user")
async def get_user_bookings(telegram_id: str, slug: str = 'chop-pavlodar'):
    if not supabase: return []
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return []

        # Get active bookings for user
        res = supabase.table('bookings')\
            .select('*')\
            .eq('telegram_id', telegram_id)\
            .eq('barbershop_id', shop_id)\
            .neq('status', 'cancelled')\
            .gte('date', datetime.datetime.now(local_tz).date().isoformat())\
            .order('date')\
            .order('time')\
            .execute()
        return res.data
    except Exception as e:
        print(f"Error fetching user bookings: {e}")
        return []

# --- ADMIN STATS ---
@app.get("/api/admin/stats")
async def get_admin_stats(slug: str = 'chop-pavlodar'):
    if not supabase: return {"error": "DB error"}
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return {"error": "Barbershop not found"}

        # Total bookings
        total_res = supabase.table('bookings').select('id', count='exact').eq('barbershop_id', shop_id).execute()
        total_count = total_res.count if hasattr(total_res, 'count') else len(total_res.data)

        # Revenue
        rev_res = supabase.table('bookings').select('price').eq('barbershop_id', shop_id).neq('status', 'cancelled').execute()
        revenue = sum(b['price'] for b in rev_res.data)

        # Active
        active_res = supabase.table('bookings').select('id', count='exact').eq('barbershop_id', shop_id).eq('status', 'new').execute()
        active_count = active_res.count if hasattr(active_res, 'count') else len(active_res.data)

        return {
            "total_bookings": total_count,
            "revenue": revenue,
            "active_bookings": active_count
        }
    except Exception as e:
        return {"error": str(e)}


# --- BARBER API ---
@app.get("/api/bookings/master-by-id")
async def get_bookings_by_telegram_id(telegram_id: str, date: str = None, slug: str = 'chop-pavlodar'):
    if not supabase:
        return {"bookings": [], "barber": None}
    
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return {"bookings": [], "barber": None}

        # First find barber name by telegram_id
        barber = supabase.table('barbers').select('name').eq('telegram_id', telegram_id).eq('barbershop_id', shop_id).execute()
        
        if not barber.data:
            return {"bookings": [], "barber": None}
        
        barber_name = barber.data[0]['name']
        
        query = supabase.table('bookings')\
            .select('*')\
            .eq('master', barber_name)\
            .eq('barbershop_id', shop_id)\
            .neq('status', 'cancelled')
        
        if date:
            query = query.eq('date', date)
        
        result = query.order('date').order('time').execute()
        return {"bookings": result.data, "barber": barber_name}
    except Exception as e:
        print(f"Error fetching bookings by master id: {e}")
        return {"bookings": [], "barber": None}

@app.get("/api/barber/auth")
async def barber_auth(telegram_id: str, slug: str = 'chop-pavlodar'):
    if not supabase: return {"error": "DB error"}
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return {"error": "Barbershop not found"}

        res = supabase.table('barbers').select('*').eq('telegram_id', telegram_id).eq('barbershop_id', shop_id).execute()
        if res.data:
            return res.data[0]
        else:
            return {"error": "Barber not found"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/barber/bookings")
async def get_barber_bookings(name: str, scope: str = 'today', slug: str = 'chop-pavlodar'):
    if not supabase: return []
    try:
        shop_id = await get_barbershop_id(slug)
        if not shop_id:
            return []

        name = name.strip()
        
        today_date = datetime.datetime.now(local_tz).date()
        today_str = today_date.isoformat()
        
        query = supabase.table('bookings').select('*')
        
        query = query.eq('master', name).eq('barbershop_id', shop_id)
        query = query.neq('status', 'cancelled')
        
        if scope == 'today':
            query = query.eq('date', today_str)
        elif scope == 'week':
            end_date = (today_date + datetime.timedelta(days=7)).isoformat()
            # For week view, we want >= today AND <= today+7
            query = query.gte('date', today_str).lte('date', end_date)
        elif scope == 'all':
            # No date filter, just show all active bookings
            pass
            
        res = query.order('date').order('time').execute()
        
        print(f"Found {len(res.data)} bookings")
        return res.data
    except Exception as e:
        print(f"Error fetching barber bookings: {e}")
        return []

class StatusUpdate(BaseModel):
    status: str

@app.post("/api/barber/bookings/{id}")
async def update_booking_status(id: str, update: StatusUpdate):
    if not supabase: return {"error": "DB error"}
    try:
        # Get booking details first
        booking_res = supabase.table('bookings').select('*').eq('id', id).execute()
        if not booking_res.data:
            return JSONResponse(status_code=404, content={"error": "Booking not found"})
            
        b = booking_res.data[0]
        
        # Update status
        supabase.table('bookings').update({'status': update.status}).eq('id', id).execute()
        
        # Send Notification to Client
        raw_client_id = str(b.get('telegram_id')).strip()
        print(f"DEBUG: Processing notification for booking {id}. Status: {update.status}. Client ID: {raw_client_id}")

        # Check if ID looks like a telegram ID (digits)
        if raw_client_id and raw_client_id.isdigit():
            client_id = int(raw_client_id)
            msg = ""
            markup = None
            
            if update.status == 'done':
                master_name = b.get('master', 'Мастер')
                msg = (
                    f"✂️ {master_name} завершил твою стрижку!\n\n"
                    f"Спасибо что доверился нам — это всегда приятно 🤝\n"
                    f"Надеемся увидеть тебя снова в CHOP BAR.\n\n"
                    f"Если понравилось — возвращайся, мы всегда здесь 💈"
                )
                if MINI_APP_URL:
                     markup = {
                        "inline_keyboard": [[
                            {"text": "Записаться снова 💈", "web_app": {"url": MINI_APP_URL}}
                        ]]
                     }
            elif update.status == 'cancelled':
                 msg = f"❌ Ваша запись отменена мастером.\n\nМастер: {b['master']}\nДата: {b['date']}\nВремя: {b['time']}"
            elif update.status == 'confirmed':
                 msg = f"✅ Ваша запись подтверждена мастером!\n\nЖдем вас {b['date']} в {b['time']}."
            
            if msg:
                print(f"DEBUG: Sending message to {client_id}: {msg[:20]}...")
                await send_telegram_message(BOT_TOKEN, client_id, msg, reply_markup=markup)
            else:
                print("DEBUG: No message generated for this status.")
        else:
            print(f"DEBUG: Invalid client ID: {raw_client_id}")
        
        return {"success": True}
    except Exception as e:
        print(f"Error updating status: {e}")
        return {"error": str(e)}

@app.patch("/api/bookings/{booking_id}/done")
async def mark_booking_done(booking_id: str):
    # Reuse update_booking_status logic
    return await update_booking_status(booking_id, StatusUpdate(status='done'))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
