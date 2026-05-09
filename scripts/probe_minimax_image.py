#!/usr/bin/env python3
"""
probe_minimax_image.py — Standalone probe for MiniMax image generation.

NOT wired into the RSI framework. This is a capability test for option 3
(first-class image worker) — exercise the API on real prompts before
committing to schema changes in protocol.py / delegate.py.

The endpoint is NOT OpenAI-compatible (POST /v1/image_generation, not
/v1/images/generations), so the OpenAI SDK doesn't reach it. Stdlib urllib
keeps the dependency surface zero and makes the wire format explicit for
when we port this to a real adapter.

Usage:
    python3 scripts/probe_minimax_image.py "a small red cube on white"
    python3 scripts/probe_minimax_image.py "..." --aspect 16:9 --n 2
    python3 scripts/probe_minimax_image.py "..." --save .rsi/probe_images/

Exit codes: 0 = success, 1 = bad args, 2 = vendor error, 3 = network error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.minimaxi.chat/v1/image_generation"
DEFAULT_MODEL = "image-01"


def call_image_api(
    prompt: str,
    aspect_ratio: str,
    n: int,
    model: str,
    response_format: str,
    timeout: int = 60,
) -> tuple[dict, float]:
    """POST to MiniMax image_generation. Returns (parsed_response, latency_s)."""
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        print("ERROR: MINIMAX_API_KEY not set in environment.", file=sys.stderr)
        sys.exit(1)

    body = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "response_format": response_format,
        "n": n,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"ERROR: HTTP {exc.code} — {body}", file=sys.stderr)
        sys.exit(3)
    except urllib.error.URLError as exc:
        print(f"ERROR: network — {exc}", file=sys.stderr)
        sys.exit(3)

    latency = round(time.time() - start, 2)
    try:
        return json.loads(raw), latency
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSON response — {exc}\n{raw[:500]}", file=sys.stderr)
        sys.exit(2)


def download_image(url: str, target: Path, timeout: int = 60) -> int:
    """Fetch a presigned URL into target. Returns bytes written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = resp.read()
    target.write_bytes(data)
    return len(data)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Probe MiniMax image_generation endpoint.",
    )
    p.add_argument("prompt", help="Prompt text (quote it).")
    p.add_argument("--aspect", default="1:1", help="Aspect ratio (default 1:1).")
    p.add_argument("--n", type=int, default=1, help="Number of images (default 1).")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Model id (default {DEFAULT_MODEL}).")
    p.add_argument(
        "--format",
        dest="response_format",
        default="url",
        choices=["url", "base64"],
        help="Response format (default url).",
    )
    p.add_argument(
        "--save",
        metavar="DIR",
        help="Download returned URL(s) into this directory. Omit to print URLs only.",
    )
    p.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds (default 60).")
    args = p.parse_args()

    data, latency = call_image_api(
        prompt=args.prompt,
        aspect_ratio=args.aspect,
        n=args.n,
        model=args.model,
        response_format=args.response_format,
        timeout=args.timeout,
    )

    base_resp = data.get("base_resp") or {}
    status = base_resp.get("status_code")
    if status != 0:
        print(f"ERROR: vendor status_code={status} msg={base_resp.get('status_msg')!r}", file=sys.stderr)
        print(json.dumps(data, indent=2)[:1000], file=sys.stderr)
        sys.exit(2)

    request_id = data.get("id", "")
    payload = data.get("data") or {}
    urls = payload.get("image_urls") or []
    metadata = data.get("metadata") or {}

    print(f"OK  request_id={request_id}  latency={latency}s  count={len(urls)}")
    print(f"    metadata={json.dumps(metadata)}")
    for i, url in enumerate(urls):
        print(f"  [{i}] {url}")

    if args.save and urls:
        target_dir = Path(args.save)
        short_id = (request_id or "img")[:12]
        for i, url in enumerate(urls):
            target = target_dir / f"minimax_{short_id}_{i}.jpg"
            n_bytes = download_image(url, target, timeout=args.timeout)
            print(f"  saved [{i}] -> {target} ({n_bytes:,} bytes)")


if __name__ == "__main__":
    main()
