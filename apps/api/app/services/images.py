from pathlib import Path

from PIL import Image, ImageFilter, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import PROJECT_ROOT
from app.models.domain import Product, ProductImage


def prepare_product_images_for_ebay(db: Session, product_id: int, size: int = 1000) -> tuple[int, int, list[ProductImage]] | None:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.id == product_id)
    )
    if product is None:
        return None
    prepared = 0
    attempted = 0
    relative_output_dir = Path("downloads") / "product_images" / str(product_id) / "edited"
    output_dir = PROJECT_ROOT / relative_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for image in sorted(product.images, key=lambda item: item.sort_order):
        if not image.local_path:
            continue
        source_path = _source_image_path(_project_path(image.local_path))
        if not source_path.exists():
            continue
        attempted += 1
        output_path = output_dir / f"{image.sort_order + 1:02d}.jpg"
        if _prepare_square_image(source_path, output_path, size=size):
            image.local_path = str(relative_output_dir / output_path.name)
            prepared += 1
    db.commit()
    refreshed = db.scalar(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.id == product_id)
    )
    return attempted, prepared, sorted(refreshed.images if refreshed else [], key=lambda item: item.sort_order)


def _prepare_square_image(source_path: Path, output_path: Path, size: int) -> bool:
    try:
        with Image.open(source_path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            margin = max(24, int(size * 0.04))
            target = max(1, size - (margin * 2))
            scale = target / max(image.width, image.height)
            resized = (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            )
            image = image.resize(resized, Image.Resampling.LANCZOS)
            if scale > 1:
                image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=3))
            canvas = Image.new("RGB", (size, size), "white")
            x = (size - image.width) // 2
            y = (size - image.height) // 2
            canvas.paste(image, (x, y))
            canvas.save(output_path, format="JPEG", quality=92, optimize=True)
        return True
    except Exception:
        return False


def _source_image_path(path: Path) -> Path:
    if path.parent.name != "edited":
        return path
    original = path.parent.parent / path.name
    return original if original.exists() else path


def _project_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
