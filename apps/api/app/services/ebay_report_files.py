import asyncio
import csv
from io import StringIO, TextIOWrapper
from pathlib import Path
import re
import shutil
from zipfile import BadZipFile, ZipFile

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.domain import EbaySyncRun, EbaySyncRunStatus
from app.services.ebay_sync import import_listing_report_rows


REPORT_FILE_PATTERN = re.compile(
    r"^ebay-(?P<report_type>active-listings)-(?P<account_key>[a-z0-9-]+)-run-(?P<run_id>\d+)\.(?P<extension>csv|tsv|txt|zip)$",
    re.IGNORECASE,
)


def ebay_report_inbox() -> Path:
    configured = str(get_settings().ebay_report_inbox or "").strip()
    return Path(configured).expanduser() if configured else Path.home() / "Downloads" / "AutoZS"


def parse_ebay_listing_report(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".zip":
        try:
            with ZipFile(path) as archive:
                names = [name for name in archive.namelist() if Path(name).suffix.lower() in {".csv", ".tsv", ".txt"}]
                if not names:
                    raise ValueError("The eBay report ZIP did not contain a CSV file.")
                with archive.open(names[0]) as source:
                    text = TextIOWrapper(source, encoding="utf-8-sig", errors="replace").read()
        except BadZipFile as exc:
            raise ValueError("The downloaded eBay report ZIP is invalid.") from exc
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        raise ValueError("The downloaded eBay report is empty.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in sample.splitlines()[0] else csv.excel
    rows = []
    for row in csv.DictReader(StringIO(text), dialect=dialect):
        cleaned = {str(key or "").strip(): str(value or "").strip() for key, value in row.items() if key is not None}
        if not any(cleaned.values()):
            continue
        cleaned.setdefault("Status", "Active")
        rows.append(cleaned)
    if not rows:
        raise ValueError("The eBay report did not contain any listing rows.")
    return rows


def import_ebay_report_file(db: Session, path: Path, run_id: int, account_key: str) -> EbaySyncRun:
    run = db.get(EbaySyncRun, run_id)
    if run is None:
        raise ValueError(f"AutoZS sync run {run_id} does not exist.")
    if run.account_key != account_key:
        raise ValueError(f"Report account {account_key} does not match sync run {run.account_key}.")
    if run.status == EbaySyncRunStatus.completed.value:
        return run
    run.status = EbaySyncRunStatus.running.value
    run.phase = "importing_report"
    run.report_filename = path.name
    run.message = f"Importing downloaded Active Listings report {path.name}."
    db.commit()
    rows = parse_ebay_listing_report(path)
    return import_listing_report_rows(
        db,
        rows=rows,
        account_key=account_key,
        run_id=run_id,
        source="automatic_active_listings_report",
        tombstone_missing=True,
    )


def scan_ebay_report_inbox(db: Session, inbox: Path | None = None) -> list[int]:
    root = inbox or ebay_report_inbox()
    root.mkdir(parents=True, exist_ok=True)
    imported: list[int] = []
    for path in sorted(root.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0):
        if not path.is_file() or path.name.endswith(".crdownload"):
            continue
        match = REPORT_FILE_PATTERN.match(path.name)
        if not match:
            continue
        run_id = int(match.group("run_id"))
        account_key = match.group("account_key").lower()
        try:
            run = import_ebay_report_file(db, path, run_id=run_id, account_key=account_key)
        except Exception as exc:
            db.rollback()
            run = db.get(EbaySyncRun, run_id)
            if run is not None:
                run.status = EbaySyncRunStatus.needs_review.value
                run.phase = "importing_report"
                run.message = f"Automatic report import failed: {exc}"
                db.commit()
            _archive_report(path, root / "failed")
            continue
        _archive_report(path, root / "processed")
        if run.status == EbaySyncRunStatus.completed.value:
            imported.append(run.id)
    return imported


def _archive_report(path: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / path.name
    if target.exists():
        target = directory / f"{path.stem}-{int(path.stat().st_mtime)}{path.suffix}"
    return Path(shutil.move(str(path), str(target)))


async def watch_ebay_report_inbox() -> None:
    settings = get_settings()
    interval = max(0.5, float(settings.ebay_report_watch_interval_seconds))
    while True:
        try:
            await asyncio.to_thread(_scan_with_local_session)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


def _scan_with_local_session() -> None:
    with SessionLocal() as db:
        scan_ebay_report_inbox(db)
