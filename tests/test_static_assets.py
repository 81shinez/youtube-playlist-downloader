from pathlib import Path
import shutil
import subprocess

import pytest


STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "youtube_music_downloader" / "static"


def read_static_file(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def function_body(script: str, signature: str) -> str:
    start = script.index(signature)
    body_start = script.index("{", start)
    depth = 0
    for index in range(body_start, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[body_start + 1 : index]
    raise AssertionError(f"Could not find function body for {signature}")


def test_index_contains_required_dashboard_controls():
    html = read_static_file("index.html")

    assert 'id="playlist-url"' in html
    assert 'id="output-dir"' in html
    assert 'value="192"' in html
    assert 'value="max"' in html
    assert 'id="cookie-source"' in html
    assert '<option value="auto" selected>자동</option>' in html
    assert '<option value="chrome">Chrome</option>' in html
    assert 'id="retry-failed"' in html
    assert 'id="pause-job"' in html
    assert 'id="resume-job"' in html
    assert 'id="cancel-job"' in html
    assert 'id="tracks-body"' in html


def test_index_contains_concurrency_and_start_controls():
    html = read_static_file("index.html")

    assert 'id="concurrency"' in html
    assert 'min="1"' in html
    assert 'max="4"' in html
    assert 'id="start-button"' in html
    assert ">다운로드 시작</button>" in html


def test_index_does_not_offer_fixed_320kbps_output_mode():
    html = read_static_file("index.html")

    assert 'value="320"' not in html
    assert "320kbps 고정" not in html


def test_javascript_contains_job_and_track_actions():
    script = read_static_file("app.js")

    assert "/retry-failed" in script
    assert "/retry" in script
    assert "/cancel" in script
    assert "/pause" in script
    assert "/resume" in script
    assert "/cookie-source" in script
    assert "updateJobCookieSource" in script
    assert "cookie_source" in script
    assert "renderTracks" in script
    assert "createJob" in script
    assert "/open-output-folder" in script


def test_javascript_surfaces_job_level_error_messages():
    script = read_static_file("app.js")
    render_body = function_body(script, "function renderJob")

    assert "job.error_message" in render_body
    assert 'setMessage(job.error_message, "error")' in render_body


def test_javascript_constructs_per_track_retry_and_cancel_endpoints_safely():
    script = read_static_file("app.js")

    assert 'const TRACK_RETRY_PATH = "/retry"' in script
    assert 'const TRACK_CANCEL_PATH = "/cancel"' in script
    assert "`/tracks/${encodedTrackId}${path}`" in script
    assert "encodeURIComponent(trackId)" in script


def test_retry_actions_send_selected_cookie_source():
    script = read_static_file("app.js")

    assert "cookie_source: selectedCookieSource()" in script
    assert "postTrackAction(trackId, TRACK_RETRY_PATH" in script
    assert 'postJobAction("/retry-failed"' in script


def test_create_job_does_not_stop_existing_polling_before_new_job_exists():
    script = read_static_file("app.js")
    body = function_body(script, "async function createJob")
    before_new_job = body.split("currentJobId = data.job_id", 1)[0]

    assert "currentJobId = data.job_id" in body
    assert "stopPolling()" not in before_new_job


def test_javascript_persists_and_restores_current_job_id():
    script = read_static_file("app.js")
    create_body = function_body(script, "async function createJob")
    poll_body = function_body(script, "async function pollJob")

    assert "CURRENT_JOB_STORAGE_KEY" in script
    assert "restoreCurrentJob()" in script
    assert "saveCurrentJobId(data.job_id)" in create_body
    assert "loadCurrentJobId()" in script
    assert "window.localStorage" in script
    assert "clearCurrentJobId()" in poll_body


def test_render_job_recovers_missing_current_job_id_from_payload():
    script = read_static_file("app.js")
    render_body = function_body(script, "function renderJob")

    assert "if (!currentJobId && job.id)" in render_body
    assert "currentJobId = job.id" in render_body
    assert "saveCurrentJobId(job.id)" in render_body
    assert "const hasCurrentJob = Boolean(currentJobId)" in render_body
    assert "elements.pauseJob.disabled = !hasCurrentJob" in render_body
    assert "elements.cancelJob.disabled = !hasCurrentJob" in render_body


def test_job_actions_fall_back_to_last_rendered_job_id():
    script = read_static_file("app.js")
    body = function_body(script, "async function postJobAction")

    assert "const jobId = currentJobId || (lastJob && lastJob.id)" in body
    assert "currentJobId = jobId" in body
    assert "saveCurrentJobId(jobId)" in body
    assert "encodeURIComponent(jobId)" in body


def test_javascript_restores_latest_job_when_no_saved_job_id():
    script = read_static_file("app.js")
    restore_body = function_body(script, "async function restoreCurrentJob")

    assert 'const JOB_LATEST_PATH = "/latest"' in script
    assert "restoreLatestJob()" in restore_body
    assert "async function restoreLatestJob" in script
    assert "saveCurrentJobId(data.id)" in script


def test_read_json_handles_non_json_error_bodies_without_throwing_syntax_error():
    script = read_static_file("app.js")
    body = function_body(script, "async function readJson")

    assert "JSON.parse(text)" in body
    assert "try {" in body
    assert "catch" in body
    assert "response.statusText" in body


def test_poll_job_keeps_polling_active_job_after_transient_response_errors():
    script = read_static_file("app.js")
    body = function_body(script, "async function pollJob")
    catch_body = body.split("} catch (error) {", 1)[1]

    assert "lastJob && isJobActive(lastJob)" in catch_body
    assert "stopPolling()" in catch_body


@pytest.mark.parametrize("scenario", ["normal", "bootstrap-failure", "expired-token", "persistent-401"])
def test_browser_requests_authenticate_poll_and_send_json_actions(scenario):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the browser request regression test")
    result = subprocess.run(
        [node, "-e", r'''
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const scenario = process.argv[2];
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: ({"playlist-url": "https://music.youtube.com/playlist?list=abc",
      "output-dir": "C:/Music", "concurrency": "2", "cookie-source": "auto"})[id] || "",
    listeners: {}, dataset: {}, append() {}, replaceChildren() {},
    addEventListener(event, handler) { this.listeners[event] = handler; },
  });
  return elements.get(id);
}
const requests = [];
const storage = new Map();
const timers = new Map();
let bootstraps = 0;
let expired = false;
let created = false;
let failPoll = false;
const response = (status, body) => ({status, ok: status >= 200 && status < 300,
  statusText: "Test response", text: async () => JSON.stringify(body)});
const job = {id: "job_test", status: "running", tracks: [], summary: {total: 0}};
const context = {
  document: {getElementById: element, querySelector: () => ({value: "192"}),
    createElement: () => element(Symbol())},
  window: {localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key)},
    setInterval: fn => { timers.set(1, fn); return 1; }, clearInterval: id => timers.delete(id)},
  Headers, URL, console,
  fetch: async (url, options = {}) => {
    const headers = new Headers(options.headers);
    requests.push({url, ...options, headers});
    assert.equal(options.mode, "same-origin");
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.equal(url.includes("?"), false, "token must not be in a URL");
    if (url === "/session-token") {
      bootstraps++;
      assert.equal(headers.get("X-YMD-Bootstrap"), "1");
      if (scenario === "bootstrap-failure" && bootstraps === 1) throw new Error("offline");
      return response(200, {token: `launch-secret-${bootstraps}`});
    }
    assert.ok(url.startsWith("/api/"));
    assert.equal(headers.get("X-YMD-Token"), `launch-secret-${bootstraps}`);
    if (scenario === "persistent-401") return response(401, {detail: "expired"});
    if (scenario === "expired-token" && !expired) {
      expired = true;
      return response(401, {detail: "expired"});
    }
    if (options.method === "POST") {
      assert.equal(headers.get("Content-Type"), "application/json");
      assert.equal(typeof JSON.parse(options.body), "object");
      if (url === "/api/jobs") {
        created = true;
        return response(200, {job_id: job.id, status: "queued"});
      }
      return response(200, job);
    }
    if (failPoll) { failPoll = false; return response(503, {detail: "temporary"}); }
    return created ? response(200, job) : response(404, {detail: "not found"});
  },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), context);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  for (let i = 0; i < 10; i++) await settle();
  if (scenario === "persistent-401") {
    assert.equal(bootstraps, 2, "authentication retries must be bounded");
    assert.equal(requests.filter(r => r.url.startsWith("/api/")).length, 2);
    return;
  }
  await element("job-form").listeners.submit({preventDefault() {}});
  assert.ok(created, "create must recover after bootstrap failure");
  assert.ok(timers.has(1), "active job must keep polling");
  failPoll = true;
  await timers.get(1)();
  assert.ok(timers.has(1), "transient errors must not stop active polling");
  await timers.get(1)();
  for (const id of ["pause-job", "resume-job", "retry-failed", "open-output-folder", "cancel-job"])
    await element(id).listeners.click();
  await element("cookie-source").listeners.change();
  for (const action of ["retry", "cancel"])
    await element("tracks-body").listeners.click({target: {closest: () => ({dataset: {action, trackId: "track_test"}})}});
  for (const action of ["pause", "resume", "retry-failed", "open-output-folder", "cancel",
    "cookie-source", "tracks/track_test/retry", "tracks/track_test/cancel"])
    assert.ok(requests.some(r => r.url === `/api/jobs/job_test/${action}` && r.method === "POST"), action);
  assert.equal(bootstraps, scenario === "normal" ? 1 : 2);
  assert.ok([...storage.values()].every(value => !value.includes("launch-secret")));
  assert.equal(element("form-message").className.includes("is-error"), false);
})().catch(error => { console.error(error); process.exitCode = 1; });
''', str(STATIC_DIR / "app.js"), scenario],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
