#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from github_common import (
    GithubHttpError,
    ScraperError,
    bytes_to_text,
    cleanup_path,
    clone_blobless_no_checkout,
    collect_metadata_document,
    fetch_raw_file,
    git_show_file,
    is_rate_limitish,
    metadata_document,
    parse_repo,
    select_files,
    stderr_summary,
    temporary_workdir,
    write_json,
    write_jsonl_stream,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch selected files from a public GitHub repository as JSONL."
    )
    parser.add_argument("--repo", required=True, help="Repository as OWNER/REPO or a GitHub URL.")
    parser.add_argument("--ref", help="Branch, tag, or ref. Defaults to trying main, then master.")
    parser.add_argument(
        "--patterns",
        nargs="*",
        default=[],
        help="Path/name/glob patterns to include. Defaults to all files after excludes.",
    )
    parser.add_argument("--exclude", nargs="*", default=[], help="Additional glob patterns to exclude.")
    parser.add_argument("--metadata-only", action="store_true", help="Output matched metadata JSON only.")
    parser.add_argument(
        "--fetch-mode",
        choices=["auto", "raw", "git"],
        default="auto",
        help="Content fetch mode. Default: auto.",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto", "api-tree", "git-tree"],
        default="auto",
        help="Metadata strategy. Default: auto.",
    )
    parser.add_argument(
        "--raw-threshold",
        type=int,
        default=50,
        help="In auto mode, use raw fetching up to this many selected files. Default: 50.",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=500 * 1024,
        help="Maximum content bytes to include per file. Default: 512000.",
    )
    parser.add_argument("--include-secretish", action="store_true", help="Include secret-like paths.")
    parser.add_argument("--include-binary", action="store_true", help="Include binary/non-UTF8 content when possible.")
    parser.add_argument("--out", required=True, help="Output path. Use '-' for stdout.")
    parser.add_argument("--workdir", help="Working directory for git metadata or fetch mode.")
    parser.add_argument("--keep-workdir", action="store_true", help="Preserve generated git workdir.")
    return parser


def _matched_metadata_doc(doc: dict, selected: list[dict]) -> dict:
    owner, repo = parse_repo(doc["repo"])
    return metadata_document(owner, repo, doc["ref"], doc["strategy"], doc["truncated"], selected, doc["workdir"])


def _ensure_git_repo(
    owner: str,
    repo: str,
    ref: str,
    existing_workdir: str | None,
    workdir_arg: str | None,
    keep_workdir: bool,
    cleanup_targets: list[Path],
) -> Path:
    if existing_workdir:
        return Path(existing_workdir)
    if workdir_arg:
        repo_dir = Path(workdir_arg)
        if not keep_workdir:
            cleanup_targets.append(repo_dir)
    else:
        temp_root = temporary_workdir()
        repo_dir = temp_root / repo
        if not keep_workdir:
            cleanup_targets.append(temp_root)
    clone_blobless_no_checkout(owner, repo, ref, repo_dir)
    return repo_dir


def _content_row(
    meta: dict,
    data: bytes | None,
    fetch_source: str,
    max_file_size: int,
    include_binary: bool,
    skipped: str | None = None,
) -> dict:
    row = dict(meta)
    row["fetch_source"] = fetch_source
    if skipped:
        row["content"] = None
        row["skipped_content"] = skipped
        return row

    assert data is not None
    row["size"] = len(data)
    row["size_state"] = "known_after_fetch"
    if max_file_size is not None and len(data) > max_file_size:
        row["content"] = None
        row["skipped_content"] = "too_large"
        return row
    content, skipped_reason = bytes_to_text(data, include_binary=include_binary)
    row["content"] = content
    row["skipped_content"] = skipped_reason
    return row


def _known_too_large(meta: dict, max_file_size: int | None) -> bool:
    return (
        max_file_size is not None
        and isinstance(meta.get("size"), int)
        and meta["size"] > max_file_size
        and meta.get("size_state") == "known"
    )


def _raw_rows(owner: str, repo: str, ref: str, selected: list[dict], args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    for meta in selected:
        if _known_too_large(meta, args.max_file_size):
            rows.append(_content_row(meta, None, "raw-github", args.max_file_size, args.include_binary, "too_large"))
            continue
        try:
            data = fetch_raw_file(owner, repo, ref, meta["path"])
            rows.append(_content_row(meta, data, "raw-github", args.max_file_size, args.include_binary))
        except GithubHttpError as exc:
            if is_rate_limitish(exc):
                raise
            rows.append(
                _content_row(
                    meta,
                    None,
                    "raw-github",
                    args.max_file_size,
                    args.include_binary,
                    f"fetch_error: {exc}",
                )
            )
        except ScraperError as exc:
            rows.append(
                _content_row(
                    meta,
                    None,
                    "raw-github",
                    args.max_file_size,
                    args.include_binary,
                    f"fetch_error: {exc}",
                )
            )
    return rows


def _git_rows(
    repo_dir: Path,
    ref: str,
    selected: list[dict],
    args: argparse.Namespace,
) -> Iterable[dict]:
    for meta in selected:
        if _known_too_large(meta, args.max_file_size):
            yield _content_row(meta, None, "git-show", args.max_file_size, args.include_binary, "too_large")
            continue
        try:
            data = git_show_file(repo_dir, ref, meta["path"])
            yield _content_row(meta, data, "git-show", args.max_file_size, args.include_binary)
        except ScraperError as exc:
            yield _content_row(
                meta,
                None,
                "git-show",
                args.max_file_size,
                args.include_binary,
                f"fetch_error: {exc}",
            )


def _choose_fetch_mode(doc: dict, selected_count: int, args: argparse.Namespace) -> str:
    if args.fetch_mode != "auto":
        return args.fetch_mode
    if doc["strategy"] == "git-tree":
        return "git"
    if selected_count > args.raw_threshold:
        return "git"
    return "raw"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cleanup_targets: list[Path] = []
    try:
        doc, cleanup_target, kept_metadata_workdir = collect_metadata_document(
            args.repo, args.ref, args.strategy, args.workdir, args.keep_workdir
        )
        if cleanup_target is not None:
            cleanup_targets.append(cleanup_target)

        selected = select_files(
            doc["files"],
            args.patterns,
            args.exclude,
            args.max_file_size,
            args.include_secretish,
            args.include_binary,
        )

        if args.metadata_only:
            matched_doc = _matched_metadata_doc(doc, selected)
            write_json(args.out, matched_doc)
            stderr_summary(
                [
                    ("repo", doc["repo"]),
                    ("ref", doc["ref"]),
                    ("strategy", doc["strategy"]),
                    ("matched", len(selected)),
                    ("output", args.out),
                    ("workdir", doc["workdir"] or "none"),
                    (
                        "workdir_status",
                        "kept" if kept_metadata_workdir and doc["workdir"] else "cleaned/none",
                    ),
                ]
            )
            return 0

        owner, repo = parse_repo(doc["repo"])
        fetch_mode = _choose_fetch_mode(doc, len(selected), args)
        rows: Iterable[dict]
        if fetch_mode == "raw":
            try:
                rows = _raw_rows(owner, repo, doc["ref"], selected, args)
            except GithubHttpError as exc:
                if args.fetch_mode == "auto" and is_rate_limitish(exc):
                    repo_dir = _ensure_git_repo(
                        owner,
                        repo,
                        doc["ref"],
                        doc["workdir"],
                        args.workdir,
                        args.keep_workdir,
                        cleanup_targets,
                    )
                    fetch_mode = "git"
                    rows = _git_rows(repo_dir, doc["ref"], selected, args)
                else:
                    raise
        else:
            repo_dir = _ensure_git_repo(
                owner,
                repo,
                doc["ref"],
                doc["workdir"],
                args.workdir,
                args.keep_workdir,
                cleanup_targets,
            )
            rows = _git_rows(repo_dir, doc["ref"], selected, args)

        write_jsonl_stream(args.out, rows)
        stderr_summary(
            [
                ("repo", doc["repo"]),
                ("ref", doc["ref"]),
                ("strategy", doc["strategy"]),
                ("fetch_mode", fetch_mode),
                ("total_entries", doc["counts"]["entries"]),
                ("matched", len(selected)),
                ("fetched", len(selected)),
                ("output", args.out),
                ("workdir", doc["workdir"] or args.workdir or "none"),
                ("workdir_status", "kept" if args.keep_workdir and (doc["workdir"] or args.workdir) else "cleaned/none"),
            ]
        )
        return 0
    except ScraperError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        seen: set[Path] = set()
        for target in cleanup_targets:
            if target not in seen:
                cleanup_path(target)
                seen.add(target)


if __name__ == "__main__":
    raise SystemExit(main())
