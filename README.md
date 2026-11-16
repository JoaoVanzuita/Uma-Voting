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

### Django fora do Docker

Use o script quando quiser rodar o Django no host com auto-reload, mantendo o PostgreSQL no
Docker Compose. Não mantenha o serviço `web` do Compose rodando na mesma porta; se ele estiver
ativo, o navegador pode continuar exibindo a versão do container.

```bash
./scripts/dev.sh
```

O script:

1. carrega o `.env`;
2. sobe apenas o serviço `db` do Compose, se necessário;
3. detecta o IP do container PostgreSQL ou usa um PostgreSQL local/`DATABASE_URL`;
4. executa `migrate`, `createcachetable` e `check`;
5. inicia `runserver` em `http://localhost:8000/` com auto-reload.

Opções:

```bash
DEV_PORT=8001 ./scripts/dev.sh          # outra porta
./scripts/dev.sh --port 8001            # equivalente
./scripts/dev.sh --stop-web             # para web/scheduler do Compose antes de iniciar
./scripts/dev.sh --no-migrate           # não executa migrations
./scripts/dev.sh --help
```

Se a porta 8000 estiver ocupada pelo container `web`, pare os serviços de aplicação:

```bash
docker compose stop web scheduler
```

Também é possível usar um PostgreSQL local, sem Docker:

```bash
uv sync
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=uma_voting
export POSTGRES_USER=uma_voting
export POSTGRES_PASSWORD=uma_voting
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
- Staging com acesso externo: `./scripts/staging.sh` (banco `uma_voting_staging` + ngrok).
- Importação externa: serviço `import-worker` processa a fila
  (`python manage.py run_import_worker --interval 5`). Variáveis `EXTERNAL_IMPORT_*` em
  `.env.example`; kill switch `EXTERNAL_IMPORT_ENABLED=False`.

Catálogo Global oficial (portal `umamusume.com`):

```bash
# baixa o elenco e os ícones oficiais para var/import/global/
uv run python scripts/fetch_global_assets.py
```

O script gera `catalog.csv`, `images.csv` e `global-metadata.json`. Datas e
aptidões vêm do GameTora; as personagens ainda não lançadas no Global ficam com
data futura e são filtradas pela data de corte da votação. A fonte
`umamusume-global` é criada pela migration `0005` e também pode ser importada
pela interface em `/admin/catalogo/importar/`.

Detalhes em `docs/operations.md`.

## Segurança e limitações

- Administradores usam senha; participantes usam somente username, com aviso explícito de
  que o acesso não comprova identidade.
- Não há cadastro público.
- Imagens são locais; a aplicação não busca imagens externas em runtime.
- Licenças de imagens externas exigem revisão manual antes de `import_images --apply`
  (risco G5 aceito, sem gate técnico no MVP). A importação externa pela interface não
  exibe nem bloqueia por licença; a nota permanece como metadado interno.
- Resultados são agregados; nenhuma visão administrativa expõe escolhas individuais.
- O risco residual de inferência por comparação de agregados é aceito na emenda 2.0.0.

Consulte `docs/security-review.md` e `docs/governance-notes.md`.

## Documentação

- Funcionalidades: `docs/functionalities.md`
- Inventário de telas: `docs/screen-inventory.md`
- Especificação: `specs/001-character-ban-voting/spec.md`
- Plano técnico: `specs/001-character-ban-voting/plan.md`
- Tarefas: `specs/001-character-ban-voting/tasks.md`
- Quickstart: `specs/001-character-ban-voting/quickstart.md`
- Operação: `docs/operations.md`
- Segurança: `docs/security-review.md`
- Governança: `docs/governance-notes.md`
- Design system: `docs/design-system.md`
