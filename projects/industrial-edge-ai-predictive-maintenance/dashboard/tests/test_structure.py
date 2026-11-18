"""Dashboard Phase 1 static checks. Source-only; not browser/render tests."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DashboardStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "styles.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")

    def test_01_local_static_assets(self):
        self.assertIn('href="./styles.css"', self.html)
        self.assertIn('src="./app.js"', self.html)

    def test_02_synthetic_disclosure(self):
        self.assertIn("SYNTHETIC DATA", self.html)
        self.assertIn("No real devices", self.html)

    def test_03_six_navigation_sections(self):
        for page in ("overview", "telemetry", "assets", "alerts", "insights", "security"):
            with self.subTest(page=page):
                self.assertIn('data-page="'+page+'"', self.html)
                self.assertIn('id="page-'+page+'"', self.html)

    def test_04_no_remote_script_or_stylesheet(self):
        self.assertNotRegex(self.html, r'<script[^>]+src="https?://')
        self.assertNotRegex(self.html, r'<link[^>]+href="https?://')

    def test_05_no_backend_requests_or_motor_operations(self):
        self.assertNotIn("fetch(", self.js)
        self.assertNotIn("WebSocket(", self.js)
        self.assertNotRegex(self.html.lower(), r'(start motor|stop motor|energize)')

    def test_06_accessible_region_structure(self):
        for snippet in ('<main id="main">', 'aria-label="Main navigation"', 'class="skip"', 'aria-live="polite"'):
            self.assertIn(snippet, self.html)

    def test_07_responsive_layout_declared(self):
        self.assertIn("max-width:760px", self.css)
        self.assertIn("max-width:1220px", self.css)

    def test_08_client_only_export_marked_as_demo(self):
        self.assertIn("edgeops-synthetic-dashboard-snapshot.json", self.js)
        self.assertIn("mode:\"synthetic-ui-prototype\"", self.js)

    def test_09_phase_one_has_no_production_auth_claim(self):
        self.assertIn("does not implement user login", self.html)

    def test_10_fixture_dataset_has_twelve_assets(self):
        assets_match = re.search(r'const assets = \[(.*?)\];', self.js, re.S)
        self.assertIsNotNone(assets_match)
        self.assertEqual(len(re.findall(r'id:"[^"]+",name:', assets_match.group(1))), 12)

if __name__ == "__main__":
    unittest.main(verbosity=2)
