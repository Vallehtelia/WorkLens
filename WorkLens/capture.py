from io import BytesIO
from typing import Tuple

import mss
from PIL import Image


def _grab_primary_monitor_rgb() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        raw = sct.grab(monitor)
        # mss returns BGRA; convert to RGB via BGRX
        img = Image.frombytes('RGB', (raw.width, raw.height), raw.bgra, 'raw', 'BGRX')
        return img


def capture_resized_jpeg(image_width: int = 1280, target_height: int = 360, quality: int = 70) -> bytes:
    """
    Capture the primary monitor, resize to target width, and center-crop vertically to ~target_height.
    Returns JPEG bytes with the given quality.
    """
    src = _grab_primary_monitor_rgb()
    if image_width > 0 and src.width != image_width:
        scale = image_width / float(src.width)
        resized_h = max(1, int(src.height * scale))
        src = src.resize((image_width, resized_h), Image.LANCZOS)

    # Center-crop to target height if taller
    if target_height > 0 and src.height > target_height:
        top = (src.height - target_height) // 2
        bottom = top + target_height
        src = src.crop((0, top, src.width, bottom))

    # Encode to JPEG
    buf = BytesIO()
    src.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()
