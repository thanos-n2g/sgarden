import sys
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402


# ─── Test data (reused from test_search_endpoint) ────────────────────────────

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
    _product("Wireless Mouse",     "Ergonomic wireless mouse with USB receiver",     "Electronics", 29.99, 150),
    _product("Mechanical Keyboard","RGB mechanical keyboard with Cherry MX switches","Electronics", 89.99,  75),
    _product("USB-C Hub",          "7-in-1 USB-C hub with HDMI and Ethernet",        "Electronics", 45.99, 200),
    _product("Monitor Stand",      "Adjustable monitor stand with USB ports",         "Accessories", 34.99, 120),
    _product("Webcam HD",          "1080p HD webcam with built-in microphone",        "Electronics", 59.99,  90),
    _product("Desk Lamp",          "LED desk lamp with adjustable brightness",        "Accessories", 24.99, 180),
    _product("Cable Organizer",    "Silicone cable management clips, pack of 10",    "Accessories",  9.99, 500),
    _product("Laptop Sleeve",      "Neoprene laptop sleeve for 15-inch laptops",     "Accessories", 19.99, 250),
    _product("External SSD",       "1TB portable external SSD, USB 3.2",             "Storage",     79.99,  60),
    _product("USB Flash Drive",    "64GB USB 3.0 flash drive",                       "Storage",     12.99, 400),
    _product("Ethernet Cable",     "Cat6 ethernet cable, 10 meters",                 "Networking",   8.99, 300),
    _product("Wi-Fi Router",       "Dual-band Wi-Fi 6 router",                       "Networking", 129.99,  45),
    _product("Mouse Pad XL",       "Extended gaming mouse pad, 900x400mm",           "Accessories", 15.99, 200),
    _product("Headphone Stand",    "Aluminum headphone stand",                       "Accessories", 22.99, 100),
    _product("Power Strip",        "6-outlet power strip with USB charging",         "Electronics", 18.99, 350),
]


# ─── In-memory async cursor ───────────────────────────────────────────────────

class _AsyncCursor:
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
    mock.find.side_effect = lambda f=None: _AsyncCursor(PRODUCTS)
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

async def test_stats_returns_200_with_positive_total_count(client):
    response = await client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["totalCount"], int)
    assert data["totalCount"] > 0


async def test_stats_returns_positive_average_price(client):
    response = await client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["averagePrice"], (int, float))
    assert data["averagePrice"] > 0


async def test_stats_min_price_lte_max_price(client):
    response = await client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert "minPrice" in data
    assert "maxPrice" in data
    assert data["maxPrice"] >= data["minPrice"]


async def test_stats_category_count_is_object_with_keys(client):
    response = await client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["categoryCount"], dict)
    assert len(data["categoryCount"]) > 0


async def test_stats_category_counts_sum_equals_total_count(client):
    response = await client.get("/api/products/stats")

    assert response.status_code == 200
    data = response.json()
    assert sum(data["categoryCount"].values()) == data["totalCount"]
