"""UX Designer model evaluation runner (Forge issue #32).

Sends the same screenshot + rubric prompt to a local Ollama vision model and
records structured findings, latency, and raw output for later comparison.

Usage:
    python3 evaluate_ux.py --model qwen3-vl:30b --screen overview [--theme natural]

Outputs JSON per run into runs/ keyed by model+screen+theme+timestamp.
Personal-data screenshots in atlas_shots/ stay local; never commit them.
"""

import argparse
import base64
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUBRIC = """You are acting as a UX Designer reviewing a personal health tracking dashboard.
Review the attached screenshot and respond with ONLY a JSON object (no markdown fence) shaped:

{
  "screen_summary": "2 sentences on what this screen shows and who it serves",
  "findings": [
    {
      "dimension": "one of: user-flow reasoning, screenshot interpretation, navigation, interaction design, visual consistency, accessibility, actionable feedback",
      "severity": "high|medium|low",
      "evidence": "what you observe in the screenshot that grounds this finding",
      "recommendation": "a specific change an engineer could implement and verify"
    }
  ],
  "top_priority": "the single most valuable change, and why",
  "open_questions": ["questions needing the product owner or data"]
}

Rules:
- Every finding's evidence must reference something actually visible in the screenshot.
- Recommendations must be concrete enough to implement and verify; no generic advice.
- Include at least one accessibility finding if any are visible (contrast, label pairing, target size, text size).
- Aim for 4-7 findings. Do not invent data or UI elements you cannot see.
"""

SCREEN_PROMPTS = {
    "overview": "This is the Overview page of the dashboard, the user's landing view.",
    "fitness": "This is the Strength/fitness page showing training progression.",
    "nutrition": "This is the Nutrition page showing logged food and quality breakdown.",
    "sleep": "This is the Sleep page.",
    "events": "This is the Events page.",
}


def run_once(model: str, image_path: Path, screen: str, theme: str) -> dict:
    prompt = SCREEN_PROMPTS[screen] + "\n\n" + RUBRIC
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt, "images": [image_b64]}
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }
    started = time.monotonic()
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=1800) as resp:
        data = json.loads(resp.read())
    elapsed = time.monotonic() - started
    content = data["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"_parse_error": True, "raw": content}
    return {
        "model": model,
        "screen": screen,
        "theme": theme,
        "image": str(image_path),
        "wall_seconds": round(elapsed, 1),
        "prompt_tokens": data.get("prompt_eval_count"),
        "output_tokens": data.get("eval_count"),
        "tokens_per_second": round(
            data.get("eval_count", 0) / max(data.get("eval_duration", 1) / 1e9, 0.001), 1
        ),
        "response": parsed,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--screen", required=True, choices=sorted(SCREEN_PROMPTS))
    parser.add_argument("--theme", default="natural")
    parser.add_argument("--shots-dir", default="atlas_shots")
    parser.add_argument("--out-dir", default="atlas_shots/runs")
    args = parser.parse_args()

    image_path = Path(args.shots_dir) / f"{args.screen}.png"
    if not image_path.exists():
        raise SystemExit(f"missing screenshot: {image_path}")
    result = run_once(args.model, image_path, args.screen, args.theme)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = f"{args.model.replace(':', '_')}--{args.screen}--{args.theme}--{stamp}.json"
    out_path = out_dir / slug
    out_path.write_text(json.dumps(result, indent=2))
    print(f"wrote {out_path}  wall={result['wall_seconds']}s  "
          f"tok/s={result['tokens_per_second']}")


if __name__ == "__main__":
    main()