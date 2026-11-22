#!/usr/bin/env python3
"""
Redfish storage test-check.

Connects to a server's BMC over the DMTF/Dell Redfish API, walks the storage
inventory (controller -> physical drives), and verifies each drive against a
spec file (health, firmware revision, media/protocol, capacity). Prints a
pass/fail report and exits non-zero if anything fails — the kind of automated
incoming/inventory check a manufacturing test station runs on every unit.

This is the modern form of the controller status reads I used to run on
enterprise storage: issue the query, read the result, verify it against spec,
pass or fail the unit.

Examples
--------
Against the bundled mock (no hardware needed):
    python mock_server.py 8000 &            # in another shell
    python redfish_check.py --base-url http://localhost:8000 --spec spec.yaml

Against a real Dell iDRAC:
    python redfish_check.py --host 192.168.0.120 --user root --password '***' \
        --spec spec.yaml

Notes
-----
* The mock path uses plain requests (open, no auth).
* The --host path uses HTTPS Basic auth against iDRAC and disables cert
  verification for the self-signed iDRAC certificate (typical on a factory
  network). In production you would use the DMTF `redfish` library's
  `redfish_client(...).login(auth="session")` — the walk logic is identical.
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.parse

import requests
try:
    import yaml
except ImportError:                 # spec can also be given as JSON
    yaml = None


# ---------------------------------------------------------------------------
# tiny Redfish client (requests-based; mirrors the DMTF `redfish` library)
# ---------------------------------------------------------------------------
class Redfish:
    def __init__(self, base_url, auth=None, verify=True):
        self.base = base_url.rstrip("/")
        self.auth = auth
        self.verify = verify

    def get(self, uri):
        url = uri if uri.startswith("http") else self.base + uri
        r = requests.get(url, auth=self.auth, verify=self.verify, timeout=20)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# inventory walk
# ---------------------------------------------------------------------------
def collect_drives(rf: Redfish):
    """Return (controller_dict, [drive_dict, ...]) for the first system/controller."""
    root = rf.get("/redfish/v1")
    systems = rf.get(root["Systems"]["@odata.id"])
    system = rf.get(systems["Members"][0]["@odata.id"])
    storage = rf.get(system["Storage"]["@odata.id"])
    controller = rf.get(storage["Members"][0]["@odata.id"])
    drives = [rf.get(d["@odata.id"]) for d in controller.get("Drives", [])]
    return controller, drives


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------
def _ver_tuple(v):
    out = []
    for part in str(v).split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


def check_drive(drive, spec):
    """Return (passed, [reason, ...]) for one drive against the spec."""
    reasons = []
    health = drive.get("Status", {}).get("Health")
    if health != spec["required_health"]:
        reasons.append(f"health={health} (want {spec['required_health']})")
    if drive.get("FailurePredicted"):
        reasons.append("failure predicted")
    if _ver_tuple(drive.get("Revision", "0")) < _ver_tuple(spec["min_drive_firmware"]):
        reasons.append(f"firmware {drive.get('Revision')} < {spec['min_drive_firmware']}")
    if drive.get("MediaType") != spec["expected_media_type"]:
        reasons.append(f"media={drive.get('MediaType')} (want {spec['expected_media_type']})")
    cap_gb = drive.get("CapacityBytes", 0) / 1e9
    if cap_gb < spec["min_capacity_gb"]:
        reasons.append(f"capacity {cap_gb:.0f}GB < {spec['min_capacity_gb']}GB")
    return (len(reasons) == 0), reasons


def run(controller, drives, spec):
    results = []
    # controller-level checks
    ctrl_fw = controller.get("StorageControllers", [{}])[0].get("FirmwareVersion", "0")
    ctrl_ok = (controller.get("Status", {}).get("Health") == spec["required_health"]
               and _ver_tuple(ctrl_fw) >= _ver_tuple(spec["min_controller_firmware"]))
    # drive count
    count_ok = len(drives) == spec["expected_drive_count"]

    for d in drives:
        passed, reasons = check_drive(d, spec)
        results.append({"serial": d.get("SerialNumber"), "bay": d.get("Id"),
                        "passed": passed, "reasons": reasons})

    overall = ctrl_ok and count_ok and all(r["passed"] for r in results)
    return {
        "controller": controller.get("Id"),
        "controller_firmware": ctrl_fw,
        "controller_ok": ctrl_ok,
        "drive_count": len(drives),
        "drive_count_ok": count_ok,
        "drives": results,
        "overall_pass": overall,
    }


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def load_spec(path):
    text = open(path).read()
    if yaml and path.endswith((".yaml", ".yml")):
        return yaml.safe_load(text)
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser(description="Redfish storage test-check")
    ap.add_argument("--base-url", default="http://localhost:8000",
                    help="Redfish base URL (mock / open service)")
    ap.add_argument("--host", help="Dell iDRAC host (uses HTTPS + Basic auth)")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--spec", default="spec.yaml")
    ap.add_argument("--out", default="report.json")
    args = ap.parse_args()

    if args.host:
        rf = Redfish(f"https://{args.host}",
                     auth=(args.user, args.password), verify=False)
        requests.packages.urllib3.disable_warnings()
    else:
        rf = Redfish(args.base_url)

    spec = load_spec(args.spec)
    controller, drives = collect_drives(rf)
    report = run(controller, drives, spec)

    # console report
    print("=" * 60)
    print(f"Controller {report['controller']}  fw {report['controller_firmware']}  "
          f"[{'OK' if report['controller_ok'] else 'FAIL'}]")
    print(f"Drives found: {report['drive_count']}  "
          f"[{'OK' if report['drive_count_ok'] else 'FAIL'}]")
    print("-" * 60)
    for r in report["drives"]:
        tag = "PASS" if r["passed"] else "FAIL"
        extra = "" if r["passed"] else "  -> " + "; ".join(r["reasons"])
        print(f"  [{tag}] {r['serial']:<10} {r['bay']}{extra}")
    print("-" * 60)
    print(f"OVERALL: {'PASS' if report['overall_pass'] else 'FAIL'}")
    print("=" * 60)

    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    main()
