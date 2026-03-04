-- Run this in Supabase SQL Editor to update the barbers table

ALTER TABLE barbers 
ADD COLUMN IF NOT EXISTS specialty text DEFAULT 'Мастер',
ADD COLUMN IF NOT EXISTS experience text DEFAULT '1 год',
ADD COLUMN IF NOT EXISTS photo_url text;

-- Update existing records with default values if needed
UPDATE barbers SET specialty = 'Классика · Фейд', experience = '7 лет' WHERE name = 'Алексей';
UPDATE barbers SET specialty = 'Андеркат · Помп', experience = '5 лет' WHERE name = 'Марат';
UPDATE barbers SET specialty = 'Борода · Скин', experience = '4 года' WHERE name = 'Дмитрий';
