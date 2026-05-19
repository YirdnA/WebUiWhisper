// Typed-confirmation modal for deleting archived transcripts.
//
// Server-side also re-validates the typed `confirm` value against the
// stem — this JS just gates the Submit button so the user can't fire
// the request without typing the right text. Bypassing the JS is fine;
// the server will 400.

(function () {
  function init() {
    const modal = document.getElementById("delete-modal");
    if (!modal) return;
    const form = document.getElementById("delete-form");
    const input = document.getElementById("delete-confirm");
    const submit = document.getElementById("delete-submit");
    const cancel = document.getElementById("delete-cancel");
    const stemHint = document.getElementById("delete-stem-hint");
    const displayCode = document.getElementById("delete-display");
    let currentStem = "";

    function open(name, stem, display) {
      currentStem = stem;
      stemHint.textContent = stem;
      displayCode.textContent = display || name;
      input.value = "";
      submit.disabled = true;
      form.action = "/transcripts/" + encodeURIComponent(name) + "/delete";
      if (typeof modal.showModal === "function") {
        modal.showModal();
      } else {
        modal.setAttribute("open", "");
      }
      setTimeout(function () { input.focus(); }, 30);
    }

    function close() {
      if (typeof modal.close === "function") {
        modal.close();
      } else {
        modal.removeAttribute("open");
      }
    }

    input.addEventListener("input", function () {
      submit.disabled = input.value.trim() !== currentStem;
    });

    cancel.addEventListener("click", function (ev) {
      ev.preventDefault();
      close();
    });

    // Re-validate on submit, in case a user bypasses the disabled flag.
    form.addEventListener("submit", function (ev) {
      if (input.value.trim() !== currentStem) {
        ev.preventDefault();
        input.focus();
      }
    });

    document.querySelectorAll(".delete-trigger").forEach(function (btn) {
      btn.addEventListener("click", function () {
        open(
          btn.dataset.name,
          btn.dataset.stem,
          btn.dataset.display
        );
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
