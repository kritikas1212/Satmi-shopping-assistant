from __future__ import annotations

from datetime import datetime, timedelta, timezone

from satmi_agent.tools import ToolingService


def _product(pid: int, title: str) -> dict:
    return {
        "id": pid,
        "title": title,
        "body_html": f"<p>{title} description</p>",
        "product_type": "Mala",
        "tags": "spiritual,beads",
        "vendor": "SATMI",
        "status": "active",
        "variants": [{"id": pid * 10, "sku": f"SKU-{pid}", "price": "999.0"}],
    }


def test_search_products_uses_fresh_db_cache(monkeypatch):
    service = ToolingService()

    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.get_catalog_cache_snapshot",
        lambda: {"product_count": 2, "latest_sync_at": datetime.now(timezone.utc)},
    )
    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.list_product_catalog",
        lambda limit=None: [_product(1, "Karungali Mala"), _product(2, "Rudraksha Mala")],
    )

    result = service.search_products("karungali mala")

    assert result["source"] == "shopify_top8_material_filtered"
    assert result["catalog_size"] == 2
    assert result["matched_count"] >= 1
    assert result["results"][0]["name"] == "Karungali Mala"


def test_search_products_syncs_shopify_when_cache_stale(monkeypatch):
    service = ToolingService()
    service._admin_store_domain = "example.myshopify.com"
    service._token = "token"

    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.get_catalog_cache_snapshot",
        lambda: {"product_count": 1, "latest_sync_at": datetime.now(timezone.utc) - timedelta(hours=2)},
    )
    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.list_product_catalog",
        lambda limit=None: [_product(3, "Old Cached Mala")],
    )

    upsert_calls: list[int] = []
    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.upsert_product_catalog",
        lambda rows: upsert_calls.append(len(rows)) or len(rows),
    )
    monkeypatch.setattr(service, "_fetch_all_shopify_products", lambda: [_product(10, "Karungali Elite Mala")])

    result = service.search_products("karungali")

    assert result["source"] == "shopify_top8_material_filtered"
    assert result["catalog_size"] == 1
    assert upsert_calls == [1]


def test_search_products_uses_stale_cache_when_shopify_fails(monkeypatch):
    service = ToolingService()
    service._admin_store_domain = "example.myshopify.com"
    service._token = "token"

    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.get_catalog_cache_snapshot",
        lambda: {"product_count": 2, "latest_sync_at": datetime.now(timezone.utc) - timedelta(hours=3)},
    )
    monkeypatch.setattr(
        "satmi_agent.tools.persistence_service.list_product_catalog",
        lambda limit=None: [_product(1, "Karungali Mala"), _product(2, "Rudraksha Mala")],
    )
    monkeypatch.setattr(service, "_fetch_all_shopify_products", lambda: (_ for _ in ()).throw(RuntimeError("shopify down")))

    result = service.search_products("rudraksha")

    assert result["source"] == "storefront_top8_material_filtered"
    assert result["catalog_size"] == 2
    assert result["matched_count"] >= 1
