import sys
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402


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
    _product("Wireless Mouse",      "Ergonomic wireless mouse with USB receiver",     "Electronics", 29.99, 150),
    _product("Mechanical Keyboard", "RGB mechanical keyboard with Cherry MX switches","Electronics", 89.99,  75),
    _product("USB-C Hub",           "7-in-1 USB-C hub with HDMI and Ethernet",        "Electronics", 45.99, 200),
    _product("Monitor Stand",       "Adjustable monitor stand with USB ports",         "Accessories", 34.99, 120),
    _product("Webcam HD",           "1080p HD webcam with built-in microphone",        "Electronics", 59.99,  90),
    _product("Desk Lamp",           "LED desk lamp with adjustable brightness",        "Accessories", 24.99, 180),
    _product("Cable Organizer",     "Silicone cable management clips, pack of 10",    "Accessories",  9.99, 500),
    _product("Laptop Sleeve",       "Neoprene laptop sleeve for 15-inch laptops",     "Accessories", 19.99, 250),
    _product("External SSD",        "1TB portable external SSD, USB 3.2",             "Storage",     79.99,  60),
    _product("USB Flash Drive",     "64GB USB 3.0 flash drive",                       "Storage",     12.99, 400),
    _product("Ethernet Cable",      "Cat6 ethernet cable, 10 meters",                 "Networking",   8.99, 300),
    _product("Wi-Fi Router",        "Dual-band Wi-Fi 6 router",                       "Networking", 129.99,  45),
    _product("Mouse Pad XL",        "Extended gaming mouse pad, 900x400mm",           "Accessories", 15.99, 200),
    _product("Headphone Stand",     "Aluminum headphone stand",                       "Accessories", 22.99, 100),
    _product("Power Strip",         "6-outlet power strip with USB charging",         "Electronics", 18.99, 350),
]


# ─── Chainable in-memory cursor ───────────────────────────────────────────────

class _AsyncCursor:
    def __init__(self, items: list):
        self._items = list(items)
        self._sort_key = None
        self._sort_reverse = False
        self._skip_n = 0
        self._limit_n = None

    def sort(self, key, direction=1):
        self._sort_key = key
        self._sort_reverse = (direction == -1)
        return self

    def skip(self, n):
        self._skip_n = n
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def _resolved(self):
        items = self._items
        if self._sort_key:
            items = sorted(
                items,
                key=lambda p: (p.get(self._sort_key) if p.get(self._sort_key) is not None else ""),
                reverse=self._sort_reverse,
            )
        items = items[self._skip_n:]
        if self._limit_n:
            items = items[: self._limit_n]
        return items

    def __aiter__(self):
        self._resolved_items = self._resolved()
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._resolved_items):
            raise StopAsyncIteration
        item = self._resolved_items[self._index]
        self._index += 1
        return item


def _make_collection_mock() -> MagicMock:
    mock = MagicMock()
    mock.find.side_effect = lambda f=None: _AsyncCursor(PRODUCTS)
    mock.count_documents = AsyncMock(return_value=len(PRODUCTS))
    return mock


# ─── Fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
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

async def test_paginated_response_has_required_fields(client):
    response = await client.get("/api/products?page=1&limit=5")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data and isinstance(data["data"], list)
    assert "page" in data
    assert "limit" in data
    assert "total" in data


async def test_page1_and_page2_have_non_overlapping_ids(client):
    r1 = await client.get("/api/products?page=1&limit=5")
    r2 = await client.get("/api/products?page=2&limit=5")

    assert r1.status_code == 200
    assert r2.status_code == 200
    ids1 = {p["id"] for p in r1.json()["data"]}
    ids2 = {p["id"] for p in r2.json()["data"]}
    assert ids1.isdisjoint(ids2), f"Overlapping IDs between page 1 and page 2: {ids1 & ids2}"


async def test_sort_by_price_ascending(client):
    response = await client.get("/api/products?sort=price&order=asc&limit=15")

    assert response.status_code == 200
    prices = [p["price"] for p in response.json()["data"]]
    assert prices == sorted(prices), f"Prices not in ascending order: {prices}"


async def test_sort_by_price_descending(client):
    response = await client.get("/api/products?sort=price&order=desc&limit=15")

    assert response.status_code == 200
    prices = [p["price"] for p in response.json()["data"]]
    assert prices == sorted(prices, reverse=True), f"Prices not in descending order: {prices}"


async def test_sort_by_name_ascending(client):
    response = await client.get("/api/products?sort=name&order=asc&limit=15")

    assert response.status_code == 200
    names = [p["name"] for p in response.json()["data"]]
    assert names == sorted(names), f"Names not in lexicographic order: {names}"


async def test_total_exceeds_page_data_length_when_limit_is_small(client):
    response = await client.get("/api/products?page=1&limit=3")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["total"], int)
    assert body["total"] > len(body["data"])


async def test_out_of_range_page_returns_200_with_empty_data(client):
    response = await client.get("/api/products?page=999&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
