"""CLI arg parsing + dispatch for the ablation harness (DB-touching only on run)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .config import DEFAULT_USER_ID, config_from_env


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ablation.run", description="Offline fusion-ablation harness")
    p.add_argument("--axis", action="append", dest="axes", help="target axis (repeatable)")
    p.add_argument("--user", default=DEFAULT_USER_ID, help="user_id")
    p.add_argument("--backend", default=None, help="mac_scaffold | desktop_gpu")
    p.add_argument("--max-set-size", type=int, default=None, dest="max_set_size")
    p.add_argument("--dry-run", action="store_true", help="evaluate + report, no promotion writes")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overrides: dict = {}
    if args.backend is not None:
        overrides["backend"] = args.backend
    if args.max_set_size is not None:
        overrides["max_set_size"] = args.max_set_size
    cfg = config_from_env(**overrides)

    from .runner import run_ablation

    out = run_ablation(args.user, args.axes, cfg, dry_run=args.dry_run)
    print(out["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
