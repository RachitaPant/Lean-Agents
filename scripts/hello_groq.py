"""Phase 0 smoke test: one plain chat completion + one tool call against Groq.

Uses Groq's OpenAI-compatible endpoint so the provider stays swappable
(set GROQ_BASE_URL / GROQ_MODEL to point at Gemini's OpenAI-compatible endpoint or Ollama instead).

Usage:  python scripts/hello_groq.py
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current temperature for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Pune'"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["city"],
        },
    },
}


def fake_get_weather(city: str, unit: str = "celsius") -> dict:
    return {"city": city, "temperature": 31 if unit == "celsius" else 88, "unit": unit}


def main() -> int:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 1
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # 1. Plain chat completion
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: hello from groq"}],
    )
    print(f"[chat] {resp.choices[0].message.content!r}")
    print(f"[chat] tokens: {resp.usage.prompt_tokens} prompt / {resp.usage.completion_tokens} completion")

    # 2. Tool call round trip
    messages = [{"role": "user", "content": "What's the temperature in Pune right now?"}]
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, tools=[WEATHER_TOOL], tool_choice="auto"
    )
    msg = resp.choices[0].message
    if not msg.tool_calls:
        print(f"[tool] FAIL: model answered without calling the tool: {msg.content!r}")
        return 1
    call = msg.tool_calls[0]
    args = json.loads(call.function.arguments)
    print(f"[tool] model called {call.function.name}({args})")

    result = fake_get_weather(**args)
    messages += [
        msg.model_dump(exclude_none=True),
        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)},
    ]
    final = client.chat.completions.create(model=MODEL, messages=messages, tools=[WEATHER_TOOL])
    print(f"[tool] final answer: {final.choices[0].message.content!r}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
