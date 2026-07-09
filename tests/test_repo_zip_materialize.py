from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "github-code-scraper-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import repo_zip_materialize


def write_repo_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("repo-main/a.py", "print('a')\n")
        archive.writestr("repo-main/b.txt", "b\n")
        archive.writestr("repo-main/.env", "SECRET=1\n")


def fake_download(owner: str, repo: str, ref: str | None, zip_path: Path) -> str:
    write_repo_zip(zip_path)
    return ref or "main"


class RepoZipMaterializeTests(unittest.TestCase):
    def test_manifest_output_and_keep_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "extract"
            manifest = Path(tmp) / "manifest.json"
            with mock.patch.object(repo_zip_materialize, "_download_zip", side_effect=fake_download):
                code = repo_zip_materialize.main(
                    ["--repo", "owner/repo", "--workdir", str(workdir), "--keep-workdir", "--manifest-out", str(manifest)]
                )
            self.assertEqual(code, 0)
            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["strategy"], "zip")
            self.assertTrue((workdir / "repo-main" / "a.py").exists())
            paths = {item["path"] for item in payload["files"]}
            self.assertIn("a.py", paths)
            self.assertNotIn(".env", paths)

    def test_jsonl_output_filters_patterns_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "files.jsonl"
            with mock.patch.object(repo_zip_materialize, "_download_zip", side_effect=fake_download):
                code = repo_zip_materialize.main(
                    ["--repo", "owner/repo", "--patterns", "*.py", "--jsonl-out", str(out)]
                )
            self.assertEqual(code, 0)
            rows = [json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual([row["path"] for row in rows], ["a.py"])
            self.assertEqual(rows[0]["fetch_source"], "zip")
            self.assertEqual(rows[0]["content"], "print('a')\n")

    def test_cleanup_removes_explicit_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "extract"
            out = Path(tmp) / "files.jsonl"
            with mock.patch.object(repo_zip_materialize, "_download_zip", side_effect=fake_download):
                code = repo_zip_materialize.main(
                    ["--repo", "owner/repo", "--workdir", str(workdir), "--cleanup", "--jsonl-out", str(out)]
                )
            self.assertEqual(code, 0)
            self.assertFalse(workdir.exists())
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
