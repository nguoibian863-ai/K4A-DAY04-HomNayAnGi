"""One-off script: run a few real scenarios through the real agent loop
against the real OpenAI API, print the actual tool calls made.

NOTE: this environment's Application Control policy blocks the `jiter`
native DLL that the `openai`/`anthropic` SDKs import, so we call the OpenAI
Chat Completions HTTP API directly with `requests` (same request shape the
SDK would send) instead of going through providers/openai_provider.py.
This script is for gathering real REPORT.md evidence only; it is not part
of the submission and does not replace the project's own providers.
"""
from __future__ import annotations

import json
import os

import requests

from chat import ROOT, ARTIFACTS_DIR, now_iso, run_model_tool_loop
from env_loader import load_lab_env
from providers.base import ModelResponse, ToolCall
from tools import load_tool_declarations, to_openai_tools

load_lab_env(ROOT)

system_prompt = (ARTIFACTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
tool_declarations = load_tool_declarations(ARTIFACTS_DIR / "tools.yaml")
openai_tools = to_openai_tools(tool_declarations)


class RawOpenAIProvider:
    default_model = "gpt-4o-mini"

    def complete(self, messages, tools=None, *, model=None, temperature=0.0, tool_choice=None):
        api_key = os.getenv("OPENAI_API_KEY")
        body = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        calls = []
        for call in msg.get("tool_calls") or []:
            args = json.loads(call["function"].get("arguments") or "{}")
            calls.append(ToolCall(name=call["function"]["name"], args=args))
        return ModelResponse(text=msg.get("content"), tool_calls=calls, raw=data)


provider = RawOpenAIProvider()

SCENARIOS = [
    "VPN co bi loi khong?",
    "May tinh cua toi LT-204 bi cham, kiem tra giup",
    "Tao ticket bao cao may LT-204 bi cham, priority cao",
    "Co, toi xac nhan",
]

transcript = {
    "transcript_id": "demo_" + now_iso().replace(":", "-"),
    "provider": "openai (raw http, SDK blocked by Application Control policy)",
    "created_at": now_iso(),
    "turns": [],
}

history: list[dict[str, str]] = []
for i, user_text in enumerate(SCENARIOS, 1):
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_text},
    ]
    result = run_model_tool_loop(
        provider=provider,
        messages=messages,
        tools=openai_tools,
        model=None,
        max_tool_rounds=4,
    )
    print(f"\n=== Turn {i}: {user_text} ===")
    print("assistant_text:", result["assistant_text"])
    for round_ in result.get("rounds", []):
        for call in round_.get("tool_calls", []):
            print("  tool_call:", call.get("name"), call.get("arguments"))
        for ev in round_.get("tool_results", []):
            print("  tool_result:", json.dumps(ev, ensure_ascii=False)[:300])
    transcript["turns"].append({"turn_index": i, "user": user_text, **result})
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": result["assistant_text"]})

out_path = ROOT / "transcripts" / f"{transcript['transcript_id']}.demo.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print("\nSaved:", out_path)
