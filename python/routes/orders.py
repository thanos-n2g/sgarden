from fastapi import APIRouter, HTTPException, status, Depends
from models.order import OrderCreateRequest, OrderUpdateRequest
from database import orders_collection, products_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/orders", tags=["orders"])


def order_to_response(order: dict) -> dict:
    return {
        "id": str(order["_id"]),
        "items": order.get("items", []),
        "total": order.get("total", 0.0),
        "createdAt": order["createdAt"].isoformat() if order.get("createdAt") else None,
        "updatedAt": order["updatedAt"].isoformat() if order.get("updatedAt") else None,
    }


async def calculate_total(items: list) -> float:
    total = 0.0
    for item in items:
        product_id = item["productId"]
        quantity = item["quantity"]
        if not ObjectId.is_valid(product_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid productId: {product_id}")
        product = await products_collection.find_one({"_id": ObjectId(product_id)})
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {product_id} not found")
        total += (product.get("price") or 0.0) * quantity
    return total


@router.get("")
async def list_orders(current_user: dict = Depends(get_current_user)):
    orders = []
    async for order in orders_collection.find():
        orders.append(order_to_response(order))
    return orders


@router.get("/{order_id}")
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order_to_response(order)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderCreateRequest, current_user: dict = Depends(get_current_user)):
    items = [{"productId": item.productId, "quantity": item.quantity} for item in request.items]
    total = await calculate_total(items)
    now = datetime.utcnow()
    order_doc = {"items": items, "total": total, "createdAt": now, "updatedAt": now}

    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return order_to_response(order_doc)


@router.put("/{order_id}")
async def update_order(order_id: str, request: OrderUpdateRequest, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    items = [{"productId": item.productId, "quantity": item.quantity} for item in request.items]
    total = await calculate_total(items)

    result = await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"items": items, "total": total, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_to_response(order)


@router.delete("/{order_id}")
async def delete_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {"message": "Order deleted"}
