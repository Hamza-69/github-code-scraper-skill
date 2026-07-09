#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from github_common import (
    ScraperError,
    cleanup_path,
    collect_metadata_document,
    metadata_document,
    parse_repo,
    stderr_summary,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect tokenless metadata for files in a public GitHub repository."
    )
    parser.add_argument("--repo", required=True, help="Repository as OWNER/REPO or a GitHub URL.")
    parser.add_argument("--ref", help="Branch, tag, or ref. Defaults to trying main, then master.")
    parser.add_argument(
        "--strategy",
        choices=["auto", "api-tree", "git-tree"],
        default="auto",
        help="Metadata strategy. Default: auto.",
    )
    parser.add_argument("--out", required=True, help="Output JSON path. Use '-' for stdout.")
    parser.add_argument("--workdir", help="Working directory for git-tree strategy.")
    parser.add_argument("--keep-workdir", action="store_true", help="Preserve generated git workdir.")
    parser.add_argument(
        "--include-dirs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include directory metadata entries. Default: true.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cleanup_target: Path | None = None
    kept_workdir = False
    try:
        doc, cleanup_target, kept_workdir = collect_metadata_document(
            args.repo, args.ref, args.strategy, args.workdir, args.keep_workdir
        )
        if not args.include_dirs:
            doc["files"] = [meta for meta in doc["files"] if meta.get("type") != "directory"]
            doc["counts"] = metadata_document(
                *parse_repo(args.repo), doc["ref"], doc["strategy"], doc["truncated"], doc["files"], doc["workdir"]
            )["counts"]
        write_json(args.out, doc)
        stderr_summary(
            [
                ("repo", doc["repo"]),
                ("ref", doc["ref"]),
                ("strategy", doc["strategy"]),
                ("entries", doc["counts"]["entries"]),
                ("files", doc["counts"]["files"]),
                ("output", args.out),
                ("workdir", doc["workdir"] or "none"),
                ("workdir_status", "kept" if kept_workdir and doc["workdir"] else "cleaned/none"),
            ]
        )
        return 0
    except ScraperError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if cleanup_target is not None:
            cleanup_path(cleanup_target)


if __name__ == "__main__":
    raise SystemExit(main())
