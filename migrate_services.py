# -*- coding: utf-8 -*-

import os
import json
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Supabase credentials missing")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def migrate():
    # 1. Check if table exists (by trying to select)
    try:
        print("Checking 'services' table...")
        supabase.table("services").select("*").limit(1).execute()
        print("'services' table exists.")
    except Exception as e:
        print(f"Table check failed (might not exist): {e}")
        # We can't create table via client usually, but we can try to insert data 
        # and hope the user created it or we need to ask user.
        # However, often in these environments we assume we can't CREATE TABLE via API unless we use SQL editor.
        # Let's try to proceed with migration. If it fails, we'll know.
    
    # 2. Load JSON data
    with open("data/barbershop.json", "r") as f:
        data = json.load(f)
        services = data.get("services", [])
        
    print(f"Found {len(services)} services in JSON.")
    
    # 3. Insert into Supabase
    for s in services:
        # Check if exists
        try:
            # Check by name
            existing = supabase.table("services").select("*").eq("name", s["name"]).execute()
            if not existing.data:
                print(f"Migrating: {s['name']}")
                payload = {
                    "name": s["name"],
                    "price": s["price"],
                    "duration_minutes": s["duration_minutes"]
                }
                supabase.table("services").insert(payload).execute()
            else:
                print(f"Skipping {s['name']} (already exists)")
        except Exception as e:
            print(f"Error migrating {s['name']}: {e}")
            
    print("Migration check complete.")

if __name__ == "__main__":
    migrate()
