# CLI Reference

All scripts are non-interactive, use structured output, and support `--help`. Diagnostics and summaries go to stderr.

## Metadata

```bash
python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py --repo pallets/flask --strategy auto --out metadata.json
python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py --repo https://github.com/pallets/flask --strategy api-tree --out metadata.json
python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py --repo pallets/flask --strategy git-tree --workdir .cache/flask --keep-workdir --out metadata.json
```

Options:

- `--repo`: required. Accepts `OWNER/REPO`, HTTPS GitHub URLs, `.git` URLs, and `git@github.com:OWNER/REPO.git`.
- `--ref`: optional. Defaults to trying `main`, then `master`.
- `--strategy`: `auto`, `api-tree`, or `git-tree`. Default: `auto`.
- `--out`: required JSON path. Use `-` for stdout.
- `--workdir`: optional git workdir.
- `--keep-workdir`: preserve generated git workdir.
- `--include-dirs` / `--no-include-dirs`: include directory entries. Default: include.

Metadata output:

```json
{
  "repo": "OWNER/REPO",
  "ref": "main",
  "strategy": "api-tree",
  "truncated": false,
  "size_known": true,
  "workdir": null,
  "counts": {
    "entries": 100,
    "files": 80,
    "directories": 18,
    "symlinks": 1,
    "submodules": 1
  },
  "files": []
}
```

## Fetch Files

```bash
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo pallets/flask --patterns "**/*.py" "pyproject.toml" "README.md" --out flask-files.jsonl
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo pallets/flask --patterns "src/**" "**/*.py" --metadata-only --out matched.json
python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py --repo pallets/flask --patterns "**/*.py" --strategy auto --fetch-mode auto --out files.jsonl
```

Options:

- `--repo`: required.
- `--ref`: optional. Defaults to trying `main`, then `master`.
- `--patterns`: zero or more include patterns. Defaults to all files after excludes.
- `--exclude`: zero or more additional exclude patterns.
- `--metadata-only`: output matched metadata JSON and fetch no content.
- `--fetch-mode`: `auto`, `raw`, or `git`. Default: `auto`.
- `--strategy`: metadata strategy: `auto`, `api-tree`, or `git-tree`. Default: `auto`.
- `--raw-threshold`: selected-file count threshold before auto mode prefers git. Default: `50`.
- `--max-file-size`: maximum bytes to include per file. Default: `512000`.
- `--include-secretish`: include secret-like paths.
- `--include-binary`: include binary or non-UTF8 content when possible.
- `--out`: required JSONL path for content mode or JSON path for metadata-only. Use `-` for stdout.
- `--workdir`: optional git workdir.
- `--keep-workdir`: preserve generated git workdir.

JSONL row:

```json
{
  "repo": "OWNER/REPO",
  "ref": "main",
  "path": "src/index.py",
  "name": "index.py",
  "extension": ".py",
  "directory": "src",
  "type": "file",
  "mode": "100644",
  "sha": null,
  "size": 4812,
  "size_state": "known_after_fetch",
  "source": "api-tree",
  "fetch_source": "raw-github",
  "content": "...",
  "skipped_content": null
}
```

## ZIP Materialize

```bash
python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py --repo pallets/flask --ref main --workdir .repos/flask --keep-workdir
python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py --repo pallets/flask --ref main --workdir .repos/flask --keep-workdir --manifest-out flask-manifest.json --jsonl-out flask-files.jsonl
python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py --repo pallets/flask --jsonl-out flask-files.jsonl --manifest-out flask-manifest.json --cleanup
```

Options:

- `--repo`: required.
- `--ref`: optional branch ref. Defaults to trying `main`, then `master`.
- `--workdir`: extraction parent directory.
- `--keep-workdir`: preserve extracted repository.
- `--cleanup`: delete extracted repository after exports.
- `--manifest-out`: optional manifest JSON path.
- `--jsonl-out`: optional content JSONL path.
- `--metadata-only`: write JSONL rows without content.
- `--patterns`: zero or more include patterns.
- `--exclude`: zero or more additional exclude patterns.
- `--max-file-size`: maximum bytes to include per file. Default: `512000`.
- `--include-secretish`: include secret-like paths.
- `--include-binary`: include binary or non-UTF8 content when possible.

Recommended defaults: use `--strategy auto`, leave `--fetch-mode auto`, prefer output files over `-`, and pass `--keep-workdir` only when the caller needs the generated clone or extracted repository.
