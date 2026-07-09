from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "github-code-scraper-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import github_common as common


def meta(path: str, entry_type: str = "file", mode: str = "100644", size: int | None = 1) -> dict:
    return common.enrich_meta(
        {
            "repo": "owner/repo",
            "ref": "main",
            "path": path,
            "type": entry_type,
            "mode": mode,
            "sha": "abc",
            "size": size,
            "size_state": "known" if size is not None else "unknown_until_fetch",
            "source": "api-tree",
        }
    )


class GithubCommonTests(unittest.TestCase):
    def test_parse_repo_accepts_supported_forms(self) -> None:
        expected = ("pallets", "flask")
        self.assertEqual(common.parse_repo("pallets/flask"), expected)
        self.assertEqual(common.parse_repo("https://github.com/pallets/flask"), expected)
        self.assertEqual(common.parse_repo("https://github.com/pallets/flask.git"), expected)
        self.assertEqual(common.parse_repo("git@github.com:pallets/flask.git"), expected)

    def test_parse_repo_rejects_invalid_values(self) -> None:
        for value in ["", "github.com/pallets/flask", "https://example.com/pallets/flask", "owner/repo/extra"]:
            with self.subTest(value=value):
                with self.assertRaises(common.InvalidArgumentError):
                    common.parse_repo(value)

    def test_api_tree_normalization_modes(self) -> None:
        cases = [
            ({"path": "app.py", "mode": "100644", "type": "blob", "sha": "1", "size": 10}, "file", False, False),
            ({"path": "bin/app", "mode": "100755", "type": "blob", "sha": "2", "size": 11}, "file", True, False),
            ({"path": "src", "mode": "040000", "type": "tree", "sha": "3"}, "directory", False, False),
            ({"path": "link", "mode": "120000", "type": "blob", "sha": "4", "size": 6}, "symlink", False, True),
            ({"path": "dep", "mode": "160000", "type": "commit", "sha": "5"}, "submodule", False, False),
            ({"path": "odd", "mode": "000000", "type": "weird", "sha": "6"}, "unknown", False, False),
        ]
        for item, entry_type, executable, symlink in cases:
            with self.subTest(item=item):
                normalized = common.normalize_api_tree_item(item, "owner/repo", "main")
                self.assertEqual(normalized["type"], entry_type)
                self.assertEqual(normalized["executable"], executable)
                self.assertEqual(normalized["symlink"], symlink)
                self.assertEqual(normalized["repo"], "owner/repo")
                self.assertEqual(normalized["ref"], "main")

    def test_git_ls_tree_z_parsing(self) -> None:
        output = (
            b"040000 tree aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tsrc\0"
            b"100644 blob bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\tsrc/file name.py\0"
            b"120000 blob cccccccccccccccccccccccccccccccccccccccc\tlink\0"
            b"160000 commit dddddddddddddddddddddddddddddddddddddddd\tvendor/lib\0"
        )
        entries = common.parse_git_ls_tree_z(output, "owner/repo", "main")
        by_path = {entry["path"]: entry for entry in entries}
        self.assertEqual(by_path["src"]["type"], "directory")
        self.assertEqual(by_path["src/file name.py"]["type"], "file")
        self.assertIsNone(by_path["src/file name.py"]["size"])
        self.assertEqual(by_path["src/file name.py"]["size_state"], "unknown_until_fetch")
        self.assertTrue(by_path["link"]["symlink"])
        self.assertTrue(by_path["vendor/lib"]["submodule"])

    def test_pattern_selection(self) -> None:
        metas = [
            meta("README.md"),
            meta("src/app.py"),
            meta("src/nested/util.py"),
            meta("src/app.test.py"),
            meta("node_modules/pkg/index.js"),
            meta(".env"),
            meta("assets/logo.png"),
            meta("src", "directory", "040000", None),
        ]
        self.assertTrue(common.matches_patterns("src/app.py", ["src/**"], []))
        self.assertTrue(common.matches_patterns("src/app.py", ["src/**/*.py"], []))
        self.assertTrue(common.matches_patterns("src/nested/util.py", ["src/**/*.py"], []))
        self.assertTrue(common.matches_patterns("README.md", ["README.md"], []))
        self.assertTrue(common.matches_patterns("src/app.py", ["src/"], []))
        selected = common.select_files(metas, ["**/*.py"], ["**/*.test.py"], None, False, False)
        self.assertEqual([item["path"] for item in selected], ["src/app.py", "src/nested/util.py"])
        all_selected = common.select_files(metas, [], [], None, False, False)
        paths = {item["path"] for item in all_selected}
        self.assertIn("README.md", paths)
        self.assertNotIn("node_modules/pkg/index.js", paths)
        self.assertNotIn(".env", paths)
        self.assertNotIn("assets/logo.png", paths)
        self.assertNotIn("src", paths)

    def test_raw_github_url_encoding(self) -> None:
        self.assertEqual(
            common.raw_github_url("owner", "repo", "main", "src/file name.py"),
            "https://raw.githubusercontent.com/owner/repo/main/src/file%20name.py",
        )
        self.assertEqual(
            common.raw_github_url("owner", "repo", "feature/x", "a+b/#file.py"),
            "https://raw.githubusercontent.com/owner/repo/feature%2Fx/a%2Bb/%23file.py",
        )

    def test_content_decoding(self) -> None:
        self.assertEqual(common.bytes_to_text("hello".encode()), ("hello", None))
        self.assertEqual(common.bytes_to_text(b"a\0b"), (None, "binary"))
        self.assertEqual(common.bytes_to_text(b"\xff"), (None, "non_utf8"))
        text, skipped = common.bytes_to_text(b"\xff", include_binary=True)
        self.assertIsNone(skipped)
        self.assertIn("\ufffd", text)

    def test_safe_extract_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "repo.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("repo-main/README.md", "ok")
            root = common.safe_extract_zip(zip_path, tmp_path / "extract")
            self.assertEqual(root.name, "repo-main")
            self.assertEqual((root / "README.md").read_text(), "ok")

    def test_safe_extract_zip_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "bad.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../evil", "bad")
            with self.assertRaises(common.UnsafeArchiveError):
                common.safe_extract_zip(zip_path, tmp_path / "extract")


if __name__ == "__main__":
    unittest.main()
