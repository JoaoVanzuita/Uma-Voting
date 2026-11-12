"""Smoke E2E opcional do fluxo administrativo de importação externa.

Requer instalação manual:
    uvx playwright install chromium
    pytest -m e2e

Sem Playwright instalado, o teste é ignorado.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.factories import (  # noqa: E402
    DEFAULT_ADMIN_PASSWORD,
    AdminUserFactory,
    CatalogSourceFactory,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_admin_abre_formulario_de_importacao_externa(live_server):
    admin = AdminUserFactory(username="smoke-admin-import")
    CatalogSourceFactory(
        name="umamusume-global",
        adapter="umamusume-global",
        enabled=True,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{live_server.url}/admin/entrar/")
            page.fill("#id_username", admin.username)
            page.fill("#id_password", DEFAULT_ADMIN_PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_url(f"{live_server.url}/admin/")

            page.goto(f"{live_server.url}/admin/catalogo/importar/")
            content = page.content()
            assert "Importar catálogo externo" in content
            assert "umamusume-global" in content
            assert "Fonte externa" in content
            assert "Licença" not in content
        finally:
            browser.close()
