const els = {
  status: document.getElementById("status"),
  token: document.getElementById("token"),
  session: document.getElementById("session"),
  mode: document.getElementById("mode"),
  savePrefs: document.getElementById("save-prefs"),
  chat: document.getElementById("chat-log"),
  prompt: document.getElementById("prompt"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  composer: document.getElementById("composer"),
};

const state = {
  controller: null,
  sessionId: null,
};

function setStatus(text, tone = "info") {
  els.status.textContent = text;
  els.status.dataset.tone = tone;
}

function persistPrefs() {
  if (els.token.value) {
    localStorage.setItem("argo_web_token", els.token.value);
  }
  if (els.session.value) {
    localStorage.setItem("argo_web_session", els.session.value);
  }
  localStorage.setItem("argo_web_mode", els.mode.value);
  setStatus("Prefs saved", "info");
  setTimeout(() => setStatus("Idle"), 800);
}

function loadPrefs() {
  const savedToken = localStorage.getItem("argo_web_token");
  if (savedToken) {
    els.token.value = savedToken;
  }
  const savedSession = localStorage.getItem("argo_web_session");
  if (savedSession) {
    els.session.value = savedSession;
    state.sessionId = savedSession;
  }
  const savedMode = localStorage.getItem("argo_web_mode");
  if (savedMode) {
    els.mode.value = savedMode;
  }
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  els.chat.appendChild(div);
  els.chat.scrollTop = els.chat.scrollHeight;
}

function resetComposer() {
  els.prompt.value = "";
  els.send.disabled = false;
  els.stop.disabled = true;
  state.controller = null;
}

function ensureSessionId() {
  if (els.session.value.trim()) {
    state.sessionId = els.session.value.trim();
    return state.sessionId;
  }
  if (!state.sessionId) {
    state.sessionId = Math.random().toString(16).slice(2, 10);
    els.session.value = state.sessionId;
  }
  return state.sessionId;
}

function parseSseChunk(chunk) {
  const lines = chunk.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.replace("event:", "").trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.replace("data:", "").trim());
    }
  }
  const data = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};
  return { event, data };
}

async function streamChat(message) {
  const sessionId = ensureSessionId();
  const token = els.token.value.trim();
  const payload = {
    message,
    session_id: sessionId,
    mode: els.mode.value,
  };

  setStatus("Talking to Argo…", "warn");
  els.send.disabled = true;
  els.stop.disabled = false;

  const controller = new AbortController();
  state.controller = controller;

  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch("/chat/stream", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal: controller.signal,
  });

  if (!response.ok || !response.body) {
    const msg = await response.text();
    setStatus("Error", "error");
    addMessage("system", `Request failed: ${msg || response.status}`);
    resetComposer();
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (!chunk.trim()) continue;
        const { event, data } = parseSseChunk(chunk);
        if (event === "session" && data.session_id) {
          state.sessionId = data.session_id;
          els.session.value = data.session_id;
          localStorage.setItem("argo_web_session", data.session_id);
        }
        if (event === "message" && data.text) {
          addMessage("assistant", data.text);
        }
        if (event === "error") {
          addMessage("system", data.message || "Unknown error");
          setStatus("Error", "error");
        }
        if (event === "done") {
          sawDone = true;
        }
      }
    }
  } catch (err) {
    if (controller.signal.aborted) {
      addMessage("system", "Generation stopped.");
      setStatus("Stopped", "warn");
    } else {
      addMessage("system", `Stream error: ${err.message}`);
      setStatus("Error", "error");
    }
  }

  resetComposer();
  if (!controller.signal.aborted && sawDone) {
    setStatus("Idle", "info");
  } else if (controller.signal.aborted) {
    setTimeout(() => setStatus("Idle", "info"), 800);
  }
}

els.savePrefs.addEventListener("click", persistPrefs);
els.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = els.prompt.value.trim();
  if (!message) return;
  addMessage("user", message);
  els.prompt.value = "";
  await streamChat(message);
});
els.stop.addEventListener("click", () => {
  if (state.controller) {
    state.controller.abort();
  }
});

loadPrefs();
setStatus("Idle", "info");
