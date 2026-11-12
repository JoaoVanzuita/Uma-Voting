/* ---------------------------------------------------------------------------
 * Uma Voting — utilitários de interface
 * Sem scripts inline (CSP script-src 'self').
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  document.documentElement.classList.add("js");

  var SELECTION_FORM = "[data-selection-form]";
  var CHARACTER_CHECKBOX = 'input[type="checkbox"][name="character_ids"]';

  function getCookie(name) {
    var prefix = name + "=";
    var cookies = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf(prefix) === 0) {
        return decodeURIComponent(cookie.slice(prefix.length));
      }
    }
    return "";
  }

  /* -----------------------------------------------------------------------
   * Contador e limite de seleção
   * --------------------------------------------------------------------- */
  function selectedValues(form) {
    var values = {};
    if (!form) {
      return values;
    }

    var hiddenInputs = form.querySelectorAll(
      '[data-selected-inputs] input[name="selected"]'
    );
    Array.prototype.forEach.call(hiddenInputs, function (input) {
      values[input.value] = true;
    });

    var checkboxes = form.querySelectorAll(CHARACTER_CHECKBOX);
    Array.prototype.forEach.call(checkboxes, function (checkbox) {
      if (checkbox.checked) {
        values[checkbox.value] = true;
      }
    });

    return values;
  }

  function syncHiddenSelection(form, checkbox) {
    var holder = form.querySelector("[data-selected-inputs]");
    if (!holder) {
      return;
    }

    var hiddenInputs = holder.querySelectorAll('input[name="selected"]');
    var existing = null;
    Array.prototype.forEach.call(hiddenInputs, function (input) {
      if (input.value === checkbox.value) {
        existing = input;
      }
    });

    if (checkbox.checked && !existing) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "selected";
      input.value = checkbox.value;
      holder.appendChild(input);
    } else if (!checkbox.checked && existing) {
      existing.remove();
    }
  }

  function updateSelectionState(form) {
    if (!form) {
      return;
    }

    var max = parseInt(form.getAttribute("data-max-choices") || "0", 10);
    var checkboxes = Array.prototype.slice.call(
      form.querySelectorAll(CHARACTER_CHECKBOX)
    );
    var selected = selectedValues(form);
    var count = Object.keys(selected).length;
    var limitReached = max > 0 && count >= max;

    var counter = form.querySelector("[data-selection-counter]");
    if (counter) {
      counter.textContent = count + " de " + max + " escolhas";
      counter.setAttribute("data-limit-reached", limitReached ? "true" : "false");
    }

    checkboxes.forEach(function (checkbox) {
      var disabled = limitReached && !checkbox.checked;
      checkbox.disabled = disabled;
      var option = checkbox.closest("[data-character-option]");
      if (option) {
        option.setAttribute("data-selected", checkbox.checked ? "true" : "false");
        option.setAttribute("data-disabled", disabled ? "true" : "false");
      }
    });

    var status = form.querySelector("[data-selection-status]");
    if (status) {
      if (limitReached) {
        status.textContent =
          "Limite de " + max + " escolhas atingido. Desmarque uma opção para trocar.";
      } else if (count === 0) {
        status.textContent = "Nenhuma personagem selecionada.";
      } else {
        status.textContent = count + " de " + max + " escolhas selecionadas.";
      }
    }
  }

  function refreshAllSelectionForms() {
    var forms = document.querySelectorAll(SELECTION_FORM);
    Array.prototype.forEach.call(forms, updateSelectionState);
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (!target || !target.matches || !target.matches(CHARACTER_CHECKBOX)) {
      return;
    }
    var form = target.closest(SELECTION_FORM);
    syncHiddenSelection(form, target);
    updateSelectionState(form);
  });

  /* -----------------------------------------------------------------------
   * Fallback de imagem quebrada (sem onerror inline, por CSP)
   * --------------------------------------------------------------------- */
  document.addEventListener(
    "error",
    function (event) {
      var image = event.target;
      if (!image || image.tagName !== "IMG") {
        return;
      }
      var fallback = image.getAttribute("data-fallback-src");
      if (fallback && image.getAttribute("src") !== fallback) {
        image.setAttribute("src", fallback);
        image.setAttribute("data-fallback-applied", "true");
      }
    },
    true
  );

  /* -----------------------------------------------------------------------
   * Filtro local de estado das imagens no admin
   * --------------------------------------------------------------------- */
  function applyImageFilter(select) {
    if (!select) {
      return;
    }
    var value = select.value;
    var rows = document.querySelectorAll("[data-image-status]");
    Array.prototype.forEach.call(rows, function (row) {
      row.hidden = Boolean(value) && row.getAttribute("data-image-status") !== value;
    });
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target && target.matches && target.matches("[data-image-filter]")) {
      applyImageFilter(target);
    }
  });

  /* -----------------------------------------------------------------------
   * CSRF para requisições HTMX
   * --------------------------------------------------------------------- */
  document.addEventListener("htmx:configRequest", function (event) {
    var token = getCookie("csrftoken");
    if (token) {
      event.detail.headers["X-CSRFToken"] = token;
    }
  });

  /* -----------------------------------------------------------------------
   * Estados de carregamento e foco após troca de fragmento
   * --------------------------------------------------------------------- */
  function setBusy(element, busy) {
    if (!element || !element.setAttribute) {
      return;
    }
    if (busy) {
      element.setAttribute("aria-busy", "true");
    } else {
      element.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("htmx:beforeRequest", function (event) {
    setBusy(event.detail.target, true);
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    setBusy(event.detail.target, false);
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    refreshAllSelectionForms();

    var target = event.detail.target;
    if (target && target.hasAttribute && target.hasAttribute("data-focus-after-swap")) {
      var focusTarget = target.querySelector("[data-focus-target]") || target;
      if (focusTarget && typeof focusTarget.focus === "function") {
        focusTarget.focus({ preventScroll: false });
      }
    }
  });

  document.addEventListener("htmx:responseError", function (event) {
    var target = event.detail.target;
    if (!target || !target.querySelector) {
      return;
    }
    var region = target.querySelector("[data-htmx-error]");
    if (region) {
      region.textContent =
        "Não foi possível concluir a operação. Tente novamente.";
      region.hidden = false;
    }
  });

  /* Confirmação de ações destrutivas sem script inline (CSP). */
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || !form.matches || !form.hasAttribute("data-confirm")) {
        return;
      }
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true
  );

  /* Evita envio duplicado de formulários marcados explicitamente. */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.matches || !form.matches("[data-submit-once]")) {
      return;
    }
    var submitter = form.querySelector('[type="submit"]');
    if (submitter) {
      submitter.setAttribute("aria-busy", "true");
      submitter.disabled = true;
    }
  });

  /* -----------------------------------------------------------------------
   * Drawer administrativo mobile
   * --------------------------------------------------------------------- */
  var ADMIN_DRAWER_OPEN = "[data-admin-drawer-open]";
  var ADMIN_DRAWER_CLOSE = "[data-admin-drawer-close]";
  var ADMIN_DRAWER_OVERLAY = "[data-admin-drawer-overlay]";
  var ADMIN_DRAWER_SELECTOR = ".admin-sidebar";
  var ADMIN_DRAWER_DESKTOP = "(min-width: 1024px)";
  var ADMIN_DRAWER_FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), ' +
    'select:not([disabled]), textarea:not([disabled]), ' +
    '[tabindex]:not([tabindex="-1"])';

  function adminDrawerFor(trigger) {
    var id = trigger && trigger.getAttribute("aria-controls");
    return id ? document.getElementById(id) : null;
  }

  function adminDrawerOverlay(drawer) {
    return drawer && drawer.parentNode
      ? drawer.parentNode.querySelector(ADMIN_DRAWER_OVERLAY)
      : null;
  }

  function adminDrawerTrigger(drawer) {
    return document.querySelector(
      ADMIN_DRAWER_OPEN + '[aria-controls="' + drawer.id + '"]'
    );
  }

  function adminDrawerFocusable(drawer) {
    return Array.prototype.filter.call(
      drawer.querySelectorAll(ADMIN_DRAWER_FOCUSABLE),
      function (element) {
        return element.getClientRects().length > 0;
      }
    );
  }

  function openAdminDrawer(trigger) {
    var drawer = adminDrawerFor(trigger);
    if (!drawer) {
      return;
    }

    drawer.classList.add("is-open");
    var overlay = adminDrawerOverlay(drawer);
    if (overlay) {
      overlay.hidden = false;
    }
    trigger.setAttribute("aria-expanded", "true");
    document.body.classList.add("admin-drawer-open");

    var close = drawer.querySelector(ADMIN_DRAWER_CLOSE);
    var focusTarget = close || adminDrawerFocusable(drawer)[0] || drawer;
    if (focusTarget && typeof focusTarget.focus === "function") {
      focusTarget.focus({ preventScroll: true });
    }
  }

  function closeAdminDrawer(drawer, restoreFocus) {
    if (!drawer || !drawer.classList.contains("is-open")) {
      return;
    }

    drawer.classList.remove("is-open");
    var overlay = adminDrawerOverlay(drawer);
    if (overlay) {
      overlay.hidden = true;
    }
    document.body.classList.remove("admin-drawer-open");

    var trigger = adminDrawerTrigger(drawer);
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
      if (restoreFocus) {
        trigger.focus({ preventScroll: true });
      }
    }
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var openButton = target.closest(ADMIN_DRAWER_OPEN);
    if (openButton) {
      event.preventDefault();
      openAdminDrawer(openButton);
      return;
    }

    var closeButton = target.closest(ADMIN_DRAWER_CLOSE);
    if (closeButton) {
      event.preventDefault();
      closeAdminDrawer(closeButton.closest(ADMIN_DRAWER_SELECTOR), true);
      return;
    }

    var overlay = target.closest(ADMIN_DRAWER_OVERLAY);
    if (overlay) {
      var overlayDrawer = overlay.parentNode.querySelector(ADMIN_DRAWER_SELECTOR);
      closeAdminDrawer(overlayDrawer, true);
      return;
    }

    var drawerLink = target.closest(".admin-sidebar.is-open a[href]");
    if (drawerLink) {
      closeAdminDrawer(drawerLink.closest(ADMIN_DRAWER_SELECTOR), false);
    }
  });

  document.addEventListener("keydown", function (event) {
    var drawer = document.querySelector(".admin-sidebar.is-open");
    if (!drawer) {
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeAdminDrawer(drawer, true);
      return;
    }

    if (event.key !== "Tab") {
      return;
    }

    var focusable = adminDrawerFocusable(drawer);
    if (!focusable.length) {
      return;
    }

    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  var adminDrawerDesktop = window.matchMedia(ADMIN_DRAWER_DESKTOP);
  function closeAdminDrawerOnDesktop(event) {
    if (!event.matches) {
      return;
    }
    var drawer = document.querySelector(".admin-sidebar.is-open");
    if (drawer) {
      closeAdminDrawer(drawer, false);
    }
  }
  if (adminDrawerDesktop.addEventListener) {
    adminDrawerDesktop.addEventListener("change", closeAdminDrawerOnDesktop);
  } else if (adminDrawerDesktop.addListener) {
    adminDrawerDesktop.addListener(closeAdminDrawerOnDesktop);
  }

  /* -----------------------------------------------------------------------
   * Inicialização
   * --------------------------------------------------------------------- */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshAllSelectionForms);
  } else {
    refreshAllSelectionForms();
  }

  document.addEventListener("htmx:afterSettle", refreshAllSelectionForms);
})();
