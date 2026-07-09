#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat
import sys
import urllib.parse
from pathlib import Path
from typing import Iterable

from github_common import (
    GithubHttpError,
    RepoRefNotFoundError,
    ScraperError,
    bytes_to_text,
    candidate_refs,
    cleanup_path,
    download_file,
    enrich_meta,
    is_secretish_path,
    metadata_document,
    parse_repo,
    safe_extract_zip,
    select_files,
    stderr_summary,
    temporary_workdir,
    write_json,
    write_jsonl_stream,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download, safely extract, and optionally export a public GitHub repository ZIP."
    )
    parser.add_argument("--repo", required=True, help="Repository as OWNER/REPO or a GitHub URL.")
    parser.add_argument("--ref", help="Branch ref. Defaults to trying main, then master.")
    parser.add_argument("--workdir", help="Extraction parent directory.")
    parser.add_argument("--keep-workdir", action="store_true", help="Preserve extracted repository.")
    parser.add_argument("--cleanup", action="store_true", help="Delete extracted repository after exports.")
    parser.add_argument("--manifest-out", help="Optional manifest JSON output path.")
    parser.add_argument("--jsonl-out", help="Optional file content JSONL output path.")
    parser.add_argument("--metadata-only", action="store_true", help="Do not include content in JSONL rows.")
    parser.add_argument(
        "--patterns",
        nargs="*",
        default=[],
        help="Path/name/glob patterns to include. Defaults to all files after excludes.",
    )
    parser.add_argument("--exclude", nargs="*", default=[], help="Additional glob patterns to exclude.")
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=500 * 1024,
        help="Maximum content bytes to include per file. Default: 512000.",
    )
    parser.add_argument("--include-secretish", action="store_true", help="Include secret-like paths.")
    parser.add_argument("--include-binary", action="store_true", help="Include binary/non-UTF8 content when possible.")
    return parser


def codeload_zip_url(owner: str, repo: str, ref: str) -> str:
    owner_q = urllib.parse.quote(owner, safe="")
    repo_q = urllib.parse.quote(repo, safe="")
    ref_q = urllib.parse.quote(ref, safe="/")
    return f"https://codeload.github.com/{owner_q}/{repo_q}/zip/refs/heads/{ref_q}"


def _download_zip(owner: str, repo: str, explicit_ref: str | None, zip_path: Path) -> str:
    last_error: ScraperError | None = None
    for ref in candidate_refs(explicit_ref):
        try:
            download_file(codeload_zip_url(owner, repo, ref), zip_path)
            return ref
        except GithubHttpError as exc:
            last_error = exc
            if exc.status == 404 and explicit_ref is None:
                continue
            break
        except ScraperError as exc:
            last_error = exc
            break
    if last_error:
        raise last_error
    raise RepoRefNotFoundError(f"Unable to find a usable ZIP ref for {owner}/{repo}")


def _prepare_extract_dir(workdir: str | None) -> tuple[Path, Path | None]:
    if workdir:
        extract_dir = Path(workdir)
        if extract_dir.exists() and any(extract_dir.iterdir()):
            raise ScraperError(f"workdir already exists and is not empty: {extract_dir}")
        extract_dir.mkdir(parents=True, exist_ok=True)
        return extract_dir, None
    temp_root = temporary_workdir("github-code-scraper-zip-")
    extract_dir = temp_root / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    return extract_dir, temp_root


def _mode_for_path(path: Path) -> str:
    if path.is_symlink():
        return "120000"
    if path.is_dir():
        return "040000"
    mode = path.stat().st_mode
    return "100755" if mode & stat.S_IXUSR else "100644"


def _walk_metadata(root: Path, repo_name: str, ref: str) -> list[dict]:
    metas: list[dict] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        current_path = Path(current)
        if current_path != root:
            rel = current_path.relative_to(root).as_posix()
            metas.append(
                enrich_meta(
                    {
                        "repo": repo_name,
                        "ref": ref,
                        "path": rel,
                        "type": "directory",
                        "mode": "040000",
                        "sha": None,
                        "size": None,
                        "size_state": "known",
                        "source": "zip",
                    }
                )
            )
        for filename in filenames:
            path = current_path / filename
            rel = path.relative_to(root).as_posix()
            is_link = path.is_symlink()
            size = 0 if is_link else path.stat().st_size
            metas.append(
                enrich_meta(
                    {
                        "repo": repo_name,
                        "ref": ref,
                        "path": rel,
                        "type": "symlink" if is_link else "file",
                        "mode": _mode_for_path(path),
                        "sha": None,
                        "size": size,
                        "size_state": "known",
                        "source": "zip",
                    }
                )
            )
    return metas


def _selected_manifest_entries(all_metas: list[dict], selected_files: list[dict], include_secretish: bool) -> list[dict]:
    selected_paths = {meta["path"] for meta in selected_files}
    entries: list[dict] = []
    for meta in all_metas:
        if meta.get("type") == "directory":
            if not include_secretish and is_secretish_path(meta["path"]):
                continue
            entries.append(meta)
        elif meta["path"] in selected_paths:
            entries.append(meta)
    return entries


def _jsonl_rows(root: Path, selected_files: list[dict], args: argparse.Namespace) -> Iterable[dict]:
    for meta in selected_files:
        row = dict(meta)
        row["fetch_source"] = "zip"
        if args.metadata_only:
            row["content"] = None
            row["skipped_content"] = "metadata_only"
            yield row
            continue
        if isinstance(meta.get("size"), int) and meta["size"] > args.max_file_size:
            row["content"] = None
            row["skipped_content"] = "too_large"
            yield row
            continue
        try:
            data = (root / meta["path"]).read_bytes()
            row["size"] = len(data)
            row["size_state"] = "known_after_fetch"
            content, skipped = bytes_to_text(data, include_binary=args.include_binary)
            row["content"] = content
            row["skipped_content"] = skipped
        except OSError as exc:
            row["content"] = None
            row["skipped_content"] = f"fetch_error: {exc}"
        yield row


def _should_keep_extraction(args: argparse.Namespace) -> bool:
    if args.keep_workdir:
        return True
    if args.cleanup:
        return False
    exports_requested = bool(args.manifest_out or args.jsonl_out)
    if args.workdir:
        return True
    return not exports_requested


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.keep_workdir and args.cleanup:
        parser.error("--keep-workdir and --cleanup cannot be used together")

    zip_temp = temporary_workdir("github-code-scraper-zipdl-")
    extract_cleanup_target: Path | None = None
    try:
        owner, repo = parse_repo(args.repo)
        extract_dir, temp_extract_root = _prepare_extract_dir(args.workdir)
        zip_path = zip_temp / "repo.zip"
        ref = _download_zip(owner, repo, args.ref, zip_path)
        extracted_root = safe_extract_zip(zip_path, extract_dir)

        all_metas = _walk_metadata(extracted_root, f"{owner}/{repo}", ref)
        selected_files = select_files(
            all_metas,
            args.patterns,
            args.exclude,
            args.max_file_size,
            args.include_secretish,
            args.include_binary,
        )
        manifest_entries = _selected_manifest_entries(all_metas, selected_files, args.include_secretish)
        manifest = metadata_document(owner, repo, ref, "zip", False, manifest_entries, str(extracted_root))

        if args.manifest_out:
            write_json(args.manifest_out, manifest)
        if args.jsonl_out:
            write_jsonl_stream(args.jsonl_out, _jsonl_rows(extracted_root, selected_files, args))

        keep_extraction = _should_keep_extraction(args)
        if not keep_extraction:
            extract_cleanup_target = Path(args.workdir) if args.workdir else temp_extract_root

        stderr_summary(
            [
                ("repo", f"{owner}/{repo}"),
                ("ref", ref),
                ("strategy", "zip"),
                ("entries", manifest["counts"]["entries"]),
                ("matched", len(selected_files)),
                ("manifest_out", args.manifest_out or "none"),
                ("jsonl_out", args.jsonl_out or "none"),
                ("workdir", str(extracted_root)),
                ("workdir_status", "kept" if keep_extraction else "cleaned"),
            ]
        )
        return 0
    except ScraperError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        cleanup_path(zip_temp)
        if extract_cleanup_target is not None:
            cleanup_path(extract_cleanup_target)


if __name__ == "__main__":
    raise SystemExit(main())
