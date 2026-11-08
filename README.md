# Uma Voting

Sistema web para organizar votações de banimento de personagens de
Umamusume: Pretty Derby em uma comunidade fechada.

Monólito Django server-rendered (Django Templates + HTMX + Bootstrap), com
PostgreSQL, Gunicorn e Caddy em Docker Compose.

## Funcionalidades

- Login de participante por username e login administrativo com senha.
- Cadastro, edição, desativação e importação CSV de participantes.
- Catálogo curado de personagens, versões, aptidões e imagens locais.
- Sincronização híbrida: novas personagens são aplicadas; alterações ficam pendentes.
- Importação e validação de imagens WebP 256 × 256 com placeholder local.
- Criação e configuração de votações em rascunho, com elegíveis e data de corte.
- Abertura manual e automática, encerramento, cancelamento e recuperação de janelas.
- Cédula definitiva com revisão, confirmação, privacidade e exclusão administrativa.
- Resultados agregados, participação e ranking final com dense rank.
- Histórico do participante e painel administrativo.

## Requisitos

- Python 3.14
- PostgreSQL 18
- `uv`
- Docker e Docker Compose (opcional para desenvolvimento e produção)

## Desenvolvimento

```bash
cp .env.example .env
uv sync
docker compose up --build
```

Sem Docker:

```bash
uv sync
export DATABASE_URL=postgres://uma_voting:uma_voting@localhost:5432/uma_voting
uv run python manage.py migrate
uv run python manage.py create_admin --username admin
uv run python manage.py runserver
```

## Testes e qualidade

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python manage.py check --deploy --settings=config.settings.prod
uv run --with pip-audit pip-audit
```

Testes usam PostgreSQL real; SQLite não é suportado. Testes de concorrência e tempo
cobrem os fluxos críticos.

Smoke tests E2E opcionais:

```bash
uvx playwright install chromium
uv run pytest -m e2e
```

## Operação

- Release: `scripts/release.sh` executa `migrate`, `createcachetable` e `collectstatic`.
- Scheduler: `python manage.py run_scheduler --interval 60`.
- Sincronização diária do catálogo: `scripts/sync_catalog.sh` às 03:00.
- Backup: `scripts/backup.sh`; restauração: `scripts/restore.sh`.
- Limpeza de sessões: `python manage.py clearsessions` diariamente.

Catálogo Global oficial (portal `umamusume.com`):

```bash
# baixa o elenco e os ícones oficiais para var/import/global/
uv run python scripts/fetch_global_assets.py
```

O script gera `catalog.csv`, `images.csv` e `global-metadata.json`. Datas e
aptidões vêm do GameTora; as personagens ainda não lançadas no Global ficam com
data futura e são filtradas pela data de corte da votação. Registre a fonte
`umamusume-global` antes da primeira importação (o docstring do script traz o
comando pronto).

Detalhes em `docs/operations.md`.

## Segurança e limitações

- Administradores usam senha; participantes usam somente username, com aviso explícito de
  que o acesso não comprova identidade.
- Não há cadastro público.
- Imagens são locais; a aplicação não busca imagens externas em runtime.
- Licenças de imagens externas exigem revisão manual antes de `import_images --apply`
  (risco G5 aceito, sem gate técnico no MVP).
- Resultados são agregados; nenhuma visão administrativa expõe escolhas individuais.
- O risco residual de inferência por comparação de agregados é aceito na emenda 2.0.0.

Consulte `docs/security-review.md` e `docs/governance-notes.md`.

## Documentação

- Especificação: `specs/001-character-ban-voting/spec.md`
- Plano técnico: `specs/001-character-ban-voting/plan.md`
- Tarefas: `specs/001-character-ban-voting/tasks.md`
- Quickstart: `specs/001-character-ban-voting/quickstart.md`
- Operação: `docs/operations.md`
- Segurança: `docs/security-review.md`
- Governança: `docs/governance-notes.md`
- Design system: `docs/design-system.md`
