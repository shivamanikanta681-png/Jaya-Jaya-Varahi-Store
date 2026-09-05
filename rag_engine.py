#!/usr/bin/env python3
"""
RAG Engine for Jaya Jaya Varahi Shop & Gifts
-------------------------------------------
Implements a complete Retrieval-Augmented Generation pipeline:
1. Knowledge Corpus Loading & Chunking
2. Dense Vector & BM25 Sparse Hybrid Retrieval
3. Real-time Supabase Catalog & Order Status Retrieval
4. Grounded Context Augmentation
5. Multi-tier Generation (Gemini API with built-in Contextual RAG Synthesizer fallback)
"""

import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from multilingual_kb import get_locale, LOCALES

BASE_DIR = Path(__file__).resolve().parent

def load_env() -> Dict[str, str]:
    env_path = BASE_DIR / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

ENV = load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", ENV.get("GEMINI_API_KEY", "")).strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", ENV.get("OPENAI_API_KEY", "")).strip()


def tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric tokens."""
    if not text:
        return []
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if len(t) > 1]
    return tokens


class KnowledgeBase:
    """Stores knowledge chunks and manages TF-IDF vector & BM25 inverted indexes."""

    def __init__(self, kb_path: Optional[Path] = None):
        self.kb_path = kb_path or (BASE_DIR / "knowledge_base.json")
        self.store_info: Dict[str, Any] = {}
        self.chunks: List[Dict[str, Any]] = []
        self.doc_tokens: List[List[str]] = []
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.chunk_vectors: List[Dict[str, float]] = []
        self.avg_doc_len: float = 0.0
        self.load()

    def load(self):
        if not self.kb_path.exists():
            print(f"[RAG] Warning: Knowledge base file {self.kb_path} not found.")
            return

        with open(self.kb_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.store_info = data.get("store_info", {})
        self.chunks = data.get("chunks", [])

        # Build index
        self.doc_tokens = []
        doc_freq: Dict[str, int] = {}
        total_tokens = 0

        for chunk in self.chunks:
            # Combine title, keywords, category and content for indexing
            text_block = f"{chunk.get('title', '')} {' '.join(chunk.get('keywords', []))} {chunk.get('category', '')} {chunk.get('content', '')}"
            tokens = tokenize(text_block)
            self.doc_tokens.append(tokens)
            total_tokens += len(tokens)

            unique_terms = set(tokens)
            for t in unique_terms:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        n_docs = max(len(self.chunks), 1)
        self.avg_doc_len = total_tokens / n_docs

        # Calculate IDF
        self.idf = {}
        for term, df in doc_freq.items():
            # Standard smoothed BM25 IDF
            self.idf[term] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

        # Build normalized TF-IDF vector embeddings for dense cosine similarity
        self.chunk_vectors = []
        for tokens in self.doc_tokens:
            vec: Dict[str, float] = {}
            if not tokens:
                self.chunk_vectors.append({})
                continue
            tf_counts: Dict[str, int] = {}
            for t in tokens:
                tf_counts[t] = tf_counts.get(t, 0) + 1

            norm_sq = 0.0
            for t, count in tf_counts.items():
                tfidf = (1.0 + math.log(count)) * self.idf.get(t, 1.0)
                vec[t] = tfidf
                norm_sq += tfidf * tfidf

            norm = math.sqrt(norm_sq) or 1.0
            for t in vec:
                vec[t] /= norm
            self.chunk_vectors.append(vec)

        print(f"[RAG] KnowledgeBase loaded: {len(self.chunks)} chunks indexed across {len(self.idf)} unique vocabulary terms.")

    def bm25_score(self, query_tokens: List[str], doc_idx: int, k1: float = 1.5, b: float = 0.75) -> float:
        """Computes Okapi BM25 score for a document."""
        doc_terms = self.doc_tokens[doc_idx]
        doc_len = len(doc_terms)
        if doc_len == 0:
            return 0.0

        tf_map: Dict[str, int] = {}
        for t in doc_terms:
            tf_map[t] = tf_map.get(t, 0) + 1

        score = 0.0
        for q in query_tokens:
            if q not in tf_map:
                continue
            tf = tf_map[q]
            idf = self.idf.get(q, 0.5)
            numerator = tf * (k1 + 1.0)
            denominator = tf + k1 * (1.0 - b + b * (doc_len / (self.avg_doc_len or 1.0)))
            score += idf * (numerator / denominator)

        return score

    def cosine_similarity(self, query_tokens: List[str], doc_idx: int) -> float:
        """Computes cosine similarity between query TF-IDF vector and document vector."""
        if not query_tokens:
            return 0.0
        doc_vec = self.chunk_vectors[doc_idx]
        if not doc_vec:
            return 0.0

        q_counts: Dict[str, int] = {}
        for t in query_tokens:
            q_counts[t] = q_counts.get(t, 0) + 1

        q_vec: Dict[str, float] = {}
        norm_sq = 0.0
        for t, cnt in q_counts.items():
            if t in self.idf:
                val = (1.0 + math.log(cnt)) * self.idf[t]
                q_vec[t] = val
                norm_sq += val * val

        q_norm = math.sqrt(norm_sq) or 1.0
        dot_product = 0.0
        for t, val in q_vec.items():
            normalized_q = val / q_norm
            if t in doc_vec:
                dot_product += normalized_q * doc_vec[t]

        return dot_product

    def retrieve(self, query: str, top_k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
        """Hybrid retrieval combining BM25 sparse scoring and vector cosine similarity."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return [(c, 0.0) for c in self.chunks[:top_k]]

        scored_chunks = []
        for idx, chunk in enumerate(self.chunks):
            bm25 = self.bm25_score(query_tokens, idx)
            cos_sim = self.cosine_similarity(query_tokens, idx)

            # Keyword direct match boost
            kw_boost = 0.0
            q_text = query.lower()
            for kw in chunk.get("keywords", []):
                if kw in q_text:
                    kw_boost += 1.2

            # Combined hybrid score
            hybrid_score = (bm25 * 0.45) + (cos_sim * 2.5) + kw_boost
            scored_chunks.append((chunk, hybrid_score))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]


class ProductRetriever:
    """Retrieves live products from Supabase database or fallback in-memory products."""

    DEFAULT_PRODUCTS = [
        {
            "id": "p1",
            "name": "Handcrafted Wooden Racing Toy Car",
            "category": "toys",
            "price": 450.0,
            "image": "images/card1.jpg",
            "description": "Handcrafted non-toxic wooden racing car with smooth rolling wheels for kids."
        },
        {
            "id": "p2",
            "name": "Interactive STEM Learning Robot",
            "category": "toys",
            "price": 899.0,
            "image": "images/card2.jpg",
            "description": "Smart STEM learning robot with lights, music, and interactive sound modes."
        },
        {
            "id": "p3",
            "name": "Plush Soft Cuddly Teddy Bear",
            "category": "toys",
            "price": 350.0,
            "image": "images/card3.jpg",
            "description": "Ultra-soft premium plush teddy bear suitable for toddlers and gifting."
        },
        {
            "id": "p4",
            "name": "Hand-Carved Pure Brass Peacock Diya",
            "category": "return_gifts",
            "price": 650.0,
            "image": "images/card4.jpg",
            "description": "Traditional pure brass peacock oil lamp with antique finish for mandir & return gifts."
        },
        {
            "id": "p5",
            "name": "Vintage Handcrafted Wooden Jewellery Box",
            "category": "return_gifts",
            "price": 550.0,
            "image": "images/card5.jpg",
            "description": "Floral carved wooden keepsake jewellery storage box with velvet interior."
        },
        {
            "id": "p6",
            "name": "Golden Thread Eco-Friendly Jute Bag",
            "category": "return_gifts",
            "price": 180.0,
            "image": "images/card6.jpg",
            "description": "Festive reusable jute gift bag with golden thread weave for poojas and ceremonies."
        },
        {
            "id": "p7",
            "name": "Tri-Ply Stainless Steel Induction Pot",
            "category": "kitchenware",
            "price": 1299.0,
            "image": "images/card7.jpg",
            "description": "Heavy gauge 3-layer steel pot with aluminum core, compatible with induction and gas."
        },
        {
            "id": "p8",
            "name": "Granite Non-Stick Frying Pan",
            "category": "kitchenware",
            "price": 850.0,
            "image": "images/card8.jpg",
            "description": "PFOA-free durable granite coated fry pan with ergonomic cool-touch handle."
        }
    ]

    def __init__(self):
        self.cached_products: List[Dict[str, Any]] = list(self.DEFAULT_PRODUCTS)
        self.last_fetch_ts: float = 0.0

    def fetch_products(self) -> List[Dict[str, Any]]:
        """Fetches products from Supabase table 'products' with fallback."""
        try:
            from supabase_client import get_supabase
            client = get_supabase()
            res = client.table("products").select("*").execute()
            if res.data and len(res.data) > 0:
                self.cached_products = res.data
                return self.cached_products
        except Exception as e:
            # Silently use cached products on database connection note
            pass
        return self.cached_products

    def search(self, query: str, day_discount: float = 15.0, top_k: int = 3) -> List[Dict[str, Any]]:
        """Extracts budget, category, keywords and retrieves matching products."""
        products = self.fetch_products()
        q_lower = query.lower()

        # Extract budget constraints (e.g., 'under 500', 'below 1000', 'less than 600')
        max_budget = None
        budget_match = re.search(r"(?:under|below|less than|within|upto|up to|costing)\s*(?:₹|rs\.?|inr)?\s*(\d+)", q_lower)
        if not budget_match:
            budget_match = re.search(r"(?:₹|rs\.?)\s*(\d+)", q_lower)
        if budget_match:
            try:
                max_budget = float(budget_match.group(1))
            except ValueError:
                pass

        query_tokens = tokenize(query)
        scored_products = []

        for p in products:
            orig_price = float(p.get("price", 0.0))
            discounted_price = round(orig_price * (1.0 - day_discount / 100.0), 2)
            
            # Budget filter
            if max_budget is not None and discounted_price > max_budget:
                continue

            name = p.get("name", "").lower()
            cat = p.get("category", "").lower()
            desc = p.get("description", "").lower()
            p_text = f"{name} {cat} {desc}"

            score = 0
            for t in query_tokens:
                if t in name:
                    score += 5
                elif t in cat:
                    score += 3
                elif t in desc:
                    score += 1

            if score > 0 or max_budget is not None:
                product_payload = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "category": p.get("category"),
                    "original_price": orig_price,
                    "discount_percent": day_discount,
                    "discounted_price": discounted_price,
                    "image": p.get("image", "images/card1.jpg"),
                    "description": p.get("description", "")
                }
                scored_products.append((product_payload, score))

        scored_products.sort(key=lambda x: x[1], reverse=True)
        return [sp[0] for sp in scored_products[:top_k]]


class OrderRetriever:
    """Retrieves order tracking details from Supabase 'orders' table."""

    @staticmethod
    def extract_order_query(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extracts order ID or phone number from customer query."""
        # Check order ID (e.g., #JJV-1001, JJV-8941, order 12345)
        order_id_match = re.search(r"(?:order(?:\s*id|\s*number|#)?[:\s]*|#)([a-zA-Z0-9\-_]{4,})", text, re.I)
        order_id = order_id_match.group(1) if order_id_match else None

        # Check 10-digit Indian mobile number
        phone_match = re.search(r"\b([6-9]\d{9})\b", text)
        phone = phone_match.group(1) if phone_match else None

        return order_id, phone

    @staticmethod
    def lookup_order(order_id: Optional[str] = None, phone: Optional[str] = None, client_orders: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """Queries client_orders or Supabase for order details."""
        clean_id = (order_id or "").replace("#", "").strip().lower() if order_id else None
        clean_phone = (phone or "").strip() if phone else None

        # 1. First check client_orders from user's current session
        if client_orders:
            for o in client_orders:
                o_id = str(o.get("id", "") or o.get("order_number", "")).replace("#", "").strip().lower()
                o_phone = str(o.get("phone", "") or o.get("customer_phone", "")).strip()
                if clean_id and clean_id in o_id:
                    return {
                        "order_number": o.get("id") or o.get("order_number", "JJV-Recent"),
                        "customer_name": o.get("customerName") or o.get("customer_name", "Customer"),
                        "status": o.get("status", "Dispatched / In Transit"),
                        "delivery_location": "Hyderabad" if o.get("isHyderabad") else "Outside Hyderabad",
                        "total_payable": o.get("totalAmount") or o.get("total_payable", 0)
                    }
                if clean_phone and clean_phone in o_phone:
                    return {
                        "order_number": o.get("id") or o.get("order_number", "JJV-Recent"),
                        "customer_name": o.get("customerName") or o.get("customer_name", "Customer"),
                        "status": o.get("status", "Dispatched / In Transit"),
                        "delivery_location": "Hyderabad" if o.get("isHyderabad") else "Outside Hyderabad",
                        "total_payable": o.get("totalAmount") or o.get("total_payable", 0)
                    }

        if not order_id and not phone:
            return None

        # 2. Check Supabase orders table
        try:
            from supabase_client import get_supabase
            client = get_supabase()
            query = client.table("orders").select("*")

            if order_id:
                res = query.ilike("order_number", f"%{clean_id}%").limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]

            if phone:
                res = client.table("orders").select("*").ilike("customer_phone", f"%{clean_phone}%").order("created_at", desc=True).limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
        except Exception as e:
            pass

        return None


class RAGPipeline:
    """End-to-end RAG controller combining Retrieval, Augmentation, and Generation."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.product_retriever = ProductRetriever()
        self.order_retriever = OrderRetriever()

    def generate_with_gemini(self, prompt: str, context_text: str, language: str) -> Optional[str]:
        """Calls Google Gemini REST API with grounded RAG context."""
        if not GEMINI_API_KEY:
            return None

        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            
            system_instruction = (
                "You are the friendly, helpful AI Customer Support Assistant for 'Jaya Jaya Varahi Gifts & Shop' "
                "(Boduppal, Hyderabad). Your task is to answer customer questions accurately, warmly, and concisely.\n\n"
                "STRICT GROUNDING RULES:\n"
                "1. Only state facts directly present in the provided STORE KNOWLEDGE CONTEXT.\n"
                "2. If you do not have enough information, politely direct the customer to our WhatsApp at +91 75693 04410.\n"
                f"3. Respond naturally in {language.upper()} language or the language used in the query.\n"
                "4. Format your answer with clean Markdown, emojis, and bullet points for readability."
            )

            full_prompt = (
                f"{system_instruction}\n\n"
                f"--- STORE KNOWLEDGE CONTEXT ---\n{context_text}\n------------------------------\n\n"
                f"CUSTOMER QUESTION:\n{prompt}\n\n"
                "ASSISTANT RESPONSE:"
            )

            payload = {
                "contents": [
                    {
                        "parts": [{"text": full_prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 600
                }
            }

            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    if text_parts:
                        ans = text_parts[0].get("text", "").strip()
                        # Convert markdown bold to html bold for web UI consistency
                        ans_html = ans.replace("\n", "<br>")
                        return ans_html
        except Exception as e:
            print(f"[RAG] Gemini API call exception: {e}")

        return None

    def synthesize_local_rag_response(self, query: str, language: str, top_chunks: List[Tuple[Dict[str, Any], float]], 
                                       matching_products: List[Dict[str, Any]], order_info: Optional[Dict[str, Any]]) -> str:
        """Intelligent, deterministic local contextual synthesizer supporting all 16 languages."""
        locale = get_locale(language)
        answers = locale.get("answers", {})
        add_text = locale.get("add_btn", "Add")
        related_title = locale.get("related_title", "Related Store Items:")

        # 1. Check Order Tracking synthesized answer
        if order_info:
            order_num = order_info.get("order_number", "JJV-Recent")
            cust_name = order_info.get("customer_name", "Customer")
            status = order_info.get("status", "In Transit")
            loc = order_info.get("delivery_location", "Hyderabad")
            total = float(order_info.get("total_payable", 0))
            is_hyd = "hyderabad" in str(loc).lower()
            delivery_mode = "🚀 Hyderabad Express (1-3 hrs)" if is_hyd else "🚚 All-India Express Courier (2-4 days)"

            template = locale.get("order_found", LOCALES["en"]["order_found"])
            try:
                return template.format(
                    order_num=order_num,
                    cust_name=cust_name,
                    status=status,
                    delivery_mode=delivery_mode,
                    total=total
                )
            except Exception:
                return f"📦 Order #{order_num}: Status: {status}, Total: ₹{total:.2f}"

        # Helper to generate product cards HTML with localized 'Add' button
        def build_cards_html(prods: List[Dict[str, Any]]) -> str:
            if not prods:
                return ""
            cards = ""
            for p in prods:
                img_src = p.get("image") or "images/card1.jpg"
                cards += f"""
                <div class="chat-product-card">
                  <img src="{img_src}" alt="{p.get('name')}" class="chat-product-img" onerror="this.src='images/card1.jpg'">
                  <div class="chat-product-details">
                    <div class="chat-product-title">{p.get('name')}</div>
                    <div class="chat-product-price-row">
                      <span class="chat-product-price">₹{p.get('discounted_price'):.2f}</span>
                      <span class="chat-product-disc">{p.get('discount_percent')}% OFF</span>
                    </div>
                  </div>
                  <button type="button" class="chat-add-btn" onclick="window.shopApp && window.shopApp.addToCart('{p.get('id')}'); window.shopApp && window.shopApp.showToast('Added to cart!', 'success');">
                    <i class='bx bx-cart-add'></i> {add_text}
                  </button>
                </div>
                """
            return f"<div class='chat-product-cards-wrap'>{cards}</div>"

        # Check if top chunk is a strong policy/support match
        has_strong_chunk = False
        primary_chunk_text = ""
        if top_chunks:
            best_chunk, score = top_chunks[0]
            cat = best_chunk.get("category", "")
            if score >= 0.8 or cat in answers or best_chunk.get("id") in answers:
                has_strong_chunk = True
                if cat in answers:
                    primary_chunk_text = answers[cat]
                elif best_chunk.get("id") in answers:
                    primary_chunk_text = answers[best_chunk.get("id")]
                else:
                    quick_answers = best_chunk.get("quick_answer", {})
                    primary_chunk_text = quick_answers.get(language) or quick_answers.get("en") or best_chunk.get("content", "")

        # Product-focused query detection
        is_explicit_product_search = any(k in query.lower() for k in [
            "show me", "looking for", "want to buy", "cost of", "price of", "how much is", 
            "under ", "below ", "less than ", "budget", "recommend", "options", "బొమ్మ", "ధర", "కావాలి", "खिलौने", "दाम", "कीमत"
        ])

        if is_explicit_product_search and matching_products:
            intro = locale.get("prod_intro", "Here are top matching recommendations:")
            return f"{intro}<br>{build_cards_html(matching_products)}<br>👉 Click <strong>'{add_text}'</strong> on any item above to place it directly in your cart!"

        # Policy / support response with optional product attachments
        if has_strong_chunk and primary_chunk_text:
            if matching_products and any(k in query.lower() for k in ["toy", "robot", "car", "teddy", "diya", "brass", "pan", "pot", "cookware", "box", "bag", "బొమ్మ", "దీపం", "खिलौना"]):
                return f"{primary_chunk_text}<br><br><strong>{related_title}</strong><br>{build_cards_html(matching_products)}"
            return primary_chunk_text

        # Product fallback if query mentions specific products
        if matching_products:
            intro = locale.get("prod_intro", "Here are matching items from our live catalog:")
            return f"{intro}<br>{build_cards_html(matching_products)}"

        # Default fallback in user's selected language
        return locale.get("default_fallback", LOCALES["en"]["default_fallback"])

    def answer_query(self, message: str, language: str = "en", customer_phone: Optional[str] = None, 
                     order_id: Optional[str] = None, day_discount: float = 15.0,
                     client_orders: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Main RAG execution flow supporting all 16 languages."""
        q = (message or "").strip()
        locale = get_locale(language)
        default_pills = locale.get("pills", ["Toys under ₹500", "Return Gifts", "Hyderabad Delivery", "Today's Offer", "Store Address"])

        # Immediate greeting response if query is welcome / empty
        if not q or q.lower() in ["welcome", "hello", "hi", "namaste", "start", "హలో", "నమస్కారం", "नमस्ते", "வணக்கம்", "ನಮಸ್ಕಾರ"]:
            return {
                "success": True,
                "answer": locale["welcome"],
                "sources": [],
                "products": [],
                "follow_ups": default_pills,
                "grounded_chunk_count": 0
            }

        # Step 1: Hybrid Retrieval of Knowledge Chunks
        retrieved_chunks = self.kb.retrieve(q, top_k=3)

        # Step 2: Catalog Retrieval of Matching Products
        matching_products = self.product_retriever.search(q, day_discount=day_discount, top_k=3)

        # Step 3: Order Retrieval (if query has order ID / phone or passed explicitly)
        extracted_order_id, extracted_phone = self.order_retriever.extract_order_query(q)
        lookup_id = extracted_order_id or order_id
        lookup_phone = extracted_phone or customer_phone
        order_info = self.order_retriever.lookup_order(order_id=lookup_id, phone=lookup_phone, client_orders=client_orders)

        # Step 4: Build Grounded Context Text
        context_parts = []
        for chunk, score in retrieved_chunks:
            context_parts.append(f"[{chunk.get('title')}]\n{chunk.get('content')}")

        if matching_products:
            prod_summary = "\n".join([f"- {p['name']} (₹{p['discounted_price']:.2f}, {p['discount_percent']}% OFF)" for p in matching_products])
            context_parts.append(f"[Available Products In Catalog]\n{prod_summary}")

        if order_info:
            context_parts.append(f"[Customer Order Status]\nOrder #{order_info.get('order_number')}: Status={order_info.get('status')}, Customer={order_info.get('customer_name')}, Total=₹{order_info.get('total_payable')}")

        grounded_context_text = "\n\n".join(context_parts)

        # Step 5: Generation (Gemini API or Multilingual Local Synthesizer)
        answer_text = None
        if GEMINI_API_KEY:
            answer_text = self.generate_with_gemini(q, grounded_context_text, language)

        if not answer_text:
            answer_text = self.synthesize_local_rag_response(q, language, retrieved_chunks, matching_products, order_info)

        # Step 6: Package Sources and Follow-ups
        sources = []
        for chunk, score in retrieved_chunks:
            if score > 0.3:
                sources.append({
                    "id": chunk.get("id"),
                    "title": chunk.get("title"),
                    "category": chunk.get("category"),
                    "relevance_score": round(float(score), 2)
                })

        # Localized follow-up suggestion pills
        follow_ups = default_pills

        return {
            "success": True,
            "answer": answer_text,
            "sources": sources,
            "products": matching_products,
            "follow_ups": follow_ups,
            "grounded_chunk_count": len(retrieved_chunks)
        }

# Global Singleton
_rag_pipeline_instance: Optional[RAGPipeline] = None

def get_rag_pipeline() -> RAGPipeline:
    global _rag_pipeline_instance
    if _rag_pipeline_instance is None:
        _rag_pipeline_instance = RAGPipeline()
    return _rag_pipeline_instance
