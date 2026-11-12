/* Atualiza o progresso da importação externa enquanto a execução está ativa. */
(function () {
  "use strict";

  const root = document.querySelector("[data-import-status]");
  if (!root) {
    return;
  }

  const statusUrl = root.getAttribute("data-status-url");
  const intervalMs = 2000;
  let reloaded = false;

  function setText(selector, value) {
    const node = root.querySelector(selector);
    if (node && value !== undefined && value !== null) {
      node.textContent = value;
    }
  }

  function apply(payload) {
    const percent = Math.max(0, Math.min(100, payload.progress ? payload.progress.percent : 0));
    setText("[data-status-label]", payload.status_label);
    setText("[data-phase-label]", payload.phase_label);
    setText("[data-current-step]", payload.current_step || "—");

    const progressText = root.querySelector("[data-progress-text]");
    if (progressText && payload.progress) {
      progressText.textContent = `${payload.progress.done} de ${payload.progress.total}`;
    }

    const bar = root.querySelector("[data-progress-bar]");
    const fill = root.querySelector("[data-progress-fill]");
    if (bar) {
      bar.setAttribute("aria-valuenow", String(percent));
      if (payload.progress) {
        bar.setAttribute(
          "aria-valuetext",
          `${payload.progress.done} de ${payload.progress.total}`,
        );
      }
    }
    if (fill) {
      fill.style.width = `${percent}%`;
    }
  }

  function schedule() {
    window.setTimeout(poll, intervalMs);
  }

  async function poll() {
    try {
      const response = await fetch(statusUrl, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        schedule();
        return;
      }
      const payload = await response.json();
      apply(payload);
      if (payload.terminal && !reloaded) {
        reloaded = true;
        window.location.reload();
        return;
      }
      if (!payload.terminal) {
        schedule();
      }
    } catch (error) {
      schedule();
    }
  }

  if (root.getAttribute("data-terminal") !== "true") {
    schedule();
  }
})();
