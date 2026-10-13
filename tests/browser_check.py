"""Isolated Chrome verification for the Probaho Topic E workflow.

The server uses a temporary SQLite database. The check never touches the
developer's default workspace database.
"""
from __future__ import annotations

import json
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
        app = Application(Path(folder) / "browser-test.sqlite3", seed=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                desktop = browser.new_context(viewport={"width": 1440, "height": 1040}, device_scale_factor=1)
                page = desktop.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))

                page.goto(url)
                expect(page.get_by_role("heading", name="Cash gap overview")).to_be_visible()
                expect(page.locator("#workspace-name")).to_have_text("Shapla Services")
                expect(page.get_by_text("BDT 120,000", exact=True).first).to_be_visible()
                expect(page.get_by_text("BDT -10,000", exact=True).first).to_be_visible()
                expect(page.get_by_text("BDT 30,000", exact=True).first).to_be_visible()
                page.screenshot(path=str(output / "overview-desktop.png"), full_page=True)

                page.locator('.nav-item[data-view="plans"]').click()
                page.get_by_role("button", name="Compare recovery plans", exact=True).click()
                expect(page.get_by_text("Supplier reschedule", exact=False).first).to_be_visible()
                supplier = page.locator(".plan-card").filter(has_text="Supplier reschedule").first
                expect(supplier.get_by_text("BDT 40,000", exact=False).first).to_be_visible()
                supplier.get_by_role("button", name="Approve plan", exact=True).click()
                expect(page.get_by_text("HUMAN APPROVAL RECORDED", exact=True)).to_be_visible()
                execute = page.get_by_role("button", name="Execute approved action", exact=True)
                expect(execute).to_be_disabled()
                page.get_by_role("button", name="Simulate supplier acceptance", exact=True).click()
                expect(page.get_by_text("accepted", exact=False).first).to_be_visible()
                expect(execute).to_be_enabled()
                page.screenshot(path=str(output / "plan-approval.png"), full_page=True)
                execute.click()
                expect(page.get_by_text("Receipt recorded", exact=True)).to_be_visible()
                expect(page.get_by_text("Actual post-commit dashboard state", exact=True)).to_be_visible()
                expect(page.get_by_text("No real-money movement occurred.", exact=False)).to_be_visible()
                page.screenshot(path=str(output / "execution-receipt.png"), full_page=True)
                assert len(app.store.executions("shapla-services")) == 1

                page.locator('.nav-item[data-view="records"]').click()
                expect(page.get_by_role("heading", name="Records")).to_be_visible()
                search = page.get_by_role("searchbox", name="Search records")
                search.fill("bill-supplier-001")
                expect(page.locator("tbody tr")).to_have_count(1)
                search.fill("")

                csv_text = (
                    "record_type,business_id,id,date,description,amount,type,currency,due_date,status,customer,payee,issue_date,expected_collection_date,priority,reschedule_allowed\n"
                    "transaction,shapla-services,browser-xss-001,2026-10-15,<img src=x onerror=window.__xss=true>,123.45,income,BDT,,,,,,,,\n"
                )
                page.get_by_role("button", name="Import combined CSV", exact=True).click()
                page.locator("#import-replace-demo").uncheck()
                page.locator("#csv-file").set_input_files({"name": "browser-example.csv", "mimeType": "text/csv", "buffer": csv_text.encode()})
                expect(page.get_by_text("1 rows validated locally", exact=False)).to_be_visible()
                page.get_by_role("button", name="Validate and import", exact=True).click()
                expect(page.locator("#import-dialog")).not_to_be_visible()
                expect(page.get_by_text("<img src=x onerror=window.__xss=true>", exact=True)).to_be_visible()
                assert page.evaluate("window.__xss === undefined")
                page.screenshot(path=str(output / "records-import.png"), full_page=True)

                page.locator('.nav-item[data-view="assistant"]').click()
                page.get_by_role("button", name="What is the cash gap?", exact=True).click()
                expect(page.get_by_text("Local demo", exact=True).last).to_be_visible()
                expect(page.get_by_text("reserve shortfall", exact=False).last).to_be_visible()
                page.screenshot(path=str(output / "assistant-demo.png"), full_page=True)

                page.locator('.nav-item[data-view="activity"]').click()
                expect(page.get_by_text("Hash-chain status: consistent", exact=True)).to_be_visible()
                with page.expect_download() as evidence_download:
                    page.get_by_role("button", name="Export evidence", exact=True).click()
                evidence_download.value.save_as(str(output / "demo-execution-evidence.json"))
                evidence = json.loads((output / "demo-execution-evidence.json").read_text(encoding="utf-8"))
                assert evidence["hash_chain_valid"]
                assert evidence["track"] == "Topic E"
                assert any(entry["action"] == "plan.execute" for entry in evidence["entries"])
                with page.expect_download() as results_download:
                    page.get_by_role("button", name="Export results", exact=True).click()
                results_download.value.save_as(str(output / "probaho-results.csv"))

                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Reset sandbox", exact=True).click()
                expect(page.get_by_text("Sandbox schedule reset only", exact=False)).to_be_visible()

                mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=1)
                mobile_page = mobile.new_page()
                mobile_page.on("pageerror", lambda error: errors.append(str(error)))
                mobile_page.goto(url)
                expect(mobile_page.get_by_role("heading", name="Cash gap overview")).to_be_visible()
                assert mobile_page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
                mobile_page.screenshot(path=str(output / "overview-mobile.png"), full_page=True)
                mobile_page.locator('.nav-item[data-view="plans"]').click()
                expect(mobile_page.get_by_role("button", name="Compare recovery plans", exact=True)).to_be_visible()
                assert not errors, errors
                browser.close()

                verification = {
                    "status": "passed",
                    "browser": "Installed Chrome via Playwright",
                    "viewport_desktop": [1440, 1040],
                    "viewport_mobile": [390, 844],
                    "live_ai_tested": False,
                    "synthetic_fixture": "shapla-services",
                    "checks": [
                        "exact Shapla opening cash and reserve gap",
                        "recovery plan comparison",
                        "approval requires separate supplier-consent simulation",
                        "execution receipt and actual read-back",
                        "records search",
                        "combined CSV import",
                        "literal HTML escaping",
                        "local assistant gap explanation",
                        "per-business evidence export",
                        "execution-results export",
                        "sandbox reset preserves records",
                        "mobile no horizontal overflow",
                        "no JavaScript errors",
                    ],
                }
                (output / "browser-verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
                print("PASS: Probaho overview; plans; approval and consent gate; sandbox receipt/read-back; records import; assistant; evidence; reset; desktop/mobile; no JavaScript errors.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
