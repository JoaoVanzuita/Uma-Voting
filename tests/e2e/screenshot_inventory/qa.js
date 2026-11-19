/* Auditoria de acessibilidade e responsividade da interface (Fase 8).
 *
 * Executa depois do inventário visual, na mesma instância isolada:
 *   NODE_PATH=var/screenshot-harness/node_modules node tests/e2e/screenshot_inventory/qa.js
 *
 * Verifica estrutura, nomes acessíveis, labels, contraste AA, alvos de toque,
 * overflow, console/HTTP, skip link, drawer por teclado, seleção por teclado e
 * prefers-reduced-motion. Gera var/screenshots/qa-report.json e falha o processo
 * quando encontra regressões.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.SCREENSHOT_BASE_URL || "http://127.0.0.1:8001";
const ROOT = process.env.SCREENSHOT_OUTPUT
  ? path.resolve(process.env.SCREENSHOT_OUTPUT)
  : path.resolve(__dirname, "../../../var/screenshots");
const PROJECT_ROOT = path.resolve(__dirname, "../../..");
const SCENARIO = JSON.parse(fs.readFileSync(path.join(ROOT, "scenario.json"), "utf8"));
const CREDENTIALS = SCENARIO.credentials;
const V = SCENARIO.votings;
const USERS = SCENARIO.users;
const CHROME =
  process.env.PLAYWRIGHT_CHROMIUM ||
  "/home/joaovanzuita/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

const report = {
  generated_at: new Date().toISOString(),
  base_url: BASE,
  pages: [],
  keyboard: [],
  reduced_motion: [],
  failures: [],
};

function urlFor(target) {
  if (/^https?:\/\//.test(target)) return target;
  return BASE + (target.startsWith("/") ? target : `/${target}`);
}

async function login(context, pathName, username, password) {
  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.accept().catch(() => {}));
  await page.goto(urlFor(pathName), { waitUntil: "domcontentloaded" });
  await page.fill("#id_username", username);
  if (password) await page.fill("#id_password", password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    page.locator('form button[type="submit"]').first().click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  return page;
}

async function releaseBallot(page, votingId, userId) {
  await page.goto(urlFor(`/admin/votacoes/${votingId}/`), {
    waitUntil: "domcontentloaded",
  });
  const form = page.locator(`form[action$="/cedulas/${userId}/excluir/"]`).first();
  if (!(await form.count())) return false;
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    form.locator('button[type="submit"]').click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  return true;
}


async function auditPage(page, label) {
  return page.evaluate((label) => {
    const issues = [];
    const visible = (element) => {
      if (!element) return false;
      if (element.closest("[hidden]")) return false;
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
        return false;
      }
      return element.getClientRects().length > 0;
    };
    const accessibleName = (element) => {
      const labelledBy = element.getAttribute("aria-labelledby");
      if (labelledBy) {
        const text = labelledBy
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent || "")
          .join(" ")
          .trim();
        if (text) return text;
      }
      const label = element.getAttribute("aria-label") || element.getAttribute("title");
      if (label && label.trim()) return label.trim();
      const text = (element.textContent || "").replace(/\s+/g, " ").trim();
      if (text) return text;
      const image = element.querySelector("img[alt]");
      if (image && image.getAttribute("alt").trim()) return image.getAttribute("alt").trim();
      return "";
    };
    const parseRgb = (value) => {
      const match = value.match(/rgba?\(([^)]+)\)/i);
      if (!match) return null;
      const parts = match[1].split(",").map((part) => Number.parseFloat(part.trim()));
      if (parts.length < 3 || parts.some((part) => Number.isNaN(part))) return null;
      return [parts[0], parts[1], parts[2], parts[3] === undefined ? 1 : parts[3]];
    };
    const relativeLuminance = (rgb) => {
      const channel = (value) => {
        const normalized = value / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : Math.pow((normalized + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
    };
    const contrastRatio = (foreground, background) => {
      const a = relativeLuminance(foreground);
      const b = relativeLuminance(background);
      const lighter = Math.max(a, b);
      const darker = Math.min(a, b);
      return (lighter + 0.05) / (darker + 0.05);
    };
    const effectiveBackground = (element) => {
      let node = element;
      while (node) {
        const parsed = parseRgb(getComputedStyle(node).backgroundColor);
        if (parsed && parsed[3] >= 0.99) return parsed;
        node = node.parentElement;
      }
      return [255, 255, 255, 1];
    };

    const language = document.documentElement.getAttribute("lang");
    if ((language || "").toLowerCase() !== "pt-br") {
      issues.push(`lang=${language || "(ausente)"}`);
    }

    const headings = Array.from(document.querySelectorAll("h1")).filter(visible);
    if (headings.length !== 1) {
      issues.push(`esperado 1 h1 visível, encontrado ${headings.length}`);
    } else if (!headings[0].textContent.trim()) {
      issues.push("h1 vazio");
    }

    const seenIds = new Map();
    for (const element of document.querySelectorAll("[id]")) {
      const id = element.id;
      seenIds.set(id, (seenIds.get(id) || 0) + 1);
    }
    for (const [id, count] of seenIds) {
      if (count > 1) issues.push(`id duplicado: #${id} (${count})`);
    }

    for (const image of Array.from(document.images)) {
      if (!visible(image)) continue;
      if (!image.hasAttribute("alt")) {
        issues.push(`imagem sem alt: ${image.getAttribute("src") || "(sem src)"}`);
      }
    }

    for (const control of Array.from(
      document.querySelectorAll("input:not([type=hidden]), select, textarea")
    )) {
      if (!visible(control) || control.disabled || control.getAttribute("aria-hidden") === "true") {
        continue;
      }
      const id = control.id;
      const hasLabel =
        (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) ||
        control.closest("label") ||
        control.getAttribute("aria-label") ||
        control.getAttribute("aria-labelledby") ||
        control.getAttribute("title");
      if (!hasLabel) {
        issues.push(`controle sem label: ${control.tagName.toLowerCase()}#${id || "(sem id)"}`);
      }
    }

    for (const action of Array.from(
      document.querySelectorAll("a[href], button, [role=button]")
    )) {
      if (!visible(action) || action.disabled) continue;
      if (!accessibleName(action)) {
        issues.push(`ação sem nome acessível: ${action.outerHTML.slice(0, 90)}`);
      }
    }

    for (const target of Array.from(document.querySelectorAll("button, .btn, input[type=submit]"))) {
      if (!visible(target) || target.disabled) continue;
      const box = target.getBoundingClientRect();
      if (box.width > 0 && box.height > 0 && (box.width < 24 || box.height < 24)) {
        issues.push(
          `alvo menor que 24 px: ${(target.textContent || target.value || "").trim().slice(0, 40)} (${Math.round(
            box.width
          )}×${Math.round(box.height)})`
        );
      }
    }

    let contrastChecks = 0;
    const contrastIssues = [];
    for (const element of Array.from(document.body.querySelectorAll("*"))) {
      if (!visible(element)) continue;
      if (element.closest("[aria-hidden=true]")) continue;
      const ownText = Array.from(element.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent.trim())
        .join(" ")
        .trim();
      if (!ownText) continue;
      const style = getComputedStyle(element);
      if (style.color === "transparent") continue;
      const foreground = parseRgb(style.color);
      if (!foreground || foreground[3] < 0.99) continue;
      const background = effectiveBackground(element);
      const ratio = contrastRatio(foreground, background);
      const fontSize = Number.parseFloat(style.fontSize);
      const weight = Number.parseInt(style.fontWeight, 10) || 400;
      const large = fontSize >= 24 || (fontSize >= 18.66 && weight >= 700);
      const minimum = large ? 3 : 4.5;
      contrastChecks += 1;
      if (ratio + 0.02 < minimum) {
        contrastIssues.push(
          `${ratio.toFixed(2)}:1 (mín. ${minimum}) em "${ownText.slice(0, 48)}" [${style.color}]`
        );
      }
    }
    if (contrastIssues.length) {
      issues.push(`contraste: ${contrastIssues.slice(0, 8).join(" | ")}`);
    }

    const root = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(root.scrollWidth, body ? body.scrollWidth : 0);
    const overflow = Math.max(0, scrollWidth - root.clientWidth);

    return {
      label,
      url: location.href,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      overflow,
      contrast_checks: contrastChecks,
      issues,
    };
  }, label);
}

async function visit(page, target, label, expectedStatus = 200) {
  const consoleErrors = [];
  const pageErrors = [];
  const onConsole = (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      consoleErrors.push(message.text());
    }
  };
  const onPageError = (error) => pageErrors.push(error.message);
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  let response;
  try {
    response = await page.goto(urlFor(target), {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(80);
    const audit = await auditPage(page, label);
    const status = response ? response.status() : null;
    if (status !== expectedStatus) {
      audit.issues.push(`HTTP ${status} (esperado ${expectedStatus})`);
    }
    if (consoleErrors.length) audit.issues.push(`console: ${consoleErrors.join(" | ")}`);
    if (pageErrors.length) audit.issues.push(`pageerror: ${pageErrors.join(" | ")}`);
    audit.http_status = status;
    report.pages.push(audit);
    if (audit.issues.length) {
      report.failures.push({ label, url: audit.url, issues: audit.issues });
      console.error(`  ✗ ${label} — ${audit.issues.length} achado(s)`);
      for (const issue of audit.issues) console.error(`      ${issue}`);
    } else {
      console.log(`  ✓ ${label}`);
    }
  } catch (error) {
    report.failures.push({ label, url: target, issues: [error.message] });
    console.error(`  ✗ ${label} — ${error.message}`);
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }
}

async function keyboardAudit(browser) {
  const participantContext = await browser.newContext({ viewport: DESKTOP });
  const participant = await login(
    participantContext,
    "/entrar/",
    CREDENTIALS.participant.username
  );
  await participant.goto(urlFor("/"), { waitUntil: "domcontentloaded" });
  await participant.keyboard.press("Tab");
  const skipFocused = await participant.evaluate(() =>
    document.activeElement?.classList.contains("skip-link")
  );
  await participant.keyboard.press("Enter");
  await participant.waitForTimeout(150);
  const skipHash = await participant.evaluate(() => window.location.hash);
  report.keyboard.push({
    flow: "skip-link",
    passed: skipFocused && skipHash === "#conteudo",
    detail: { focused: skipFocused, hash: skipHash },
  });

  const releaseContext = await browser.newContext({ viewport: DESKTOP });
  const releaseAdmin = await login(
    releaseContext,
    "/admin/entrar/",
    CREDENTIALS.admin.username,
    CREDENTIALS.admin.password
  );
  await releaseAdmin.goto(urlFor(`/admin/votacoes/${V.open_ballots.id}/`), {
    waitUntil: "domcontentloaded",
  });
  const ballotDelete = releaseAdmin.locator(
    `form[action$="/cedulas/${USERS.participant_id}/excluir/"]`
  );
  let ballotReleased = false;
  if (await ballotDelete.count()) {
    await Promise.all([
      releaseAdmin.waitForNavigation({ waitUntil: "domcontentloaded" }),
      ballotDelete.first().locator('button[type="submit"]').click(),
    ]);
    await releaseAdmin.waitForLoadState("networkidle").catch(() => {});
    ballotReleased = true;
  }
  await releaseContext.close();

  const selectionContext = await browser.newContext({ viewport: DESKTOP });
  const selector = await login(
    selectionContext,
    "/entrar/",
    CREDENTIALS.participant.username
  );
  await selector.goto(urlFor(`/votacoes/${V.open_ballots.id}/`), {
    waitUntil: "domcontentloaded",
  });
  await selector.waitForLoadState("networkidle").catch(() => {});
  const checkbox = selector.locator('input[name="character_ids"]:not([disabled])').first();
  const canSelect = (await checkbox.count()) > 0;
  let selectionPassed = false;
  let selectionDetail = { ballot_released: ballotReleased };
  if (canSelect) {
    await checkbox.focus();
    await selector.keyboard.press("Space");
    await selector.waitForTimeout(220);
    selectionDetail = await selector.evaluate((detail) => {
      const input = document.querySelector('input[name="character_ids"]:checked');
      const option = input?.closest("[data-character-option]");
      const counter = document.querySelector("[data-selection-counter]");
      return {
        ...detail,
        js: document.documentElement.classList.contains("js"),
        form_found: Boolean(input?.closest("[data-selection-form]")),
        options: document.querySelectorAll("[data-character-option]").length,
        checked_count: document.querySelectorAll('input[name="character_ids"]:checked').length,
        checked: Boolean(input),
        selected: option?.getAttribute("data-selected") || null,
        counter: counter?.textContent.replace(/\s+/g, " ").trim() || null,
      };
    }, selectionDetail);
    selectionPassed =
      selectionDetail.js &&
      selectionDetail.form_found &&
      selectionDetail.checked &&
      selectionDetail.selected === "true" &&
      Boolean(selectionDetail.counter);
  }
  report.keyboard.push({
    flow: "selecao-por-teclado",
    passed: selectionPassed,
    detail: selectionDetail,
  });

  const mobileContext = await browser.newContext({ viewport: MOBILE });
  const mobileAdmin = await login(
    mobileContext,
    "/admin/entrar/",
    CREDENTIALS.admin.username,
    CREDENTIALS.admin.password
  );
  await mobileAdmin.goto(urlFor("/admin/"), { waitUntil: "domcontentloaded" });
  const openButton = mobileAdmin.locator("[data-admin-drawer-open]").first();
  await openButton.focus();
  await mobileAdmin.keyboard.press("Enter");
  await mobileAdmin.waitForTimeout(180);
  const drawerOpen = await mobileAdmin.evaluate(() => {
    const sidebar = document.querySelector(".admin-sidebar");
    const button = document.querySelector("[data-admin-drawer-open]");
    return {
      isOpen: sidebar?.classList.contains("is-open") || false,
      expanded: button?.getAttribute("aria-expanded"),
      focusInside: Boolean(sidebar?.contains(document.activeElement)),
    };
  });
  await mobileAdmin.keyboard.press("Escape");
  await mobileAdmin.waitForTimeout(180);
  const drawerClosed = await mobileAdmin.evaluate(() => {
    const sidebar = document.querySelector(".admin-sidebar");
    const button = document.querySelector("[data-admin-drawer-open]");
    return {
      isOpen: sidebar?.classList.contains("is-open") || false,
      expanded: button?.getAttribute("aria-expanded"),
      focusReturned: document.activeElement === button,
    };
  });
  report.keyboard.push({
    flow: "drawer-teclado",
    passed:
      drawerOpen.isOpen &&
      drawerOpen.expanded === "true" &&
      drawerOpen.focusInside &&
      !drawerClosed.isOpen &&
      drawerClosed.expanded === "false" &&
      drawerClosed.focusReturned,
    detail: { open: drawerOpen, closed: drawerClosed },
  });

  await participantContext.close();
  await selectionContext.close();
  await mobileContext.close();
}

async function reducedMotionAudit(browser) {
  const context = await browser.newContext({
    viewport: DESKTOP,
    reducedMotion: "reduce",
  });
  const participant = await login(
    context,
    "/entrar/",
    CREDENTIALS.participant.username
  );
  for (const target of ["/", `/votacoes/${V.closed.id}/resultado/`]) {
    await participant.goto(urlFor(target), { waitUntil: "domcontentloaded" });
    await participant.waitForLoadState("networkidle").catch(() => {});
    const result = await participant.evaluate(() => {
      const selectors = ".card, .result-item, .character-option, .stage-band, .selection-summary";
      const offenders = [];
      for (const element of document.querySelectorAll(selectors)) {
        const style = getComputedStyle(element);
        if (style.animationName && style.animationName !== "none") {
          offenders.push(`${element.className}: ${style.animationName}`);
        }
      }
      return offenders;
    });
    report.reduced_motion.push({ url: target, passed: result.length === 0, offenders: result });
  }
  await context.close();
}

async function main() {
  const launchOptions = { args: ["--no-sandbox", "--disable-dev-shm-usage"] };
  if (fs.existsSync(CHROME)) launchOptions.executablePath = CHROME;
  const browser = await chromium.launch(launchOptions);

  console.log("\n[QA] Estrutura, contraste e responsividade");

  const guestContext = await browser.newContext({ viewport: DESKTOP });
  const guest = await guestContext.newPage();
  const participantContext = await browser.newContext({ viewport: DESKTOP });
  const participant = await login(
    participantContext,
    "/entrar/",
    CREDENTIALS.participant.username
  );
  const adminContext = await browser.newContext({ viewport: DESKTOP });
  const admin = await login(
    adminContext,
    "/admin/entrar/",
    CREDENTIALS.admin.username,
    CREDENTIALS.admin.password
  );
  await releaseBallot(admin, V.open_ballots.id, USERS.participant_id);

  const desktopPages = [
    [guest, "/entrar/", "Login de participante"],
    [guest, "/admin/entrar/", "Login administrativo"],
    [participant, "/", "Home de votações"],
    [participant, "/historico/", "Histórico"],
    [participant, `/votacoes/${V.closed.id}/resultado/`, "Resultado final"],
    [participant, `/votacoes/${V.open_ballots.id}/`, "Seleção de personagens"],
    [admin, "/admin/", "Dashboard administrativo"],
    [admin, "/admin/votacoes/", "Lista de votações"],
    [admin, `/admin/votacoes/${V.draft.id}/`, "Detalhe da votação"],
    [admin, "/admin/participantes/", "Lista de participantes"],
    [admin, "/admin/catalogo/", "Catálogo"],
    [admin, "/admin/catalogo/personagens/", "Personagens do catálogo"],
    [admin, "/admin/catalogo/imagens/", "Imagens do catálogo"],
  ];
  for (const [page, target, label] of desktopPages) {
    await visit(page, target, `1440 — ${label}`);
  }

  const mobileContext = await browser.newContext({ viewport: MOBILE });
  const mobileAdmin = await login(
    mobileContext,
    "/admin/entrar/",
    CREDENTIALS.admin.username,
    CREDENTIALS.admin.password
  );
  const mobileParticipantContext = await browser.newContext({ viewport: MOBILE });
  const mobileParticipant = await login(
    mobileParticipantContext,
    "/entrar/",
    CREDENTIALS.participant.username
  );
  const mobilePages = [
    [mobileParticipant, "/", "Home de votações"],
    [mobileParticipant, `/votacoes/${V.closed.id}/resultado/`, "Resultado final"],
    [mobileAdmin, "/admin/", "Dashboard administrativo"],
    [mobileAdmin, "/admin/votacoes/", "Lista de votações"],
    [mobileAdmin, "/admin/participantes/", "Lista de participantes"],
    [mobileAdmin, "/admin/catalogo/imagens/", "Imagens do catálogo"],
  ];
  for (const [page, target, label] of mobilePages) {
    await visit(page, target, `390 — ${label}`);
  }

  console.log("\n[QA] Teclado");
  await keyboardAudit(browser);
  for (const entry of report.keyboard) {
    if (entry.passed) console.log(`  ✓ ${entry.flow}`);
    else {
      console.error(`  ✗ ${entry.flow} — ${JSON.stringify(entry.detail)}`);
      report.failures.push({ label: entry.flow, issues: [JSON.stringify(entry.detail)] });
    }
  }

  console.log("\n[QA] prefers-reduced-motion");
  await reducedMotionAudit(browser);
  for (const entry of report.reduced_motion) {
    if (entry.passed) console.log(`  ✓ ${entry.url}`);
    else {
      console.error(`  ✗ ${entry.url} — ${entry.offenders.join(" | ")}`);
      report.failures.push({ label: `reduced-motion ${entry.url}`, issues: entry.offenders });
    }
  }

  await guestContext.close();
  await participantContext.close();
  await adminContext.close();
  await mobileContext.close();
  await mobileParticipantContext.close();
  await browser.close();

  const reportPath = path.join(ROOT, "qa-report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nRelatório de QA: ${reportPath}`);
  console.log(
    `${report.pages.length} páginas auditadas, ${report.keyboard.length} fluxos de teclado, ` +
      `${report.reduced_motion.length} verificações de movimento, ${report.failures.length} falha(s).`
  );
  if (report.failures.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error("\nFalha fatal na auditoria:", error);
  process.exitCode = 1;
});
