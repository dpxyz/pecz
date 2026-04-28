#!/usr/bin/env python3
"""Test if a model is available and responds correctly."""
import json, sys, urllib.request

API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://172.17.0.1:32771/v1/chat/completions"
API_KEY = sys.argv[2] if len(sys.argv) > 2 else "ollama-cloud"
MODEL = sys.argv[3] if len(sys.argv) > 3 else None

if not MODEL:
    # Try candidates in order
    candidates = ["deepseek-v4-pro:cloud", "gemma4:31b-cloud"]
else:
    candidates = [MODEL]

for candidate in candidates:
    payload = json.dumps({
        "model": candidate,
        "messages": [{"role": "user", "content": "Reply with OK"}],
        "max_tokens": 10
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                print(f"✅ {candidate} responded: {content[:50]}")
                print(candidate)
                sys.exit(0)
            else:
                print(f"⚠️ {candidate} returned empty content (thinking model?)")
                # For thinking models, check reasoning field
                reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning", "").strip()
                if reasoning:
                    print(f"✅ {candidate} has reasoning (thinking model), accepting")
                    print(candidate)
                    sys.exit(0)
    except Exception as e:
        print(f"⚠️ {candidate} failed: {e}")

print("❌ No model available")
sys.exit(1)