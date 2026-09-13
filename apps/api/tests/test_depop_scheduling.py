import json
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.depop import DepopAccount, DepopListingJob, DepopListingVariant, DepopSourcePhoto
from app.models.domain import Product, ProductImage
from app.schemas.depop import DepopJobCreate
from app.services.depop_jobs import _next_schedule_slots, schedule_approved_photo_batches, start_next_depop_job


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.depop_jobs.PROJECT_ROOT", tmp_path)
    (tmp_path / "downloads").mkdir()
    (tmp_path / "downloads" / "image.jpg").write_bytes(b"test image")
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def seed(db, count=4):
    db.add(DepopAccount(key='closet', label='Closet', writes_enabled=True))
    product = Product(sku='owned-bag', title='Bag')
    db.add(product)
    db.flush()
    variant = DepopListingVariant(product_id=product.id, account_key='closet', variant_key='blue', title='Blue bag', description='My blue bag', price=25, brand='Other', category='Bags', condition='Good', shipping_method='Medium Under 1lb')
    db.add(variant)
    db.flush()
    add_photos(db, variant, 0, count)
    db.commit()
    return variant


def add_photos(db, variant, start, count):
    for index in range(start, start + count):
        url = f'https://images.test/{index}.jpg'
        db.add(ProductImage(product_id=variant.product_id, image_url=url, local_path="downloads/image.jpg"))
        db.add(DepopSourcePhoto(product_id=variant.product_id, variant_id=variant.id, image_url=url, status='approved', sort_order=index))
    db.flush()


def schedule(db):
    return schedule_approved_photo_batches(db, account_key='closet', now=datetime(2026, 9, 11, 10), daily_hours=[12, 20])[0]


def test_incremental_batches_reserve_existing_slots(db):
    variant = seed(db)
    first = schedule(db)[0]
    add_photos(db, variant, 4, 4)
    db.commit()
    second = schedule(db)[0]
    assert first.scheduled_for == datetime(2026, 9, 11, 17)
    assert second.scheduled_for == datetime(2026, 9, 12, 1)


@pytest.mark.parametrize('status', ['queued', 'running', 'needs_review', 'completed'])
def test_rescheduling_preserves_existing_payload_and_does_not_duplicate(db, status):
    variant = seed(db)
    job = schedule(db)[0]
    job.status = status
    variant.status = status
    original_images = variant.image_ids_json
    photo = db.query(DepopSourcePhoto).first()
    photo.sort_order = 99
    db.commit()
    assert schedule(db) == []
    assert variant.image_ids_json == original_images
    assert variant.status == status
    assert db.query(DepopListingJob).count() == 1


def test_explicit_offset_schedule_normalized_before_sqlite_storage():
    value = DepopJobCreate(variant_id=1, scheduled_for='2026-09-11T12:00:00-05:00')
    assert value.scheduled_for == datetime(2026, 9, 11, 17)


def test_cancelled_attempt_cannot_be_replaced_by_batch_scheduler(db):
    variant = seed(db)
    job = schedule(db)[0]
    job.attempts = 1
    job.status = 'cancelled'
    db.commit()
    assert schedule(db) == []
    assert db.query(DepopListingJob).count() == 1


def test_extra_photo_batch_preserves_shipping_weight_policy(db):
    variant = seed(db, count=8)
    variant.packed_weight_lb = 3
    variant.supplier_weight_lb = 5
    variant.shipping_method = 'Extra large Under 10lb'
    db.commit()
    jobs = schedule(db)
    extra = db.get(DepopListingVariant, jobs[1].variant_id)
    assert extra.packed_weight_lb == 3
    assert extra.supplier_weight_lb == 5
    assert extra.shipping_method == variant.shipping_method


def test_dst_missing_hour_skipped_and_fall_back_never_yields_past():
    spring = _next_schedule_slots(datetime(2026, 3, 8, 6), 'America/Chicago', [2])
    assert next(spring) == datetime(2026, 3, 9, 7)
    fall = _next_schedule_slots(datetime(2026, 11, 1, 7, 30), 'America/Chicago', [1])
    assert next(fall) == datetime(2026, 11, 2, 7)


@pytest.mark.parametrize('changes', [{'price': 0}, {'price': float('inf')}, {'account_key': 'other'}, {'depop_listing_id': 'already-live'}, {'description': ''}])
def test_claim_revalidates_payload(db, changes):
    variant = seed(db)
    job = schedule(db)[0]
    for key, value in changes.items():
        setattr(variant, key, value)
    db.commit()
    result = start_next_depop_job(db, now=datetime(2026, 9, 12))
    assert result.id == job.id
    assert result.status == 'needs_review'
    assert result.attempts == 0


def test_future_job_stays_queued(db):
    seed(db)
    job = schedule(db)[0]
    assert start_next_depop_job(db, now=datetime(2026, 9, 11, 16, 59)) is None
    assert job.status == 'queued'
    assert start_next_depop_job(db, now=datetime(2026, 9, 11, 17)).status == 'running'


def test_missing_download_blocks_claim(db):
    seed(db)
    schedule(db)
    db.query(ProductImage).first().local_path = None
    db.commit()
    assert start_next_depop_job(db, now=datetime(2026, 9, 12)).status == "needs_review"


def test_account_filter_does_not_claim_other_account(db):
    seed(db)
    schedule(db)
    assert start_next_depop_job(db, now=datetime(2026, 9, 12), account_key="another") is None
    assert db.query(DepopListingJob).one().attempts == 0


def test_every_two_hours_default_includes_midnight_and_new_condition(db):
    from app.schemas.depop import DepopApprovedBatchScheduleRequest, DepopVariantCreate
    request = DepopApprovedBatchScheduleRequest(account_key="closet")
    assert request.daily_hours == list(range(0, 24, 2))
    assert DepopVariantCreate(product_id=1, account_key="closet", variant_key="new", title="Bag", price=25).condition == "Brand new"
    seed(db, 8)
    jobs, *_ = schedule_approved_photo_batches(db, account_key="closet", now=datetime(2026, 9, 12, 4, 59))
    assert [job.scheduled_for for job in jobs] == [datetime(2026, 9, 12, 5), datetime(2026, 9, 12, 7)]


@pytest.mark.parametrize("packed,supplier,explicit,expected,source", [
    (None, None, "", "Extra large Under 10lb", "owner_approved_estimate"),
    (None, 3, "", "Extra large Under 10lb", "supplier_weight"),
    (0.4, None, "", "Extra small Under 8oz", "packed_weight"),
    (0.4, None, "Large Under 2lb", "Large Under 2lb", "packed_weight"),
    (None, 10, "", "", "supplier_weight"),
])
def test_weight_provenance_and_no_understatement(db, packed, supplier, explicit, expected, source):
    from app.services.depop_jobs import depop_shipping
    variant = seed(db)
    variant.packed_weight_lb, variant.supplier_weight_lb, variant.shipping_method = packed, supplier, explicit
    package = depop_shipping(variant)
    assert package["shipping_method"] == expected
    assert package["shipping_weight_source"] == source


def test_missing_selected_image_is_not_silently_dropped(db):
    from app.services.depop_jobs import depop_listing_problem
    variant = seed(db)
    schedule(db)
    ids = json.loads(variant.image_ids_json)
    ids[-1] = 999999
    variant.image_ids_json = json.dumps(ids)
    assert "Every selected" in depop_listing_problem(db, variant)


def test_durable_submission_and_confirmation_guards(db):
    from fastapi import HTTPException
    from app.api.routes import begin_depop_submission, confirm_depop_publication, update_depop_job, update_depop_variant
    from app.schemas.depop import DepopSubmissionBegin, DepopPublicationConfirm, DepopJobUpdate, DepopVariantUpdate
    variant = seed(db)
    job = schedule(db)[0]
    confirmation = DepopPublicationConfirm(depop_listing_id="closet-bag-123")
    with pytest.raises(HTTPException):
        confirm_depop_publication(job.id, confirmation, db)
    start_next_depop_job(db, now=datetime(2026, 9, 12))
    with pytest.raises(HTTPException):
        update_depop_variant(variant.id, DepopVariantUpdate(price=50), db)
    result = begin_depop_submission(job.id, DepopSubmissionBegin(account_key="closet"), db)
    assert result.status == "needs_review"
    with pytest.raises(HTTPException):
        begin_depop_submission(job.id, DepopSubmissionBegin(account_key="closet"), db)
    with pytest.raises(HTTPException):
        update_depop_job(job.id, DepopJobUpdate(status="queued"), db)
    assert confirm_depop_publication(job.id, confirmation, db).status == "completed"
    assert confirm_depop_publication(job.id, confirmation, db).status == "completed"
    with pytest.raises(HTTPException):
        confirm_depop_publication(job.id, DepopPublicationConfirm(depop_listing_id="conflicting"), db)


def test_concurrent_claims_never_double_claim_same_job(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.depop_jobs.PROJECT_ROOT", tmp_path)
    (tmp_path / "downloads").mkdir()
    (tmp_path / "downloads" / "image.jpg").write_bytes(b"test image")
    db_path = tmp_path / "concurrent.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 5})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as setup:
        seed(setup)
        schedule(setup)

    results = []
    barrier = threading.Barrier(2)

    def claim():
        with SessionLocal() as session:
            barrier.wait()
            results.append(start_next_depop_job(session, now=datetime(2026, 9, 12)))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    running = [job for job in results if job is not None and job.status == "running"]
    assert len(running) == 1
    with SessionLocal() as check:
        job = check.query(DepopListingJob).one()
        assert job.attempts == 1
        assert job.status == "running"
    engine.dispose()


def test_invalid_batch_never_queued(db):
    variant = seed(db)
    variant.description = ""
    db.commit()
    with pytest.raises(ValueError):
        schedule(db)
    db.rollback()
    assert db.query(DepopListingJob).count() == 0


def test_pending_publication_survives_session_loss_and_blocks_next_claim(db):
    from fastapi import HTTPException
    from app.api.routes import begin_depop_submission, confirm_depop_publication, update_depop_job
    from app.schemas.depop import DepopSubmissionBegin, DepopPublicationConfirm, DepopJobUpdate
    seed(db, count=8)
    jobs = schedule(db)
    first_id, next_id = jobs[0].id, jobs[1].id
    start_next_depop_job(db, now=datetime(2026, 9, 13))
    pending = begin_depop_submission(first_id, DepopSubmissionBegin(account_key="closet"), db)
    assert pending.submission_started_at is not None
    with pytest.raises(HTTPException):
        update_depop_job(first_id, DepopJobUpdate(status="cancelled"), db)
    db.rollback()
    # A fresh session has no browser-local state or identity-map history.
    with Session(db.get_bind()) as recovered:
        assert start_next_depop_job(recovered, now=datetime(2026, 9, 13)) is None
        recovered.rollback()
        confirm_depop_publication(first_id, DepopPublicationConfirm(depop_listing_id="closet-blue"), recovered)
        assert start_next_depop_job(recovered, now=datetime(2026, 9, 13)).id == next_id


def test_legacy_depop_migration_idempotent_and_preserves_submission_hold(tmp_path, monkeypatch):
    from sqlalchemy import text, inspect
    from app import main
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE depop_listing_variants (id INTEGER PRIMARY KEY, title TEXT)"))
        connection.execute(text("INSERT INTO depop_listing_variants VALUES (1, 'Original bag')"))
        connection.execute(text("CREATE TABLE depop_listing_jobs (id INTEGER PRIMARY KEY, attempts INTEGER, status TEXT, message TEXT, updated_at DATETIME)"))
        connection.execute(text("INSERT INTO depop_listing_jobs VALUES (1, 1, 'needs_review', :message, '2026-09-12 12:00:00')"),
                           {"message": "Submission started; outcome requires listing confirmation before any retry."})
        connection.execute(text("INSERT INTO depop_listing_jobs VALUES (2, 0, 'queued', '', '2026-09-12 12:00:00')"))
    monkeypatch.setattr(main, "engine", engine)
    main._ensure_lightweight_columns()
    main._ensure_lightweight_columns()
    with engine.connect() as connection:
        row = connection.execute(text("SELECT title, shipping_method, packed_weight_lb, supplier_weight_lb FROM depop_listing_variants")).one()
        assert tuple(row) == ("Original bag", "", None, None)
        holds = connection.execute(text("SELECT submission_started_at FROM depop_listing_jobs ORDER BY id")).scalars().all()
        assert holds == ["2026-09-12 12:00:00", None]
    assert "submission_started_at" in {col["name"] for col in inspect(engine).get_columns("depop_listing_jobs")}
    engine.dispose()
