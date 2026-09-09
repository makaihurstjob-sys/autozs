from app.services.importer import _apply_description_template


def test_existing_wrapped_description_removes_supplier_navigation_only():
    content = '<div data-autozs-template="1"><ul><li>8 spray patterns</li><li>Truck &amp; Tool Rental</li><li>Return Policy</li></ul><p>Returns follow the listing policy.</p></div>'
    cleaned = _apply_description_template("Hose nozzle", content, {"description_template_enabled": True})
    assert "8 spray patterns" in cleaned
    assert "Returns follow the listing policy." in cleaned
    assert "Truck" not in cleaned
    assert "Return Policy" not in cleaned
    assert cleaned.count("data-autozs-template") == 1
