(function () {
  "use strict";

  var TURKISH_MONTHS = [
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
  ];

  var openInstance = null;

  function formatLongDate(iso) {
    if (!iso) return "";
    var parts = iso.split("-");
    if (parts.length !== 3) return "";
    var year = Number(parts[0]);
    var month = Number(parts[1]);
    var day = Number(parts[2]);
    if (!year || !month || day === 0 || Number.isNaN(day) || !TURKISH_MONTHS[month - 1]) {
      return "";
    }
    return day + " " + TURKISH_MONTHS[month - 1] + " " + year;
  }

  function updatePreview(input, isoValue) {
    var targetId = input.getAttribute("data-date-preview");
    if (!targetId) return;
    var target = document.getElementById(targetId);
    if (!target) return;
    target.textContent = formatLongDate(isoValue);
  }

  function addQuickButtons(instance) {
    var container = instance.calendarContainer;
    if (!container || container.querySelector(".flatpickr-tr-actions")) return;

    var actions = document.createElement("div");
    actions.className = "flatpickr-tr-actions no-print";

    var todayButton = document.createElement("button");
    todayButton.type = "button";
    todayButton.className = "flatpickr-tr-action";
    todayButton.textContent = "Bugün";
    todayButton.addEventListener("click", function (event) {
      event.preventDefault();
      instance.setDate(new Date(), true, "Y-m-d");
      instance.close();
    });

    var clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "flatpickr-tr-action";
    clearButton.textContent = "Temizle";
    clearButton.addEventListener("click", function (event) {
      event.preventDefault();
      instance.clear();
      instance.close();
    });

    actions.appendChild(todayButton);
    actions.appendChild(clearButton);
    container.appendChild(actions);
  }

  function relabelInput(input, altInput) {
    if (!altInput) return;
    if (input.id) {
      var label = document.querySelector('label[for="' + input.id + '"]');
      altInput.id = input.id;
      input.removeAttribute("id");
      if (label) label.setAttribute("for", altInput.id);
    }
    altInput.classList.add("form-control");
    if (input.getAttribute("aria-label")) {
      altInput.setAttribute("aria-label", input.getAttribute("aria-label"));
    }
    var placeholder = input.getAttribute("placeholder");
    if (placeholder) {
      altInput.placeholder = placeholder;
    }
    if (input.required) {
      input.required = false;
      altInput.required = true;
    }
  }

  function initPicker(input) {
    if (!window.flatpickr || input.dataset.pickerReady === "true") return;

    var initialValue = input.value;
    var instance = window.flatpickr(input, {
      locale: "tr",
      dateFormat: "Y-m-d",
      altInput: true,
      altFormat: "d.m.Y",
      altInputClass: "form-control",
      firstDayOfWeek: 1,
      allowInput: true,
      disableMobile: true,
      monthSelectorType: "static",
      onChange: function (_selectedDates, dateStr) {
        updatePreview(input, dateStr);
      },
      onValueUpdate: function (_selectedDates, dateStr) {
        updatePreview(input, dateStr);
      },
      onReady: function (_selectedDates, dateStr, fp) {
        relabelInput(input, fp.altInput);
        addQuickButtons(fp);
        updatePreview(input, dateStr || initialValue);
      },
      onOpen: function (_selectedDates, _dateStr, fp) {
        openInstance = fp;
        addQuickButtons(fp);
      },
      onClose: function () {
        openInstance = null;
      },
    });

    input.dataset.pickerReady = "true";
    updatePreview(input, initialValue);
  }

  function initAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-date-picker]").forEach(initPicker);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll(document);
    });
  } else {
    initAll(document);
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && openInstance) {
      event.preventDefault();
      openInstance.close();
    }
  }, true);

  document.addEventListener("htmx:afterSwap", function (event) {
    initAll(event.target);
  });
})();
