import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


class ReleaseDistributionTests(unittest.TestCase):
    def _release_with_existing_dashboard(self, build_fails=False):
        git, shell = shutil.which('git'), shutil.which('pwsh') or shutil.which('powershell')
        node = PROJECT_ROOT / 'runtime/node-v22.23.0-win-x64/node.exe'
        if not git or not shell or not node.is_file():
            self.skipTest('Windows release tools required for actual packaging regression')
        with tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT / 'validation')) as folder:
            root = Path(folder)
            (root / 'tools').mkdir()
            (root / 'dashboard/dist').mkdir(parents=True)
            runtime = root / 'runtime/node-v22.23.0-win-x64'
            (runtime / 'node_modules/npm/bin').mkdir(parents=True)
            os.link(str(node), str(runtime / 'node.exe'))
            (runtime / 'node_modules/npm/bin/npm-cli.js').write_text(
                "const fs=require('fs'),path=require('path');"
                "const dir=process.argv[process.argv.indexOf('--prefix')+1];"
                + ("process.exit(9);" if build_fails else
                   "fs.writeFileSync(path.join(dir,'dist/index.html'),'<html>fresh-build</html>');"), encoding='utf-8')
            shutil.copyfile(str(PROJECT_ROOT / 'tools/build_windows_release.ps1'), str(root / 'tools/build_windows_release.ps1'))
            (root / 'VERSION').write_text('1.0.0', encoding='utf-8')
            (root / '.gitignore').write_text('dashboard/dist/\nartifacts/\nruntime/\n', encoding='utf-8')
            (root / 'dashboard/dist/index.html').write_text('<html>stale-build</html>', encoding='utf-8')
            for args in (('init',), ('add', '.'), ('-c', 'user.name=Release gate test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'synthetic release')):
                subprocess.run([git] + list(args), cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-File', str(root / 'tools/build_windows_release.ps1')],
                                    cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if build_fails:
                self.assertNotEqual(result.returncode, 0, 'A failed rebuild must not publish an existing stale dashboard')
                self.assertFalse((root / 'artifacts/release').exists())
            else:
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode('utf-8', errors='replace'))
                with zipfile.ZipFile(root / 'artifacts/release/SRC-Auto-Windows-x64.zip') as archive:
                    self.assertEqual(archive.read('SRC-Auto/dashboard/dist/index.html'), b'<html>fresh-build</html>')

    def test_default_release_rebuilds_existing_dashboard(self):
        self._release_with_existing_dashboard()

    def test_failed_dashboard_rebuild_does_not_package_stale_dist(self):
        self._release_with_existing_dashboard(True)

    def test_python_metadata_and_package_version_match_release(self):
        import src_auto
        version = (PROJECT_ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        metadata = (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertEqual(re.search(r'^version = "([^"]+)"', metadata, re.M).group(1), version)
        self.assertEqual(src_auto.__version__, version)

    def _assert_dirty_source_blocks_release(self, untracked):
        git, shell = shutil.which('git'), shutil.which('pwsh') or shutil.which('powershell')
        if not git or not shell:
            self.skipTest('Windows PowerShell and Git required for actual packaging gate')
        with tempfile.TemporaryDirectory(dir=str(PROJECT_ROOT / 'validation')) as folder:
            root = Path(folder)
            (root / 'tools').mkdir()
            (root / 'dashboard/dist').mkdir(parents=True)
            shutil.copyfile(str(PROJECT_ROOT / 'tools/build_windows_release.ps1'), str(root / 'tools/build_windows_release.ps1'))
            (root / 'VERSION').write_text('1.0.0', encoding='utf-8')
            (root / '.gitignore').write_text('dashboard/dist/\nartifacts/\n', encoding='utf-8')
            (root / 'dashboard/dist/index.html').write_text('<html>synthetic</html>', encoding='utf-8')
            def run_git(*args):
                subprocess.run([git] + list(args), cwd=str(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            run_git('init')
            run_git('add', 'VERSION', '.gitignore', 'tools/build_windows_release.ps1')
            run_git('-c', 'user.name=Release gate test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'synthetic fixture')
            if untracked:
                (root / 'new-module.py').write_text('# synthetic untracked source', encoding='utf-8')
            else:
                (root / 'VERSION').write_text('1.0.1', encoding='utf-8')
            result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-File', str(root / 'tools/build_windows_release.ps1'), '-SkipDashboardBuild'], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(result.returncode, 0, 'A dirty checkout must not produce a release with an old commit identity')
            self.assertIn(b'release_source_not_clean', result.stdout + result.stderr, 'Failure must be the source-identity gate, not an unrelated error')
            self.assertFalse((root / 'artifacts/release').exists(), 'The guard must run before creating or replacing output')

    def test_actual_release_blocks_modified_tracked_source(self):
        self._assert_dirty_source_blocks_release(False)

    def test_actual_release_blocks_untracked_source(self):
        self._assert_dirty_source_blocks_release(True)

    def test_l4_manual_lab_launcher_is_in_the_distribution_allowlist(self):
        content = (PROJECT_ROOT / 'tools/build_windows_release.ps1').read_text(encoding='utf-8-sig')
        root_files = content[content.index('$rootFiles = @('):content.index('$deniedFragments = @(')]
        self.assertIn("'START_L4_LAB.ps1'", root_files)
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
        self.assertIn("python -m coverage run -m unittest discover", content)
        self.assertIn("python -m coverage report", content)
        self.assertIn("if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }", content)
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
        self.assertIn("python -m coverage run -m unittest discover", content)
        self.assertIn("python -m coverage report", content)
        self.assertIn("if($LASTEXITCODE -ne 0){ exit $LASTEXITCODE }", content)
        self.assertIn("npm ci", content)
        self.assertIn("npm run test", content)
        self.assertIn("npm run test:coverage", content)
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
