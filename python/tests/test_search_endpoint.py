import sys
import os
import re
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402  (import after sys.path patch)


# ─── Test data ───────────────────────────────────────────────────────────────

def _product(name, description, category, price, stock=0):
    return {
        "_id": ObjectId(),
        "name": name,
        "description": description,
        "category": category,
        "price": price,
        "stock": stock,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }


PRODUCTS = [
    _product("Wireless Mouse",    "Ergonomic wireless mouse with USB receiver",    "Electronics", 29.99, 150),
    _product("Mechanical Keyboard","RGB mechanical keyboard with Cherry MX switches","Electronics", 89.99,  75),
    _product("USB-C Hub",          "7-in-1 USB-C hub with HDMI and Ethernet",       "Electronics", 45.99, 200),
    _product("Monitor Stand",      "Adjustable monitor stand with USB ports",        "Accessories", 34.99, 120),
    _product("Webcam HD",          "1080p HD webcam with built-in microphone",       "Electronics", 59.99,  90),
    _product("Desk Lamp",          "LED desk lamp with adjustable brightness",       "Accessories", 24.99, 180),
    _product("Cable Organizer",    "Silicone cable management clips, pack of 10",   "Accessories",  9.99, 500),
    _product("Laptop Sleeve",      "Neoprene laptop sleeve for 15-inch laptops",    "Accessories", 19.99, 250),
    _product("External SSD",       "1TB portable external SSD, USB 3.2",            "Storage",     79.99,  60),
    _product("USB Flash Drive",    "64GB USB 3.0 flash drive",                      "Storage",     12.99, 400),
    _product("Ethernet Cable",     "Cat6 ethernet cable, 10 meters",                "Networking",   8.99, 300),
    _product("Wi-Fi Router",       "Dual-band Wi-Fi 6 router",                      "Networking", 129.99,  45),
    _product("Mouse Pad XL",       "Extended gaming mouse pad, 900x400mm",          "Accessories", 15.99, 200),
    _product("Headphone Stand",    "Aluminum headphone stand",                      "Accessories", 22.99, 100),
    _product("Power Strip",        "6-outlet power strip with USB charging",        "Electronics", 18.99, 350),
]


# ─── In-memory MongoDB filter simulation ─────────────────────────────────────

def _field_matches(product: dict, key: str, val) -> bool:
    field_val = product.get(key) or ""
    if isinstance(val, re.Pattern):
        return bool(val.search(str(field_val)))
    return field_val == val


def _apply_filter(products: list, mongo_filter: dict) -> list:
    def matches(p: dict) -> bool:
        for key, val in (mongo_filter or {}).items():
            if key == "$or":
                if not any(
                    all(_field_matches(p, k, v) for k, v in cond.items())
                    for cond in val
                ):
                    return False
            elif key == "price":
                price = p.get("price", 0)
                if "$gte" in val and price < val["$gte"]:
                    return False
                if "$lte" in val and price > val["$lte"]:
                    return False
            else:
                if not _field_matches(p, key, val):
                    return False
        return True

    return [p for p in products if matches(p)]


class _AsyncCursor:
    """Async iterator that wraps a plain list, standing in for a Motor cursor."""

    def __init__(self, items: list):
        self._items = items
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def _make_collection_mock() -> MagicMock:
    mock = MagicMock()
    mock.find.side_effect = lambda f=None: _AsyncCursor(_apply_filter(PRODUCTS, f or {}))
    return mock


# ─── Shared fixture ───────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """HTTP test client with MongoDB collection and startup hooks mocked out."""
    with (
        patch("routes.products.products_collection", _make_collection_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


# ─── Tests ───────────────────────────────────────────────────────────────────

async def test_text_search_returns_products_with_query_in_name_or_description(client):
    response = await client.get("/api/products/search?q=mouse")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for product in data:
        combined = (product["name"] + " " + (product["description"] or "")).lower()
        assert "mouse" in combined, f"'mouse' not found in product: {product['name']!r}"


async def test_category_filter_returns_only_matching_category(client):
    response = await client.get("/api/products/search?category=Electronics")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(p["category"] == "Electronics" for p in data)


async def test_min_price_filter_returns_products_above_floor(client):
    response = await client.get("/api/products/search?minPrice=50")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(p["price"] >= 50 for p in data), (
        f"Found product below minPrice=50: {[p for p in data if p['price'] < 50]}"
    )


async def test_max_price_filter_returns_products_below_ceiling(client):
    response = await client.get("/api/products/search?maxPrice=20")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(p["price"] <= 20 for p in data), (
        f"Found product above maxPrice=20: {[p for p in data if p['price'] > 20]}"
    )


async def test_combined_text_and_price_range_filter(client):
    response = await client.get("/api/products/search?q=USB&minPrice=10&maxPrice=50")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for product in data:
        combined = (product["name"] + " " + (product["description"] or "")).lower()
        assert "usb" in combined, f"'USB' not found in: {product['name']!r}"
        assert 10 <= product["price"] <= 50, (
            f"Price {product['price']} out of [10, 50] for {product['name']!r}"
        )


async def test_search_with_no_matches_returns_empty_array(client):
    response = await client.get("/api/products/search?q=nonexistentxyz")

    assert response.status_code == 200
    assert response.json() == []
