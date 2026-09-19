/*
 * Knowledge OS Reader — hand-written client script (Sec.7: "roughly 50
 * lines of vanilla JavaScript ... no SPA router, no node toolchain").
 *
 * Progressive enhancement only: every behaviour here degrades to "does
 * nothing" without breaking the page. `templates/document.html` is the only
 * template that currently loads this file.
 *
 * - Rail toggle: a manual desktop switch for single-column deep reading
 *   (Sec.5), remembered across page loads. The <900px responsive collapse
 *   is a separate, script-free <details> in base.html and is untouched by
 *   this.
 * - Rail-to-table-of-contents swap: for a document with headings, the rail
 *   shows metadata first and swaps to a table of contents once the reader
 *   scrolls past the title (Sec.6 "Long document").
 */
(function () {
  "use strict";

  var RAIL_HIDDEN_KEY = "kos-read:rail-hidden";

  function initRailToggle() {
    var button = document.querySelector("[data-rail-toggle]");
    if (!button) return;

    function apply(hidden) {
      document.body.classList.toggle("rail-hidden", hidden);
      button.setAttribute("aria-pressed", String(hidden));
      button.textContent = hidden ? button.dataset.showLabel : button.dataset.hideLabel;
    }

    var hidden = false;
    try {
      hidden = window.localStorage.getItem(RAIL_HIDDEN_KEY) === "1";
    } catch (error) {
      /* localStorage may be unavailable (private mode, disabled storage). */
    }
    apply(hidden);

    button.addEventListener("click", function () {
      hidden = !document.body.classList.contains("rail-hidden");
      apply(hidden);
      try {
        window.localStorage.setItem(RAIL_HIDDEN_KEY, hidden ? "1" : "0");
      } catch (error) {
        /* Ignore: the toggle still works for this page view. */
      }
    });
  }

  function initRailToc() {
    var sentinel = document.querySelector("[data-rail-sentinel]");
    if (!sentinel || !("IntersectionObserver" in window)) return;
    var observer = new IntersectionObserver(
      function (entries) {
        var entry = entries[0];
        var scrolledPast = Boolean(entry) && entry.boundingClientRect.top < 0;
        document.body.classList.toggle("rail-toc-active", scrolledPast);
      },
      { threshold: 0 }
    );
    observer.observe(sentinel);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initRailToggle();
    initRailToc();
  });
})();
