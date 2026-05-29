import re
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import products_collection
from models.product import (
    ProductCreateRequest,
    ProductListResponse,
    ProductStatsResponse,
    ProductUpdateRequest,
    StockUpdateRequest,
)
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])


def product_to_response(product: dict) -> dict:
    """Convert a MongoDB product document to the API response format."""
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": product.get("createdAt", "").isoformat() if product.get("createdAt") else None,
        "updatedAt": product.get("updatedAt", "").isoformat() if product.get("updatedAt") else None,
    }


@router.get("", response_model=ProductListResponse)
async def get_all_products(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    order: Optional[str] = Query("asc"),
):
    """List all products with pagination and optional sorting."""
    sort_direction = 1 if order != "desc" else -1
    skip = (page - 1) * limit

    total = await products_collection.count_documents({})

    cursor = products_collection.find()
    if sort:
        cursor = cursor.sort(sort, sort_direction)
    cursor = cursor.skip(skip).limit(limit)

    products = []
    async for product in cursor:
        products.append(product_to_response(product))

    return ProductListResponse(data=products, page=page, limit=limit, total=total)


@router.get("/search")
async def search_products(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, alias="minPrice"),
    max_price: Optional[float] = Query(None, alias="maxPrice"),
):
    """Search products by name/description, category, and price range."""
    mongo_filter = {}

    if q:
        pattern = re.compile(re.escape(q), re.IGNORECASE)
        mongo_filter["$or"] = [{"name": pattern}, {"description": pattern}]

    if category is not None:
        mongo_filter["category"] = category

    price_filter = {}
    if min_price is not None:
        price_filter["$gte"] = min_price
    if max_price is not None:
        price_filter["$lte"] = max_price
    if price_filter:
        mongo_filter["price"] = price_filter

    products = []
    async for product in products_collection.find(mongo_filter):
        products.append(product_to_response(product))
    return products


@router.get("/stats", response_model=ProductStatsResponse)
async def get_product_stats():
    """Return aggregate statistics across all products."""
    total_count = 0
    prices = []
    category_counts: dict[str, int] = {}

    async for product in products_collection.find():
        total_count += 1
        price = product.get("price")
        if price is not None:
            prices.append(price)
        category = product.get("category") or "Uncategorized"
        category_counts[category] = category_counts.get(category, 0) + 1

    avg_price = sum(prices) / len(prices) if prices else 0.0

    return ProductStatsResponse(
        totalCount=total_count,
        averagePrice=avg_price,
        minPrice=min(prices) if prices else 0.0,
        maxPrice=max(prices) if prices else 0.0,
        categoryCount=category_counts,
    )


@router.get("/{product_id}")
async def get_product_by_id(product_id: str):
    """Fetch a single product by its ID."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return product_to_response(product)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    _current_user: dict = Depends(get_current_user),
):
    """Create a new product. Requires authentication."""
    product_doc = {
        "name": request.name,
        "description": request.description,
        "category": request.category,
        "price": request.price,
        "stock": request.stock if request.stock is not None else 0,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await products_collection.insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    return product_to_response(product_doc)


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    request: ProductUpdateRequest,
    _current_user: dict = Depends(get_current_user),
):
    """Update a product's fields. Requires authentication."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.patch("/{product_id}/stock")
async def update_product_stock(
    product_id: str,
    request: StockUpdateRequest,
    _current_user: dict = Depends(get_current_user),
):
    """Update a product's stock level. Requires authentication."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"stock": request.stock, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    _current_user: dict = Depends(get_current_user),
):
    """Delete a product. Requires authentication."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return {"message": "Product deleted"}
