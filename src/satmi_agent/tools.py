from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
import time
from typing import Any
from uuid import uuid4

import httpx

from satmi_agent.config import settings
from satmi_agent.observability import record_shopify_error
from satmi_agent.persistence import persistence_service
from satmi_agent.schemas import HandoffTicket
from satmi_agent.tracing import get_tracer


DEFAULT_PRODUCT_IMAGE_URL = "https://placehold.co/640x400/F9F6F2/7A1E1E?text=SATMI"
logger = logging.getLogger("satmi_agent.tools")


class ToolingService:
    """Shopify-backed tooling with local fallback when credentials are not configured."""

    def __init__(self) -> None:
        # Public storefront identity remains fixed to satmi.in.
        self._public_store_domain = "satmi.in"
        # Admin API domain may differ (typically *.myshopify.com).
        self._admin_store_domain = settings.shopify_store_domain or self._public_store_domain
        self._token = settings.shopify_admin_api_token
        self._api_version = settings.shopify_api_version
        self._shop_currency_cache: str | None = None

    @property
    def shopify_enabled(self) -> bool:
        return bool(self._admin_store_domain and self._token)

    def _shopify_headers(self) -> dict[str, str]:
        if not self._token:
            raise RuntimeError("Shopify Admin API token is not configured.")
        return {
            "X-Shopify-Access-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _shopify_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not self._admin_store_domain:
            raise RuntimeError("Shopify store domain is not configured.")
        safe_path = path if path.startswith("/") else f"/{path}"
        return f"https://{self._admin_store_domain}/admin/api/{self._api_version}{safe_path}"

    def _draft_orders_endpoint_url(self) -> str:
        if not self._admin_store_domain:
            raise RuntimeError("Shopify store domain is not configured.")
        return f"https://{self._admin_store_domain}/admin/api/2024-01/draft_orders.json"

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._shopify_url(path)
        retryable_status = {429, 500, 502, 503, 504}
        tracer = get_tracer("satmi_agent.tools")

        with httpx.Client(timeout=settings.shopify_timeout_seconds) as client:
            for attempt in range(settings.shopify_max_retries + 1):
                try:
                    with tracer.start_as_current_span("shopify.request") as span:
                        span.set_attribute("shopify.method", method)
                        span.set_attribute("shopify.path", path)
                        span.set_attribute("shopify.attempt", attempt)
                        response = client.request(method, url, headers=self._shopify_headers(), params=params, json=json)
                        span.set_attribute("http.status_code", response.status_code)
                    if response.status_code in retryable_status and attempt < settings.shopify_max_retries:
                        retry_after = response.headers.get("Retry-After")
                        sleep_for = float(retry_after) if retry_after and retry_after.isdigit() else (2**attempt)
                        time.sleep(sleep_for)
                        continue

                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    with tracer.start_as_current_span("shopify.request.error") as span:
                        span.set_attribute("http.status_code", exc.response.status_code)
                    error_class = "5xx" if exc.response.status_code >= 500 else str(exc.response.status_code)
                    record_shopify_error(error_class)
                    raise RuntimeError(self._normalize_shopify_error(exc.response.status_code)) from exc
                except httpx.RequestError as exc:
                    with tracer.start_as_current_span("shopify.request.error") as span:
                        span.set_attribute("error.type", "request_error")
                    record_shopify_error("request_error")
                    if attempt < settings.shopify_max_retries:
                        time.sleep(2**attempt)
                        continue
                    raise RuntimeError("Shopify service is temporarily unavailable. Please try again.") from exc

        raise RuntimeError("Shopify service is temporarily unavailable. Please try again.")

    def _normalize_shopify_error(self, status_code: int) -> str:
        if status_code == 401:
            return "Shopify authentication failed. Please verify API credentials."
        if status_code == 403:
            return "Shopify access denied. Required API scopes may be missing."
        if status_code == 404:
            return "Requested Shopify resource was not found."
        if status_code == 429:
            return "Shopify rate limit reached. Please retry shortly."
        if status_code >= 500:
            return "Shopify is temporarily unavailable. Please retry shortly."
        return "Shopify request failed due to an unexpected error."

    def _extract_order_number(self, order_reference: str) -> str:
        digits = "".join(ch for ch in order_reference if ch.isdigit())
        if not digits:
            raise RuntimeError("Order reference must contain digits (example: #1001).")
        return digits

    def _strip_product_gid(self, product_id: str) -> str:
        raw = str(product_id or "").strip()
        if not raw:
            return ""
        # Handles gid://shopify/Product/1234567890 and plain numeric ids.
        if raw.startswith("gid://shopify/Product/"):
            raw = raw.rsplit("/", 1)[-1]
        match = re.search(r"(\d+)", raw)
        return match.group(1) if match else raw

    def _resolve_checkout_variant_and_title(self, product_id: str) -> tuple[str, str]:
        cleaned_id = str(product_id or "").strip()
        if not cleaned_id:
            raise RuntimeError("product_id is required for checkout.")

        products = persistence_service.list_product_catalog(limit=settings.catalog_cache_max_products)
        for product in products:
            current_product_id = str(product.get("id") or "").strip()
            product_title = str(product.get("title") or cleaned_id).strip() or cleaned_id
            variants = product.get("variants") if isinstance(product.get("variants"), list) else []

            if current_product_id and current_product_id == cleaned_id:
                for variant in variants:
                    variant_id = str((variant or {}).get("id") or "").strip()
                    if variant_id:
                        return variant_id, product_title
                return cleaned_id, product_title

            for variant in variants:
                variant_id = str((variant or {}).get("id") or "").strip()
                if variant_id and variant_id == cleaned_id:
                    return variant_id, product_title

        return cleaned_id, cleaned_id

    def _find_order_by_reference(self, order_reference: str) -> dict[str, Any]:
        order_number = self._extract_order_number(order_reference)
        response = self._request("GET", "/orders.json", params={"status": "any", "limit": 50})
        orders = response.get("orders", [])

        expected_name = f"#{order_number}"
        for order in orders:
            if str(order.get("name", "")).strip() == expected_name:
                return order
        raise RuntimeError(f"Order {expected_name} was not found in Shopify.")

    def _shop_currency(self) -> str:
        if self._shop_currency_cache:
            return self._shop_currency_cache
        if not self.shopify_enabled:
            return settings.display_currency_code
        try:
            response = self._request("GET", "/shop.json")
            shop = response.get("shop", {})
            code = str(shop.get("currency") or settings.display_currency_code).upper()
            self._shop_currency_cache = code
            return code
        except Exception:
            return settings.display_currency_code

    def _storefront_domain(self) -> str:
        domain = (self._public_store_domain or settings.shopify_store_domain or "uismgu-m5.myshopify.com").strip()
        if domain.startswith("http://") or domain.startswith("https://"):
            domain = domain.split("://", 1)[1]
        return domain.strip("/")

    def _query_tokens(self, query: str) -> list[str]:
        stop_words = {
            "what",
            "is",
            "a",
            "an",
            "the",
            "of",
            "for",
            "to",
            "me",
            "about",
            "tell",
            "show",
            "please",
            "do",
            "you",
            "have",
        }
        tokens = re.findall(r"[a-zA-Z0-9']+", query.lower())
        return [token for token in tokens if token not in stop_words and len(token) > 1]

    def _extract_material_hints(self, query: str) -> set[str]:
        known_materials = {
            "rudraksha",
            "karungali",
            "crystal",
            "pyrite",
            "rose",
            "quartz",
            "tulsi",
            "sandal",
            "silver",
        }
        tokens = set(self._query_tokens(query))
        hints: set[str] = set()
        if "rose" in tokens and "quartz" in tokens:
            hints.add("rose quartz")
        hints.update(token for token in tokens if token in known_materials)
        return hints

    def _matches_material_hints(self, product: dict[str, Any], hints: set[str]) -> bool:
        if not hints:
            return True
        searchable = self._searchable_product_text(product)
        for hint in hints:
            if hint in searchable:
                return True
        return False

    def _searchable_product_text(self, product: dict[str, Any]) -> str:
        title = str(product.get("title", ""))
        body = str(product.get("body_html", ""))
        product_type = str(product.get("product_type", ""))
        tags = str(product.get("tags", ""))
        body_no_html = re.sub(r"<[^>]+>", " ", body)
        return " ".join([title, body_no_html, product_type, tags]).lower()

    def _score_product(self, *, query: str, tokens: list[str], product: dict[str, Any]) -> int:
        if not tokens:
            return 0
        searchable = self._searchable_product_text(product)
        title = str(product.get("title", "")).lower()
        product_type = str(product.get("product_type", "")).lower()
        tags = str(product.get("tags", "")).lower()

        score = 0
        for token in tokens:
            if token in title:
                score += 3
            elif token in product_type or token in tags:
                score += 2
            elif token in searchable:
                score += 1

        query_l = query.lower().strip()
        if query_l and query_l in title:
            score += 4
        if tokens and all(token in searchable for token in tokens):
            score += 2
        return score

    def _cache_snapshot_fresh(self, latest_sync_at: Any) -> bool:
        if latest_sync_at is None:
            return False
        try:
            if isinstance(latest_sync_at, datetime):
                sync_time = latest_sync_at if latest_sync_at.tzinfo else latest_sync_at.replace(tzinfo=timezone.utc)
            else:
                return False
            age_seconds = (datetime.now(timezone.utc) - sync_time).total_seconds()
            return age_seconds <= max(0, settings.catalog_cache_ttl_seconds)
        except Exception:
            return False

    def _extract_product_image_url(self, product: dict[str, Any]) -> str:
        image_url = ""

        # --- Robust fallback chain with explicit dict handling ---
        # 1. REST: product.image.src
        if product.get("image") and isinstance(product["image"], dict) and product["image"].get("src"):
            image_url = str(product["image"]["src"] or "").strip()
        # 2. REST: product.images[0].src
        elif product.get("images") and isinstance(product.get("images"), list) and len(product["images"]) > 0:
            first_img = product["images"][0]
            if isinstance(first_img, dict) and first_img.get("src"):
                image_url = str(first_img["src"] or "").strip()
        # 3. GraphQL: product.featuredImage.url
        elif product.get("featuredImage") and isinstance(product.get("featuredImage"), dict) and product["featuredImage"].get("url"):
            image_url = str(product["featuredImage"]["url"] or "").strip()
        # 4. GraphQL edges: product.images.edges[0].node.url
        elif product.get("images") and isinstance(product.get("images"), dict):
            image_edges = product.get("images", {}).get("edges") or []
            if image_edges and isinstance(image_edges[0], dict):
                image_url = str(image_edges[0].get("node", {}).get("url", "") or "").strip()

        # 5. Backward-compat flat key — must also handle dict objects.
        if not image_url:
            raw = product.get("image_url") or ""
            if isinstance(raw, dict):
                image_url = str(raw.get("src") or raw.get("url") or "").strip()
            else:
                image_url = str(raw).strip()

        # STRICT GUARD: if the final string starts with { it is a stringified dict.
        if image_url.startswith("{"):
            image_url = DEFAULT_PRODUCT_IMAGE_URL

        return image_url or DEFAULT_PRODUCT_IMAGE_URL

    def _extract_variant_id(self, product: dict[str, Any]) -> str | None:
        """Extract numeric variant_id from the FIRST item in the variants array.

        GoKwik requires the VARIANT id (not product id) for cart permalinks.
        """
        variants = product.get("variants")
        if not isinstance(variants, list) or len(variants) == 0:
            return None
        first = variants[0]
        if not isinstance(first, dict):
            return None
        vid = first.get("id")
        if vid is None:
            return None
        # Ensure we return a clean string representation of the numeric id.
        return str(vid).strip() or None

    def _normalize_variant(self, variant: dict[str, Any], fallback_id: Any, image_url: str | None = None) -> dict[str, Any]:
        return {
            "id": variant.get("id"),
            "sku": variant.get("sku") or str(fallback_id),
            "price": variant.get("price") or 0.0,
            "image_url": image_url,
        }

    def _rank_products(self, *, query: str, products: list[dict[str, Any]], currency: str) -> tuple[list[dict[str, Any]], int]:
        tokens = self._query_tokens(query)
        scored: list[tuple[int, dict[str, Any]]] = []

        for product in products:
            score = self._score_product(query=query, tokens=tokens, product=product)
            if score <= 0:
                continue
            scored.append((score, product))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, product in scored[: settings.catalog_search_result_limit]:
            variants = product.get("variants") or []
            first_variant = variants[0] if variants else {}
            title = str(product.get("title") or product.get("name") or "Unknown Product")
            handle = str(product.get("handle") or "").strip()
            if not handle and title:
                handle = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            image_url = self._extract_product_image_url(product)
            if image_url == DEFAULT_PRODUCT_IMAGE_URL and isinstance(first_variant, dict):
                variant_image_url = str(first_variant.get("image_url") or "").strip()
                if variant_image_url:
                    image_url = variant_image_url
            storefront_domain = self._storefront_domain()
            product_url = f"https://{storefront_domain}/products/{handle}" if storefront_domain and handle else None
            body_no_html = re.sub(r"<[^>]+>", " ", str(product.get("body_html", ""))).strip()
            results.append(
                {
                    "product_id": product.get("id"),
                    "variant_id": first_variant.get("id"),
                    "handle": handle or None,
                    "url": product_url,
                    "product_url": product_url,
                    "image_url": image_url,
                    "title": title,
                    "sku": first_variant.get("sku") or str(product.get("id")),
                    "name": title,
                    "price": float(first_variant.get("price") or 0.0),
                    "currency": currency,
                    "description": " ".join(body_no_html.split())[:240],
                    "relevance": score,
                }
            )

        return results, len(scored)

    def _fetch_all_shopify_products(self) -> list[dict[str, Any]]:
        products: list[dict[str, Any]] = []
        since_id = 0

        while True:
            params: dict[str, Any] = {
                "limit": 250,
                "status": "active",
            }
            if since_id > 0:
                params["since_id"] = since_id

            response = self._request("GET", "/products.json", params=params)
            batch = response.get("products", [])
            if not batch:
                break

            products.extend(batch)
            last_id = batch[-1].get("id")
            try:
                since_id = int(last_id)
            except Exception:
                break

            if len(batch) < 250:
                break

        return products

    def _fetch_public_storefront_products(self) -> list[dict[str, Any]]:
        """Fetch products from public storefront JSON endpoint when Admin API is unavailable."""
        candidate_domains = []
        primary = self._storefront_domain()
        if primary:
            candidate_domains.append(primary)
        # Known SATMI storefront fallback.
        if "uismgu-m5.myshopify.com" not in candidate_domains:
            candidate_domains.append("uismgu-m5.myshopify.com")

        for domain in candidate_domains:
            url = f"https://{domain}/products.json"
            try:
                with httpx.Client(timeout=settings.shopify_timeout_seconds) as client:
                    response = client.get(url, params={"limit": 250})
                if response.status_code != 200:
                    continue
                body = response.json()
                products = body.get("products")
                if isinstance(products, list) and products:
                    return products
            except Exception:
                continue

        return []

    def _cache_ready_shopify_products(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cache_rows: list[dict[str, Any]] = []
        for product in products:
            variants = product.get("variants") or []
            image_url = self._extract_product_image_url(product)
            normalized_variants = [self._normalize_variant(variant, product.get("id"), image_url=image_url) for variant in variants]
            cache_rows.append(
                {
                    "id": product.get("id"),
                    "title": product.get("title", "Unknown Product"),
                    "handle": product.get("handle"),
                    "body_html": product.get("body_html", ""),
                    "product_type": product.get("product_type", ""),
                    "tags": product.get("tags", ""),
                    "vendor": product.get("vendor", ""),
                    "status": product.get("status", "active"),
                    "image_url": image_url,
                    "variants": normalized_variants,
                    "searchable_text": self._searchable_product_text(product),
                    "updated_at": product.get("updated_at"),
                }
            )
        return cache_rows

    def shopify_health(self) -> dict[str, Any]:
        if not self.shopify_enabled:
            return {
                "configured": False,
                "reachable": False,
            }
        try:
            response = self._request("GET", "/shop.json")
            shop = response.get("shop", {})
            return {
                "configured": True,
                "reachable": True,
                "shop_name": shop.get("name"),
                "currency": shop.get("currency"),
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "error": str(exc),
            }

    def get_customer_orders(self, customer_id: str) -> dict:
        if self.shopify_enabled:
            try:
                response = self._request(
                    "GET",
                    f"/customers/{customer_id}/orders.json",
                    params={"status": "any", "limit": 5},
                )
                orders = [
                    {
                        "order_id": str(order.get("name") or order.get("id")),
                        "status": order.get("financial_status") or order.get("fulfillment_status") or "unknown",
                        "total": float(order.get("current_total_price") or order.get("total_price") or 0.0),
                    }
                    for order in response.get("orders", [])
                ]
                return {"customer_id": customer_id, "orders": orders, "source": "shopify"}
            except Exception:
                # Graceful fallback keeps support flows usable even when Shopify is unavailable.
                pass

        return {
            "customer_id": customer_id,
            "orders": [
                {"order_id": "SAT-1001", "status": "processing", "total": 149.99},
                {"order_id": "SAT-1002", "status": "delivered", "total": 49.50},
            ],
            "source": "stub_fallback" if self.shopify_enabled else "stub",
        }

    def search_products(self, query: str) -> dict:
        """Search the catalog and return up to the configured result limit without synthetic padding."""
        currency = self._shop_currency()
        source = "shopify_top8"
        clean_query = " ".join((query or "").split()).strip()
        query_tokens = self._query_tokens(clean_query)
        material_hints = self._extract_material_hints(clean_query)
        generic_discovery = len(query_tokens) == 0 or clean_query.lower() in {
            "product",
            "products",
            "satmi",
            "best seller",
            "best sellers",
        }

        # --- Fetch products from best available source ---
        products: list[dict[str, Any]] = []
        try:
            products = self._fetch_all_shopify_products() if self.shopify_enabled else self._fetch_public_storefront_products()
        except Exception:
            products = []

        if not products:
            try:
                products = self._fetch_public_storefront_products()
                source = "storefront_top8"
            except Exception:
                products = []

        if not products:
            try:
                products = persistence_service.list_product_catalog(limit=max(8, settings.catalog_search_result_limit))
                if products:
                    source = "catalog_cache"
            except Exception:
                products = []

        if not products:
            return {
                "query": query,
                "results": [],
                "source": "catalog_unavailable",
                "error": "Catalog unavailable",
                "catalog_size": 0,
                "matched_count": 0,
            }

        # --- Material hard-filter ---
        candidate_products = products
        if material_hints:
            filtered_by_material = [item for item in products if self._matches_material_hints(item, material_hints)]
            candidate_products = filtered_by_material
            source = f"{source}_material_filtered"

        # --- Rank & score ---
        ranked_results, matched_count = self._rank_products(query=clean_query or query, products=candidate_products, currency=currency)

        # --- Build final list from actual catalog matches only ---
        normalized_results: list[dict[str, Any]] = []
        storefront_domain = self._storefront_domain()

        if generic_discovery:
            source_products = ranked_results if ranked_results else candidate_products[: settings.catalog_search_result_limit]
        else:
            source_products = ranked_results
        for item in source_products[: settings.catalog_search_result_limit]:
            # Title
            title = str(item.get("title") or item.get("name") or "SATMI Product").strip() or "SATMI Product"

            # Handle
            handle = str(item.get("handle") or "").strip()
            if not handle and title:
                handle = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

            # Variant ID — CRITICAL for GoKwik cart permalinks
            variant_id: str | None = None
            if "variant_id" in item and item["variant_id"] is not None:
                variant_id = str(item["variant_id"]).strip() or None
            if not variant_id:
                variant_id = self._extract_variant_id(item)

            # Price
            price_raw = item.get("price")
            if price_raw is None:
                variants = item.get("variants")
                if isinstance(variants, list) and len(variants) > 0:
                    fv = variants[0]
                    if isinstance(fv, dict):
                        price_raw = fv.get("price")
            try:
                numeric_price = float(price_raw or 0.0)
            except (TypeError, ValueError):
                numeric_price = 0.0

            # Image — robust chain with dict-safety guard
            raw_image = item.get("image_url") or item.get("image") or ""
            # If Shopify sent a dict object instead of a URL string, extract the key.
            if isinstance(raw_image, dict):
                image_url = str(raw_image.get("src") or raw_image.get("url") or "").strip()
            else:
                image_url = str(raw_image).strip()
            if not image_url or image_url == DEFAULT_PRODUCT_IMAGE_URL:
                image_url = self._extract_product_image_url(item)
            if isinstance(image_url, str) and image_url.startswith("//"):
                image_url = f"https:{image_url}"
            # Final guard: never let a stringified dict leak through.
            if image_url.startswith("{"):
                image_url = DEFAULT_PRODUCT_IMAGE_URL

            # URLs
            product_url = f"https://{storefront_domain}/products/{handle}" if storefront_domain and handle else None
            cart_url = None
            if variant_id and storefront_domain:
                cart_url = f"https://{storefront_domain}/cart/{variant_id}:1"

            normalized_results.append(
                {
                    "id": str(item.get("product_id") or item.get("id") or ""),
                    "product_id": str(item.get("product_id") or item.get("id") or ""),
                    "variant_id": variant_id,
                    "title": title,
                    "price": numeric_price,
                    "currency": str(item.get("currency") or currency),
                    "handle": handle or None,
                    "image": image_url or DEFAULT_PRODUCT_IMAGE_URL,
                    "image_url": image_url or DEFAULT_PRODUCT_IMAGE_URL,
                    "product_url": product_url,
                    "url": product_url,
                    "cart_url": cart_url,
                    "relevance": item.get("relevance"),
                }
            )

        return {
            "query": query,
            "results": normalized_results,
            "source": source,
            "catalog_size": len(candidate_products),
            "matched_count": len(normalized_results),
        }

    def create_draft_order(self, variant_id: str, customer_email: str, quantity: int = 1) -> dict[str, Any]:
        if not self.shopify_enabled:
            raise RuntimeError("Shopify is not configured for draft order creation.")

        cleaned_variant_id = str(variant_id).strip()
        if not cleaned_variant_id:
            raise RuntimeError("variant_id is required to create a draft order.")

        safe_quantity = max(1, int(quantity or 1))
        line_item_variant_id: int | str = int(cleaned_variant_id) if cleaned_variant_id.isdigit() else cleaned_variant_id

        payload: dict[str, Any] = {
            "draft_order": {
                "line_items": [
                    {
                        "variant_id": line_item_variant_id,
                        "quantity": safe_quantity,
                    }
                ],
                "note": "Order placed via SATMI AI Chatbot (COD)",
                "tags": "chatbot, COD",
            }
        }
        if customer_email:
            payload["draft_order"]["email"] = customer_email

        response = self._request("POST", self._draft_orders_endpoint_url(), json=payload)
        draft_order = response.get("draft_order", {})
        if not draft_order:
            raise RuntimeError("Shopify draft order creation returned an empty payload.")

        return {
            "draft_order_id": draft_order.get("id"),
            "draft_order_name": draft_order.get("name"),
            "invoice_url": draft_order.get("invoice_url"),
            "currency": draft_order.get("currency"),
            "total_price": float(draft_order.get("total_price") or 0.0),
        }

    def cancel_order(self, order_id: str, reason: str) -> dict:
        if self.shopify_enabled:
            order = self._find_order_by_reference(order_id)
            shopify_order_id = order.get("id")
            if not shopify_order_id:
                raise RuntimeError("Matched Shopify order has no id.")

            response = self._request(
                "POST",
                f"/orders/{shopify_order_id}/cancel.json",
                json={"reason": "customer", "email": True, "restock": True},
            )
            cancelled_order = response.get("order", {})
            return {
                "order_id": cancelled_order.get("name") or order_id,
                "cancelled": bool(cancelled_order),
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "shopify",
            }

        return {
            "order_id": order_id,
            "cancelled": True,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "stub",
        }

    def process_cancel_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_id = str(payload.get("order_id", ""))
        reason = str(payload.get("reason", "Queued cancellation request"))
        if not order_id:
            raise RuntimeError("Queued cancellation payload missing order_id")
        return self.cancel_order(order_id=order_id, reason=reason)

    def handoff_to_human(self, ticket: HandoffTicket) -> dict:
        handoff_id = f"HND-{uuid4().hex[:8].upper()}"
        return {
            "handoff_id": handoff_id,
            "queue": "satmi-tier-1-manual-support",
            "eta_minutes": 15,
            "ticket": ticket.model_dump(),
        }


tooling_service = ToolingService()
