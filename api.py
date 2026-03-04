import os
import json
import re
import datetime
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
    telegram_id: Union[str, int] # Allow int or str

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

# --- ENDPOINTS ---

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

@app.post("/booking")
async def create_booking(booking: BookingModel):
    booking_data = booking.dict()
    
    # Generate UUID for the booking
    booking_data["id"] = str(uuid.uuid4())
    # Ensure telegram_id is string for Supabase
    booking_data["telegram_id"] = str(booking_data["telegram_id"])
    
    if supabase:
        try:
            response = supabase.table("bookings").insert(booking_data).execute()
            # If successful, return the data from DB
            return {"status": "success", "data": response.data[0]}
        except Exception as e:
            print(f"Supabase error: {e}")
            return JSONResponse(status_code=500, content={"error": "Database error", "details": str(e)})
    else:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

@app.get("/bookings")
async def get_bookings():
    if supabase:
        try:
            response = supabase.table("bookings").select("*").order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Supabase fetch error: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})
    else:
        return []

@app.get("/bookings/slots")
async def get_occupied_slots(master: str, date: str):
    if not supabase:
        return {"occupied": []}
    try:
        # User wants occupied times for that master on that date
        # Also exclude cancelled bookings
        result = supabase.table('bookings')\
            .select('time')\
            .eq('master', master)\
            .eq('date', date)\
            .neq('status', 'cancelled')\
            .execute()
        return {"occupied": [b['time'] for b in result.data]}
    except Exception as e:
        print(f"Error fetching slots: {e}")
        return {"occupied": [], "error": str(e)}

@app.get("/booking/active")
async def get_active_booking(telegram_id: str):
    if not supabase:
        return {"active": None}
    try:
        # Check for future bookings that are 'new'
        # We need to filter by date/time > now
        # Supabase filtering for date/time > now is tricky with separate date/time columns.
        # We'll fetch all 'new' bookings for the user and filter in python for simplicity
        # unless there are thousands, which is unlikely for a single user.
        
        response = supabase.table('bookings')\
            .select('*')\
            .eq('telegram_id', telegram_id)\
            .eq('status', 'new')\
            .execute()
            
        bookings = response.data
        now = datetime.datetime.now()
        
        active = None
        for b in bookings:
            try:
                booking_dt = datetime.datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
                if booking_dt > now:
                    # Found a future booking
                    # If multiple, take the soonest one? Or just the first found?
                    # Let's take the soonest one.
                    if active is None:
                        active = b
                        active['dt'] = booking_dt
                    elif booking_dt < active['dt']:
                        active = b
                        active['dt'] = booking_dt
            except ValueError:
                continue # Skip invalid date formats
        
        if active:
            # Remove the temp dt object before returning
            del active['dt']
            return active
        else:
            return None # No active booking
            
    except Exception as e:
        print(f"Error fetching active booking: {e}")
        return {"error": str(e)}

@app.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str):
    if supabase:
        try:
            # Update status to cancelled
            response = supabase.table("bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
            return {"status": "cancelled", "id": booking_id}
        except Exception as e:
            print(f"Supabase delete error: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})
    else:
        return JSONResponse(status_code=503, content={"error": "Database not configured"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
