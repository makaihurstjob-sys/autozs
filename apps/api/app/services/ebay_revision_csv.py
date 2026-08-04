import csv
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    EbayListing,
    EbayRevisionJob,
    EbayRevisionJobStatus,
    EbayRevisionTemplate,
    ListingDraft,
    SupplierProduct,
)
from app.services.ebay_revisions import STOCK_ACTION_QUANTITY


HEADER_ALIASES = {
    "action": {"action"},
    "item_number": {"item number", "item id", "itemid"},
    "start_price": {"start price", "price"},
}
# eBay's own "revise price and quantity" download names this column "Available quantity",
# not "Quantity". Matching only the short name appended a second, dead column and left the
# real one blank, so the listing would never actually go out of stock.
QUANTITY_HEADERS = {"available quantity", "quantity", "quantity available"}


def build_ebay_price_revision_csv(
    db: Session,
    *,
    account_key: str,
    job_ids: list[int],
    template_csv: str,
) -> tuple[str, list[int]]:
    if not job_ids:
        raise ValueError("Select at least one approved eBay revision job")

    rows = list(csv.reader(StringIO(template_csv.lstrip("\ufeff"))))
    header_index, columns = _find_header(rows)
    prefix = rows[:header_index]
    header = list(rows[header_index])
    pack_job_ids = {
        job_id
        for job_id in dict.fromkeys(job_ids)
        if _minimum_order_quantity(db, db.get(EbayRevisionJob, job_id)) > 1
    }
    title_column = next((index for index, value in enumerate(header) if value.strip().lower() == "title"), None)
    if pack_job_ids and title_column is None:
        title_column = len(header)
        header.append("Title")
    # Quantity is optional in the saved template, so add it only when a stock revision
    # actually needs it rather than forcing every seller's sheet to carry the column.
    stock_job_ids = {
        job_id
        for job_id in dict.fromkeys(job_ids)
        if getattr(db.get(EbayRevisionJob, job_id), "action", None) in STOCK_ACTION_QUANTITY
    }
    quantity_column = next(
        (index for index, value in enumerate(header) if value.strip().lower() in QUANTITY_HEADERS),
        None,
    )
    if stock_job_ids and quantity_column is None:
        quantity_column = len(header)
        header.append("Available quantity")
    output_rows = [*prefix, header]
    prepared_ids: list[int] = []

    for job_id in dict.fromkeys(job_ids):
        job = db.get(EbayRevisionJob, job_id)
        if job is None:
            raise ValueError(f"eBay revision job {job_id} was not found")
        _validate_job(job, account_key)
        listing = db.get(EbayListing, job.ebay_listing_id)
        listing_id = str(listing.listing_id if listing is not None else "").strip()
        if not (listing_id.isdigit() and len(listing_id) == 12):
            raise ValueError(f"Job {job.id} does not have a valid 12-digit eBay item number")

        row = [""] * len(header)
        row[columns["action"]] = "Revise"
        row[columns["item_number"]] = listing_id
        if job.action in STOCK_ACTION_QUANTITY:
            # Quantity-only revision. Start price is left blank on purpose: eBay changes
            # only the fields a row populates, so re-asserting a price here could push a
            # stale value at a listing we only meant to take out of stock.
            row[quantity_column] = str(STOCK_ACTION_QUANTITY[job.action])
        else:
            row[columns["start_price"]] = f"{job.target_price:.2f}"
        if title_column is not None and job.id in pack_job_ids:
            draft = db.scalar(
                select(ListingDraft)
                .where(ListingDraft.product_id == job.product_id, ListingDraft.marketplace == "ebay")
                .order_by(ListingDraft.created_at.asc(), ListingDraft.id.asc())
            )
            if draft is None or not str(draft.title or "").startswith(f"({_minimum_order_quantity(db, job)}X) "):
                raise ValueError(f"Job {job.id} requires a pack title before it can be revised")
            row[title_column] = draft.title
        output_rows.append(row)
        prepared_ids.append(job.id)

    output = StringIO(newline="")
    output.write("\ufeff")
    csv.writer(output, lineterminator="\r\n").writerows(output_rows)
    return output.getvalue(), prepared_ids


def _minimum_order_quantity(db: Session, job: EbayRevisionJob | None) -> int:
    if job is None:
        return 1
    supplier = db.scalar(
        select(SupplierProduct)
        .where(SupplierProduct.product_id == job.product_id)
        .order_by(SupplierProduct.created_at.asc(), SupplierProduct.id.asc())
    )
    return max(1, int(supplier.minimum_order_quantity or 1)) if supplier is not None else 1


def save_ebay_revision_template(
    db: Session,
    *,
    account_key: str,
    filename: str,
    template_csv: str,
) -> EbayRevisionTemplate:
    rows = list(csv.reader(StringIO(template_csv.lstrip("\ufeff"))))
    _find_header(rows)
    template = db.query(EbayRevisionTemplate).filter(EbayRevisionTemplate.account_key == account_key).first()
    if template is None:
        template = EbayRevisionTemplate(account_key=account_key, filename=filename, template_csv=template_csv)
        db.add(template)
    else:
        template.filename = filename
        template.template_csv = template_csv
    db.commit()
    db.refresh(template)
    return template


def read_ebay_revision_template(db: Session, account_key: str) -> EbayRevisionTemplate | None:
    return db.query(EbayRevisionTemplate).filter(EbayRevisionTemplate.account_key == account_key).first()


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows):
        normalized = {value.strip().lower(): column for column, value in enumerate(row)}
        columns: dict[str, int] = {}
        for key, aliases in HEADER_ALIASES.items():
            match = next((normalized[alias] for alias in aliases if alias in normalized), None)
            if match is not None:
                columns[key] = match
        if len(columns) == len(HEADER_ALIASES):
            return index, columns
    raise ValueError("The eBay template must contain Action, Item number, and Start price columns")


def _validate_job(job: EbayRevisionJob, account_key: str) -> None:
    if job.ebay_account_key != account_key:
        raise ValueError(f"Job {job.id} belongs to eBay account {job.ebay_account_key}, not {account_key}")
    if job.status != EbayRevisionJobStatus.queued.value:
        raise ValueError(f"Job {job.id} must be queued before it can be added to a revision sheet")
    if not job.guard_passed:
        raise ValueError(job.guard_reason or f"Job {job.id} did not pass its profit guard")
    if job.approval_required or job.approved_at is None:
        raise ValueError(f"Job {job.id} has not been approved")
