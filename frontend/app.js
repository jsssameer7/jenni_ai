// Jenni AI — Your Personal Assistant (Frontend Client)

let currentSessionId = "default";
let isSpeakingEnabled = false;
let activeConfirmationId = null;
let isRecording = false;
let speechRecognition = null;

// --- Authentication & Session Management ---
function getSessionToken() {
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get("token");
  if (urlToken) {
    localStorage.setItem("jenni_session_token", urlToken);
    return urlToken;
  }
  return localStorage.getItem("jenni_session_token") || localStorage.getItem("jenni_token") || "";
}

function getCurrentUser() {
  try {
    const raw = localStorage.getItem("jenni_user");
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

async function handleLogout() {
  const token = getSessionToken();
  if (token) {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
    } catch (e) {}
  }
  localStorage.removeItem("jenni_session_token");
  localStorage.removeItem("jenni_user");
  localStorage.removeItem("jenni_token");
  window.location.replace("/login");
}

function updateUserInfoUI() {
  const user = getCurrentUser();
  const label = document.getElementById("logout-user-label");
  if (label && user) {
    label.textContent = user.display_name || user.username || "";
  }
}

function copyPhoneUrl() {
  const host = window.location.host;
  const protocol = window.location.protocol;
  const url = `${protocol}//${host}/login`;
  navigator.clipboard.writeText(url).then(() => {
    alert("Phone login link copied to clipboard:\n" + url);
  }).catch(() => {
    prompt("Copy this URL to open on your Android phone:", url);
  });
}

// Helper for authenticated fetch
async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = getSessionToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
    headers["X-Jenni-Token"] = token;
  }
  try {
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      localStorage.removeItem("jenni_session_token");
      window.location.replace("/login");
    }
    return res;
  } catch (e) {
    console.error("Network or fetch error:", e);
    throw e;
  }
}

// Initialize application
document.addEventListener("DOMContentLoaded", async () => {
  const token = getSessionToken();
  if (!token) {
    window.location.replace("/login");
    return;
  }

  updateUserInfoUI();
  setupNavigation();
  setupSpeechRecognition();
  setupVoiceSynthesis();
  setupChatHandlers();
  setupMemoryHandlers();
  setupFileSearchHandlers();
  setupImageStudioHandlers();
  setupModals();

  // Load initial data
  await loadSystemStatus();
  await loadChatHistory();
  await loadMemories();
  await loadPCMetrics();
  await loadWorkflows();
  await loadImages();
  await loadMobileInfo();

  // Background metric poller every 5 seconds
  setInterval(loadPCMetrics, 5000);
});

// --- Navigation Tabs ---
function setupNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  const tabViews = document.querySelectorAll(".tab-view");
  const viewTitle = document.getElementById("current-view-title");
  const mobileToggle = document.getElementById("mobile-toggle");
  const sidebar = document.getElementById("sidebar");

  const titles = {
    "chat-tab": "Chat & Voice Assistant",
    "pc-tab": "Safe PC Functions & Hardware",
    "memory-tab": "Persistent Personal Memory",
    "files-tab": "Approved Directory File Search",
    "images-tab": "Jenni AI Image Studio",
    "tasks-tab": "Automated Multi-Step Workflows",
    "mobile-tab": "Android 12 Phone Integration"
  };

  navItems.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");

      navItems.forEach(n => n.classList.remove("active"));
      tabViews.forEach(v => v.classList.remove("active"));

      btn.classList.add("active");
      const targetView = document.getElementById(targetId);
      if (targetView) targetView.classList.add("active");

      if (viewTitle) viewTitle.textContent = titles[targetId] || "Jenni AI";
      if (sidebar) sidebar.classList.remove("open");
    });
  });

  if (mobileToggle && sidebar) {
    mobileToggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
  }
}

// --- Speech Recognition (Speech-to-Text) ---
function setupSpeechRecognition() {
  const micBtn = document.getElementById("voice-record-btn");
  const indicator = document.getElementById("voice-indicator");
  const langSelect = document.getElementById("voice-lang-select");
  const chatInput = document.getElementById("chat-input");

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    console.warn("Browser SpeechRecognition not natively supported.");
    if (micBtn) {
      micBtn.title = "Web Speech API not supported in this browser. Use text input.";
    }
    return;
  }

  speechRecognition = new SpeechRecognition();
  speechRecognition.continuous = false;
  speechRecognition.interimResults = false;

  speechRecognition.onstart = () => {
    isRecording = true;
    micBtn.classList.add("recording");
    if (indicator) indicator.classList.add("active");
  };

  speechRecognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (chatInput && transcript) {
      chatInput.value = transcript;
      sendMessage(transcript);
    }
  };

  speechRecognition.onerror = (event) => {
    console.warn("Speech recognition error:", event.error);
    stopRecording();
  };

  speechRecognition.onend = () => {
    stopRecording();
  };

  function stopRecording() {
    isRecording = false;
    micBtn.classList.remove("recording");
    if (indicator) indicator.classList.remove("active");
  }

  if (micBtn) {
    micBtn.addEventListener("click", () => {
      if (isRecording) {
        speechRecognition.stop();
      } else {
        speechRecognition.lang = langSelect.value || "en-US";
        speechRecognition.start();
      }
    });
  }
}

// --- Speech Synthesis (Text-to-Speech) ---
function setupVoiceSynthesis() {
  const ttsBtn = document.getElementById("tts-toggle-btn");
  const ttsLabel = document.getElementById("tts-label");
  const iconOn = document.getElementById("tts-icon-on");
  const iconOff = document.getElementById("tts-icon-off");

  const savedPref = localStorage.getItem("jenni_audio_output");
  isSpeakingEnabled = savedPref === "true";

  function updateTTSUI() {
    if (isSpeakingEnabled) {
      if (ttsLabel) ttsLabel.textContent = "Audio: On";
      if (iconOn) iconOn.classList.remove("hidden");
      if (iconOff) iconOff.classList.add("hidden");
    } else {
      if (ttsLabel) ttsLabel.textContent = "Audio: Off";
      if (iconOn) iconOn.classList.add("hidden");
      if (iconOff) iconOff.classList.remove("hidden");
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    }
  }

  updateTTSUI();

  if (ttsBtn) {
    ttsBtn.addEventListener("click", () => {
      isSpeakingEnabled = !isSpeakingEnabled;
      localStorage.setItem("jenni_audio_output", isSpeakingEnabled ? "true" : "false");
      updateTTSUI();
    });
  }
}

function speakTextAloud(text) {
  if (!isSpeakingEnabled || !text) {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    return;
  }

  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const langSelect = document.getElementById("voice-lang-select");
    utterance.lang = langSelect ? langSelect.value : "en-US";
    utterance.rate = 1.0;
    utterance.pitch = 1.05;

    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => 
      v.name.includes("Zira") || v.name.includes("Female") || v.name.includes("Google UK English Female")
    );
    if (preferredVoice) utterance.voice = preferredVoice;

    window.speechSynthesis.speak(utterance);
  }
}

// --- Chat View & Messaging ---
function setupChatHandlers() {
  const sendBtn = document.getElementById("send-btn");
  const chatInput = document.getElementById("chat-input");
  const clearBtn = document.getElementById("clear-chat-btn");
  const quickChips = document.querySelectorAll(".suggestion-chip");

  if (sendBtn && chatInput) {
    sendBtn.addEventListener("click", () => {
      const msg = chatInput.value.trim();
      if (msg) {
        sendMessage(msg);
        chatInput.value = "";
      }
    });

    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const msg = chatInput.value.trim();
        if (msg) {
          sendMessage(msg);
          chatInput.value = "";
        }
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      if (confirm("Are you sure you want to clear the conversation history?")) {
        await apiFetch(`/api/chat/history?session_id=${currentSessionId}`, { method: "DELETE" });
        const container = document.getElementById("chat-messages");
        if (container) container.innerHTML = "";
        renderAssistantGreeting();
      }
    });
  }

  quickChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-query");
      if (q) sendMessage(q);
    });
  });
}

function renderMessage(role, text, metadata = null) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-av" : "jenni-av"}`;
  avatar.textContent = role === "user" ? "You" : "JA";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  let formatted = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  bubble.innerHTML = formatted;

  if (metadata && metadata.data) {
    const actCard = document.createElement("div");
    actCard.className = "action-card-inline";
    actCard.innerHTML = `<span>⚡</span> <span>${metadata.data.message || "Executed PC Action"}</span>`;
    bubble.appendChild(actCard);

    if (metadata.data.url) {
      const imgWrap = document.createElement("div");
      imgWrap.className = "chat-image-preview";
      imgWrap.style = "margin-top: 10px; border-radius: 12px; overflow: hidden; max-width: 380px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.15); cursor: pointer;";
      imgWrap.innerHTML = `
        <img src="${metadata.data.url}" alt="${metadata.data.prompt || 'Generated AI Image'}" style="width: 100%; height: auto; display: block;" loading="lazy">
        <div style="padding: 8px 12px; background: rgba(15,23,42,0.95); font-size: 12px; color: #94a3b8; display: flex; justify-content: space-between; align-items: center;">
          <span style="color: #38bdf8; font-weight: 500;">Jenni AI • Watermark-Free</span>
          <span style="font-size: 11px;">Click to enlarge</span>
        </div>
      `;
      imgWrap.addEventListener("click", () => {
        openImageModal(metadata.data.url, metadata.data.filename || "jenni_ai.png");
      });
      bubble.appendChild(imgWrap);
    }
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  container.appendChild(row);

  container.scrollTop = container.scrollHeight;
}

async function sendMessage(text) {
  renderMessage("user", text);

  const container = document.getElementById("chat-messages");
  const typingRow = document.createElement("div");
  typingRow.className = "message-row assistant typing-temp";
  typingRow.innerHTML = `
    <div class="avatar jenni-av">JA</div>
    <div class="msg-bubble"><em>Jenni AI is thinking...</em></div>
  `;
  container.appendChild(typingRow);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: currentSessionId })
    });

    typingRow.remove();

    if (res.ok) {
      const data = await res.json();
      renderMessage("assistant", data.content, data.action);

      if (isSpeakingEnabled && data.spoken_text) {
        speakTextAloud(data.spoken_text);
      }

      if (data.action && data.action.data && data.action.data.needs_confirmation) {
        showConfirmationModal(data.action.data.confirmation_id, data.action.data.message);
      }

      if (data.memory_saved) {
        loadMemories();
      }
    } else {
      const err = await res.json();
      renderMessage("assistant", `⚠️ Error: ${err.detail || err.message || "Unable to get response from Jenni AI"}`);
    }
  } catch (e) {
    typingRow.remove();
    renderMessage("assistant", `⚠️ Connection error: Make sure Jenni AI backend is running. (${e.message})`);
  }
}

async function loadChatHistory() {
  try {
    const res = await apiFetch(`/api/chat/history?session_id=${currentSessionId}`);
    if (res.ok) {
      const history = await res.json();
      const container = document.getElementById("chat-messages");
      if (container) container.innerHTML = "";

      if (history.length === 0) {
        renderAssistantGreeting();
      } else {
        history.forEach(item => {
          renderMessage(item.role, item.content, item.metadata);
        });
      }
    }
  } catch (e) {
    renderAssistantGreeting();
  }
}

function renderAssistantGreeting() {
  renderMessage("assistant", "Hello! I'm Jenni AI, your personal intelligent assistant for Windows 11 and Android 12. How can I help you today? You can talk to me, launch apps, search files, or test automated workflows!");
}

// --- System Status & Metrics ---
async function loadSystemStatus() {
  try {
    const res = await apiFetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      
      const aiBadge = document.getElementById("ai-status-text");
      if (aiBadge) {
        aiBadge.textContent = data.ai.ollama_online ? `Ollama: ${data.ai.default_model}` : "Ollama: Offline";
      }

      const gpuBadge = document.getElementById("gpu-status-text");
      if (gpuBadge && data.gpu) {
        gpuBadge.textContent = data.gpu.available ? `${data.gpu.model.slice(0, 15)} (4GB)` : "GPU: Active";
      }
    }
  } catch (e) {
    console.error("Status load error", e);
  }
}

async function loadPCMetrics() {
  try {
    const res = await apiFetch("/api/pc/status");
    if (res && res.ok) {
      const d = await res.json();

      document.getElementById("metric-cpu").textContent = `${d.cpu_percent}%`;
      document.getElementById("fill-cpu").style.width = `${Math.min(d.cpu_percent, 100)}%`;

      document.getElementById("metric-ram").textContent = `${d.ram_used_gb} / ${d.ram_total_gb} GB (${d.ram_percent}%)`;
      document.getElementById("fill-ram").style.width = `${d.ram_percent}%`;

      if (d.gpu) {
        document.getElementById("metric-gpu").textContent = `${d.gpu.used_vram_mb} / ${d.gpu.total_vram_mb} MB`;
        const gpuPct = (d.gpu.used_vram_mb / (d.gpu.total_vram_mb || 4096)) * 100;
        document.getElementById("fill-gpu").style.width = `${Math.min(gpuPct, 100)}%`;
      }

      document.getElementById("metric-disk").textContent = `${d.disk_free_gb} GB Free (${100 - d.disk_percent}%)`;
      document.getElementById("fill-disk").style.width = `${d.disk_percent}%`;
    }

    // Also load recent action logs
    const logRes = await apiFetch("/api/pc/logs");
    if (logRes && logRes.ok) {
      const logs = await logRes.json();
      const container = document.getElementById("pc-action-logs");
      if (container && logs.length > 0) {
        container.innerHTML = logs.map(l => `
          <div class="log-entry" style="padding: 8px 12px; border-bottom: 1px solid #1e293b; font-size: 0.85rem; display: flex; justify-content: space-between;">
            <div><strong>${l.action_type.toUpperCase()}</strong>: ${l.command}</div>
            <span style="color: ${l.status === 'success' ? '#10b981' : '#f59e0b'};">${l.status}</span>
          </div>
        `).join("");
      }
    }
  } catch (e) {}
}

async function launchApp(appName) {
  try {
    const res = await apiFetch("/api/pc/app", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_name: appName })
    });
    const d = await res.json();
    if (!res.ok) {
      alert(d.detail || d.message || `Could not launch ${appName}`);
      return;
    }
    alert(d.message || `Launched ${appName} successfully.`);
    loadPCMetrics();
  } catch (e) {
    alert("Error launching app: " + (e.message || "Server not reachable"));
  }
}

async function openWeb(url) {
  try {
    const res = await apiFetch("/api/pc/website", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });
    const d = await res.json();
    if (!res.ok) {
      alert(d.detail || d.message || "Failed to open website");
      return;
    }
    if (d.needs_confirmation) {
      showConfirmationModal(d.confirmation_id, d.message);
    } else {
      alert(d.message || `Opened ${url} in your browser.`);
    }
    loadPCMetrics();
  } catch (e) {
    alert("Error opening website: " + (e.message || "Server not reachable"));
  }
}

// --- Memory Manager ---
function setupMemoryHandlers() {
  const saveBtn = document.getElementById("save-memory-btn");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const keyInput = document.getElementById("memory-key");
      const valInput = document.getElementById("memory-val");
      const catInput = document.getElementById("memory-cat");

      const key = keyInput.value.trim();
      const val = valInput.value.trim();
      const cat = catInput.value;

      if (!key || !val) {
        alert("Please provide both a key and a value for this memory preference.");
        return;
      }

      try {
        const res = await apiFetch("/api/memory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key, value: val, category: cat })
        });
        if (res.ok) {
          keyInput.value = "";
          valInput.value = "";
          loadMemories();
        } else {
          const err = await res.json();
          alert("Security guard: " + (err.detail || err.message || "Invalid preference"));
        }
      } catch (e) {
        alert("Failed to save memory: " + e.message);
      }
    });
  }
}

async function loadMemories() {
  try {
    const res = await apiFetch("/api/memory");
    if (res.ok) {
      const list = await res.json();
      const container = document.getElementById("memory-list");
      if (!container) return;

      if (list.length === 0) {
        container.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;">No memories saved yet. Talk to Jenni AI or add one above!</div>`;
        return;
      }

      container.innerHTML = list.map(m => `
        <div class="memory-card">
          <div class="memory-cat">${m.category}</div>
          <div class="memory-key">${m.key}</div>
          <div class="memory-val">${m.value}</div>
          <div class="memory-actions">
            <button class="del-btn" onclick="deleteMemory('${m.id}')" title="Delete memory">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
            </button>
          </div>
        </div>
      `).join("");
    }
  } catch (e) {}
}

async function deleteMemory(id) {
  if (confirm("Delete this preference from Jenni AI's memory?")) {
    await apiFetch(`/api/memory/${id}`, { method: "DELETE" });
    loadMemories();
  }
}

// --- File Search ---
function setupFileSearchHandlers() {
  const searchBtn = document.getElementById("execute-file-search-btn");
  const queryInput = document.getElementById("file-search-input");
  const extInput = document.getElementById("file-ext-input");

  async function performSearch() {
    const query = queryInput.value.trim();
    const ext = extInput.value.trim();
    const container = document.getElementById("file-results");

    container.innerHTML = `<div class="empty-state">Searching approved folders...</div>`;

    try {
      const res = await apiFetch(`/api/files/search?query=${encodeURIComponent(query)}&extension=${encodeURIComponent(ext)}`);
      if (res.ok) {
        const files = await res.json();
        if (files.length === 0) {
          container.innerHTML = `<div class="empty-state">No matching files found in approved directories.</div>`;
          return;
        }

        container.innerHTML = files.map(f => `
          <div class="file-item">
            <div class="file-info">
              <strong>${f.name}</strong>
              <span>${f.path} (${f.size_kb} KB)</span>
            </div>
            <div class="file-actions">
              <button class="sm-btn" onclick="openFile('${encodeURIComponent(f.path)}', false)">Open</button>
              <button class="sm-btn" onclick="openFile('${encodeURIComponent(f.path)}', true)">Reveal</button>
            </div>
          </div>
        `).join("");
      }
    } catch (e) {
      container.innerHTML = `<div class="empty-state">Error during file search: ${e.message}</div>`;
    }
  }

  if (searchBtn) searchBtn.addEventListener("click", performSearch);
  if (queryInput) {
    queryInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") performSearch();
    });
  }
}

async function openFile(encodedPath, reveal) {
  const path = decodeURIComponent(encodedPath);
  try {
    const res = await apiFetch("/api/files/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, reveal })
    });
    const d = await res.json();
    alert(d.message || d.detail || "File operation complete.");
  } catch (e) {
    alert("Error opening file: " + e.message);
  }
}

// --- Image Studio ---
function setupImageStudioHandlers() {
  const genBtn = document.getElementById("generate-image-btn");
  const promptInput = document.getElementById("image-prompt");
  const ratioSelect = document.getElementById("image-ratio");

  if (genBtn) {
    genBtn.addEventListener("click", async () => {
      const prompt = promptInput.value.trim();
      if (!prompt) {
        alert("Please enter a visual prompt for Jenni AI.");
        return;
      }

      genBtn.disabled = true;
      genBtn.innerHTML = `<span>Synthesizing Artwork...</span>`;

      const [w, h] = ratioSelect.value.split("x").map(Number);

      try {
        const res = await apiFetch("/api/images/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, width: w, height: h })
        });
        const d = await res.json();
        if (!res.ok) {
          alert(d.detail || d.message || "Image generation failed.");
          return;
        }
        await loadImages();
        if (d.url) {
          openImageModal(d.url, d.filename || "jenni_ai.png");
        }
      } catch (e) {
        alert("Image generation failed: " + (e.message || "Server offline."));
      } finally {
        genBtn.disabled = false;
        genBtn.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          <span>Generate Artwork</span>
        `;
      }
    });
  }
}

async function loadImages() {
  try {
    const res = await apiFetch("/api/images/list");
    if (res.ok) {
      const imgs = await res.json();
      const container = document.getElementById("image-gallery");
      if (!container) return;

      if (imgs.length === 0) {
        container.innerHTML = `<div class="empty-state" style="grid-column: 1/-1;">No images generated yet. Create one on the left!</div>`;
        return;
      }

      container.innerHTML = imgs.map(img => `
        <div class="gallery-card" onclick="openImageModal('${img.url}', '${img.filename}')">
          <img src="${img.url}" alt="${img.filename}" loading="lazy">
        </div>
      `).join("");
    }

    // Check ComfyUI status
    const comfyRes = await apiFetch("/api/images/status");
    if (comfyRes.ok) {
      const cd = await comfyRes.json();
      const dot = document.getElementById("comfy-dot");
      const text = document.getElementById("comfy-status-text");
      const rec = document.getElementById("gpu-rec-text");

      if (dot && text) {
        if (cd.online) {
          dot.className = "status-dot online";
          text.textContent = "ComfyUI: Connected (SD 1.5 Ready)";
        } else {
          dot.className = "status-dot warning";
          text.textContent = "ComfyUI: Offline (Visual Synth Fallback Active)";
        }
      }
      if (rec && cd.gpu) {
        rec.textContent = `Hardware: ${cd.gpu.model} (${cd.gpu.total_vram_mb} MB VRAM). ${cd.gpu.recommendation}`;
      }
    }
  } catch (e) {}
}

function openImageModal(url, filename) {
  const modal = document.getElementById("image-modal");
  const imgPreview = document.getElementById("modal-image-preview");
  const nameLabel = document.getElementById("modal-image-name");
  const downloadBtn = document.getElementById("modal-image-download");

  if (modal && imgPreview) {
    imgPreview.src = url;
    if (nameLabel) nameLabel.textContent = filename;
    if (downloadBtn) downloadBtn.href = url;
    modal.classList.remove("hidden");
  }
}

// --- Automations & Tasks ---
async function loadWorkflows() {
  try {
    const res = await apiFetch("/api/tasks/workflows");
    if (res.ok) {
      const workflows = await res.json();
      const container = document.getElementById("workflows-container");
      if (!container) return;

      container.innerHTML = workflows.map(wf => `
        <div class="workflow-card">
          <div class="workflow-info">
            <h4>${wf.title}</h4>
            <p>${wf.description}</p>
          </div>
          <div class="workflow-steps-preview">
            ${wf.steps.map(s => `<div>• Step ${s.id}: ${s.name}</div>`).join("")}
          </div>
          <button class="btn primary" onclick="runWorkflow('${wf.id}')">Run Workflow</button>
        </div>
      `).join("");
    }
    loadTaskHistory();
  } catch (e) {}
}

async function runWorkflow(workflowId) {
  try {
    const res = await apiFetch("/api/tasks/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_id: workflowId })
    });
    const d = await res.json();
    if (!res.ok) {
      alert(d.detail || d.message || "Could not start workflow");
      return;
    }
    alert(d.message || "Workflow completed");
    loadTaskHistory();
  } catch (e) {
    alert("Could not start workflow: " + (e.message || "Server offline"));
  }
}

async function loadTaskHistory() {
  try {
    const res = await apiFetch("/api/tasks/history");
    if (res.ok) {
      const list = await res.json();
      const container = document.getElementById("task-history-list");
      if (!container) return;

      if (list.length === 0) {
        container.innerHTML = `<div class="empty-state">No workflow history recorded.</div>`;
        return;
      }

      container.innerHTML = list.map(t => `
        <div class="task-history-item">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <strong>${t.title}</strong>
            <span style="color: ${t.status === 'completed' ? '#10b981' : t.status === 'running' ? '#38bdf8' : '#f59e0b'};">${t.status.toUpperCase()}</span>
          </div>
          <div style="font-size: 0.85rem; color: #94a3b8;">
            ${(t.steps || []).map(s => `<div>✓ ${s.name}: ${s.result || s.status}</div>`).join("")}
          </div>
        </div>
      `).join("");
    }
  } catch (e) {}
}

// --- Android Connect & Mobile Info ---
async function loadMobileInfo() {
  try {
    const res = await apiFetch("/api/mobile/info");
    if (res.ok) {
      const data = await res.json();
      const urlBox = document.getElementById("mobile-connect-urls");
      if (urlBox && data.connection_urls) {
        urlBox.innerHTML = data.connection_urls.map(u => `<div>🔗 <a href="${u}" target="_blank" style="color: #38bdf8;">${u}</a></div>`).join("");
      }

      const taskerBox = document.getElementById("tasker-preview");
      if (taskerBox && data.token) {
        taskerBox.textContent = `Method: POST\nURL: http://<PC_TAILSCALE_IP>:8000/api/chat\nHeaders:\n  Content-Type: application/json\n  Authorization: Bearer <YOUR_SESSION_TOKEN>\nBody:\n  {"message": "%VOICE_INPUT"}`;
      }
    }
  } catch (e) {}
}

// --- Modals Setup ---
function setupModals() {
  const confirmModal = document.getElementById("confirmation-modal");
  const approveBtn = document.getElementById("modal-approve-btn");
  const rejectBtn = document.getElementById("modal-reject-btn");

  const imageModal = document.getElementById("image-modal");
  const closeImageModalBtn = document.getElementById("close-image-modal");

  if (approveBtn) {
    approveBtn.addEventListener("click", async () => {
      if (activeConfirmationId) {
        await resolveConfirmation(activeConfirmationId, true);
        confirmModal.classList.add("hidden");
        activeConfirmationId = null;
      }
    });
  }

  if (rejectBtn) {
    rejectBtn.addEventListener("click", async () => {
      if (activeConfirmationId) {
        await resolveConfirmation(activeConfirmationId, false);
        confirmModal.classList.add("hidden");
        activeConfirmationId = null;
      }
    });
  }

  if (closeImageModalBtn && imageModal) {
    closeImageModalBtn.addEventListener("click", () => {
      imageModal.classList.add("hidden");
    });
    imageModal.addEventListener("click", (e) => {
      if (e.target === imageModal) imageModal.classList.add("hidden");
    });
  }
}

function showConfirmationModal(confirmationId, description) {
  activeConfirmationId = confirmationId;
  const modal = document.getElementById("confirmation-modal");
  const desc = document.getElementById("modal-confirm-desc");
  if (modal && desc) {
    desc.textContent = description;
    modal.classList.remove("hidden");
  }
}

async function resolveConfirmation(confirmationId, approved) {
  try {
    const res = await apiFetch("/api/pc/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_id: confirmationId, approved })
    });
    const d = await res.json();
    alert(d.message || d.detail || "Confirmation processed.");
  } catch (e) {
    alert("Error resolving confirmation: " + (e.message || "Server offline"));
  }
}
