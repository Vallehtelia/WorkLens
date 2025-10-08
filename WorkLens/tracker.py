from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from . import capture
from . import analyze
from .config import AppConfig, load_config, save_config


LOG_PATH = os.path.join(os.path.dirname(__file__), 'logs', 'activity.log')


def _append_log(line: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception:
        pass


class FocusTracker:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._ui_callback: Optional[Callable[[dict], None]] = None

        self.config: AppConfig = load_config()
        self.planned_task: str = self.config.planned_task
        self.interval_minutes: int = self.config.interval_minutes
        self.profession: str = self.config.profession

        self.input_tokens_total: int = 0
        self.output_tokens_total: int = 0
        self.cost_usd: float = 0.0

        self.last_status: Optional[bool] = None
        self.last_reason: str = ""
        self.last_check_time_utc: Optional[datetime] = None

        self.break_active: bool = False
        self.break_end_time_utc: Optional[datetime] = None

    # ---- Public API ----
    def start(self, planned_task: str, interval_minutes: int, ui_callback: Callable[[dict], None], profession: str = "") -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                # Update runtime parameters and continue
                self.planned_task = planned_task.strip()
                self.interval_minutes = max(1, int(interval_minutes))
                self.profession = profession.strip()
                self._ui_callback = ui_callback
                save_config(AppConfig(
                    planned_task=self.planned_task,
                    interval_minutes=self.interval_minutes,
                    image_width=self.config.image_width,
                    api_key_env=self.config.api_key_env,
                    profession=self.profession,
                ))
                # Wake loop to apply updates promptly
                self._wake_event.set()
                return

            self.planned_task = planned_task.strip()
            self.interval_minutes = max(1, int(interval_minutes))
            self.profession = profession.strip()
            self._ui_callback = ui_callback
            self._stop_event.clear()
            self._wake_event.clear()
            self.break_active = False
            self.break_end_time_utc = None

            # Persist config
            save_config(AppConfig(
                planned_task=self.planned_task,
                interval_minutes=self.interval_minutes,
                image_width=self.config.image_width,
                api_key_env=self.config.api_key_env,
                profession=self.profession,
            ))

            self._thread = threading.Thread(target=self._run_loop, name="WorkLensTracker", daemon=True)
            self._thread.start()
            self._emit_ui({
                "running": True,
                "status": "Started",
                "on_task": None,
                "reason": "",
                "cost": self.cost_usd,
                "last_check": "",
                "break_active": False,
                "break_remaining": 0,
            })

    def update_task(self, planned_task: Optional[str] = None, interval_minutes: Optional[int] = None, profession: Optional[str] = None) -> None:
        with self._lock:
            if planned_task is not None:
                self.planned_task = planned_task.strip()
            if interval_minutes is not None:
                try:
                    self.interval_minutes = max(1, int(interval_minutes))
                except Exception:
                    pass
            if profession is not None:
                self.profession = profession.strip()
            save_config(AppConfig(
                planned_task=self.planned_task,
                interval_minutes=self.interval_minutes,
                image_width=self.config.image_width,
                api_key_env=self.config.api_key_env,
                profession=self.profession,
            ))
            # Wake loop to apply updates promptly
            self._wake_event.set()
            self._emit_ui({
                "status": "Updated",
            })

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._emit_ui({"running": False, "status": "Stopped"})

    def toggle_break(self) -> None:
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                return
            if not self.break_active:
                self.break_active = True
                self.break_end_time_utc = datetime.now(timezone.utc) + timedelta(minutes=60)
            else:
                self.break_active = False
                self.break_end_time_utc = None
            # Interrupt sleep to enter/exit break immediately
            self._wake_event.set()

    # ---- Internal ----
    def _emit_ui(self, payload: dict) -> None:
        cb = self._ui_callback
        if cb:
            try:
                cb(payload)
            except Exception:
                pass

    def _compute_cost(self) -> float:
        # Pricing per prompt: $0.15 / 1M input tokens, $0.60 / 1M output tokens
        return (self.input_tokens_total / 1_000_000.0 * 0.15) + (self.output_tokens_total / 1_000_000.0 * 0.60)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if self._stop_event.is_set():
                return
            if self._wake_event.is_set():
                # Clear and return so loop can react to new state immediately
                self._wake_event.clear()
                return
            time.sleep(min(0.25, end - time.time()))

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            # Handle break state with 1-second ticks for countdown
            if self.break_active:
                while self.break_active and not self._stop_event.is_set():
                    remaining_s = 0
                    if self.break_end_time_utc:
                        remaining_s = max(0, int((self.break_end_time_utc - datetime.now(timezone.utc)).total_seconds()))
                        if remaining_s <= 0:
                            self.break_active = False
                            self.break_end_time_utc = None
                            break
                    self._emit_ui({
                        "break_active": True,
                        "break_remaining": remaining_s,
                        "status": "On break",
                    })
                    # Check frequently for resume
                    self._sleep_interruptible(1)
                # After break auto-resume, continue to next cycle without immediate capture
                continue

            # Capture and analyze
            try:
                jpeg_bytes = capture.capture_resized_jpeg(image_width=self.config.image_width, target_height=360, quality=70)
                result = analyze.analyze_screenshot(jpeg_bytes, self.planned_task, self.profession)
            except Exception as e:
                self._emit_ui({
                    "status": "Paused (capture/analysis error)",
                    "on_task": None,
                    "reason": str(e),
                })
                self._sleep_interruptible(self.interval_minutes * 60)
                continue

            # Update token usage and cost
            self.input_tokens_total += result.input_tokens
            self.output_tokens_total += result.output_tokens
            self.cost_usd = self._compute_cost()

            # Handle parse/API errors
            if result.parsed is None:
                self.last_status = None
                self.last_reason = result.error_message or "Parsing failed"
                self.last_check_time_utc = datetime.now(timezone.utc)
                iso = self.last_check_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
                _append_log(f"{iso} | planned=\"{self.planned_task}\" | on_task=? | reason=\"{self.last_reason}\" | cost=${self.cost_usd:.4f}")
                self._emit_ui({
                    "status": "Paused (API error)",
                    "on_task": None,
                    "reason": self.last_reason,
                    "last_check": iso,
                    "cost": self.cost_usd,
                })
                self._sleep_interruptible(self.interval_minutes * 60)
                continue

            # Successful parse
            fc = result.parsed
            self.last_status = bool(fc.on_task)
            self.last_reason = fc.reason
            self.last_check_time_utc = datetime.now(timezone.utc)

            # Log line
            iso = self.last_check_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            _append_log(
                f"{iso} | planned=\"{self.planned_task}\" | on_task={str(self.last_status)} | reason=\"{self.last_reason}\" | cost=${self.cost_usd:.4f}"
            )

            notify = None
            if not self.last_status:
                notify = {"type": "off_task", "task": self.planned_task, "reason": self.last_reason}

            self._emit_ui({
                "status": "On task" if self.last_status else "Off task",
                "on_task": self.last_status,
                "reason": self.last_reason,
                "last_check": iso,
                "cost": self.cost_usd,
                "break_active": False,
                "break_remaining": 0,
                "notify": notify,
            })

            self._sleep_interruptible(self.interval_minutes * 60)
