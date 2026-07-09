from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Iterator


EXIT_GENERIC = 1
EXIT_INVALID_ARGS = 2
EXIT_NOT_FOUND = 3
EXIT_NETWORK = 4
EXIT_UNSAFE_ARCHIVE = 5
EXIT_GIT_UNAVAILABLE = 6

USER_AGENT = "github-code-scraper-skill/1.0"

DEFAULT_EXCLUDE_PATTERNS = [
    ".git/**",
    "**/.git/**",
    "node_modules/**",
    "**/node_modules/**",
    "dist/**",
    "**/dist/**",
    "build/**",
    "**/build/**",
    ".next/**",
    "**/.next/**",
    "coverage/**",
    "**/coverage/**",
    "vendor/**",
    "**/vendor/**",
]

DEFAULT_BINARY_PATTERNS = [
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.ico",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.mp4",
    "*.mov",
    "*.woff",
    "*.woff2",
    "*.ttf",
]

DEFAULT_SECRETISH_PATTERNS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/*secret*",
    "**/*private*key*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/id_dsa",
]


class ScraperError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_GENERIC):
        super().__init__(message)
        self.exit_code = exit_code


class InvalidArgumentError(ScraperError):
    def __init__(self, message: str):
        super().__init__(message, EXIT_INVALID_ARGS)


class RepoRefNotFoundError(ScraperError):
    def __init__(self, message: str):
        super().__init__(message, EXIT_NOT_FOUND)


class NetworkError(ScraperError):
    def __init__(self, message: str):
        super().__init__(message, EXIT_NETWORK)


class GithubHttpError(NetworkError):
    def __init__(self, url: str, status: int, reason: str, body: str = ""):
        self.url = url
        self.status = status
        self.reason = reason
        self.body = body
        exit_code = EXIT_NOT_FOUND if status == 404 else EXIT_NETWORK
        ScraperError.__init__(self, f"GitHub request failed ({status} {reason}): {url}", exit_code)


class UnsafeArchiveError(ScraperError):
    def __init__(self, message: str):
        super().__init__(message, EXIT_UNSAFE_ARCHIVE)


class GitUnavailableError(ScraperError):
    def __init__(self, message: str = "git is required for this operation but is not available"):
        super().__init__(message, EXIT_GIT_UNAVAILABLE)


def parse_repo(repo: str) -> tuple[str, str]:
    value = repo.strip()
    patterns = [
        r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
        r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            owner, repo_name = match.group("owner"), match.group("repo")
            if owner in {".", ".."} or repo_name in {".", ".."}:
                break
            return owner, repo_name
    raise InvalidArgumentError(
        "repo must be OWNER/REPO, https://github.com/OWNER/REPO, "
        "https://github.com/OWNER/REPO.git, or git@github.com:OWNER/REPO.git"
    )


def repo_to_https_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}.git"


def candidate_refs(explicit_ref: str | None) -> list[str]:
    if explicit_ref:
        return [explicit_ref]
    return ["main", "master"]


def _request(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise GithubHttpError(url, exc.code, exc.reason, body) from exc
    except urllib.error.URLError as exc:
        raise NetworkError(f"Network error while requesting {url}: {exc.reason}") from exc


def request_json(url: str) -> dict:
    data = _request(url)
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScraperError(f"GitHub returned invalid JSON for {url}") from exc
    if not isinstance(parsed, dict):
        raise ScraperError(f"GitHub returned non-object JSON for {url}")
    return parsed


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = _request(url)
    dest.write_bytes(data)


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
        for info in archive.infolist():
            target = (extract_dir / info.filename).resolve()
            if target != root and root not in target.parents:
                raise UnsafeArchiveError(f"Unsafe archive path: {info.filename}")
        archive.extractall(extract_dir)

    top_levels = {Path(name).parts[0] for name in names if Path(name).parts}
    if len(top_levels) == 1:
        candidate = extract_dir / next(iter(top_levels))
        if candidate.is_dir():
            return candidate
    return extract_dir


def _entry_type(mode: str | None, git_type: str | None) -> str:
    if mode == "040000" or git_type == "tree":
        return "directory"
    if mode == "160000" or git_type == "commit":
        return "submodule"
    if mode == "120000":
        return "symlink"
    if mode in {"100644", "100755"} or git_type == "blob":
        return "file"
    return "unknown"


def enrich_meta(meta: dict) -> dict:
    path = _normalize_posix_path(str(meta.get("path", "")))
    name = posixpath.basename(path)
    directory = posixpath.dirname(path)
    extension = posixpath.splitext(name)[1]
    mode = meta.get("mode")
    entry_type = meta.get("type") or _entry_type(mode, meta.get("git_type"))
    enriched = {
        **meta,
        "path": path,
        "name": name,
        "extension": extension,
        "directory": directory,
        "type": entry_type,
        "executable": mode == "100755",
        "symlink": entry_type == "symlink" or mode == "120000",
        "submodule": entry_type == "submodule" or mode == "160000",
    }
    enriched.pop("git_type", None)
    return enriched


def normalize_api_tree_item(item: dict, repo: str, ref: str) -> dict:
    mode = item.get("mode")
    git_type = item.get("type")
    entry_type = _entry_type(mode, git_type)
    size = item.get("size")
    meta = {
        "repo": repo,
        "ref": ref,
        "path": item.get("path", ""),
        "type": entry_type,
        "mode": mode,
        "sha": item.get("sha"),
        "size": size if isinstance(size, int) else None,
        "size_state": "known" if isinstance(size, int) else "unknown_until_fetch",
        "source": "api-tree",
    }
    return enrich_meta(meta)


def parse_git_ls_tree_z(output: bytes, repo: str, ref: str) -> list[dict]:
    entries: list[dict] = []
    for raw_entry in output.split(b"\0"):
        if not raw_entry:
            continue
        try:
            header, raw_path = raw_entry.split(b"\t", 1)
            mode, git_type, sha = header.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8", errors="surrogateescape")
        except ValueError as exc:
            raise ScraperError("Unable to parse git ls-tree output") from exc
        meta = {
            "repo": repo,
            "ref": ref,
            "path": path,
            "type": _entry_type(mode, git_type),
            "mode": mode,
            "sha": sha,
            "size": None,
            "size_state": "unknown_until_fetch",
            "source": "git-tree",
            "git_type": git_type,
        }
        entries.append(enrich_meta(meta))
    return entries


def _normalize_posix_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def normalize_patterns(patterns: list[str] | None) -> list[str]:
    if not patterns:
        return ["**/*"]
    normalized: list[str] = []
    for pattern in patterns:
        value = _normalize_posix_path(pattern)
        if not value:
            continue
        if pattern.endswith("/"):
            value = f"{value}/**"
        normalized.append(value)
    return normalized or ["**/*"]


def _normalize_exclude_patterns(patterns: list[str] | None) -> list[str]:
    if not patterns:
        return []
    normalized: list[str] = []
    for pattern in patterns:
        value = _normalize_posix_path(pattern)
        if not value:
            continue
        if pattern.endswith("/"):
            value = f"{value}/**"
        normalized.append(value)
    return normalized


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _match_one(path: str, pattern: str) -> bool:
    path = _normalize_posix_path(path)
    pattern = _normalize_posix_path(pattern)
    if pattern in {"*", "**", "**/*"}:
        return True
    if not _has_glob(pattern):
        return path == pattern or posixpath.basename(path) == pattern
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return False


def matches_patterns(path: str, include_patterns: list[str], exclude_patterns: list[str]) -> bool:
    normalized_include = normalize_patterns(include_patterns)
    normalized_exclude = _normalize_exclude_patterns(exclude_patterns)
    if any(_match_one(path, pattern) for pattern in normalized_exclude):
        return False
    return any(_match_one(path, pattern) for pattern in normalized_include)


def is_secretish_path(path: str) -> bool:
    normalized = _normalize_posix_path(path).lower()
    basename = posixpath.basename(normalized)
    if basename == ".env" or basename.startswith(".env."):
        return True
    if basename in {"id_rsa", "id_dsa"}:
        return True
    if basename.endswith((".pem", ".key")):
        return True
    return "secret" in normalized or "privatekey" in normalized.replace("-", "").replace("_", "")


def _is_binaryish_path(path: str) -> bool:
    return any(_match_one(path.lower(), pattern.lower()) for pattern in DEFAULT_BINARY_PATTERNS)


def select_files(
    metas: Iterable[dict],
    include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
    max_file_size: int | None,
    include_secretish: bool,
    include_binary: bool,
) -> list[dict]:
    del max_file_size
    includes = normalize_patterns(include_patterns)
    excludes = DEFAULT_EXCLUDE_PATTERNS + _normalize_exclude_patterns(exclude_patterns)
    selected: list[dict] = []
    for meta in metas:
        if meta.get("type") != "file" or meta.get("symlink") or meta.get("submodule"):
            continue
        path = meta["path"]
        if not matches_patterns(path, includes, excludes):
            continue
        if not include_secretish and is_secretish_path(path):
            continue
        if not include_binary and _is_binaryish_path(path):
            continue
        selected.append(meta)
    return selected


def is_probably_binary_bytes(data: bytes) -> bool:
    sample = data[:8192]
    if b"\0" in sample:
        return True
    if not sample:
        return False
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13, 12, 8})
    return control / len(sample) > 0.30


def bytes_to_text(data: bytes, include_binary: bool = False) -> tuple[str | None, str | None]:
    if is_probably_binary_bytes(data) and not include_binary:
        return None, "binary"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        if include_binary:
            return data.decode("utf-8", errors="replace"), None
        return None, "non_utf8"


def run_cmd(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def git_available() -> bool:
    return shutil.which("git") is not None


def clone_blobless_no_checkout(owner: str, repo: str, ref: str, workdir: Path) -> Path:
    if not git_available():
        raise GitUnavailableError()
    repo_dir = workdir
    if repo_dir.exists():
        if (repo_dir / ".git").exists():
            return repo_dir
        if any(repo_dir.iterdir()):
            raise ScraperError(f"workdir already exists and is not an empty git clone: {repo_dir}")
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "git",
        "clone",
        "--depth=1",
        "--filter=blob:none",
        "--no-checkout",
        "--branch",
        ref,
        repo_to_https_url(owner, repo),
        str(repo_dir),
    ]
    result = run_cmd(args)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        if "Remote branch" in stderr or "not found" in stderr:
            raise RepoRefNotFoundError(f"ref not found for {owner}/{repo}: {ref}")
        raise ScraperError(f"git clone failed for {owner}/{repo}@{ref}: {stderr.strip()}")
    return repo_dir


def git_ls_tree(repo_dir: Path) -> list[dict]:
    if not git_available():
        raise GitUnavailableError()
    remote = run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=repo_dir)
    repo = "unknown/unknown"
    if remote.returncode == 0:
        try:
            owner, repo_name = parse_repo(remote.stdout.decode("utf-8").strip())
            repo = f"{owner}/{repo_name}"
        except ScraperError:
            pass
    result = run_cmd(["git", "ls-tree", "-r", "-t", "-z", "HEAD"], cwd=repo_dir)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise ScraperError(f"git ls-tree failed: {stderr.strip()}")
    return parse_git_ls_tree_z(result.stdout, repo, "HEAD")


def git_tree_metadata(owner: str, repo: str, ref: str, repo_dir: Path) -> list[dict]:
    result = run_cmd(["git", "ls-tree", "-r", "-t", "-z", "HEAD"], cwd=repo_dir)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise ScraperError(f"git ls-tree failed for {owner}/{repo}@{ref}: {stderr.strip()}")
    return parse_git_ls_tree_z(result.stdout, f"{owner}/{repo}", ref)


def git_show_file(repo_dir: Path, ref: str, path: str) -> bytes:
    del ref
    result = run_cmd(["git", "show", f"HEAD:{path}"], cwd=repo_dir)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise ScraperError(f"git show failed for {path}: {stderr.strip()}")
    return result.stdout


def raw_github_url(owner: str, repo: str, ref: str, path: str) -> str:
    owner_q = urllib.parse.quote(owner, safe="")
    repo_q = urllib.parse.quote(repo, safe="")
    ref_q = urllib.parse.quote(ref, safe="")
    path_q = "/".join(urllib.parse.quote(part, safe="") for part in _normalize_posix_path(path).split("/"))
    return f"https://raw.githubusercontent.com/{owner_q}/{repo_q}/{ref_q}/{path_q}"


def fetch_raw_file(owner: str, repo: str, ref: str, path: str) -> bytes:
    return _request(raw_github_url(owner, repo, ref, path))


def write_json(path_or_dash: str, data) -> None:
    if path_or_dash == "-":
        json.dump(data, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    path = Path(path_or_dash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl_stream(path_or_dash: str, rows_iterable: Iterable[dict]) -> None:
    stream = sys.stdout if path_or_dash == "-" else None
    handle = None
    try:
        if stream is None:
            path = Path(path_or_dash)
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("w", encoding="utf-8")
            stream = handle
        for row in rows_iterable:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if handle is not None:
            handle.close()


def summarize_counts(metas: list[dict]) -> dict:
    return {
        "entries": len(metas),
        "files": sum(1 for meta in metas if meta.get("type") == "file"),
        "directories": sum(1 for meta in metas if meta.get("type") == "directory"),
        "symlinks": sum(1 for meta in metas if meta.get("symlink")),
        "submodules": sum(1 for meta in metas if meta.get("submodule")),
    }


def api_tree_url(owner: str, repo: str, ref: str) -> str:
    owner_q = urllib.parse.quote(owner, safe="")
    repo_q = urllib.parse.quote(repo, safe="")
    ref_q = urllib.parse.quote(ref, safe="")
    return f"https://api.github.com/repos/{owner_q}/{repo_q}/git/trees/{ref_q}?recursive=1"


def fetch_api_tree(owner: str, repo: str, ref: str) -> tuple[list[dict], bool]:
    payload = request_json(api_tree_url(owner, repo, ref))
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise RepoRefNotFoundError(f"tree not found for {owner}/{repo}@{ref}")
    truncated = bool(payload.get("truncated"))
    metas = [normalize_api_tree_item(item, f"{owner}/{repo}", ref) for item in tree if isinstance(item, dict)]
    return metas, truncated


def metadata_document(
    owner: str,
    repo: str,
    ref: str,
    strategy: str,
    truncated: bool,
    metas: list[dict],
    workdir: str | None = None,
) -> dict:
    return {
        "repo": f"{owner}/{repo}",
        "ref": ref,
        "strategy": strategy,
        "truncated": truncated,
        "size_known": all(
            meta.get("type") != "file" or meta.get("size_state") in {"known", "known_after_fetch"}
            for meta in metas
        ),
        "workdir": workdir,
        "counts": summarize_counts(metas),
        "files": metas,
    }


def _git_metadata_document(
    owner: str,
    repo: str,
    ref: str,
    workdir_arg: str | None,
    keep_workdir: bool,
    truncated: bool,
) -> tuple[dict, Path | None]:
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
    return doc, cleanup_target


def collect_metadata_document(
    repo_arg: str,
    explicit_ref: str | None,
    strategy: str,
    workdir_arg: str | None = None,
    keep_workdir: bool = False,
) -> tuple[dict, Path | None, bool]:
    owner, repo = parse_repo(repo_arg)
    last_error: ScraperError | None = None

    for ref in candidate_refs(explicit_ref):
        try:
            if strategy == "git-tree":
                doc, cleanup_target = _git_metadata_document(
                    owner, repo, ref, workdir_arg, keep_workdir, truncated=False
                )
                return doc, cleanup_target, keep_workdir

            metas, truncated = fetch_api_tree(owner, repo, ref)
            if strategy == "api-tree":
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

            doc, cleanup_target = _git_metadata_document(
                owner, repo, ref, workdir_arg, keep_workdir, truncated=True
            )
            return doc, cleanup_target, keep_workdir
        except GithubHttpError as exc:
            last_error = exc
            if exc.status == 404 and explicit_ref is None:
                continue
            if strategy == "auto" and is_rate_limitish(exc):
                try:
                    doc, cleanup_target = _git_metadata_document(
                        owner, repo, ref, workdir_arg, keep_workdir, truncated=True
                    )
                    return doc, cleanup_target, keep_workdir
                except ScraperError as git_exc:
                    last_error = git_exc
            break
        except RepoRefNotFoundError as exc:
            last_error = exc
            if explicit_ref is None:
                continue
            break
        except ScraperError as exc:
            last_error = exc
            break

    if last_error:
        raise last_error
    raise RepoRefNotFoundError(f"Unable to find a usable ref for {owner}/{repo}")


def temporary_workdir(prefix: str = "github-code-scraper-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def cleanup_path(path: Path | None) -> None:
    if path and path.exists():
        shutil.rmtree(path)


def is_rate_limitish(error: Exception) -> bool:
    if isinstance(error, GithubHttpError):
        body = error.body.lower()
        return error.status in {403, 429} or "rate limit" in body or "abuse" in body
    return False


def stderr_summary(lines: Iterable[tuple[str, object]]) -> None:
    for key, value in lines:
        print(f"{key}: {value}", file=sys.stderr)
