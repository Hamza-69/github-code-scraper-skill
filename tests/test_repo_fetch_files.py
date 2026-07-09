from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "github-code-scraper-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import github_common as common
import repo_fetch_files


def meta(path: str, source: str = "api-tree", size: int | None = 3) -> dict:
    return common.enrich_meta(
        {
            "repo": "owner/repo",
            "ref": "main",
            "path": path,
            "type": "file",
            "mode": "100644",
            "sha": "abc",
            "size": size,
            "size_state": "known" if size is not None else "unknown_until_fetch",
            "source": source,
        }
    )


def doc(strategy: str = "api-tree") -> dict:
    files = [meta("README.md"), meta("src/app.py"), meta("tests/app.test.py")]
    return common.metadata_document("owner", "repo", "main", strategy, False, files, None)


class RepoFetchFilesTests(unittest.TestCase):
    def test_metadata_only_returns_matched_metadata_without_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "matched.json"
            with mock.patch.object(repo_fetch_files, "collect_metadata_document", return_value=(doc(), None, False)), mock.patch.object(
                repo_fetch_files, "fetch_raw_file"
            ) as raw:
                code = repo_fetch_files.main(
                    ["--repo", "owner/repo", "--patterns", "src/**", "--metadata-only", "--out", str(out)]
                )
            self.assertEqual(code, 0)
            raw.assert_not_called()
            payload = json.loads(out.read_text())
            self.assertEqual([item["path"] for item in payload["files"]], ["src/app.py"])

    def test_raw_mode_fetches_only_matched_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "files.jsonl"
            with mock.patch.object(repo_fetch_files, "collect_metadata_document", return_value=(doc(), None, False)), mock.patch.object(
                repo_fetch_files, "fetch_raw_file", return_value=b"print('ok')\n"
            ) as raw:
                code = repo_fetch_files.main(
                    ["--repo", "owner/repo", "--patterns", "src/**", "--fetch-mode", "raw", "--out", str(out)]
                )
            self.assertEqual(code, 0)
            raw.assert_called_once_with("owner", "repo", "main", "src/app.py")
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["fetch_source"], "raw-github")
            self.assertEqual(row["size_state"], "known_after_fetch")

    def test_auto_chooses_git_above_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "files.jsonl"
            workdir = Path(tmp) / "clone"
            with mock.patch.object(repo_fetch_files, "collect_metadata_document", return_value=(doc(), None, False)), mock.patch.object(
                repo_fetch_files, "clone_blobless_no_checkout"
            ) as clone, mock.patch.object(repo_fetch_files, "git_show_file", return_value=b"hello"):
                code = repo_fetch_files.main(
                    [
                        "--repo",
                        "owner/repo",
                        "--patterns",
                        "src/**",
                        "--raw-threshold",
                        "0",
                        "--workdir",
                        str(workdir),
                        "--out",
                        str(out),
                    ]
                )
            self.assertEqual(code, 0)
            clone.assert_called_once()
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["fetch_source"], "git-show")

    def test_auto_falls_back_to_git_on_raw_rate_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "files.jsonl"
            workdir = Path(tmp) / "clone"
            rate_error = common.GithubHttpError("url", 429, "Too Many Requests")
            with mock.patch.object(repo_fetch_files, "collect_metadata_document", return_value=(doc(), None, False)), mock.patch.object(
                repo_fetch_files, "fetch_raw_file", side_effect=rate_error
            ), mock.patch.object(repo_fetch_files, "clone_blobless_no_checkout") as clone, mock.patch.object(
                repo_fetch_files, "git_show_file", return_value=b"hello"
            ):
                code = repo_fetch_files.main(
                    [
                        "--repo",
                        "owner/repo",
                        "--patterns",
                        "src/**",
                        "--workdir",
                        str(workdir),
                        "--out",
                        str(out),
                    ]
                )
            self.assertEqual(code, 0)
            clone.assert_called_once()
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["fetch_source"], "git-show")
            self.assertEqual(row["content"], "hello")


if __name__ == "__main__":
    unittest.main()
