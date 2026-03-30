from __future__ import annotations

from datetime import datetime
import time
from typing import Any
from uuid import uuid4

import httpx

from satmi_agent.config import settings
from satmi_agent.observability import record_shopify_error
from satmi_agent.schemas import HandoffTicket
from satmi_agent.tracing import get_tracer


class ToolingService:
    """Shopify-backed tooling with local fallback when credentials are not configured."""

    def __init__(self) -> None:
        self._store_domain = settings.shopify_store_domain
        self._token = settings.shopify_admin_api_token
        self._api_version = settings.shopify_api_version

    @property
    def shopify_enabled(self) -> bool:
        return bool(self._store_domain and self._token)

    def _shopify_headers(self) -> dict[str, str]:
        if not self._token:
            raise RuntimeError("Shopify Admin API token is not configured.")
        return {
            "X-Shopify-Access-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _shopify_url(self, path: str) -> str:
        if not self._store_domain:
            raise RuntimeError("Shopify store domain is not configured.")
        safe_path = path if path.startswith("/") else f"/{path}"
        return f"https://{self._store_domain}/admin/api/{self._api_version}{safe_path}"

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

    def get_customer_orders(self, customer_id: str) -> dict:
        if self.shopify_enabled:
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

        return {
            "customer_id": customer_id,
            "orders": [
                {"order_id": "SAT-1001", "status": "processing", "total": 149.99},
                {"order_id": "SAT-1002", "status": "delivered", "total": 49.50},
            ],
            "source": "stub",
        }

    def search_products(self, query: str) -> dict:
        if self.shopify_enabled:
            response = self._request(
                "GET",
                "/products.json",
                params={"limit": 5, "title": query},
            )
            results = []
            for product in response.get("products", []):
                variants = product.get("variants") or []
                first_variant = variants[0] if variants else {}
                results.append(
                    {
                        "sku": first_variant.get("sku") or str(product.get("id")),
                        "name": product.get("title", "Unknown Product"),
                        "price": float(first_variant.get("price") or 0.0),
                    }
                )
            return {"query": query, "results": results, "source": "shopify"}

        return {
            "query": query,
            "results": [
                {"sku": "SHOE-RED-42", "name": "Red Runner Shoes", "price": 89.99},
                {"sku": "SHOE-BLK-42", "name": "Black Trainer Shoes", "price": 95.00},
            ],
            "source": "stub",
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
