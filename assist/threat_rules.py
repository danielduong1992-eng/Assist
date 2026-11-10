from __future__ import annotations

"""Defensive heuristics for strange or dangerous network activity.

These rules are intentionally conservative and meant for personal
workstation awareness — not exploit tooling.
"""

from dataclasses import dataclass
from typing import Iterable


# High-confidence malware / remote-shell style ports.
MALWARE_PORTS: dict[int, str] = {
    4444: "Common remote-shell listener",
    5555: "Common remote-shell / ADB-over-TCP",
    6667: "IRC (often abused by bots)",
    6668: "IRC (often abused by bots)",
    6669: "IRC (often abused by bots)",
    31337: "Classic backdoor port",
    12345: "Classic backdoor port",
    27374: "Classic SubSeven-style port",
}

# Sensitive services — warn when exposed broadly, not every local Windows default.
SENSITIVE_PORTS: dict[int, str] = {
    23: "Cleartext Telnet",
    135: "Windows RPC endpoint mapper",
    139: "NetBIOS session",
    445: "SMB file share",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "Remote Desktop",
    5900: "VNC remote desktop",
}

SUSPICIOUS_PORTS: dict[int, str] = {**SENSITIVE_PORTS, **MALWARE_PORTS}

# Outbound destinations that are odd for a normal workstation baseline.
WATCH_OUTBOUND_PORTS = set(MALWARE_PORTS)

# Well-known safe-ish service ports we should not over-alert on as listeners.
COMMON_SAFE_LISTENERS = {
    22,
    53,
    80,
    443,
    853,
    993,
    995,
    8080,
    8443,
}


@dataclass(frozen=True)
class ThreatFinding:
    severity: str  # info | warn | danger
    title: str
    detail: str
    category: str
    evidence: str = ""


def classify_port(port: int) -> str | None:
    return SUSPICIOUS_PORTS.get(port)


def _is_local_only(address: str) -> bool:
    return address in {"127.0.0.1", "::1", "localhost", ""}


def findings_for_listener(port: int, address: str = "") -> list[ThreatFinding]:
    findings: list[ThreatFinding] = []
    if port in MALWARE_PORTS:
        findings.append(
            ThreatFinding(
                severity="danger",
                title=f"Suspicious listener on port {port}",
                detail=f"{MALWARE_PORTS[port]} is listening locally ({address or 'unknown'}).",
                category="listener",
                evidence=f"listen:{address}:{port}",
            )
        )
        return findings

    if port in SENSITIVE_PORTS and not _is_local_only(address) and address not in {"0.0.0.0", "::"}:
        # Bound to a specific non-local interface.
        findings.append(
            ThreatFinding(
                severity="warn",
                title=f"Sensitive service exposed on port {port}",
                detail=f"{SENSITIVE_PORTS[port]} is listening on {address}:{port}.",
                category="listener",
                evidence=f"listen:{address}:{port}",
            )
        )
    elif port in SENSITIVE_PORTS and address in {"0.0.0.0", "::", "*"}:
        findings.append(
            ThreatFinding(
                severity="warn",
                title=f"Sensitive service open on all interfaces ({port})",
                detail=f"{SENSITIVE_PORTS[port]} accepts connections on all interfaces.",
                category="listener",
                evidence=f"listen:{address}:{port}",
            )
        )
    return findings


def findings_for_outbound(remote_ip: str, remote_port: int, local_port: int = 0) -> list[ThreatFinding]:
    findings: list[ThreatFinding] = []
    if remote_port in WATCH_OUTBOUND_PORTS:
        label = classify_port(remote_port) or "Suspicious remote port"
        findings.append(
            ThreatFinding(
                severity="danger",
                title=f"Outbound connection to suspicious port {remote_port}",
                detail=f"Connection to {remote_ip}:{remote_port} ({label}).",
                category="outbound",
                evidence=f"out:{remote_ip}:{remote_port}:from:{local_port}",
            )
        )
    if remote_ip in {"0.0.0.0", "255.255.255.255"}:
        findings.append(
            ThreatFinding(
                severity="warn",
                title="Strange remote endpoint",
                detail=f"Traffic involving unusual address {remote_ip}:{remote_port}.",
                category="outbound",
                evidence=f"out:{remote_ip}:{remote_port}",
            )
        )
    return findings


def findings_for_scan(unique_ports: int, unique_hosts: int, window_seconds: float) -> list[ThreatFinding]:
    findings: list[ThreatFinding] = []
    if unique_ports >= 20 and window_seconds <= 15:
        findings.append(
            ThreatFinding(
                severity="danger",
                title="Possible port-scan pattern",
                detail=f"{unique_ports} distinct ports contacted in {window_seconds:.0f}s.",
                category="scan",
                evidence=f"scan:ports={unique_ports}:hosts={unique_hosts}:window={window_seconds:.1f}",
            )
        )
    elif unique_hosts >= 30 and window_seconds <= 20:
        findings.append(
            ThreatFinding(
                severity="warn",
                title="Burst of connections to many hosts",
                detail=f"{unique_hosts} remote hosts contacted in {window_seconds:.0f}s.",
                category="scan",
                evidence=f"burst:hosts={unique_hosts}:window={window_seconds:.1f}",
            )
        )
    return findings


def findings_for_packet(
    protocol: str,
    src: str,
    dst: str,
    sport: int | None,
    dport: int | None,
    flags: str = "",
    length: int = 0,
) -> list[ThreatFinding]:
    findings: list[ThreatFinding] = []
    proto = (protocol or "").upper()

    for port in (sport, dport):
        if port is None:
            continue
        label = classify_port(port)
        if label and port in WATCH_OUTBOUND_PORTS:
            findings.append(
                ThreatFinding(
                    severity="danger",
                    title=f"Packet hits watched port {port}",
                    detail=f"{proto} {src}:{sport} → {dst}:{dport} ({label}).",
                    category="packet",
                    evidence=f"pkt:{proto}:{src}:{sport}>{dst}:{dport}:{flags}",
                )
            )

    if proto == "TCP" and "S" in flags and "A" not in flags and dport and dport in SUSPICIOUS_PORTS:
        findings.append(
            ThreatFinding(
                severity="warn",
                title="SYN to sensitive service",
                detail=f"TCP SYN toward {dst}:{dport} ({classify_port(dport)}).",
                category="packet",
                evidence=f"syn:{dst}:{dport}",
            )
        )

    if length >= 1200 and proto in {"UDP", "ICMP"}:
        findings.append(
            ThreatFinding(
                severity="info",
                title="Large unusual datagram",
                detail=f"{proto} packet of {length} bytes {src} → {dst}.",
                category="packet",
                evidence=f"large:{proto}:{length}:{src}>{dst}",
            )
        )

    return findings


def merge_unique(findings: Iterable[ThreatFinding]) -> list[ThreatFinding]:
    seen: set[str] = set()
    out: list[ThreatFinding] = []
    for item in findings:
        key = f"{item.category}|{item.title}|{item.evidence}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
