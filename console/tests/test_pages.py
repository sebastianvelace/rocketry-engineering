import sys
import unittest
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

from core import diagrams, wiring_guides  # noqa: E402
from core import ui  # noqa: E402


class PageSmokeTests(unittest.TestCase):
    def test_every_page_renders_without_uncaught_exception(self):
        pages = [
            "pages/1_Bench.py",
            "pages/2_Wiring.py",
            "pages/3_Motor.py",
            "pages/4_Flight.py",
            "pages/5_History.py",
            "pages/6_Agent.py",
        ]
        for page in pages:
            with self.subTest(page=page):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=20)
                app.switch_page(page).run(timeout=20)
                self.assertEqual([exception.message for exception in app.exception], [])

    def test_spanish_session_renders_home_and_wiring(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=20)
        language = app.segmented_control[0]
        language.set_value("ES")
        app.run(timeout=20)
        self.assertEqual([exception.message for exception in app.exception], [])
        self.assertEqual(language.value, "ES")

        app.switch_page("pages/2_Wiring.py").run(timeout=20)
        self.assertEqual([exception.message for exception in app.exception], [])
        self.assertEqual(app.segmented_control[0].value, "ES")
        self.assertTrue(any("¿Qué vas a conectar?" == item.label for item in app.radio))

    def test_every_circuit_has_complete_bilingual_guidance(self):
        self.assertEqual(set(diagrams.CIRCUITS), set(wiring_guides.GUIDES))
        for guide in wiring_guides.GUIDES.values():
            for field in ("short", "purpose", "use_for", "parts", "before", "verify"):
                self.assertIn(field, guide)
                self.assertIn(f"{field}_es", guide)
                self.assertTrue(guide[field])
                self.assertTrue(guide[f"{field}_es"])

    def test_schematic_is_embedded_as_visible_themed_svg(self):
        svg, _ = diagrams.direct_jumper()
        uri = ui.schematic_data_uri(svg)
        decoded = base64.b64decode(uri.split(",", 1)[1]).decode()
        self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
        self.assertIn("stroke:#d7dee8", decoded)
        self.assertIn('fill="#d7dee8"', decoded)


if __name__ == "__main__":
    unittest.main()
