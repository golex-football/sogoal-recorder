// SoGoal Link Recorder Frontend Application

const API_BASE = window.location.origin;
let activeSessions = [];
let presets = null;
let socket = null;

// DOM Elements
const formRecord = document.getElementById("form-record");
const inputUrl = document.getElementById("input-url");
const selectSeason = document.getElementById("select-season");
const selectComp = document.getElementById("select-competition");
const inputMatchName = document.getElementById("input-match-name");
const selectBitrate = document.getElementById("select-bitrate");
const selectEngine = document.getElementById("select-engine");
const activeContainer = document.getElementById("active-recordings-container");
const activeCountLabel = document.getElementById("active-count");
const libraryTbody = document.getElementById("library-tbody");
const wsStatusBadge = document.getElementById("ws-status");
const btnPaste = document.getElementById("btn-paste");
const btnAddSeason = document.getElementById("btn-add-season");
const btnAddComp = document.getElementById("btn-add-comp");
const btnOpenRootFolder = document.getElementById("btn-open-root-folder");
const btnRefreshLibrary = document.getElementById("btn-refresh-library");

// Initialize
document.addEventListener("DOMContentLoaded", async () => {
  await loadPresets();
  await loadLibrary();
  initWebSocket();
  setupEventListeners();
});

// Load Presets from API
async function loadPresets() {
  try {
    const res = await fetch(`${API_BASE}/api/presets`);
    presets = await res.json();

    // Populate Seasons
    selectSeason.innerHTML = "";
    presets.seasons.forEach((season) => {
      const opt = document.createElement("option");
      opt.value = season;
      opt.textContent = season.replace(/_/g, " ");
      selectSeason.appendChild(opt);
    });

    // Populate Competitions
    selectComp.innerHTML = "";
    presets.competitions.forEach((comp) => {
      const opt = document.createElement("option");
      opt.value = comp;
      opt.textContent = comp.replace(/_/g, " ");
      selectComp.appendChild(opt);
    });

    // Populate Bitrates
    selectBitrate.innerHTML = "";
    for (const [key, val] of Object.entries(presets.bitrate_presets)) {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = `${val.label} - ${val.desc}`;
      selectBitrate.appendChild(opt);
    }
  } catch (err) {
    console.error("Failed to load presets:", err);
  }
}

// Setup Event Listeners
function setupEventListeners() {
  // Form submission
  formRecord.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = inputUrl.value.trim();
    const season = selectSeason.value;
    const competition = selectComp.value;
    const matchName = inputMatchName.value.trim();
    const bitrate = selectBitrate.value;
    const engine = selectEngine.value;

    if (!url || !matchName) {
      alert("Please fill in both the Link and Match ID / Name.");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/record/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url,
          season: season,
          competition: competition,
          match_name: matchName,
          bitrate_preset: bitrate,
          capture_type: engine,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Failed to start recording: ${err.detail || "Unknown error"}`);
        return;
      }

      inputUrl.value = "";
      // Suggest next match id if numeric
      const matchNum = matchName.match(/match_id_(\d+)/);
      if (matchNum) {
        const nextNum = parseInt(matchNum[1], 10) + 1;
        inputMatchName.value = `match_id_${nextNum}`;
      }

      await loadLibrary();
    } catch (err) {
      alert(`Error starting recording: ${err.message}`);
    }
  });

  // Paste button
  btnPaste.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        inputUrl.value = text;
      }
    } catch (e) {
      inputUrl.focus();
    }
  });

  // Add Custom Season
  btnAddSeason.addEventListener("click", async () => {
    const name = prompt("Enter new Season name (e.g. Season_2027_2028):");
    if (!name) return;
    try {
      const res = await fetch(`${API_BASE}/api/presets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "season", name: name }),
      });
      if (res.ok) {
        await loadPresets();
        selectSeason.value = name.trim().replace(/\s+/g, "_");
      }
    } catch (err) {
      alert("Error adding season: " + err);
    }
  });

  // Add Custom Competition
  btnAddComp.addEventListener("click", async () => {
    const name = prompt("Enter new Competition name (e.g. Asian_Champions_League):");
    if (!name) return;
    try {
      const res = await fetch(`${API_BASE}/api/presets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "competition", name: name }),
      });
      if (res.ok) {
        await loadPresets();
        selectComp.value = name.trim().replace(/\s+/g, "_");
      }
    } catch (err) {
      alert("Error adding competition: " + err);
    }
  });

  // Open Storage Root Folder
  btnOpenRootFolder.addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/api/system/open-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    } catch (e) {
      console.error(e);
    }
  });

  // Refresh Library
  btnRefreshLibrary.addEventListener("click", async () => {
    await loadLibrary();
  });
}

// WebSocket Connection for Live Metrics
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    wsStatusBadge.textContent = "🟢 Live Connected";
    wsStatusBadge.style.color = "var(--accent)";
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && data.recordings) {
        renderActiveRecordings(data.recordings);
      }
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  socket.onclose = () => {
    wsStatusBadge.textContent = "🔴 Reconnecting...";
    wsStatusBadge.style.color = "var(--danger)";
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = (err) => {
    console.error("WS error:", err);
  };
}

// Render Active Concurrent Recordings
function renderActiveRecordings(recordings) {
  activeSessions = recordings.filter(
    (r) => r.status === "recording" || r.status === "starting" || r.status === "stopping"
  );
  activeCountLabel.textContent = `${activeSessions.length} Active`;

  if (activeSessions.length === 0) {
    activeContainer.innerHTML = `<div class="empty-state">No streams currently recording. Enter a link above and click Start!</div>`;
    return;
  }

  // Preserve open logs states
  const openLogs = new Set();
  document.querySelectorAll(".log-drawer.open").forEach((el) => {
    openLogs.add(el.dataset.id);
  });

  activeContainer.innerHTML = activeSessions
    .map((session) => {
      const isStopping = session.status === "stopping";
      const isLogsOpen = openLogs.has(session.id) ? "open" : "";
      const logLines = (session.logs || []).slice(-10).join("\n") || "Connecting...";

      return `
      <div class="active-card ${session.status}" id="session-card-${session.id}">
        <div class="active-card-top">
          <div class="badge-rec">
            <div class="pulse-dot"></div>
            <span>${isStopping ? "STOPPING..." : "RECORDING"}</span>
          </div>
          <div class="live-timer">${session.elapsed_formatted}</div>
        </div>

        <div class="match-info-title">${escapeHtml(session.match_name)}</div>
        <div class="match-subtext">
          <span class="subtext-tag">${escapeHtml(session.season)}</span>
          <span class="subtext-tag">${escapeHtml(session.competition)}</span>
          <span class="subtext-tag">${escapeHtml(session.bitrate_preset)}</span>
        </div>

        <div class="stats-bar">
          <div class="stat-item">
            <span class="stat-label">File Size</span>
            <span class="stat-val">${session.file_size_formatted}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Bitrate</span>
            <span class="stat-val">${session.current_bitrate || "--"}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">FPS</span>
            <span class="stat-val">${session.fps || "--"}</span>
          </div>
        </div>

        <button class="btn-stop" onclick="stopRecording('${session.id}')" ${isStopping ? "disabled" : ""}>
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
          ${isStopping ? "Finalizing Stream..." : "Stop & Finalize Recording"}
        </button>

        <button class="log-toggle" onclick="toggleLogs('${session.id}')">Toggle Live Stream Log</button>
        <div class="log-drawer ${isLogsOpen}" id="log-${session.id}" data-id="${session.id}">
          <pre>${escapeHtml(logLines)}</pre>
        </div>
      </div>
    `;
    })
    .join("");
}

// Stop Recording
window.stopRecording = async function (id) {
  try {
    const btn = document.querySelector(`#session-card-${id} .btn-stop`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Finalizing Stream...";
    }
    const res = await fetch(`${API_BASE}/api/record/stop/${id}`, {
      method: "POST",
    });
    if (res.ok) {
      setTimeout(loadLibrary, 2000);
    }
  } catch (err) {
    alert("Error stopping recording: " + err.message);
  }
};

// Toggle Logs
window.toggleLogs = function (id) {
  const drawer = document.getElementById(`log-${id}`);
  if (drawer) {
    drawer.classList.toggle("open");
  }
};

// Load Library from Directory
async function loadLibrary() {
  try {
    const res = await fetch(`${API_BASE}/api/recordings/library`);
    const data = await res.json();
    const items = data.items || [];

    if (items.length === 0) {
      libraryTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No recorded video files found yet in storage folder.</td></tr>`;
      return;
    }

    libraryTbody.innerHTML = items
      .map(
        (item) => `
      <tr>
        <td style="font-weight: 600; color: #ffffff;">${escapeHtml(item.name)}</td>
        <td><span class="subtext-tag">${escapeHtml(item.season)}</span></td>
        <td><span class="subtext-tag">${escapeHtml(item.competition)}</span></td>
        <td><strong style="color: var(--accent);">${escapeHtml(item.match)}</strong></td>
        <td style="font-family: var(--font-mono);">${item.size_formatted}</td>
        <td style="color: var(--text-muted); font-size: 0.8rem;">${item.modified_formatted}</td>
        <td style="text-align: right;">
          <div class="action-btns" style="justify-content: flex-end;">
            <button class="btn-play" onclick="playVideo('${escapeQuote(item.path)}')">Play</button>
            <button class="btn-open" onclick="openFolder('${escapeQuote(item.folder)}')">Folder</button>
            <button class="btn-open" style="color: var(--danger); border-color: rgba(255,51,75,0.3);" onclick="deleteVideo('${escapeQuote(item.path)}')">✕</button>
          </div>
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    console.error("Library load error:", err);
  }
}

// System Actions
window.playVideo = async function (path) {
  try {
    await fetch(`${API_BASE}/api/system/play`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  } catch (e) {
    alert("Could not launch video player: " + e);
  }
};

window.openFolder = async function (path) {
  try {
    await fetch(`${API_BASE}/api/system/open-folder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  } catch (e) {
    alert("Could not open folder: " + e);
  }
};

window.deleteVideo = async function (path) {
  if (!confirm("Are you sure you want to permanently delete this recording?")) return;
  try {
    const res = await fetch(`${API_BASE}/api/recordings/file`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (res.ok) {
      await loadLibrary();
    }
  } catch (e) {
    alert("Delete error: " + e);
  }
};

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeQuote(str) {
  if (!str) return "";
  return str.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}
