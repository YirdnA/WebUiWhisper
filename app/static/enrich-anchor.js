// Click-to-seek for enrichment anchors and the timecode toggle switch.

(function () {
  function init() {
    const audio = document.getElementById("ww-audio");
    if (audio) {
      document.addEventListener("click", function (ev) {
        const btn = ev.target.closest(".enrich-anchor");
        if (!btn) return;
        const sec = parseFloat(btn.dataset.anchor || "0");
        if (isNaN(sec) || sec < 0) return;
        audio.currentTime = sec;
        if (audio.paused) {
          audio.play().catch(function () { /* autoplay block — fine */ });
        }
      });
    }

    // Timecode toggle — flips visibility on .enrich-ts-mark spans.
    const ts = document.getElementById("enrich-ts");
    if (ts) {
      function apply() {
        document.querySelectorAll(".enrich-ts-mark").forEach(function (el) {
          el.hidden = !ts.checked;
        });
      }
      ts.addEventListener("change", apply);
      apply();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
