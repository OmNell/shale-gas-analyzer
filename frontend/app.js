const state = {
  eventSeq: 0,
  eventSource: null,
  running: false,
  startedAt: null,
  timer: null,
  phases: new Set(),
};

const els = {
  form: document.querySelector("#runForm"),
  wellName: document.querySelector("#wellName"),
  dataFile: document.querySelector("#dataFile"),
  dataFileLabel: document.querySelector("#dataFileLabel"),
  ragEnabled: document.querySelector("#ragEnabled"),
  ragRebuild: document.querySelector("#ragRebuild"),
  startBtn: document.querySelector("#startBtn"),
  stopBtn: document.querySelector("#stopBtn"),
  clearLogBtn: document.querySelector("#clearLogBtn"),
  refreshReportBtn: document.querySelector("#refreshReportBtn"),
  statusPill: document.querySelector("#statusPill"),
  statusText: document.querySelector("#statusText"),
  runId: document.querySelector("#runId"),
  phaseName: document.querySelector("#phaseName"),
  elapsed: document.querySelector("#elapsed"),
  logStream: document.querySelector("#logStream"),
  reportView: document.querySelector("#reportView"),
  timeline: document.querySelector("#timeline"),
};

function postJSON(url, payload = {}) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  });
}

async function uploadDataFile() {
  const file = els.dataFile.files && els.dataFile.files[0];
  if (!file) return null;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    throw new Error("只能上传 CSV 文件");
  }
  const response = await fetch("/api/upload", {
    method: "POST",
    headers: {
      "Content-Type": "text/csv",
      "X-File-Name": encodeURIComponent(file.name),
    },
    body: await file.arrayBuffer(),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "上传失败");
  return data.file;
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const minutes = String(Math.floor(total / 60)).padStart(2, "0");
  const rest = String(total % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function updateElapsed() {
  if (!state.startedAt) {
    els.elapsed.textContent = "00:00";
    return;
  }
  els.elapsed.textContent = formatTime(Date.now() / 1000 - state.startedAt);
}

function setRunning(running) {
  state.running = running;
  els.startBtn.disabled = running;
  els.stopBtn.disabled = !running;
  els.statusPill.classList.toggle("running", running);
  if (running && !state.timer) {
    state.timer = setInterval(updateElapsed, 1000);
  }
  if (!running && state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

function setStatus(status) {
  const label = {
    starting: "Starting",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    stopped: "Stopped",
    stopping: "Stopping",
    idle: "Idle",
  }[status] || status;
  els.statusText.textContent = label;
  els.statusPill.classList.toggle("failed", status === "failed");
}

function resetTimeline() {
  state.phases.clear();
  els.timeline.querySelectorAll("li").forEach((item) => {
    item.classList.remove("active", "done");
  });
}

function markPhase(phase) {
  if (!phase || ["queued", "agent", "stopping", "done"].includes(phase)) return;
  state.phases.add(phase);
  const readable = {
    rag: "RAG",
    data: "数据分析",
    engineering: "工程决策",
    report: "报告生成",
    error: "异常",
  }[phase] || phase;
  els.phaseName.textContent = readable;
  els.timeline.querySelectorAll("li").forEach((item) => {
    const itemPhase = item.dataset.phase;
    item.classList.toggle("active", itemPhase === phase);
    if (state.phases.has(itemPhase) && itemPhase !== phase) item.classList.add("done");
  });
}

function appendLog(event) {
  const nearBottom = els.logStream.scrollHeight - els.logStream.scrollTop - els.logStream.clientHeight < 48;
  const time = new Date(event.timestamp * 1000).toLocaleTimeString("zh-CN", { hour12: false });
  const prefix = event.kind === "log" ? "" : `[${event.kind}] `;
  els.logStream.textContent += `${time} ${prefix}${event.message}\n`;
  const lines = els.logStream.textContent.split("\n");
  if (lines.length > 1200) {
    els.logStream.textContent = lines.slice(lines.length - 1200).join("\n");
  }
  if (nearBottom) {
    els.logStream.scrollTop = els.logStream.scrollHeight;
  }
}

function escapeHTML(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inlineMarkdown(text) {
  return escapeHTML(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  let inList = false;
  let table = [];

  function closeList() {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  }

  function flushTable() {
    if (!table.length) return;
    closeList();
    const rows = table
      .filter((line) => !/^\s*\|?\s*-{3,}/.test(line.replace(/\|/g, "")))
      .map((line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => inlineMarkdown(cell.trim())));
    if (rows.length) {
      html.push("<table>");
      rows.forEach((row, index) => {
        html.push(index === 0 ? "<thead><tr>" : "<tr>");
        row.forEach((cell) => html.push(index === 0 ? `<th>${cell}</th>` : `<td>${cell}</td>`));
        html.push(index === 0 ? "</tr></thead><tbody>" : "</tr>");
      });
      html.push("</tbody></table>");
    }
    table = [];
  }

  for (const raw of lines) {
    const line = raw.trim();
    if (line.includes("|") && line.startsWith("|")) {
      table.push(line);
      continue;
    }
    flushTable();

    if (!line) {
      closeList();
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      html.push(`<h1>${inlineMarkdown(line.slice(2))}</h1>`);
    } else if (line.startsWith("## ")) {
      closeList();
      html.push(`<h2>${inlineMarkdown(line.slice(3))}</h2>`);
    } else if (line.startsWith("### ")) {
      closeList();
      html.push(`<h3>${inlineMarkdown(line.slice(4))}</h3>`);
    } else if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`);
    } else {
      closeList();
      html.push(`<p>${inlineMarkdown(line)}</p>`);
    }
  }
  flushTable();
  closeList();
  return html.join("");
}

async function loadReport() {
  const response = await fetch("/api/report");
  const report = await response.json();
  if (!report.exists || !report.content.trim()) {
    els.reportView.innerHTML = '<p class="empty">暂无新报告</p>';
    return;
  }
  els.reportView.innerHTML = renderMarkdown(report.content);
}

function openEvents() {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = new EventSource(`/api/events?after=${state.eventSeq}`);
  state.eventSource.onmessage = async (message) => {
    const payload = JSON.parse(message.data);
    for (const event of payload.events) {
      state.eventSeq = Math.max(state.eventSeq, Number(event.seq));
      markPhase(event.phase);
      appendLog(event);
      if (event.kind === "report") await loadReport();
    }
    const run = payload.state.run;
    if (run) applyRun(run);
    if (!payload.state.running && state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
      await loadReport();
    }
  };
  state.eventSource.onerror = () => {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
  };
}

function applyRun(run) {
  els.runId.textContent = run?.id || "-";
  if (run?.startedAt) state.startedAt = run.startedAt;
  setStatus(run?.status || "idle");
  setRunning(["starting", "running", "stopping"].includes(run?.status));
  updateElapsed();
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.logStream.textContent = "";
  resetTimeline();
  state.eventSeq = 0;

  const mode = new FormData(els.form).get("mode") || "run";
  const payload = {
    mode,
    wellName: els.wellName.value.trim(),
    skipRag: !els.ragEnabled.checked,
    ragRebuild: els.ragRebuild.checked,
  };

  try {
    const uploaded = await uploadDataFile();
    if (uploaded) {
      payload.dataFileId = uploaded.id;
      els.logStream.textContent += `上传数据文件：${uploaded.name} (${uploaded.size} bytes)\n`;
    }
    const data = await postJSON("/api/runs", payload);
    applyRun(data.run);
    openEvents();
  } catch (error) {
    setStatus("failed");
    els.logStream.textContent += `${error.message}\n`;
  }
});

els.dataFile.addEventListener("change", () => {
  const file = els.dataFile.files && els.dataFile.files[0];
  els.dataFileLabel.textContent = file ? file.name : "上传生产 CSV";
});

els.stopBtn.addEventListener("click", async () => {
  await postJSON("/api/stop", {});
});

els.clearLogBtn.addEventListener("click", () => {
  els.logStream.textContent = "";
});

els.refreshReportBtn.addEventListener("click", loadReport);

async function boot() {
  const response = await fetch("/api/state");
  const snapshot = await response.json();
  if (snapshot.run) {
    applyRun(snapshot.run);
    state.eventSeq = Math.max(0, Number(snapshot.sequence || 0) - 200);
    if (snapshot.running) openEvents();
  } else {
    setStatus("idle");
    setRunning(false);
  }
  await loadReport();
}

boot();
