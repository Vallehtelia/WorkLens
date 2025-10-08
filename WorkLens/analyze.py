from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, ValidationError


class FocusCheck(BaseModel):
    on_task: bool
    reason: str


@dataclass
class AnalysisResult:
    parsed: Optional[FocusCheck]
    input_tokens: int
    output_tokens: int
    error_message: Optional[str] = None


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _to_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def analyze_screenshot(jpeg_bytes: bytes, planned_task: str, profession: str = "") -> AnalysisResult:
    client = _get_client()
    data_url = _to_data_url(jpeg_bytes)

    profession_hint = profession.strip()

    try:
        response = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a focus monitoring assistant. "
                        "Given a screenshot, a planned task, and the user's profession/domain, decide if the activity "
                        "appears related to the planned task within that professional context. Return a JSON object with: "
                        "'on_task' (boolean) and 'reason' (string). "
                        "Be conservative: if the evidence is ambiguous or typical supporting windows/tools for the profession could plausibly relate to the task, prefer on_task=true. "
                        "Only return on_task=false if the content clearly contradicts the planned task (e.g., unrelated entertainment, shopping, or social media). "
                        "Keep the reason concise."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"Planned task: {planned_task}. "
                                + (f"Profession/domain: {profession_hint}. " if profession_hint else "")
                                + "Analyze the following screenshot and respond only with JSON."
                            ),
                        },
                        {"type": "input_image", "image_url": data_url},
                    ],
                },
            ],
            text_format=FocusCheck,
            max_output_tokens=128,
        )

        parsed: Optional[FocusCheck] = response.output_parsed
        in_tokens = getattr(response.usage, 'input_tokens', 0) or 0
        out_tokens = getattr(response.usage, 'output_tokens', 0) or 0

        if parsed is None:
            return AnalysisResult(parsed=None, input_tokens=in_tokens, output_tokens=out_tokens, error_message="Parsing failed")

        return AnalysisResult(parsed=parsed, input_tokens=in_tokens, output_tokens=out_tokens)

    except ValidationError as ve:
        return AnalysisResult(parsed=None, input_tokens=0, output_tokens=0, error_message=f"Validation error: {ve}")
    except Exception as e:
        return AnalysisResult(parsed=None, input_tokens=0, output_tokens=0, error_message=str(e))
