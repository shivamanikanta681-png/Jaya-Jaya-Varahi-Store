-- =======================================================
-- Jaya Jaya Varahi Shop - Supabase Database Schema
-- Run this in your Supabase SQL Editor (Dashboard -> SQL Editor)
-- =======================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS public.users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    platform TEXT DEFAULT 'Website Account',
    phone TEXT,
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 2. Orders Table
CREATE TABLE IF NOT EXISTS public.orders (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    order_number TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    customer_email TEXT,
    delivery_location TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    pincode TEXT,
    items JSONB NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    discount_amount NUMERIC(10, 2) DEFAULT 0,
    total_payable NUMERIC(10, 2) NOT NULL,
    status TEXT DEFAULT 'Pending' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Products Table
CREATE TABLE IF NOT EXISTS public.products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    image TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS) with open read/write for public anon key
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

-- Public read & write policies for website operation
CREATE POLICY "Allow public read users" ON public.users FOR SELECT USING (true);
CREATE POLICY "Allow public insert/update users" ON public.users FOR ALL USING (true);

CREATE POLICY "Allow public read orders" ON public.orders FOR SELECT USING (true);
CREATE POLICY "Allow public insert orders" ON public.orders FOR ALL USING (true);

CREATE POLICY "Allow public read products" ON public.products FOR SELECT USING (true);
CREATE POLICY "Allow public insert products" ON public.products FOR ALL USING (true);

-- Insert initial sample products
INSERT INTO public.products (id, name, category, price, image, description)
VALUES 
  ('p1', 'Wooden Racing Toy Car', 'toys', 450, 'images/toy_car.jpg', 'Handcrafted non-toxic wooden racing car with smooth rolling wheels for kids.'),
  ('p2', 'Interactive Educational Robot', 'toys', 899, 'https://images.unsplash.com/photo-1596461404969-9ae70f2830c1?auto=format&fit=crop&w=600&q=80', 'Smart STEM learning robot with lights, music, and interactive sound modes.'),
  ('p3', 'Plush Soft Teddy Bear', 'toys', 350, 'https://images.unsplash.com/photo-1559454403-b8fb88521f11?auto=format&fit=crop&w=600&q=80', 'Ultra-soft premium plush teddy bear suitable for toddlers and gifting.')
ON CONFLICT (id) DO NOTHING;
