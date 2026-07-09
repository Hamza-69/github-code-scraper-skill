You are working in this repository. Build a production-quality Agent Skill named `github-code-scraper-skill`.

This is not just a random script folder. Build it as an Agent Skills-compatible skill, following the open Agent Skills structure and best practices.

The skill must help an agent inspect and fetch files from public GitHub repositories without requiring a GitHub token, API key, login, OAuth, or browser scraping.

High-level goal:
Create a robust, tokenless public GitHub code scraper skill that supports:

1. Metadata collection
2. Pattern-based file fetching
3. Full ZIP materialization and optional JSON/JSONL export

The final skill must live here:

.agents/skills/github-code-scraper-skill/
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

Do not put README.md inside the skill folder. If human documentation is needed, create a repo-level README outside `.agents/skills/github-code-scraper-skill/`.

Core constraints:

* No GitHub token.
* No API key.
* No login.
* No browser or HTML scraping.
* Public GitHub repositories only.
* Python 3.11+ preferred.
* Use only Python standard library unless a dependency is truly justified.
* `git` is optional but strongly recommended for fallback behavior.
* Every script must support `--help`.
* No interactive prompts.
* Agents run these scripts in non-interactive shells.
* Structured output only: JSON or JSONL.
* Diagnostics, progress, warnings, and summaries go to stderr.
* Data output goes to output files, or stdout only when `--out -` is explicitly passed.
* Default behavior should be safe and non-destructive.
* Exclude secret-like files by default.
* Exclude binary files by default for JSONL content export.
* Stream JSONL output. Do not build one giant in-memory array for repo contents.
* Do not fetch content before pattern filtering.

Skill purpose:
The skill should activate when a user asks things like:

* “fetch files from this GitHub repo”
* “get repo metadata”
* “get the file map”
* “scrape code from this public GitHub repo”
* “read all TypeScript files from this repo”
* “fetch README and package.json”
* “download this repo and inspect it”
* “materialize this repo into filesystem”
* “get all files matching src/**/*.py”
* “export repo files as JSONL”
* “analyze a public GitHub repository without a token”

================================================================================
AGENT SKILL REQUIREMENTS
========================

Create:

.agents/skills/github-code-scraper-skill/SKILL.md

It must have valid YAML frontmatter.

Required frontmatter:

---

name: github-code-scraper-skill
description: Fetches metadata, file maps, selected files, and full ZIP materializations from public GitHub repositories without requiring a token. Use when the user asks to inspect a GitHub repo, scrape public repo code, fetch code by path or glob pattern, export repo files as JSON/JSONL, get repository file metadata, or materialize a public repo into the filesystem.
compatibility: Python 3.11+. Internet access required. Git optional but recommended for truncated tree fallback and large pattern fetches.
------------------------------------------------------------------------------------------------------------------------------------------

Rules:

* `name` must be exactly `github-code-scraper-skill`.
* Folder name must match skill name exactly.
* Use `github-code-scraper-skill` everywhere.
* Do not use `github-public-repo-fetcher`.
* Do not use `github-code-scraper`.
* Do not use `github-repo-fetcher`.
* Keep the frontmatter description under 1024 characters.
* Do not include XML angle brackets in frontmatter.
* Do not include `claude` or `anthropic` in the skill name.
* Do not put README.md inside the skill folder.
* Keep `SKILL.md` concise and workflow-oriented.
* Put deeper explanations in `references/`.

`SKILL.md` body should include:

1. When to use this skill
2. Available scripts
3. Default decision tree
4. Common commands
5. Gotchas
6. Safety rules
7. Output expectations
8. When to read references

Default decision tree:

* Metadata only:
  Use `scripts/repo_metadata.py`
* Files by path/glob:
  Use `scripts/repo_fetch_files.py`
* Full filesystem materialization:
  Use `scripts/repo_zip_materialize.py`
* If the user only wants matched file metadata, use `repo_fetch_files.py --metadata-only`.
* If raw GitHub fetch hits limits or many files are selected, use git fetch mode.
* If GitHub API tree is truncated, fall back to git-tree strategy.

Important gotchas to include in `SKILL.md`:

* A blobless no-checkout clone has no working-tree files.
* `git ls-tree` reads Git tree objects, not filesystem files.
* `git ls-tree --long` is not default because size can require blob/object fetching.
* API-tree size is known when not truncated.
* Git-tree size is unknown until content fetch.
* Always filter before fetching contents.
* Do not include secret-like files unless the user explicitly asks and passes `--include-secretish`.
* Prefer output files over dumping huge stdout.
* If raw GitHub fetching hits limits, switch to git mode.

================================================================================
VERSION CONTROL REQUIREMENT
===========================

Commit frequently while implementing this. Do not do the whole task in one giant commit.

Before changing anything:

* Run `git status`.
* Inspect the current working tree.
* Do not overwrite unrelated user changes.
* Preserve any existing user changes.

Commit cadence:
Make small, meaningful commits after each stable milestone:

1. Skill folder structure and initial `SKILL.md`
2. Shared helpers in `github_common.py`
3. Metadata script implementation
4. Fetch-files script implementation
5. ZIP materialization script implementation
6. References documentation
7. Unit tests
8. Integration test scaffolding
9. Fixes after test runs

Commit message examples:

* `feat: add github code scraper skill scaffold`
* `feat: implement tokenless repo metadata collection`
* `feat: add pattern-based repo file fetching`
* `feat: add zip materialization exporter`
* `test: cover repo parsing and metadata normalization`
* `docs: add skill references and CLI examples`
* `fix: handle truncated tree fallback`

Strict commit attribution rules:

* Do not add `Co-authored-by:` trailers.
* Do not add `Co-authored-by: Codex`.
* Do not add `Co-authored-by: ChatGPT`.
* Do not add `Co-authored-by: OpenAI`.
* Do not add “Generated by Codex”.
* Do not add “Generated with ChatGPT”.
* Do not add “Generated by AI”.
* Do not add any AI/tool attribution in commit messages.
* Commit messages must contain only the human-readable commit title/body needed for the change.
* Use normal `git commit -m "message"` commits.
* Do not alter git author config.
* Do not use `--author`.
* Do not sign commits unless the repository already requires it.

Commit rules:

* Each commit should pass relevant tests for that milestone when possible.
* If tests are failing at a checkpoint, do not commit unless the commit message clearly says it is WIP.
* Prefer not to leave WIP commits unless absolutely necessary.
* Never commit secrets.
* Never commit generated large JSONL files.
* Never commit downloaded ZIPs.
* Never commit extracted repos.
* Never commit temp directories.
* Never commit cache folders.
* Add `.gitignore` entries if needed.

At the end, run `git status` and report:

* commits created
* tests run
* files changed
* anything left uncommitted
* live integration checks run or skipped

================================================================================
CORE ARCHITECTURE
=================

There are three scripts/workflows:

1. `repo_metadata.py`
   Gets repository file metadata.

2. `repo_fetch_files.py`
   Gets selected files by exact name/path/glob pattern.

3. `repo_zip_materialize.py`
   Downloads a full repo ZIP, extracts it into filesystem, and optionally exports metadata/content as JSON/JSONL.

Shared helpers go in:

.agents/skills/github-code-scraper-skill/scripts/github_common.py

Do not duplicate logic across scripts.

================================================================================
NORMALIZED METADATA SHAPE
=========================

Every metadata entry from every strategy must normalize into this shape:

{
"repo": "OWNER/REPO",
"ref": "main",
"path": "src/index.ts",
"name": "index.ts",
"extension": ".ts",
"directory": "src",
"type": "file" | "directory" | "symlink" | "submodule" | "unknown",
"mode": "100644",
"sha": "abc123..." or null,
"size": 1234 or null,
"size_state": "known" | "unknown_until_fetch" | "known_after_fetch",
"source": "api-tree" | "git-tree" | "zip",
"executable": true or false,
"symlink": true or false,
"submodule": true or false
}

Mode mapping:

* `100644` blob => normal file
* `100755` blob => executable file
* `040000` tree => directory
* `120000` blob => symlink
* `160000` commit => submodule

Important size semantics:

* API-tree strategy:

  * File size is known when GitHub Trees API response is not truncated.
  * Set `size_state: "known"` for files with size.
* Git-tree strategy:

  * File size is unknown initially.
  * Set `size: null`.
  * Set `size_state: "unknown_until_fetch"`.
  * After fetching content with `git show`, set `size = len(content_bytes)` and `size_state: "known_after_fetch"`.
* ZIP strategy:

  * File size is known from filesystem stat.
  * Set `size_state: "known"`.

================================================================================
WORKFLOW 1: METADATA COLLECTION
===============================

Script:

.agents/skills/github-code-scraper-skill/scripts/repo_metadata.py

Purpose:
Collect repository file metadata.

CLI examples:

python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py 
--repo pallets/flask 
--ref main 
--strategy auto 
--out metadata.json

python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py 
--repo https://github.com/pallets/flask 
--strategy api-tree 
--out metadata.json

python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py 
--repo pallets/flask 
--strategy git-tree 
--workdir .cache/flask 
--keep-workdir 
--out metadata.json

Required flags:

* `--repo`
  Accept:

  * `OWNER/REPO`
  * `https://github.com/OWNER/REPO`
  * `https://github.com/OWNER/REPO.git`
  * `git@github.com:OWNER/REPO.git`
* `--ref`
  Optional. If absent, try `main`, then `master`.
* `--strategy`
  One of:

  * `auto`
  * `api-tree`
  * `git-tree`
* `--out`
  Output JSON path. Allow `-` for stdout only if explicitly passed.
* `--workdir`
  Optional working directory.
* `--keep-workdir`
  Preserve generated clone/cache.
* `--include-dirs`
  Include directory metadata entries. Default true for metadata.
  File-fetching must still only fetch files.

Strategies:

1. `api-tree`

Use GitHub Git Trees API:

https://api.github.com/repos/OWNER/REPO/git/trees/REF?recursive=1

No auth.

Behavior:

* Parse `tree`.
* If `truncated: false`, output metadata with sizes known for blobs/files.
* If `truncated: true` and strategy is forced `api-tree`, fail clearly or output a documented truncated error.
* If `truncated: true` and strategy is `auto`, fall back to `git-tree`.

2. `git-tree`

Use blobless no-checkout clone:

git clone --depth=1 --filter=blob:none --no-checkout https://github.com/OWNER/REPO.git WORKDIR

Then run:

git ls-tree -r -t -z HEAD

Important:

* There are no working-tree files after `--no-checkout`.
* `git ls-tree` reads Git tree objects from `.git`, not filesystem files.
* Do not use `git ls-tree --long` by default.
* This strategy gets:

  * path
  * mode
  * git type
  * sha
* It does not reliably get file size without fetching blob information.
* Set:

  * `size: null`
  * `size_state: "unknown_until_fetch"`

3. `auto`

Behavior:

* Try `api-tree`.
* If not truncated, use API result.
* If truncated, use `git-tree`.
* If requested ref fails and no explicit ref was supplied, try `main`, then `master`.
* If all fail, return clear error.

Output JSON shape:

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
"files": [...]
}

For git fallback:

{
"repo": "OWNER/REPO",
"ref": "main",
"strategy": "git-tree",
"truncated": true,
"size_known": false,
"workdir": ".cache/flask",
"counts": {...},
"files": [...]
}

================================================================================
WORKFLOW 2: PATTERN-BASED FILE FETCHING
=======================================

Script:

.agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py

Purpose:
Fetch selected files by exact name, path, or glob pattern.

Flow:

1. Collect metadata using shared Python functions from `github_common.py`.
2. Do not shell out to `repo_metadata.py` unless there is a strong reason.
3. Filter metadata array in Python.
4. If `--metadata-only` is passed, output matched metadata only.
5. Otherwise fetch file contents for matched files only.
6. Output fetched files as JSONL.

CLI examples:

python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py 
--repo pallets/flask 
--patterns "**/*.py" "pyproject.toml" "README.md" 
--out flask-files.jsonl

python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py 
--repo pallets/flask 
--patterns "src/**" "**/*.py" 
--metadata-only 
--out matched.json

python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py 
--repo pallets/flask 
--patterns "**/*.py" 
--strategy auto 
--fetch-mode auto 
--out files.jsonl

Required flags:

* `--repo`
* `--ref`
* `--patterns`
  Zero or more patterns. If omitted, default to all files except default excludes.
* `--exclude`
  Zero or more exclude patterns.
* `--metadata-only`
  Filter metadata and output matched metadata only. Do not fetch content.
* `--fetch-mode`
  One of:

  * `auto`
  * `raw`
  * `git`
* `--strategy`
  Metadata strategy:

  * `auto`
  * `api-tree`
  * `git-tree`
* `--raw-threshold`
  Default 50. If selected file count exceeds threshold, auto should prefer git.
* `--max-file-size`
  Default around 250 KB or 500 KB.
* `--include-secretish`
* `--include-binary`
* `--out`
* `--workdir`
* `--keep-workdir`

Pattern behavior:
Support:

* `README.md`
* `package.json`
* `src/**`
* `src/**/*.py`
* `**/*.ts`
* `**/*.tsx`
* `apps/web/**`
* directory patterns ending with `/`, treated as `pattern/**`

Use POSIX-style paths.

Default excludes:

* `.git/**`
* `**/.git/**`
* `node_modules/**`
* `**/node_modules/**`
* `dist/**`
* `**/dist/**`
* `build/**`
* `**/build/**`
* `.next/**`
* `**/.next/**`
* `coverage/**`
* `**/coverage/**`
* `vendor/**`
* `**/vendor/**`

Default binary/content excludes unless `--include-binary`:

* `*.png`
* `*.jpg`
* `*.jpeg`
* `*.gif`
* `*.webp`
* `*.ico`
* `*.pdf`
* `*.zip`
* `*.tar`
* `*.gz`
* `*.mp4`
* `*.mov`
* `*.woff`
* `*.woff2`
* `*.ttf`

Default secret-like excludes unless `--include-secretish`:

* `.env`
* `.env.*`
* `**/.env`
* `**/.env.*`
* `**/*secret*`
* `**/*private*key*`
* `**/*.pem`
* `**/*.key`
* `**/id_rsa`
* `**/id_dsa`

Fetch modes:

1. `raw`

Use:

https://raw.githubusercontent.com/OWNER/REPO/REF/path/to/file

Requirements:

* Properly URL-encode each path segment.
* Good when selected file count is small.
* If raw fetching returns 403, 429, or rate-limit-ish errors in auto mode, fall back to git.

2. `git`

Ensure blobless no-checkout clone exists.

Use:

git show HEAD:path/to/file

Requirements:

* Fetch only selected files.
* Get bytes from stdout.
* Set:

  * `size = len(content_bytes)`
  * `size_state = "known_after_fetch"`
  * `fetch_source = "git-show"`

3. `auto`

Behavior:

* If metadata strategy is `git-tree`, use `git`.
* If metadata strategy is `api-tree` and selected file count <= raw threshold, try raw.
* If raw fails due to rate limit-ish errors, fall back to git.
* If selected file count > raw threshold, prefer git.
* Raw threshold default: 50.

Output JSONL row for fetched file:

{
"repo": "OWNER/REPO",
"ref": "main",
"path": "src/index.py",
"name": "index.py",
"extension": ".py",
"directory": "src",
"type": "file",
"mode": "100644",
"sha": "...",
"size": 4812,
"size_state": "known_after_fetch",
"source": "api-tree",
"fetch_source": "raw-github" or "git-show",
"content": "...",
"skipped_content": null
}

If content is skipped:

{
...
"content": null,
"skipped_content": "binary" | "non_utf8" | "too_large" | "secretish" | "fetch_error: ..."
}

Important:
Do not invent a `fetch-mode=none`. Use `--metadata-only` for no-content mode.
Do not fetch content before filtering.

================================================================================
WORKFLOW 3: ZIP MATERIALIZATION
===============================

Script:

.agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py

Purpose:
Download an entire public GitHub repository as ZIP, extract it to filesystem, and optionally export a manifest JSON and file contents JSONL.

CLI examples:

python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py 
--repo pallets/flask 
--ref main 
--workdir .repos/flask 
--keep-workdir

python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py 
--repo pallets/flask 
--ref main 
--workdir .repos/flask 
--keep-workdir 
--manifest-out flask-manifest.json 
--jsonl-out flask-files.jsonl

python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py 
--repo pallets/flask 
--jsonl-out flask-files.jsonl 
--manifest-out flask-manifest.json 
--cleanup

Behavior:

* Download from:
  `https://codeload.github.com/OWNER/REPO/zip/refs/heads/REF`
* If ref is not supplied, try `main`, then `master`.
* Extract safely. Prevent zip-slip/path traversal attacks.
* Identify extracted root directory.
* Walk the real filesystem.
* Collect metadata with actual filesystem sizes.
* Optionally export:

  * manifest JSON
  * contents JSONL
* Support pattern filtering and default excludes.
* This is the brute-force fallback and the “make it into filesystem for subsequent manipulation” mode.

Required/optional flags:

* `--repo`
* `--ref`
* `--workdir`
* `--keep-workdir`
* `--cleanup`
* `--manifest-out`
* `--jsonl-out`
* `--metadata-only`
* `--patterns`
* `--exclude`
* `--max-file-size`
* `--include-secretish`
* `--include-binary`

Cleanup behavior:

For metadata and fetch scripts:

* Default: temporary workdir is deleted.
* If `--keep-workdir`, preserve it.
* If `--workdir` is provided without `--keep-workdir`, still clean unless the script help clearly says otherwise.

For zip materialization:

* If user passes `--keep-workdir`, preserve extracted repo.
* If user passes `--cleanup`, delete extracted repo after exports.
* If both are passed, error.
* If neither is passed:

  * If no JSON export is requested and `--workdir` is explicit, keep the extracted repo because materialization is the purpose.
  * If JSON export is requested and workdir is temporary, clean up by default.
* Print final filesystem root if kept.

================================================================================
SHARED MODULE: github_common.py
===============================

Implement shared utilities in:

.agents/skills/github-code-scraper-skill/scripts/github_common.py

Required functions:

* `parse_repo(repo: str) -> tuple[str, str]`
* `repo_to_https_url(owner: str, repo: str) -> str`
* `candidate_refs(explicit_ref: str | None) -> list[str]`
* `request_json(url: str) -> dict`
* `download_file(url: str, dest: Path) -> None`
* `safe_extract_zip(zip_path: Path, extract_dir: Path) -> Path`
* `normalize_api_tree_item(item: dict, repo: str, ref: str) -> dict`
* `parse_git_ls_tree_z(output: bytes, repo: str, ref: str) -> list[dict]`
* `enrich_meta(meta: dict) -> dict`
* `normalize_patterns(patterns: list[str]) -> list[str]`
* `matches_patterns(path: str, include_patterns: list[str], exclude_patterns: list[str]) -> bool`
* `select_files(metas, include_patterns, exclude_patterns, max_file_size, include_secretish, include_binary) -> list[dict]`
* `is_secretish_path(path: str) -> bool`
* `is_probably_binary_bytes(data: bytes) -> bool`
* `bytes_to_text(data: bytes, include_binary: bool = False) -> tuple[str | None, str | None]`
* `run_cmd(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess`
* `git_available() -> bool`
* `clone_blobless_no_checkout(owner: str, repo: str, ref: str, workdir: Path) -> Path`
* `git_ls_tree(repo_dir: Path) -> list[dict]`
* `git_show_file(repo_dir: Path, ref: str, path: str) -> bytes`
* `raw_github_url(owner: str, repo: str, ref: str, path: str) -> str`
* `fetch_raw_file(owner: str, repo: str, ref: str, path: str) -> bytes`
* `write_json(path_or_dash: str, data) -> None`
* `write_jsonl_stream(path_or_dash: str, rows_iterable) -> None`
* `summarize_counts(metas: list[dict]) -> dict`

================================================================================
REFERENCES
==========

Create:

.agents/skills/github-code-scraper-skill/references/architecture.md

Include:

* API-tree strategy
* git-tree strategy
* ZIP strategy
* size semantics
* cleanup semantics
* fetch-mode semantics
* why blobless no-checkout has no working-tree files
* why `git ls-tree` reads tree objects
* why `git ls-tree --long` is not default

Create:

.agents/skills/github-code-scraper-skill/references/cli-reference.md

Include:

* Complete CLI options for all three scripts
* Examples for common tasks
* Recommended defaults
* Output format examples

Create:

.agents/skills/github-code-scraper-skill/references/edge-cases.md

Include:

* truncated API tree
* unauthenticated rate limits
* missing refs
* binary files
* symlinks
* submodules
* large repos
* weird filenames
* paths with spaces
* secret-like files
* ZIP extraction safety
* raw GitHub 403/429 fallback
* git unavailable fallback limitations

================================================================================
TESTING
=======

Create a proper test suite.

Suggested test structure:

tests/
test_github_common.py
test_repo_metadata.py
test_repo_fetch_files.py
test_repo_zip_materialize.py
test_integration_github.py

Use mocked network/subprocess for most tests. Do not rely only on live GitHub.

Required unit tests:

1. Repo parsing

* `pallets/flask`
* `https://github.com/pallets/flask`
* `https://github.com/pallets/flask.git`
* `git@github.com:pallets/flask.git`
* reject invalid repo values

2. API tree normalization

* normal file `100644 blob`
* executable file `100755 blob`
* directory `040000 tree`
* symlink `120000 blob`
* submodule `160000 commit`
* unknown mode/type

3. Git ls-tree parsing

* parse null-delimited `git ls-tree -r -t -z HEAD` output
* parse file
* parse directory
* parse symlink
* parse submodule
* parse paths with spaces
* ensure size is null and size_state is unknown_until_fetch for git-tree files

4. Pattern selection

* `src/**`
* `**/*.py`
* exact file `README.md`
* directory pattern `src/`
* exclude `**/*.test.py`
* default excludes
* secretish excludes
* binary extension excludes
* ensure only real files are selected for fetching

5. Raw GitHub URL encoding

* normal path
* nested path
* path with spaces
* path with special characters

6. Content decoding

* UTF-8
* binary with NUL bytes
* non-UTF8
* include_binary behavior

7. ZIP extraction

* safe normal zip
* malicious `../evil` path raises
* extracted root directory detection

8. Metadata strategy

* API tree not truncated returns api-tree metadata with size
* API tree truncated in auto falls back to git-tree
* forced api-tree with truncated raises or returns documented error
* missing ref tries main then master when no ref explicitly supplied

9. Fetch files

* metadata-only returns matched metadata, no content fetch
* raw mode calls raw fetch only for matched files
* git mode calls git show only for matched files
* auto chooses raw under threshold
* auto chooses git above threshold
* auto falls back to git on raw 403/429/rate-limit-ish error
* fetched files get size known_after_fetch

10. ZIP materialize

* manifest output
* JSONL output
* cleanup behavior
* keep-workdir behavior
* patterns/excludes applied before JSONL export

Integration tests:
Create optional live tests guarded by:

RUN_GITHUB_INTEGRATION=1

Use:

* `pallets/flask`
* optionally `octocat/Hello-World`

Manual commands to verify if network is available:

python .agents/skills/github-code-scraper-skill/scripts/repo_metadata.py 
--repo pallets/flask 
--strategy auto 
--out /tmp/flask-meta.json

python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py 
--repo pallets/flask 
--patterns "**/*.py" "pyproject.toml" "README.md" 
--out /tmp/flask-files.jsonl

python .agents/skills/github-code-scraper-skill/scripts/repo_fetch_files.py 
--repo pallets/flask 
--patterns "**/*.py" 
--metadata-only 
--out /tmp/flask-matched.json

python .agents/skills/github-code-scraper-skill/scripts/repo_zip_materialize.py 
--repo pallets/flask 
--workdir /tmp/flask-materialized 
--keep-workdir 
--manifest-out /tmp/flask-manifest.json 
--jsonl-out /tmp/flask-zip-files.jsonl

================================================================================
EXIT CODES
==========

Use meaningful exit codes:

* 0 success
* 1 generic failure
* 2 invalid arguments
* 3 repo/ref not found
* 4 rate limit or network failure
* 5 unsafe archive
* 6 git unavailable when required

Do not silently swallow important failures.

================================================================================
OUTPUT AND SUMMARIES
====================

Each script should print a small execution summary to stderr:

* repo
* ref
* strategy
* total file/entry count
* matched count if relevant
* fetched count if relevant
* output path
* workdir kept or cleaned

Do not print huge content to stdout by default.

================================================================================
GITIGNORE
=========

Ensure generated artifacts are ignored if needed:

* `.cache/`
* `.repos/`
* `*.jsonl` if generated test outputs are likely
* downloaded ZIPs
* extracted repo dirs
* temp directories

Do not over-ignore source files or tests.

================================================================================
IMPLEMENTATION ORDER
====================

Follow this exact order:

1. Inspect the current repository.
2. Run `git status`.
3. Identify and preserve any existing user changes.
4. Create the skill folder structure.
5. Create initial `SKILL.md`.
6. Commit scaffold.
7. Implement `github_common.py`.
8. Run relevant tests or static checks.
9. Commit shared helpers.
10. Implement `repo_metadata.py`.
11. Test metadata behavior.
12. Commit metadata script.
13. Implement `repo_fetch_files.py`.
14. Test pattern filtering and fetch behavior.
15. Commit fetch-files script.
16. Implement `repo_zip_materialize.py`.
17. Test ZIP behavior.
18. Commit ZIP materialization script.
19. Write references:

    * `references/architecture.md`
    * `references/cli-reference.md`
    * `references/edge-cases.md`
20. Commit docs.
21. Write tests.
22. Run tests.
23. Fix failures.
24. Commit passing tests/fixes.
25. Run live manual command against `pallets/flask` if network is available.
26. Run final `git status`.
27. Report:

    * commits created
    * tests run
    * live checks run or skipped
    * files changed
    * anything left uncommitted
    * known limitations

================================================================================
QUALITY BAR
===========

* Make the code readable and modular.
* Keep CLI help concise but useful.
* Avoid cleverness.
* Prefer deterministic scripts over agent guesswork.
* Do not use shell-specific behavior unless needed.
* Handle network errors clearly.
* Handle missing git clearly.
* Handle missing refs clearly.
* Handle raw GitHub rate/permission errors clearly.
* Keep file paths POSIX-style in outputs.
* Use safe ZIP extraction.
* Do not fake successful live integration if network is unavailable.
* If network is unavailable, say mocked/unit tests passed and live GitHub integration was skipped.

Final deliverable:
A committed Agent Skill folder at:

.agents/skills/github-code-scraper-skill/

with working scripts, references, tests, and a final report.
