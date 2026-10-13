"""Capture actual Probaho UI using an isolated, disposable seeded database.

Only this production-assets folder is written. No default user database,
application files, existing evidence files, or source reference are modified.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
ROOT = ASSETS.parents[2]
sys.path.insert(0, str(ROOT))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ASSETS / "browser-runtime")

from finmate.server import Application, make_handler
from playwright.sync_api import expect, sync_playwright


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not list((ASSETS / "browser-runtime").glob("ffmpeg-*/ffmpeg-win64.exe")):
        subprocess.run([sys.executable, "-m", "playwright", "install", "ffmpeg"], check=True)
    errors = []
    captures = []
    with tempfile.TemporaryDirectory(prefix="isolated-fixture-", dir=ASSETS) as folder:
        app = Application(Path(folder) / "presentation-fixture.sqlite3", key="", seed=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        before = app.dashboard("shapla-services", "2026-10-31")
        assert before["projection"]["base"]["closing_cash_minor"] == -1_000_000
        assert before["projection"]["base"]["minimum_cash_minor"] == -1_000_000
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                    record_video_dir=str(ASSETS / "recordings"),
                    record_video_size={"width": 1440, "height": 1000},
                )
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                video = page.video
                began = time.monotonic()

                def hold(seconds=2.4):
                    page.wait_for_timeout(int(seconds * 1000))

                def capture(name, focus=None):
                    if focus is None:
                        page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
                    else:
                        page.locator(focus).first.evaluate("el => window.scrollTo({top:Math.max(0,el.getBoundingClientRect().top+window.scrollY-35),behavior:'smooth'})")
                    page.wait_for_timeout(650)
                    path = ASSETS / f"{name}.png"
                    page.screenshot(path=str(path), full_page=False)
                    captures.append({"file": path.name, "elapsed_seconds": round(time.monotonic() - began, 2), "scroll_y": page.evaluate("window.scrollY")})
                    print(f"Captured {path.name}", flush=True)
                    hold()

                def navigate(view):
                    page.locator(f'.nav-item[data-view="{view}"]').click()
                    page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
                    page.wait_for_timeout(400)

                page.goto(url)
                expect(page.get_by_role("heading", name="Cash gap overview")).to_be_visible()
                expect(page.locator("#workspace-name")).to_have_text("Shapla Services")
                expect(page.get_by_text("BDT -10,000", exact=True).first).to_be_visible()
                expect(page.get_by_text("BDT 30,000", exact=True).first).to_be_visible()
                capture("overview")

                navigate("records")
                expect(page.get_by_role("heading", name="Records")).to_be_visible()
                capture("records")
                page.get_by_role("button", name="Import combined CSV", exact=True).click()
                page.locator("#import-replace-demo").uncheck()
                csv_path = ROOT / "examples" / "probaho-sample-records.csv"
                page.locator("#csv-file").set_input_files(str(csv_path))
                expect(page.get_by_text("4 rows validated locally", exact=False)).to_be_visible()
                capture("import-preview")
                page.get_by_role("button", name="Cancel", exact=True).click()
                expect(page.locator("#import-dialog")).not_to_be_visible()
                after_preview = app.dashboard("shapla-services", "2026-10-31")
                assert after_preview["projection"]["base"]["closing_cash_minor"] == -1_000_000
                assert before["transactions"] == after_preview["transactions"]
                assert before["invoices"] == after_preview["invoices"]
                assert before["bills"] == after_preview["bills"]

                navigate("assistant")
                page.get_by_role("button", name="What is the cash gap?", exact=True).click()
                expect(page.get_by_text("Local demo", exact=True).last).to_be_visible()
                expect(page.get_by_text("reserve shortfall", exact=False).last).to_be_visible()
                answer = page.locator(".message.assistant").last.inner_text()
                assert "10,000" in answer and "30,000" in answer, answer
                capture("assistant")

                navigate("plans")
                page.get_by_role("button", name="Compare recovery plans", exact=True).click()
                supplier = page.locator(".plan-card").filter(has_text="Supplier reschedule").first
                expect(supplier.get_by_text("BDT 40,000", exact=False).first).to_be_visible()
                capture("plans")
                supplier.get_by_role("button", name="Approve plan", exact=True).click()
                expect(page.get_by_text("HUMAN APPROVAL RECORDED", exact=True)).to_be_visible()
                execute = page.get_by_role("button", name="Execute approved action", exact=True)
                expect(execute).to_be_disabled()
                capture("approved", ".pending-panel")

                page.get_by_role("button", name="Simulate supplier acceptance", exact=True).click()
                expect(execute).to_be_enabled()
                expect(page.locator(".consent-box.accepted")).to_be_visible()
                capture("consent", ".pending-panel")

                execute.click()
                expect(page.get_by_text("Receipt recorded", exact=True)).to_be_visible()
                expect(page.get_by_text("Actual post-commit dashboard state", exact=True)).to_be_visible()
                expect(page.get_by_text("Atomic read-back verified", exact=True)).to_be_visible()
                expect(page.get_by_text("No real-money movement occurred.", exact=False)).to_be_visible()
                assert len(app.store.executions("shapla-services")) == 1
                capture("executed", ".result-panel")
                # An extra lower viewport supplies readable atomic-read-back detail.
                capture("readback", ".current-state-note")

                navigate("overview")
                expect(page.get_by_text("Accepted recovery schedule active", exact=True)).to_be_visible()
                recovery = app.dashboard("shapla-services", "2026-10-31")
                recovered = recovery["projection"]["approved_recovery"]
                assert recovered["closing_cash_minor"] == 3_000_000, recovered
                assert recovered["minimum_cash_minor"] == 3_000_000, recovered
                assert recovered["minimum_reserve_shortfall_minor"] == 0, recovered
                capture("recovered-overview")

                navigate("activity")
                expect(page.get_by_text("Hash-chain status: consistent", exact=True)).to_be_visible()
                capture("activity")
                with page.expect_download() as evidence_download:
                    page.get_by_role("button", name="Export evidence", exact=True).click()
                evidence_download.value.save_as(str(ASSETS / "execution-evidence.json"))
                with page.expect_download() as results_download:
                    page.get_by_role("button", name="Export results", exact=True).click()
                results_download.value.save_as(str(ASSETS / "results.csv"))
                assert not errors, errors
                context.close()
                if video is not None:
                    video.save_as(str(ASSETS / "realflow.webm"))
                browser.close()

                manifest = {
                    "status": "passed", "source": "Actual Probaho UI; installed Chrome via Playwright",
                    "viewport": [1440, 1000], "full_page": False,
                    "fixture": "Fresh synthetic Shapla Services in isolated disposable database",
                    "live_ai_tested": False, "import": "Valid example CSV locally previewed then cancelled; no records changed",
                    "initial_closing_bdt": -10000, "initial_reserve_shortfall_bdt": 30000,
                    "supplier_reschedule_amount_bdt": 40000,
                    "approved_recovery_closing_bdt": 30000, "approved_recovery_shortfall_bdt": 0,
                    "real_money_movement": False, "supplier_contacted": False,
                    "screenshots": captures, "page_errors": errors,
                }
                (ASSETS / "capture-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(json.dumps(manifest, indent=2), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
