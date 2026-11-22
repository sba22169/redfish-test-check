# Redfish Storage Test-Check

A small, runnable tool that connects to a server's BMC over the **DMTF / Dell
iDRAC Redfish** API, walks the storage inventory (controller → physical drives),
and **verifies each drive against a spec** — health, predicted-failure flag,
firmware revision, media type and capacity — producing a pass/fail report and a
non-zero exit code on any failure.

This is the automated incoming / inventory check a manufacturing test station
runs on every unit: *issue the query, read the result, verify it against spec,
pass or fail the unit*. It is the modern form of the controller status reads I
used to run on enterprise RAID storage — the same idea, a current API.

> Built as a learning / demonstration project. It ships with a **Redfish mock
> server** so it runs with no hardware, and is ready to point at a real Dell
> iDRAC with `--host/--user/--password`.

## Run it (no hardware needed)

```bash
pip install -r requirements.txt
python mock_server.py 8000 &                 # serves a mock Dell storage tree
python redfish_check.py --base-url http://localhost:8000 --spec spec.yaml
```

### Example output

```
============================================================
Controller RAID.Integrated.1-1  fw 8.6.0.0.0  [OK]
Drives found: 8  [OK]
------------------------------------------------------------
  [PASS] S000ACME   Disk.Bay.0:...:RAID.Integrated.1-1
  [PASS] S001ACME   Disk.Bay.1:...:RAID.Integrated.1-1
  [PASS] S002ACME   Disk.Bay.2:...:RAID.Integrated.1-1
  [FAIL] S003ACME   Disk.Bay.3:...:RAID.Integrated.1-1  -> health=Critical (want OK); failure predicted
  [PASS] S004ACME   Disk.Bay.4:...:RAID.Integrated.1-1
  [PASS] S005ACME   Disk.Bay.5:...:RAID.Integrated.1-1
  [FAIL] S006ACME   Disk.Bay.6:...:RAID.Integrated.1-1  -> firmware 2.4.0 < 2.6.0
  [PASS] S007ACME   Disk.Bay.7:...:RAID.Integrated.1-1
------------------------------------------------------------
OVERALL: FAIL
============================================================
```

The mock seeds two faults on purpose — a predicted-failure drive and a
down-rev-firmware drive — so the checker has something to catch. A full JSON
report is written to `report.json` (see `sample_output/` for a captured run).



## Against a real Dell iDRAC

```bash
python redfish_check.py --host 192.168.0.120 --user root --password '***' --spec spec.yaml
```

The iDRAC path uses HTTPS Basic auth and tolerates the self-signed iDRAC
certificate typical on a factory network. In production you would swap in the
DMTF `redfish` client (`redfish_client(...).login(auth="session")`); the
inventory-walk and verification logic are identical.

## The spec

`spec.yaml` defines what a good unit looks like — edit it per product:

```yaml
expected_drive_count: 8
required_health: "OK"
min_controller_firmware: "8.5.0.0.0"
min_drive_firmware: "2.6.0"
expected_media_type: "SSD"
min_capacity_gb: 1900
```

## Files

```
redfish_check.py   connect, walk storage inventory, verify vs spec, report + exit code
mock_server.py     minimal Redfish mock (realistic Dell iDRAC storage tree, 8 drives)
spec.yaml          per-product expected configuration / limits
sample_output/     a captured console + JSON report from a mock run
```


