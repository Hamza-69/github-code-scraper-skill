#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from github_common import (
    GithubHttpError,
    RepoRefNotFoundError,
    ScraperError,
    candidate_refs,
    cleanup_path,
    clone_blobless_no_checkout,
    fetch_api_tree,
    git_tree_metadata,
    is_rate_limitish,
    metadata_document,
    parse_repo,
    stderr_summary,
    temporary_workdir,
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


def _git_document(
    owner: str,
    repo: str,
    ref: str,
    workdir_arg: str | None,
    keep_workdir: bool,
    truncated: bool,
) -> tuple[dict, Path | None, Path]:
    cleanup_target: Path | None = None
    if workdir_arg:
        repo_dir = Path(workdir_arg)
        cleanup_target = None if keep_workdir else repo_dir
    else:
        temp_root = temporary_workdir()
        repo_dir = temp_root / repo
        cleanup_target = None if keep_workdir else temp_root

    clone_blobless_no_checkout(owner, repo, ref, repo_dir)
    metas = git_tree_metadata(owner, repo, ref, repo_dir)
    doc = metadata_document(
        owner,
        repo,
        ref,
        "git-tree",
        truncated,
        metas,
        workdir=str(repo_dir),
    )
    return doc, cleanup_target, repo_dir


def collect_metadata(args: argparse.Namespace) -> tuple[dict, Path | None, bool]:
    owner, repo = parse_repo(args.repo)
    last_error: ScraperError | None = None

    for ref in candidate_refs(args.ref):
        try:
            if args.strategy == "git-tree":
                doc, cleanup_target, repo_dir = _git_document(
                    owner, repo, ref, args.workdir, args.keep_workdir, truncated=False
                )
                return doc, cleanup_target, args.keep_workdir

            metas, truncated = fetch_api_tree(owner, repo, ref)
            if args.strategy == "api-tree":
                if truncated:
                    raise ScraperError(
                        f"GitHub API tree is truncated for {owner}/{repo}@{ref}; "
                        "use --strategy auto or --strategy git-tree"
                    )
                doc = metadata_document(owner, repo, ref, "api-tree", False, metas)
                return doc, None, False

            if not truncated:
                doc = metadata_document(owner, repo, ref, "api-tree", False, metas)
                return doc, None, False

            doc, cleanup_target, repo_dir = _git_document(
                owner, repo, ref, args.workdir, args.keep_workdir, truncated=True
            )
            return doc, cleanup_target, args.keep_workdir
        except GithubHttpError as exc:
            last_error = exc
            if exc.status == 404 and args.ref is None:
                continue
            if args.strategy == "auto" and is_rate_limitish(exc):
                try:
                    doc, cleanup_target, repo_dir = _git_document(
                        owner, repo, ref, args.workdir, args.keep_workdir, truncated=True
                    )
                    return doc, cleanup_target, args.keep_workdir
                except ScraperError as git_exc:
                    last_error = git_exc
            break
        except RepoRefNotFoundError as exc:
            last_error = exc
            if args.ref is None:
                continue
            break
        except ScraperError as exc:
            last_error = exc
            break

    if last_error:
        raise last_error
    raise RepoRefNotFoundError(f"Unable to find a usable ref for {owner}/{repo}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cleanup_target: Path | None = None
    kept_workdir = False
    try:
        doc, cleanup_target, kept_workdir = collect_metadata(args)
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
