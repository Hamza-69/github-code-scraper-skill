# Edge Cases

## Truncated API Tree

The GitHub Trees API can return `truncated: true`. Forced `api-tree` fails because the metadata would be incomplete. `auto` falls back to git-tree.

## Unauthenticated Rate Limits

Raw and API requests are unauthenticated. A 403, 429, abuse-detection, or rate-limit response in auto raw mode causes a git fallback when possible. If `git` is unavailable, the script exits with a clear error.

## Missing Refs

When `--ref` is omitted, scripts try `main`, then `master`. When `--ref` is explicit, failure is reported instead of guessing another ref.

## Binary Files

Known binary extensions are excluded from JSONL content export by default. If binary bytes are detected in a selected file, `content` is `null` and `skipped_content` is `binary` unless `--include-binary` is passed.

## Symlinks

Symlink entries are represented with `mode: "120000"` and `type: "symlink"`. File-fetching selects only real files by default, not symlinks.

## Submodules

Submodules use `mode: "160000"` and `type: "submodule"`. They are metadata entries only; the scripts do not recursively fetch submodule repositories.

## Large Repositories

Use `repo_fetch_files.py --metadata-only` to inspect matches before fetching content. For many selected files, auto mode prefers git to avoid many raw HTTP requests. ZIP materialization is the brute-force fallback when a real filesystem tree is needed.

## Weird Filenames

Metadata uses POSIX-style paths. Raw GitHub URLs URL-encode path segments, so spaces and special characters are safe. JSON and JSONL outputs use UTF-8.

## Paths With Spaces

Pass patterns as quoted shell arguments:

```bash
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo owner/repo --patterns "docs/My File.md" --out files.jsonl
```

## Secret-Like Files

Secret-like paths such as `.env`, `.pem`, `.key`, `id_rsa`, and names containing `secret` are excluded by default. Include them only when the user explicitly asks and pass `--include-secretish`.

## ZIP Extraction Safety

ZIP extraction validates resolved paths before extracting. Entries that would escape the extraction directory raise an unsafe archive error and exit with code 5.

## Raw GitHub 403/429 Fallback

Auto fetch mode retries through git when raw GitHub returns rate-limit-like 403 or 429 errors. Forced raw mode reports the raw fetch failure.

## Git Unavailable

API-tree metadata and small raw fetches can work without git. Git-tree, large auto fetches, and raw fallback require `git`; if it is missing, scripts exit with code 6.
