/** EF-02 Dashboard SPA controller */
window.EF02App = (function () {
  const STORAGE_KEY = "ef02_last_job_id";
  let jobId = localStorage.getItem(STORAGE_KEY);
  let jobName = null;
  let pipeline = null;
  let eventSource = null;
  let classifyStartTime = null;
  let classifyModel = "gpt-4o-mini";
  let classifyLogEntries = [];
  let classifyTimerId = null;
  let sessionModalResolve = null;

  const pages = ["home", "data", "classify", "analysis"];

  function qs(sel) {
    return document.querySelector(sel);
  }

  function showPage(name) {
    pages.forEach((p) => {
      const page = document.getElementById(`page-${p}`);
      const nav = document.querySelector(`[data-page="${p}"]`);
      if (page) page.classList.toggle("active", p === name);
      if (nav) nav.classList.toggle("active", p === name);
    });
    if (name === "analysis" && jobId && pipeline?.analysis.ready) {
      window.EF02Analysis.render(jobId).catch(console.error);
    }
  }

  function formatNum(n) {
    return Number(n).toLocaleString();
  }

  function formatElapsed(ms) {
    const sec = Math.floor(ms / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  async function parseApiError(res, fallback) {
    try {
      const data = await res.json();
      return data.detail || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return "—";
    }
  }

  function openSessionModal({ title, hint, confirmLabel, defaultValue = "" }) {
    return new Promise((resolve) => {
      sessionModalResolve = resolve;
      qs("#sessionModalTitle").textContent = title;
      qs("#sessionModalHint").textContent = hint;
      qs("#btnSessionConfirm").textContent = confirmLabel;
      const input = qs("#sessionNameInput");
      if (input) {
        input.value = defaultValue;
        setTimeout(() => input.focus(), 50);
      }
      qs("#sessionModal").classList.add("open");
    });
  }

  function closeSessionModal(result) {
    qs("#sessionModal")?.classList.remove("open");
    if (sessionModalResolve) {
      sessionModalResolve(result);
      sessionModalResolve = null;
    }
  }

  async function createNamedJob(name) {
    const fd = new FormData();
    fd.append("name", name);
    const res = await fetch("/api/jobs", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await parseApiError(res, "Failed to create session"));
    const data = await res.json();
    jobId = data.job_id;
    jobName = data.name || name;
    localStorage.setItem(STORAGE_KEY, jobId);
    updateJobBadge();
    await loadRecentRuns();
    return jobId;
  }

  async function ensureJob() {
    if (!jobId) return null;
    const res = await fetch(`/api/jobs/${jobId}/pipeline-state`);
    if (res.ok) return jobId;
    if (res.status === 404) {
      jobId = null;
      jobName = null;
      localStorage.removeItem(STORAGE_KEY);
      updateJobBadge();
    }
    return null;
  }

  async function requireJob() {
    const existing = await ensureJob();
    if (existing) return existing;
    const name = await openSessionModal({
      title: "Name your analysis",
      hint: "Create a session before uploading data.",
      confirmLabel: "Create & continue",
    });
    if (!name?.trim()) return null;
    return createNamedJob(name.trim());
  }

  function updateJobBadge() {
    const el = qs("#jobBadge");
    if (!el) return;
    if (!jobId) {
      el.textContent = "No session";
      return;
    }
    el.textContent = jobName || `Session ${jobId.slice(0, 8)}`;
    el.title = jobId;
  }

  async function refreshPipeline() {
    if (!jobId) return;
    const res = await fetch(`/api/jobs/${jobId}/pipeline-state`);
    if (!res.ok) return;
    pipeline = await res.json();
    const statusRes = await fetch(`/api/jobs/${jobId}/status`);
    if (statusRes.ok) {
      const s = await statusRes.json();
      jobName = s.name || jobName;
      updateJobBadge();
    }
    applyNavLocks();
    updateDataZones();
    updatePhasePanels();
    updateNextButtons();
    updateAnalysisVisibility();
    if (pipeline.analysis.ready) {
      try {
        await window.EF02Analysis.render(jobId);
      } catch (_) {
        /* analysis page may not be visible yet */
      }
    }
  }

  function updateAnalysisVisibility() {
    const empty = qs("#analysisEmpty");
    const content = qs("#analysisContent");
    if (!empty || !content || !pipeline) return;
    if (pipeline.analysis.ready) {
      empty.style.display = "none";
      content.style.display = "block";
    } else {
      empty.style.display = "block";
      content.style.display = "none";
    }
  }

  function applyNavLocks() {
    if (!pipeline) return;
    const map = {
      classify: pipeline.classify.ready,
      analysis: pipeline.consolidate.ready,
    };
    Object.entries(map).forEach(([page, ready]) => {
      const li = document.querySelector(`[data-page="${page}"]`);
      if (li) li.classList.toggle("nav-locked", !ready);
      const check = li?.querySelector(".check");
      if (check) {
        const done =
          (page === "classify" && pipeline.classify.done) ||
          (page === "analysis" && pipeline.analysis.done);
        check.style.display = done ? "inline" : "none";
      }
    });
    const dataOk =
      (pipeline.data.headlines || pipeline.data.labels) &&
      pipeline.data.cpi &&
      pipeline.data.fx;
    const dataNav = document.querySelector('[data-page="data"] .check');
    if (dataNav) dataNav.style.display = dataOk ? "inline" : "none";
  }

  function updateNextButtons() {
    if (!pipeline) return;
    const canClassify = !!pipeline.data.can_classify;
    const canSkip = !!pipeline.data.can_skip_to_analysis;
    const nextClassify = qs("#btnNextClassify");
    if (nextClassify) nextClassify.hidden = !canClassify;
    const nextAnalysisFromData = qs("#btnNextAnalysisFromData");
    if (nextAnalysisFromData) nextAnalysisFromData.hidden = !canSkip;
    const dataActions = qs("#dataNextActions");
    if (dataActions) dataActions.hidden = !(canClassify || canSkip);
    const nextAnalysis = qs("#btnNextAnalysis");
    if (nextAnalysis) nextAnalysis.hidden = !pipeline.classify.done;
  }

  function updateDataZones() {
    if (!pipeline) return;
    setZoneDone("headlines", pipeline.data.headlines);
    setZoneDone("labels", pipeline.data.labels);
    setZoneDone("cpi", pipeline.data.cpi);
    setZoneDone("fx", pipeline.data.fx);
    const preview = qs("#dataPreview");
    if (preview && (pipeline.data.ready || pipeline.data.can_skip_to_analysis)) {
      fetch(`/api/jobs/${jobId}/status`)
        .then((r) => r.json())
        .then((s) => {
          const p = s.preview || {};
          preview.hidden = false;
          if (pipeline.data.labels && !pipeline.data.headlines) {
            preview.textContent = p.overlap_range
              ? `Labelled path · Overlap: ${p.overlap_range.join(" → ")} · ${p.labelled_rows || p.headline_rows || "?"} rows`
              : "Labelled CSV + macro data ready — skip to Analysis";
          } else {
            preview.textContent = p.overlap_range
              ? `Overlap: ${p.overlap_range.join(" → ")} · ${p.headline_rows || "?"} headlines`
              : "Datasets uploaded";
          }
        });
    }
  }

  function setZoneDone(type, done) {
    const z = qs(`#zone-${type}`);
    if (z) z.classList.toggle("done", !!done);
  }

  function updatePhasePanels() {
    if (!pipeline) return;
    const classifyStatus = qs("#classifyStatus");
    if (classifyStatus) {
      if (pipeline.classify.done) {
        classifyStatus.textContent = "Labelled CSV ready — Classify is optional; continue to Analysis";
      } else if (pipeline.classify.can_run) {
        classifyStatus.textContent = "Ready to classify";
      } else {
        classifyStatus.textContent = "Upload headlines + CPI + FX, or skip with a labelled CSV on Data Import";
      }
    }
    const consolidateStatus = qs("#consolidateStatus");
    if (consolidateStatus) {
      consolidateStatus.textContent = pipeline.consolidate.done
        ? "Visualization data cached — charts below"
        : pipeline.consolidate.ready
          ? "Ready to consolidate"
          : "Need labelled CSV + CPI + USD/TZS first";
    }
    const runClassifyBtn = qs("#btnRunClassify");
    if (runClassifyBtn) {
      runClassifyBtn.disabled = !pipeline.classify.can_run;
      runClassifyBtn.title = pipeline.classify.done
        ? "Labels already present — upload a new labelled CSV to replace, or continue to Analysis"
        : "";
    }
  }

  function stopClassifyTimer() {
    if (classifyTimerId) {
      clearInterval(classifyTimerId);
      classifyTimerId = null;
    }
  }

  function startClassifyTimer() {
    stopClassifyTimer();
    classifyStartTime = Date.now();
    classifyLogEntries = [];
    const logEl = qs("#classifyLog");
    if (logEl) logEl.innerHTML = "";
    classifyTimerId = setInterval(() => {
      const stats = qs("#classifyStats");
      if (stats && classifyStartTime) {
        stats.textContent = `Model: ${classifyModel} · Elapsed: ${formatElapsed(Date.now() - classifyStartTime)}`;
      }
    }, 1000);
  }

  function pushClassifyLog(message) {
    if (!message) return;
    classifyLogEntries.unshift(message);
    classifyLogEntries = classifyLogEntries.slice(0, 5);
    const logEl = qs("#classifyLog");
    if (logEl) {
      logEl.innerHTML = classifyLogEntries.map((m) => `<li>${m}</li>`).join("");
    }
  }

  function connectEvents(onUpdate, onComplete) {
    if (eventSource) eventSource.close();
    if (!jobId) return;
    eventSource = new EventSource(`/api/jobs/${jobId}/events`);
    eventSource.onmessage = async (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "close") {
          eventSource.close();
          return;
        }
        onUpdate(data);
        if (data.status === "completed" || data.status === "failed") {
          stopClassifyTimer();
          await refreshPipeline();
          if (onComplete) await onComplete(data);
        }
      } catch (_) {
        /* ignore */
      }
    };
  }

  function updateProgress(data, prefix) {
    const msg = qs(`#${prefix}Message`);
    const fill = qs(`#${prefix}Fill`);
    const text = qs(`#${prefix}Text`);

    if (msg) msg.textContent = data.message || data.phase || data.status;

    let pct = 0;
    if (prefix === "classify" && data.headlines_total > 0 && data.headlines_done != null) {
      pct = Math.round((data.headlines_done / data.headlines_total) * 100);
      if (fill) fill.style.width = `${pct}%`;
      if (text) {
        const batchPart =
          data.total_batches > 0 ? ` · Batch ${data.batch}/${data.total_batches}` : "";
        text.textContent = `${formatNum(data.headlines_done)} of ${formatNum(data.headlines_total)} headlines (${pct}%)${batchPart}`;
      }
      const stats = qs("#classifyStats");
      if (stats && classifyStartTime) {
        stats.textContent = `Model: ${classifyModel} · Elapsed: ${formatElapsed(Date.now() - classifyStartTime)}`;
      }
      if (data.message) pushClassifyLog(data.message);
    } else if (data.total_batches > 0 && fill && text) {
      pct = Math.round((data.batch / data.total_batches) * 100);
      fill.style.width = `${pct}%`;
      text.textContent = `Batch ${data.batch}/${data.total_batches}`;
    } else if (fill && data.status === "running") {
      fill.style.width = "100%";
    }
  }

  async function uploadZone(type, files) {
    if (!(await requireJob())) return;
    if (type === "labels") {
      await uploadLabels(files[0]);
      return;
    }
    const fd = new FormData();
    if (type === "headlines") {
      for (const f of files) fd.append("files", f);
      const res = await fetch(`/api/jobs/${jobId}/data/headlines`, { method: "POST", body: fd });
      if (!res.ok) {
        const msg = await parseApiError(res, "Upload failed");
        throw new Error(
          res.status === 404
            ? "Upload API not found — restart the dashboard server from dashboard/."
            : msg
        );
      }
    } else {
      fd.append("file", files[0]);
      const res = await fetch(`/api/jobs/${jobId}/data/${type}`, { method: "POST", body: fd });
      if (!res.ok) {
        const msg = await parseApiError(res, "Upload failed");
        throw new Error(
          res.status === 404
            ? "Upload API not found — restart the dashboard server from dashboard/."
            : msg
        );
      }
    }
    await refreshPipeline();
  }

  function setupDropZone(type, multiple) {
    const zone = qs(`#zone-${type}`);
    const input = qs(`#input-${type}`);
    if (!zone || !input) return;

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      const files = [...e.dataTransfer.files].filter((f) => f.name.endsWith(".csv"));
      if (!files.length) return;
      try {
        await uploadZone(type, multiple ? files : [files[0]]);
        const badge = qs(`#badge-${type}`);
        if (badge) {
          badge.style.display = "block";
          badge.textContent = multiple ? `${files.length} file(s) uploaded` : files[0].name;
        }
      } catch (err) {
        alert(err.message);
      }
    });
    input.addEventListener("change", async () => {
      const files = [...input.files];
      if (!files.length) return;
      try {
        await uploadZone(type, multiple ? files : files);
        const badge = qs(`#badge-${type}`);
        if (badge) {
          badge.style.display = "block";
          badge.textContent = multiple ? `${files.length} file(s) uploaded` : files[0].name;
        }
      } catch (err) {
        alert(err.message);
      }
    });
  }

  async function runClassify() {
    if (!(await requireJob())) return;
    const settingsRes = await fetch(`/api/jobs/${jobId}/settings`);
    if (settingsRes.ok) {
      const s = await settingsRes.json();
      classifyModel = s.settings?.model || "gpt-4o-mini";
    }
    startClassifyTimer();
    const res = await fetch(`/api/jobs/${jobId}/classify`, { method: "POST", body: new FormData() });
    if (!res.ok) {
      stopClassifyTimer();
      throw new Error((await res.json()).detail || "Failed to start");
    }
    connectEvents(
      (d) => updateProgress(d, "classify"),
      (data) => {
        if (data.status === "completed") {
          const msg = qs("#classifyMessage");
          if (msg) msg.textContent = data.message || "Classification complete";
        }
      }
    );
  }

  async function runConsolidate() {
    if (!(await requireJob())) return;
    const res = await fetch(`/api/jobs/${jobId}/consolidate`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to start");
    connectEvents(
      (d) => updateProgress(d, "consolidate"),
      async (data) => {
        if (data.status === "completed") {
          await window.EF02Analysis.render(jobId);
          updateAnalysisVisibility();
          const content = qs("#analysisContent");
          if (content) content.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    );
  }

  async function uploadLabels(file) {
    if (!(await requireJob())) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/jobs/${jobId}/consolidate/upload-labels`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await parseApiError(res, "Upload failed"));
    const data = await res.json();
    const badge = qs("#badge-labels");
    if (badge) {
      badge.style.display = "block";
      badge.textContent = `${file.name} (${formatNum(data.rows || 0)} rows)`;
    }
    await refreshPipeline();
    return data;
  }

  async function openSettings() {
    if (!(await requireJob())) return;
    const res = await fetch(`/api/jobs/${jobId}/settings`);
    const data = await res.json();
    qs("#settingsSystemPrompt").value = data.settings.system_prompt;
    qs("#settingsUserPrompt").value = data.settings.user_prompt_template;
    qs("#settingsBatchSize").value = data.settings.batch_size;
    qs("#settingsRetryBatch").value = data.settings.retry_batch_size;
    qs("#settingsSleep").value = data.settings.sleep_sec;
    qs("#settingsModel").value = data.settings.model || "gpt-4o-mini";
    qs("#settingsApiKey").value = "";
    const hint = qs("#settingsApiKeyHint");
    if (hint) {
      hint.textContent = data.has_api_key
        ? "API key saved for this job (enter a new value to replace)"
        : "No key saved — will use .env if available";
    }
    qs("#settingsModal").classList.add("open");
  }

  async function saveSettings() {
    const body = {
      system_prompt: qs("#settingsSystemPrompt").value,
      user_prompt_template: qs("#settingsUserPrompt").value,
      batch_size: Number(qs("#settingsBatchSize").value),
      retry_batch_size: Number(qs("#settingsRetryBatch").value),
      sleep_sec: Number(qs("#settingsSleep").value),
      model: qs("#settingsModel").value,
    };
    const apiKey = qs("#settingsApiKey")?.value?.trim();
    if (apiKey) body.api_key = apiKey;
    const res = await fetch(`/api/jobs/${jobId}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("Save failed");
    qs("#settingsModal").classList.remove("open");
  }

  async function resetSettings() {
    await fetch(`/api/jobs/${jobId}/settings/reset`, { method: "POST" });
    await openSettings();
  }

  async function resumeSession(id, name) {
    jobId = id;
    jobName = name;
    localStorage.setItem(STORAGE_KEY, jobId);
    updateJobBadge();
    await refreshPipeline();
    if (!pipeline) {
      showPage("home");
      return;
    }
    if (pipeline.analysis.ready) showPage("analysis");
    else if (pipeline.data?.can_skip_to_analysis || pipeline.classify.done) showPage("analysis");
    else if (pipeline.data?.can_classify) showPage("classify");
    else showPage("data");
  }

  async function deleteSession(id, name) {
    if (!confirm(`Delete "${name}"?\n\nThis permanently removes all cached files for this session.`)) return;
    const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await parseApiError(res, "Delete failed"));
    if (jobId === id) {
      jobId = null;
      jobName = null;
      pipeline = null;
      localStorage.removeItem(STORAGE_KEY);
      updateJobBadge();
    }
    await loadRecentRuns();
  }

  async function renameSession(id, currentName) {
    const name = await openSessionModal({
      title: "Rename session",
      hint: "Choose a new name for this analysis.",
      confirmLabel: "Save",
      defaultValue: currentName,
    });
    if (!name?.trim() || name.trim() === currentName) return;
    const res = await fetch(`/api/jobs/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!res.ok) throw new Error(await parseApiError(res, "Rename failed"));
    if (jobId === id) {
      jobName = name.trim();
      updateJobBadge();
    }
    await loadRecentRuns();
  }

  function displayName(job) {
    return job.name || `Session ${job.job_id.slice(0, 8)}`;
  }

  async function loadRecentRuns() {
    const res = await fetch("/api/jobs");
    if (!res.ok) return;
    const data = await res.json();
    const jobs = data.jobs || [];
    const tbody = qs("#runsTableBody");
    const empty = qs("#runsEmpty");
    if (!tbody) return;

    if (empty) empty.hidden = jobs.length > 0;
    tbody.innerHTML = jobs
      .map((j) => {
        const label = displayName(j);
        return `<tr>
          <td>
            <span class="session-name">${escapeHtml(label)}</span>
            <span class="session-id">${j.job_id}</span>
          </td>
          <td>${escapeHtml(j.status || "—")}</td>
          <td>${j.preview?.headline_rows ?? "—"}</td>
          <td>${formatDateTime(j.created_at)}</td>
          <td>${formatDateTime(j.updated_at || j.created_at)}</td>
          <td>
            <div class="session-actions">
              <button class="btn-secondary" data-resume="${j.job_id}" data-name="${escapeAttr(label)}">Open</button>
              <button class="btn-secondary" data-rename="${j.job_id}" data-name="${escapeAttr(label)}">Rename</button>
              <button class="btn-danger" data-delete="${j.job_id}" data-name="${escapeAttr(label)}">Delete</button>
            </div>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-resume]").forEach((btn) => {
      btn.addEventListener("click", () =>
        resumeSession(btn.dataset.resume, btn.dataset.name).catch((e) => alert(e.message))
      );
    });
    tbody.querySelectorAll("[data-rename]").forEach((btn) => {
      btn.addEventListener("click", () =>
        renameSession(btn.dataset.rename, btn.dataset.name).catch((e) => alert(e.message))
      );
    });
    tbody.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", () =>
        deleteSession(btn.dataset.delete, btn.dataset.name).catch((e) => alert(e.message))
      );
    });
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/'/g, "&#39;");
  }

  function bindNav() {
    document.querySelectorAll(".nav a[data-goto]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const li = a.closest("li");
        if (li?.classList.contains("nav-locked")) return;
        showPage(a.dataset.goto);
      });
    });
    qs("#logoHome")?.addEventListener("click", (e) => {
      e.preventDefault();
      showPage("home");
    });
    qs("#btnNewJob")?.addEventListener("click", async () => {
      const name = await openSessionModal({
        title: "Name your analysis",
        hint: "Give this session a memorable name before you begin.",
        confirmLabel: "Create",
      });
      if (!name?.trim()) return;
      try {
        await createNamedJob(name.trim());
        pipeline = null;
        await refreshPipeline();
        showPage("data");
      } catch (e) {
        alert(e.message);
      }
    });
    qs("#btnOpenData")?.addEventListener("click", async () => {
      if (!jobId) {
        alert("Create a new analysis or open a saved session first.");
        return;
      }
      await refreshPipeline();
      if (pipeline?.analysis.ready) showPage("analysis");
      else if (pipeline?.data?.can_skip_to_analysis || pipeline?.classify.done) showPage("analysis");
      else if (pipeline?.data?.can_classify) showPage("classify");
      else showPage("data");
    });
    qs("#btnNextClassify")?.addEventListener("click", () => showPage("classify"));
    qs("#btnNextAnalysis")?.addEventListener("click", () => showPage("analysis"));
    qs("#btnNextAnalysisFromData")?.addEventListener("click", () => showPage("analysis"));
    qs("#btnRunClassify")?.addEventListener("click", () => runClassify().catch((e) => alert(e.message)));
    qs("#btnRunConsolidate")?.addEventListener("click", () => runConsolidate().catch((e) => alert(e.message)));
    qs("#btnOpenSettings")?.addEventListener("click", () => openSettings());
    qs("#btnCloseSettings")?.addEventListener("click", () => qs("#settingsModal").classList.remove("open"));
    qs("#btnSaveSettings")?.addEventListener("click", () => saveSettings().catch((e) => alert(e.message)));
    qs("#btnResetSettings")?.addEventListener("click", () => resetSettings());
    const onLabelsFile = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      try {
        await uploadLabels(f);
        if (pipeline?.data?.can_skip_to_analysis) showPage("analysis");
      } catch (err) {
        alert(err.message);
      }
    };
    qs("#inputLabelsUpload")?.addEventListener("change", onLabelsFile);
    qs("#inputLabelsUploadClassify")?.addEventListener("change", onLabelsFile);
    qs("#btnSessionConfirm")?.addEventListener("click", () => {
      const name = qs("#sessionNameInput")?.value?.trim();
      if (!name) {
        alert("Please enter a session name.");
        return;
      }
      closeSessionModal(name);
    });
    qs("#btnSessionCancel")?.addEventListener("click", () => closeSessionModal(null));
    qs("#sessionNameInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") qs("#btnSessionConfirm")?.click();
      if (e.key === "Escape") closeSessionModal(null);
    });
    document.querySelectorAll(".modal-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".modal-tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".modal-panel").forEach((p) => (p.style.display = "none"));
        tab.classList.add("active");
        qs(`#panel-${tab.dataset.tab}`).style.display = "block";
      });
    });
  }

  async function init() {
    bindNav();
    setupDropZone("headlines", true);
    setupDropZone("labels", false);
    setupDropZone("cpi", false);
    setupDropZone("fx", false);
    updateJobBadge();
    await loadRecentRuns();

    const params = new URLSearchParams(location.search);
    if (params.get("job")) {
      jobId = params.get("job");
      localStorage.setItem(STORAGE_KEY, jobId);
    }
    if (jobId) {
      await refreshPipeline();
    } else {
      updateJobBadge();
    }

    let page = params.get("page") || "home";
    if (page === "consolidate") page = "analysis";
    showPage(pages.includes(page) ? page : "home");
    if (page === "analysis" && pipeline?.analysis.ready) {
      await window.EF02Analysis.render(jobId);
    }
  }

  return { init, showPage, refreshPipeline };
})();

document.addEventListener("DOMContentLoaded", () => EF02App.init());
