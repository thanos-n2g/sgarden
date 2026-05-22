import sys
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock, ANY

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from security.jwt_handler import get_current_user  # noqa: E402

FAKE_USER = {"_id": str(ObjectId()), "username": "admin", "role": "admin"}

PRODUCT_ID = ObjectId()
INITIAL_STOCK = 100
FAKE_PRODUCT = {
    "_id": PRODUCT_ID,
    "name": "Test Product",
    "description": "A product",
    "category": "Electronics",
    "price": 25.0,
    "stock": INITIAL_STOCK,
    "createdAt": datetime.utcnow(),
    "updatedAt": datetime.utcnow(),
}


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def make_products_mock(product=None, update_matched=1):
    mock = MagicMock()
    _product = product if product is not None else FAKE_PRODUCT

    update_result = MagicMock()
    update_result.matched_count = update_matched
    mock.update_one = AsyncMock(return_value=update_result)

    insert_result = MagicMock()
    insert_result.inserted_id = ObjectId()
    mock.insert_one = AsyncMock(return_value=insert_result)

    mock.find_one = AsyncMock(return_value=_product)
    mock.find = MagicMock(side_effect=lambda *a, **kw: _AsyncIter([_product]))
    mock.count_documents = AsyncMock(return_value=1)
    return mock


def make_orders_mock():
    mock = MagicMock()
    insert_result = MagicMock()
    insert_result.inserted_id = ObjectId()
    mock.insert_one = AsyncMock(return_value=insert_result)
    mock.find = MagicMock(side_effect=lambda *a, **kw: _AsyncIter([]))
    return mock


# ─── GET /api/products/:id includes stock field ───────────────────────────────

async def test_get_product_includes_stock_field_as_number():
    products_mock = make_products_mock()
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", products_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/api/products/{PRODUCT_ID}")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "stock" in data
    assert isinstance(data["stock"], int)


# ─── PATCH /api/products/:id/stock ───────────────────────────────────────────

async def test_patch_stock_updates_to_75():
    updated_product = {**FAKE_PRODUCT, "stock": 75}
    products_mock = make_products_mock(product=updated_product)
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", products_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch(f"/api/products/{PRODUCT_ID}/stock", json={"stock": 75})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["stock"] == 75


async def test_patch_stock_negative_value_returns_400():
    products_mock = make_products_mock()
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", products_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch(f"/api/products/{PRODUCT_ID}/stock", json={"stock": -10})
    app.dependency_overrides.clear()

    assert response.status_code == 400


async def test_patch_stock_without_auth_returns_401_or_403():
    products_mock = make_products_mock()
    with (
        patch("routes.products.products_collection", products_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch(f"/api/products/{PRODUCT_ID}/stock", json={"stock": 75})

    assert response.status_code in (401, 403)


# ─── POST /api/products with stock ───────────────────────────────────────────

async def test_create_product_with_stock_sets_correctly():
    created_product = {
        "_id": ObjectId(),
        "name": "Stocked Item",
        "description": None,
        "category": "Electronics",
        "price": 10.0,
        "stock": 50,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    products_mock = make_products_mock(product=created_product)
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", products_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/products",
                json={"name": "Stocked Item", "price": 10.0, "category": "Electronics", "stock": 50},
            )
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["stock"] == 50


# ─── POST /api/orders stock reduction ────────────────────────────────────────

async def test_order_reduces_product_stock():
    order_quantity = 3
    products_mock = make_products_mock()
    orders_mock = make_orders_mock()

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.products_collection", products_mock),
        patch("routes.orders.orders_collection", orders_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/orders",
                json={"items": [{"productId": str(PRODUCT_ID), "quantity": order_quantity}]},
            )
    app.dependency_overrides.clear()

    assert response.status_code == 201
    products_mock.update_one.assert_called_once_with(
        {"_id": ObjectId(str(PRODUCT_ID))},
        {"$inc": {"stock": -order_quantity}, "$set": {"updatedAt": ANY}},
    )


async def test_order_with_insufficient_stock_returns_400():
    low_stock_product = {**FAKE_PRODUCT, "stock": 2}
    products_mock = make_products_mock(product=low_stock_product)
    orders_mock = make_orders_mock()

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.products_collection", products_mock),
        patch("routes.orders.orders_collection", orders_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/orders",
                json={"items": [{"productId": str(PRODUCT_ID), "quantity": 5}]},
            )
    app.dependency_overrides.clear()

    assert response.status_code == 400


async def test_stock_unchanged_when_order_rejected_due_to_insufficient_stock():
    low_stock_product = {**FAKE_PRODUCT, "stock": 2}
    products_mock = make_products_mock(product=low_stock_product)
    orders_mock = make_orders_mock()

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.products_collection", products_mock),
        patch("routes.orders.orders_collection", orders_mock),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/orders",
                json={"items": [{"productId": str(PRODUCT_ID), "quantity": 5}]},
            )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    products_mock.update_one.assert_not_called()
