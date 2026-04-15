import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OpenSourceReleaseTests(unittest.TestCase):
    def test_license_file_exists(self) -> None:
        self.assertTrue((ROOT / "LICENSE").exists())

    def test_contributing_guide_exists(self) -> None:
        self.assertTrue((ROOT / "CONTRIBUTING.md").exists())


if __name__ == "__main__":
    unittest.main()
