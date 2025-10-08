# responses_parse_smoke.py  (OpenAI Python 2.2.0)
from pydantic import BaseModel
from openai import OpenAI

class Decision(BaseModel):
    alert: bool
    reason: str

client = OpenAI()

resp = client.responses.parse(
    model="gpt-5-nano",  # use a vision-capable model you have access to
    input=[
        {"role":"system","content":"Return a Decision JSON."},
        {"role":"user","content":"alert=false, reason='ok'."}
    ],
    text_format=Decision,  # <-- IMPORTANT in 2.2.0
)

print("usage:", resp.usage)
print("parsed:", resp.output_parsed)  # -> Decision(alert=False, reason='ok')