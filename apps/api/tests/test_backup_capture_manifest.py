import json
from pathlib import Path
import unittest

from app.services.backup_capture_manifest import build_backup_capture_manifest


class BackupCaptureManifestTests(unittest.TestCase):
    def test_supplier_scripts_survive_mixed_marketplace_match_groups(self):
        source_path = Path(__file__).resolve().parents[3] / "tools/chrome-extension/manifest.json"
        source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        backup = build_backup_capture_manifest(source)
        self.assertEqual(source["name"], "AutoZS Source Capture")
        for host in ("www.amazon.com", "amazon.com", "www.homedepot.com"):
            self.assertIn(f"https://{host}/*", backup["host_permissions"])
            self.assertTrue(any(
                f"https://{host}/dp/*" in script["matches"]
                if "amazon" in host else f"https://{host}/p/*" in script["matches"]
                for script in backup["content_scripts"] if "capture.js" in script["js"]
            ))
        for group in backup["content_scripts"]:
            self.assertFalse(any(host in match for match in group["matches"] for host in ("ebay.com", "depop.com", "lowes.com")))
        self.assertFalse(any("ebay.com" in p for p in backup["host_permissions"]))


if __name__ == "__main__":
    unittest.main()
