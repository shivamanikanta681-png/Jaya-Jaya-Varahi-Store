// ES Module Supabase Connection Client (Node.js)
// ----------------------------------------------
import 'dotenv/config';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

export const supabase = createClient(supabaseUrl, supabaseKey);

// Self-test when run via: node supabase.mjs
if (import.meta.url === `file://${process.argv[1].replace(/\\/g, '/')}`) {
  console.log('>> Supabase ES Module Client ready for:', supabaseUrl);
}
