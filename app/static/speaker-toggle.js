// Speaker toggle on the transcript detail view.
//   - Each .speaker-toggle button hides/shows its speaker's .seg-item rows.
//   - Hidden-speakers set persists in localStorage under
//     `webui:hidden-speakers:{name}` so reloading keeps the same view.
//   - "Show all" clears the set.
//   - Download buttons get a `?hide=A,B,...` query string mirroring the
//     active set, plus a "(filtered)" indicator.

(function () {
  const STORAGE_PREFIX = "webui:hidden-speakers:";

  function init() {
    const bar = document.getElementById("speaker-toggle-bar");
    if (!bar) return;

    const name = bar.dataset.name || "";
    const storageKey = STORAGE_PREFIX + name;
    const checkboxes = Array.from(bar.querySelectorAll(".speaker-toggle-input[data-speaker]"));
    const showAllBtn = document.getElementById("speaker-show-all");
    const segItems = Array.from(document.querySelectorAll(".seg-item[data-speaker]"));
    const downloadLinks = Array.from(document.querySelectorAll("a[data-download]"));

    // Snapshot each download link's clean base URL once.
    downloadLinks.forEach(function (a) {
      if (!a.dataset.baseHref) {
        a.dataset.baseHref = a.getAttribute("href");
      }
    });

    function loadHidden() {
      try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return new Set();
        const arr = JSON.parse(raw);
        return new Set(Array.isArray(arr) ? arr : []);
      } catch (e) {
        return new Set();
      }
    }

    function saveHidden(set) {
      try {
        if (set.size === 0) {
          localStorage.removeItem(storageKey);
        } else {
          localStorage.setItem(storageKey, JSON.stringify(Array.from(set).sort()));
        }
      } catch (e) {
        // Storage full / disabled — UX still works, just doesn't persist.
      }
    }

    function apply(set) {
      // Checkboxes: checked = visible, unchecked = hidden.
      checkboxes.forEach(function (cb) {
        const off = set.has(cb.dataset.speaker);
        cb.checked = !off;
        const label = cb.closest(".speaker-toggle");
        if (label) label.classList.toggle("off", off);
      });
      // Segments
      segItems.forEach(function (li) {
        li.hidden = set.has(li.dataset.speaker);
      });
      // Downloads
      const hideParam = Array.from(set).sort().map(encodeURIComponent).join(",");
      downloadLinks.forEach(function (a) {
        const base = a.dataset.baseHref;
        a.setAttribute("href", hideParam ? base + "?hide=" + hideParam : base);
        // Indicator
        let badge = a.querySelector(".filter-indicator");
        if (hideParam) {
          if (!badge) {
            badge = document.createElement("span");
            badge.className = "filter-indicator";
            badge.textContent = "(filtered)";
            a.appendChild(document.createTextNode(" "));
            a.appendChild(badge);
          }
        } else if (badge) {
          // Also drop any preceding whitespace text node we added.
          const prev = badge.previousSibling;
          if (prev && prev.nodeType === Node.TEXT_NODE && /^\s+$/.test(prev.nodeValue)) {
            prev.remove();
          }
          badge.remove();
        }
      });
    }

    let hidden = loadHidden();
    apply(hidden);

    checkboxes.forEach(function (cb) {
      cb.addEventListener("change", function () {
        const spk = cb.dataset.speaker;
        if (cb.checked) hidden.delete(spk); else hidden.add(spk);
        saveHidden(hidden);
        apply(hidden);
      });
    });

    if (showAllBtn) {
      showAllBtn.addEventListener("click", function () {
        hidden.clear();
        saveHidden(hidden);
        apply(hidden);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
