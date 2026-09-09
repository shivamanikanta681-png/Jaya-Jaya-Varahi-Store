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

  async saveProduct(product) {
    if (!db || !isFirebaseConfigured() || !product) {
      return false;
    }
    try {
      const prodId = String(product.id || 'p_' + Date.now());
      await db.collection('products').doc(prodId).set(product, { merge: true });
      console.log('🔥 [Firebase] Product saved to Firestore collection:', prodId);
      return true;
    } catch (err) {
      console.warn('Firebase Firestore saveProduct note (enable write rules if restricting):', err.message || err);
      return false;
    }
  },

  async deleteProduct(productId) {
    if (!db || !isFirebaseConfigured() || !productId) {
      return false;
    }
    try {
      await db.collection('products').doc(String(productId)).delete();
      console.log('🔥 [Firebase] Product deleted from Firestore collection:', productId);
      return true;
    } catch (err) {
      console.warn('Firebase Firestore deleteProduct note:', err.message || err);
      return false;
    }
  },

  async seedCatalog(defaultProducts) {
    if (!db || !isFirebaseConfigured() || !Array.isArray(defaultProducts)) {
      return { success: false, count: 0 };
    }
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
      return { success: false, count: 0, error: err.message || err };
    }
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

