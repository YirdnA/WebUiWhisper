// Bulk action bar: enables/disables buttons based on selection;
// asks confirmation before destructive actions; sets the hidden action field.

(function () {
  function init() {
    const form = document.getElementById("bulk-form");
    if (!form) return;
    const bar = document.getElementById("bulk-bar");
    const countEl = document.getElementById("bulk-count");
    const actionField = document.getElementById("bulk-action");
    const checkAll = document.getElementById("bulk-check-all");
    const checkboxes = Array.from(form.querySelectorAll(".bulk-check"));

    function selected() {
      return checkboxes.filter(function (c) { return c.checked; });
    }
    function refresh() {
      const n = selected().length;
      if (countEl) countEl.textContent = String(n);
      if (bar) bar.hidden = n === 0;
    }

    checkboxes.forEach(function (c) {
      c.addEventListener("change", refresh);
    });
    if (checkAll) {
      checkAll.addEventListener("change", function () {
        checkboxes.forEach(function (c) { c.checked = checkAll.checked; });
        refresh();
      });
    }

    form.querySelectorAll("[data-bulk-action]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        const action = btn.dataset.bulkAction;
        const n = selected().length;
        if (n === 0) return;
        const verb = action === "delete" ? "DELETE" : "archive";
        const msg = verb + " " + n + " transcript" + (n === 1 ? "" : "s") +
                    (action === "delete" ? " AND associated audio backups? This cannot be undone." : "?");
        if (!confirm(msg)) return;
        if (actionField) actionField.value = action;
        form.submit();
      });
    });

    refresh();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
