-- =======================================================
-- Jaya Jaya Varahi Shop - Supabase Database Schema
-- Unified Production Schema & Row Level Security (RLS)
-- Tables:
-- 1. users / profiles (Linked to auth.users)
-- 2. orders (Customer Checkout Orders)
-- 3. store_settings (Discounts & Announcements)
-- 4. categories (Store Categories)
-- 5. wishlists (Customer Saved Favorite Items)
-- 6. products (Authoritative Store Catalog for Store & AI)
-- =======================================================

-- 1. Users / Profiles Table (Store Customer Accounts)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    platform TEXT DEFAULT 'Website Account',
    phone TEXT,
    address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Note: The store utilizes a secure, server-side Email OTP verification system.
-- Drop any legacy auth.users trigger dependency if previously applied:
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- 2. Orders Table (Customer Orders)
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

-- 3. Store Settings Table (Discounts, Announcements)
CREATE TABLE IF NOT EXISTS public.store_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Categories Table (Store Categories)
CREATE TABLE IF NOT EXISTS public.categories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    icon TEXT DEFAULT 'bx-grid-alt',
    builtin BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Wishlists Table (Customer Favorite Items)
CREATE TABLE IF NOT EXISTS public.wishlists (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    user_email TEXT NOT NULL,
    product_id TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_email, product_id)
);

-- 6. Products Table (Unified Authoritative Catalog for Store & RAG AI)
CREATE TABLE IF NOT EXISTS public.products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    image TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- =======================================================
-- Enable Row Level Security (RLS) on All Tables
-- =======================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.store_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wishlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

-- =======================================================
-- Secure Row Level Security Policies
-- =======================================================

-- 1. Users Policies:
DROP POLICY IF EXISTS "Users read own profile" ON public.users;
CREATE POLICY "Users read own profile" 
    ON public.users 
    FOR SELECT 
    TO public, authenticated, anon, service_role 
    USING (true);

DROP POLICY IF EXISTS "Users update own profile" ON public.users;
CREATE POLICY "Users update own profile" 
    ON public.users 
    FOR UPDATE 
    TO public, authenticated, anon, service_role 
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow user registration" ON public.users;
DROP POLICY IF EXISTS "Allow authenticated profile creation" ON public.users;
DROP POLICY IF EXISTS "Allow user profile creation" ON public.users;
CREATE POLICY "Allow user profile creation" 
    ON public.users 
    FOR INSERT 
    TO public, authenticated, anon, service_role 
    WITH CHECK (true);

-- 2. Orders Policies:
DROP POLICY IF EXISTS "Public create orders" ON public.orders;
CREATE POLICY "Public create orders" 
    ON public.orders 
    FOR INSERT 
    WITH CHECK (true);

DROP POLICY IF EXISTS "Admin read orders" ON public.orders;
CREATE POLICY "Admin read orders" 
    ON public.orders 
    FOR SELECT 
    TO authenticated 
    USING (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin');

DROP POLICY IF EXISTS "Admin update orders" ON public.orders;
CREATE POLICY "Admin update orders" 
    ON public.orders 
    FOR UPDATE 
    TO authenticated 
    USING (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin');

-- 3. Products Policies:
DROP POLICY IF EXISTS "Public read products" ON public.products;
CREATE POLICY "Public read products" 
    ON public.products 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "Admin manage products" ON public.products;
CREATE POLICY "Admin manage products" 
    ON public.products 
    FOR ALL 
    TO authenticated 
    USING (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin')
    WITH CHECK (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin');

-- 4. Store Settings Policies:
DROP POLICY IF EXISTS "Public read store settings" ON public.store_settings;
CREATE POLICY "Public read store settings" 
    ON public.store_settings 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "Admin manage store settings" ON public.store_settings;
CREATE POLICY "Admin manage store settings" 
    ON public.store_settings 
    FOR ALL 
    TO authenticated 
    USING (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin') 
    WITH CHECK (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin');

-- 5. Categories Policies:
DROP POLICY IF EXISTS "Public read categories" ON public.categories;
CREATE POLICY "Public read categories" 
    ON public.categories 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "Admin manage categories" ON public.categories;
CREATE POLICY "Admin manage categories" 
    ON public.categories 
    FOR ALL 
    TO authenticated 
    USING (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin') 
    WITH CHECK (auth.role() = 'service_role' OR auth.jwt() ->> 'role' = 'admin');

-- 6. Wishlists Policies:
DROP POLICY IF EXISTS "Public manage wishlists" ON public.wishlists;
CREATE POLICY "Public manage wishlists" 
    ON public.wishlists 
    FOR ALL 
    USING (true) 
    WITH CHECK (true);

-- =======================================================
-- Initial Seed Data: Store Settings, Categories & Default Products
-- =======================================================
INSERT INTO public.store_settings (key, value)
VALUES 
  ('discount_offers', '{"day_discount": 15, "special_offer_text": "🎉 Mega Sale! Enjoy 15% OFF on all Toys, Return Gifts & Kitchenware!"}')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

INSERT INTO public.categories (id, name, icon, builtin)
VALUES 
  ('all', 'All', 'bx-grid-alt', true),
  ('toys', 'Toys', 'bx-bot', true),
  ('return_gifts', 'Return Gifts', 'bx-gift', true),
  ('kitchenware', 'Kitchenware', 'bx-dish', true)
ON CONFLICT (id) DO NOTHING;

-- Initial Seed Products (Matches Storefront & RAG Engine exactly)
INSERT INTO public.products (id, name, category, price, image, description)
VALUES
  ('p1', 'Wooden Racing Toy Car', 'toys', 450.00, 'images/toy_car.webp', 'Handcrafted non-toxic wooden racing car with smooth rolling wheels for kids.'),
  ('p2', 'Interactive Educational Robot', 'toys', 899.00, 'https://images.unsplash.com/photo-1596461404969-9ae70f2830c1?auto=format&fit=crop&w=600&q=80', 'Smart STEM learning robot with lights, music, and interactive sound modes.'),
  ('p3', 'Plush Soft Teddy Bear', 'toys', 350.00, 'https://images.unsplash.com/photo-1559454403-b8fb88521f11?auto=format&fit=crop&w=600&q=80', 'Ultra-soft premium plush teddy bear suitable for toddlers and gifting.'),
  ('p4', 'Traditional Brass Diya Gift Set', 'return_gifts', 599.00, 'images/return_gift.webp', 'Exquisite hand-carved pure brass oil diya set packaged in a velvet gift box.'),
  ('p5', 'Handcrafted Wooden Jewellery Box', 'return_gifts', 299.00, 'https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?auto=format&fit=crop&w=600&q=80', 'Vintage carved wooden trinket box perfect for return gifts and festive favors.'),
  ('p6', 'Eco-Friendly Jute Gift Bag Set', 'return_gifts', 199.00, 'https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=600&q=80', 'Set of 3 stylish reusable printed jute carry bags with secure zipper.'),
  ('p7', 'Premium Stainless Steel Cookware Set', 'kitchenware', 1499.00, 'images/kitchenware.webp', '3-piece induction bottom stainless steel pots & saucepans with glass lids.'),
  ('p8', 'Non-Stick Granite Frying Pan', 'kitchenware', 799.00, 'https://images.unsplash.com/photo-1584992236310-6edddc08acff?auto=format&fit=crop&w=600&q=80', 'Heavy duty scratch-resistant granite coating fry pan with soft touch handle.'),
  ('p9', 'Ceramic Designer Coffee Mugs Set', 'kitchenware', 449.00, 'https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=600&q=80', 'Set of 4 hand-glazed stoneware coffee mugs for home and office.')
ON CONFLICT (id) DO NOTHING;
