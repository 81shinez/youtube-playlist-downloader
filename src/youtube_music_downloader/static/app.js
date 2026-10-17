(() => {
  "use strict";

  const API_ROOT = "/api/jobs";
  const POLL_INTERVAL_MS = 1500;
  const CURRENT_JOB_STORAGE_KEY = "ymd.currentJobId";
  const JOB_LATEST_PATH = "/latest";
  const TRACK_RETRY_PATH = "/retry";
  const TRACK_CANCEL_PATH = "/cancel";
  const JOB_PAUSE_PATH = "/pause";
  const JOB_RESUME_PATH = "/resume";
  const JOB_CANCEL_PATH = "/cancel";
  const JOB_COOKIE_SOURCE_PATH = "/cookie-source";
  const ACTIVE_JOB_STATUSES = new Set(["queued", "analyzing", "running"]);
  const ACTIVE_TRACK_STATUSES = new Set(["queued", "analyzing", "downloading", "converting"]);
  const RETRYABLE_TRACK_STATUSES = new Set(["failed", "completed"]);
  const TERMINAL_JOB_STATUSES = new Set(["completed", "completed_with_errors", "failed", "canceled"]);
  const STATUS_LABELS = {
    queued: "대기",
    analyzing: "분석 중",
    running: "진행 중",
    paused: "일시 정지",
    downloading: "다운로드 중",
    converting: "변환 중",
    completed: "완료",
    completed_with_errors: "오류 포함 완료",
    failed: "실패",
    canceled: "취소",
  };

  let currentJobId = null;
  let pollTimer = null;
  let lastJob = null;
  let tokenPromise = null;

  const elements = {
    form: document.getElementById("job-form"),
    playlistUrl: document.getElementById("playlist-url"),
    outputDir: document.getElementById("output-dir"),
    cookieSource: document.getElementById("cookie-source"),
    concurrency: document.getElementById("concurrency"),
    startButton: document.getElementById("start-button"),
    formMessage: document.getElementById("form-message"),
    jobStatus: document.getElementById("job-status"),
    summaryTotal: document.getElementById("summary-total"),
    summaryCompleted: document.getElementById("summary-completed"),
    summaryFailed: document.getElementById("summary-failed"),
    summaryCanceled: document.getElementById("summary-canceled"),
    pauseJob: document.getElementById("pause-job"),
    resumeJob: document.getElementById("resume-job"),
    cancelJob: document.getElementById("cancel-job"),
    retryFailed: document.getElementById("retry-failed"),
    openOutputFolder: document.getElementById("open-output-folder"),
    lastUpdated: document.getElementById("last-updated"),
    tracksCount: document.getElementById("tracks-count"),
    tracksBody: document.getElementById("tracks-body"),
  };

  if (!elements.form) {
    return;
  }

  elements.form.addEventListener("submit", createJob);
  elements.pauseJob.addEventListener("click", pauseJob);
  elements.resumeJob.addEventListener("click", resumeJob);
  elements.cancelJob.addEventListener("click", cancelJob);
  elements.cookieSource.addEventListener("change", updateJobCookieSource);
  elements.retryFailed.addEventListener("click", retryFailedTracks);
  elements.openOutputFolder.addEventListener("click", openOutputFolder);
  elements.tracksBody.addEventListener("click", handleTrackAction);
  restoreCurrentJob();

  async function sessionToken() {
    if (!tokenPromise) {
      tokenPromise = (async () => {
        const response = await fetch("/session-token", {
          headers: { "X-YMD-Bootstrap": "1" },
          mode: "same-origin",
          cache: "no-store",
          redirect: "error",
        });
        const data = await readJson(response);
        if (!response.ok || typeof data.token !== "string" || !data.token) {
          throw new Error("로컬 앱 인증에 실패했습니다. 화면을 새로고침해 주세요.");
        }
        return data.token;
      })().catch((error) => {
        tokenPromise = null;
        throw error;
      });
    }
    return tokenPromise;
  }

  async function apiRequest(path, options = {}) {
    const headers = new Headers(options.headers);
    const requestOptions = { ...options, headers, mode: "same-origin", cache: "no-store", redirect: "error" };
    if (!["GET", "HEAD", "OPTIONS"].includes((options.method || "GET").toUpperCase())) {
      headers.set("Content-Type", "application/json");
      requestOptions.body = options.body == null ? "{}" : options.body;
    }
    const token = await sessionToken();
    headers.set("X-YMD-Token", token);
    let response = await fetch(path, requestOptions);
    if (response.status === 401) {
      // Retry only a request the server rejected before running its action.
      if (await sessionToken() === token) {
        tokenPromise = null;
      }
      headers.set("X-YMD-Token", await sessionToken());
      response = await fetch(path, requestOptions);
    }
    return response;
  }

  async function createJob(event) {
    event.preventDefault();
    setFormBusy(true);
    setMessage("작업을 생성하는 중입니다...", "info");

    try {
      const payload = {
        playlist_url: elements.playlistUrl.value.trim(),
        output_dir: elements.outputDir.value.trim(),
        output_mode: selectedOutputMode(),
        cookie_source: selectedCookieSource(),
        concurrency: Number(elements.concurrency.value),
      };

      const response = await apiRequest(API_ROOT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await readJson(response);

      if (!response.ok) {
        throw new Error(errorDetail(data, "작업 생성에 실패했습니다."));
      }

      currentJobId = data.job_id;
      saveCurrentJobId(data.job_id);
      setMessage("작업이 생성되었습니다. 진행 상황을 불러옵니다.", "success");
      const job = await pollJob();
      if (job && isJobActive(job)) {
        startPolling();
      }
    } catch (error) {
      setMessage(error.message, "error");
    } finally {
      setFormBusy(false);
    }
  }

  async function pollJob() {
    if (!currentJobId) {
      return null;
    }

    try {
      const response = await apiRequest(`${API_ROOT}/${encodeURIComponent(currentJobId)}`);
      const data = await readJson(response);

      if (!response.ok) {
        if (response.status === 404) {
          clearCurrentJobId();
          currentJobId = null;
          lastJob = null;
        }
        throw new Error(errorDetail(data, "작업 정보를 불러오지 못했습니다."));
      }

      lastJob = data;
      renderJob(data);

      if (!isJobActive(data)) {
        stopPolling();
      }

      return data;
    } catch (error) {
      setMessage(error.message, "error");
      if (!(lastJob && isJobActive(lastJob))) {
        stopPolling();
      }
      return null;
    }
  }

  function renderJob(job) {
    if (!currentJobId && job.id) {
      currentJobId = job.id;
      saveCurrentJobId(job.id);
    }

    const summary = job.summary || {};
    const tracks = Array.isArray(job.tracks) ? job.tracks : [];
    const failedCount = Number(summary.failed || 0);
    const hasCurrentJob = Boolean(currentJobId);

    elements.jobStatus.textContent = `작업 상태: ${statusLabel(job.status)}`;
    elements.summaryTotal.textContent = String(summary.total || tracks.length || 0);
    elements.summaryCompleted.textContent = String(summary.completed || 0);
    elements.summaryFailed.textContent = String(failedCount);
    elements.summaryCanceled.textContent = String(summary.canceled || 0);
    elements.pauseJob.disabled = !hasCurrentJob || job.status === "paused" || isJobTerminal(job);
    elements.resumeJob.disabled = !hasCurrentJob || job.status !== "paused";
    elements.cancelJob.disabled = !hasCurrentJob || isJobTerminal(job);
    elements.retryFailed.disabled = !hasCurrentJob || failedCount === 0;
    elements.openOutputFolder.disabled = !hasCurrentJob;
    elements.lastUpdated.textContent = `마지막 갱신: ${new Date().toLocaleTimeString("ko-KR")}`;
    elements.tracksCount.textContent = `${tracks.length}개 트랙`;
    if (job.error_message) {
      setMessage(job.error_message, "error");
    }

    renderTracks(tracks);
  }

  function renderTracks(tracks) {
    elements.tracksBody.replaceChildren();

    if (tracks.length === 0) {
      const row = document.createElement("tr");
      row.className = "empty-row";
      const cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "플레이리스트를 분석하면 트랙 목록이 표시됩니다.";
      row.append(cell);
      elements.tracksBody.append(row);
      return;
    }

    for (const track of tracks) {
      elements.tracksBody.append(renderTrackRow(track));
    }
  }

  function renderTrackRow(track) {
    const row = document.createElement("tr");
    const progress = boundedProgress(track.progress);

    row.append(
      trackInfoCell(track),
      statusCell(track.status),
      progressCell(progress),
      bitrateCell(track),
      errorCell(track.error_message),
      actionCell(track),
    );

    return row;
  }

  function trackInfoCell(track) {
    const cell = document.createElement("td");
    const title = document.createElement("div");
    const meta = document.createElement("div");

    title.className = "track-title";
    title.textContent = track.title || "제목 없음";
    meta.className = "track-meta";
    meta.textContent = track.artist ? `${track.artist} · ${track.source_url || ""}` : track.source_url || "소스 URL 없음";

    cell.append(title, meta);
    return cell;
  }

  function statusCell(status) {
    const cell = document.createElement("td");
    const badge = document.createElement("span");

    badge.className = `status-badge ${statusClass(status)}`;
    badge.textContent = statusLabel(status);
    cell.append(badge);
    return cell;
  }

  function progressCell(progress) {
    const cell = document.createElement("td");
    const wrap = document.createElement("div");
    const bar = document.createElement("div");
    const fill = document.createElement("div");
    const label = document.createElement("span");

    wrap.className = "progress-wrap";
    bar.className = "progress-bar";
    fill.className = "progress-fill";
    fill.style.width = `${progress}%`;
    label.textContent = `${progress}%`;

    bar.append(fill);
    wrap.append(bar, label);
    cell.append(wrap);
    return cell;
  }

  function bitrateCell(track) {
    const cell = document.createElement("td");
    const output = Number(track.target_bitrate_kbps);

    cell.textContent = Number.isFinite(output) && output > 0 ? `${output}kbps` : "-";
    return cell;
  }

  function errorCell(message) {
    const cell = document.createElement("td");
    const text = document.createElement("div");

    text.className = message ? "error-text" : "";
    text.textContent = message || "-";
    cell.append(text);
    return cell;
  }

  function actionCell(track) {
    const cell = document.createElement("td");
    const actions = document.createElement("div");
    const status = String(track.status || "");

    actions.className = "actions";

    if (RETRYABLE_TRACK_STATUSES.has(status)) {
      actions.append(trackButton(track.id, "retry", status === "completed" ? "다시 받기" : "재시도"));
    }

    if (ACTIVE_TRACK_STATUSES.has(status)) {
      actions.append(trackButton(track.id, "cancel", status === "queued" ? "제거" : "취소", true));
    }

    if (!actions.childElementCount) {
      const empty = document.createElement("span");
      empty.className = "track-meta";
      empty.textContent = "-";
      actions.append(empty);
    }

    cell.append(actions);
    return cell;
  }

  function trackButton(trackId, action, label, danger = false) {
    const button = document.createElement("button");

    button.className = danger ? "track-action danger" : "track-action";
    button.type = "button";
    button.dataset.action = action;
    button.dataset.trackId = trackId;
    button.textContent = label;
    return button;
  }

  async function handleTrackAction(event) {
    const button = event.target.closest("button[data-action][data-track-id]");

    if (!button || !currentJobId) {
      return;
    }

    const { action, trackId } = button.dataset;
    if (action === "retry") {
      await postTrackAction(trackId, TRACK_RETRY_PATH, "트랙 재시도", cookiePayload());
    } else if (action === "cancel") {
      await postTrackAction(trackId, TRACK_CANCEL_PATH, "트랙 취소");
    }
  }

  async function pauseJob() {
    await postJobAction(JOB_PAUSE_PATH, "작업 일시 정지");
  }

  async function resumeJob() {
    await postJobAction(JOB_RESUME_PATH, "작업 다시 시작");
  }

  async function cancelJob() {
    await postJobAction(JOB_CANCEL_PATH, "작업 취소");
  }

  async function updateJobCookieSource() {
    if (!currentJobId) {
      return;
    }

    await postJobAction(JOB_COOKIE_SOURCE_PATH, "브라우저 쿠키 변경", cookiePayload());
  }

  async function retryFailedTracks() {
    await postJobAction("/retry-failed", "실패 항목 전체 재시도", cookiePayload());
  }

  async function openOutputFolder() {
    await postJobAction("/open-output-folder", "출력 폴더 열기");
  }

  async function restoreCurrentJob() {
    const savedJobId = loadCurrentJobId();
    if (savedJobId) {
      currentJobId = savedJobId;
      const job = await pollJob();
      if (job) {
        if (isJobActive(job)) {
          startPolling();
        }
        return;
      }
    }

    await restoreLatestJob();
  }

  async function restoreLatestJob() {
    try {
      const response = await apiRequest(`${API_ROOT}${JOB_LATEST_PATH}`);
      const data = await readJson(response);

      if (response.status === 404) {
        return null;
      }

      if (!response.ok) {
        throw new Error(errorDetail(data, "최근 작업을 불러오지 못했습니다."));
      }

      currentJobId = data.id;
      saveCurrentJobId(data.id);
      lastJob = data;
      renderJob(data);

      if (isJobActive(data)) {
        startPolling();
      }
      return data;
    } catch (error) {
      setMessage(error.message, "error");
      return;
    }
  }

  async function postTrackAction(trackId, path, label, payload = null) {
    const encodedTrackId = encodeURIComponent(trackId);
    await postJobAction(`/tracks/${encodedTrackId}${path}`, label, payload);
  }

  async function postJobAction(path, label, payload = null) {
    const jobId = currentJobId || (lastJob && lastJob.id);
    if (!jobId) {
      setMessage("먼저 작업을 시작하세요.", "error");
      return;
    }
    if (!currentJobId) {
      currentJobId = jobId;
      saveCurrentJobId(jobId);
    }

    setMessage(`${label} 요청 중입니다...`, "info");

    try {
      const requestOptions = { method: "POST" };
      if (payload) {
        requestOptions.headers = { "Content-Type": "application/json" };
        requestOptions.body = JSON.stringify(payload);
      }

      const response = await apiRequest(`${API_ROOT}/${encodeURIComponent(jobId)}${path}`, requestOptions);
      const data = await readJson(response);

      if (!response.ok) {
        throw new Error(errorDetail(data, `${label} 요청에 실패했습니다.`));
      }

      setMessage(`${label} 요청을 보냈습니다.`, "success");
      await pollJob();
      if (lastJob && isJobActive(lastJob)) {
        startPolling();
      }
    } catch (error) {
      setMessage(error.message, "error");
    }
  }

  function selectedOutputMode() {
    const checked = document.querySelector('input[name="output_mode"]:checked');
    return checked ? checked.value : "192";
  }

  function selectedCookieSource() {
    return elements.cookieSource ? elements.cookieSource.value : "";
  }

  function cookiePayload() {
    return { cookie_source: selectedCookieSource() };
  }

  function saveCurrentJobId(jobId) {
    try {
      window.localStorage.setItem(CURRENT_JOB_STORAGE_KEY, jobId);
    } catch (_error) {
      // Private browsing or locked-down browsers can reject localStorage.
    }
  }

  function loadCurrentJobId() {
    try {
      return window.localStorage.getItem(CURRENT_JOB_STORAGE_KEY) || "";
    } catch (_error) {
      return "";
    }
  }

  function clearCurrentJobId() {
    try {
      window.localStorage.removeItem(CURRENT_JOB_STORAGE_KEY);
    } catch (_error) {
      // Nothing to clear when storage is unavailable.
    }
  }

  function setFormBusy(isBusy) {
    elements.startButton.disabled = isBusy;
    elements.startButton.textContent = isBusy ? "시작 중..." : "다운로드 시작";
  }

  function setMessage(message, type) {
    elements.formMessage.textContent = message;
    elements.formMessage.className = `message ${type === "error" ? "is-error" : ""} ${type === "success" ? "is-success" : ""}`;
  }

  function startPolling() {
    if (pollTimer || !currentJobId) {
      return;
    }

    pollTimer = window.setInterval(pollJob, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (!pollTimer) {
      return;
    }

    window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function isJobActive(job) {
    const tracks = Array.isArray(job.tracks) ? job.tracks : [];
    return ACTIVE_JOB_STATUSES.has(job.status) || tracks.some((track) => ACTIVE_TRACK_STATUSES.has(track.status));
  }

  function isJobTerminal(job) {
    return TERMINAL_JOB_STATUSES.has(String(job.status || ""));
  }

  function boundedProgress(value) {
    const progress = Number(value);
    if (!Number.isFinite(progress)) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round(progress)));
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || "알 수 없음";
  }

  function statusClass(status) {
    if (status === "completed") {
      return "is-completed";
    }
    if (status === "failed") {
      return "is-failed";
    }
    if (status === "canceled") {
      return "is-canceled";
    }
    if (status === "paused") {
      return "is-paused";
    }
    if (ACTIVE_TRACK_STATUSES.has(status) || ACTIVE_JOB_STATUSES.has(status)) {
      return "is-running";
    }
    return "";
  }

  async function readJson(response) {
    const text = await response.text();
    if (!text.trim()) {
      return {};
    }

    try {
      return JSON.parse(text);
    } catch (_error) {
      return {
        detail: text.trim() || response.statusText || "요청 처리 중 오류가 발생했습니다.",
      };
    }
  }

  function errorDetail(data, fallback) {
    if (data && typeof data.detail === "string") {
      return data.detail;
    }
    return fallback;
  }
})();
