"""Capture isolated Probaho synthetic-workspace previews."""
from __future__ import annotations

import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from finmate.server import Application, make_handler
from playwright.sync_api import expect, sync_playwright


def main():
    output = ROOT / "evidence"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Application(Path(folder) / "preview.sqlite3")))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                desktop = browser.new_context(viewport={"width": 1440, "height": 1040})
                page = desktop.new_page()
                page.goto(url)
                expect(page.get_by_role("heading", name="Cash gap overview")).to_be_visible()
                page.screenshot(path=str(output / "overview-desktop.png"), full_page=True)
                page.locator('.nav-item[data-view="plans"]').click()
                page.get_by_role("button", name="Compare recovery plans", exact=True).click()
                expect(page.get_by_text("Supplier reschedule", exact=False).first).to_be_visible()
                page.screenshot(path=str(output / "plan-comparison.png"), full_page=True)
                page.locator('.nav-item[data-view="assistant"]').click()
                page.get_by_role("button", name="What is the cash gap?", exact=True).click()
                expect(page.get_by_text("Local demo", exact=True).last).to_be_visible()
                page.screenshot(path=str(output / "assistant-demo.png"), full_page=True)
                mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                phone = mobile.new_page()
                phone.goto(url)
                expect(phone.get_by_role("heading", name="Cash gap overview")).to_be_visible()
                phone.screenshot(path=str(output / "overview-mobile.png"), full_page=True)
                browser.close()
                print("Captured isolated Probaho synthetic-workspace previews.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
