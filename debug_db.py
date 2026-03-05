import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_data():
    print("--- BOOKINGS ---")
    bookings = supabase.table('bookings').select('*').execute()
    for b in bookings.data:
        print(f"ID: {b.get('id')} | Master: '{b.get('master')}' | Date: {b.get('date')} | Status: {b.get('status')}")

    print("\n--- BARBERS ---")
    barbers = supabase.table('barbers').select('*').execute()
    for b in barbers.data:
        print(f"Name: '{b.get('name')}' | TG ID: {b.get('telegram_id')}")

if __name__ == "__main__":
    check_data()
