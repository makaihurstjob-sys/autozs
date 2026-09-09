from app.services.importer import _infer_brand

def test_back_to_the_roots_brand_is_not_truncated():
    assert _infer_brand('Back to the Roots 12 qt. Organic Indoor Potting Mix Soil (1-Pack)') == 'Back to the Roots'
