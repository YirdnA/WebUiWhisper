// Live progress banner: connects to /progress/stream (SSE) and appends log
// lines tagged by phase (transcribe / diarize / merge / done / info / error).
//
// Auto-reconnects via the browser's native EventSource backoff.

(function () {
  function init() {
    const root = document.getElementById("ww-progress");
    if (!root) return;
    const logEl = root.querySelector(".progress-log");
    const phaseEl = root.querySelector(".progress-phase");
    if (!logEl || !phaseEl) return;

    const MAX_LINES = 80;
    const lines = [];

    function setPhase(phase) {
      phaseEl.textContent = phase || "idle";
      phaseEl.dataset.phase = phase || "";
    }

    function append(rec) {
      const div = document.createElement("div");
      div.className = "log-line";
      if (rec.phase) div.dataset.phase = rec.phase;
      div.textContent = rec.text;
      logEl.appendChild(div);
      lines.push(div);
      while (lines.length > MAX_LINES) {
        const old = lines.shift();
        if (old && old.parentNode) old.parentNode.removeChild(old);
      }
      logEl.scrollTop = logEl.scrollHeight;
      if (rec.phase) setPhase(rec.phase);
    }

    const es = new EventSource("/progress/stream");
    es.addEventListener("hello", function () {
      setPhase("idle");
    });
    es.addEventListener("log", function (ev) {
      try {
        append(JSON.parse(ev.data));
      } catch (e) { /* ignore malformed */ }
    });
    es.addEventListener("error", function () {
      setPhase("disconnected");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
