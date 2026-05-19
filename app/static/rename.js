// Rename UI on the transcript detail page.
// - ✎ swaps the H2 for an inline rename form.
// - ✨ POSTs to /display-name/auto, pre-fills the input with the
//   suggested title, and focuses the input for the user to confirm.
// - Save (form submit) POSTs the new name and reloads.
// - Reset fetch DELETE-s the sidecar and reloads.
//
// CSRF is read from the hidden field embedded in the form.

(function () {
  function init() {
    const target = document.querySelector(".rename-target");
    if (!target) return;
    const display = target.querySelector(".rename-display");
    const editBtn = target.querySelector(".rename-edit");
    const autoBtn = target.querySelector(".rename-auto");
    const form = document.querySelector(".rename-form");
    if (!form) return;
    const input = form.querySelector("input[name='display_name']");
    const cancelBtn = form.querySelector(".rename-cancel");
    const resetBtn = form.querySelector(".rename-reset");
    const csrf = form.querySelector("input[name]").value;
    const name = target.dataset.name;

    function openForm(prefill) {
      target.hidden = true;
      form.hidden = false;
      if (typeof prefill === "string") input.value = prefill;
      input.focus();
      input.select();
    }
    function closeForm() {
      form.hidden = true;
      target.hidden = false;
    }

    if (editBtn) {
      editBtn.addEventListener("click", function () {
        openForm();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        closeForm();
      });
    }

    if (autoBtn) {
      autoBtn.addEventListener("click", async function (ev) {
        ev.preventDefault();
        autoBtn.disabled = true;
        const original = autoBtn.textContent;
        autoBtn.textContent = "…";
        try {
          const fd = new FormData();
          fd.append("csrf_token", csrf);
          const r = await fetch(
            "/transcripts/" + encodeURIComponent(name) + "/display-name/auto",
            { method: "POST", body: fd, credentials: "same-origin" }
          );
          const data = await r.json();
          if (data.title) {
            openForm(data.title);
          } else if (data.error) {
            alert("Auto-name failed: " + data.error);
          } else {
            alert("Auto-name returned no title (Ollama may be unreachable).");
          }
        } catch (err) {
          alert("Auto-name request failed: " + err);
        } finally {
          autoBtn.disabled = false;
          autoBtn.textContent = original;
        }
      });
    }

    if (resetBtn) {
      resetBtn.addEventListener("click", async function (ev) {
        ev.preventDefault();
        if (!confirm("Reset display name to the default?")) return;
        const fd = new FormData();
        fd.append("csrf_token", csrf);
        await fetch(
          "/transcripts/" + encodeURIComponent(name) + "/display-name",
          { method: "DELETE", body: fd, credentials: "same-origin" }
        );
        window.location.reload();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
