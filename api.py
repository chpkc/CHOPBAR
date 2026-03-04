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
    telegram_id: str

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
    services_str = "\n".join([f"- {s['name']}: ${s['price']} ({s['duration_minutes']} min)" for s in data['services']])
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

# --- BOOKING LOGIC ---

def save_booking_local(booking_data: dict):
    file_path = "data/bookings.json"
    new_booking = {
        "id": str(datetime.datetime.now().timestamp()), # Simple ID for local
        **booking_data,
        "status": "new",
        "created_at": datetime.datetime.now().isoformat()
    }
    
    try:
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, "r+", encoding="utf-8") as f:
                bookings = json.load(f)
                bookings.append(new_booking)
                f.seek(0)
                json.dump(bookings, f, indent=4)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([new_booking], f, indent=4)
        return new_booking
    except Exception as e:
        print(f"Error saving booking locally: {e}")
        return None

def get_bookings_local():
    file_path = "data/bookings.json"
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

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
    
    if supabase:
        try:
            response = supabase.table("bookings").insert(booking_data).execute()
            return {"status": "success", "data": response.data[0]}
        except Exception as e:
            print(f"Supabase error: {e}")
            # Fallback to local? Maybe not for production, but for dev yes.
            saved = save_booking_local(booking_data)
            return {"status": "success", "data": saved, "source": "local_fallback"}
    else:
        saved = save_booking_local(booking_data)
        return {"status": "success", "data": saved, "source": "local"}

@app.get("/bookings")
async def get_bookings():
    if supabase:
        try:
            response = supabase.table("bookings").select("*").order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            print(f"Supabase fetch error: {e}")
            return get_bookings_local()
    else:
        return get_bookings_local()

@app.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str):
    if supabase:
        try:
            # Soft delete
            response = supabase.table("bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
            return {"status": "cancelled"}
        except Exception as e:
            print(f"Supabase delete error: {e}")
            return {"error": str(e)}
    else:
        # Local soft delete (not fully implemented for local JSON to keep it simple, but we can try)
        # For local dev, we just pretend it worked
        return {"status": "cancelled", "note": "Local delete simulated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
