#!/usr/bin/env python3
"""
Minimal Redfish mock server for demo purpose .

Serves a small, realistic subset of a Dell iDRAC Redfish tree so that
`redfish_check.py` can be run and demonstrated without real hardware:

    ServiceRoot -> Systems -> System.Embedded.1 -> Storage
                -> RAID.Integrated.1-1 (PERC controller) -> Drives (8)

Note: Two drives are seeded with faults (one predicted-failure, one down-rev
firmware) so the checker has something to flag. The JSON shapes mirror the
real DMTF/Dell Redfish schema closely enough to port straight onto a live
iDRAC. Run:  python mock_server.py 8000
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

CONTROLLER = "RAID.Integrated.1-1"
SYS = "System.Embedded.1"
DRIVE_BASE = f"/redfish/v1/Systems/{SYS}/Storage/{CONTROLLER}/Drives"


def _drive(bay, health="OK", predicted=False, firmware="2.6.1", cap_gb=1920):
    did = f"Disk.Bay.{bay}:Enclosure.Internal.0-1:{CONTROLLER}"
    return {
        "@odata.id": f"{DRIVE_BASE}/{did}",
        "Id": did,
        "Name": f"Solid State Disk 0:1:{bay}",
        "MediaType": "SSD",
        "Protocol": "NVMe",
        "Manufacturer": "ACME",
        "Model": "MZ-NVME1920",
        "Revision": firmware,                 # drive firmware version
        "SerialNumber": f"S{bay:03d}ACME",
        "CapacityBytes": cap_gb * 1000 * 1000 * 1000,
        "FailurePredicted": predicted,
        "Status": {"Health": health, "State": "Enabled"},
    }


# Eight drives; bay 3 predicted-failure/critical, bay 6 down-rev firmware.
DRIVES = []
for b in range(8):
    if b == 3:
        DRIVES.append(_drive(b, health="Critical", predicted=True))
    elif b == 6:
        DRIVES.append(_drive(b, firmware="2.4.0"))
    else:
        DRIVES.append(_drive(b))

RESOURCES = {
    "/redfish/v1": {
        "@odata.id": "/redfish/v1", "Id": "RootService",
        "RedfishVersion": "1.13.0",
        "Systems": {"@odata.id": "/redfish/v1/Systems"},
    },
    "/redfish/v1/Systems": {
        "@odata.id": "/redfish/v1/Systems",
        "Members@odata.count": 1,
        "Members": [{"@odata.id": f"/redfish/v1/Systems/{SYS}"}],
    },
    f"/redfish/v1/Systems/{SYS}": {
        "@odata.id": f"/redfish/v1/Systems/{SYS}", "Id": SYS,
        "Model": "PowerEdge R760xa", "SerialNumber": "CNFCP00",
        "Storage": {"@odata.id": f"/redfish/v1/Systems/{SYS}/Storage"},
    },
    f"/redfish/v1/Systems/{SYS}/Storage": {
        "@odata.id": f"/redfish/v1/Systems/{SYS}/Storage",
        "Members@odata.count": 1,
        "Members": [{"@odata.id": f"/redfish/v1/Systems/{SYS}/Storage/{CONTROLLER}"}],
    },
    f"/redfish/v1/Systems/{SYS}/Storage/{CONTROLLER}": {
        "@odata.id": f"/redfish/v1/Systems/{SYS}/Storage/{CONTROLLER}",
        "Id": CONTROLLER, "Name": "PERC H965i Front",
        "Status": {"Health": "OK", "State": "Enabled"},
        "StorageControllers": [{
            "FirmwareVersion": "8.6.0.0.0",
            "Manufacturer": "DELL", "Model": "PERC H965i Front",
            "Status": {"Health": "OK"},
        }],
        "Drives@odata.count": len(DRIVES),
        "Drives": [{"@odata.id": d["@odata.id"]} for d in DRIVES],
    },
}
for d in DRIVES:
    RESOURCES[d["@odata.id"]] = d


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.rstrip("/") or "/redfish/v1"
        body = RESOURCES.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):          # keep the console quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Redfish mock serving on http://localhost:{port}/redfish/v1")
    HTTPServer(("localhost", port), Handler).serve_forever()
