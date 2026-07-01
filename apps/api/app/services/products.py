from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.domain import CandidateProduct, CandidateStatus, Product, ProductStatus


def approve_candidate(db: Session, candidate: CandidateProduct) -> Product:
    settings = get_settings()
    if candidate.status == CandidateStatus.approved.value:
        existing = db.query(Product).filter(Product.candidate_id == candidate.id).first()
        if existing:
            return existing

    product = Product(
        sku=f"SKU-{candidate.id:06d}",
        title=candidate.title,
        status=ProductStatus.draft.value,
        candidate_id=candidate.id,
        competitor_listing_url=candidate.listing_url,
        competitor_price=candidate.competitor_price,
        desired_profit=settings.default_min_profit,
        risk_buffer=settings.default_risk_buffer,
        ebay_fee_rate=settings.default_ebay_fee_rate,
        promoted_rate=settings.default_promoted_rate,
        return_risk_rate=settings.default_return_risk_rate,
        undercut_amount=settings.default_undercut_amount,
    )
    candidate.status = CandidateStatus.approved.value
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
