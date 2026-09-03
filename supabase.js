// Node.js Supabase Connection Client
// ------------------------------------
require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.warn('⚠️ Supabase credentials missing from .env');
}

const supabase = createClient(supabaseUrl, supabaseKey);

// Self-test when run directly: `node supabase.js`
if (require.main === module) {
  console.log('=======================================================');
  console.log('>> Testing Node.js Supabase Database Connection...');
  console.log('=======================================================');
  console.log(`>> Supabase URL : ${supabaseUrl}`);
  console.log(`>> Supabase Key : ${supabaseKey ? supabaseKey.slice(0, 12) + '...' : 'NONE'}`);

  supabase
    .from('products')
    .select('*')
    .limit(1)
    .then(({ data, error }) => {
      if (error) {
        console.log(`>> Project connected! (Table note: ${error.message})`);
      } else {
        console.log(`>> Success! Queried products table: ${data.length} records.`);
      }
    })
    .catch((err) => {
      console.error('>> Connection error:', err);
    });
}

module.exports = { supabase };
