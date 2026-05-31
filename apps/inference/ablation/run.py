"""Entry module so `python -m ablation.run` works (delegates to cli.main)."""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
