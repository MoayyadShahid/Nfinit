"""Local-only browser regression checks for the Studio controls.

Install playwright, run next dev without Supabase configuration, then:
  python frontend/tests/studio_controls.py --base-url http://127.0.0.1:3100
All API traffic is fulfilled with fixtures; external browser requests are blocked.
"""
import argparse
import gzip
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
MONACO_ROOT = ROOT.parent / "node_modules/monaco-editor"
MONACO_PATH = re.compile(r"/npm/monaco-editor@\d+\.\d+\.\d+/min/vs/(.+)")
SONNET = "anthropic/claude-sonnet-5.5"
OPUS = "anthropic/claude-opus-5.5"
STAMP = datetime.now(timezone.utc).isoformat()
CODE = "result = Box(20, 30, 10)"
UNTRUSTED = '<img src=x onerror="window.uiInjected=true">'
INSPECTION = {"valid": True, "shape_type": "Solid", "bounding_box_mm": {"x": 20, "y": 30, "z": 10}, "volume_mm3": 6000}


def revision(number=2):
    return {"id": f"revision-{number}", "projectId": "test-part", "revisionNumber": number, "createdAt": STAMP,
            "state": {"code": CODE, "messages": [{"role": "user", "content": "Make a bracket"}, {"role": "assistant", "content": CODE}],
                      "modelId": SONNET, "selection": None, "lastRunId": None}}


PROJECT = {"id": "test-part", "name": "Cable bracket", "revisionCount": 2, "createdAt": STAMP, "updatedAt": STAMP, "thumbnailUpdatedAt": STAMP}


class Fixtures:
    def __init__(self, page, base, active=True, local_agents=None):
        self.requests = []
        self.blocked = []
        self.errors = []
        self.active = active
        self.local_agents = local_agents
        self.export_status = 200
        self.run_failed = False
        self.phase = 0
        self.base = urlparse(base)
        self.model = gzip.decompress(next((ROOT / "public/demos/fpv-drone").glob("*.glb.gz")).read_bytes())
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.context.route("**/*", self.route)

    def route(self, route):
        request = route.request
        url = urlparse(request.url)
        path = url.path
        # The loader's default CDN version can differ from npm's peer version.
        # Use the installed package for this offline UI-integration test.
        monaco_asset = MONACO_PATH.fullmatch(path)
        if url.hostname == "cdn.jsdelivr.net" and monaco_asset:
            root = (MONACO_ROOT / "min/vs").resolve()
            asset = (root / monaco_asset.group(1)).resolve()
            if asset.is_relative_to(root) and asset.is_file():
                route.fulfill(path=str(asset), content_type=mimetypes.guess_type(str(asset))[0] or "application/octet-stream", headers={"Access-Control-Allow-Origin": "*"})
                return
        if url.hostname not in ("127.0.0.1", "localhost"):
            self.blocked.append(request.url)
            route.abort()
            return
        if path == "/fixture.glb":
            route.fulfill(status=200, content_type="model/gltf-binary", body=self.model, headers={"Access-Control-Allow-Origin": "*"})
            return
        if not path.startswith("/api/"):
            route.continue_()
            return
        body = request.post_data_json if request.method == "POST" else None
        self.requests.append((request.method, path, body))
        status, data = 200, None
        if path == "/api/cad/local-agents":
            status, data = (404, {"detail": "Not found"}) if self.local_agents is None else (200, {"local": True, "agents": self.local_agents})
        elif path == "/api/billing/status":
            data = {"enabled": True, "active": self.active, "status": "active" if self.active else "none", "currentPeriodEnd": None, "cancelAtPeriodEnd": False, "taxAtCheckout": False}
        elif path == "/api/projects" and request.method == "GET":
            data = [PROJECT, {**PROJECT, "id": "untrusted-name", "name": UNTRUSTED}]
        elif path == "/api/projects/test-part":
            data = {**PROJECT, "latestRevision": revision()}
        elif path == "/api/projects/test-part/revisions":
            data = [{k: v for k, v in revision(n).items() if k != "state"} for n in (2, 1)]
        elif path.endswith("/mesh"):
            data = {"url": "/fixture.glb", "expiresAt": STAMP, "bytes": len(self.model), "inspection": INSPECTION}
        elif re.fullmatch(r"/api/projects/test-part/revisions/[12]", path):
            data = revision(int(path[-1]))
        elif path == "/api/cad/export-model":
            route.fulfill(status=self.export_status, content_type="application/json" if self.export_status != 200 else "application/octet-stream", body='{"detail":"Subscription required"}' if self.export_status != 200 else 'fixture CAD export')
            return
        elif path == "/api/cad/runs" or path.startswith("/api/cad/runs/ui-run"):
            if path.endswith("/stream"):
                status, data = 503, {"detail": "Use local polling fixture"}
            else:
                after = int(parse_qs(url.query).get("after", ["0"])[0])
                events = [
                    {"seq": 1, "stage": "plan", "status": "started", "message": "Planning a cable bracket", "attempt": 1, "durationMs": None, "createdAt": STAMP},
                    {"seq": 2, "stage": "plan", "status": "complete", "message": "Plan ready", "attempt": 1, "durationMs": 1250, "createdAt": STAMP},
                    {"seq": 3, "stage": "inspect", "status": "started", "message": "Checking geometry", "attempt": 1, "durationMs": None, "createdAt": STAMP},
                    {"seq": 4, "stage": "inspect", "status": "failed", "message": UNTRUSTED, "attempt": 1, "durationMs": 750, "createdAt": STAMP},
                    {"seq": 5, "stage": "repair", "status": "started", "message": "Repairing the bracket", "attempt": 2, "durationMs": None, "createdAt": STAMP},
                    {"seq": 6, "stage": "repair", "status": "complete", "message": "Repair applied", "attempt": None, "durationMs": 2300, "createdAt": STAMP},
                    {"seq": 7, "stage": "inspect", "status": "started", "message": "Checking the repaired part", "attempt": None, "durationMs": None, "createdAt": STAMP},
                ]
                data = {"runId": "ui-run", "projectId": "test-part", "status": "failed" if self.run_failed else "running", "prompt": "Make a bracket", "modelId": OPUS, "result": None, "error": "Local fixture: the part could not be generated" if self.run_failed else None, "createdAt": STAMP, "completedAt": None,
                        "events": [] if request.method == "POST" else [e for e in events[:(3, 5, 7)[self.phase]] if e["seq"] > after]}
        else:
            raise AssertionError(f"Unexpected API request: {request.method} {path}")
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data))


def open_studio(browser, base, *, mobile=False, active=True, project=False, reduced=False, local_agents=None):
    context = browser.new_context(viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 1000}, is_mobile=mobile, has_touch=mobile, reduced_motion="reduce" if reduced else "no-preference")
    page = context.new_page()
    fixture = Fixtures(page, base, active, local_agents)
    # A locked account normally starts a demo. Suppress demo discovery in the
    # paywall fixture only; recorded demos are tested separately.
    if not active:
        page.route("**/demos/index.json", lambda route: route.fulfill(json={"demos": []}))
    page.goto(base + ("/studio?project=test-part" if project else "/studio?new=1"))
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name=re.compile("^Generation model:")).first).to_be_visible()
    return context, page, fixture


def palette(page, query=""):
    page.get_by_role("button", name="Search Studio commands").click()
    dialog = page.get_by_role("dialog", name="Studio commands")
    expect(dialog).to_be_visible()
    if query:
        dialog.get_by_role("combobox").fill(query)
    return dialog


def test_desktop(browser, base, shots):
    context, page, fixture = open_studio(browser, base)
    trigger = page.get_by_role("button", name="Generation model: Claude Sonnet 5.5")
    trigger.click()
    group = page.get_by_role("radiogroup", name="Generation model")
    expect(group.get_by_role("radio")).to_have_count(2)
    expect(group.get_by_role("radio", name=re.compile("Sonnet"))).to_be_checked()
    group.get_by_role("radio", name=re.compile("Opus")).click()
    expect(page.get_by_role("button", name="Generation model: Claude Opus 5.5")).to_be_focused()
    assert page.get_by_text("Effort", exact=True).count() == 0
    page.get_by_role("button", name="Generation model: Claude Opus 5.5").click()
    group.get_by_role("radio", name=re.compile("Opus")).focus()
    page.keyboard.press("ArrowUp", delay=100)
    expect(group.get_by_role("radio", name=re.compile("Sonnet"))).to_be_checked()
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    prompt = page.get_by_placeholder("Describe the part you want to make…")
    prompt.fill("Keep this draft")
    prompt.focus()
    page.keyboard.press("Control+k")
    expect(page.get_by_role("dialog", name="Studio commands")).to_be_visible()
    page.keyboard.press("Escape")
    expect(prompt).to_be_focused()
    expect(prompt).to_have_value("Keep this draft")
    dialog = palette(page, "unfindable-command")
    expect(dialog.get_by_text("No matching commands.")).to_be_visible()
    dialog.get_by_role("combobox").fill("onerror")
    expect(dialog.get_by_role("option", name=UNTRUSTED)).to_be_visible()
    assert not page.evaluate("Boolean(window.uiInjected)")
    page.keyboard.press("Escape")
    expect(page.get_by_role("button", name="Search Studio commands")).to_be_focused()
    dialog = palette(page, "Cable bracket")
    # Discard confirmation must run before changing a part.
    page.once("dialog", lambda dialog: dialog.dismiss())
    dialog.get_by_role("option", name="Cable bracket").click()
    expect(prompt).to_have_value("Keep this draft")
    assert not any(path == "/api/projects/test-part" for _, path, _ in fixture.requests)
    dialog = palette(page)
    page.wait_for_timeout(250)
    page.screenshot(path=str(shots / "commands-desktop.png"))
    page.keyboard.press("Escape")
    assert not fixture.errors, fixture.errors
    context.close()
    print("PASS desktop model picker, shortcut/focus, filtering, literal text, discard confirmation")


def test_project(browser, base, shots):
    context, page, fixture = open_studio(browser, base, project=True)
    expect(page.locator('[aria-current="step"]')).to_contain_text("Version 2")
    dialog = palette(page, "Version 1")
    dialog.get_by_role("option", name=re.compile("Version 1")).click()
    expect(page.locator('[aria-current="step"]')).to_contain_text("Version 1")
    assert any(path == "/api/projects/test-part/revisions/1" for _, path, _ in fixture.requests)
    # The rail selects a revision before its mesh finishes downloading. Wait
    # for the new canvas/model so a later load cannot undo the test's zoom.
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="Export", exact=True)).to_be_enabled(timeout=30000)
    expect(page.get_by_text("Features", exact=True)).to_be_visible(timeout=30000)
    canvas = page.locator("canvas").first
    expect(canvas).to_be_visible()
    page.wait_for_timeout(1000)  # let the model's reveal transition finish
    box = canvas.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(500)
    page.mouse.move(10, 10)  # exclude face-hover highlights from the comparison
    before = canvas.screenshot()
    count = len(fixture.requests)
    palette(page, "Fit model").get_by_role("option", name="Fit model in view").click()
    page.wait_for_timeout(500)
    assert before != canvas.screenshot(), "Fit view should move the camera"
    assert len(fixture.requests) == count, "Fit view must not regenerate a mesh"
    # Model changes in the composer are the exact allowlisted id in a run.
    page.get_by_role("button", name="Generation model: Claude Sonnet 5.5").click()
    page.get_by_role("radio", name=re.compile("Opus")).click()
    page.get_by_placeholder("Describe your next change…").fill("Make the bracket taller")
    page.get_by_role("button", name="Send request", exact=True).click()
    progress = page.get_by_role("region", name="Build progress")
    expect(progress).to_be_visible()
    expect(progress.get_by_text("Plan ready")).to_be_visible(timeout=10000)
    assert any(body and body.get("modelId") == OPUS for _, path, body in fixture.requests if path == "/api/cad/runs")
    expect(page.get_by_role("button", name="Generation model: Claude Opus 5.5")).to_be_disabled()
    dialog = palette(page)
    expect(dialog.get_by_role("option", name="New part", exact=True)).to_have_attribute("aria-disabled", "true")
    expect(dialog.get_by_role("option", name="Export STEP", exact=True)).to_have_attribute("aria-disabled", "true")
    page.keyboard.press("Escape")
    fixture.phase = 1
    expect(progress.get_by_text("Repairing the bracket")).to_be_visible(timeout=10000)
    expect(progress.get_by_text(UNTRUSTED, exact=True)).to_be_visible()
    assert not page.evaluate("Boolean(window.uiInjected)")
    expect(progress.get_by_text("1.3 s", exact=True)).to_be_visible()
    expect(progress.get_by_role("listitem")).to_have_count(3)
    collapse = progress.get_by_role("button")
    collapse.click()
    expect(collapse).to_have_attribute("aria-expanded", "false")
    collapse.click()
    expect(progress.get_by_role("list")).to_be_visible()
    page.get_by_role("button", name="Toggle color theme").click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(shots / "progress-midnight.png"))
    # Real backend completion events omit the numbered repair attempt.
    fixture.phase = 2
    expect(progress.get_by_text("Repair applied")).to_be_visible(timeout=10000)
    expect(progress.get_by_text("2.3 s", exact=True)).to_be_visible()
    expect(progress.get_by_role("listitem")).to_have_count(4)
    fixture.run_failed = True
    expect(page.get_by_text("Local fixture: the part could not be generated", exact=True)).to_be_visible(timeout=10000)
    expect(progress).to_have_count(0)
    assert not fixture.errors, fixture.errors
    context.close()
    print("PASS saved revision switching, camera fit, allowlisted request, real progress/retry/error and busy gates")


def test_mobile(browser, base, shots):
    context, page, fixture = open_studio(browser, base, mobile=True, project=True, reduced=True)
    trigger = page.get_by_role("button", name="Export part", exact=True)
    trigger.click()
    drawer = page.get_by_role("dialog", name="Export your part")
    expect(drawer).to_be_visible()
    expect(drawer.get_by_role("button", name=re.compile("STEP"))).to_be_visible()
    expect(drawer.get_by_role("button", name=re.compile("BREP"))).to_be_visible()
    expect(drawer.get_by_role("button", name=re.compile("STL"))).to_be_visible()
    assert drawer.evaluate("el => getComputedStyle(el).animationName") == "none"
    assert drawer.evaluate("el => getComputedStyle(el).transitionDuration") == "0s"
    page.screenshot(path=str(shots / "export-mobile.png"))
    drawer.get_by_role("button", name="Cancel").click()
    expect(drawer).to_have_count(0)
    expect(trigger).to_be_focused()
    trigger.click()
    page.keyboard.press("Escape")
    expect(drawer).to_have_count(0)
    trigger.click()
    expect(drawer).to_be_visible()
    # Vaul ignores drags for 500 ms after opening, even with reduced motion.
    page.wait_for_timeout(550)
    bounds = drawer.bounding_box()
    page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 22)
    page.mouse.down()
    page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 350, steps=12)
    page.mouse.up()
    expect(drawer).to_have_count(0)
    trigger.click()
    with page.expect_download() as download:
        drawer.get_by_role("button", name=re.compile("STL")).click()
    assert download.value.suggested_filename == "model.stl"
    exports = [body for _, path, body in fixture.requests if path == "/api/cad/export-model"]
    assert exports == [{"code": CODE, "format": "stl"}], exports
    fixture.export_status = 402
    trigger.click()
    drawer.get_by_role("button", name=re.compile("STEP")).click()
    expect(page.get_by_role("dialog", name="Take it into the real world.")).to_be_visible()
    assert not any("checkout" in path for _, path, _ in fixture.requests)
    page.get_by_role("button", name="Close", exact=True).click()
    for width in (320, 390, 768):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"overflow at {width}"
        for name in ("Search Studio commands", "Toggle color theme"):
            bounds = page.get_by_role("button", name=name).bounding_box()
            assert 0 <= bounds["x"] and bounds["x"] + bounds["width"] <= width
    assert not fixture.errors, fixture.errors
    context.close()
    print("PASS mobile drawer, reduced motion, focus/dismissal, export format and backend 402 paywall")


def test_locked(browser, base):
    context, page, fixture = open_studio(browser, base, mobile=True, active=False)
    page.get_by_role("button", name="Export part", exact=True).click()
    page.get_by_role("dialog", name="Export your part").get_by_role("button", name=re.compile("STL")).click()
    expect(page.get_by_role("dialog", name="Take it into the real world.")).to_be_visible()
    assert not any(path == "/api/cad/export-model" or "checkout" in path for _, path, _ in fixture.requests)
    page.set_viewport_size({"width": 320, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not fixture.errors, fixture.errors
    context.close()
    print("PASS unsubscribed users retain the paywall without paid requests")


def test_local_agents(browser, base):
    context, page, fixture = open_studio(browser, base, local_agents=[
        {"id": "local/claude", "label": "Claude Code", "installed": False},
        {"id": "local/codex", "label": "Codex", "installed": True},
    ])
    trigger = page.get_by_role("button", name="Generation model: Codex · local")
    expect(trigger).to_be_visible()
    trigger.click()
    group = page.get_by_role("radiogroup", name="Generation model")
    expect(group.get_by_role("radio")).to_have_count(4)
    expect(group.get_by_role("radio", name=re.compile("Claude Code"))).to_be_disabled()
    expect(group.get_by_role("radio", name=re.compile("Codex"))).to_be_checked()
    group.get_by_role("radio", name=re.compile("Sonnet")).click()
    palette(page, "Open advanced editor").get_by_role("option", name="Open advanced editor").click()
    page.get_by_role("button", name="Generation model: Claude Sonnet 5.5").last.click()
    expect(page.get_by_role("radio", name=re.compile("Claude Code"))).to_be_disabled()
    page.get_by_role("radio", name=re.compile("Codex")).click()
    page.get_by_role("button", name="Close advanced editor").click()
    expect(trigger).to_be_visible()
    page.get_by_text("References & copies", exact=True).click()
    expect(page.get_by_role("button", name="Import STL", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Attach reference pictures")).to_be_visible()
    page.get_by_placeholder("Describe the part you want to make…").fill("Make a local bracket")
    page.get_by_role("button", name="Send request", exact=True).click()
    expect(page.get_by_role("region", name="Build progress")).to_be_visible()
    assert any(body and body.get("modelId") == "local/codex" for _, path, body in fixture.requests if path == "/api/cad/runs")
    assert not fixture.errors, fixture.errors
    context.close()
    print("PASS local-agent selection, unavailable agents, editor synchronization and reference controls")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3100")
    parser.add_argument("--channel", default=None, help="Use chrome for an installed Google Chrome, or omit for Playwright Chromium")
    parser.add_argument("--screenshots", default="/tmp/nfinit-ui-checks")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        raise SystemExit("Only a local HTTP development server is permitted.")
    shots = Path(args.screenshots)
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel=args.channel,
            # CI has no GPU. This is a browser-test setting, never app code.
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        try:
            test_desktop(browser, args.base_url, shots)
            test_project(browser, args.base_url, shots)
            test_mobile(browser, args.base_url, shots)
            test_locked(browser, args.base_url)
            test_local_agents(browser, args.base_url)
        finally:
            browser.close()
    print("All Studio control checks passed. All API requests were local fixtures.")


if __name__ == "__main__":
    main()
