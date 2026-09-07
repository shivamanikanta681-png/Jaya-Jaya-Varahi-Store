// ==============================================================================
// Jaya Jaya Varahi Shop - Supabase Client
// Handles Customer Auth, Orders, Categories, Settings & Wishlists
// ==============================================================================

const SUPABASE_URL = "https://gftsfdlchvjylpitjbps.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_aJ2OouHZ-cfj9WmmUVNOPA_IPS6GF51";

let supabaseClient = null;

function initSupabaseClient() {
  try {
    const supabaseLib = (typeof window !== 'undefined' && window.supabase) || (typeof supabase !== 'undefined' ? supabase : null);
    if (supabaseLib && typeof supabaseLib.createClient === 'function') {
      supabaseClient = supabaseLib.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
      if (typeof window !== 'undefined') {
        window.supabaseClient = supabaseClient;
      }
      console.log("⚡ [Supabase] Client initialized successfully!");
      return supabaseClient;
    }
  } catch (err) {
    console.warn("Supabase init note:", err.message);
  }
  return null;
}

// Immediate and event-driven initialization
initSupabaseClient();
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    if (!window.supabaseClient) initSupabaseClient();
  });
}

const supabaseDataService = {
  getClient() {
    if (supabaseClient) return supabaseClient;
    if (typeof window !== 'undefined' && window.supabaseClient) return window.supabaseClient;
    return initSupabaseClient();
  },

  // 1. Store Settings (Discounts & Announcements)
  async getStoreSettings() {
    const client = this.getClient();
    if (!client) return null;
    try {
      // Try key-value row first
      const { data: kvData, error: kvError } = await client
        .from('store_settings')
        .select('*')
        .eq('key', 'discount_offers')
        .maybeSingle();

      if (!kvError && kvData && kvData.value) {
        return kvData.value;
      }

      // Try single row with id
      const { data, error } = await client
        .from('store_settings')
        .select('*')
        .limit(1)
        .maybeSingle();

      if (error && error.code !== 'PGRST116') throw error;
      return data;
    } catch (e) {
      console.warn("Supabase getStoreSettings note:", e.message);
      return null;
    }
  },

  async saveStoreSettings(settings) {
    const client = this.getClient();
    if (!client || !settings) return false;
    try {
      // Upsert key-value format
      await client
        .from('store_settings')
        .upsert([{
          key: 'discount_offers',
          value: settings,
          updated_at: new Date().toISOString()
        }], { onConflict: 'key' });

      console.log("✅ [Supabase] Store settings synced!");
      return true;
    } catch (e) {
      console.warn("Supabase saveStoreSettings note:", e.message);
      return false;
    }
  },

  // 2. Categories Sync
  async getCategories() {
    const client = this.getClient();
    if (!client) return null;
    try {
      const { data, error } = await client
        .from('categories')
        .select('*')
        .order('builtin', { ascending: false });
      if (error) throw error;
      return data;
    } catch (e) {
      return null;
    }
  },

  async saveCategories(categories) {
    const client = this.getClient();
    if (!client || !categories) return false;
    try {
      const records = categories.map(c => ({
        id: c.id,
        name: c.name,
        icon: c.icon || 'bx-grid-alt',
        builtin: Boolean(c.builtin)
      }));
      const { error } = await client
        .from('categories')
        .upsert(records, { onConflict: 'id' });
      if (error) throw error;
      console.log("✅ [Supabase] Categories synced!");
      return true;
    } catch (e) {
      return false;
    }
  },

  // 3. Customer Wishlist Sync
  async syncWishlist(email, wishlistItems) {
    const client = this.getClient();
    if (!client || !email) return false;
    try {
      const cleanEmail = String(email).toLowerCase().trim();
      // Sync into users table profile
      await client
        .from('users')
        .upsert({ email: cleanEmail, wishlist: wishlistItems, updated_at: new Date().toISOString() }, { onConflict: 'email' });

      // Also sync into dedicated wishlists table if available
      if (Array.isArray(wishlistItems) && wishlistItems.length > 0) {
        const records = wishlistItems.map(prodId => ({
          user_email: cleanEmail,
          product_id: String(prodId)
        }));
        await client.from('wishlists').upsert(records, { onConflict: 'user_email,product_id' });
      }
      return true;
    } catch (e) {
      return false;
    }
  },

  // 4. Customer User Sync
  async syncUser(user) {
    const client = this.getClient();
    if (!client || !user || !user.email) return null;
    try {
      const { data, error } = await client
        .from('users')
        .upsert([{
          email: user.email.toLowerCase().trim(),
          name: user.name || '',
          platform: user.platform || 'Website Account',
          phone: user.phone || null,
          last_login: new Date().toISOString()
        }], { onConflict: 'email' })
        .select();
      if (!error) {
        console.log(`✅ [Supabase] Customer ${user.email} synced to 'users' table.`);
      }
      return { data, error };
    } catch (err) {
      return null;
    }
  },

  // 5. Customer Order Sync
  async syncOrder(orderPayload) {
    const client = this.getClient();
    if (!client || !orderPayload) return null;
    try {
      const { data, error } = await client
        .from('orders')
        .insert([orderPayload])
        .select();
      if (!error) {
        console.log(`✅ [Supabase] Order saved to 'orders' table.`);
      }
      return { data, error };
    } catch (err) {
      return null;
    }
  },

  // Alias for compatibility
  async insertOrder(orderPayload) {
    return this.syncOrder(orderPayload);
  }
};

if (typeof window !== 'undefined') {
  window.supabaseDataService = supabaseDataService;
  window.supabaseClient = supabaseClient;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { supabaseClient, supabaseDataService };
}
