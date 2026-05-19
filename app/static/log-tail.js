// Live log tail via SSE. Mirrors the style of audio-sync.js / progress.js.
// Reads `data-file` from #log-tail; opens EventSource at /logs/{file}/stream.
// Auto-scrolls to bottom unless the user has scrolled up.
// Pauses on tab hide to keep the server quiet when nobody's watching.

(function () {
  const MAX_LINES = 5000;
  const STICK_THRESHOLD_PX = 50;

  function init() {
    const wrap = document.getElementById("log-tail");
    if (!wrap) return;
    const file = wrap.dataset.file;
    if (!file) return;
    const out = document.getElementById("log");
    if (!out) return;

    let source = null;

    function isStuckToBottom() {
      const dist = out.scrollHeight - out.scrollTop - out.clientHeight;
      return dist <= STICK_THRESHOLD_PX;
    }

    function append(text, phase) {
      const stick = isStuckToBottom();
      const div = document.createElement("div");
      div.className = "log-line" + (phase ? " phase-" + phase : "");
      div.textContent = text;
      out.appendChild(div);
      // Trim oldest if we're past the cap.
      while (out.childNodes.length > MAX_LINES) {
        out.removeChild(out.firstChild);
      }
      if (stick) out.scrollTop = out.scrollHeight;
    }

    function open() {
      if (source) return;
      source = new EventSource("/logs/" + encodeURIComponent(file) + "/stream");
      source.addEventListener("hello", function (ev) {
        try {
          const j = JSON.parse(ev.data);
          append("--- streaming " + (j.file || file) + " ---", "info");
        } catch (e) { /* ignore */ }
      });
      source.addEventListener("log", function (ev) {
        try {
          const j = JSON.parse(ev.data);
          append(j.text || "", j.phase || "");
        } catch (e) { /* ignore */ }
      });
      source.addEventListener("error", function () {
        // EventSource auto-reconnects; nothing to do.
      });
    }

    function close() {
      if (!source) return;
      source.close();
      source = null;
    }

    open();

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) close(); else open();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
