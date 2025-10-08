import os
import sys
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import ttkbootstrap as tb
from PIL import Image, ImageTk

from WorkLens.config import load_config, save_config, AppConfig
from WorkLens.tracker import FocusTracker
from WorkLens.notifier import notify_off_task


def _resource_path(*paths: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, *paths)


class WorkLensApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WorkLens – AI Focus Tracker")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # Icons (PNG for window/iconphoto; ICO preferred for taskbar, especially when packaged)
        self.app_icon_image = None
        ico_path = _resource_path('images', 'icon.ico')
        png_path = _resource_path('images', 'logo.png')
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(default=ico_path)
            except Exception:
                pass
        if os.path.exists(png_path):
            try:
                with Image.open(png_path) as im:
                    im = im.convert('RGBA')
                    # Resize to a small icon size while keeping aspect ratio
                    max_side = 28
                    im.thumbnail((max_side, max_side), Image.LANCZOS)
                    self.app_icon_image = ImageTk.PhotoImage(im)
                self.root.iconphoto(True, self.app_icon_image)
            except Exception:
                self.app_icon_image = None

        # Center small window
        self.root.update_idletasks()
        width, height = 520, 340
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self.config = load_config()
        self.tracker = FocusTracker()

        pad = 8

        # Main form
        frm = tb.Frame(self.root, padding=pad)
        frm.pack(fill=tk.BOTH, expand=True)

        # Planned task
        tb.Label(frm, text="Planned Task").grid(row=0, column=0, sticky="w")
        self.task_var = tk.StringVar(value=self.config.planned_task)
        self.task_entry = tb.Entry(frm, textvariable=self.task_var, width=44)
        self.task_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(pad, 0))

        # Profession / Domain
        tb.Label(frm, text="Profession/Domain").grid(row=1, column=0, sticky="w")
        self.prof_var = tk.StringVar(value=self.config.profession)
        self.prof_entry = tb.Entry(frm, textvariable=self.prof_var, width=44)
        self.prof_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(pad, 0))

        # Interval
        tb.Label(frm, text="Interval (minutes)").grid(row=2, column=0, sticky="w")
        self.interval_var = tk.StringVar(value=str(self.config.interval_minutes))
        self.interval_entry = tb.Entry(frm, textvariable=self.interval_var, width=8)
        self.interval_entry.grid(row=2, column=1, sticky="w", padx=(pad, 0))

        # Buttons
        self.start_btn = tb.Button(frm, text="Start", command=self.on_start, bootstyle="success")
        self.start_btn.grid(row=3, column=0, pady=(pad, pad))

        self.update_btn = tb.Button(frm, text="Update Task", command=self.on_update_task, bootstyle="secondary")
        self.update_btn.grid(row=3, column=1, pady=(pad, pad))

        self.break_btn = tb.Button(frm, text="Break", command=self.on_break_toggle, state=tk.DISABLED, bootstyle="warning")
        self.break_btn.grid(row=3, column=2, pady=(pad, pad))

        self.stop_btn = tb.Button(frm, text="Stop", command=self.on_stop, state=tk.DISABLED, bootstyle="danger")
        self.stop_btn.grid(row=3, column=3, pady=(pad, pad))

        # Status labels
        self.status_var = tk.StringVar(value="Idle")
        tb.Label(frm, text="Status:").grid(row=4, column=0, sticky="w")
        self.status_lbl = tb.Label(frm, textvariable=self.status_var)
        self.status_lbl.grid(row=4, column=1, columnspan=3, sticky="w")

        self.reason_var = tk.StringVar(value="")
        tb.Label(frm, text="Reason:").grid(row=5, column=0, sticky="w")
        self.reason_lbl = tb.Label(frm, textvariable=self.reason_var, wraplength=380)
        self.reason_lbl.grid(row=5, column=1, columnspan=3, sticky="w")

        self.last_check_var = tk.StringVar(value="")
        tb.Label(frm, text="Last check:").grid(row=6, column=0, sticky="w")
        self.last_check_lbl = tb.Label(frm, textvariable=self.last_check_var)
        self.last_check_lbl.grid(row=6, column=1, columnspan=3, sticky="w")

        self.cost_var = tk.StringVar(value="$0.0000")
        tb.Label(frm, text="Cost so far:").grid(row=7, column=0, sticky="w")
        self.cost_lbl = tb.Label(frm, textvariable=self.cost_var)
        self.cost_lbl.grid(row=7, column=1, columnspan=3, sticky="w")

        self.break_var = tk.StringVar(value="")
        self.break_lbl = tb.Label(frm, textvariable=self.break_var)
        self.break_lbl.grid(row=8, column=0, columnspan=4, sticky="w")

        frm.columnconfigure(1, weight=1)

    # ---- Event handlers ----
    def on_start(self) -> None:
        planned = self.task_var.get().strip()
        profession = self.prof_var.get().strip()
        try:
            interval = int(self.interval_var.get().strip())
        except Exception:
            interval = 10
            self.interval_var.set(str(interval))

        self.start_btn.configure(state=tk.DISABLED)
        self.break_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED if False else tk.NORMAL)

        # Save config immediately
        save_config(AppConfig(
            planned_task=planned,
            interval_minutes=interval,
            image_width=self.config.image_width,
            api_key_env=self.config.api_key_env,
            profession=profession,
        ))

        # Start tracker and pass UI callback
        self.tracker.start(planned, interval, self._on_tracker_update, profession=profession)
        self.status_var.set("Started")
        self.reason_var.set("")

    def on_update_task(self) -> None:
        planned = self.task_var.get().strip()
        profession = self.prof_var.get().strip()
        try:
            interval = int(self.interval_var.get().strip())
        except Exception:
            interval = None
        self.tracker.update_task(planned_task=planned, interval_minutes=interval, profession=profession)

    def on_stop(self) -> None:
        self.tracker.stop()
        self.start_btn.configure(state=tk.NORMAL)
        self.break_btn.configure(state=tk.DISABLED, text="Break")
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_var.set("Stopped")
        self.break_var.set("")

    def on_break_toggle(self) -> None:
        self.tracker.toggle_break()

    # ---- UI callback from tracker (runs in worker thread) ----
    def _on_tracker_update(self, payload: dict) -> None:
        def apply():
            status = payload.get("status")
            if status:
                self.status_var.set(status)
            if "on_task" in payload and payload.get("on_task") is not None:
                self.status_var.set("On task" if payload.get("on_task") else "Off task")
            if "reason" in payload and payload.get("reason") is not None:
                self.reason_var.set(payload.get("reason") or "")
            if "last_check" in payload and payload.get("last_check"):
                self.last_check_var.set(payload.get("last_check"))
            if "cost" in payload and payload.get("cost") is not None:
                self.cost_var.set(f"${payload.get('cost'):.4f}")

            # Break UI
            if payload.get("break_active"):
                remaining = payload.get("break_remaining", 0)
                self.break_var.set(f"Break active – resumes in {remaining // 60:02d}:{remaining % 60:02d}")
                self.break_btn.configure(text="Resume")
            else:
                self.break_var.set("")
                self.break_btn.configure(text="Break")

            # Off-task notification (UI thread)
            notify = payload.get("notify")
            if notify and notify.get("type") == "off_task":
                try:
                    notify_off_task(notify.get("task", ""), notify.get("reason", ""))
                except Exception:
                    pass

        self.root.after(0, apply)


def main() -> None:
    root = tb.Window(themename="darkly")
    app = WorkLensApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
