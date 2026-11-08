"""Smoke tests E2E opcionais com Playwright.

Requer instalação manual:
    uvx playwright install chromium
    pytest -m e2e

Sem Playwright instalado, os testes são ignorados.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.factories import ParticipantFactory  # noqa: E402

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_participante_faz_login_e_ve_home(live_server):
    participant = ParticipantFactory(username="smoke-participante")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{live_server.url}/entrar/")
            page.fill("#id_username", participant.username)
            page.click("button[type=submit]")
            page.wait_for_url(f"{live_server.url}/")
            assert participant.username in page.content()
        finally:
            browser.close()
