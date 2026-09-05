// ==============================================================================
// Jaya Jaya Varahi Shop - Supabase Client & Data Service
// Exclusively stores EVERYTHING except Products:
// - Customer Accounts & Authentication ('users')
// - Customer Orders & Checkout ('orders')
// - Day Discounts & Announcement Offers ('store_settings')
// - Store Categories ('categories')
// - Customer Wishlists ('wishlists')
// (Note: Only Products are stored in Firebase Cloud Firestore)
// ==============================================================================

const SUPABASE_CONFIG = {
  url: "https://gftsfdlchvjylpitjbps.supabase.co",
  key: "sb_publishable_aJ2OouHZ-cfj9WmmUVNOPA_IPS6GF51"
};

function initSupabaseClient() {
  if (typeof supabase !== 'undefined' && supabase.createClient) {
    window.supabaseClient = supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.key);
    console.log('✅ Supabase Client initialized for all Non-Product Store Data!');
    return window.supabaseClient;
  }
  return null;
}

initSupabaseClient();
window.addEventListener('DOMContentLoaded', initSupabaseClient);

// ── COMPREHENSIVE SUPABASE DATA SERVICE ──
const supabaseDataService = {
  getClient() {
    return window.supabaseClient || (typeof supabase !== 'undefined' && supabase.createClient ? initSupabaseClient() : null);
  },

  // 1. Customer User Sync
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
      console.warn('Supabase syncUser note:', err);
      return null;
    }
  },

  // 2. Customer Order Sync
  async syncOrder(orderPayload) {
    const client = this.getClient();
    if (!client || !orderPayload) return null;
    try {
      const { data, error } = await client
        .from('orders')
        .insert([orderPayload])
        .select();
      if (!error) {
        console.log(`✅ [Supabase] Order ${orderPayload.order_number} saved to 'orders' table.`);
      }
      return { data, error };
    } catch (err) {
      console.warn('Supabase syncOrder note:', err);
      return null;
    }
  },

  // 3. Store Settings & Discounts Sync
  async getStoreSettings() {
    const client = this.getClient();
    if (!client) return null;
    try {
      const { data, error } = await client
        .from('store_settings')
        .select('*')
        .eq('key', 'discount_offers')
        .single();
      if (!error && data && data.value) {
        return data.value;
      }
      return null;
    } catch (err) {
      return null;
    }
  },

  async saveStoreSettings(settings) {
    const client = this.getClient();
    if (!client || !settings) return false;
    try {
      const { error } = await client
        .from('store_settings')
        .upsert([{
          key: 'discount_offers',
          value: settings,
          updated_at: new Date().toISOString()
        }], { onConflict: 'key' });
      if (!error) {
        console.log('✅ [Supabase] Day discounts & offer banner saved to Supabase!');
        return true;
      }
      return false;
    } catch (err) {
      console.warn('Supabase saveStoreSettings note:', err);
      return false;
    }
  },

  // 4. Categories Sync
  async getCategories() {
    const client = this.getClient();
    if (!client) return null;
    try {
      const { data, error } = await client
        .from('categories')
        .select('*')
        .order('builtin', { ascending: false });
      if (!error && data && data.length > 0) {
        return data;
      }
      return null;
    } catch (err) {
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
      await client.from('categories').upsert(records, { onConflict: 'id' });
      console.log('✅ [Supabase] Categories synced to Supabase table!');
      return true;
    } catch (err) {
      return false;
    }
  },

  // 5. Customer Wishlist Sync
  async syncWishlist(userEmail, items) {
    const client = this.getClient();
    if (!client || !userEmail) return false;
    try {
      const cleanEmail = userEmail.toLowerCase().trim();
      // Store in users profile or wishlist table
      const records = items.map(prodId => ({
        user_email: cleanEmail,
        product_id: String(prodId)
      }));
      if (records.length > 0) {
        await client.from('wishlists').upsert(records, { onConflict: 'user_email,product_id' });
      }
      return true;
    } catch (err) {
      return false;
    }
  }
};

window.supabaseDataService = supabaseDataService;
