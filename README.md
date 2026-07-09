# github-code-scraper-skill

Agent Skill for inspecting and fetching files from public GitHub repositories without a GitHub token, API key, login, OAuth flow, or browser scraping.

The checked-in skill lives at:

```text
skill/github-code-scraper-skill/
```

## What It Does

- Collects normalized repository metadata from public GitHub repos.
- Fetches selected files by exact path, filename, or glob pattern.
- Downloads and safely extracts full repository ZIP archives.
- Exports metadata as JSON and file contents as streamed JSONL.
- Falls back from unauthenticated GitHub API/raw fetches to `git` where appropriate.

## Requirements

- Python 3.11+
- Internet access for live GitHub operations
- `git` optional, but recommended for truncated API trees and large file selections

The implementation uses only the Python standard library.

## Installation

To install the skill into your agents, run:

```bash
npx skills add https://github.com/Hamza-69/github-code-scraper-skill/skill --skill github-code-scraper-skill
```

## Skill Layout

```text
skill/github-code-scraper-skill/
  SKILL.md
  scripts/
    github_common.py
    repo_metadata.py
    repo_fetch_files.py
    repo_zip_materialize.py
  references/
    architecture.md
    cli-reference.md
    edge-cases.md
```

## Scripts

- `repo_metadata.py`: builds a normalized file map using GitHub's tree API or a blobless no-checkout git clone.
- `repo_fetch_files.py`: filters metadata first, then fetches only matched file contents through raw GitHub URLs or `git show`.
- `repo_zip_materialize.py`: downloads a full repo ZIP, validates archive paths, extracts it, and optionally exports JSON/JSONL.

## Safety Defaults

- Public GitHub repositories only.
- No tokens, API keys, logins, OAuth, browser automation, or HTML scraping.
- Secret-like paths are excluded unless `--include-secretish` is passed.
- Binary files are excluded from content export unless `--include-binary` is passed.
- JSONL content export streams rows instead of building one giant in-memory array.
- Diagnostics and summaries go to stderr; structured data goes to output files or stdout only when explicitly requested with `--out -`.

## Tests

Run the offline test suite:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/pycache python3 -m unittest discover -s tests
```

Run the optional live GitHub integration test:

```bash
RUN_GITHUB_INTEGRATION=1 PYTHONPYCACHEPREFIX=/private/tmp/pycache python3 -m unittest discover -s tests
```

## References

- `skill/github-code-scraper-skill/references/architecture.md`
- `skill/github-code-scraper-skill/references/cli-reference.md`
- `skill/github-code-scraper-skill/references/edge-cases.md`
