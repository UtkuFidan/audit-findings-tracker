"""Command line entry point: ``findings-tracker generate --seed 7``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .generate import write_dataset


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="findings-tracker")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Generate synthetic audit findings CSVs")
    gen.add_argument("--seed", type=int, default=7)
    gen.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        counts = write_dataset(args.out, args.seed)
        print(f"Wrote {args.out}/: " + ", ".join(f"{n} {k}" for k, n in counts.items()))


if __name__ == "__main__":
    main()
