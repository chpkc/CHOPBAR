CREATE TABLE IF NOT EXISTS barbershops ( 
   id SERIAL PRIMARY KEY, 
   name VARCHAR(100), 
   city VARCHAR(100), 
   phone VARCHAR(20), 
   instagram VARCHAR(200), 
   slug VARCHAR(50) UNIQUE, 
   owner_telegram_id BIGINT, 
   created_at TIMESTAMP DEFAULT NOW() 
); 

CREATE TABLE IF NOT EXISTS invites ( 
   id SERIAL PRIMARY KEY, 
   code VARCHAR(20) UNIQUE, 
   used BOOLEAN DEFAULT FALSE, 
   used_by BIGINT, 
   created_at TIMESTAMP DEFAULT NOW() 
);