// ==============================================================================
// Jaya Jaya Varahi Shop - Firebase Firestore Products Client
// Exclusively responsible for Store Products Catalog, Categories & Inventory
// Customer Data (Users & Orders) is strictly managed by Supabase (supabaseClient.js)
// ==============================================================================

const firebaseConfig = {
  apiKey: "AIzaSyDIUrfr7J1WWtppp3EsXviBkGiI3y7Vx54",
  authDomain: "jaya-jaya-varahi-shop.firebaseapp.com",
  projectId: "jaya-jaya-varahi-shop",
  storageBucket: "jaya-jaya-varahi-shop.firebasestorage.app",
  messagingSenderId: "134693419982",
  appId: "1:134693419982:web:087870ddcf5d8f8bf9c99f",
  measurementId: "G-8Q1DWFSJLW"
};

// Check if valid Firebase configuration has been inserted
function isFirebaseConfigured() {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);
}

let app = null;
let db = null;
let analytics = null;

try {
  if (typeof firebase !== 'undefined' && firebase.initializeApp) {
    if (!firebase.apps.length) {
      app = firebase.initializeApp(firebaseConfig);
    } else {
      app = firebase.app();
    }
    window.app = app;
    window.firebaseApp = app;

    db = firebase.firestore();
    window.db = db;
    window.firebaseDb = db;

    if (typeof firebase.analytics === 'function') {
      try {
        analytics = firebase.analytics();
        window.analytics = analytics;
      } catch (analyticsErr) {
        console.warn('Analytics note:', analyticsErr.message);
      }
    }

    console.log('🔥 Live Firebase App & Firestore initialized for Project "jaya-jaya-varahi-shop"!');
  }
} catch (err) {
  console.warn('⚠️ Firebase initialization note:', err.message);
}

// ── EXCLUSIVE FIREBASE PRODUCT SERVICE ──
const firebaseProductService = {
  isConfigured: isFirebaseConfigured,

  /**
   * Fetches all products from Cloud Firestore 'products' collection
   * @returns {Promise<Array|null>} List of products or null if not configured / error
   */
  async getProducts() {
    if (!db || !isFirebaseConfigured()) {
      return null;
    }
    try {
      const snapshot = await db.collection('products').get();
      if (snapshot.empty) {
        return [];
      }
      const products = [];
      snapshot.forEach(doc => {
        products.push({ id: doc.id, ...doc.data() });
      });
      return products;
    } catch (err) {
      console.warn('Firebase Firestore getProducts note:', err);
      return null;
    }
  },

  /**
   * Note: Client-side writes are intentionally disabled by firestore.rules (allow write: if false).
   * Supabase is the unified, authoritative database for catalog CRUD operations.
   */
  async saveProduct(_product) {
    console.warn('ℹ️ [Firebase Notice] Catalog writes are managed authoritatively via Supabase backend. Client Firestore write skipped.');
    return false;
  },

  async deleteProduct(_productId) {
    console.warn('ℹ️ [Firebase Notice] Catalog deletions are managed authoritatively via Supabase backend. Client Firestore delete skipped.');
    return false;
  },

  async seedCatalog(_defaultProducts) {
    console.warn('ℹ️ [Firebase Notice] Catalog seeding is managed authoritatively via Supabase backend.');
    return { success: false, count: 0, note: 'Direct client-side Firestore writes are restricted by security rules.' };
  }
};

window.firebaseProductService = firebaseProductService;

// Also export if running in Node / bundler environment
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { app, db, analytics, firebaseProductService, firebaseConfig };
}
