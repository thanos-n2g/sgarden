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

EXISTING_PRODUCT_ID = ObjectId()
EXISTING_PRODUCT = {
    "_id": EXISTING_PRODUCT_ID,
    "name": "Existing Product",
    "description": None,
    "category": "Electronics",
    "price": 49.99,
    "stock": 5,
    "createdAt": datetime.utcnow(),
    "updatedAt": datetime.utcnow(),
}


def _make_collection_mock(update_matched: int = 1) -> MagicMock:
    mock = MagicMock()

    insert_result = MagicMock()
    insert_result.inserted_id = ObjectId()
    mock.insert_one = AsyncMock(return_value=insert_result)

    update_result = MagicMock()
    update_result.matched_count = update_matched
    mock.update_one = AsyncMock(return_value=update_result)

    mock.find_one = AsyncMock(return_value=EXISTING_PRODUCT if update_matched > 0 else None)

    return mock


@pytest.fixture
async def client():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", _make_collection_mock()),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def client_not_found():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with (
        patch("routes.products.products_collection", _make_collection_mock(update_matched=0)),
        patch("database.init_indexes", new=AsyncMock()),
        patch("seed.seed_data", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


# ─── POST /api/products validation ───────────────────────────────────────────

async def test_create_product_missing_name_returns_400_with_errors_name(client):
    response = await client.post("/api/products", json={"price": 10.0, "category": "Electronics"})

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert "name" in data["errors"]


async def test_create_product_negative_price_returns_400_with_errors_price(client):
    response = await client.post("/api/products", json={"name": "Widget", "price": -5.0})

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert "price" in data["errors"]


async def test_create_product_zero_price_returns_400_with_errors_price(client):
    response = await client.post("/api/products", json={"name": "Widget", "price": 0})

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert "price" in data["errors"]


async def test_create_product_invalid_category_returns_400_with_errors_category(client):
    response = await client.post("/api/products", json={"name": "Widget", "category": "Furniture"})

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert "category" in data["errors"]


async def test_create_product_valid_fields_returns_201_with_product(client):
    response = await client.post(
        "/api/products",
        json={"name": "USB-C Cable", "price": 12.99, "category": "Electronics", "stock": 100},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "USB-C Cable"


# ─── PUT /api/products/:id validation ────────────────────────────────────────

async def test_update_product_negative_price_returns_400_with_errors_price(client):
    response = await client.put(
        f"/api/products/{EXISTING_PRODUCT_ID}",
        json={"price": -1.0},
    )

    assert response.status_code == 400
    data = response.json()
    assert "errors" in data
    assert "price" in data["errors"]


async def test_update_product_nonexistent_returns_404(client_not_found):
    response = await client_not_found.put(
        "/api/products/000000000000000000000000",
        json={"name": "Ghost Product"},
    )

    assert response.status_code == 404


# ─── Error response structure ─────────────────────────────────────────────────

async def test_error_response_has_errors_object_with_string_values(client):
    response = await client.post(
        "/api/products",
        json={"price": -1.0, "category": "Furniture"},
    )

    assert response.status_code == 400
    data = response.json()
    assert isinstance(data.get("errors"), dict)
    for value in data["errors"].values():
        assert isinstance(value, str)
