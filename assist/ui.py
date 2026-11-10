from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any
from zoneinfo import ZoneInfo

from assist import storage
from assist.packet_monitor import Alert, PacketMonitor
from assist.threat_rules import ThreatFinding
from assist.weather import WeatherError, result_to_place, safe_fetch_weather, safe_search, weather_label


# Light desk palette — soft sky, warm paper, teal accent.
COLORS = {
    "bg": "#e8eef4",
    "bg_soft": "#f7f4ef",
    "panel": "#fffdf9",
    "ink": "#172033",
    "muted": "#4a5870",
    "line": "#d5dde8",
    "accent": "#1f6f6a",
    "accent_text": "#f7fffe",
    "danger": "#9b3b32",
    "warn": "#8a5a12",
    "warn_bg": "#fff4df",
    "danger_bg": "#f8e8e6",
    "chip": "#eef5f4",
}


class AssistApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Assist")
        self.geometry("380x520")
        self.minsize(320, 420)
        self.configure(bg=COLORS["bg"])

        self.places: list[dict[str, Any]] = storage.load_places()
        self.weather_by_id: dict[str, dict[str, Any]] = {}
        self._place_frames: dict[str, dict[str, Any]] = {}
        self._busy = False
        self._suggest_after: str | None = None
        self._alert_queue: list[Alert] = []
        self.monitor = PacketMonitor(on_alert=self._on_monitor_alert)

        self._setup_style()
        self._build()
        self._render_places()
        self._render_alerts()
        self.after(50, self.refresh_weather)
        self.after(1000, self._tick_clocks)
        self.after(10 * 60 * 1000, self._schedule_weather)
        self.after(200, self._start_monitor)
        self.after(400, self._drain_alert_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.bind("<Configure>", self._on_resize)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure(
            "Brand.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 18),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        style.configure(
            "Status.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        style.configure(
            "Guard.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "Name.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Region.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        style.configure(
            "Time.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Date.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        style.configure(
            "Temp.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["ink"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Condition.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(10, 4),
        )
        style.map(
            "Accent.TButton",
            background=[("!disabled", COLORS["accent"]), ("disabled", "#8aa9a6")],
            foreground=[("!disabled", COLORS["accent_text"]), ("disabled", "#f2f8f7")],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["line"],
            troughcolor=COLORS["bg_soft"],
            bordercolor=COLORS["bg"],
            arrowcolor=COLORS["muted"],
        )

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Root.TFrame", padding=(12, 10, 12, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Assist", style="Brand.TLabel").grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )

        search = ttk.Frame(header, style="Root.TFrame")
        search.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        search.columnconfigure(0, weight=1)

        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(search, textvariable=self.query_var, font=("Segoe UI", 9))
        self.query_entry.grid(row=0, column=0, sticky="ew", ipady=2, padx=(0, 6))
        self.query_entry.bind("<Return>", lambda _e: self.add_place())
        self.query_entry.bind("<KeyRelease>", self._on_query_typed)

        self.add_btn = ttk.Button(search, text="Add", style="Accent.TButton", command=self.add_place)
        self.add_btn.grid(row=0, column=1, sticky="e")

        self.alert_banner = tk.Frame(header, bg=COLORS["danger_bg"], highlightthickness=0)
        self.alert_banner.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.alert_banner.grid_remove()
        self.alert_banner_var = tk.StringVar(value="")
        tk.Label(
            self.alert_banner,
            textvariable=self.alert_banner_var,
            bg=COLORS["danger_bg"],
            fg=COLORS["danger"],
            font=("Segoe UI Semibold", 8),
            justify="left",
            anchor="w",
            padx=8,
            pady=4,
            wraplength=340,
        ).pack(fill="x")

        guard = ttk.Frame(header, style="Root.TFrame")
        guard.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        guard.columnconfigure(0, weight=1)
        ttk.Label(guard, text="Guard", style="Guard.TLabel").grid(row=0, column=0, sticky="w")
        self.guard_status_var = tk.StringVar(value="Starting…")
        ttk.Label(guard, textvariable=self.guard_status_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )
        actions = ttk.Frame(guard, style="Root.TFrame")
        actions.grid(row=0, column=2, sticky="e")
        tk.Button(
            actions,
            text="Clear",
            command=self.clear_alerts,
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            activebackground=COLORS["chip"],
            relief="groove",
            bd=1,
            cursor="hand2",
            font=("Segoe UI", 8),
            padx=6,
            pady=1,
        ).grid(row=0, column=0, padx=(0, 4))
        tk.Button(
            actions,
            text="Test",
            command=self._test_alert,
            bg=COLORS["accent"],
            fg=COLORS["accent_text"],
            activebackground=COLORS["accent"],
            activeforeground=COLORS["accent_text"],
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=2,
        ).grid(row=0, column=1)

        self.alerts_frame = ttk.Frame(header, style="Root.TFrame")
        self.alerts_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        self._suggest_results: list[dict[str, Any]] = []
        self.suggest_list = tk.Listbox(
            self,
            height=4,
            activestyle="dotbox",
            font=("Segoe UI", 8),
            bg=COLORS["panel"],
            fg=COLORS["ink"],
            selectbackground=COLORS["chip"],
            selectforeground=COLORS["ink"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            relief="flat",
            borderwidth=0,
        )
        self.suggest_list.bind("<Return>", self._on_suggest_activate)
        self.suggest_list.bind("<Double-Button-1>", self._on_suggest_activate)
        self.suggest_list.bind("<Escape>", lambda _e: self._hide_suggestions())

        body = ttk.Frame(self, style="Root.TFrame", padding=(12, 2, 12, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(body, bg=COLORS["bg"], highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.list_frame = ttk.Frame(self.canvas, style="Root.TFrame")
        self._list_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._on_list_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        footer = ttk.Label(
            self,
            text="Open-Meteo · local places · network guard",
            style="Muted.TLabel",
            padding=(12, 0, 12, 8),
        )
        footer.grid(row=2, column=0, sticky="w")

    def _on_list_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._list_window, width=event.width)

    def _on_resize(self, _event: tk.Event) -> None:
        # Keep layout fluid on smaller Windows windows.
        pass

    def _bind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux_up)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux_down)

    def _unbind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_mousewheel_linux_up(self, _event: tk.Event) -> None:
        self.canvas.yview_scroll(-1, "units")

    def _on_mousewheel_linux_down(self, _event: tk.Event) -> None:
        self.canvas.yview_scroll(1, "units")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.add_btn.configure(state=state)
        self.query_entry.configure(state=state)

    def _on_query_typed(self, _event: tk.Event) -> None:
        if self._suggest_after:
            self.after_cancel(self._suggest_after)
        query = self.query_var.get().strip()
        if len(query) < 2:
            self._hide_suggestions()
            return
        self._suggest_after = self.after(300, lambda: self._run_async("suggest", self._suggest_worker, query))

    def _suggest_worker(self, query: str) -> list[dict[str, Any]]:
        return safe_search(query)

    def _show_suggestions(self, results: list[dict[str, Any]]) -> None:
        self._suggest_results = results[:6]
        self.suggest_list.delete(0, tk.END)
        if not self._suggest_results:
            self._hide_suggestions()
            return
        for result in self._suggest_results:
            place = result_to_place(result)
            detail = ", ".join(part for part in (place["admin"], place["country"]) if part)
            text = f"{place['name']} — {detail}" if detail else place["name"]
            self.suggest_list.insert(tk.END, text)

        self.update_idletasks()
        x = self.query_entry.winfo_rootx() - self.winfo_rootx()
        y = self.query_entry.winfo_rooty() - self.winfo_rooty() + self.query_entry.winfo_height() + 4
        width = max(self.query_entry.winfo_width() + self.add_btn.winfo_width() + 8, 240)
        self.suggest_list.place(x=x, y=y, width=width)
        self.suggest_list.lift()
        self.suggest_list.selection_clear(0, tk.END)
        self.suggest_list.selection_set(0)
        self.suggest_list.activate(0)

    def _hide_suggestions(self) -> None:
        self._suggest_results = []
        self.suggest_list.delete(0, tk.END)
        self.suggest_list.place_forget()

    def _on_suggest_activate(self, _event: tk.Event | None = None) -> None:
        selection = self.suggest_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self._suggest_results):
            self._add_from_result(self._suggest_results[index])

    def add_place(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            return
        self._run_async("search", self._search_and_add_worker, query)

    def _search_and_add_worker(self, query: str) -> dict[str, Any]:
        results = safe_search(query)
        return {"query": query, "results": results}

    def _add_from_result(self, result: dict[str, Any]) -> None:
        place = result_to_place(result)
        if any(
            p["id"] == place["id"] or (p["name"] == place["name"] and p["country"] == place["country"])
            for p in self.places
        ):
            self.set_status(f"{place['name']} is already on your list.")
            self._hide_suggestions()
            self.query_var.set("")
            return

        self.places.insert(0, place)
        storage.save_places(self.places)
        self.query_var.set("")
        self._hide_suggestions()
        self.set_status(f"Added {place['name']}.")
        self._render_places()
        self.refresh_weather()

    def remove_place(self, place_id: str) -> None:
        removed = next((p for p in self.places if p["id"] == place_id), None)
        self.places = [p for p in self.places if p["id"] != place_id]
        self.weather_by_id.pop(place_id, None)
        storage.save_places(self.places)
        self.set_status(f"Removed {removed['name']}." if removed else "Place removed.")
        self._render_places()

    def refresh_weather(self) -> None:
        places_snapshot = [dict(p) for p in self.places]
        self._run_async("weather", self._weather_worker, places_snapshot)

    def _weather_worker(self, places: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return safe_fetch_weather(places)

    def _schedule_weather(self) -> None:
        self.refresh_weather()
        self.after(10 * 60 * 1000, self._schedule_weather)

    def _run_async(self, kind: str, worker, *args) -> None:
        if self._busy and kind == "search":
            return

        if kind == "search":
            self._set_busy(True)
            self.set_status("Searching…")

        def task() -> None:
            try:
                result = worker(*args)
            except WeatherError as exc:
                self.after(0, lambda: self._on_async_error(kind, str(exc)))
                return
            except Exception as exc:  # noqa: BLE001 - surface unexpected network/UI worker failures
                self.after(0, lambda: self._on_async_error(kind, str(exc)))
                return
            self.after(0, lambda: self._on_async_success(kind, result))

        threading.Thread(target=task, daemon=True).start()

    def _on_async_error(self, kind: str, message: str) -> None:
        if kind == "search":
            self._set_busy(False)
            self.set_status("Search failed. Check your connection.")
            messagebox.showerror("Assist", f"Could not search places.\n{message}")
        elif kind == "weather":
            self.set_status("Could not refresh weather. Times still update.")
        elif kind == "suggest":
            self._hide_suggestions()

    def _on_async_success(self, kind: str, result) -> None:
        if kind == "search":
            self._set_busy(False)
            results = result["results"]
            query = result["query"]
            if not results:
                self.set_status(f'No matches for “{query}”.')
                self._hide_suggestions()
                return
            exact = [
                item
                for item in results
                if str(item.get("name", "")).casefold() == query.casefold()
            ]
            chosen = exact[0] if exact else (results[0] if len(results) == 1 else None)
            if chosen is not None and (exact or len(results) == 1):
                self._add_from_result(chosen)
                return
            self._show_suggestions(results)
            self.set_status("Pick a place from the list, then press Enter.")
        elif kind == "weather":
            self.weather_by_id = result
            self._update_weather_labels()
            self.set_status("Weather updated.")
        elif kind == "suggest":
            self._show_suggestions(result)

    def _render_places(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._place_frames.clear()

        if not self.places:
            empty = ttk.Frame(self.list_frame, style="Card.TFrame", padding=10)
            empty.pack(fill="x", pady=3)
            ttk.Label(empty, text="No places yet — add a city above.", style="Region.TLabel").pack(anchor="w")
            return

        for place in self.places:
            self._build_place_card(place)
        self._update_weather_labels()
        self._tick_clocks()

    def _build_place_card(self, place: dict[str, Any]) -> None:
        card = tk.Frame(
            self.list_frame,
            bg=COLORS["panel"],
            highlightbackground=COLORS["line"],
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x", pady=3)

        inner = ttk.Frame(card, style="Card.TFrame", padding=(10, 8))
        inner.pack(fill="x")
        inner.columnconfigure(1, weight=1)

        left = ttk.Frame(inner, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nw")
        ttk.Label(left, text=place["name"], style="Name.TLabel").pack(anchor="w")
        region = ", ".join(part for part in (place["admin"], place["country"]) if part)
        if region:
            ttk.Label(left, text=region, style="Region.TLabel").pack(anchor="w")

        mid = ttk.Frame(inner, style="Card.TFrame")
        mid.grid(row=0, column=1, sticky="w", padx=(10, 0))
        time_lbl = ttk.Label(mid, text="--:--", style="Time.TLabel")
        time_lbl.pack(anchor="w")
        date_lbl = ttk.Label(mid, text="", style="Date.TLabel")
        date_lbl.pack(anchor="w")

        right = ttk.Frame(inner, style="Card.TFrame")
        right.grid(row=0, column=2, sticky="ne")
        temp_lbl = ttk.Label(right, text="—", style="Temp.TLabel")
        temp_lbl.pack(anchor="e")
        condition_lbl = ttk.Label(right, text="…", style="Condition.TLabel")
        condition_lbl.pack(anchor="e")
        extras_lbl = ttk.Label(right, text="", style="Condition.TLabel")
        # Keep extras label for updates, but hide dense humidity/wind in compact UI.
        extras_lbl.pack_forget()

        remove_btn = tk.Button(
            inner,
            text="×",
            command=lambda pid=place["id"]: self.remove_place(pid),
            bg=COLORS["panel"],
            fg=COLORS["danger"],
            activebackground=COLORS["chip"],
            activeforeground=COLORS["danger"],
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 11),
            padx=4,
            pady=0,
        )
        remove_btn.grid(row=0, column=3, sticky="ne", padx=(6, 0))

        self._place_frames[place["id"]] = {
            "time": time_lbl,
            "date": date_lbl,
            "temp": temp_lbl,
            "condition": condition_lbl,
            "extras": extras_lbl,
            "timezone": place["timezone"],
        }

    def _tick_clocks(self) -> None:
        now_utc = datetime.now().astimezone()
        for meta in self._place_frames.values():
            try:
                local = now_utc.astimezone(ZoneInfo(meta["timezone"]))
            except Exception:  # noqa: BLE001 - invalid tz falls back to local
                local = now_utc
            meta["time"].configure(text=local.strftime("%I:%M %p").lstrip("0"))
            meta["date"].configure(text=local.strftime("%a %b %d"))
        self.after(1000, self._tick_clocks)

    def _update_weather_labels(self) -> None:
        for place_id, meta in self._place_frames.items():
            weather = self.weather_by_id.get(place_id)
            if not weather:
                meta["temp"].configure(text="—")
                meta["condition"].configure(text="…")
                meta["extras"].configure(text="")
                continue
            temp = weather.get("temperature")
            meta["temp"].configure(text=f"{round(temp)}°" if isinstance(temp, (int, float)) else "—")
            meta["condition"].configure(text=weather_label(weather.get("weather_code")))
            meta["extras"].configure(text="")

    def _start_monitor(self) -> None:
        self.monitor.start()
        self._refresh_guard_status()
        self.after(4000, self._refresh_guard_status)

    def _refresh_guard_status(self) -> None:
        snap = self.monitor.snapshot()
        mode = snap.mode.replace("+", " + ")
        if snap.running:
            self.guard_status_var.set(f"{mode} · {len(snap.alerts)} alert(s)")
        else:
            self.guard_status_var.set("stopped")
        if snap.last_error and "Packet capture unavailable" in snap.last_error:
            # Soft note only — connection analysis still runs.
            pass
        if self.monitor.running:
            self.after(5000, self._refresh_guard_status)

    def _on_monitor_alert(self, alert: Alert) -> None:
        # Called from monitor thread — queue for UI thread.
        self._alert_queue.append(alert)

    def _drain_alert_queue(self) -> None:
        while self._alert_queue:
            alert = self._alert_queue.pop(0)
            self._notify_alert(alert)
        self.after(400, self._drain_alert_queue)

    def _notify_alert(self, alert: Alert) -> None:
        self._render_alerts()
        banner = f"{alert.severity.upper()}: {alert.title}"
        self.alert_banner_var.set(banner)
        bg = COLORS["danger_bg"] if alert.severity == "danger" else COLORS["warn_bg"]
        fg = COLORS["danger"] if alert.severity == "danger" else COLORS["warn"]
        self.alert_banner.configure(bg=bg)
        for child in self.alert_banner.winfo_children():
            child.configure(bg=bg, fg=fg)
        self.alert_banner.grid()
        self.set_status(f"Network guard: {alert.title}")
        self.monitor.mark_notified(alert.id)
        if alert.severity == "danger":
            # Non-blocking-ish notify: show warning dialog for dangerous events.
            messagebox.showwarning("Assist Network Guard", f"{alert.title}\n\n{alert.detail}")

    def _render_alerts(self) -> None:
        for child in self.alerts_frame.winfo_children():
            child.destroy()
        alerts = self.monitor.snapshot().alerts[:2]
        if not alerts:
            self.alert_banner.grid_remove()
            return
        for alert in alerts:
            card = tk.Frame(
                self.alerts_frame,
                bg=COLORS["panel"],
                highlightbackground=COLORS["line"],
                highlightthickness=1,
                bd=0,
            )
            card.pack(fill="x", pady=2)
            inner = ttk.Frame(card, style="Card.TFrame", padding=(8, 5))
            inner.pack(fill="x")
            title_color = COLORS["danger"] if alert.severity == "danger" else COLORS["warn"]
            tk.Label(
                inner,
                text=f"{alert.severity.upper()} · {alert.title}",
                bg=COLORS["panel"],
                fg=title_color,
                font=("Segoe UI Semibold", 8),
                anchor="w",
                justify="left",
                wraplength=340,
            ).pack(fill="x")


    def clear_alerts(self) -> None:
        self.monitor.clear_alerts()
        self.alert_banner.grid_remove()
        self._render_alerts()
        self.set_status("Alerts cleared.")

    def _test_alert(self) -> None:
        finding = ThreatFinding(
            severity="danger",
            title="Test: suspicious listener on port 4444",
            detail="Synthetic alert to verify notifications. No real threat was found.",
            category="test",
            evidence=f"test:{datetime.now().timestamp()}",
        )
        alert = self.monitor.inject_finding(finding)
        if alert:
            self._notify_alert(alert)

    def _on_close(self) -> None:
        try:
            self.monitor.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def run() -> None:
    app = AssistApp()
    app.mainloop()

