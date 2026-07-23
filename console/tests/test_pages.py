import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import diagrams, wiring_guides  # noqa: E402


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

    def test_spanish_session_renders_home_and_wiring(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=20)
        language = next(item for item in app.selectbox if item.label == "Language / Idioma")
        language.set_value("Español")
        app.run(timeout=20)
        self.assertEqual([exception.message for exception in app.exception], [])
        self.assertEqual(language.value, "Español")

        app.switch_page("pages/2_Wiring.py").run(timeout=20)
        next(item for item in app.selectbox if item.label == "Language / Idioma").set_value("Español")
        app.run(timeout=20)
        self.assertEqual([exception.message for exception in app.exception], [])
        self.assertTrue(any("¿Qué vas a conectar?" == item.label for item in app.radio))

    def test_every_circuit_has_complete_bilingual_guidance(self):
        self.assertEqual(set(diagrams.CIRCUITS), set(wiring_guides.GUIDES))
        for guide in wiring_guides.GUIDES.values():
            for field in ("short", "purpose", "use_for", "parts", "before", "verify"):
                self.assertIn(field, guide)
                self.assertIn(f"{field}_es", guide)
                self.assertTrue(guide[field])
                self.assertTrue(guide[f"{field}_es"])


if __name__ == "__main__":
    unittest.main()
