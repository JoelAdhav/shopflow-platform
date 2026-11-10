"""Request and response shapes. Pydantic validates input before our code runs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0, default=0)


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: int
    status: str
    created_at: datetime
    processed_at: datetime | None
