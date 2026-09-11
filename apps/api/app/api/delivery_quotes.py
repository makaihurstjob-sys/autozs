from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.delivery_quotes import record_cart_quote, product_delivery_quotes

router = APIRouter(prefix="/delivery-quotes", tags=["delivery-quotes"])


class CartQuote(BaseModel):
    source_url: str = Field(max_length=2048)
    postal_code: str = Field(pattern=r"^\d{5}$")
    quantity: int = Field(strict=True, ge=1, le=999)
    delivery_charge: float = Field(ge=0, le=10000, allow_inf_nan=False)


@router.post("/cart")
def capture_cart_quote(payload: CartQuote, db: Session = Depends(get_db)):
    try:
        count = record_cart_quote(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": count}


@router.get("/products/{product_id}")
def read_product_quotes(product_id: int, db: Session = Depends(get_db)):
    return product_delivery_quotes(db, product_id)
