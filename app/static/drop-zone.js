// Drag-and-drop overlay for the upload page.

(function () {
  function init() {
    const zone = document.getElementById("drop-zone");
    const input = document.getElementById("audio-file");
    if (!zone || !input) return;

    function show(text) {
      const span = zone.querySelector(".drop-zone-text");
      if (span) span.textContent = text;
    }
    input.addEventListener("change", function () {
      const f = input.files && input.files[0];
      if (f) show("Selected: " + f.name + " (" + Math.round(f.size / 1024) + " KB)");
    });

    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) {
        e.preventDefault();
        zone.classList.remove("dragover");
      });
    });

    zone.addEventListener("drop", function (e) {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length > 0) {
        input.files = dt.files;
        const f = dt.files[0];
        show("Selected: " + f.name + " (" + Math.round(f.size / 1024) + " KB)");
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
