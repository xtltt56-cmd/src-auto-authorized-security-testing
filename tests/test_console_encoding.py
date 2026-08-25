import os
import subprocess
import sys
import unittest


class ConsoleEncodingTests(unittest.TestCase):
    def test_module_cli_help_is_utf8_and_keeps_simplified_chinese(self):
        env = os.environ.copy()
        env.pop("PYTHONIOENCODING", None)
        completed = subprocess.run(
            [sys.executable, "-m", "src_auto", "local-labs", "--help"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        output = completed.stdout.decode("utf-8")
        self.assertIn("靶场操作", output)
        self.assertIn("显示帮助并退出", output)


if __name__ == "__main__":
    unittest.main()
