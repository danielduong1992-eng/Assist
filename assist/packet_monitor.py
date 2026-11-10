from __future__ import annotations

import json
import os
import platform
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from assist.threat_rules import (
    ThreatFinding,
    findings_for_listener,
    findings_for_outbound,
    findings_for_packet,
    findings_for_scan,
    merge_unique,
)

APP_DIR = Path.home() / ".assist"
ALERTS_FILE = APP_DIR / "alerts.json"


@dataclass
class Alert:
    id: str
    severity: str
    title: str
    detail: str
    category: str
    evidence: str
    created_at: str
    notified: bool = False

    @classmethod
    def from_finding(cls, finding: ThreatFinding) -> "Alert":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return cls(
            id=f"{stamp}-{finding.category}",
            severity=finding.severity,
            title=finding.title,
            detail=finding.detail,
            category=finding.category,
            evidence=finding.evidence,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )


@dataclass
class MonitorSnapshot:
    mode: str
    running: bool
    packet_count: int
    connection_samples: int
    last_error: str = ""
    alerts: list[Alert] = field(default_factory=list)


AlertCallback = Callable[[Alert], None]


class PacketMonitor:
    """Light defensive monitor: connections always, packets when permitted."""

    def __init__(self, on_alert: AlertCallback | None = None) -> None:
        self.on_alert = on_alert
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._alerts: list[Alert] = []
        self._seen_evidence: set[str] = set()
        self._recent_ports: deque[tuple[float, int]] = deque(maxlen=500)
        self._recent_hosts: deque[tuple[float, str]] = deque(maxlen=500)
        self.packet_count = 0
        self.connection_samples = 0
        self.mode = "idle"
        self.last_error = ""
        self._load_alerts()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> MonitorSnapshot:
        with self._lock:
            alerts = list(self._alerts)
        return MonitorSnapshot(
            mode=self.mode,
            running=self.running,
            packet_count=self.packet_count,
            connection_samples=self.connection_samples,
            last_error=self.last_error,
            alerts=alerts,
        )

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="assist-packet-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self.mode = "idle"

    def inject_finding(self, finding: ThreatFinding) -> Alert | None:
        """Test helper / manual signal injection."""
        return self._emit(finding)

    def _run(self) -> None:
        packet_ok = self._try_packet_loop_once()
        if packet_ok:
            self.mode = "packets+connections"
            packet_thread = threading.Thread(target=self._packet_loop, name="assist-packets", daemon=True)
            packet_thread.start()
        else:
            self.mode = "connections"

        while not self._stop.is_set():
            try:
                self._scan_connections()
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
            self._stop.wait(3.0)

    def _try_packet_loop_once(self) -> bool:
        if platform.system() == "Linux":
            try:
                sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
                sock.settimeout(0.5)
                sock.close()
                return True
            except (PermissionError, OSError) as exc:
                self.last_error = f"Packet capture unavailable ({exc}). Using connection analysis."
                return False
        # Windows raw capture needs Npcap/admin; keep connection mode light by default.
        self.last_error = "Packet capture needs admin/Npcap on Windows. Using connection analysis."
        return False

    def _packet_loop(self) -> None:
        try:
            sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
            sock.settimeout(0.8)
        except OSError as exc:
            self.last_error = str(exc)
            return

        try:
            while not self._stop.is_set():
                try:
                    frame, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    break
                self.packet_count += 1
                parsed = _parse_ethernet_frame(frame)
                if not parsed:
                    continue
                for finding in findings_for_packet(**parsed):
                    self._emit(finding)
                if parsed.get("dport"):
                    self._note_destination(parsed.get("dst") or "", int(parsed["dport"]))
                self._evaluate_scan_window()
        finally:
            sock.close()

    def _scan_connections(self) -> None:
        listeners, remotes = _list_sockets()
        self.connection_samples += 1
        for address, port in listeners:
            for finding in findings_for_listener(port, address):
                self._emit(finding)
        for local_port, remote_ip, remote_port in remotes:
            self._note_destination(remote_ip, remote_port)
            for finding in findings_for_outbound(remote_ip, remote_port, local_port):
                self._emit(finding)
        self._evaluate_scan_window()

    def _note_destination(self, host: str, port: int) -> None:
        now = time.time()
        if port:
            self._recent_ports.append((now, port))
        if host:
            self._recent_hosts.append((now, host))

    def _evaluate_scan_window(self) -> None:
        now = time.time()
        window = 12.0
        ports = {p for ts, p in self._recent_ports if now - ts <= window}
        hosts = {h for ts, h in self._recent_hosts if now - ts <= window}
        for finding in findings_for_scan(len(ports), len(hosts), window):
            self._emit(finding)

    def _emit(self, finding: ThreatFinding) -> Alert | None:
        evidence = finding.evidence or f"{finding.category}:{finding.title}"
        with self._lock:
            if evidence in self._seen_evidence:
                return None
            self._seen_evidence.add(evidence)
            alert = Alert.from_finding(finding)
            self._alerts.insert(0, alert)
            self._alerts = self._alerts[:100]
            self._save_alerts_unlocked()
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception:  # noqa: BLE001
                pass
        return alert

    def _load_alerts(self) -> None:
        try:
            if not ALERTS_FILE.exists():
                return
            raw = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            alerts: list[Alert] = []
            for item in raw[:100]:
                alerts.append(
                    Alert(
                        id=str(item.get("id") or time.time()),
                        severity=str(item.get("severity") or "info"),
                        title=str(item.get("title") or "Alert"),
                        detail=str(item.get("detail") or ""),
                        category=str(item.get("category") or "general"),
                        evidence=str(item.get("evidence") or ""),
                        created_at=str(item.get("created_at") or ""),
                        notified=bool(item.get("notified", True)),
                    )
                )
                if alerts[-1].evidence:
                    self._seen_evidence.add(alerts[-1].evidence)
            self._alerts = alerts
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._alerts = []

    def _save_alerts_unlocked(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        payload = [asdict(alert) for alert in self._alerts[:100]]
        ALERTS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def mark_notified(self, alert_id: str) -> None:
        with self._lock:
            for alert in self._alerts:
                if alert.id == alert_id:
                    alert.notified = True
                    break
            self._save_alerts_unlocked()

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts.clear()
            self._seen_evidence.clear()
            self._save_alerts_unlocked()


def _parse_ethernet_frame(frame: bytes) -> dict | None:
    if len(frame) < 14:
        return None
    eth_type = struct.unpack("!H", frame[12:14])[0]
    if eth_type != 0x0800:  # IPv4 only for light path
        return None
    ip = frame[14:]
    if len(ip) < 20:
        return None
    ihl = (ip[0] & 0x0F) * 4
    if len(ip) < ihl:
        return None
    protocol = ip[9]
    src = socket.inet_ntoa(ip[12:16])
    dst = socket.inet_ntoa(ip[16:20])
    payload = ip[ihl:]
    sport = dport = None
    flags = ""
    proto_name = {1: "ICMP", 6: "TCP", 17: "UDP"}.get(protocol, str(protocol))

    if protocol == 6 and len(payload) >= 14:  # TCP
        sport, dport = struct.unpack("!HH", payload[0:4])
        flag_byte = payload[13]
        parts = []
        if flag_byte & 0x02:
            parts.append("S")
        if flag_byte & 0x10:
            parts.append("A")
        if flag_byte & 0x01:
            parts.append("F")
        if flag_byte & 0x04:
            parts.append("R")
        flags = "".join(parts)
    elif protocol == 17 and len(payload) >= 4:  # UDP
        sport, dport = struct.unpack("!HH", payload[0:4])

    return {
        "protocol": proto_name,
        "src": src,
        "dst": dst,
        "sport": sport,
        "dport": dport,
        "flags": flags,
        "length": len(frame),
    }


def _list_sockets() -> tuple[list[tuple[str, int]], list[tuple[int, str, int]]]:
    system = platform.system()
    if system == "Linux":
        return _list_sockets_linux()
    if system == "Windows":
        return _list_sockets_windows()
    return [], []


def _list_sockets_linux() -> tuple[list[tuple[str, int]], list[tuple[int, str, int]]]:
    listeners: list[tuple[str, int]] = []
    remotes: list[tuple[int, str, int]] = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            local = parts[1]
            remote = parts[2]
            state = parts[3]
            lip, lport = _decode_proc_addr(local, ipv6=path.endswith("tcp6"))
            rip, rport = _decode_proc_addr(remote, ipv6=path.endswith("tcp6"))
            if state == "0A":  # LISTEN
                listeners.append((lip, lport))
            elif state == "01" and rip not in {"0.0.0.0", "::", "127.0.0.1", "::1"} and rport:
                remotes.append((lport, rip, rport))
    return listeners, remotes


def _decode_proc_addr(field: str, ipv6: bool = False) -> tuple[str, int]:
    ip_hex, port_hex = field.split(":")
    port = int(port_hex, 16)
    if ipv6:
        # Keep presentation simple; prefer mapped IPv4 when present.
        raw = bytes.fromhex(ip_hex)
        # /proc stores little-endian 32-bit words.
        words = [raw[i : i + 4][::-1] for i in range(0, 16, 4)]
        packed = b"".join(words)
        try:
            ip = socket.inet_ntop(socket.AF_INET6, packed)
        except OSError:
            ip = "::"
        return ip, port
    raw = bytes.fromhex(ip_hex)
    ip = socket.inet_ntoa(raw[::-1])
    return ip, port


def _list_sockets_windows() -> tuple[list[tuple[str, int]], list[tuple[int, str, int]]]:
    """Use netstat parsing as a light, dependency-free Windows fallback."""
    listeners: list[tuple[str, int]] = []
    remotes: list[tuple[int, str, int]] = []
    try:
        import subprocess

        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in completed.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local = parts[1]
            remote = parts[2]
            state = parts[3].upper()
            lip, lport = _split_endpoint(local)
            rip, rport = _split_endpoint(remote)
            if state == "LISTENING":
                listeners.append((lip, lport))
            elif state == "ESTABLISHED" and rip not in {"0.0.0.0", "127.0.0.1"} and rport:
                remotes.append((lport, rip, rport))
    except (OSError, ValueError):
        return [], []
    return listeners, remotes


def _split_endpoint(value: str) -> tuple[str, int]:
    if value.count(":") == 1:
        host, port_s = value.split(":")
        return host, int(port_s)
    # IPv6 like [::1]:445
    if value.startswith("["):
        host, port_s = value.rsplit("]:", 1)
        return host.strip("[]"), int(port_s)
    host, port_s = value.rsplit(":", 1)
    return host, int(port_s)


def can_use_packet_capture() -> bool:
    if platform.system() != "Linux":
        return False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
        sock.close()
        return True
    except OSError:
        return False
