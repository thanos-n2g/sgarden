import sys
import os
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from security.jwt_handler import get_current_user  # noqa: E402

FAKE_USER = {"_id": str(ObjectId()), "username": "admin", "role": "admin"}

PRODUCT_ID = ObjectId()
PRODUCT_PRICE = 25.0
FAKE_PRODUCT = {
    "_id": PRODUCT_ID,
    "name": "Test Product",
    "price": PRODUCT_PRICE,
    "stock": 100,
}

ORDER_ID = ObjectId()
ORDER_ITEMS = [{"productId": str(PRODUCT_ID), "quantity": 2}]
ORDER_TOTAL = PRODUCT_PRICE * 2  # 50.0
FAKE_ORDER = {
    "_id": ORDER_ID,
    "items": ORDER_ITEMS,
    "total": ORDER_TOTAL,
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


def make_products_mock():
    mock = MagicMock()
    mock.find_one = AsyncMock(return_value=FAKE_PRODUCT)
    return mock


def make_orders_mock(order=None, orders=None, update_matched=1, delete_count=1):
    mock = MagicMock()
    _order = order if order is not None else FAKE_ORDER
    _orders = orders if orders is not None else [_order]

    insert_result = MagicMock()
    insert_result.inserted_id = ObjectId()
    mock.insert_one = AsyncMock(return_value=insert_result)

    update_result = MagicMock()
    update_result.matched_count = update_matched
    mock.update_one = AsyncMock(return_value=update_result)

    delete_result = MagicMock()
    delete_result.deleted_count = delete_count
    mock.delete_one = AsyncMock(return_value=delete_result)

    mock.find_one = AsyncMock(return_value=_order)
    mock.find = MagicMock(side_effect=lambda *a, **kw: _AsyncIter(list(_orders)))

    return mock


_COMMON_PATCHES = {
    "database.init_indexes": AsyncMock(),
    "seed.seed_data": AsyncMock(),
}


@pytest.fixture
async def client():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.orders_collection", make_orders_mock()),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


# ─── POST /api/orders ─────────────────────────────────────────────────────────

async def test_create_order_returns_201_with_id_and_items(client):
    response = await client.post(
        "/api/orders",
        json={"items": [{"productId": str(PRODUCT_ID), "quantity": 2}]},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "items" in data
    assert len(data["items"]) == 1


async def test_create_order_total_equals_price_times_quantity(client):
    quantity = 3
    response = await client.post(
        "/api/orders",
        json={"items": [{"productId": str(PRODUCT_ID), "quantity": quantity}]},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["total"] == PRODUCT_PRICE * quantity


# ─── GET /api/orders ──────────────────────────────────────────────────────────

async def test_list_orders_returns_200_with_array(client):
    response = await client.get("/api/orders")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


# ─── GET /api/orders/:id ──────────────────────────────────────────────────────

async def test_get_order_by_id_returns_matching_order(client):
    response = await client.get(f"/api/orders/{ORDER_ID}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(ORDER_ID)
    assert data["items"] == ORDER_ITEMS
    assert data["total"] == ORDER_TOTAL


# ─── PUT /api/orders/:id ──────────────────────────────────────────────────────

async def test_update_order_recalculates_total():
    new_quantity = 5
    expected_total = PRODUCT_PRICE * new_quantity
    updated_order = {
        **FAKE_ORDER,
        "items": [{"productId": str(PRODUCT_ID), "quantity": new_quantity}],
        "total": expected_total,
    }

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.orders_collection", make_orders_mock(order=updated_order)),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.put(
                f"/api/orders/{ORDER_ID}",
                json={"items": [{"productId": str(PRODUCT_ID), "quantity": new_quantity}]},
            )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == expected_total


# ─── DELETE /api/orders/:id ───────────────────────────────────────────────────

async def test_delete_order_returns_200_and_subsequent_get_returns_404():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER

    with (
        patch("routes.orders.orders_collection", make_orders_mock()),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            delete_response = await ac.delete(f"/api/orders/{ORDER_ID}")

    assert delete_response.status_code == 200

    not_found_mock = make_orders_mock()
    not_found_mock.find_one = AsyncMock(return_value=None)

    with (
        patch("routes.orders.orders_collection", not_found_mock),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            get_response = await ac.get(f"/api/orders/{ORDER_ID}")

    app.dependency_overrides.clear()

    assert get_response.status_code == 404


# ─── 404 for non-existent order ───────────────────────────────────────────────

async def test_get_nonexistent_order_returns_404():
    not_found_mock = make_orders_mock()
    not_found_mock.find_one = AsyncMock(return_value=None)

    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.orders.orders_collection", not_found_mock),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/orders/000000000000000000000000")
    app.dependency_overrides.clear()

    assert response.status_code == 404


# ─── Authentication ───────────────────────────────────────────────────────────

async def test_create_order_without_auth_returns_401_or_403():
    with (
        patch("routes.orders.orders_collection", make_orders_mock()),
        patch("routes.orders.products_collection", make_products_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/orders",
                json={"items": [{"productId": str(PRODUCT_ID), "quantity": 1}]},
            )

    assert response.status_code in (401, 403)
