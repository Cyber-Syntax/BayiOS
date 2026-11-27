(function () {
  "use strict";

  function enhance(container) {
    if (!container || container.dataset.scrollEnhanced === "true") return;
    container.dataset.scrollEnhanced = "true";

    var shell = document.createElement("div");
    shell.className = "table-scroll-shell";
    container.parentNode.insertBefore(shell, container);
    shell.appendChild(container);
    container.classList.add("table-scroll-area");

    var hint = document.createElement("div");
    hint.className = "table-scroll-hint";
    hint.setAttribute("aria-hidden", "true");
    hint.innerHTML = "<span>&larr; Yatay kaydır &rarr;</span><span class=\"table-scroll-hint-arrows\">&harr;</span>";

    var bar = document.createElement("div");
    bar.className = "table-scroll-bar";
    bar.setAttribute("aria-hidden", "true");
    var track = document.createElement("div");
    track.className = "table-scroll-track";
    bar.appendChild(track);

    shell.insertBefore(hint, container);
    shell.appendChild(bar);

    function sync() {
      var max = container.scrollWidth - container.clientWidth;
      var scrollable = max > 2;
      shell.classList.toggle("is-scrollable", scrollable);
      if (!scrollable) {
        track.style.width = "0px";
        return;
      }
      track.style.width = container.scrollWidth + "px";
      bar.scrollLeft = container.scrollLeft;
    }

    container.addEventListener("scroll", function () {
      bar.scrollLeft = container.scrollLeft;
    });
    bar.addEventListener("scroll", function () {
      container.scrollLeft = bar.scrollLeft;
    });

    if (window.ResizeObserver) {
      var observer = new ResizeObserver(sync);
      observer.observe(container);
      Array.prototype.forEach.call(container.children, function (child) {
        observer.observe(child);
      });
    }
    window.addEventListener("resize", sync);
    window.addEventListener("load", sync);
    sync();
  }

  function initAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-table-scroll]").forEach(enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll(document);
    });
  } else {
    initAll(document);
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    initAll(event.target);
  });
})();
