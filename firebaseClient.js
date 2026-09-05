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
   * Adds or updates a product in Cloud Firestore
   * @param {Object} product
   * @returns {Promise<boolean>}
   */
  async saveProduct(product) {
    if (!db || !isFirebaseConfigured() || !product || !product.id) {
      return false;
    }
    try {
      const prodId = String(product.id);
      const cleanData = {
        name: product.name || '',
        category: product.category || 'toys',
        price: parseFloat(product.price) || 0,
        image: product.image || '',
        description: product.description || '',
        discount: parseFloat(product.discount) || 0,
        updatedAt: new Date().toISOString()
      };
      await db.collection('products').doc(prodId).set(cleanData, { merge: true });
      console.log(`🔥 [Firebase] Product "${product.name}" synced to Firestore (ID: ${prodId})`);
      return true;
    } catch (err) {
      console.error('🔥 [Firebase Error] Saving product to Firestore failed:', err);
      return false;
    }
  },

  /**
   * Deletes a product from Cloud Firestore
   * @param {string} productId
   * @returns {Promise<boolean>}
   */
  async deleteProduct(productId) {
    if (!db || !isFirebaseConfigured() || !productId) {
      return false;
    }
    try {
      await db.collection('products').doc(String(productId)).delete();
      console.log(`🔥 [Firebase] Product deleted from Firestore (ID: ${productId})`);
      return true;
    } catch (err) {
      console.error('🔥 [Firebase Error] Deleting product from Firestore failed:', err);
      return false;
    }
  },

  /**
   * Seeds default product catalog into Firestore
   * @param {Array} defaultProducts
   * @returns {Promise<{success: boolean, count: number}>}
   */
  async seedCatalog(defaultProducts) {
    if (!db || !isFirebaseConfigured()) {
      throw new Error("Please configure your Firebase credentials in firebaseClient.js first.");
    }
    try {
      const batch = db.batch();
      let count = 0;
      for (const p of defaultProducts) {
        const ref = db.collection('products').doc(String(p.id));
        batch.set(ref, {
          name: p.name,
          category: p.category,
          price: parseFloat(p.price) || 0,
          image: p.image || '',
          description: p.description || '',
          discount: parseFloat(p.discount) || 0,
          updatedAt: new Date().toISOString()
        }, { merge: true });
        count++;
      }
      await batch.commit();
      console.log(`🔥 [Firebase] Successfully seeded ${count} products to Firestore collection!`);
      return { success: true, count };
    } catch (err) {
      console.error('🔥 [Firebase Error] Seeding catalog failed:', err);
      throw err;
    }
  }
};

window.firebaseProductService = firebaseProductService;

// Also export if running in Node / bundler environment
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { app, db, analytics, firebaseProductService, firebaseConfig };
}
