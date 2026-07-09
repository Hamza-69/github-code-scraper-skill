from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "github-code-scraper-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import github_common as common


def file_meta(source: str = "api-tree") -> dict:
    return common.enrich_meta(
        {
            "repo": "pallets/flask",
            "ref": "main",
            "path": "README.md",
            "type": "file",
            "mode": "100644",
            "sha": "abc",
            "size": 10 if source == "api-tree" else None,
            "size_state": "known" if source == "api-tree" else "unknown_until_fetch",
            "source": source,
        }
    )


class RepoMetadataTests(unittest.TestCase):
    def test_api_tree_not_truncated_returns_metadata(self) -> None:
        with mock.patch.object(common, "fetch_api_tree", return_value=([file_meta()], False)):
            doc, cleanup, kept = common.collect_metadata_document("pallets/flask", "main", "auto")
        self.assertIsNone(cleanup)
        self.assertFalse(kept)
        self.assertEqual(doc["strategy"], "api-tree")
        self.assertTrue(doc["size_known"])
        self.assertEqual(doc["counts"]["files"], 1)

    def test_auto_truncated_api_falls_back_to_git_tree(self) -> None:
        git_meta = file_meta("git-tree")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(common, "fetch_api_tree", return_value=([file_meta()], True)), mock.patch.object(
                common, "clone_blobless_no_checkout"
            ) as clone, mock.patch.object(common, "git_tree_metadata", return_value=[git_meta]):
                doc, cleanup, kept = common.collect_metadata_document("pallets/flask", "main", "auto", tmp, False)
        clone.assert_called_once()
        self.assertFalse(kept)
        self.assertEqual(doc["strategy"], "git-tree")
        self.assertTrue(doc["truncated"])
        self.assertFalse(doc["size_known"])
        self.assertIsNotNone(cleanup)

    def test_forced_api_tree_truncated_raises(self) -> None:
        with mock.patch.object(common, "fetch_api_tree", return_value=([file_meta()], True)):
            with self.assertRaises(common.ScraperError):
                common.collect_metadata_document("pallets/flask", "main", "api-tree")

    def test_missing_ref_tries_main_then_master(self) -> None:
        not_found = common.GithubHttpError("url", 404, "Not Found")
        with mock.patch.object(common, "fetch_api_tree", side_effect=[not_found, ([file_meta()], False)]) as fetch:
            doc, cleanup, kept = common.collect_metadata_document("pallets/flask", None, "auto")
        self.assertEqual(fetch.call_args_list[0].args[2], "main")
        self.assertEqual(fetch.call_args_list[1].args[2], "master")
        self.assertEqual(doc["ref"], "master")
        self.assertIsNone(cleanup)
        self.assertFalse(kept)


if __name__ == "__main__":
    unittest.main()
