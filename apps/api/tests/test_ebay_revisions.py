from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.domain import EbayRevisionJob, EbayRevisionJobStatus
from app.services.ebay_revisions import MAX_REVISION_ATTEMPTS, release_expired_ebay_revision_jobs


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_expired_revision_lease_returns_approved_job_to_queue() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        attempts=1,
        lease_expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    assert release_expired_ebay_revision_jobs(db) == 1
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.queued.value
    assert job.started_at is None
    assert job.lease_expires_at is None
    assert "returned" in (job.message or "")


def test_revision_stops_after_repeated_timeouts() -> None:
    db = make_session()
    job = EbayRevisionJob(
        product_id=1,
        ebay_listing_id=1,
        target_price=29.99,
        status=EbayRevisionJobStatus.running.value,
        guard_passed=True,
        approval_required=False,
        approved_at=datetime.utcnow(),
        attempts=MAX_REVISION_ATTEMPTS,
        lease_expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()

    assert release_expired_ebay_revision_jobs(db) == 1
    db.refresh(job)
    assert job.status == EbayRevisionJobStatus.failed.value
    assert job.completed_at is not None
    assert "manual attention" in (job.message or "")
