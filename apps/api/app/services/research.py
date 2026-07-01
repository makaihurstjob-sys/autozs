import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import CandidateProduct, ResearchJob


def create_mock_candidates(db: Session, job: ResearchJob) -> list[CandidateProduct]:
    """Seed deterministic candidates until real eBay research credentials are connected."""
    base_titles = {
        "competitor": [
            "Heavy Duty Garage Storage Shelf",
            "Cordless Drill Driver Kit",
            "Outdoor Resin Storage Deck Box",
        ],
        "keyword": [
            f"{job.query.title()} Organizer Rack",
            f"{job.query.title()} Tool Kit",
            f"{job.query.title()} Storage Cabinet",
        ],
    }
    created: list[CandidateProduct] = []
    for index, title in enumerate(base_titles.get(job.source, base_titles["keyword"]), start=1):
        external_id = hashlib.sha1(f"{job.source}:{job.query}:{title}".encode()).hexdigest()[:12]
        existing = db.scalar(
            select(CandidateProduct).where(
                CandidateProduct.source == job.source,
                CandidateProduct.external_id == external_id,
            )
        )
        if existing:
            continue
        candidate = CandidateProduct(
            source=job.source,
            external_id=external_id,
            title=title,
            listing_url=f"https://www.ebay.com/itm/{external_id}",
            image_url=None,
            competitor_price=round(59.99 + (index * 12.5), 2),
            estimated_sold=25 * index,
            seller_username=job.query if job.source == "competitor" else None,
            research_job_id=job.id,
        )
        db.add(candidate)
        created.append(candidate)
    job.status = "completed"
    job.message = f"Created {len(created)} mock candidates"
    db.commit()
    return created
