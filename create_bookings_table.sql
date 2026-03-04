-- Create bookings table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.bookings (
    id text PRIMARY KEY,
    master text,
    service text,
    price numeric,
    date text,
    time text,
    duration integer,
    telegram_id text,
    status text DEFAULT 'new',
    created_at timestamp with time zone DEFAULT now(),
    notified_24h boolean DEFAULT false,
    notified_2h boolean DEFAULT false
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;

-- Drop policy if it exists to avoid error on recreation
DROP POLICY IF EXISTS "Enable access for all users" ON public.bookings;

-- Create policy for public access (since we use anon/publishable key)
CREATE POLICY "Enable access for all users" ON public.bookings
    FOR ALL
    USING (true)
    WITH CHECK (true);
