import csv
import base64
from datetime import datetime, timedelta
from io import BytesIO, StringIO, TextIOWrapper
import json
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayListing,
    EbayRevisionBatch,
    EbayRevisionBatchStatus,
    EbayRevisionJob,
    EbayRevisionJobStatus,
)
from app.services.ebay_revision_csv import build_ebay_price_revision_csv, read_ebay_revision_template
from app.services.ebay_revisions import update_ebay_revision_job


ACTIVE_BATCH_STATUSES = {
    EbayRevisionBatchStatus.prepared.value,
    EbayRevisionBatchStatus.uploading.value,
    EbayRevisionBatchStatus.waiting_results.value,
}
BULK_REVISION_LEASE_MINUTES = 30


def list_ebay_revision_batches(
    db: Session,
    *,
    account_key: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[EbayRevisionBatch]:
    stmt = select(EbayRevisionBatch)
    if account_key:
        stmt = stmt.where(EbayRevisionBatch.account_key == account_key)
    if status:
        stmt = stmt.where(EbayRevisionBatch.status == status)
    return list(
        db.scalars(
            stmt.order_by(EbayRevisionBatch.updated_at.desc(), EbayRevisionBatch.id.desc()).limit(limit)
        ).all()
    )


def prepare_next_ebay_revision_batch(
    db: Session,
    *,
    account_key: str,
    limit: int = 25,
) -> EbayRevisionBatch | None:
    active = db.scalar(
        select(EbayRevisionBatch)
        .where(EbayRevisionBatch.account_key == account_key, EbayRevisionBatch.status.in_(ACTIVE_BATCH_STATUSES))
        .order_by(EbayRevisionBatch.created_at.asc(), EbayRevisionBatch.id.asc())
    )
    if active is not None:
        return active
    template = read_ebay_revision_template(db, account_key)
    if template is None:
        raise ValueError(f"No eBay price revision template is stored for {account_key}")
    jobs = list(
        db.scalars(
            select(EbayRevisionJob)
            .where(
                EbayRevisionJob.ebay_account_key == account_key,
                EbayRevisionJob.status == EbayRevisionJobStatus.queued.value,
                EbayRevisionJob.guard_passed.is_(True),
                EbayRevisionJob.approval_required.is_(False),
                EbayRevisionJob.approved_at.is_not(None),
            )
            .order_by(EbayRevisionJob.created_at.asc(), EbayRevisionJob.id.asc())
            .limit(limit)
        ).all()
    )
    if not jobs:
        return None
    csv_content, job_ids = build_ebay_price_revision_csv(
        db,
        account_key=account_key,
        job_ids=[job.id for job in jobs],
        template_csv=template.template_csv,
    )
    now = datetime.utcnow()
    safe_account = _safe_token(account_key)
    batch = EbayRevisionBatch(
        account_key=account_key,
        status=EbayRevisionBatchStatus.prepared.value,
        job_ids_json=json.dumps(job_ids),
        filename=f"autozs-price-revisions-{safe_account}-{now:%Y%m%d%H%M%S}.csv",
        csv_content=csv_content,
        rows_total=len(job_ids),
        message=f"Prepared {len(job_ids)} guarded eBay price revision(s) for upload.",
    )
    db.add(batch)
    for job in jobs:
        job.status = EbayRevisionJobStatus.running.value
        job.started_at = now
        job.completed_at = None
        job.lease_expires_at = now + timedelta(minutes=BULK_REVISION_LEASE_MINUTES)
        job.attempts += 1
        job.message = "Prepared in an eBay Seller Hub price revision sheet; waiting for upload."
    db.commit()
    db.refresh(batch)
    return batch


def update_ebay_revision_batch(
    db: Session,
    batch: EbayRevisionBatch,
    *,
    status: str | None = None,
    message: str | None = None,
) -> EbayRevisionBatch:
    if status is not None:
        if status not in {item.value for item in EbayRevisionBatchStatus}:
            raise ValueError(f"Unsupported revision batch status {status}")
        batch.status = status
        if status == EbayRevisionBatchStatus.uploading.value:
            batch.started_at = batch.started_at or datetime.utcnow()
            batch.attempts += 1
        if status in {
            EbayRevisionBatchStatus.completed.value,
            EbayRevisionBatchStatus.needs_review.value,
            EbayRevisionBatchStatus.failed.value,
            EbayRevisionBatchStatus.cancelled.value,
        }:
            batch.completed_at = datetime.utcnow()
        if status in {EbayRevisionBatchStatus.needs_review.value, EbayRevisionBatchStatus.failed.value}:
            for job in _batch_jobs(db, batch):
                if job.status == EbayRevisionJobStatus.running.value:
                    job.status = EbayRevisionJobStatus.paused.value
                    job.lease_expires_at = None
                    job.message = message or "The eBay revision batch needs manual attention."
    if message is not None:
        batch.message = message
    db.commit()
    db.refresh(batch)
    return batch


def import_ebay_revision_result(
    db: Session,
    batch: EbayRevisionBatch,
    *,
    result_csv: str,
    filename: str = "",
) -> EbayRevisionBatch:
    rows = _read_result_rows(result_csv)
    jobs = {job.id: job for job in _batch_jobs(db, batch)}
    jobs_by_item = {}
    for job in jobs.values():
        listing = db.get(EbayListing, job.ebay_listing_id)
        if listing is not None:
            jobs_by_item[str(listing.listing_id)] = job
    seen: set[int] = set()
    succeeded = 0
    failed = 0
    for row in rows:
        item_number = _row_value(row, "item number", "item id", "itemid")
        job = jobs_by_item.get(item_number)
        if job is None:
            continue
        seen.add(job.id)
        error = _row_value(row, "error message", "error", "message", "failure reason")
        status = _row_value(row, "status", "result", "response status")
        success = not error and (not status or any(token in status.lower() for token in ("success", "complete", "uploaded")))
        if success:
            update_ebay_revision_job(
                db,
                job,
                status=EbayRevisionJobStatus.completed.value,
                message=f"eBay bulk upload confirmed the price revision to ${job.target_price:.2f}.",
            )
            succeeded += 1
        else:
            update_ebay_revision_job(
                db,
                job,
                status=EbayRevisionJobStatus.paused.value,
                message=f"eBay bulk upload needs attention: {error or status or 'unknown row result'}",
            )
            failed += 1
    for job_id, job in jobs.items():
        if job_id in seen:
            continue
        update_ebay_revision_job(
            db,
            job,
            status=EbayRevisionJobStatus.paused.value,
            message="The eBay upload result did not contain this item; manual verification is required.",
        )
        failed += 1
    batch.result_filename = filename
    batch.rows_succeeded = succeeded
    batch.rows_failed = failed
    batch.status = EbayRevisionBatchStatus.completed.value if failed == 0 and succeeded == len(jobs) else EbayRevisionBatchStatus.needs_review.value
    batch.completed_at = datetime.utcnow()
    batch.message = f"eBay results reconciled: {succeeded} succeeded, {failed} need attention."
    db.commit()
    db.refresh(batch)
    return batch


def decode_ebay_revision_result(*, filename: str, result_csv: str = "", result_base64: str | None = None) -> str:
    if result_csv.strip():
        return result_csv
    if not result_base64:
        raise ValueError("The eBay revision result is empty")
    try:
        content = base64.b64decode(result_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("The eBay revision result is not valid base64") from exc
    if not content:
        raise ValueError("The eBay revision result is empty")
    if str(filename or "").lower().endswith(".zip"):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".tsv", ".txt"))]
                if not names:
                    raise ValueError("The eBay revision result ZIP did not contain a CSV file")
                with archive.open(names[0]) as source:
                    return TextIOWrapper(source, encoding="utf-8-sig", errors="replace").read()
        except BadZipFile as exc:
            raise ValueError("The eBay revision result ZIP is invalid") from exc
    return content.decode("utf-8-sig", errors="replace")


def serialize_ebay_revision_batch(batch: EbayRevisionBatch, *, include_csv: bool = False) -> dict:
    payload = {
        "id": batch.id,
        "account_key": batch.account_key,
        "status": batch.status,
        "job_ids": json.loads(batch.job_ids_json or "[]"),
        "filename": batch.filename,
        "result_filename": batch.result_filename,
        "rows_total": batch.rows_total,
        "rows_succeeded": batch.rows_succeeded,
        "rows_failed": batch.rows_failed,
        "attempts": batch.attempts,
        "started_at": batch.started_at,
        "completed_at": batch.completed_at,
        "message": batch.message,
        "runner_url": (
            "https://www.ebay.com/sh/reports/uploads"
            f"?autozs_revision_batch={batch.id}&autozs_account_key={batch.account_key}"
        ),
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }
    if include_csv:
        payload["csv_content"] = batch.csv_content
    return payload


def _batch_jobs(db: Session, batch: EbayRevisionBatch) -> list[EbayRevisionJob]:
    ids = [int(value) for value in json.loads(batch.job_ids_json or "[]")]
    if not ids:
        return []
    jobs = list(db.scalars(select(EbayRevisionJob).where(EbayRevisionJob.id.in_(ids))).all())
    return sorted(jobs, key=lambda job: ids.index(job.id))


def _read_result_rows(text: str) -> list[dict[str, str]]:
    clean = text.lstrip("\ufeff")
    lines = clean.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if "item number" in line.lower() or "item id" in line.lower()),
        None,
    )
    if header_index is None:
        raise ValueError("The eBay upload result did not contain an item-number header")
    reader = csv.DictReader(StringIO("\n".join(lines[header_index:])))
    rows = [{str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("The eBay upload result did not contain any rows")
    return rows


def _row_value(row: dict[str, str], *names: str) -> str:
    return next((row.get(name, "").strip() for name in names if row.get(name, "").strip()), "")


def _safe_token(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value) or "account"
