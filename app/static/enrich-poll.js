// While an enrich job is in flight, poll the sidecar endpoint every 5s
// and reload the page when results land. Polling stops on visibilitychange
// to avoid hammering when the tab is hidden.

(function () {
  function init() {
    const u = new URLSearchParams(window.location.search);
    if (u.get("enrich") !== "queued") return;
    const box = document.querySelector(".enrich-box");
    if (!box) return;
    const name = box.dataset.name;
    if (!name) return;

    const url = "/transcripts/" + encodeURIComponent(name) + "/enrich.json";
    let stopped = false;

    function tick() {
      if (stopped) return;
      if (document.hidden) {
        setTimeout(tick, 5000);
        return;
      }
      fetch(url, { headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (data && data.ran_at) {
            stopped = true;
            const newUrl = window.location.pathname;
            window.location.replace(newUrl);
            return;
          }
          setTimeout(tick, 5000);
        })
        .catch(function () { setTimeout(tick, 5000); });
    }

    setTimeout(tick, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
