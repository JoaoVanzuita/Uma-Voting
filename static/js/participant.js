/* ---------------------------------------------------------------------------
 * Uma Voting — comportamentos de apresentação do fluxo do participante.
 *
 * Mantém os chips de filtros ativos sincronizados com os checkboxes HTMX de
 * P02/P03 sem alterar a busca server-side nem o debounce de 300 ms.
 * Sem scripts inline (CSP script-src 'self').
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  var SELECTION_FORM = "[data-selection-form]";
  var FILTER_INPUT = "input[data-filter-category]";
  var ACTIVE_FILTERS = "[data-active-filters]";

  function filterInputs(form) {
    return Array.prototype.slice.call(form.querySelectorAll(FILTER_INPUT));
  }

  function activeFilterInputs(form) {
    return filterInputs(form).filter(function (input) {
      return input.checked;
    });
  }

  function filterLabel(input) {
    return input.getAttribute("data-filter-label") || input.value;
  }

  function chipSelector(category, value) {
    return (
      FILTER_INPUT +
      '[data-filter-category="' +
      category +
      '"][data-filter-value="' +
      value +
      '"]'
    );
  }

  function createActiveChip(input) {
    var label = filterLabel(input);
    var button = document.createElement("button");

    button.type = "button";
    button.className = "chip chip--active";
    button.setAttribute("data-filter-chip", "");
    button.setAttribute(
      "data-filter-category",
      input.getAttribute("data-filter-category")
    );
    button.setAttribute("data-filter-value", input.getAttribute("data-filter-value"));
    button.setAttribute("aria-label", "Remover filtro " + label);

    button.appendChild(document.createTextNode(label + " "));

    var mark = document.createElement("span");
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = "×";
    button.appendChild(mark);

    return button;
  }

  function renderActiveFilters(form) {
    if (!form) {
      return;
    }

    var holder = form.querySelector(ACTIVE_FILTERS);
    if (!holder) {
      return;
    }

    var active = activeFilterInputs(form);
    holder.textContent = "";

    active.forEach(function (input) {
      holder.appendChild(createActiveChip(input));
    });

    holder.hidden = active.length === 0;
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var chip = target.closest("[data-filter-chip]");
    if (!chip) {
      return;
    }

    var form = chip.closest(SELECTION_FORM);
    if (!form) {
      return;
    }

    var input = form.querySelector(
      chipSelector(
        chip.getAttribute("data-filter-category"),
        chip.getAttribute("data-filter-value")
      )
    );
    if (!input) {
      return;
    }

    event.preventDefault();
    input.checked = false;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var clear = target.closest("[data-clear-filters]");
    if (!clear) {
      return;
    }

    var form = clear.closest(SELECTION_FORM);
    if (!form || !window.htmx || typeof window.htmx.trigger !== "function") {
      return;
    }

    event.preventDefault();

    var search = form.querySelector("#character-search");
    filterInputs(form).forEach(function (input) {
      input.checked = false;
    });
    if (search) {
      search.value = "";
    }

    renderActiveFilters(form);

    if (search) {
      search.focus({ preventScroll: true });
      window.htmx.trigger(search, "search");
    }
  });

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (!target || !target.matches || !target.matches(FILTER_INPUT)) {
      return;
    }
    renderActiveFilters(target.closest(SELECTION_FORM));
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || !target.closest) {
      return;
    }
    renderActiveFilters(target.closest(SELECTION_FORM));
  });

  /* Mantém o elemento focado acima da barra persistente de resumo. */
  document.addEventListener("focusin", function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var form = target.closest(SELECTION_FORM);
    if (!form) {
      return;
    }

    var summary = form.querySelector("#selection-summary");
    if (!summary || summary.contains(target)) {
      return;
    }

    var focused =
      target.closest("[data-character-option]") || target;
    var focusedRect = focused.getBoundingClientRect();
    var summaryRect = summary.getBoundingClientRect();

    if (
      focusedRect.bottom > summaryRect.top &&
      focusedRect.top < summaryRect.bottom
    ) {
      window.scrollBy({
        top: focusedRect.bottom - summaryRect.top + 16,
        left: 0,
        behavior: "auto",
      });
    }
  });

  function init() {
    var forms = document.querySelectorAll(SELECTION_FORM);
    Array.prototype.forEach.call(forms, renderActiveFilters);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
