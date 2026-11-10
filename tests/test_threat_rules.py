from assist.threat_rules import findings_for_listener, findings_for_outbound, findings_for_scan
from assist.packet_monitor import PacketMonitor
from assist.threat_rules import ThreatFinding


def test_malware_listener_is_danger():
    hits = findings_for_listener(4444, "0.0.0.0")
    assert hits and hits[0].severity == "danger"


def test_localhost_smb_is_quiet():
    assert findings_for_listener(445, "127.0.0.1") == []


def test_outbound_watch_port():
    hits = findings_for_outbound("203.0.113.9", 4444, 51234)
    assert hits and hits[0].severity == "danger"


def test_scan_pattern():
    hits = findings_for_scan(25, 3, 10)
    assert hits and hits[0].category == "scan"


def test_monitor_inject_and_dedupe():
    seen = []
    monitor = PacketMonitor(on_alert=seen.append)
    finding = ThreatFinding(
        severity="danger",
        title="unit",
        detail="detail",
        category="test",
        evidence="unit-evidence-1",
    )
    first = monitor.inject_finding(finding)
    second = monitor.inject_finding(finding)
    assert first is not None
    assert second is None
    assert len(seen) == 1
