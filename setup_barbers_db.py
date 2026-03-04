import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def setup_db():
    print("--- Checking 'barbers' table ---")
    
    # Check if table exists by selecting
    try:
        supabase.table('barbers').select('*').limit(1).execute()
        print("'barbers' table exists.")
    except Exception as e:
        print(f"Table might be missing or error: {e}")
        print("\nPlease run the following SQL in Supabase SQL Editor to create the table:")
        print("""
create table if not exists barbers (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  telegram_id text unique,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Insert sample data (Update telegram_id with REAL IDs of your barbers!)
insert into barbers (name, telegram_id) values 
  ('Алексей', '123456789'),
  ('Марат', '987654321'),
  ('Дмитрий', '555555555')
on conflict (telegram_id) do nothing;
        """)

if __name__ == "__main__":
    setup_db()
