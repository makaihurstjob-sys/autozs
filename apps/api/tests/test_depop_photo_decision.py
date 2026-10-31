import io

import httpx
import pytest
from PIL import Image


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 60, 80)).save(buffer, "JPEG")
    return buffer.getvalue()


class _Response:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://images.test/review.jpg")
            raise httpx.HTTPStatusError(
                "refused", request=request, response=httpx.Response(self.status_code, request=request)
            )


@pytest.fixture()
def isolated_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.routes.PROJECT_ROOT", tmp_path)
    return tmp_path


def _import_photo(client):
    product = client.post(
        "/products/import-captured",
        json={
            "source_url": "https://example.test/decision-bag",
            "title": "Decision bag",
            "source_price": 10,
            "source_in_stock": True,
            "image_urls": "https://images.test/cover.jpg",
        },
    ).json()
    imported = client.post(
        "/depop/amazon-import",
        json={
            "product_id": product["id"],
            "title": "Decision bag",
            "variations": [{"label": "Black", "asin": "BLACK", "image_url": "https://images.test/black.jpg"}],
            "review_photos": [{"image_url": "https://images.test/review.jpg", "review_id": "r1"}],
        },
    ).json()
    photo = next(item for item in imported["photos"] if item["kind"] == "review")
    return product, photo, imported["variants"][0]


def _state(client, product, photo, variant):
    photos = client.get(f"/depop/source-photos?product_id={product['id']}").json()
    variants = client.get(f"/depop/variants?product_id={product['id']}").json()
    return (
        next(item for item in photos if item["id"] == photo["id"]),
        next(item for item in variants if item["id"] == variant["id"]),
    )


def _approve(client, photo, variant):
    return client.post(
        f"/depop/source-photos/{photo['id']}/decision",
        json={"status": "approved", "variant_id": variant["id"]},
    )


def _artifact(root, product, photo):
    return root / "downloads" / "product_images" / str(product["id"]) / f"depop-{photo['id']}.jpg"


def _assert_not_approved(client, root, product, photo, variant, before_ids):
    after_photo, after_variant = _state(client, product, photo, variant)
    assert after_photo["status"] == "pending"
    assert after_photo["variant_id"] is None
    assert after_variant["image_ids"] == before_ids
    assert not _artifact(root, product, photo).exists()
    assert not list(root.rglob("*.part"))


def test_download_failure_does_not_save_approval(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)

    def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.api.routes.httpx.get", offline)
    response = _approve(client, photo, variant)
    assert response.status_code == 502
    assert "not approved" in response.json()["detail"]
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_http_error_status_does_not_save_approval(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(b"", 503))
    assert _approve(client, photo, variant).status_code == 502
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_undecodable_pixels_do_not_save_approval(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(b"<html>not an image</html>"))
    response = _approve(client, photo, variant)
    assert response.status_code == 502
    # The response body from the image host is never echoed back.
    assert "html" not in response.text.lower()
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_truncated_image_does_not_save_approval(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(_jpeg_bytes()[:200]))
    assert _approve(client, photo, variant).status_code == 502
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_artifact_save_failure_does_not_save_approval(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(_jpeg_bytes()))

    def disk_full(self, data):
        raise OSError("disk full")

    with monkeypatch.context() as patched:
        patched.setattr("pathlib.Path.write_bytes", disk_full)
        response = _approve(client, photo, variant)
    assert response.status_code == 500
    assert "not approved" in response.json()["detail"]
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_commit_failure_removes_new_artifact(client, monkeypatch, isolated_root) -> None:
    from sqlalchemy.orm import Session

    product, photo, variant = _import_photo(client)
    _, before = _state(client, product, photo, variant)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(_jpeg_bytes()))

    def locked(self):
        raise RuntimeError("database locked")

    with monkeypatch.context() as patched:
        patched.setattr(Session, "commit", locked)
        with pytest.raises(RuntimeError):
            _approve(client, photo, variant)
    _assert_not_approved(client, isolated_root, product, photo, variant, before["image_ids"])


def test_valid_photo_approval_saves_rendered_artifact_and_wires_variant(
    client, monkeypatch, isolated_root
) -> None:
    product, photo, variant = _import_photo(client)
    monkeypatch.setattr("app.api.routes.httpx.get", lambda *a, **k: _Response(_jpeg_bytes()))
    response = _approve(client, photo, variant)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    after_photo, after_variant = _state(client, product, photo, variant)
    assert after_photo["variant_id"] == variant["id"]
    assert len(after_variant["image_ids"]) == 1
    saved = _artifact(isolated_root, product, photo)
    with Image.open(saved) as rendered:
        assert rendered.size == (1200, 1200)
    assert not list(isolated_root.rglob("*.part"))


def test_reject_and_undo_do_not_need_a_download(client, monkeypatch, isolated_root) -> None:
    product, photo, variant = _import_photo(client)

    def must_not_download(*args, **kwargs):
        raise AssertionError("rejecting must not download")

    monkeypatch.setattr("app.api.routes.httpx.get", must_not_download)
    rejected = client.post(f"/depop/source-photos/{photo['id']}/decision", json={"status": "rejected"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    undone = client.post(
        f"/depop/source-photos/{photo['id']}/decision", json={"status": "pending", "variant_id": None}
    )
    assert undone.status_code == 200
    assert undone.json()["status"] == "pending"
