from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA_SCRIPT = ROOT / ".agents" / "skills" / "github-code-scraper-skill" / "scripts" / "repo_metadata.py"


@unittest.skipUnless(os.environ.get("RUN_GITHUB_INTEGRATION") == "1", "set RUN_GITHUB_INTEGRATION=1 for live GitHub tests")
class GithubIntegrationTests(unittest.TestCase):
    def test_live_metadata_for_octocat_hello_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "metadata.json"
            result = subprocess.run(
                [sys.executable, str(METADATA_SCRIPT), "--repo", "octocat/Hello-World", "--strategy", "auto", "--out", str(out)],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(out.read_text())
            self.assertEqual(payload["repo"], "octocat/Hello-World")
            self.assertGreaterEqual(payload["counts"]["files"], 1)


if __name__ == "__main__":
    unittest.main()
