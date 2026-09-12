from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.delivery_quotes import router
from app.core.database import Base, get_db
from app.models.domain import DeliveryCheckJob, EbayListing, Product, SupplierProduct
from app.services import delivery_checks as checks


@pytest.fixture()
def db():
    engine = create_engine('sqlite:///:memory:', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def listing(db, number=1, **overrides):
    product = Product(sku=f'audit-{number}', title='Audit product', status='monitoring')
    db.add(product)
    db.flush()
    supplier = SupplierProduct(product_id=product.id,
        source_url=f'https://www.homedepot.com/p/Audit/{100000000 + number}', in_stock=True)
    row = EbayListing(product_id=product.id, listing_id=str(number), account_id='owner',
                      environment='production', status='live', quantity=1)
    for key, value in overrides.items():
        setattr(row, key, value)
    db.add_all([supplier, row])
    db.commit()
    return row, supplier


def enable(db):
    checks.write_policy(db, {'enabled': True, 'postal_codes': ['84532'], 'trial': None})


def test_selection_is_account_production_live_and_explicit(db):
    selected, supplier = listing(db)
    other, _ = listing(db, 2, account_id='other')
    sandbox, _ = listing(db, 3, environment='sandbox')
    ended, _ = listing(db, 4, status='ended')
    untouched, _ = listing(db, 5)
    enable(db)
    result = checks.enroll_live_listings(db, 'owner', [selected.id, other.id, sandbox.id, ended.id, 999])
    assert [row['listing_id'] for row in result['enrolled']] == [selected.id]
    assert len(result['skipped']) == 4
    assert result['postal_codes'] == ['84532']
    jobs = db.scalars(select(DeliveryCheckJob)).all()
    assert len(jobs) == 1 and jobs[0].supplier_product_id == supplier.id
    assert jobs[0].postal_code == '84532'
    assert untouched.status == 'live'


def test_repeated_enrollment_preserves_running_lease(db):
    row, _ = listing(db)
    enable(db)
    first = checks.enroll_live_listings(db, 'owner', [row.id])
    claimed = checks.claim_check(db, 'audit-browser')
    job = db.get(DeliveryCheckJob, claimed['id'])
    before = (job.status, job.worker_id, job.lease_token, job.lease_expires_at, job.attempts)
    second = checks.enroll_live_listings(db, 'owner', [row.id])
    assert first['enrolled'][0]['jobs'][0]['id'] == second['enrolled'][0]['jobs'][0]['id']
    assert (job.status, job.worker_id, job.lease_token, job.lease_expires_at, job.attempts) == before
    assert len(db.scalars(select(DeliveryCheckJob)).all()) == 1


def test_unknown_failure_never_changes_listing_or_supplier_and_stays_held(db):
    row, supplier = listing(db)
    enable(db)
    checks.enroll_live_listings(db, 'owner', [row.id])
    claimed = checks.claim_check(db, 'audit-browser')
    checks.fail_check(db, claimed['id'], 'audit-browser', claimed['lease_token'],
                      'Missing delivery page evidence', False)
    again = checks.enroll_live_listings(db, 'owner', [row.id])
    assert again['enrolled'][0]['jobs'][0]['status'] == 'needs_review'
    assert checks.claim_check(db, 'audit-browser') is None
    db.refresh(row)
    db.refresh(supplier)
    assert (row.status, row.quantity, row.relist_blocked) == ('live', 1, False)
    assert supplier.in_stock is True


def test_fresh_evidence_reused_stale_evidence_requeued(db):
    row, _ = listing(db)
    enable(db)
    checks.enroll_live_listings(db, 'owner', [row.id])
    job = db.scalar(select(DeliveryCheckJob))
    job.status, job.completed_at, job.delivery_charge = 'completed', datetime.utcnow(), 0
    job.lease_token = 'old-token'
    db.commit()
    checks.enroll_live_listings(db, 'owner', [row.id])
    assert job.status == 'completed'
    job.completed_at -= timedelta(days=2)
    db.commit()
    checks.enroll_live_listings(db, 'owner', [row.id])
    assert job.status == 'queued' and job.completed_at is None
    assert job.delivery_charge is None and job.lease_token == ''


def test_ineligible_supplier_skipped(db):
    row, supplier = listing(db)
    supplier.source_url = 'https://www.amazon.com/dp/B123456789'
    db.commit()
    enable(db)
    result = checks.enroll_live_listings(db, 'owner', [row.id])
    assert result['enrolled'] == [] and len(result['skipped']) == 1
    assert db.scalar(select(DeliveryCheckJob)) is None


def test_policy_required_and_trial_cannot_expand(db):
    row, supplier = listing(db)
    with pytest.raises(ValueError):
        checks.enroll_live_listings(db, 'owner', [row.id])
    checks.write_policy(db, {'enabled': False, 'postal_codes': ['84532'],
        'trial': {'supplier_product_id': supplier.id, 'postal_code': '84532'}})
    with pytest.raises(ValueError):
        checks.enroll_live_listings(db, 'owner', [row.id])
    assert db.scalar(select(DeliveryCheckJob)) is None


@pytest.mark.parametrize('ids', [[], [1, 1], list(range(1, 102)), [0], [-1], [True], ['1']])
def test_api_validates_bound_and_ids_without_starting_application(db, ids):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        assert client.post('/delivery-quotes/audits/live-listings',
            json={'account_id': 'owner', 'listing_ids': ids}).status_code == 422


def test_api_returns_audit_and_maps_policy_error(db):
    row, _ = listing(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        payload = {'account_id': 'owner', 'listing_ids': [row.id]}
        assert client.post('/delivery-quotes/audits/live-listings', json=payload).status_code == 422
        enable(db)
        response = client.post('/delivery-quotes/audits/live-listings', json=payload)
        assert response.status_code == 200
        assert response.json()['enrolled'][0]['listing_id'] == row.id

@pytest.mark.parametrize('new_state', ['running', 'completed'])
def test_stale_enrollment_cannot_overwrite_new_lease_or_completion(db, new_state):
    row, _ = listing(db)
    enable(db)
    checks.enroll_live_listings(db, 'owner', [row.id])
    job = db.scalar(select(DeliveryCheckJob))
    job.status = 'completed'
    job.completed_at = datetime.utcnow() - timedelta(days=2)
    job.delivery_charge = 0
    db.commit()
    with Session(db.get_bind(), expire_on_commit=False) as stale:
        old_job = stale.get(DeliveryCheckJob, job.id)
        assert old_job.status == 'completed'
        checks.enroll_live_listings(db, 'owner', [row.id])
        claimed = checks.claim_check(db, 'new-browser')
        if new_state == 'completed':
            job.status, job.completed_at, job.delivery_charge = 'completed', datetime.utcnow(), 7
            db.commit()
        db.refresh(job)
        expected = (job.status, job.lease_token, job.lease_expires_at, job.completed_at, job.delivery_charge)
        checks.enroll_live_listings(stale, 'owner', [row.id])
        db.refresh(job)
        assert (job.status, job.lease_token, job.lease_expires_at, job.completed_at, job.delivery_charge) == expected
        assert old_job.status == new_state
        assert job.lease_token == claimed['lease_token']
