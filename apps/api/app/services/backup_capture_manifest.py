"""Build the supplier-only failover extension without dropping shared scripts."""
from copy import deepcopy
from urllib.parse import urlsplit


def build_backup_capture_manifest(source: dict) -> dict:
    manifest = deepcopy(source)
    hosts = {
        "www.homedepot.com", "delivery-tracker.pr-sc-delivery-execution.gcp.homedepot.com",
        "amazon.com", "www.amazon.com", "desktop-56u49jf.tailb2892a.ts.net",
        "127.0.0.1", "localhost",
    }

    def allowed(pattern: str) -> bool:
        return urlsplit(pattern).hostname in hosts

    manifest["name"] = "AutoZS Home Depot Backup Capture"
    manifest["description"] = "Supplier-only Home Depot/Amazon failover worker. No marketplace jobs."
    manifest["host_permissions"] = [p for p in manifest.get("host_permissions", []) if allowed(p)]
    scripts = []
    for script in manifest.get("content_scripts", []):
        script["matches"] = [p for p in script.get("matches", []) if allowed(p)]
        if script["matches"]:
            scripts.append(script)
    manifest["content_scripts"] = scripts
    resources = []
    for resource in manifest.get("web_accessible_resources", []):
        resource["matches"] = [p for p in resource.get("matches", []) if allowed(p)]
        if resource["matches"]:
            resources.append(resource)
    manifest["web_accessible_resources"] = resources
    return manifest
