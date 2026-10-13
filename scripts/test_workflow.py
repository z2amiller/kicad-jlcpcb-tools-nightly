"""Checks of nightly.yml that a run can't afford to learn the slow way."""

from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "nightly.yml"


class TargetCheckoutTest(unittest.TestCase):
    def test_the_target_checkout_is_not_a_python_package_name(self):
        # The plugin's root __init__.py registers its ActionPlugin. pytest
        # imports a root conftest.py as <dir>.conftest when <dir> is a valid
        # identifier holding an __init__.py, which registers the plugin outside
        # KiCad; KiCad asserts PgmOrNull() and, on Windows, blocks on a modal
        # box. A hyphenated directory, as in upstream's own CI, avoids that.
        text = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r"repository: \$\{\{ needs\.plan\.outputs\.repository \}\}\n"
            r"\s+ref: .*\n\s+path: (\S+)",
            text,
        )
        self.assertIsNotNone(match, "target checkout step not found")
        directory = match.group(1)
        self.assertFalse(directory.isidentifier(), directory)
        self.assertIn(f"working-directory: {directory}\n", text)


if __name__ == "__main__":
    unittest.main()
