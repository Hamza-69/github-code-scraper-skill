# Architecture

`github-code-scraper-skill` uses tokenless public GitHub endpoints and optional local `git` commands. It never uses a GitHub token, login, OAuth flow, browser automation, or HTML scraping.

## API-Tree Strategy

`repo_metadata.py --strategy api-tree` calls:

```text
https://api.github.com/repos/OWNER/REPO/git/trees/REF?recursive=1
```

When GitHub returns `truncated: false`, file sizes for blobs are available from the API response and each file entry uses `size_state: "known"`. If `truncated: true` is returned with forced `api-tree`, the script fails clearly because the file map is incomplete.

## Git-Tree Strategy

`repo_metadata.py --strategy git-tree` creates a blobless no-checkout clone:

```bash
git clone --depth=1 --filter=blob:none --no-checkout https://github.com/OWNER/REPO.git WORKDIR
git ls-tree -r -t -z HEAD
```

A blobless no-checkout clone has no working-tree files. The clone stores enough Git objects to inspect tree structure without checking files out. `git ls-tree` reads Git tree objects from `.git`, not filesystem files.

`git ls-tree --long` is not the default because sizes can require blob or object fetching. Git-tree metadata sets `size: null` and `size_state: "unknown_until_fetch"` until content is fetched with `git show`.

## ZIP Strategy

`repo_zip_materialize.py` downloads:

```text
https://codeload.github.com/OWNER/REPO/zip/refs/heads/REF
```

It validates every archive path before extraction to prevent zip-slip path traversal. After extraction, it walks the real filesystem and records sizes from `stat`, so ZIP metadata uses `size_state: "known"` for files.

## Size Semantics

- API-tree: blob size is known when the API response is not truncated.
- Git-tree: size is unknown until the selected file is fetched with `git show`.
- ZIP: size is known from the extracted filesystem.
- Fetched content rows update size to `len(content_bytes)` and use `size_state: "known_after_fetch"`.

## Fetch Modes

- `raw`: fetches selected files from `raw.githubusercontent.com` after metadata filtering.
- `git`: fetches selected files with `git show HEAD:path/to/file` from a blobless clone.
- `auto`: uses git when metadata came from git-tree or the selected file count exceeds `--raw-threshold`; otherwise tries raw and falls back to git on rate-limit-like 403 or 429 responses.

Content is never fetched before pattern filtering.

## Cleanup Semantics

Metadata and fetch scripts delete generated git workdirs by default. Passing `--keep-workdir` preserves them. If `--workdir` is provided without `--keep-workdir`, the script still treats it as managed scratch space and cleans it after completion.

ZIP materialization rejects `--keep-workdir` and `--cleanup` together. When neither is passed, explicit `--workdir` paths are kept because filesystem materialization is the purpose. Temporary ZIP extraction dirs are cleaned when only JSON exports are requested.

## Safety Defaults

Default path excludes remove common generated directories. Secret-like files are excluded from file selection unless `--include-secretish` is passed. Binary extensions are excluded from JSONL content export unless `--include-binary` is passed.
