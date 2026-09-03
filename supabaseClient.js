// Supabase Client Utility for Frontend (Browser)
// ------------------------------------------------
// Provides a global window.supabaseClient instance for direct database/auth queries.

const SUPABASE_CONFIG = {
  url: "https://gftsfdlchvjylpitjbps.supabase.co",
  key: "sb_publishable_aJ2OouHZ-cfj9WmmUVNOPA_IPS6GF51"
};

// Initialize if Supabase JS CDN is available
if (typeof supabase !== 'undefined' && supabase.createClient) {
  window.supabaseClient = supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.key);
  console.log('✅ Supabase Frontend Client initialized successfully!');
} else {
  // If CDN script loads later, attach ready callback
  window.addEventListener('DOMContentLoaded', () => {
    if (typeof supabase !== 'undefined' && supabase.createClient) {
      window.supabaseClient = supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.key);
      console.log('✅ Supabase Frontend Client initialized successfully!');
    }
  });
}
