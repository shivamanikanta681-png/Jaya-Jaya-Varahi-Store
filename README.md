# 🛍️ Jaya Jaya Varahi Shop & Gifts

A modern e-commerce storefront for **Jaya Jaya Varahi Gifts & Shop** (Boduppal, Hyderabad), featuring real-time catalog filtering, multi-language AI chatbot assistance, Day-Theme discounts, Supabase database integration, and a 100% Free Email OTP authentication system.

---

## ✨ Features

- **Storefront & Catalog**: Handcrafted Wooden Toys, STEM Learning Robots, Divine Return Gifts, and Kitchenware.
- **Dynamic Day Themes**: Automatic daily styling, discount engine (15% OFF today), and sound effects powered by Web Audio API.
- **100% Free Email OTP System**: Forgot password and passwordless login with 6-digit verification codes and live countdown timers.
- **Database Integration (Supabase)**: Synchronizes users, orders, and authentication records to a live PostgreSQL database via official Supabase client libraries (Python & JavaScript).
- **Multilingual AI Shopping Assistant**: Interactive chatbot with language selection (English, Telugu, Hindi, Tamil) and smart product recommendation cards.
- **Owner Administration Console**: Password-protected dashboard (`varahi123`) to manage inventory, edit product prices, and review customer orders.
- **Customer Checkout & WhatsApp Ordering**: Location-based delivery address validation (Hyderabad vs outside Hyderabad) and instant WhatsApp order generation (`+91 75693 04410`).

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** or **Node.js 18+**

### 2. Setup Credentials
Copy `.env.example` to `.env` and fill in your Supabase and optional Gmail SMTP credentials:
```bash
cp .env.example .env
```

```env
SUPABASE_URL="https://your-project-ref.supabase.co"
SUPABASE_KEY="your-supabase-anon-key"
PORT=8000
```

### 3. Run the Local Server
```bash
python server.py
```
Open your browser at [http://localhost:8000](http://localhost:8000).

---

## 🗄️ Database Setup (Supabase)
To create the necessary tables in your Supabase project:
1. Open your **Supabase Dashboard** -> **SQL Editor**.
2. Run the SQL statements provided in [`supabase_schema.sql`](./supabase_schema.sql).

---

## 📂 Project Structure

```
├── images/                 # Store product and branding assets
├── index.html              # Main storefront interface
├── SignUp_LogIn_Form.css   # Full responsive styling & theme system
├── SignUp_LogIn_Form.js    # Storefront logic, cart, sound engine & UI
├── server.py               # Python backend (HTTP server, Email OTP & API)
├── supabase_client.py      # Python Supabase connection manager
├── supabase.js             # Node.js CommonJS Supabase client
├── supabase.mjs            # Node.js ES Module Supabase client
├── supabaseClient.js       # Frontend browser Supabase client
├── supabase_schema.sql     # Database tables and RLS policies
├── .env.example            # Environment variables template
└── .gitignore              # Ignored dependencies & private files
```

---

## 📍 Store Location & Contact
- **Address**: Jaya Jaya Varahi Gifts, Boduppal, Hyderabad, Telangana
- **WhatsApp**: [+91 75693 04410](https://wa.me/917569304410)
