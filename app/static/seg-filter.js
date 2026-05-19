// In-page segment filter — hides .seg-item rows whose text doesn't match.

(function () {
  function init() {
    const input = document.getElementById("seg-filter");
    if (!input) return;
    const items = Array.from(document.querySelectorAll(".seg-item"));
    if (!items.length) return;

    let timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(apply, 80);
    });

    function apply() {
      const q = input.value.trim().toLowerCase();
      items.forEach(function (it) {
        if (!q) {
          it.hidden = false;
          return;
        }
        const text = (it.textContent || "").toLowerCase();
        it.hidden = !text.includes(q);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
