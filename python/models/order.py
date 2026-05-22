from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class OrderItem(BaseModel):
    productId: str
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be a positive integer")
        return v


class OrderCreateRequest(BaseModel):
    items: List[OrderItem]

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: List[OrderItem]) -> List[OrderItem]:
        if not v:
            raise ValueError("Items cannot be empty")
        return v


class OrderUpdateRequest(BaseModel):
    items: List[OrderItem]

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: List[OrderItem]) -> List[OrderItem]:
        if not v:
            raise ValueError("Items cannot be empty")
        return v


class OrderResponse(BaseModel):
    id: str
    items: List[dict]
    total: float
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
