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
let auth = null;
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

    if (typeof firebase.auth === 'function') {
      try {
        auth = firebase.auth();
        auth.useDeviceLanguage();
        window.auth = auth;
        window.firebaseAuth = auth;
      } catch (authErr) {
        console.warn('Auth note:', authErr.message);
      }
    }

    if (typeof firebase.analytics === 'function') {
      try {
        analytics = firebase.analytics();
        window.analytics = analytics;
      } catch (analyticsErr) {
        console.warn('Analytics note:', analyticsErr.message);
      }
    }

    console.log('🔥 Live Firebase App, Auth & Firestore initialized for Project "jaya-jaya-varahi-shop"!');
  }
} catch (err) {
  console.warn('⚠️ Firebase initialization note:', err.message);
}

// ── EXCLUSIVE FIREBASE PRODUCT SERVICE ──
// Helper to parse Firestore REST API document format
function parseFirestoreDoc(doc) {
  if (!doc || !doc.fields) return null;
  const id = doc.name ? doc.name.split('/').pop() : '';
  const obj = { id };
  for (const [key, valObj] of Object.entries(doc.fields)) {
    if ('stringValue' in valObj) obj[key] = valObj.stringValue;
    else if ('integerValue' in valObj) obj[key] = parseInt(valObj.integerValue, 10);
    else if ('doubleValue' in valObj) obj[key] = parseFloat(valObj.doubleValue);
    else if ('booleanValue' in valObj) obj[key] = valObj.booleanValue;
    else if ('mapValue' in valObj) obj[key] = valObj.mapValue;
    else if ('arrayValue' in valObj) obj[key] = (valObj.arrayValue.values || []).map(v => Object.values(v)[0]);
  }
  return obj;
}

// Helper to convert plain JS object to Firestore REST API format
function toFirestoreDocBody(product) {
  const fields = {};
  for (const [key, val] of Object.entries(product)) {
    if (val === undefined || val === null) continue;
    if (typeof val === 'number') {
      if (Number.isInteger(val)) fields[key] = { integerValue: String(val) };
      else fields[key] = { doubleValue: val };
    } else if (typeof val === 'boolean') {
      fields[key] = { booleanValue: val };
    } else {
      fields[key] = { stringValue: String(val) };
    }
  }
  return { fields };
}

// ── EXCLUSIVE FIREBASE PRODUCT SERVICE ──
const firebaseProductService = {
  isConfigured: isFirebaseConfigured,

  /**
   * Fetches all products directly from Cloud Firestore 'products' collection.
   * Uses Firebase SDK when available with seamless REST API fallback.
   * @returns {Promise<Array|null>} List of products or null if not configured / error
   */
  async getProducts() {
    if (!isFirebaseConfigured()) {
      return null;
    }

    // 1. Try official Firebase SDK if available
    if (db && typeof db.collection === 'function') {
      try {
        const snapshot = await db.collection('products').get();
        if (!snapshot.empty) {
          const products = [];
          snapshot.forEach(doc => {
            products.push({ id: doc.id, ...doc.data() });
          });
          console.log(`🔥 [Firebase SDK] Successfully fetched ${products.length} products from Firestore!`);
          return products;
        }
      } catch (sdkErr) {
        console.warn('Firebase SDK getProducts note, trying REST API fallback:', sdkErr.message || sdkErr);
      }
    }

    // 2. Direct REST API fallback
    try {
      const restUrl = `https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)/documents/products?key=${firebaseConfig.apiKey}`;
      const response = await fetch(restUrl);
      if (response.ok) {
        const json = await response.json();
        const docs = json.documents || [];
        const products = docs.map(parseFirestoreDoc).filter(Boolean);
        console.log(`🔥 [Firebase REST] Successfully fetched ${products.length} products from Firestore!`);
        return products;
      }
    } catch (restErr) {
      console.warn('Firebase REST getProducts fallback note:', restErr.message || restErr);
    }

    return null;
  },

  /**
   * Saves or updates a product document in Cloud Firestore 'products' collection.
   * Uses Firebase SDK with seamless REST API fallback.
   */
  async saveProduct(product) {
    if (!isFirebaseConfigured() || !product) {
      return false;
    }

    const prodId = String(product.id || 'p_' + Date.now());
    const cleanProduct = {
      ...product,
      id: prodId,
      updated_at: new Date().toISOString()
    };

    // 1. Try Firebase SDK
    if (db && typeof db.collection === 'function') {
      try {
        await db.collection('products').doc(prodId).set(cleanProduct, { merge: true });
        console.log('🔥 [Firebase SDK] Product saved to Firestore collection:', prodId);
        return true;
      } catch (sdkErr) {
        console.warn('Firebase SDK saveProduct note, attempting REST API fallback:', sdkErr.message || sdkErr);
      }
    }

    // 2. Direct REST API fallback
    try {
      const restUrl = `https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)/documents/products/${encodeURIComponent(prodId)}?key=${firebaseConfig.apiKey}`;
      const docPayload = toFirestoreDocBody(cleanProduct);
      const response = await fetch(restUrl, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(docPayload)
      });
      if (response.ok) {
        console.log('🔥 [Firebase REST] Product successfully saved to Firestore collection:', prodId);
        return true;
      } else {
        const errData = await response.text();
        console.warn('Firebase REST saveProduct response note:', errData);
      }
    } catch (restErr) {
      console.warn('Firebase REST saveProduct fallback note:', restErr.message || restErr);
    }

    return false;
  },

  /**
   * Deletes a product document from Cloud Firestore 'products' collection.
   */
  async deleteProduct(productId) {
    if (!isFirebaseConfigured() || !productId) {
      return false;
    }

    const prodId = String(productId);

    // 1. Try Firebase SDK
    if (db && typeof db.collection === 'function') {
      try {
        await db.collection('products').doc(prodId).delete();
        console.log('🔥 [Firebase SDK] Product deleted from Firestore collection:', prodId);
        return true;
      } catch (sdkErr) {
        console.warn('Firebase SDK deleteProduct note, attempting REST API fallback:', sdkErr.message || sdkErr);
      }
    }

    // 2. Direct REST API fallback
    try {
      const restUrl = `https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)/documents/products/${encodeURIComponent(prodId)}?key=${firebaseConfig.apiKey}`;
      const response = await fetch(restUrl, { method: 'DELETE' });
      if (response.ok) {
        console.log('🔥 [Firebase REST] Product deleted from Firestore collection:', prodId);
        return true;
      }
    } catch (restErr) {
      console.warn('Firebase REST deleteProduct fallback note:', restErr.message || restErr);
    }

    return false;
  },

  async seedCatalog(defaultProducts) {
    if (!isFirebaseConfigured() || !Array.isArray(defaultProducts)) {
      return { success: false, count: 0 };
    }
    if (db && typeof db.batch === 'function') {
      try {
        const batch = db.batch();
        defaultProducts.forEach(prod => {
          const ref = db.collection('products').doc(String(prod.id));
          batch.set(ref, prod, { merge: true });
        });
        await batch.commit();
        return { success: true, count: defaultProducts.length };
      } catch (err) {
        console.warn('Firebase Firestore seedCatalog note:', err.message || err);
      }
    }
    // Fallback: save items individually
    let saved = 0;
    for (const p of defaultProducts) {
      const ok = await this.saveProduct(p);
      if (ok) saved++;
    }
    return { success: saved > 0, count: saved };
  }
};

window.firebaseProductService = firebaseProductService;

// ── FIREBASE PHONE AUTHENTICATION SERVICE (Development & Testing) ──
const firebasePhoneAuthService = {
  isConfigured() {
    return isFirebaseConfigured() && typeof firebase !== 'undefined' && typeof firebase.auth === 'function';
  },

  getAuth() {
    if (auth) return auth;
    if (typeof firebase !== 'undefined' && typeof firebase.auth === 'function') {
      auth = firebase.auth();
      return auth;
    }
    return null;
  },

  /**
   * Initializes or refreshes the reCAPTCHA verifier attached to containerId
   */
  initRecaptcha(containerId = 'recaptcha-container') {
    const authInstance = this.getAuth();
    if (!authInstance) {
      throw new Error('Firebase Authentication is not available. Ensure Firebase scripts are loaded.');
    }

    if (window.recaptchaVerifier) {
      try {
        window.recaptchaVerifier.clear();
      } catch (_e) {
        // ignore clear error
      }
      window.recaptchaVerifier = null;
    }

    const containerEl = document.getElementById(containerId) || document.body;

    window.recaptchaVerifier = new firebase.auth.RecaptchaVerifier(containerEl, {
      size: 'invisible',
      callback: () => {
        // reCAPTCHA solved
      },
      'expired-callback': () => {
        console.warn('[Firebase Recaptcha] Token expired. Will re-initialize on next attempt.');
      }
    });

    return window.recaptchaVerifier;
  },

  /**
   * Dispatches phone OTP via Firebase Phone Auth.
   * Seamlessly verifies test phone numbers added in Firebase Console.
   */
  async sendPhoneOtp(phoneNumber, verifier) {
    const authInstance = this.getAuth();
    if (!authInstance) throw new Error('Firebase Auth is not initialized.');
    const appVerifier = verifier || window.recaptchaVerifier || this.initRecaptcha();
    return await authInstance.signInWithPhoneNumber(phoneNumber, appVerifier);
  },

  /**
   * Verifies the OTP entered by user using Firebase confirmation result.
   */
  async verifyPhoneOtp(confirmationResult, otpCode) {
    if (!confirmationResult || typeof confirmationResult.confirm !== 'function') {
      throw new Error('No pending Firebase phone verification session found.');
    }
    return await confirmationResult.confirm(otpCode);
  },

  async signOut() {
    const authInstance = this.getAuth();
    if (authInstance && typeof authInstance.signOut === 'function') {
      return await authInstance.signOut();
    }
  }
};

window.firebasePhoneAuthService = firebasePhoneAuthService;

// ── FIREBASE EMAIL & PASSWORD AUTHENTICATION SERVICE (100% Free, Zero SMS) ──
const firebaseEmailAuthService = {
  isConfigured() {
    return isFirebaseConfigured() && typeof firebase !== 'undefined' && typeof firebase.auth === 'function';
  },

  getAuth() {
    if (auth) return auth;
    if (typeof firebase !== 'undefined' && typeof firebase.auth === 'function') {
      auth = firebase.auth();
      return auth;
    }
    return null;
  },

  async signUpWithEmail(email, password, displayName = '') {
    const authInstance = this.getAuth();
    if (!authInstance) throw new Error('Firebase Authentication is not available.');
    const userCredential = await authInstance.createUserWithEmailAndPassword(email.trim(), password);
    if (displayName && userCredential.user && typeof userCredential.user.updateProfile === 'function') {
      try {
        await userCredential.user.updateProfile({ displayName: displayName.trim() });
      } catch (_e) {
        // profile update non-fatal
      }
    }
    const idToken = await userCredential.user.getIdToken();
    return { user: userCredential.user, idToken };
  },

  async signInWithEmail(email, password) {
    const authInstance = this.getAuth();
    if (!authInstance) throw new Error('Firebase Authentication is not available.');
    const userCredential = await authInstance.signInWithEmailAndPassword(email.trim(), password);
    const idToken = await userCredential.user.getIdToken();
    return { user: userCredential.user, idToken };
  },

  async sendPasswordReset(email) {
    const authInstance = this.getAuth();
    if (!authInstance) throw new Error('Firebase Authentication is not available.');
    await authInstance.sendPasswordResetEmail(email.trim());
    return true;
  },

  async getCurrentUserToken() {
    const authInstance = this.getAuth();
    if (authInstance && authInstance.currentUser) {
      return await authInstance.currentUser.getIdToken();
    }
    return null;
  },

  async signOut() {
    const authInstance = this.getAuth();
    if (authInstance && typeof authInstance.signOut === 'function') {
      return await authInstance.signOut();
    }
  }
};

window.firebaseEmailAuthService = firebaseEmailAuthService;

// Also export if running in Node / bundler environment
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { app, db, auth, analytics, firebaseProductService, firebasePhoneAuthService, firebaseEmailAuthService, firebaseConfig };
}

