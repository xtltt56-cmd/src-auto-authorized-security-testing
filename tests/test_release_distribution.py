import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class ReleaseDistributionTests(unittest.TestCase):
    def test_version_is_single_semantic_version(self):
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_release_builder_has_explicit_safe_distribution_contract(self):
        content = (PROJECT_ROOT / "tools" / "build_windows_release.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("SRC-Auto-Windows-x64.zip", content)
        self.assertIn("release-manifest.json", content)
        self.assertIn("SHA256SUMS.txt", content)
        self.assertIn("git ls-files", content)
        self.assertNotIn("git archive --format", content)
        for excluded in ("config\\secrets", "config\\sessions", "data", "reports", "validation"):
            self.assertIn(excluded, content)

    def test_release_builder_only_allows_the_intentionally_bundled_python_runtime(self):
        content = (PROJECT_ROOT / "tools" / "build_windows_release.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("runtime\\python", content)
        self.assertIn("$runtimeIncluded", content)
        self.assertIn("$runtimeAllowed", content)
        self.assertIn("$runtimePrunePaths", content)
        self.assertIn("'Lib\\test'", content)
        self.assertIn("Select-Object -First 20", content)

    def test_small_source_wrappers_are_not_git_lfs_objects(self):
        content = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("vendor/bin/*.cmd -filter -diff -merge text", content)

    def test_release_workflow_tests_builds_and_publishes_fixed_asset_name(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch", content)
        self.assertIn("tags:", content)
        self.assertIn("v*", content)
        self.assertIn("permissions:", content)
        self.assertIn("contents: write", content)
        self.assertIn("python -m unittest discover", content)
        self.assertIn("npm run build", content)
        self.assertIn("build_windows_release.ps1", content)
        self.assertIn("SRC-Auto-Windows-x64.zip", content)
        self.assertIn("--latest", content)

    def test_ci_workflow_covers_python_and_dashboard(self):
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("pull_request", content)
        self.assertIn("push", content)
        self.assertIn("python -m unittest discover", content)
        self.assertIn("npm ci", content)
        self.assertIn("npm run test", content)
        self.assertIn("npm run build", content)
        self.assertIn("$grepExit", content)
        self.assertIn("$grepExit -eq 1", content)

    def test_no_secret_match_is_an_explicit_success_in_every_workflow(self):
        for name in ("ci.yml", "release.yml"):
            content = (PROJECT_ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertRegex(
                content,
                r"if\(\$grepExit -eq 1\)\{[^\n]*exit 0[^\n]*\}",
                msg=name,
            )

    def test_download_documentation_uses_stable_latest_release_url(self):
        content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        url = (
            "https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/"
            "releases/latest/download/SRC-Auto-Windows-x64.zip"
        )
        self.assertIn(url, content)

    def test_release_manifest_uses_current_version_as_the_release_tag(self):
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        content = (PROJECT_ROOT / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")
        self.assertIn("**发布标识：** `v{}`".format(version), content)
        self.assertNotIn("本发布的 Git 标签为 `v0.8.28-loopback-lab-control`", content)


if __name__ == "__main__":
    unittest.main()
