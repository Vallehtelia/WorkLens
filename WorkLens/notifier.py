import os
import sys
from typing import Optional
import ctypes

from win10toast import ToastNotifier


_toaster: Optional[ToastNotifier] = None
_appid_set: bool = False


def _resource_path(*paths: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, *paths)


def _ensure_app_id() -> None:
    global _appid_set
    if _appid_set:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WorkLens.WorkLens")
        _appid_set = True
    except Exception:
        pass


def _get_toaster() -> ToastNotifier:
    global _toaster
    if _toaster is None:
        _ensure_app_id()
        _toaster = ToastNotifier()
    return _toaster


def _icon_path() -> Optional[str]:
    # Prefer packaged icon
    ico = _resource_path('images', 'icon.ico')
    if os.path.exists(ico):
        return ico
    # Fallback: try repo-relative icon
    here = os.path.dirname(__file__)
    alt = os.path.join(here, 'images', 'icon.ico')
    if os.path.exists(alt):
        return alt
    return None


def notify_off_task(task: str, reason: str) -> None:
    try:
        icon = _icon_path()
        _get_toaster().show_toast(
            title="WorkLens",
            msg=f"⚠️ Off task ({task}) – {reason}",
            icon_path=icon,
            duration=5,
            threaded=True,
        )
    except Exception:
        pass
