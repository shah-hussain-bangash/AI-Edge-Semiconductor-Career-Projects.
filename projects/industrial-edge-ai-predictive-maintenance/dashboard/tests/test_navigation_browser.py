"""Real-browser acceptance for all 12 EDGEOPS navigation sections.

Runs against a disposable, isolated local FastAPI instance with a synthetic
account and database. Never touches the operator's .local/dashboard.sqlite3.

Install: python -m pip install -r requirements.txt playwright
         python -m playwright install chromium
Run:     python -m unittest discover -s tests -p test_navigation_browser.py -v
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "overview", "assets", "telemetry", "architecture", "insights", "hardware",
    "alerts", "maintenance", "security", "governance", "reports", "settings",
)


@unittest.skipIf(sync_playwright is None, "Install playwright and chromium for browser acceptance")
class NavigationBrowserAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="edgeops-navigation-")
        cls.email = "navigation-tester@example.invalid"
        cls.password = secrets.token_urlsafe(28)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["EDGEOPS_DASHBOARD_DB"] = str(Path(cls.temp.name) / "isolated.sqlite3")
        env["EDGEOPS_ADMIN_EMAIL"] = cls.email
        env["EDGEOPS_ADMIN_PASSWORD"] = cls.password
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            for _ in range(80):
                if cls.server.poll() is not None:
                    raise RuntimeError("Isolated FastAPI process exited during startup")
                try:
                    with urllib.request.urlopen(cls.base + "/signin", timeout=1) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(.15)
            else:
                raise RuntimeError("Isolated FastAPI service failed to respond")
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except BaseException:
            cls.server.terminate()
            cls.server.wait(timeout=8)
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.terminate()
        try:
            cls.server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=8)
        cls.server.stderr.close()
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(self.base + "/signin")
        self.page.locator("#email").fill(self.email)
        self.page.locator("#password").fill(self.password)
        self.page.locator("#submit").click()
        self.page.wait_for_url("**/app", timeout=10000)
        self.page.locator("#connection-chip[data-state='ok']").wait_for(timeout=10000)

    def tearDown(self):
        self.context.close()

    def assert_stage(self, name):
        section = self.page.locator(f"#page-{name}")
        self.assertTrue(section.is_visible(), f"Section {name} must be displayed")
        self.assertEqual(
            self.page.locator(".page-section.active").count(), 1,
            f"Only one content section may be active for {name}",
        )
        active = self.page.locator(f'.nav-item[data-page="{name}"]')
        self.assertEqual(active.get_attribute("aria-current"), "page")
        self.assertTrue(active.get_attribute("class").find("active") >= 0)
        self.assertGreater(len(self.page.locator("#page-title").inner_text().strip()), 4)
        self.assertGreater(len(self.page.locator("#page-subtitle").inner_text().strip()), 12)
        self.assertIn("#" + name, self.page.url)
        self.assertIn("EDGEOPS", self.page.title())

    def test_01_all_twelve_pages_render_without_browser_errors(self):
        self.assertEqual(self.page.locator(".nav-item[data-page]").count(), len(STAGES))
        for name in STAGES:
            with self.subTest(section=name):
                self.page.locator(f'.nav-item[data-page="{name}"]').click()
                self.assert_stage(name)
                if name == "architecture":
                    self.page.locator('[data-arch-node="mqtt"]').click()
                    self.assertIn("MQTT", self.page.locator("#arch-detail-title").inner_text())
                if name == "assets":
                    self.page.locator("#asset-search").fill("motor")
                    self.assertIn("of 12 assets", self.page.locator("#asset-result-count").inner_text())
                    self.page.locator("#asset-search").fill("")
                if name == "hardware":
                    self.page.locator("#hardware-table tr").first.wait_for()
                    self.assertGreater(self.page.locator("#hardware-table tr").count(), 10)
                if name == "security":
                    self.assertEqual(self.page.locator("#session-role").inner_text(), "admin")
                    self.assertGreater(self.page.locator("#audit-entries tr").count(), 0)
        self.assertFalse(self.errors, "Uncaught JS errors: " + repr(self.errors))

    def test_02_browser_history_and_deep_links(self):
        for name in ("assets", "architecture", "security"):
            self.page.locator(f'.nav-item[data-page="{name}"]').click()
            self.assert_stage(name)
        self.page.go_back()
        self.assert_stage("architecture")
        self.page.go_back()
        self.assert_stage("assets")
        self.page.go_forward()
        self.assert_stage("architecture")
        self.page.reload()
        self.assert_stage("architecture")
        self.assertFalse(self.errors, repr(self.errors))

    def test_03_mobile_navigation_open_close_and_section_selection(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        menu=self.page.locator("#menu-toggle")
        self.assertTrue(menu.is_visible())
        menu.click()
        self.assertEqual(menu.get_attribute("aria-expanded"), "true")
        self.page.locator('.nav-item[data-page="architecture"]').click()
        self.assert_stage("architecture")
        self.assertEqual(menu.get_attribute("aria-expanded"), "false")
        self.assertTrue(self.page.locator("#mobile-scrim").is_hidden())
        menu.click()
        self.page.keyboard.press("Escape")
        self.assertEqual(menu.get_attribute("aria-expanded"), "false")
        self.assertFalse(self.errors, repr(self.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
