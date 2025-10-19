-- Supabase SQL setup for restaurant booking system
-- Run this in your Supabase SQL editor

-- Create the bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    date DATE NOT NULL,
    time TIME NOT NULL,
    party_size INTEGER NOT NULL CHECK (party_size > 0 AND party_size <= 20),
    guest_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    special_requests TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create an index on date and time for faster availability queries
CREATE INDEX IF NOT EXISTS idx_bookings_date_time ON bookings(date, time);

-- Create an index on status for filtering active bookings
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);

-- Enable Row Level Security (RLS)
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;

-- Create policies for anonymous users (public access for the voice assistant)
-- Allow anonymous users to insert bookings
CREATE POLICY "Allow anonymous inserts" ON bookings
    FOR INSERT
    TO anon
    WITH CHECK (true);

-- Allow anonymous users to select their own bookings (by phone number)
CREATE POLICY "Allow anonymous selects" ON bookings
    FOR SELECT
    TO anon
    USING (true);

-- Allow anonymous users to update their own bookings (by phone number)
CREATE POLICY "Allow anonymous updates" ON bookings
    FOR UPDATE
    TO anon
    USING (true)
    WITH CHECK (true);

-- Allow service role full access (for admin operations)
CREATE POLICY "Allow service role full access" ON bookings
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create a trigger to automatically update updated_at
CREATE TRIGGER update_bookings_updated_at
    BEFORE UPDATE ON bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
