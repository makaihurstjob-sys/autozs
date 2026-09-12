from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.delivery_quotes import record_cart_quote, product_delivery_quotes
from app.services import delivery_checks
from app.models.domain import DeliveryCheckJob
from sqlalchemy import select
from pydantic import field_validator, model_validator

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


class CheckTrial(BaseModel):
    supplier_product_id: int = Field(strict=True, gt=0)
    postal_code: str = Field(pattern=r"^[0-9]{5}$")


class CheckPolicy(BaseModel):
    enabled: bool
    trial: CheckTrial | None = None
    postal_codes: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def trial_requires_broad_disabled(self):
        if self.enabled and self.trial:
            raise ValueError("Disable broad checks before configuring a bounded trial")
        return self

    @field_validator("postal_codes")
    @classmethod
    def valid_zips(cls, values):
        import re
        if len(set(values)) != len(values) or any(not re.fullmatch(r"[0-9]{5}", v) for v in values):
            raise ValueError("Provide unique five-digit ZIP codes")
        return values


class LiveListingAudit(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    listing_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=100)

    @field_validator("listing_ids")
    @classmethod
    def unique_listing_ids(cls, values):
        if len(set(values)) != len(values) or any(v <= 0 for v in values):
            raise ValueError("Provide unique positive listing row IDs")
        return values


@router.post("/audits/live-listings")
def enroll_live_listing_audit(payload: LiveListingAudit, db: Session = Depends(get_db)):
    try:
        return delivery_checks.enroll_live_listings(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class WorkerClaim(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)


class WorkerLease(WorkerClaim):
    lease_token: str = Field(min_length=32, max_length=64)


class CheckResult(WorkerLease):
    quote: CartQuote
    cart_cleared: bool


class CheckFailure(WorkerLease):
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False


@router.get("/policy")
def read_check_policy(db: Session = Depends(get_db)):
    return delivery_checks.read_policy(db)


@router.put("/policy")
def save_check_policy(payload: CheckPolicy, db: Session = Depends(get_db)):
    try:
        return delivery_checks.write_policy(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs")
def list_checks(db: Session = Depends(get_db)):
    return [delivery_checks.serialize_job(j) for j in db.scalars(
        select(DeliveryCheckJob).order_by(DeliveryCheckJob.id.desc()).limit(250)).all()]


@router.post("/jobs/claim")
def claim_check(payload: WorkerClaim, db: Session = Depends(get_db)):
    return delivery_checks.claim_check(db, payload.worker_id)


@router.post("/jobs/{job_id}/heartbeat")
def check_heartbeat(job_id: int, payload: WorkerLease, db: Session = Depends(get_db)):
    try:
        return delivery_checks.heartbeat(db, job_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/complete")
def complete_check(job_id: int, payload: CheckResult, db: Session = Depends(get_db)):
    if not payload.cart_cleared:
        raise HTTPException(status_code=409, detail="Clear the owned test item before completing the check")
    try:
        return delivery_checks.finish_check(db, job_id, payload.worker_id, payload.lease_token, payload.quote.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/failed")
def fail_check(job_id: int, payload: CheckFailure, db: Session = Depends(get_db)):
    try:
        return delivery_checks.fail_check(db, job_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
