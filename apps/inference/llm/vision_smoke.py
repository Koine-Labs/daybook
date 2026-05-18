"""Smoke test: send the Koine wisp logo to Codex `input_image`.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m llm.vision_smoke

Codex multimodal may not be enabled on the consumer ChatGPT plan. If so, the
test prints the exact 4xx body so you know what the backend said and exits
with a clear pass/fail report.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .auth.session import get_sign_in_status
from .vision import VisionNotAvailableError, describe_image


LOGO_PATH = Path(
    "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Logo/Clear-Koine-Wisp.png"
)


def main() -> int:
    print("=== Daybook vision smoke test ===\n")

    status = get_sign_in_status()
    if not status.signed_in:
        print(
            "Not signed in. Run first:\n"
            "  python -m llm.auth.sign_in",
            file=sys.stderr,
        )
        return 1
    print(
        f"Signed in as {status.identity.email or status.identity.account_id}\n"
    )

    if not LOGO_PATH.exists():
        print(f"Logo file not found at {LOGO_PATH}", file=sys.stderr)
        return 1

    size_kb = LOGO_PATH.stat().st_size / 1024
    print(f"Test image: {LOGO_PATH.name} ({size_kb:.1f} KB)\n")

    print("[Test 1] describe_image() via Codex `input_image` ...")
    t0 = time.monotonic()
    try:
        description = describe_image(
            image_path=LOGO_PATH,
            prompt="Describe this image in 1-2 plain sentences. Be concrete about subject, color, and mood.",
        )
        dt = time.monotonic() - t0
        print(f"  PASS in {dt:.1f}s")
        print(f"  description: {description!r}\n")
    except VisionNotAvailableError as e:
        dt = time.monotonic() - t0
        print(f"  FAIL — Codex multimodal NOT available (after {dt:.1f}s)")
        print(f"  reason: {e}")
        print(
            "\n  This means walking_remark.remark_on_image will fall back to "
            "an abstract description. We need either:\n"
            "    (a) an Anthropic API key for Claude Vision, or\n"
            "    (b) a local vision model (e.g. LLaVA / Qwen-VL)\n"
        )
        return 2
    except Exception as e:
        dt = time.monotonic() - t0
        print(f"  FAIL — unexpected error after {dt:.1f}s")
        print(f"  {type(e).__name__}: {e}")
        return 1

    print("=== Vision smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
