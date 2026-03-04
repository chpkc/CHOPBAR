-- Create bookings table
CREATE TABLE public.bookings (
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

-- Enable Row Level Security (RLS) is recommended, but for the bot to work easily with the anon key (if used improperly) or service_role,
-- we might need to open it up or set policies.
-- For now, let's enable RLS and allow public access for simplicity (NOT RECOMMENDED FOR PRODUCTION)
-- OR better: The bot uses the service_role key usually, but here we have a publishable key.
-- If we only have the publishable key, we MUST allow public insert/select/update.

ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;

-- Allow anonymous access (since we are using a publishable key without user auth)
CREATE POLICY "Enable access for all users" ON public.bookings
    FOR ALL
    USING (true)
    WITH CHECK (true);
