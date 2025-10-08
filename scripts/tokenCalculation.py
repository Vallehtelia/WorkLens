# tokenCalculation.py
# ------------------------------------------------------------
# Screenshots your desktop (Windows), resizes to multiple widths,
# sends each to OpenAI Responses API, and prints token usage + cost.
# Works with GPT-5 Nano / GPT-4o / GPT-4o-mini (vision + structured output).
# ------------------------------------------------------------

import io, os, time, base64
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from PIL import Image
import mss
from openai import OpenAI

# ----- config -----
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")   # or "gpt-4o-mini"
PRICE_INPUT_PER_MTOK  = float(os.getenv("PRICE_INPUT_PER_MTOK",  "0.15"))
PRICE_OUTPUT_PER_MTOK = float(os.getenv("PRICE_OUTPUT_PER_MTOK", "0.60"))
WIDTHS = [None, 1600, 1280, 1024]                       # None = original size
JPEG_QUALITY = 70
# -------------------

class Ack(BaseModel):
    ok: bool
    curr_task: str

def capture_fullscreen() -> Image.Image:
    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.rgb)

def to_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")

def resize_keep_aspect(img: Image.Image, target_w: Optional[int]) -> Image.Image:
    if target_w is None:
        return img
    W, H = img.size
    if W <= target_w:
        return img
    r = target_w / float(W)
    return img.resize((target_w, int(H * r)), Image.LANCZOS)

def to_jpeg_bytes(img: Image.Image, q: int = 60) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()

def est_cost(inp_tokens: int, out_tokens: int) -> float:
    return (inp_tokens / 1_000_000) * PRICE_INPUT_PER_MTOK + (out_tokens / 1_000_000) * PRICE_OUTPUT_PER_MTOK

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY")

    client = OpenAI()
    base = capture_fullscreen()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Captured screenshot: {base.size[0]}x{base.size[1]}")

    for w in WIDTHS:
        try:
            img = resize_keep_aspect(base, w)
            jpeg = to_jpeg_bytes(img, JPEG_QUALITY)

            t0 = time.time()
            resp = client.responses.parse(
                model=MODEL,
                top_p=1,
                max_output_tokens=64,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Return ONLY a valid JSON object matching the provided schema. "
                            "Do not include code fences, explanations, or text before/after. "
                            "Keys required: 'ok' (boolean) and 'curr_task' (string)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Acknowledge this image. "
                                    "curr_task should be what you think the current task is the user is doing. "
                                    "return {'ok': true, 'curr_task': The current task the user is doing. }. "
                                ),
                            },
                            {"type": "input_image", "image_url": to_data_url(jpeg)},
                        ],
                    },
                ],
                text_format=Ack,
            )
            dt = time.time() - t0

            usage = getattr(resp, "usage", None)
            in_tok = getattr(usage, "input_tokens", 0) if usage else 0
            out_tok = getattr(usage, "output_tokens", 0) if usage else 0
            cost = est_cost(in_tok, out_tok)

            parsed = getattr(resp, "output_parsed", None)
            if parsed is None:
                print("RAW OUTPUT:", getattr(resp, "output_text", None))

            ok_val = getattr(parsed, "ok", None)
            curr_task_val = getattr(parsed, "curr_task", None)

            print(
                f"→ {img.size[0]}x{img.size[1]} | {int(len(jpeg)/1024)} KB | "
                f"in:{in_tok} out:{out_tok} | cost:${cost:.6f} | "
                f"{dt:.2f}s | ok:{ok_val} | curr_task:{curr_task_val}"
            )

        except Exception as e:
            print(f"ERROR for width={w}: {e}")
            print("Hint: if this is a 400 about images, switch MODEL to 'gpt-4o' or 'gpt-4o-mini'.")

if __name__ == "__main__":
    main()