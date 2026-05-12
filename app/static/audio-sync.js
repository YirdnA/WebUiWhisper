// Audio <-> transcript segment sync.
// Wires #ww-audio to a list of .seg-item elements carrying data-start / data-end.
//   - Click a segment => seek audio there.
//   - Audio time update => mark the active segment, scroll it into view.

(function () {
  function init() {
    const audio = document.getElementById("ww-audio");
    if (!audio) return;

    // Hide the player if the source 404s (audio outside the 6-day window).
    audio.addEventListener("error", function () {
      audio.hidden = true;
      const missing = document.getElementById("audio-missing");
      if (missing) missing.hidden = false;
    });

    const segs = Array.from(document.querySelectorAll(".seg-item[data-start]"));
    if (segs.length === 0) return;

    const items = segs.map(function (el) {
      return {
        el: el,
        start: parseFloat(el.dataset.start || "0"),
        end: parseFloat(el.dataset.end || "0"),
      };
    });

    let active = null;
    let userScrolledRecently = 0;

    function setActive(idx) {
      if (active === idx) return;
      if (active !== null && items[active]) {
        items[active].el.classList.remove("playing");
      }
      active = idx;
      if (idx !== null && items[idx]) {
        items[idx].el.classList.add("playing");
        // Scroll only if the user hasn't manually scrolled in the last 3 s.
        if (Date.now() - userScrolledRecently > 3000) {
          items[idx].el.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }
    }

    function findIndexAt(t) {
      // Linear scan is fine for a few hundred segments; binary search if needed.
      for (let i = 0; i < items.length; i++) {
        if (t >= items[i].start && t < items[i].end) return i;
      }
      return null;
    }

    audio.addEventListener("timeupdate", function () {
      setActive(findIndexAt(audio.currentTime));
    });

    audio.addEventListener("ended", function () {
      setActive(null);
    });

    document.addEventListener("scroll", function () {
      userScrolledRecently = Date.now();
    }, { passive: true });

    segs.forEach(function (el, idx) {
      el.addEventListener("click", function (ev) {
        // Don't hijack clicks on links inside the segment.
        if (ev.target.closest("a")) return;
        audio.currentTime = items[idx].start;
        if (audio.paused) {
          audio.play().catch(function () { /* autoplay block — fine */ });
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
