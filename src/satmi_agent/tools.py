from __future__ import annotations

from datetime import datetime, timezone
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

    def _normalize_variant(self, variant: dict[str, Any], fallback_id: Any) -> dict[str, Any]:
        return {
            "id": variant.get("id"),
            "sku": variant.get("sku") or str(fallback_id),
            "price": variant.get("price") or 0.0,
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
            body_no_html = re.sub(r"<[^>]+>", " ", str(product.get("body_html", ""))).strip()
            results.append(
                {
                    "product_id": product.get("id"),
                    "variant_id": first_variant.get("id"),
                    "sku": first_variant.get("sku") or str(product.get("id")),
                    "name": product.get("title", "Unknown Product"),
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

    def _cache_ready_shopify_products(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cache_rows: list[dict[str, Any]] = []
        for product in products:
            variants = product.get("variants") or []
            normalized_variants = [self._normalize_variant(variant, product.get("id")) for variant in variants]
            cache_rows.append(
                {
                    "id": product.get("id"),
                    "title": product.get("title", "Unknown Product"),
                    "body_html": product.get("body_html", ""),
                    "product_type": product.get("product_type", ""),
                    "tags": product.get("tags", ""),
                    "vendor": product.get("vendor", ""),
                    "status": product.get("status", "active"),
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
        currency = self._shop_currency()

        if settings.catalog_cache_enabled:
            try:
                snapshot = persistence_service.get_catalog_cache_snapshot()
                has_cache = int(snapshot.get("product_count") or 0) > 0
                fresh_cache = self._cache_snapshot_fresh(snapshot.get("latest_sync_at"))

                if has_cache and fresh_cache:
                    cached_products = persistence_service.list_product_catalog(limit=settings.catalog_cache_max_products)
                    results, matched_count = self._rank_products(query=query, products=cached_products, currency=currency)
                    return {
                        "query": query,
                        "results": results,
                        "source": "db_cache",
                        "catalog_size": len(cached_products),
                        "matched_count": matched_count,
                    }
            except Exception:
                # Continue with live fetch if cache read fails.
                pass

        if self.shopify_enabled:
            try:
                products = self._fetch_all_shopify_products()
                if settings.catalog_cache_enabled and products:
                    persistence_service.upsert_product_catalog(self._cache_ready_shopify_products(products))

                results, matched_count = self._rank_products(query=query, products=products, currency=currency)
                return {
                    "query": query,
                    "results": results,
                    "source": "shopify_live_sync",
                    "catalog_size": len(products),
                    "matched_count": matched_count,
                }
            except Exception:
                # Fall back to stale cache or local stub matching so product queries still resolve.
                if settings.catalog_cache_enabled:
                    try:
                        stale_cache = persistence_service.list_product_catalog(limit=settings.catalog_cache_max_products)
                        if stale_cache:
                            results, matched_count = self._rank_products(query=query, products=stale_cache, currency=currency)
                            return {
                                "query": query,
                                "results": results,
                                "source": "db_cache_stale",
                                "catalog_size": len(stale_cache),
                                "matched_count": matched_count,
                            }
                    except Exception:
                        pass

        stub_products = [
            {
                "product_id": "P-1001",
                "variant_id": "V-1001",
                "sku": "MALA-KARUNGALI-001",
                "name": "Karungali Mala",
                "price": 29.99,
                "currency": "INR",
                "description": "Traditional karungali wood mala used for daily wear and spiritual practice.",
            },
            {
                "product_id": "P-1002",
                "variant_id": "V-1002",
                "sku": "MALA-RUDRA-001",
                "name": "Rudraksha Mala",
                "price": 34.5,
                "currency": "INR",
                "description": "Classic rudraksha mala with natural beads suitable for prayer and meditation.",
            },
            {
                "product_id": "P-1003",
                "variant_id": "V-1003",
                "sku": "BRACELET-BLK-01",
                "name": "Black Bead Bracelet",
                "price": 15.0,
                "currency": "INR",
                "description": "Minimal black bead bracelet for casual everyday use.",
            },
        ]
        tokens = self._query_tokens(query)
        filtered_results: list[dict[str, Any]] = []
        for product in stub_products:
            searchable = f"{product['name']} {product['description']}".lower()
            score = sum(1 for token in tokens if token in searchable)
            if score > 0:
                filtered_results.append({**product, "relevance": score})

        filtered_results.sort(key=lambda item: item["relevance"], reverse=True)
        return {
            "query": query,
            "results": filtered_results[: settings.catalog_search_result_limit],
            "source": "stub_fallback" if self.shopify_enabled else "stub",
            "catalog_size": len(stub_products),
            "matched_count": len(filtered_results),
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

    def place_order(
        self,
        *,
        product_query: str,
        quantity: int,
        user_id: str,
        authenticated_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_quantity = max(1, int(quantity or 1))
        search = self.search_products(product_query)
        results = search.get("results", [])
        source = str(search.get("source", "unknown"))

        if not results:
            return {
                "placed": False,
                "needs_input": True,
                "message": "No close product match found.",
                "source": source,
                "quantity": safe_quantity,
                "query": product_query,
            }

        selected = results[0]

        if source == "shopify":
            variant_id = selected.get("variant_id")
            if not variant_id:
                return {
                    "placed": False,
                    "needs_input": True,
                    "message": "Matched product variant is unavailable for ordering.",
                    "source": source,
                    "selected_product": selected,
                    "quantity": safe_quantity,
                }

            draft_payload: dict[str, Any] = {
                "draft_order": {
                    "line_items": [{"variant_id": int(variant_id), "quantity": safe_quantity}],
                    "note": f"Created by SATMI chatbot for user {user_id}",
                    "tags": "satmi-chatbot",
                }
            }

            if authenticated_user and authenticated_user.get("email"):
                draft_payload["draft_order"]["email"] = authenticated_user["email"]

            response = self._request("POST", "/draft_orders.json", json=draft_payload)
            draft_order = response.get("draft_order", {})
            return {
                "placed": bool(draft_order),
                "order_mode": "draft_order",
                "draft_order_id": draft_order.get("id"),
                "draft_order_name": draft_order.get("name"),
                "invoice_url": draft_order.get("invoice_url"),
                "total_price": float(draft_order.get("total_price") or selected.get("price") or 0.0),
                "currency": str(draft_order.get("currency") or selected.get("currency") or self._shop_currency()),
                "selected_product": selected,
                "quantity": safe_quantity,
                "source": source,
            }

        # Do not fake checkout creation when the store is unavailable.
        return {
            "placed": False,
            "requires_live_store": True,
            "order_mode": "unavailable",
            "selected_product": selected,
            "quantity": safe_quantity,
            "source": source,
            "message": "Live Shopify order placement is unavailable right now.",
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
