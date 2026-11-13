/* Inventário visual — captura Playwright de todas as telas e componentes.
 *
 * Uso:
 *   NODE_PATH=var/screenshot-harness/node_modules node tests/e2e/screenshot_inventory/capture.js
 *
 * Requer a instância isolada em http://127.0.0.1:8001 apontando para o banco
 * clonado e o cenário criado por seed.py.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.SCREENSHOT_BASE_URL || "http://127.0.0.1:8001";
const ROOT = process.env.SCREENSHOT_OUTPUT
  ? path.resolve(process.env.SCREENSHOT_OUTPUT)
  : path.resolve(__dirname, "../../../var/screenshots");
const PNG_DIR = path.join(ROOT, "png");
const PROJECT_ROOT = path.resolve(__dirname, "../../..");
const SCENARIO = JSON.parse(fs.readFileSync(path.join(ROOT, "scenario.json"), "utf8"));

function fixturePath(value) {
  if (!value) return value;
  if (value.startsWith("/app/")) {
    return path.join(PROJECT_ROOT, value.slice("/app/".length));
  }
  return path.isAbsolute(value) ? value : path.join(PROJECT_ROOT, value);
}

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };
const TABLET = { width: 820, height: 1180 };

const CREDENTIALS = SCENARIO.credentials;
const USERS = SCENARIO.users;
const V = SCENARIO.votings;
const FIXTURES = SCENARIO.fixtures;
const CHROME =
  process.env.PLAYWRIGHT_CHROMIUM ||
  "/home/joaovanzuita/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome";

const manifest = [];
const failures = [];
const pageAudits = new WeakMap();

// Capturas que intencionalmente retornam 4xx/5xx ou carregam um recurso
// ausente (por exemplo, /health/ não serve favicon).
const ERROR_CAPTURES = new Set([
  "I01-01",
  "I02-01",
  "I02-02",
  "I02-03",
  "I03-01",
  "I04-01",
  "P02-04",
  "P02-06",
  "P02-07",
  "P05-02",
  "P06-03",
  "P08-01",
]);

function ensurePageAudit(page) {
  let state = pageAudits.get(page);
  if (!state) {
    state = { console: [], pageerrors: [] };
    page.on("console", (message) => {
      if (message.type() === "error") state.console.push(message.text());
    });
    page.on("pageerror", (error) => state.pageerrors.push(error.message));
    pageAudits.set(page, state);
  }
  return state;
}

function resetPageAudit(page) {
  const state = ensurePageAudit(page);
  state.console.length = 0;
  state.pageerrors.length = 0;
}

async function measureOverflow(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(
      root ? root.scrollWidth : 0,
      body ? body.scrollWidth : 0
    );
    const clientWidth = root ? root.clientWidth : 0;
    return Math.max(0, scrollWidth - clientWidth);
  });
}

function auditedConsoleErrors(errors, id) {
  if (!ERROR_CAPTURES.has(id)) return errors;
  return errors.filter((message) => !message.startsWith("Failed to load resource:"));
}

const FLOW = [
  {
    phase: "0. Preparação",
    description:
      "Banco isolado clonado, cenário determinístico criado por seed.py e instância em 127.0.0.1:8001.",
  },
  {
    phase: "1. Visitante",
    description:
      "Login de participante e administrativo (padrão e erro), healthcheck e página 404.",
    screens: ["A01", "A02", "I01", "I03"],
  },
  {
    phase: "2. Administração — base",
    description:
      "Dashboard, participantes (lista, busca, criação, edição, desativação) e importação CSV em duas etapas.",
    screens: ["D01", "D02", "D03", "D04"],
  },
  {
    phase: "3. Catálogo e sincronização",
    description:
      "Status do catálogo, sincronização com falha, sincronização com mudanças pendentes, aprovação/rejeição, personagens e imagens.",
    screens: ["D05", "D06", "D07", "D08"],
  },
  {
    phase: "4. Votações administrativas — configuração",
    description:
      "Lista e filtros, formulário de criação/edição, detalhe em rascunho, agendada, aberta, encerrada e cancelada, elegíveis.",
    screens: ["V01", "V02", "V03", "V04"],
  },
  {
    phase: "5. Participante — seleção",
    description:
      "Home, seleção com busca/filtros HTMX, limite de escolhas, erro de seleção e revisão da cédula.",
    screens: ["P01", "P02", "P03", "P04"],
  },
  {
    phase: "6. Participante — cédula e resultados",
    description:
      "Confirmação, consulta da cédula, segundo envio, resultado final, resultado vazio e histórico.",
    screens: ["P05", "P06", "P07"],
  },
  {
    phase: "7. Conflito de encerramento",
    description:
      "Revisão aberta no participante, encerramento pelo administrador e confirmação bloqueada (P08).",
    screens: ["P04", "P08"],
  },
  {
    phase: "8. Administração — acompanhamento",
    description:
      "Resultados parciais com votos, participação, detalhe da votação aberta, encerramento, ranking final e dashboard final.",
    screens: ["V03", "V05", "V06", "D01"],
  },
  {
    phase: "9. Erros e componentes",
    description:
      "403, 404, 500, modo participante, mensagens globais, badges e catálogo de componentes isolados.",
    screens: ["I02", "I03", "I04", "I05", "I06", "I07", "C01-C30"],
  },
  {
    phase: "10. Responsivo",
    description:
      "Telas principais em viewport móvel (390×844), tablet (820×1180) e matriz de breakpoints 360–1280 px.",
    screens: ["R01-R14", "W01-W20"],
  },
];

/* ------------------------------------------------------------------------- */
/* Utilidades                                                                */
/* ------------------------------------------------------------------------- */

function urlFor(target) {
  if (!target) return BASE;
  if (/^https?:\/\//.test(target)) return target;
  return BASE + (target.startsWith("/") ? target : `/${target}`);
}

async function go(page, target) {
  const response = await page.goto(urlFor(target), {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await page.waitForLoadState("networkidle").catch(() => {});
  return response;
}

async function settle(page, { scroll = true } = {}) {
  await page.waitForLoadState("domcontentloaded").catch(() => {});
  await page.evaluate(() => {
    document.querySelectorAll('img[loading="lazy"]').forEach((image) => {
      image.loading = "eager";
      if (!image.complete) image.src = image.src;
    });
  });
  if (scroll) {
    await page.evaluate(async () => {
      const step = Math.max(Math.floor(window.innerHeight * 0.75), 320);
      const height = Math.max(
        document.body ? document.body.scrollHeight : 0,
        document.documentElement ? document.documentElement.scrollHeight : 0
      );
      window.scrollTo(0, height);
      await new Promise((resolve) => setTimeout(resolve, 250));
      for (let y = 0; y <= height; y += step) {
        window.scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 22));
      }
      window.scrollTo(0, 0);
    });
  }
  await page.waitForTimeout(180);
  await page.evaluate(async () => {
    const images = Array.from(document.images || []);
    await Promise.all(
      images.map((image) => {
        if (image.complete && image.naturalWidth > 0) return Promise.resolve();
        return new Promise((resolve) => {
          image.addEventListener("load", resolve, { once: true });
          image.addEventListener("error", resolve, { once: true });
          setTimeout(resolve, 5000);
        });
      })
    );
  });
  await page.waitForTimeout(120);
}

async function submit(page, locator, { timeout = 15000 } = {}) {
  const target = typeof locator === "string" ? page.locator(locator).first() : locator;
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout }),
    target.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
}

async function clickNavigate(page, locator, { timeout = 15000 } = {}) {
  const target = typeof locator === "string" ? page.locator(locator).first() : locator;
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout }),
    target.click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
}

async function releaseParticipantBallot(page, votingId, userId) {
  await go(page, `/admin/votacoes/${votingId}/`);
  const form = page.locator(`form[action$="/cedulas/${userId}/excluir/"]`).first();
  if (!(await form.count())) return false;
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 15000 }),
    form.locator('button[type="submit"]').click(),
  ]);
  await page.waitForLoadState("networkidle").catch(() => {});
  return true;
}

async function shot(page, options) {
  const {
    id,
    group,
    screen,
    title,
    state = "",
    description = "",
    target,
    selector,
    fullPage = true,
    beforeGoto,
    before,
    staticSelectors = null,
    notes = "",
    timeout = 15000,
    wait = 100,
  } = options;

  if (!id || !group || !screen || !title) {
    throw new Error(`Screenshot sem metadados obrigatórios: ${JSON.stringify(options)}`);
  }

  resetPageAudit(page);

  if (beforeGoto) await beforeGoto(page);
  let response = null;
  if (target) response = await go(page, target);
  if (before) await before(page);
  if (wait) await page.waitForTimeout(wait);
  await settle(page, { scroll: fullPage });

  if (fullPage && staticSelectors && staticSelectors.length) {
    await page.evaluate((selectors) => {
      document.querySelectorAll(selectors.join(",")).forEach((node) => {
        node.dataset.screenshotPrevStyle = node.getAttribute("style") || "";
        node.style.setProperty("position", "static", "important");
      });
    }, staticSelectors);
  }

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(120);

  const file = path.join(PNG_DIR, `${id}.png`);
  let bounds = null;

  try {
    if (selector) {
      const locator = page.locator(selector).first();
      await locator.waitFor({ state: "visible", timeout });
      await locator.scrollIntoViewIfNeeded();
      await locator.screenshot({ path: file, timeout });
      bounds = await locator.boundingBox().catch(() => null);
    } else {
      await page.screenshot({ path: file, fullPage, timeout: 30000 });
    }
  } finally {
    if (fullPage && staticSelectors && staticSelectors.length) {
      await page.evaluate((selectors) => {
        document.querySelectorAll(selectors.join(",")).forEach((node) => {
          const previous = node.dataset.screenshotPrevStyle;
          if (previous) node.setAttribute("style", previous);
          else node.removeAttribute("style");
          delete node.dataset.screenshotPrevStyle;
        });
      }, staticSelectors);
    }
  }

  const stat = fs.statSync(file);
  const auditState = ensurePageAudit(page);
  const overflow = await measureOverflow(page);
  const httpStatus = response ? response.status() : null;
  const httpError = Boolean(httpStatus && httpStatus >= 400 && !ERROR_CAPTURES.has(id));
  const audit = {
    http_status: httpStatus,
    overflow,
    console_errors: [...auditState.console],
    page_errors: [...auditState.pageerrors],
  };
  resetPageAudit(page);

  manifest.push({
    id,
    group,
    screen,
    title,
    state,
    description,
    notes,
    file: `png/${id}.png`,
    url: page.url(),
    selector: selector || null,
    viewport: page.viewportSize(),
    bounds,
    bytes: stat.size,
    captured_at: new Date().toISOString(),
    audit,
  });
  console.log(`  ✓ ${id} — ${title}`);

  const auditIssues = [];
  if (httpError) auditIssues.push(`HTTP ${httpStatus}`);
  if (overflow > 1) auditIssues.push(`overflow horizontal de ${overflow}px`);
  const consoleErrors = auditedConsoleErrors(audit.console_errors, id);
  if (consoleErrors.length) {
    auditIssues.push(`console: ${consoleErrors.join(" | ")}`);
  }
  if (audit.page_errors.length) {
    auditIssues.push(`pageerror: ${audit.page_errors.join(" | ")}`);
  }
  if (auditIssues.length) {
    throw new Error(`auditoria da captura: ${auditIssues.join("; ")}`);
  }
}

async function safeShot(page, options) {
  try {
    await shot(page, options);
  } catch (error) {
    console.error(`  ✗ ${options.id} — ${error.message}`);
    failures.push({ ...options, error: error.message });
  }
}

async function safely(label, fn) {
  try {
    await fn();
  } catch (error) {
    console.error(`  ! ${label}: ${error.message}`);
    failures.push({ id: label, error: error.message });
  }
}

/* ------------------------------------------------------------------------- */
/* Autenticação                                                              */
/* ------------------------------------------------------------------------- */

async function loginParticipant(context, username) {
  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.accept().catch(() => {}));
  await go(page, "/entrar/");
  await page.fill("#id_username", username);
  await submit(page, 'form button[type="submit"]');
  return page;
}

async function loginAdmin(context) {
  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.accept().catch(() => {}));
  await go(page, "/admin/entrar/");
  await page.fill("#id_username", CREDENTIALS.admin.username);
  await page.fill("#id_password", CREDENTIALS.admin.password);
  await submit(page, 'form button[type="submit"]');
  return page;
}

async function logoutParticipant(context) {
  const page = await context.newPage();
  await go(page, "/");
  const form = page.locator('form[action="/sair/"]').first();
  if (await form.count()) {
    await submit(page, form.locator('button[type="submit"]'));
  }
  await page.close();
}

async function selectCharacters(page, count) {
  const boxes = page.locator('input[name="character_ids"]:not([disabled])');
  for (let index = 0; index < count; index += 1) {
    await boxes.nth(index).check();
  }
  await page.waitForTimeout(120);
}

async function selectedCharacterIds(page) {
  return page
    .locator('input[name="character_ids"]')
    .evaluateAll((elements) => elements.map((element) => element.value));
}

async function submitReview(page) {
  await submit(page, '#selection-summary button[type="submit"]');
}

async function confirmBallot(page) {
  await submit(page, 'button:has-text("Confirmar voto")');
}

async function htmxSearch(page, value) {
  await page.fill("#character-search", value);
  await page.waitForTimeout(900);
  await page.waitForLoadState("networkidle").catch(() => {});
}

function csrfFromCookies(cookies) {
  const cookie = cookies.find((item) => item.name === "csrftoken");
  return cookie ? cookie.value : "";
}

async function formAction(page, buttonText, rowText = null) {
  const scope = rowText
    ? page.locator("#conteudo table tbody tr", { hasText: rowText }).first()
    : page.locator("#conteudo");
  const form = scope.locator("form").filter({ hasText: buttonText }).first();
  await form.waitFor({ state: "attached", timeout: 15000 });
  const action = await form.getAttribute("action");
  if (!action) throw new Error(`Formulário sem action: ${buttonText}`);
  return action;
}

async function postForm(page, action, fields) {  const cookies = await page.context().cookies();
  const csrf = csrfFromCookies(cookies);
  const navigation = page
    .waitForNavigation({ waitUntil: "domcontentloaded", timeout: 15000 })
    .catch(() => null);
  await page.evaluate(
    ({ formAction, formFields, token }) => {
      const form = document.createElement("form");
      form.method = "post";
      form.action = formAction;
      const csrfInput = document.createElement("input");
      csrfInput.type = "hidden";
      csrfInput.name = "csrfmiddlewaretoken";
      csrfInput.value = token;
      form.appendChild(csrfInput);
      Object.entries(formFields).forEach(([name, value]) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        if (Array.isArray(value)) {
          value.forEach((item) => {
            const clone = input.cloneNode();
            clone.value = item;
            form.appendChild(clone);
          });
        } else {
          input.value = value;
          form.appendChild(input);
        }
      });
      document.body.appendChild(form);
      form.submit();
    },
    { formAction: action, formFields: fields, token: csrf }
  );
  await navigation;
  await page.waitForLoadState("networkidle").catch(() => {});
}

/* ------------------------------------------------------------------------- */
/* Execução                                                                  */
/* ------------------------------------------------------------------------- */

async function main() {
  fs.mkdirSync(PNG_DIR, { recursive: true });

  const launchOptions = {
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  };
  if (fs.existsSync(CHROME)) launchOptions.executablePath = CHROME;
  const browser = await chromium.launch(launchOptions);

  const guestContext = await browser.newContext({ viewport: DESKTOP });
  const adminContext = await browser.newContext({ viewport: DESKTOP });
  const participantContext = await browser.newContext({ viewport: DESKTOP });
  const emptyContext = await browser.newContext({ viewport: DESKTOP });
  const mobileGuestContext = await browser.newContext({ viewport: MOBILE, deviceScaleFactor: 1 });
  const mobileParticipantContext = await browser.newContext({
    viewport: MOBILE,
    deviceScaleFactor: 1,
  });
  const mobileAdminContext = await browser.newContext({ viewport: MOBILE, deviceScaleFactor: 1 });
  const tabletContext = await browser.newContext({ viewport: TABLET, deviceScaleFactor: 1 });
  const tabletAdminContext = await browser.newContext({
    viewport: TABLET,
    deviceScaleFactor: 1,
  });

  const guest = await guestContext.newPage();
  const admin = await loginAdmin(adminContext);
  const participant = await loginParticipant(participantContext, CREDENTIALS.participant.username);
  const empty = await loginParticipant(emptyContext, CREDENTIALS.empty_participant.username);

  /* --------------------------------------------------------------------- */
  /* 1. Visitante                                                          */
  /* --------------------------------------------------------------------- */
  console.log("\n[1] Visitante");

  await safeShot(guest, {
    id: "A01-01",
    group: "Autenticação",
    screen: "A01",
    title: "Login de participante",
    state: "Padrão",
    description:
      "Formulário com username, aviso de que o acesso não comprova identidade e link para o login administrativo.",
    target: "/entrar/",
  });

  await safeShot(guest, {
    id: "A01-02",
    group: "Autenticação",
    screen: "A01",
    title: "Login de participante",
    state: "Erro de credenciais",
    description: "Mensagem genérica após username inexistente.",
    before: async (page) => {
      await page.fill("#id_username", "nao_existe_em_screenshot");
      await submit(page, 'form button[type="submit"]');
    },
  });

  await safeShot(guest, {
    id: "A02-01",
    group: "Autenticação",
    screen: "A02",
    title: "Login administrativo",
    state: "Padrão",
    description: "Formulário com username e senha e link para o acesso de participante.",
    target: "/admin/entrar/",
  });

  await safeShot(guest, {
    id: "A02-02",
    group: "Autenticação",
    screen: "A02",
    title: "Login administrativo",
    state: "Erro de credenciais",
    description: "Mensagem genérica após senha incorreta.",
    before: async (page) => {
      await page.fill("#id_username", CREDENTIALS.admin.username);
      await page.fill("#id_password", "senha-incorreta");
      await submit(page, 'form button[type="submit"]');
    },
  });

  await safeShot(guest, {
    id: "I01-01",
    group: "Infraestrutura",
    screen: "I01",
    title: "Healthcheck",
    state: "Aplicação e banco disponíveis",
    description: "Resposta JSON de /health/ com status e banco.",
    target: "/health/",
  });

  await safeShot(guest, {
    id: "I03-01",
    group: "Infraestrutura",
    screen: "I03",
    title: "Página não encontrada",
    state: "404",
    description: "Handler global para endereço inexistente.",
    target: "/rota-que-nao-existe-no-inventario/",
  });

  /* --------------------------------------------------------------------- */
  /* 2. Administração — base                                               */
  /* --------------------------------------------------------------------- */
  console.log("\n[2] Administração — base");

  await safeShot(admin, {
    id: "D01-01",
    group: "Administração",
    screen: "D01",
    title: "Dashboard administrativo",
    state: "Visão inicial",
    description:
      "Ação necessária, votações em andamento, panorama da operação e saúde do catálogo.",
    target: "/admin/",
  });

  await safeShot(admin, {
    id: "D02-01",
    group: "Administração",
    screen: "D02",
    title: "Lista de participantes",
    state: "Lista completa",
    description: "Tabela com administrador somente leitura e participantes ativos.",
    target: "/admin/participantes/",
  });

  await safeShot(admin, {
    id: "D02-02",
    group: "Administração",
    screen: "D02",
    title: "Lista de participantes",
    state: "Resultado de busca",
    description: "Pesquisa parcial por username.",
    target: "/admin/participantes/?q=adm",
  });

  await safeShot(admin, {
    id: "D02-03",
    group: "Administração",
    screen: "D02",
    title: "Lista de participantes",
    state: "Busca sem resultados",
    description: "Estado vazio após pesquisa sem correspondências.",
    target: "/admin/participantes/?q=zzzzzz",
  });

  await safeShot(admin, {
    id: "D03-01",
    group: "Administração",
    screen: "D03",
    title: "Novo participante",
    state: "Formulário padrão",
    description: "Campo username, ajuda sobre ausência de senha e ações.",
    target: "/admin/participantes/novo/",
  });

  await safeShot(admin, {
    id: "D03-02",
    group: "Administração",
    screen: "D03",
    title: "Novo participante",
    state: "Username duplicado",
    description: "Erro de validação case-insensitive ao usar um username existente.",
    before: async (page) => {
      await page.fill("#id_username", CREDENTIALS.participant.username);
      await submit(page, '#conteudo button[type="submit"]');
    },
  });

  await safeShot(admin, {
    id: "D03-03",
    group: "Administração",
    screen: "D03",
    title: "Participante criado",
    state: "Sucesso",
    description: "Mensagem de sucesso e retorno à lista de participantes.",
    before: async (page) => {
      await page.fill("#id_username", "screenshot_convidado");
      await submit(page, '#conteudo button[type="submit"]');
    },
  });

  let invitedEditPath = null;
  await safely("localizar participante convidado", async () => {
    await go(admin, "/admin/participantes/?q=screenshot_convidado");
    invitedEditPath = await admin
      .locator("#conteudo table tbody tr", { hasText: "screenshot_convidado" })
      .locator('a:has-text("Editar")')
      .getAttribute("href");
  });

  if (invitedEditPath) {
    await safeShot(admin, {
      id: "D03-04",
      group: "Administração",
      screen: "D03",
      title: "Editar participante",
      state: "Formulário preenchido",
      description: "Edição do username de um participante existente.",
      target: invitedEditPath,
    });

    await safeShot(admin, {
      id: "D03-05",
      group: "Administração",
      screen: "D03",
      title: "Participante atualizado",
      state: "Sucesso",
      description: "Username alterado e mensagem de confirmação.",
      before: async (page) => {
        await page.fill("#id_username", "screenshot_convidado_editado");
        await submit(page, '#conteudo button[type="submit"]');
      },
    });

    await safeShot(admin, {
      id: "D03-06",
      group: "Administração",
      screen: "D03",
      title: "Participante desativado",
      state: "Inativo",
      description: "Desativação com badge de inativo e mensagem de sucesso.",
      before: async (page) => {
        const row = page.locator("#conteudo table tbody tr", {
          hasText: "screenshot_convidado_editado",
        });
        await submit(page, row.locator('button:has-text("Desativar")'));
      },
    });
  }

  await safeShot(admin, {
    id: "D04-01",
    group: "Administração",
    screen: "D04",
    title: "Importar participantes",
    state: "Formulário padrão",
    description: "Upload de CSV com instruções de formato e atomicidade.",
    target: "/admin/participantes/importar/",
  });

  await safeShot(admin, {
    id: "D04-02",
    group: "Administração",
    screen: "D04",
    title: "Importar participantes",
    state: "Relatório com erros",
    description: "Linhas inválidas, username existente, duplicidade e vírgula não suportada.",
    before: async (page) => {
      await page.setInputFiles("#id_file", fixturePath(FIXTURES.participant_import_invalid));
      await submit(page, 'button:has-text("Validar arquivo")');
    },
  });

  await safeShot(admin, {
    id: "D04-03",
    group: "Administração",
    screen: "D04",
    title: "Importar participantes",
    state: "Prévia válida",
    description: "Lista de usernames válidos e confirmação explícita.",
    target: "/admin/participantes/importar/",
    before: async (page) => {
      await page.setInputFiles("#id_file", fixturePath(FIXTURES.participant_import_valid));
      await submit(page, 'button:has-text("Validar arquivo")');
    },
  });

  await safeShot(admin, {
    id: "D04-04",
    group: "Administração",
    screen: "D04",
    title: "Importar participantes",
    state: "Importação aplicada",
    description: "Mensagem de sucesso e contagem de participantes importados.",
    before: async (page) => {
      await postForm(page, "/admin/participantes/importar/", { action: "apply" });
    },
  });

  /* --------------------------------------------------------------------- */
  /* 3. Catálogo e sincronização                                           */
  /* --------------------------------------------------------------------- */
  console.log("\n[3] Catálogo e sincronização");

  await safeShot(admin, {
    id: "D05-01",
    group: "Catálogo",
    screen: "D05",
    title: "Catálogo",
    state: "Status inicial",
    description:
      "Métricas com número e frase, sincronização, fontes, pendências e histórico recente.",
    target: "/admin/catalogo/",
  });

  await safeShot(admin, {
    id: "D06-01",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Execução parcial existente",
    description: "Resumo, mudanças aplicadas automaticamente e mudanças aprovadas.",
    target: `/admin/catalogo/sincronizacoes/2/`,
  });

  await safeShot(admin, {
    id: "D06-02",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Execução com falha",
    description: "CSV inválido gera execução falha com mensagem de erro e nenhuma mudança.",
    target: "/admin/catalogo/",
    before: async (page) => {
      await page.selectOption("#id_source", { label: "curadoria-local" });
      await page.setInputFiles("#id_file", fixturePath(FIXTURES.catalog_sync_invalid));
      await submit(page, 'button:has-text("Sincronizar catálogo")');
    },
  });
  const failedSyncPath = new URL(admin.url()).pathname;

  await safeShot(admin, {
    id: "D05-02",
    group: "Catálogo",
    screen: "D05",
    title: "Catálogo",
    state: "Última sincronização com falha",
    description: "Histórico atualizado e alerta de erro da última execução.",
    target: "/admin/catalogo/",
  });

  await safeShot(admin, {
    id: "D06-03",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Mudanças pendentes",
    description: "Atualização de personagem, versão e aptidões aguardando revisão.",
    target: "/admin/catalogo/",
    before: async (page) => {
      await page.selectOption("#id_source", { label: "curadoria-local" });
      await page.setInputFiles("#id_file", fixturePath(FIXTURES.catalog_sync_pending));
      await submit(page, 'button:has-text("Sincronizar catálogo")');
    },
  });
  const pendingSyncPath = new URL(admin.url()).pathname;

  await safeShot(admin, {
    id: "D05-03",
    group: "Catálogo",
    screen: "D05",
    title: "Catálogo",
    state: "Mudanças pendentes",
    description: "Indicador de pendências e tabela de revisão na tela de status.",
    target: "/admin/catalogo/",
  });

  await safeShot(admin, {
    id: "D06-04",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Mudança aprovada",
    description: "Aprovação aplica o payload e registra revisor/data.",
    target: pendingSyncPath,
    before: async (page) => {
      const action = await formAction(page, "Aprovar");
      await postForm(page, action, {});
    },
  });

  await safeShot(admin, {
    id: "D06-05",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Mudança rejeitada",
    description: "Rejeição com nota e registro de revisão.",
    before: async (page) => {
      const action = await formAction(page, "Rejeitar");
      await postForm(page, action, { note: "Rejeitada no inventário visual" });
    },
  });

  await safeShot(admin, {
    id: "D06-06",
    group: "Catálogo",
    screen: "D06",
    title: "Detalhe de sincronização",
    state: "Mudanças revisadas",
    description: "Tabela final com estados aprovada, rejeitada e pendente.",
    target: pendingSyncPath,
  });

  await safeShot(admin, {
    id: "D07-01",
    group: "Catálogo",
    screen: "D07",
    title: "Personagens do catálogo",
    state: "Primeira página",
    description: "Tabela paginada com imagem, versões elegíveis e aptidões consolidadas.",
    target: "/admin/catalogo/personagens/",
  });

  await safeShot(admin, {
    id: "D07-02",
    group: "Catálogo",
    screen: "D07",
    title: "Personagens do catálogo",
    state: "Segunda página",
    description: "Navegação de paginação com 50 personagens por página.",
    before: async (page) => {
      await clickNavigate(page, '.pagination a:has-text("Próxima")');
    },
  });

  await safeShot(admin, {
    id: "D07-03",
    group: "Catálogo",
    screen: "D07",
    title: "Personagens do catálogo",
    state: "Busca por personagem",
    description: "Filtro por nome ou identificador estável.",
    target: "/admin/catalogo/personagens/?q=Special",
  });

  await safeShot(admin, {
    id: "D07-04",
    group: "Catálogo",
    screen: "D07",
    title: "Personagens do catálogo",
    state: "Busca sem resultados",
    description: "Estado vazio para pesquisa sem correspondências.",
    target: "/admin/catalogo/personagens/?q=zzzzzz",
  });

  await safeShot(admin, {
    id: "D07-05",
    group: "Catálogo",
    screen: "D07",
    title: "Personagens do catálogo",
    state: "Data de corte alternativa",
    description: "Consulta com corte em 31/12/2025 e menos versões elegíveis.",
    target: "/admin/catalogo/personagens/?cutoff=2025-12-31",
  });

  await safeShot(admin, {
    id: "D08-01",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Acervo completo",
    description:
      "Métricas com link, validação, assets em moldura e personagens sem imagem válida.",
    target: "/admin/catalogo/imagens/",
  });

  await safeShot(admin, {
    id: "D08-02",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Filtro por status inválido",
    description: "Filtro server-side de assets por situação.",
    target: "/admin/catalogo/imagens/?status=invalid",
  });

  await safeShot(admin, {
    id: "D08-03",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Relatório de validação",
    description: "Validação do acervo com problemas, ausências e personagens sem imagem.",
    target: "/admin/catalogo/imagens/",
    before: async (page) => {
      await submit(page, 'button:has-text("Validar acervo agora")');
    },
  });

  await safeShot(admin, {
    id: "D08-04",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Personagens sem imagem válida",
    description: "Seção com personagens sem asset corrente válido.",
    target: "/admin/catalogo/imagens/",
    selector: 'section[aria-labelledby="without-title"]',
  });

  await safeShot(admin, {
    id: "D08-05",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Filtro por status ausente",
    description: "Assets cujo arquivo não foi encontrado no disco.",
    target: "/admin/catalogo/imagens/?status=missing",
  });

  await safeShot(admin, {
    id: "D08-06",
    group: "Catálogo",
    screen: "D08",
    title: "Imagens do catálogo",
    state: "Relatório de validação em destaque",
    description: "Seção do relatório com contagens e problemas encontrados.",
    target: "/admin/catalogo/imagens/",
    before: async (page) => {
      await submit(page, 'button:has-text("Validar acervo agora")');
    },
    selector: 'section[aria-labelledby="report-title"]',
  });

  /* --------------------------------------------------------------------- */
  /* 4. Votações administrativas                                           */
  /* --------------------------------------------------------------------- */
  console.log("\n[4] Votações administrativas");

  await safeShot(admin, {
    id: "V01-01",
    group: "Votações",
    screen: "V01",
    title: "Lista de votações",
    state: "Todos os estados",
    description: "Lista editorial com índice, estado, metadados compactos e duas ações no máximo.",
    target: "/admin/votacoes/",
  });

  await safeShot(admin, {
    id: "V01-02",
    group: "Votações",
    screen: "V01",
    title: "Lista de votações",
    state: "Filtro por abertas",
    description: "Filtro por estado da votação.",
    target: "/admin/votacoes/?status=open",
  });

  await safeShot(admin, {
    id: "V01-03",
    group: "Votações",
    screen: "V01",
    title: "Lista de votações",
    state: "Filtro por agendadas",
    description: "Filtro por votações agendadas.",
    target: "/admin/votacoes/?status=scheduled",
  });

  await safeShot(admin, {
    id: "V01-04",
    group: "Votações",
    screen: "V01",
    title: "Lista de votações",
    state: "Busca sem resultados",
    description: "Estado vazio após pesquisa por título inexistente.",
    target: "/admin/votacoes/?q=zzzzzz",
  });

  await safeShot(admin, {
    id: "V02-01",
    group: "Votações",
    screen: "V02",
    title: "Nova votação",
    state: "Formulário padrão",
    description: "Título, descrição, escolhas, corte, modos e datas com ajuda contextual.",
    target: "/admin/votacoes/nova/",
  });

  await safeShot(admin, {
    id: "V02-02",
    group: "Votações",
    screen: "V02",
    title: "Nova votação",
    state: "Erros de validação",
    description: "Erro de título obrigatório e de data obrigatória no modo automático.",
    before: async (page) => {
      await page.locator("#conteudo form").evaluate((form) => {
        form.noValidate = true;
      });
      await submit(page, '#conteudo button[type="submit"]');
    },
  });

  await safeShot(admin, {
    id: "V02-03",
    group: "Votações",
    screen: "V02",
    title: "Editar votação",
    state: "Rascunho preenchido",
    description: "Edição de configuração permitida apenas em rascunho.",
    target: `/admin/votacoes/${V.draft.id}/editar/`,
  });

  await safeShot(admin, {
    id: "V02-04",
    group: "Votações",
    screen: "V02",
    title: "Votação criada pela interface",
    state: "Sucesso",
    description: "Criação de rascunho e redirecionamento para o detalhe.",
    target: "/admin/votacoes/nova/",
    before: async (page) => {
      await page.fill("#id_title", "[SCREENSHOT] Criada pela interface");
      await page.fill("#id_description", "Rascunho criado durante o inventário visual.");
      await submit(page, '#conteudo button[type="submit"]');
    },
  });

  await safeShot(admin, {
    id: "V02-05",
    group: "Votações",
    screen: "V02",
    title: "Votação atualizada",
    state: "Sucesso",
    description: "Edição de descrição com mensagem de configuração atualizada.",
    target: `/admin/votacoes/${V.draft.id}/editar/`,
    before: async (page) => {
      await page.fill(
        "#id_description",
        "Descrição atualizada durante a captura do inventário visual."
      );
      await submit(page, '#conteudo button[type="submit"]');
    },
  });

  const v03States = [
    ["V03-01", "draft", "Rascunho pronto", "Pré-condições atendidas e ação de abertura disponível."],
    ["V03-02", "draft_blocked", "Rascunho bloqueado", "Pré-condições insuficientes e aviso de bloqueio."],
    ["V03-03", "scheduled", "Agendada", "Configuração congelada e abertura automática futura."],
    ["V03-04", "open", "Aberta", "Ações de encerramento/cancelamento e tabela de cédulas."],
    ["V03-05", "closed", "Encerrada", "Acesso aos resultados e à participação."],
    ["V03-06", "cancelled", "Cancelada", "Votação cancelada com cédulas eliminadas."],
  ];

  for (const [id, key, state, description] of v03States) {
    await safeShot(admin, {
      id,
      group: "Votações",
      screen: "V03",
      title: "Detalhe da votação",
      state,
      description,
      target: `/admin/votacoes/${V[key].id}/`,
    });
  }

  await safeShot(admin, {
    id: "V03-07",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Elegíveis bloqueados fora do rascunho",
    description: "Redirecionamento com mensagem ao tentar alterar elegíveis fora do rascunho.",
    target: `/admin/votacoes/${V.open.id}/elegiveis/`,
  });

  await safeShot(admin, {
    id: "V03-08",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Votação aberta com cédulas",
    description: "Tabela de cédulas com participante e horário, sem escolhas.",
    target: `/admin/votacoes/${V.open_ballots.id}/`,
  });

  await safeShot(admin, {
    id: "V03-09",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Cédula excluída",
    description: "Exclusão administrativa de cédula com votação aberta.",
    before: async (page) => {
      const action = await formAction(page, "Excluir voto", "admin");
      await postForm(page, action, {});
    },
  });

  await safeShot(admin, {
    id: "V03-10",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Exclusão sem cédula",
    description: "Mensagem informativa quando não existe cédula para o participante.",
    target: `/admin/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await postForm(
        page,
        `/admin/votacoes/${V.open_ballots.id}/cedulas/${USERS.empty_participant_id}/excluir/`,
        {}
      );
    },
  });

  await safeShot(admin, {
    id: "V04-01",
    group: "Votações",
    screen: "V04",
    title: "Elegíveis",
    state: "Rascunho com usuários disponíveis",
    description: "Checkboxes de ativos ainda não elegíveis e tabela de elegíveis atuais.",
    target: `/admin/votacoes/${V.draft.id}/elegiveis/`,
  });

  await safeShot(admin, {
    id: "V04-02",
    group: "Votações",
    screen: "V04",
    title: "Elegíveis",
    state: "Elegíveis adicionados",
    description: "Seleção múltipla e mensagem de sucesso.",
    before: async (page) => {
      const boxes = page.locator('#conteudo input[name="users"]');
      const total = await boxes.count();
      for (let index = 0; index < total; index += 1) await boxes.nth(index).check();
      await submit(page, 'button:has-text("Adicionar selecionados")');
    },
  });

  await safeShot(admin, {
    id: "V04-03",
    group: "Votações",
    screen: "V04",
    title: "Elegíveis",
    state: "Todos os ativos já elegíveis",
    description: "Estado que substitui o formulário de inclusão.",
    target: `/admin/votacoes/${V.draft.id}/elegiveis/`,
  });

  await safeShot(admin, {
    id: "V04-04",
    group: "Votações",
    screen: "V04",
    title: "Elegíveis",
    state: "Nenhum elegível",
    description: "Alerta de que a votação não poderá ser aberta sem elegíveis.",
    target: `/admin/votacoes/${V.draft_blocked.id}/elegiveis/`,
  });

  await safeShot(admin, {
    id: "V05-01",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Parciais sem votos",
    description: "Agregados de uma votação aberta ainda sem cédulas.",
    target: `/admin/votacoes/${V.open.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V05-02",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Parciais com votos",
    description: "Agregados parciais de outra votação aberta com cédulas.",
    target: `/admin/votacoes/${V.open_ballots.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V05-03",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Ranking final",
    description: "Ranking com posições, empates e imagens.",
    target: `/admin/votacoes/${V.closed.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V05-04",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Votação cancelada",
    description: "Votações canceladas não possuem resultado oficial.",
    target: `/admin/votacoes/${V.cancelled.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V05-05",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Encerrada sem votos",
    description: "Ranking vazio para votação encerrada sem cédulas.",
    target: `/admin/votacoes/${V.closed_no_ballot.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V06-01",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Aberta sem votos",
    description: "Lista de elegíveis e situação de voto.",
    target: `/admin/votacoes/${V.open.id}/participacao/`,
  });

  await safeShot(admin, {
    id: "V06-02",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Aberta com votos",
    description: "Contagem de votantes e badges de situação.",
    target: `/admin/votacoes/${V.open_ballots.id}/participacao/`,
  });

  await safeShot(admin, {
    id: "V06-03",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Encerrada",
    description: "Participação de votação encerrada.",
    target: `/admin/votacoes/${V.closed.id}/participacao/`,
  });

  await safeShot(admin, {
    id: "V06-04",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Sem elegíveis",
    description: "Estado vazio quando a votação não possui elegíveis.",
    target: `/admin/votacoes/${V.draft_blocked.id}/participacao/`,
  });

  await safeShot(admin, {
    id: "I05-01",
    group: "Infraestrutura",
    screen: "I05",
    title: "Modo participante",
    state: "Banner ativo",
    description: "Administrador navegando com a interface de participante.",
    before: async (page) => {
      await submit(page, 'button:has-text("Modo participante")');
    },
  });

  await safely("retornar ao modo administrativo", async () => {
    await submit(admin, 'button:has-text("Voltar à administração")');
  });

  await safeShot(admin, {
    id: "I02-02",
    group: "Infraestrutura",
    screen: "I02",
    title: "Acesso negado",
    state: "403 — edição de administrador",
    description: "Contas administrativas são somente leitura na área de participantes.",
    target: `/admin/participantes/${USERS.admin_id}/editar/`,
  });

  /* --------------------------------------------------------------------- */
  /* 5. Participante — seleção                                             */
  /* --------------------------------------------------------------------- */
  console.log("\n[5] Participante — seleção");

  await safeShot(participant, {
    id: "P01-01",
    group: "Participante",
    screen: "P01",
    title: "Home de votações",
    state: "Votações disponíveis",
    description: "Votação em destaque e demais votações em lista para o participante elegível.",
    target: "/",
  });

  await safeShot(participant, {
    id: "P02-01",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Votação aberta",
    description: "Cabeçalho, busca, filtros, grid e resumo de seleção.",
    notes:
      "Na aplicação, o resumo de seleção é fixo no rodapé; nesta captura full-page ele foi posicionado estaticamente para não sobrepor o grid.",
    staticSelectors: [".selection-summary"],
    target: `/votacoes/${V.open.id}/`,
  });

  await safeShot(participant, {
    id: "P02-02",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Limite de escolhas atingido",
    description:
      "Três personagens selecionadas e numeradas; demais cards ficam desabilitados.",
    staticSelectors: [".selection-summary"],
    before: async (page) => {
      await selectCharacters(page, 3);
    },
  });

  await safeShot(participant, {
    id: "P03-01",
    group: "Participante",
    screen: "P03",
    title: "Grid de personagens",
    state: "Busca HTMX por 'special'",
    description: "Fragmento atualizado sem recarregar a página, preservando a seleção oculta.",
    before: async (page) => {
      await htmxSearch(page, "special");
    },
    selector: "#character-grid",
  });

  await safeShot(participant, {
    id: "P02-03",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Busca combinada com seleção",
    description: "Página completa após busca HTMX, com resumo OOB e seleção preservada.",
    staticSelectors: [".selection-summary"],
    before: async (page) => {
      await htmxSearch(page, "special");
    },
  });

  await safeShot(participant, {
    id: "P03-02",
    group: "Participante",
    screen: "P03",
    title: "Grid de personagens",
    state: "Busca sem resultados",
    description: "Mensagem de estado vazio no fragmento do grid.",
    target: `/votacoes/${V.open.id}/`,
    before: async (page) => {
      await htmxSearch(page, "zzzzzz");
    },
    selector: "#character-grid",
  });

  await safeShot(participant, {
    id: "P03-03",
    group: "Participante",
    screen: "P03",
    title: "Grid de personagens",
    state: "Busca sem seleção prévia",
    description: "Fragmento HTMX com resultado normal, sem o limite de escolhas atingido.",
    target: `/votacoes/${V.open.id}/`,
    before: async (page) => {
      await htmxSearch(page, "special");
    },
    selector: "#character-grid",
  });

  await safeShot(participant, {
    id: "P02-04",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Erro de quantidade",
    description: "Revisão sem seleção retorna à tela com HTTP 400 e mensagem de validação.",
    staticSelectors: [".selection-summary"],
    target: `/votacoes/${V.open.id}/`,
    before: async (page) => {
      await submitReview(page);
    },
  });

  await safeShot(participant, {
    id: "P02-05",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Votação agendada",
    description: "Aviso de que a votação ainda não está aberta.",
    target: `/votacoes/${V.scheduled.id}/`,
  });

  await safeShot(participant, {
    id: "P02-06",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "404 — rascunho",
    description: "Rascunhos não são acessíveis ao participante.",
    target: `/votacoes/${V.draft.id}/`,
  });

  await safeShot(participant, {
    id: "P02-07",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "404 — cancelada",
    description: "Votações canceladas não são acessíveis.",
    target: `/votacoes/${V.cancelled.id}/`,
  });

  await safeShot(participant, {
    id: "P02-08",
    group: "Participante",
    screen: "P02",
    title: "Seleção de personagens",
    state: "Filtro por aptidão",
    description: "Chip de estratégia aplicado e grid atualizado por HTMX.",
    staticSelectors: [".selection-summary"],
    target: `/votacoes/${V.open.id}/`,
    before: async (page) => {
      await page.locator('.filter-panel__summary').first().click();
      await page.locator('.filter-group input[type="checkbox"]').first().check({ force: true });
      await page.waitForTimeout(1100);
      await page.waitForLoadState("networkidle").catch(() => {});
    },
  });

  await safeShot(participant, {
    id: "P04-01",
    group: "Participante",
    screen: "P04",
    title: "Revisão da cédula",
    state: "Três escolhas",
    description:
      "Revisão com faixa de etapa, ordem das escolhas, aviso de confirmação definitiva e ações de confirmar/voltar.",
    target: `/votacoes/${V.open.id}/`,
    before: async (page) => {
      await selectCharacters(page, 3);
      await submitReview(page);
    },
  });

  /* --------------------------------------------------------------------- */
  /* 6. Participante — cédula e resultados                                 */
  /* --------------------------------------------------------------------- */
  console.log("\n[6] Participante — cédula e resultados");

  const selectedIds = await selectedCharacterIds(participant);

  await safeShot(participant, {
    id: "P05-01",
    group: "Participante",
    screen: "P05",
    title: "Minha cédula",
    state: "Votação aberta",
    description:
      "Voto registrado com faixa de etapa, escolhas em ordem, badge definitivo e data de envio.",
    before: async (page) => {
      await confirmBallot(page);
    },
  });

  await safeShot(participant, {
    id: "P05-02",
    group: "Participante",
    screen: "P05",
    title: "Minha cédula",
    state: "Segundo envio bloqueado",
    description: "Tentativa de reenviar a mesma cédula retorna HTTP 409 com mensagem.",
    before: async (page) => {
      await postForm(page, `/votacoes/${V.open.id}/confirmar/`, {
        character_ids: selectedIds,
      });
    },
  });

  await safeShot(participant, {
    id: "P05-03",
    group: "Participante",
    screen: "P05",
    title: "Minha cédula",
    state: "Votação encerrada",
    description: "Cédula consultável após o encerramento, com acesso ao resultado.",
    target: `/votacoes/${V.closed.id}/cedula/`,
  });

  await safeShot(participant, {
    id: "P06-01",
    group: "Participante",
    screen: "P06",
    title: "Resultado final",
    state: "Ranking com votos",
    description:
      "Resultado com estado encerrado, participação agregada e ranking com barras proporcionais.",
    target: `/votacoes/${V.closed.id}/resultado/`,
  });

  await safeShot(participant, {
    id: "P06-02",
    group: "Participante",
    screen: "P06",
    title: "Resultado final",
    state: "Sem votos",
    description: "Estado vazio para votação encerrada sem cédulas.",
    target: `/votacoes/${V.closed_no_ballot.id}/resultado/`,
  });

  await safeShot(participant, {
    id: "P06-03",
    group: "Participante",
    screen: "P06",
    title: "Resultado final",
    state: "404 antes do encerramento",
    description: "Resultado indisponível enquanto a votação está aberta.",
    target: `/votacoes/${V.open.id}/resultado/`,
  });

  await safeShot(participant, {
    id: "P07-01",
    group: "Participante",
    screen: "P07",
    title: "Histórico",
    state: "Respondidas e encerradas sem resposta",
    description: "Duas seções com votações respondidas e encerradas sem cédula.",
    target: "/historico/",
  });

  /* --------------------------------------------------------------------- */
  /* 7. Conflito de encerramento (P08)                                     */
  /* --------------------------------------------------------------------- */
  console.log("\n[7] Conflito de encerramento");

  await safeShot(participant, {
    id: "P04-02",
    group: "Participante",
    screen: "P04",
    title: "Revisão da cédula",
    state: "Revisão de votação que será encerrada",
    description: "Revisão aberta antes do encerramento administrativo.",
    target: `/votacoes/${V.unavailable.id}/`,
    before: async (page) => {
      await selectCharacters(page, 3);
      await submitReview(page);
    },
  });

  await safely("encerrar votação de indisponibilidade", async () => {
    await go(admin, `/admin/votacoes/${V.unavailable.id}/`);
    await submit(admin, 'button:has-text("Encerrar votação")');
  });

  await safeShot(participant, {
    id: "P08-01",
    group: "Participante",
    screen: "P08",
    title: "Votação indisponível",
    state: "Encerrada durante a revisão",
    description: "Confirmação bloqueada porque a votação deixou de aceitar cédulas (HTTP 409).",
    before: async (page) => {
      await confirmBallot(page);
    },
  });

  /* --------------------------------------------------------------------- */
  /* 8. Administração — acompanhamento                                     */
  /* --------------------------------------------------------------------- */
  console.log("\n[8] Administração — acompanhamento");

  await safeShot(admin, {
    id: "V05-06",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Parciais após voto do participante",
    description: "Agregados atualizados com a cédula recém-registrada.",
    target: `/admin/votacoes/${V.open.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V06-05",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Aberta com voto registrado",
    description: "Participante aparece como votante sem expor escolhas.",
    target: `/admin/votacoes/${V.open.id}/participacao/`,
  });

  await safeShot(admin, {
    id: "V03-11",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Aberta com cédula do participante",
    description: "Tabela de cédulas e ação de encerramento disponível.",
    target: `/admin/votacoes/${V.open.id}/`,
  });

  await safeShot(admin, {
    id: "V03-12",
    group: "Votações",
    screen: "V03",
    title: "Detalhe da votação",
    state: "Encerrada pelo administrador",
    description: "Encerramento com mensagem de sucesso e novos atalhos.",
    before: async (page) => {
      await submit(page, 'button:has-text("Encerrar votação")');
    },
  });

  await safeShot(admin, {
    id: "V05-07",
    group: "Votações",
    screen: "V05",
    title: "Resultados",
    state: "Ranking final após encerramento",
    description: "Ranking definitivo da votação encerrada.",
    target: `/admin/votacoes/${V.open.id}/resultados/`,
  });

  await safeShot(admin, {
    id: "V06-06",
    group: "Votações",
    screen: "V06",
    title: "Participação",
    state: "Encerrada após voto",
    description: "Participação final da votação encerrada.",
    target: `/admin/votacoes/${V.open.id}/participacao/`,
  });

  await safeShot(participant, {
    id: "P05-04",
    group: "Participante",
    screen: "P05",
    title: "Minha cédula",
    state: "Encerrada com resultado",
    description: "Cédula da votação encerrada e acesso ao resultado.",
    target: `/votacoes/${V.open.id}/cedula/`,
  });

  await safeShot(participant, {
    id: "P06-04",
    group: "Participante",
    screen: "P06",
    title: "Resultado final",
    state: "Ranking da votação encerrada",
    description:
      "Resultado final da votação votada pelo participante, com participação e ranking.",
    target: `/votacoes/${V.open.id}/resultado/`,
  });

  await safeShot(participant, {
    id: "P07-02",
    group: "Participante",
    screen: "P07",
    title: "Histórico",
    state: "Após encerramento",
    description: "Histórico com a votação recém-encerrada.",
    target: "/historico/",
  });

  await safeShot(admin, {
    id: "D01-02",
    group: "Administração",
    screen: "D01",
    title: "Dashboard administrativo",
    state: "Após o fluxo completo",
    description:
      "Ação necessária e panorama atualizados após votos, encerramentos e revisões.",
    target: "/admin/",
  });

  /* --------------------------------------------------------------------- */
  /* 9. Erros, modo participante e estados vazios                          */
  /* --------------------------------------------------------------------- */
  console.log("\n[9] Erros e estados vazios");

  await safeShot(participant, {
    id: "I02-01",
    group: "Infraestrutura",
    screen: "I02",
    title: "Acesso negado",
    state: "403 — participante na área administrativa",
    description: "Participante autenticado sem privilégio administrativo.",
    target: "/admin/",
  });

  await safeShot(empty, {
    id: "P01-02",
    group: "Participante",
    screen: "P01",
    title: "Home de votações",
    state: "Sem votações",
    description: "Estado vazio para participante sem elegibilidade.",
    target: "/",
  });

  await safeShot(empty, {
    id: "P07-03",
    group: "Participante",
    screen: "P07",
    title: "Histórico",
    state: "Sem histórico",
    description: "Estados vazios nas duas seções do histórico.",
    target: "/historico/",
  });

  await safeShot(empty, {
    id: "I02-03",
    group: "Infraestrutura",
    screen: "I02",
    title: "Acesso negado",
    state: "403 — participante não elegível",
    description: "Participante sem elegibilidade tenta abrir uma votação.",
    target: `/votacoes/${V.open.id}/`,
  });

  await safeShot(participant, {
    id: "I04-01",
    group: "Infraestrutura",
    screen: "I04",
    title: "Erro interno",
    state: "500",
    description: "Template 500 renderizado com o layout base e ação de retorno.",
    beforeGoto: async (page) => {
      const local500 = path.join(ROOT, "500.html");
      const fallback500 = path.join(PROJECT_ROOT, "var/screenshots/500.html");
      const html = fs.readFileSync(fs.existsSync(local500) ? local500 : fallback500, "utf8");
      await page.route("**/__screenshot_500__", (route) =>
        route.fulfill({ status: 500, contentType: "text/html; charset=utf-8", body: html })
      );
    },
    target: "/__screenshot_500__",
  });

  await safeShot(admin, {
    id: "I06-01",
    group: "Infraestrutura",
    screen: "I06",
    title: "Mensagem global",
    state: "Sucesso",
    description: "Feedback de ação administrativa concluída.",
    target: `/admin/votacoes/${V.cancelled.id}/`,
    before: async (page) => {
      await postForm(page, `/admin/votacoes/${V.cancelled.id}/cancelar/`, {
        reason: "Repetição idempotente no inventário visual",
      });
    },
  });

  await safeShot(admin, {
    id: "I06-02",
    group: "Infraestrutura",
    screen: "I06",
    title: "Mensagem global",
    state: "Aviso",
    description: "Sincronização concluída com mudanças pendentes de aprovação.",
    target: "/admin/catalogo/",
    before: async (page) => {
      await page.selectOption("#id_source", { label: "curadoria-local" });
      await page.setInputFiles("#id_file", fixturePath(FIXTURES.catalog_sync_pending));
      await submit(page, 'button:has-text("Sincronizar catálogo")');
    },
  });

  await safeShot(admin, {
    id: "I06-03",
    group: "Infraestrutura",
    screen: "I06",
    title: "Mensagem global",
    state: "Erro",
    description: "Tentativa de agendar votação manual gera feedback de erro.",
    target: `/admin/votacoes/${V.draft.id}/`,
    before: async (page) => {
      await postForm(page, `/admin/votacoes/${V.draft.id}/agendar/`, {});
    },
  });

  await safeShot(admin, {
    id: "I06-04",
    group: "Infraestrutura",
    screen: "I06",
    title: "Mensagem global",
    state: "Informação",
    description: "Exclusão de cédula inexistente gera mensagem informativa.",
    target: `/admin/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await postForm(
        page,
        `/admin/votacoes/${V.open_ballots.id}/cedulas/${USERS.empty_participant_id}/excluir/`,
        {}
      );
    },
  });

  await safeShot(admin, {
    id: "I07-01",
    group: "Infraestrutura",
    screen: "I07",
    title: "Badges de status",
    state: "Estados de votação",
    description: "Rascunho, agendada, aberta, encerrada e cancelada.",
    target: "/admin/votacoes/",
    selector: ".av-voting-list",
  });

  await safeShot(admin, {
    id: "I07-02",
    group: "Infraestrutura",
    screen: "I07",
    title: "Badges de status",
    state: "Estados de mudança de catálogo",
    description: "Aplicada automaticamente, aprovada, rejeitada e pendente.",
    target: pendingSyncPath,
    selector: ".change-list",
  });

  await safeShot(admin, {
    id: "I07-03",
    group: "Infraestrutura",
    screen: "I07",
    title: "Badges de status",
    state: "Estados de imagem",
    description: "Válida, inválida e ausente.",
    target: "/admin/catalogo/imagens/",
    selector: "#conteudo .table tbody",
  });

  /* --------------------------------------------------------------------- */
  /* 10. Componentes                                                       */
  /* --------------------------------------------------------------------- */
  console.log("\n[10] Componentes");

  await safely("liberar seleção do participante", async () => {
    await releaseParticipantBallot(admin, V.open_ballots.id, USERS.participant_id);
  });

  await safeShot(guest, {
    id: "C01",
    group: "Componentes",
    screen: "C",
    title: "Card de autenticação",
    state: "Componente",
    description: "Superfície do formulário de login com cabeçalho, campos e aviso.",
    target: "/entrar/",
    selector: ".auth-card",
  });

  await safeShot(participant, {
    id: "C02",
    group: "Componentes",
    screen: "C",
    title: "Cabeçalho do participante",
    state: "Componente",
    description: "Marca, navegação principal, usuário e ações de sessão.",
    target: "/",
    selector: ".site-header",
  });

  await safeShot(participant, {
    id: "C03",
    group: "Componentes",
    screen: "C",
    title: "Card de votação",
    state: "Componente",
    description: "Card com badge, escolhas, título, descrição e ação.",
    target: "/",
    selector: ".voting-card",
  });

  await safeShot(participant, {
    id: "C04",
    group: "Componentes",
    screen: "C",
    title: "Rodapé",
    state: "Componente",
    description: "Rodapé institucional do shell de participante.",
    target: "/",
    selector: ".site-footer",
  });

  await safeShot(participant, {
    id: "C05",
    group: "Componentes",
    screen: "C",
    title: "Barra de filtros",
    state: "Componente",
    description: "Busca, chips de aptidão e limpeza de filtros.",
    target: `/votacoes/${V.open_ballots.id}/`,
    selector: ".filters",
  });

  await safeShot(participant, {
    id: "C06",
    group: "Componentes",
    screen: "C",
    title: "Grupo de chips",
    state: "Componente",
    description: "Checkboxes visuais de aptidão com estado marcado.",
    target: `/votacoes/${V.open_ballots.id}/`,
    selector: ".filter-panel",
    before: async (page) => {
      await page.locator('.filter-panel__summary').first().click();
    },
  });

  await safeShot(participant, {
    id: "C07",
    group: "Componentes",
    screen: "C",
    title: "Card de personagem",
    state: "Não selecionado",
    description: "Imagem, nome e checkbox oculto do card de personagem.",
    target: `/votacoes/${V.open_ballots.id}/`,
    selector: ".character-option",
  });

  await safeShot(participant, {
    id: "C08",
    group: "Componentes",
    screen: "C",
    title: "Card de personagem",
    state: "Selecionado",
    description: "Card com número de ordem, check visual e estado selecionado.",
    target: `/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await page.locator('input[name="character_ids"]').first().check();
    },
    selector: '.character-option[data-selected="true"]',
  });

  await safeShot(participant, {
    id: "C09",
    group: "Componentes",
    screen: "C",
    title: "Card de personagem",
    state: "Desabilitado pelo limite",
    description: "Card desabilitado pelo limite, com borda tracejada e conteúdo legível.",
    target: `/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await selectCharacters(page, 3);
    },
    selector: '.character-option[data-disabled="true"]',
  });

  await safeShot(participant, {
    id: "C10",
    group: "Componentes",
    screen: "C",
    title: "Resumo de seleção",
    state: "Componente",
    description: "Contador, miniaturas, status acessível e botão de revisão.",
    target: `/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await selectCharacters(page, 2);
    },
    selector: "#selection-summary",
  });

  await safeShot(participant, {
    id: "C11",
    group: "Componentes",
    screen: "C",
    title: "Lista de revisão",
    state: "Componente",
    description: "Escolhas ordenadas com posição, retrato e nome antes da confirmação.",
    target: `/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await selectCharacters(page, 3);
      await submitReview(page);
    },
    selector: ".review-list",
  });

  await safeShot(participant, {
    id: "C12",
    group: "Componentes",
    screen: "C",
    title: "Resumo da cédula",
    state: "Componente",
    description: "Voto registrado com estado, data de envio e escolhas definitivas.",
    target: `/votacoes/${V.closed.id}/cedula/`,
    selector: ".ballot-panel",
  });

  await safeShot(participant, {
    id: "C13",
    group: "Componentes",
    screen: "C",
    title: "Lista de resultado",
    state: "Componente",
    description: "Ranking com posição ampliada, retrato, nome, votos e barra proporcional.",
    target: `/votacoes/${V.closed.id}/resultado/`,
    selector: ".result-list",
  });

  await safeShot(admin, {
    id: "C14",
    group: "Componentes",
    screen: "C",
    title: "Grade de indicadores",
    state: "Componente",
    description: "Faixa de métricas número + frase + link do dashboard.",
    target: "/admin/",
    selector: ".dashboard-metrics",
  });

  await safeShot(admin, {
    id: "C15",
    group: "Componentes",
    screen: "C",
    title: "Tabela administrativa",
    state: "Componente",
    description: "Tabela com cabeçalho, linhas, badges e ações.",
    target: "/admin/participantes/",
    selector: ".table",
  });

  await safeShot(admin, {
    id: "C16",
    group: "Componentes",
    screen: "C",
    title: "Paginação",
    state: "Componente",
    description: "Navegação entre páginas do catálogo.",
    target: "/admin/catalogo/personagens/",
    selector: ".pagination",
  });

  await safeShot(admin, {
    id: "C17",
    group: "Componentes",
    screen: "C",
    title: "Estado vazio",
    state: "Componente",
    description: "Bloco tracejado para listas e buscas sem resultado.",
    target: "/admin/participantes/?q=zzzzzz",
    selector: ".empty-state",
  });

  await safeShot(admin, {
    id: "C18",
    group: "Componentes",
    screen: "C",
    title: "Definition list",
    state: "Componente",
    description: "Pares termo/descrição da configuração da votação.",
    target: `/admin/votacoes/${V.closed.id}/`,
    selector: ".detail-list",
  });

  await safeShot(admin, {
    id: "C19",
    group: "Componentes",
    screen: "C",
    title: "Bloco de código",
    state: "Componente",
    description: "Prévia do payload proposto em uma mudança de catálogo.",
    target: `/admin/catalogo/sincronizacoes/2/`,
    before: async (page) => {
      const details = page.locator("#conteudo details").first();
      if (await details.count()) await details.locator("summary").click();
    },
    selector: ".code-block",
  });

  await safeShot(admin, {
    id: "C20",
    group: "Componentes",
    screen: "C",
    title: "Grupo de formulário",
    state: "Componente",
    description: "Label, controle, ajuda contextual e espaçamento.",
    target: "/admin/votacoes/nova/",
    selector: ".form-group",
  });

  await safeShot(admin, {
    id: "C21",
    group: "Componentes",
    screen: "C",
    title: "Badges de status de votação",
    state: "Componente",
    description: "Rascunho, agendada, aberta, encerrada e cancelada na mesma lista.",
    target: "/admin/votacoes/",
    selector: ".av-voting-list",
  });

  await safeShot(admin, {
    id: "C22",
    group: "Componentes",
    screen: "C",
    title: "Alerta de erro",
    state: "Componente",
    description: "Alerta vermelho de falha de sincronização.",
    target: failedSyncPath,
    selector: ".alert",
  });

  await safeShot(admin, {
    id: "C23",
    group: "Componentes",
    screen: "C",
    title: "Lista simples",
    state: "Componente",
    description: "Lista de pré-condições e versões sem marcadores.",
    target: `/admin/votacoes/${V.draft.id}/`,
    selector: ".av-check-list",
  });

  await safeShot(admin, {
    id: "C24",
    group: "Componentes",
    screen: "C",
    title: "Mensagem global",
    state: "Componente",
    description: "Mensagem de sucesso com role=status e aria-live.",
    target: `/admin/votacoes/${V.cancelled.id}/`,
    before: async (page) => {
      await postForm(
        page,
        `/admin/votacoes/${V.open_ballots.id}/cedulas/${USERS.empty_participant_id}/excluir/`,
        {}
      );
    },
    selector: ".messages",
  });

  await safeShot(admin, {
    id: "C25",
    group: "Componentes",
    screen: "C",
    title: "Barra lateral administrativa",
    state: "Componente",
    description: "Marca, navegação, usuário, modo participante e logout.",
    target: "/admin/",
    selector: ".admin-sidebar",
  });

  await safeShot(admin, {
    id: "C26",
    group: "Componentes",
    screen: "C",
    title: "Topbar administrativa",
    state: "Componente",
    description: "Título, subtítulo e ações da página.",
    target: "/admin/",
    selector: ".admin-topbar",
  });

  await safeShot(admin, {
    id: "C27",
    group: "Componentes",
    screen: "C",
    title: "Miniatura de personagem",
    state: "Componente",
    description: "Miniatura 48×48 com badge de status de imagem.",
    target: "/admin/catalogo/personagens/",
    selector: ".character-thumb",
  });

  await safeShot(participant, {
    id: "C28",
    group: "Componentes",
    screen: "C",
    title: "Cabeçalho de página",
    state: "Componente",
    description: "Título, contexto e ação de retorno.",
    target: "/historico/",
    selector: ".page-header",
  });

  await safeShot(participant, {
    id: "C29",
    group: "Componentes",
    screen: "C",
    title: "Status de seleção",
    state: "Componente",
    description: "Texto acessível com aria-live sobre a seleção atual.",
    target: `/votacoes/${V.open_ballots.id}/`,
    before: async (page) => {
      await selectCharacters(page, 1);
    },
    selector: "[data-selection-status]",
  });

  await safeShot(admin, {
    id: "C30",
    group: "Componentes",
    screen: "C",
    title: "Badges de status de imagem",
    state: "Componente",
    description: "Válida, inválida e ausente na lista de assets.",
    target: "/admin/catalogo/imagens/",
    selector: "#conteudo .table tbody",
  });

  /* --------------------------------------------------------------------- */
  /* 11. Responsivo                                                        */
  /* --------------------------------------------------------------------- */
  console.log("\n[11] Responsivo");

  const mobileGuest = await mobileGuestContext.newPage();
  const mobileParticipant = await loginParticipant(
    mobileParticipantContext,
    CREDENTIALS.participant.username
  );
  const mobileAdmin = await loginAdmin(mobileAdminContext);
  const tablet = await loginParticipant(tabletContext, CREDENTIALS.participant.username);
  const tabletAdmin = await loginAdmin(tabletAdminContext);

  await safeShot(mobileGuest, {
    id: "R01",
    group: "Responsivo",
    screen: "R",
    title: "Login de participante",
    state: "Móvel 390×844",
    description: "Layout de autenticação em coluna única.",
    target: "/entrar/",
  });

  await safeShot(mobileParticipant, {
    id: "R02",
    group: "Responsivo",
    screen: "R",
    title: "Home de votações",
    state: "Móvel 390×844",
    description: "Cards de votação empilhados.",
    target: "/",
  });

  await safeShot(mobileParticipant, {
    id: "R03",
    group: "Responsivo",
    screen: "R",
    title: "Seleção de personagens",
    state: "Móvel 390×844",
    description: "Filtros, grid e resumo de seleção em viewport móvel.",
    staticSelectors: [".selection-summary"],
    target: `/votacoes/${V.open_ballots.id}/`,
  });

  await safeShot(mobileParticipant, {
    id: "R04",
    group: "Responsivo",
    screen: "R",
    title: "Minha cédula",
    state: "Móvel 390×844",
    description: "Cédula e cabeçalho em viewport móvel.",
    target: `/votacoes/${V.closed.id}/cedula/`,
  });

  await safeShot(mobileParticipant, {
    id: "R05",
    group: "Responsivo",
    screen: "R",
    title: "Histórico",
    state: "Móvel 390×844",
    description: "Seções de histórico empilhadas.",
    target: "/historico/",
  });

  await safeShot(mobileParticipant, {
    id: "R06",
    group: "Responsivo",
    screen: "R",
    title: "Resultado final",
    state: "Móvel 390×844",
    description: "Ranking em viewport móvel.",
    target: `/votacoes/${V.closed.id}/resultado/`,
  });

  await safeShot(mobileAdmin, {
    id: "R07",
    group: "Responsivo",
    screen: "R",
    title: "Dashboard administrativo",
    state: "Móvel 390×844",
    description: "Shell administrativo em coluna única, com ação necessária na primeira dobra.",
    target: "/admin/",
  });

  await safeShot(mobileAdmin, {
    id: "R08",
    group: "Responsivo",
    screen: "R",
    title: "Detalhe da votação",
    state: "Móvel 390×844",
    description: "Configuração, pré-condições e ações empilhadas.",
    target: `/admin/votacoes/${V.draft.id}/`,
  });

  await safeShot(mobileAdmin, {
    id: "R09",
    group: "Responsivo",
    screen: "R",
    title: "Imagens do catálogo",
    state: "Móvel 390×844",
    description: "Indicadores, filtros e tabela com rolagem horizontal.",
    target: "/admin/catalogo/imagens/",
  });

  await safeShot(tablet, {
    id: "R10",
    group: "Responsivo",
    screen: "R",
    title: "Seleção de personagens",
    state: "Tablet 820×1180",
    description: "Grid de personagens em largura intermediária.",
    target: `/votacoes/${V.open_ballots.id}/`,
  });

  await safeShot(tabletAdmin, {
    id: "R11",
    group: "Responsivo",
    screen: "R",
    title: "Lista de votações",
    state: "Tablet 820×1180",
    description: "Lista editorial administrativa em largura intermediária.",
    target: "/admin/votacoes/",
  });

  await safeShot(mobileAdmin, {
    id: "R12",
    group: "Responsivo",
    screen: "R",
    title: "Participantes",
    state: "Móvel 390×844",
    description: "Filtros e tabela de participantes convertida em cartões.",
    target: "/admin/participantes/",
  });

  await safeShot(mobileAdmin, {
    id: "R13",
    group: "Responsivo",
    screen: "R",
    title: "Catálogo",
    state: "Móvel 390×844",
    description: "Métricas, sincronização e fontes em coluna única.",
    target: "/admin/catalogo/",
  });

  await safeShot(mobileAdmin, {
    id: "R14",
    group: "Responsivo",
    screen: "R",
    title: "Lista de votações",
    state: "Móvel 390×844",
    description: "Lista editorial com índice, estado e ações empilhadas.",
    target: "/admin/votacoes/",
  });

  /* Matriz de breakpoints: 360, 480, 768, 1024 e 1280 px. */
  const BREAKPOINT_WIDTHS = [360, 480, 768, 1024, 1280];
  const BREAKPOINT_PAGES = [
    {
      page: participant,
      path: "/",
      title: "Home de votações",
      description: "Cards, destaque e histórico em largura de breakpoint.",
    },
    {
      page: participant,
      path: `/votacoes/${V.open_ballots.id}/`,
      title: "Seleção de personagens",
      description: "Grid, busca, filtros e barra de escolhas no breakpoint.",
    },
    {
      page: admin,
      path: "/admin/",
      title: "Dashboard administrativo",
      description: "Shell, sidebar/drawer, ação necessária e métricas no breakpoint.",
    },
    {
      page: admin,
      path: "/admin/votacoes/",
      title: "Lista de votações",
      description: "Lista editorial e ações administrativas no breakpoint.",
    },
  ];
  let breakpointIndex = 0;
  for (const width of BREAKPOINT_WIDTHS) {
    await participant.setViewportSize({ width, height: 900 });
    await admin.setViewportSize({ width, height: 900 });
    for (const item of BREAKPOINT_PAGES) {
      breakpointIndex += 1;
      await safeShot(item.page, {
        id: `W${String(breakpointIndex).padStart(2, "0")}`,
        group: "Breakpoints",
        screen: "W",
        title: item.title,
        state: `${width}×900`,
        description: item.description,
        target: item.path,
      });
    }
  }

  /* --------------------------------------------------------------------- */
  /* Fechamento                                                            */
  /* --------------------------------------------------------------------- */
  await mobileGuestContext.close();
  await mobileParticipantContext.close();
  await mobileAdminContext.close();
  await tabletContext.close();
  await tabletAdminContext.close();
  await guestContext.close();
  await adminContext.close();
  await participantContext.close();
  await emptyContext.close();
  await browser.close();

  writeInventory();
}

/* ------------------------------------------------------------------------- */
/* Inventário HTML/JSON                                                      */
/* ------------------------------------------------------------------------- */

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function groupSummary() {
  const counts = new Map();
  for (const entry of manifest) {
    counts.set(entry.group, (counts.get(entry.group) || 0) + 1);
  }
  return Array.from(counts.entries()).map(([group, count]) => ({ group, count }));
}

function writeInventory() {
  const generatedAt = new Date().toISOString();
  const payload = {
    generated_at: generatedAt,
    base_url: BASE,
    scenario: {
      generated_at: SCENARIO.generated_at,
      counts: SCENARIO.counts,
      votings: V,
      credentials: CREDENTIALS,
    },
    flow: FLOW,
    summary: groupSummary(),
    screenshots: manifest,
    failures,
  };

  fs.writeFileSync(path.join(ROOT, "manifest.json"), JSON.stringify(payload, null, 2));
  fs.writeFileSync(path.join(ROOT, "flow.json"), JSON.stringify(FLOW, null, 2));

  const groups = groupSummary();
  const sections = groups
    .map(({ group, count }) => {
      const items = manifest.filter((entry) => entry.group === group);
      const cards = items
        .map(
          (entry) => `
          <article class="card" id="${escapeHtml(entry.id)}">
            <a class="shot" href="${escapeHtml(entry.file)}" target="_blank" rel="noreferrer">
              <img src="${escapeHtml(entry.file)}" alt="${escapeHtml(entry.title)} — ${escapeHtml(
            entry.state
          )}" loading="lazy">
            </a>
            <div class="card-body">
              <div class="card-kicker"><code>${escapeHtml(entry.id)}</code> <span>${escapeHtml(
            entry.screen
          )}</span></div>
              <h3>${escapeHtml(entry.title)}</h3>
              <p class="state">${escapeHtml(entry.state)}</p>
              <p>${escapeHtml(entry.description)}</p>
              ${
                entry.notes
                  ? `<p class="note"><strong>Nota:</strong> ${escapeHtml(entry.notes)}</p>`
                  : ""
              }
              <dl>
                <dt>URL</dt><dd><code>${escapeHtml(entry.url)}</code></dd>
                ${
                  entry.selector
                    ? `<dt>Seletor</dt><dd><code>${escapeHtml(entry.selector)}</code></dd>`
                    : ""
                }
                <dt>Viewport</dt><dd>${entry.viewport.width}×${entry.viewport.height}</dd>
                <dt>Arquivo</dt><dd><code>${escapeHtml(entry.file)}</code> (${Math.round(
            entry.bytes / 1024
          )} KB)</dd>
              </dl>
            </div>
          </article>`
        )
        .join("\n");
      return `
      <section class="group" id="grupo-${escapeHtml(
        group.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")
      )}">
        <div class="group-head">
          <h2>${escapeHtml(group)}</h2>
          <span>${count} captura(s)</span>
        </div>
        <div class="grid">
          ${cards}
        </div>
      </section>`;
    })
    .join("\n");

  const flowItems = FLOW.map(
    (phase) => `
      <li>
        <strong>${escapeHtml(phase.phase)}</strong>
        <p>${escapeHtml(phase.description)}</p>
        ${
          phase.screens
            ? `<p class="screens">Telas: ${phase.screens.map((screen) => `<code>${escapeHtml(screen)}</code>`).join(" ")}</p>`
            : ""
        }
      </li>`
  ).join("\n");

  const summaryRows = groups
    .map(
      ({ group, count }) =>
        `<tr><td>${escapeHtml(group)}</td><td>${count}</td><td><a href="#grupo-${escapeHtml(
          group.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")
        )}">Ver seção</a></td></tr>`
    )
    .join("\n");

  const failuresBlock = failures.length
    ? `<section class="failures"><h2>Falhas de captura</h2><ul>${failures
        .map((failure) => `<li><code>${escapeHtml(failure.id)}</code>: ${escapeHtml(failure.error)}</li>`)
        .join("")}</ul></section>`
    : "";

  const html = `<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inventário visual — Uma Voting</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6fa;
      --surface: #ffffff;
      --ink: #202431;
      --muted: #747b8c;
      --border: #e5e7ef;
      --primary: #7771d8;
      --primary-soft: #efedfb;
      --radius: 12px;
      --shadow: 0 10px 30px rgb(32 36 49 / 8%);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    a { color: #4f49b8; }
    .page { width: min(100% - 32px, 1500px); margin: 0 auto; padding: 32px 0 64px; }
    header.hero {
      background: linear-gradient(135deg, #2e2a63, #7771d8);
      color: white;
      border-radius: 20px;
      padding: 36px;
      box-shadow: var(--shadow);
    }
    header.hero h1 { margin: 0 0 8px; font-size: clamp(1.8rem, 4vw, 2.6rem); }
    header.hero p { margin: 0; max-width: 900px; color: #eceafe; }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }
    .meta span {
      background: rgb(255 255 255 / 14%);
      border: 1px solid rgb(255 255 255 / 25%);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 0.82rem;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      margin-top: 24px;
      box-shadow: var(--shadow);
    }
    .panel h2 { margin-top: 0; }
    .flow { margin: 0; padding-left: 22px; }
    .flow li { margin-bottom: 12px; }
    .flow p { margin: 2px 0; color: var(--muted); }
    .flow .screens code { margin-right: 4px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { text-align: left; border-bottom: 1px solid var(--border); padding: 8px 10px; }
    th { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .group { margin-top: 40px; }
    .group-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
    .group-head h2 { margin: 0 0 4px; }
    .group-head span { color: var(--muted); font-size: 0.9rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 20px;
      margin-top: 16px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
    }
    .shot {
      display: block;
      background: #eef0f7;
      border-bottom: 1px solid var(--border);
      max-height: 360px;
      overflow: hidden;
    }
    .shot img { width: 100%; height: auto; display: block; }
    .card-body { padding: 16px; }
    .card-kicker { display: flex; align-items: center; gap: 8px; font-size: 0.78rem; color: var(--muted); }
    .card-kicker code { background: var(--primary-soft); color: #4f49b8; padding: 2px 6px; border-radius: 6px; }
    .card h3 { margin: 6px 0 2px; font-size: 1.02rem; }
    .state { margin: 0 0 8px; color: var(--primary); font-weight: 600; font-size: 0.85rem; }
    .note {
      border-left: 3px solid #c58a32;
      background: #fbf3e5;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.78rem;
      color: #6b4f1f;
    }
    .card p { margin: 0 0 10px; font-size: 0.86rem; color: #4b5162; }
    .card dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; margin: 0; font-size: 0.74rem; }
    .card dt { color: var(--muted); }
    .card dd { margin: 0; overflow-wrap: anywhere; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.92em; }
    .failures { border: 1px solid #e7b4ba; background: #fbeaec; border-radius: var(--radius); padding: 20px; margin-top: 24px; }
    .failures h2 { margin-top: 0; }
    @media (max-width: 720px) {
      .page { width: min(100% - 20px, 1500px); padding-top: 12px; }
      header.hero { padding: 24px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>Inventário visual — Uma Voting</h1>
      <p>
        Captura das telas e dos componentes da aplicação em cenários de uso reais,
        produzida por um fluxo Playwright sobre uma instância isolada com banco clonado.
      </p>
      <div class="meta">
        <span>${manifest.length} capturas</span>
        <span>${groups.length} grupos</span>
        <span>Base: ${escapeHtml(BASE)}</span>
        <span>Gerado em ${escapeHtml(generatedAt)}</span>
      </div>
    </header>

    <section class="panel">
      <h2>Fluxo de teste</h2>
      <ol class="flow">
        ${flowItems}
      </ol>
    </section>

    <section class="panel">
      <h2>Resumo por grupo</h2>
      <table>
        <thead><tr><th>Grupo</th><th>Capturas</th><th></th></tr></thead>
        <tbody>${summaryRows}</tbody>
      </table>
    </section>

    ${failuresBlock}

    ${sections}
  </div>
</body>
</html>`;

  fs.writeFileSync(path.join(ROOT, "index.html"), html, "utf8");

  console.log(`\nInventário gerado:`);
  console.log(`  ${path.join(ROOT, "index.html")}`);
  console.log(`  ${path.join(ROOT, "manifest.json")}`);
  console.log(`  ${path.join(ROOT, "flow.json")}`);
  console.log(`  ${manifest.length} capturas, ${failures.length} falha(s).`);
}

main().catch(async (error) => {
  console.error("\nFalha fatal na captura:", error);
  failures.push({ id: "fatal", error: error.stack || error.message });
  try {
    writeInventory();
  } catch (writeError) {
    console.error("Não foi possível escrever o inventário parcial:", writeError.message);
  }
  process.exitCode = 1;
});
