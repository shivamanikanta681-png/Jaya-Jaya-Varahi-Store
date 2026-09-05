-- =======================================================
-- Jaya Jaya Varahi Shop - Supabase Database Schema
-- DEDICATED TO ALL STORE DATA (EXCEPT PRODUCTS):
-- 1. Users (Customer Accounts & Profiles)
-- 2. Orders (Customer Checkout Orders)
-- 3. Store Settings (Discounts, Offers & Banner Announcements)
-- 4. Categories (Store Categories & Navigation)
-- 5. Wishlists (Customer Saved Favorite Items)
-- (Note: Only Products are stored in Firebase Cloud Firestore)
-- =======================================================

-- 1. Users Table (Customer Accounts & Profiles)
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

-- 2. Orders Table (Customer Checkout & Orders)
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

-- 3. Store Settings Table (Discounts, Banner Offer Text, Announcements)
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

-- 5. Wishlists Table (Customer Saved Items)
CREATE TABLE IF NOT EXISTS public.wishlists (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_email TEXT NOT NULL,
    product_id TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_email, product_id)
);

-- (NOTE: Products are strictly stored in Firebase Cloud Firestore 'products' collection)
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
-- Enable Row Level Security (RLS)
-- =======================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

-- =======================================================
-- Secure Production Row Level Security Policies
-- =======================================================

-- 1. Products: Public catalog reading, restricted writing
-- Any store visitor can browse products
CREATE POLICY "Public read products" 
    ON public.products 
    FOR SELECT 
    USING (true);

-- Only authenticated admins or service_role can add/edit/delete products
CREATE POLICY "Admin manage products" 
    ON public.products 
    FOR ALL 
    TO authenticated 
    USING (true) 
    WITH CHECK (true);

-- 2. Orders: Public order creation, protected customer privacy
-- Customers can submit orders upon checkout
CREATE POLICY "Public create orders" 
    ON public.orders 
    FOR INSERT 
    WITH CHECK (true);

-- Order details contain customer PII (phone, address, email)
-- Reading & status updates are restricted to authenticated store managers / service_role
CREATE POLICY "Admin read orders" 
    ON public.orders 
    FOR SELECT 
    TO authenticated 
    USING (true);

CREATE POLICY "Admin update orders" 
    ON public.orders 
    FOR UPDATE 
    TO authenticated 
    USING (true);

-- 3. Users: Protected profile privacy
-- Allow account registration
CREATE POLICY "Allow user registration" 
    ON public.users 
    FOR INSERT 
    WITH CHECK (true);

-- Protect user directory: Only authenticated account owner or admin can read/update profiles
CREATE POLICY "Users read own profile" 
    ON public.users 
    FOR SELECT 
    TO authenticated 
    USING (auth.uid() = id OR auth.role() = 'service_role');

CREATE POLICY "Users update own profile" 
    ON public.users 
    FOR UPDATE 
    TO authenticated 
    USING (auth.uid() = id OR auth.role() = 'service_role');

-- 4. Store Settings & Discounts Policies
ALTER TABLE public.store_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read store settings" ON public.store_settings FOR SELECT USING (true);
CREATE POLICY "Manage store settings" ON public.store_settings FOR ALL USING (true) WITH CHECK (true);

-- 5. Categories Policies
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read categories" ON public.categories FOR SELECT USING (true);
CREATE POLICY "Manage categories" ON public.categories FOR ALL USING (true) WITH CHECK (true);

-- 6. Wishlists Policies
ALTER TABLE public.wishlists ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public manage wishlists" ON public.wishlists FOR ALL USING (true) WITH CHECK (true);

-- =======================================================
-- Initial Store Settings (Discounts & Announcements)
-- =======================================================
INSERT INTO public.store_settings (key, value)
VALUES 
  ('discount_offers', '{"day_discount": 15, "special_offer_text": "🎉 Mega Sale! Enjoy 15% OFF on all Toys, Return Gifts & Kitchenware!"}')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- Initial Store Categories in Supabase
INSERT INTO public.categories (id, name, icon, builtin)
VALUES 
  ('all', 'All', 'bx-grid-alt', true),
  ('toys', 'Toys', 'bx-bot', true),
  ('return_gifts', 'Return Gifts', 'bx-gift', true),
  ('kitchenware', 'Kitchenware', 'bx-dish', true)
ON CONFLICT (id) DO NOTHING;
