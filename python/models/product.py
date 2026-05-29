"""Pydantic models for product request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

VALID_CATEGORIES = {"Electronics", "Accessories", "Storage", "Networking"}


class ProductInDB(BaseModel):
    """Internal product representation as stored in MongoDB."""

    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProductRequest(BaseModel):
    """Generic partial product payload (all fields optional)."""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None


class ProductCreateRequest(BaseModel):
    """Payload for creating a new product."""

    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Ensure the product name is not blank."""
        if not v or not v.strip():
            raise ValueError("Name is required and cannot be empty")
        return v

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        """Ensure price is positive when provided."""
        if v is not None and v <= 0:
            raise ValueError("Price must be a positive number")
        return v

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Ensure category belongs to the allowed set."""
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
        return v


class ProductUpdateRequest(BaseModel):
    """Payload for updating an existing product (all fields optional)."""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        """Ensure price is positive when provided."""
        if v is not None and v <= 0:
            raise ValueError("Price must be a positive number")
        return v

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Ensure category belongs to the allowed set."""
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
        return v


class ProductResponse(BaseModel):
    """Product shape returned by the API."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class ProductListResponse(BaseModel):
    """Paginated list of products."""

    data: list[dict]
    page: int
    limit: int
    total: int


class ProductStatsResponse(BaseModel):
    """Aggregate product statistics."""

    totalCount: int
    averagePrice: float
    minPrice: float
    maxPrice: float
    categoryCount: dict[str, int]


class StockUpdateRequest(BaseModel):
    """Payload for updating a product's stock level."""

    stock: int

    @field_validator("stock")
    @classmethod
    def stock_must_not_be_negative(cls, v: int) -> int:
        """Ensure stock is not negative."""
        if v < 0:
            raise ValueError("Stock cannot be negative")
        return v
