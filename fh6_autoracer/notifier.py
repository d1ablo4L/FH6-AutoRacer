from __future__ import annotations
import csv
import datetime as dt
import threading
from pathlib import Path


def log_race(log_path, outcome: str, total: int) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "outcome", "total_races"])
        writer.writerow([
            dt.datetime.now().isoformat(timespec="seconds"),
            outcome, total,
        ])


def notify_autostop(race_count: int, sound: bool, toast: bool) -> None:
    def _run() -> None:
        if sound:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        if toast:
            try:
                from win11toast import toast as show_toast
                show_toast("AutoRacer",
                           f"Auto-stop reached ({race_count} this session)",
                           audio={"silent": "true"})
            except Exception:
                pass

    threading.Thread(target=_run, name="tool-notify", daemon=True).start()