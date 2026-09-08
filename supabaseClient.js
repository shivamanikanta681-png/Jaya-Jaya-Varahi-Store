// ==============================================================================
// Jaya Jaya Varahi Shop - Supabase Client
// Handles Customer Auth, Products, Orders, Categories, Settings & Wishlists
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
      return supabaseClient;
    }
  } catch (err) {
    console.warn("[Supabase] Initialization note:", err.message);
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
      const { data, error } = await client
        .from('store_settings')
        .select('*')
        .eq('key', 'discount_offers')
        .maybeSingle();

      if (error && error.code !== 'PGRST116') {
        console.warn("[Supabase] getStoreSettings query error:", error.message);
        return null;
      }
      if (data && data.value) return data.value;
      return null;
    } catch (e) {
      console.warn("[Supabase] getStoreSettings error:", e.message);
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

      if (error) {
        console.warn("[Supabase] saveStoreSettings note:", error.message);
        return false;
      }
      return true;
    } catch (e) {
      console.warn("[Supabase] saveStoreSettings error:", e.message);
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
      if (error) {
        console.warn("[Supabase] getCategories note:", error.message);
        return null;
      }
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
      if (error) {
        console.warn("[Supabase] saveCategories note:", error.message);
        return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  },

  // 3. Products Catalog (Unified Source of Truth)
  async getProducts() {
    const client = this.getClient();
    if (!client) return null;
    try {
      const { data, error } = await client
        .from('products')
        .select('*')
        .order('created_at', { ascending: true });
      if (error) {
        console.warn("[Supabase] getProducts query note:", error.message);
        return null;
      }
      if (data && data.length > 0) return data;
      return null;
    } catch (e) {
      console.warn("[Supabase] getProducts exception:", e.message);
      return null;
    }
  },

  async saveProduct(product) {
    const client = this.getClient();
    if (!client || !product) return false;
    try {
      const { error } = await client
        .from('products')
        .upsert([product], { onConflict: 'id' });
      if (error) {
        console.warn("[Supabase] saveProduct note:", error.message);
        return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  },

  async deleteProduct(productId) {
    const client = this.getClient();
    if (!client || !productId) return false;
    try {
      const { error } = await client
        .from('products')
        .delete()
        .eq('id', productId);
      if (error) {
        console.warn("[Supabase] deleteProduct note:", error.message);
        return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  },

  // 4. Customer Wishlist Sync (Dedicated wishlists table only)
  async getWishlist(email) {
    const client = this.getClient();
    if (!client || !email) return [];
    try {
      const cleanEmail = String(email).toLowerCase().trim();
      const { data, error } = await client
        .from('wishlists')
        .select('product_id')
        .eq('user_email', cleanEmail);
      if (error) return [];
      return (data || []).map(r => r.product_id);
    } catch (e) {
      return [];
    }
  },

  async syncWishlist(email, wishlistItems) {
    const client = this.getClient();
    if (!client || !email) return false;
    try {
      const cleanEmail = String(email).toLowerCase().trim();
      const newItems = Array.isArray(wishlistItems) ? wishlistItems.map(String) : [];

      // Fetch existing items in wishlists table
      const { data: existing, error: fetchErr } = await client
        .from('wishlists')
        .select('product_id')
        .eq('user_email', cleanEmail);

      if (!fetchErr && existing) {
        const existingIds = existing.map(r => r.product_id);
        const toDelete = existingIds.filter(id => !newItems.includes(id));
        if (toDelete.length > 0) {
          await client
            .from('wishlists')
            .delete()
            .eq('user_email', cleanEmail)
            .in('product_id', toDelete);
        }
      }

      // Upsert current items
      if (newItems.length > 0) {
        const records = newItems.map(prodId => ({
          user_email: cleanEmail,
          product_id: String(prodId)
        }));
        const { error: upsertErr } = await client
          .from('wishlists')
          .upsert(records, { onConflict: 'user_email,product_id' });
        if (upsertErr) {
          console.warn("[Supabase] Wishlist upsert note:", upsertErr.message);
        }
      }
      return true;
    } catch (e) {
      console.warn("[Supabase] syncWishlist exception:", e.message);
      return false;
    }
  },

  // 5. Customer Profile Sync (Supports both Phone and Email Accounts)
  async syncUser(user) {
    const client = this.getClient();
    if (!client || !user) return null;
    const phone = user.phone_normalized || user.phone || null;
    const email = user.email ? String(user.email).toLowerCase().trim() : null;
    const name = user.name || '';
    const platform = user.platform || 'Firebase Phone Account';
    const nowIso = new Date().toISOString();

    if (!phone && !email) return null;

    try {
      // 1. Check existing customer by normalized phone or email to prevent duplicates
      let existing = null;
      if (phone) {
        const { data: phoneMatch } = await client
          .from('users')
          .select('*')
          .eq('phone_normalized', phone)
          .maybeSingle();
        if (phoneMatch) existing = phoneMatch;
      }

      if (!existing && email) {
        const { data: emailMatch } = await client
          .from('users')
          .select('*')
          .eq('email', email)
          .maybeSingle();
        if (emailMatch) existing = emailMatch;
      }

      if (existing) {
        const updatePayload = {
          last_login: nowIso,
          platform: platform
        };
        if (name && !existing.name) updatePayload.name = name;
        if (phone && !existing.phone_normalized) {
          updatePayload.phone_normalized = phone;
          updatePayload.phone = phone;
        }
        if (email && !existing.email) updatePayload.email = email;

        const { data: updated, error: updateErr } = await client
          .from('users')
          .update(updatePayload)
          .eq('id', existing.id)
          .select()
          .maybeSingle();

        if (updateErr) {
          console.warn("[Supabase] syncUser update note:", updateErr.message);
        }
        return { data: updated || { ...existing, ...updatePayload }, error: updateErr };
      }

      // 2. Insert new customer record
      const insertPayload = {
        name: name || (phone ? phone.slice(-4) : (email ? email.split('@')[0] : 'Customer')),
        platform: platform,
        last_login: nowIso,
        created_at: nowIso
      };
      if (phone) {
        insertPayload.phone_normalized = phone;
        insertPayload.phone = phone;
      }
      if (email) {
        insertPayload.email = email;
      }

      const { data: inserted, error: insertErr } = await client
        .from('users')
        .insert([insertPayload])
        .select()
        .maybeSingle();

      if (insertErr) {
        console.warn("[Supabase] syncUser insert note:", insertErr.message);
      }
      return { data: inserted || insertPayload, error: insertErr };
    } catch (err) {
      console.warn("[Supabase] syncUser exception:", err.message);
      return null;
    }
  }
};

if (typeof window !== 'undefined') {
  window.supabaseDataService = supabaseDataService;
  window.initSupabaseClient = initSupabaseClient;
  window.supabaseClient = supabaseClient;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { supabaseClient, supabaseDataService };
}
