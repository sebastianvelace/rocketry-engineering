import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402


class PageSmokeTests(unittest.TestCase):
    def test_every_page_renders_without_uncaught_exception(self):
        pages = [
            "pages/1_Bench.py",
            "pages/2_Wiring.py",
            "pages/3_Motor.py",
            "pages/4_Flight.py",
            "pages/5_History.py",
        ]
        for page in pages:
            with self.subTest(page=page):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=20)
                app.switch_page(page).run(timeout=20)
                self.assertEqual([exception.message for exception in app.exception], [])


if __name__ == "__main__":
    unittest.main()
