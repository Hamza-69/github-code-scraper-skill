---
name: github-code-scraper-skill
description: Fetches metadata, file maps, selected files, and full ZIP materializations from public GitHub repositories without requiring a token. Use when the user asks to inspect a GitHub repo, scrape public repo code, fetch code by path or glob pattern, export repo files as JSON/JSONL, get repository file metadata, or materialize a public repo into the filesystem.
compatibility: Python 3.11+. Internet access required. Git optional but recommended for truncated tree fallback and large pattern fetches.
---

# GitHub Code Scraper Skill

Use this skill when a user asks to inspect, scrape, fetch, export, or materialize files from a public GitHub repository without a token, API key, login, OAuth flow, or browser scraping.

## Available Scripts

- `scripts/repo_metadata.py`: collect repository file metadata.
- `scripts/repo_fetch_files.py`: fetch selected files by exact path, name, or glob.
- `scripts/repo_zip_materialize.py`: download and extract a repository ZIP, with optional JSON manifest and JSONL content export.

## Default Decision Tree

- Metadata only: use `scripts/repo_metadata.py`.
- Files by path/glob: use `scripts/repo_fetch_files.py`.
- Full filesystem materialization: use `scripts/repo_zip_materialize.py`.
- Matched file metadata only: use `repo_fetch_files.py --metadata-only`.
- Raw GitHub fetch hits limits or many files are selected: switch to git fetch mode.
- GitHub API tree is truncated: fall back to git-tree strategy.

## Common Commands

```bash
python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py --repo pallets/flask --strategy auto --out metadata.json
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo pallets/flask --patterns "**/*.py" "pyproject.toml" "README.md" --out flask-files.jsonl
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo pallets/flask --patterns "src/**" --metadata-only --out matched.json
python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py --repo pallets/flask --workdir .repos/flask --keep-workdir
```

## Gotchas

- A blobless no-checkout clone has no working-tree files.
- `git ls-tree` reads Git tree objects, not filesystem files.
- `git ls-tree --long` is not default because size can require blob/object fetching.
- API-tree size is known when the tree is not truncated.
- Git-tree size is unknown until content fetch.
- Always filter before fetching contents.
- Do not include secret-like files unless the user explicitly asks and passes `--include-secretish`.
- Prefer output files over dumping huge stdout.
- If raw GitHub fetching hits limits, switch to git mode.

## Safety Rules

- Public GitHub repositories only.
- No token, API key, login, OAuth, browser automation, or HTML scraping.
- No interactive prompts.
- Exclude secret-like paths by default.
- Exclude binary files by default for JSONL content export.
- Keep outputs structured as JSON or JSONL.

## Output Expectations

Diagnostics, progress, warnings, and summaries go to stderr. Data goes to output files, or to stdout only when `--out -` is explicitly passed. JSONL content exports are streamed instead of accumulated into one large in-memory array.

## When To Read References

Read `references/architecture.md` for strategy semantics, `references/cli-reference.md` for full CLI usage, and `references/edge-cases.md` when handling truncation, rate limits, unusual paths, binary files, symlinks, submodules, or unsafe archives.
