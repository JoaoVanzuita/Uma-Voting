# Tasks: Uma Voting — Votações de Banimento de Personagens

**Input**: Design documents from `specs/001-character-ban-voting/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`

**Tests**: incluídos porque a constituição e o plano exigem testes automatizados dos fluxos
críticos (autenticação, autorização, ciclo de vida, cédulas, resultados, snapshots e imagens).
Escrever os testes de cada história antes da implementação correspondente.

**Organization**: tarefas agrupadas por história de usuário para permitir implementação e
teste independentes.

**Regra de fidelidade**: tipos, tamanhos, nulabilidade, valores enumerados e constraints
seguem literalmente `data-model.md` §3–9; rotas e serviços seguem `contracts/`; formatos de
importação seguem `contracts/import-formats.md`.

## Format: `[ID] [P?] [Story] Descrição`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história de usuário (`US1`–`US8`)
- Todo task inclui caminho de arquivo exato

## Path Conventions

Projeto Django único na raiz do repositório:

- aplicações em `apps/`
- configuração em `config/`
- templates em `templates/`
- estáticos em `static/`
- mídia em `media/`
- testes em `apps/*/tests/`, `tests/integration/`, `tests/concurrency/`, `tests/e2e/`

---

## Phase 1: Setup (Infraestrutura Compartilhada)

**Purpose**: inicialização do projeto, containers, configuração e base visual.

- [X] T001 Criar a estrutura de diretórios e o esqueleto Django (`manage.py`, `config/settings/{base,dev,prod,test}.py`, `config/urls.py`, `config/wsgi.py`, `apps/{accounts,catalog,voting,core}/`, `templates/`, `static/`, `media/`, `tests/`)
- [X] T002 Criar `pyproject.toml` com Python 3.14, Django 5.2.18, Gunicorn 23.x, psycopg 3.x, Pillow, django-environ, pytest 9.x, pytest-django 4.14, factory_boy, freezegun e Ruff; gerar `uv.lock`
- [X] T003 [P] Criar `Dockerfile` multi-stage com usuário não-root, dependências via `uv` e comando Gunicorn para produção
- [X] T004 [P] Criar `compose.yaml`, `compose.override.yaml` e `compose.prod.yaml` com serviços `db`, `release`, `web`, `scheduler`, `caddy` e volumes `postgres_data`, `media_data`, `static_data`, `caddy_data`, `caddy_config`
- [X] T005 [P] Criar `Caddyfile` com TLS automático, `handle_path /static/*` e `/media/*`, compressão e cabeçalhos de segurança
- [X] T006 [P] Criar `.env.example` e settings `base/dev/prod/test` com `LANGUAGE_CODE='pt-br'`, `TIME_ZONE='America/Sao_Paulo'`, `USE_TZ=True`, `SECURE_PROXY_SSL_HEADER` e leitura via django-environ
- [X] T007 [P] Vendorizar Bootstrap 5.3.8, HTMX 2.0.11, Inter e Lucide em `static/vendor/` e `static/fonts/`
- [X] T008 [P] Criar `templates/base.html`, `templates/participant/base.html`, `templates/admin/base.html`, `templates/errors/{403,404,500}.html` e os tokens CSS em `static/css/tokens.css` e `static/css/base.css`
- [X] T009 [P] Configurar Ruff, pytest, pytest-django, `conftest.py` e settings de teste PostgreSQL em `pyproject.toml`/`tests/conftest.py`
- [X] T010 [P] Criar `.github/workflows/ci.yml` com lint, `makemigrations --check`, testes, `check --deploy` e build Docker
- [X] T011 Criar healthcheck `/health/`, middleware de request ID e logging base em `apps/core/views.py`, `apps/core/middleware.py`, `apps/core/urls.py` e `config/urls.py`
- [X] T012 Criar esqueletos de `scripts/release.sh`, `scripts/backup.sh` e `scripts/restore.sh` com `migrate`, `collectstatic`, `createcachetable`, `pg_dump` e tar de `media/`

**Checkpoint**: aplicação sobe, health responde, CI e layout base prontos.

---

## Phase 2: Foundational (Pré-requisitos Bloqueantes)

**Purpose**: modelos e infraestrutura compartilhados por todas as histórias.

**⚠️ CRITICAL**: nenhuma história deve começar antes desta fase.

- [X] T013 Criar `accounts.User(AbstractBaseUser)` em `apps/accounts/models.py` com `USERNAME_FIELD='username'`, `REQUIRED_FIELDS=[]`, campos `username`, `password`, `is_admin`, `is_active`, `date_joined`, `last_login`, manager com `get_by_natural_key()` usando `username__iexact` e `UniqueConstraint(Lower('username'), name='uniq_user_username_ci')`; gerar migration
- [X] T014 Criar `CatalogSource` (`name`, `kind IN ('html','api','file','manual')`, `base_url`, `terms_url`, `license_note`, `enabled`), `Character` (`stable_id` único), `CharacterVersion` (`stable_id` único, `release_date_global` nullable, unique `(character_id, stable_id)`), `Aptitude` (unique `(category, value)`), `CharacterVersionAptitude` (unique `(version_id, aptitude_id)`) e `ImageAsset` (`file_path` único, partial unique `(character_id) WHERE is_current`, `status IN ('valid','invalid','missing')`, checksum, width > 0, height > 0) em `apps/catalog/models.py`; gerar migration com índices
- [X] T015 Criar data migration em `apps/catalog/migrations/0002_seed_aptitudes.py` com as 10 aptidões (4 estratégias, 4 distâncias, 2 superfícies) e o `CatalogSource` `curadoria-local` (o modelo é criado em T014)
- [X] T016 [P] Criar factories compartilhadas em `tests/factories.py` para usuários, fontes de catálogo, personagens, versões, aptidões e imagens
- [X] T017 [P] Criar template tags compartilhadas em `apps/core/templatetags/ui_tags.py` para URL de imagem/placeholder, badges de estado e formatação de data/hora em `America/Sao_Paulo`
- [X] T018 [P] Criar componentes CSS compartilhados (botões, formulários, tabelas, alertas, cards, estados vazios) em `static/css/components.css` e `static/css/pages.css`
- [X] T019 [P] Criar utilitários JS em `static/js/app.js` para contador de seleção, fallback de imagem, CSRF em HTMX e gerenciamento de foco
- [X] T020 Criar esqueletos de URLs e views namespaced em `apps/accounts/urls.py`, `apps/catalog/urls.py`, `apps/voting/urls.py` e `config/urls.py`
- [X] T021 Configurar logging sem dados sensíveis, segurança base, sessão em banco, `DatabaseCache`, `SESSION_EXPIRE_AT_BROWSER_CLOSE=True` e cookies em `config/settings/base.py`
- [X] T022 Criar `AdminRequiredMixin`, `ActiveUserRequiredMixin` e helper de elegibilidade em `apps/core/permissions.py` com verificação server-side

**Checkpoint**: modelos compartilhados, settings, segurança e base visual prontos.

---

## Phase 3: User Story 1 — Acessar o sistema conforme o perfil (Priority: P1) 🎯

**Goal**: administrador entra com username e senha; participante entra somente com username;
sessão dura até logout/fechamento do navegador; administrador alterna para a experiência de
participante.

**Independent Test**: cadastrar um admin e um participante ativo, autenticar cada perfil,
conferir áreas permitidas, rejeitar username inexistente/inativo/admin no fluxo de participante,
fazer logout e confirmar expiração ao fechar o navegador.

### Tests for User Story 1

- [X] T023 [P] [US1] Testes unitários de unicidade case-insensitive e manager `get_by_natural_key()` em `apps/accounts/tests/test_models.py`
- [X] T024 [P] [US1] Testes de integração de login admin/participante, rejeição de username admin, inexistente/inativo, CSRF, aviso de limitação do username, logout, expiração ao fechar navegador e alternância de modo em `apps/accounts/tests/test_auth_views.py`
- [X] T025 [P] [US1] Testes de throttle de login por IP/username em `apps/accounts/tests/test_throttle.py`

### Implementation for User Story 1

- [X] T026 [US1] Implementar `accounts.services.auth` com login admin (senha), login participante (username), rejeição de admin no fluxo de participante, mensagem genérica e logout em `apps/accounts/services/auth.py`
- [X] T027 [US1] Implementar `accounts.services.throttle` com `DatabaseCache`, janela de 5 minutos e limites do plano em `apps/accounts/services/throttle.py`
- [X] T028 [US1] Criar formulários e views de login/logout/modo em `apps/accounts/forms.py` e `apps/accounts/views.py`
- [X] T029 [US1] Criar templates de login `templates/participant/login.html` e `templates/admin/login.html` com link para o outro acesso, mensagens genéricas e aviso no login de participante: “Este acesso identifica apenas o username; não comprova sua identidade.”
- [X] T030 [US1] Implementar `create_admin` com senha via prompt/stdin em `apps/accounts/management/commands/create_admin.py`
- [X] T031 [US1] Configurar `AUTHENTICATION_BACKENDS`, sessão, CSRF, cookies `Secure`/`HttpOnly`/`SameSite=Lax` e `SESSION_COOKIE_AGE` em `config/settings/base.py` e `config/settings/prod.py`
- [X] T032 [US1] Wire das rotas `participant:login`, `admin:login`, `participant:logout` e `admin:logout` em `apps/accounts/urls.py` e `config/urls.py`
- [X] T033 [US1] Implementar middleware/context processor de modo admin↔participante em `apps/core/middleware.py` e `apps/core/context_processors.py`
- [X] T034 [US1] Adicionar logging de falhas de autenticação e transições de sessão sem senha/username sensível em `apps/accounts/services/auth.py`
- [X] T035 [US1] Executar os cenários do quickstart §5.1, exceto a listagem de votações elegíveis (validada em T053), e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: US1 funcional e testável isoladamente.

---

## Phase 4: User Story 2 — Votar em uma votação aberta (Priority: P1) 🎯

**Goal**: participante elegível vê na home as votações disponíveis, encontra personagens por
cards, busca e filtros, seleciona exatamente N escolhas distintas, revisa, confirma a cédula
definitiva e consulta a própria cédula.

**Independent Test**: com uma votação aberta criada por factory e snapshots de catálogo,
autenticar um participante elegível, conferir a home com a votação elegível, filtrar personagens,
selecionar 3, revisar, confirmar, consultar a cédula e verificar que um segundo envio é bloqueado.

### Tests for User Story 2

- [X] T036 [P] [US2] Testes de modelos/constraints de `Voting`, `VotingEligibility`, snapshots, `Ballot` e `BallotChoice`, incluindo duas votações abertas simultâneas com elegibilidades/cédulas independentes, em `apps/voting/tests/test_models.py`
- [X] T037 [P] [US2] Testes de serviço de cédula (quantidade exata, duplicidade, snapshot, votação fechada, segundo envio) em `apps/voting/tests/test_ballots.py`
- [X] T038 [P] [US2] Testes de integração de seleção, busca, filtros, revisão, confirmação e consulta da própria cédula, incluindo asserção do aviso de cédula definitiva e admin elegível no modo participante com voto contado normalmente e cédula própria visível, em `apps/voting/tests/test_participant_flow.py`
- [X] T039 [P] [US2] Testes de concorrência de envio duplo e envio vs encerramento em `tests/concurrency/test_ballots.py`

### Implementation for User Story 2

- [X] T040 [US2] Criar `Voting` (`CHECK choices_count > 0`, `CHECK closes_at > opens_at`, modos automáticos exigem datas, status `draft/scheduled/open/closed/cancelled`), `VotingEligibility` (unique `(voting_id, user_id)`), `VotingCharacterSnapshot` (unique `(voting_id, source_character_id)` e `(voting_id, stable_id)`), `VotingVersionSnapshot` (unique `(character_snapshot_id, source_version_id)`), `VotingVersionAptitudeSnapshot` (unique `(version_snapshot_id, aptitude_id)`), `Ballot` (unique `(voting_id, participant_id)`) e `BallotChoice` (unique `(ballot_id, character_snapshot_id)`) em `apps/voting/models.py`
- [X] T041 [US2] Gerar migration de `apps/voting/models.py` com constraints e índices de `data-model.md` §13
- [X] T042 [US2] Adicionar factories de votação aberta, snapshots, elegibilidade e cédula em `tests/factories.py`
- [X] T043 [US2] Implementar `submit_ballot` e `get_own_ballot` em `apps/voting/services/ballots.py` com `transaction.atomic()`, `SELECT ... FOR SHARE` na votação, validação de status/horário/elegibilidade, quantidade exata, IDs distintos, snapshot, `AlreadyVotedError` e 409
- [X] T044 [US2] Implementar `search_characters` em `apps/voting/services/filters.py`: OU dentro da categoria, E entre categorias, mesma versão, busca `icontains` e `DISTINCT` por personagem
- [X] T045 [US2] Implementar views de participante `home`, `voting_detail`, `character_grid`, `review`, `confirm` e `ballot` em `apps/voting/views/participant.py` e `apps/voting/urls.py`, validando elegibilidade, `voting.status` e cédula própria filtrada por `request.user` inclusive para admin no modo participante
- [X] T046 [US2] Criar templates `templates/participant/home.html`, `voting_detail.html`, `character_grid.html`, `review.html` e `ballot.html` com lista de elegíveis, estado vazio, cards, busca, filtros, contador e revisão
- [X] T047 [US2] Implementar partial HTMX de busca/filtros preservando `selected` e o contador em `templates/participant/character_grid.html` e `static/js/app.js`
- [X] T048 [US2] Implementar seleção sem duplicidade, limite de escolhas, indicação visual, contador `aria-live` e bloqueio ao atingir o limite em `static/js/app.js` e templates
- [X] T049 [US2] Adicionar validação server-side e mensagens PT-BR para quantidade/duplicidade/snapshot/estado em `apps/voting/views/participant.py`
- [X] T050 [US2] Criar migration PostgreSQL em `apps/voting/migrations/0002_ballot_triggers.py` com funções/triggers `ballot_insert_open`, `ballot_eligible_participant`, `ballot_no_update`, `ballot_delete_window`, `ballot_choice_insert_open`, `ballot_choice_no_update`, `ballot_choice_delete_window`, `ballot_choice_same_voting` e `ballot_choice_count` (constraint trigger diferido)
- [X] T051 [US2] Criar testes de triggers de cédula/contagem/exclusão em `apps/voting/tests/test_db_invariants.py`
- [X] T052 [US2] Implementar fallback de imagem quebrada e placeholder nos cards em `apps/core/templatetags/ui_tags.py` e `static/js/app.js`
- [X] T053 [US2] Executar os cenários do quickstart §5.1 (listagem de votações elegíveis e estado vazio) e §5.4/§5.5 (incluindo admin elegível votando no modo participante e medição de SC-002 <3 min), e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: US1 e US2 funcionam; o fluxo central de voto está validado.

---

## Phase 5: User Story 3 — Administrar participantes (Priority: P2)

**Goal**: administrador cadastra, pesquisa, edita, desativa e importa participantes por CSV,
com unicidade case-insensitive e importação atômica.

**Independent Test**: cadastrar participantes individualmente e por CSV, pesquisar, editar,
desativar e verificar inclusão automática em uma votação em rascunho.

### Tests for User Story 3

- [X] T054 [P] [US3] Testes unitários de criação/edição/desativação e unicidade case-insensitive em `apps/accounts/tests/test_participants.py`
- [X] T055 [P] [US3] Testes de importação CSV (válido, duplicidades, vazio, encoding, atomicidade) em `apps/accounts/tests/test_import.py`
- [X] T056 [P] [US3] Testes de integração do admin de participantes (CRUD, busca, importação) em `apps/accounts/tests/test_admin_participants.py`

### Implementation for User Story 3

- [X] T057 [US3] Implementar `accounts.services.participants` com `create_participant` (com `set_unusable_password()`), `update_participant` e `deactivate_participant`; rejeitar `is_admin=True` na área de participantes em `apps/accounts/services/participants.py`
- [X] T058 [US3] Implementar parser/importador CSV atômico em `apps/accounts/services/imports.py` com relatório por linha e rejeição integral em caso de inconsistência
- [X] T059 [US3] Criar formulários/views/urls de participantes em `apps/accounts/forms.py`, `apps/accounts/views.py` e `apps/accounts/urls.py`
- [X] T060 [US3] Criar templates `templates/admin/participants/list.html`, `form.html` e `import.html`
- [X] T061 [US3] Implementar `import_participants` em `apps/accounts/management/commands/import_participants.py`
- [X] T062 [US3] Implementar `add_default_eligible(voting)` em `apps/voting/services/eligibility.py` e testes de inclusão de todos os usuários ativos, incluindo administradores elegíveis, na criação, e de exclusão de cadastros posteriores
- [X] T063 [US3] Adicionar navegação de participantes e badge read-only para administradores em `templates/admin/base.html`
- [X] T064 [US3] Executar os cenários do quickstart §5.2 e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: US3 funcional; importação inválida não grava dados.

---

## Phase 6: User Story 4 — Manter o catálogo e as imagens (Priority: P2)

**Goal**: sincronizar catálogo por arquivo, aplicar novas personagens, deixar alterações
existentes pendentes, aprovar/rejeitar, gerenciar imagens locais e validar o acervo.

**Independent Test**: importar um catálogo com uma personagem nova e uma alteração existente,
conferir prévia, aprovar a alteração, importar/validar imagens e confirmar que snapshots antigos
não mudam.

### Tests for User Story 4

- [X] T065 [P] [US4] Testes de modelos/constraints do catálogo em `apps/catalog/tests/test_models.py`
- [X] T066 [P] [US4] Testes de parser/sincronização híbrida (nova auto-aplicada, existente pendente, cutoff, aptidões) em `apps/catalog/tests/test_sync.py`
- [X] T067 [P] [US4] Testes de validação/importação de imagens (WebP 256×256, checksum, órfãos, placeholder) em `apps/catalog/tests/test_images.py`
- [X] T068 [P] [US4] Testes de integração do admin de catálogo (status, prévia, aprovação/rejeição, imagens) em `apps/catalog/tests/test_admin.py`

### Implementation for User Story 4

- [X] T069 [US4] Criar `SyncRun` e `SyncChange` em `apps/catalog/models.py` com status, payload JSON, histórico e índices; gerar migration (`CatalogSource` já existe desde T014)
- [X] T070 [US4] Implementar parser/validador de catálogo em `apps/catalog/services/importers.py` conforme `contracts/import-formats.md` §2; não implementar scraping do GameTora no MVP
- [X] T071 [US4] Implementar `sync_from_file` em `apps/catalog/services/sync.py` com nova personagem `auto_applied`, alterações `pending`, transação e `SyncRun`; não substituir imagens válidas
- [X] T072 [US4] Implementar `approve_change` e `reject_change` em `apps/catalog/services/sync.py` com revisão, transação e histórico
- [X] T073 [US4] Implementar consultas de elegibilidade e consolidação por cutoff em `apps/catalog/services/queries.py`
- [X] T074 [US4] Implementar comandos `import_catalog`, `sync_catalog`, `approve_catalog_change` e `reject_catalog_change` em `apps/catalog/management/commands/`
- [X] T075 [US4] Implementar views/urls do admin de catálogo (status, sincronização, prévia, aprovação/rejeição, personagens, imagens, validação) em `apps/catalog/views.py` e `apps/catalog/urls.py`
- [X] T076 [US4] Criar templates `templates/admin/catalog/status.html`, `sync_detail.html`, `characters.html` e `images.html`
- [X] T077 [US4] Implementar `validate_image_asset`, `validate_all_images` e `import_images` em `apps/catalog/services/images.py` com Pillow, limite de pixels/tamanho, WebP 256×256, `ImageOps.pad`, checksum, caminho `media/characters/<stable_id>/<sha256>.webp`, detecção de órfãos/referências quebradas/checksums duplicados, registro de `source`, `source_url` e `license_note`, e revisão manual obrigatória de licença externa antes de `--apply` (sem gate técnico no MVP)
- [X] T078 [US4] Implementar comandos `import_images` e `validate_images` em `apps/catalog/management/commands/`
- [X] T079 [US4] Implementar template tag `character_image` e placeholder em `apps/catalog/templatetags/catalog_tags.py` e `static/img/character-placeholder.webp`
- [X] T080 [US4] Exibir estado das imagens e personagens sem imagem no admin em `templates/admin/catalog/images.html` e `static/js/app.js`
- [X] T081 [US4] Adicionar testes de que atualizações de catálogo/imagem não alteram snapshots em `apps/catalog/tests/test_snapshots.py`
- [X] T082 [US4] Executar os cenários do quickstart §5.3/§5.9 e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: catálogo e imagens gerenciáveis; snapshots históricos preservados.

---

## Phase 7: User Story 5 — Criar e configurar votações (Priority: P2)

**Goal**: administrador cria e configura votação em rascunho, ajusta elegíveis, define corte,
datas e modos, e agenda quando a abertura é automática.

**Independent Test**: criar uma votação em rascunho, configurar todos os campos, ajustar
elegíveis, validar bloqueio de abertura sem elegíveis/catálogo e agendar uma votação automática.

### Tests for User Story 5

- [X] T083 [P] [US5] Testes de modelos/forms de votação (3 escolhas padrão, datas obrigatórias em modos automáticos e informativas/opcionais em modos manuais, corte, modos) em `apps/voting/tests/test_voting_config.py`
- [X] T084 [P] [US5] Testes de integração de criação/edição em rascunho, elegíveis, agendamento e bloqueio de edição em `apps/voting/tests/test_admin_voting_config.py`

### Implementation for User Story 5

- [X] T085 [US5] Implementar `create_voting`, `update_voting` e `schedule_voting` em `apps/voting/services/lifecycle.py`, com `create_voting` chamando `add_default_eligible` e validações de `choices_count > 0`, datas obrigatórias conforme o modo, modos e corte
- [X] T086 [P] [US5] Criar formulários de votação em `apps/voting/forms.py`
- [X] T087 [P] [US5] Implementar adição/remoção de elegíveis apenas em rascunho em `apps/voting/services/eligibility.py`
- [X] T088 [US5] Implementar views/urls do admin de votações (lista, criação, edição, detalhe, elegíveis) em `apps/voting/views/admin.py` e `apps/voting/urls.py`
- [X] T089 [US5] Criar templates `templates/admin/voting/list.html`, `form.html`, `detail.html` e `eligible.html`
- [X] T090 [US5] Implementar UI de agendamento, bloqueio de edição e helper de pré-condições de abertura em `apps/voting/services/lifecycle.py` e templates
- [X] T091 [US5] Adicionar testes de validação de datas invertidas, modos automáticos sem data, modos manuais com datas informativas/ausentes, catálogo insuficiente e ausência de elegíveis em `apps/voting/tests/test_voting_config.py`
- [X] T092 [US5] Adicionar links de navegação para a área de votações em `templates/admin/base.html`
- [X] T093 [US5] Executar os cenários do quickstart §5.3/§5.7 (parte de configuração), incluindo medição de SC-001 (<5 min), e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: votações configuráveis e agendáveis; configuração bloqueada após agendamento.

---

## Phase 8: User Story 6 — Operar o ciclo de vida da votação (Priority: P3)

**Goal**: abrir, acompanhar, encerrar e cancelar votações; congelar elegíveis/catálogo; executar
transições automáticas sem navegador; excluir cédulas enquanto aberta.

**Independent Test**: abrir uma votação manualmente, excluir uma cédula, encerrar e bloquear
exclusões; criar votação automática, parar o web, confirmar abertura/encerramento pelo scheduler
e testar recuperação de janelas perdidas.

### Tests for User Story 6

- [X] T094 [P] [US6] Testes de lifecycle (abrir, encerrar, cancelar, idempotência) em `apps/voting/tests/test_lifecycle.py`
- [X] T095 [P] [US6] Testes de snapshot (cutoff, versões, aptidões, imagem e imutabilidade) em `apps/voting/tests/test_snapshots.py`
- [X] T096 [P] [US6] Testes do scheduler (abertura/encerramento, janela perdida, sem elegíveis, lock) em `apps/voting/tests/test_scheduler.py`
- [X] T097 [P] [US6] Testes de concorrência (abertura vs cancelamento, encerramento vs envio, exclusão vs encerramento) em `tests/concurrency/test_lifecycle.py` e testes dedicados de exclusão administrativa em `apps/voting/tests/test_admin_ballot_delete.py` cobrindo FR-071–FR-075
- [X] T098 [P] [US6] Testes de triggers de transição/configuração/elegibilidade/snapshot em `apps/voting/tests/test_db_invariants.py`

### Implementation for User Story 6

- [X] T099 [US6] Implementar `create_snapshots` em `apps/voting/services/snapshots.py`: copiar personagens, versões e aptidões com `release_date_global <= catalog_cutoff_date`, `display_name`/`stable_id` denormalizados e `image_asset` exato
- [X] T100 [US6] Implementar `open_voting`, `close_voting` e `cancel_voting` em `apps/voting/services/lifecycle.py` com `SELECT ... FOR UPDATE`, pré-condições, transições e exclusão de cédulas no cancelamento
- [X] T101 [US6] Implementar `process_due_transitions` e `run_scheduler` em `apps/voting/services/scheduler.py` com `pg_try_advisory_lock`, `FOR UPDATE SKIP LOCKED`, idempotência e recuperação de janelas
- [X] T102 [US6] Implementar comandos `process_voting_transitions` e `run_scheduler` em `apps/voting/management/commands/`
- [X] T103 [US6] Criar migration PostgreSQL em `apps/voting/migrations/0003_voting_triggers.py` com `voting_transition`, `voting_config_immutable`, `eligibility_draft_only`, `snapshot_no_update/delete`, `snapshot_insert_window`, `snapshot_image_character` e `snapshot_version_character`
- [X] T104 [US6] Implementar views/urls de ciclo de vida (abrir, encerrar, cancelar, excluir cédula) em `apps/voting/views/admin.py` e `apps/voting/urls.py`, e o serviço `delete_ballot_admin` em `apps/voting/services/ballots.py`, sem notificar o participante, sem registrar autoria/horário da exclusão e sem exibir diferença de agregados antes/depois
- [X] T105 [US6] Adicionar confirmação e feedback das ações de ciclo de vida em `templates/admin/voting/detail.html`
- [X] T106 [US6] Configurar o serviço `scheduler` no Compose com comando `python manage.py run_scheduler --interval 60` em `compose.yaml` e `compose.prod.yaml`
- [X] T107 [US6] Adicionar logging de transições e ciclos do scheduler sem escolhas em `apps/voting/services/lifecycle.py` e `scheduler.py`
- [X] T108 [US6] Adicionar testes de cancelamento em todos os estados e da regra “status cancelled antes de apagar cédulas” em `apps/voting/tests/test_lifecycle.py`
- [X] T109 [US6] Executar os cenários do quickstart §5.7 e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: ciclo de vida completo, transições automáticas e recuperação validadas.

---

## Phase 9: User Story 7 — Consultar resultados e participação (Priority: P3)

**Goal**: admin vê agregados e participação sem escolhas individuais; participante não vê
resultados parciais e, após encerramento, vê ranking com dense rank e todos os empates.

**Independent Test**: registrar cédulas com empates, conferir agregados/participação no admin,
bloquear resultados para participante durante a votação, encerrar e conferir ranking
`1º, 2º, 2º, 3º, 3º` sem personagens com zero votos.

### Tests for User Story 7

- [X] T110 [P] [US7] Testes de agregação, dense rank, empates, exclusão de zero votos e reprodutibilidade após mutação de catálogo em `apps/voting/tests/test_results.py` e `apps/voting/tests/test_results_reproducibility.py`
- [X] T111 [P] [US7] Testes de privacidade (admin sem escolhas de outros; admin no modo participante vê somente a própria cédula; participante sem parciais; própria cédula) em `apps/voting/tests/test_privacy.py`
- [X] T112 [P] [US7] Testes de integração de resultados/participação no admin e resultado/cedula no participante em `apps/voting/tests/test_results_views.py`

### Implementation for User Story 7

- [X] T113 [US7] Implementar `aggregate_results`, `participation` e `rank_results` em `apps/voting/services/results.py` com `Count`, `EXISTS`, `DENSE_RANK` (ou cálculo equivalente), filtro `votes > 0` e sem `participant_id` no resultado
- [X] T114 [P] [US7] Implementar views/urls/templates de resultados e participação administrativos em `apps/voting/views/admin.py` e `templates/admin/voting/{results,participation}.html`
- [X] T115 [P] [US7] Implementar view/url/template de resultado final do participante em `apps/voting/views/participant.py` e `templates/participant/result.html`
- [X] T116 [US7] Integrar consulta da própria cédula após encerramento em `apps/voting/views/participant.py` e `templates/participant/ballot.html`
- [X] T117 [US7] Adicionar guarda de privacidade: views administrativas importam apenas serviços de agregados; rota de participante filtra a cédula por `request.user` inclusive para admin; logs sem escolhas; sem diff de agregados antes/depois da exclusão em `apps/voting/views/admin.py` e `apps/voting/services/results.py`
- [X] T118 [US7] Adicionar índices de agregação/consulta em `apps/voting/models.py` e migration correspondente
- [X] T119 [US7] Executar os cenários do quickstart §5.5/§5.8 e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: resultados corretos, empates densos e privacidade validada.

---

## Phase 10: User Story 8 — Consultar histórico e painel administrativo (Priority: P4)

**Goal**: participante encontra votações respondidas/encerradas no histórico; admin usa painel
com resumo, votações em andamento e atalhos; canceladas só aparecem no histórico administrativo.

**Independent Test**: acessar o painel administrativo, conferir votações em andamento e atalhos;
como participante, conferir histórico após responder e após encerramento; confirmar que
canceladas não aparecem para participante.

### Tests for User Story 8

- [X] T120 [P] [US8] Testes de integração de histórico do participante, painel admin e histórico de canceladas em `apps/voting/tests/test_history.py`

### Implementation for User Story 8

- [X] T121 [P] [US8] Implementar views/urls/templates de histórico do participante em `apps/voting/views/participant.py` e `templates/participant/history.html`
- [X] T122 [P] [US8] Implementar dashboard administrativo com total de participantes ativos, votações abertas, votações agendadas, mudanças de catálogo pendentes, imagens ausentes/inválidas, últimas votações e atalhos em `apps/voting/views/admin.py` e `templates/admin/dashboard.html`
- [X] T123 [US8] Implementar lista/filtros de votações administrativas incluindo canceladas em `apps/voting/views/admin.py` e `templates/admin/voting/list.html`
- [X] T124 [US8] Garantir que o histórico do participante exclui canceladas e separa respondidas/encerradas em `apps/voting/views/participant.py`
- [X] T125 [US8] Adicionar sidebar administrativa, navegação de participante e links de alternância de modo em `templates/admin/base.html` e `templates/participant/base.html`
- [X] T126 [US8] Adicionar estados vazios, carregamento, erro e sucesso consistentes em `templates/participant/` e `templates/admin/`
- [X] T127 [US8] Executar os cenários do quickstart §5.1/§5.2 (histórico/dashboard) e corrigir divergências em `specs/001-character-ban-voting/quickstart.md`

**Checkpoint**: histórico e painel completos; navegação consistente.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: endurecimento, operação, documentação e validação final.

- [X] T128 [P] Endurecer segurança: CSP, headers, HSTS, cookies, `check --deploy` e rate limit em `Caddyfile`, `config/settings/prod.py` e `apps/accounts/services/throttle.py`
- [X] T129 [P] Auditar acessibilidade e responsividade (360 px–desktop, teclado, foco, contraste, `aria-live`) em `templates/` e `static/css/`
- [X] T130 [P] Otimizar consultas, índices, paginação/lazy loading e tempo de busca em `apps/voting/services/` e `static/js/app.js`, e documentar medição manual com 500 personagens (<1 s)
- [X] T131 [P] Finalizar backups/restauração e runbook (incluindo `clearsessions` diário) em `scripts/backup.sh`, `scripts/restore.sh` e `docs/operations.md`
- [X] T132 [P] Finalizar CI (lint, testes, `makemigrations --check`, `check --deploy`, build) em `.github/workflows/ci.yml`
- [X] T133 [P] Criar smoke tests E2E opcionais com Playwright em `tests/e2e/test_critical_flows.py`
- [X] T134 Documentar decisões, limitações e operação em `README.md`, `docs/operations.md` e `docs/governance-notes.md`, incluindo revisão manual de licença, medições SC-001/SC-002/SC-010 e riscos aceitos
- [X] T135 Executar o quickstart completo e corrigir falhas de integração em `specs/001-character-ban-voting/quickstart.md`
- [X] T136 [P] Revisar privacidade/segurança, rodar auditoria de dependências e registrar em `docs/security-review.md`, incluindo checklist de cadastro público, exibição somente de username e revisão manual de licença
- [X] T137 [P] Registrar a emenda 2.0.0, os riscos aceitos G5/M3 e as medições manuais G2/G4 em `docs/governance-notes.md`
- [X] T138 Criar `scripts/sync_catalog.sh` e documentar a sincronização periódica diária às 03:00 via cron/systemd em `scripts/sync_catalog.sh` e `docs/operations.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências; pode começar imediatamente.
- **Foundational (Phase 2)**: depende do Setup; **bloqueia todas as histórias**.
- **US1 (Phase 3)**: depende do Foundational.
- **US2 (Phase 4)**: depende do Foundational e dos modelos compartilhados de catálogo/usuário; pode ser testada com factories.
- **US3 (Phase 5)**: depende de US1 (admin) e US2 (`VotingEligibility`); CRUD de participantes pode começar após o Foundational.
- **US4 (Phase 6)**: depende do Foundational (modelos de catálogo) e US1 (admin); pode rodar em paralelo com US2/US3 nos serviços.
- **US5 (Phase 7)**: depende de US2 (modelos de votação) e US3 (participantes elegíveis).
- **US6 (Phase 8)**: depende de US4 (snapshot de catálogo) e US5 (configuração/agendamento).
- **US7 (Phase 9)**: depende de US2 (cédulas) e US6 (votações encerradas).
- **US8 (Phase 10)**: depende de US1, US5, US6 e US7.
- **Polish (Phase 11)**: depende de todas as histórias desejadas.

### User Story Dependencies

- **US1**: independente após o Foundational.
- **US2**: depende do Foundational; validação ponta a ponta usa login de US1.
- **US3**: depende de US1/US2 para o fluxo completo; CRUD isolado usa `force_login`.
- **US4**: depende do Foundational/US1; não depende de US2 para serviços de catálogo.
- **US5**: depende de US2/US3.
- **US6**: depende de US4/US5.
- **US7**: depende de US2/US6.
- **US8**: depende de US1/US5/US6/US7.

### Within Each User Story

- Testes primeiro; confirmar falha antes da implementação.
- Modelos antes de serviços; serviços antes de views; views antes de templates quando aplicável.
- Triggers/migrations de invariantes junto ao modelo correspondente.
- Validar o checkpoint da história antes de avançar.

### Parallel Opportunities

- Setup: T003–T010 em paralelo (arquivos diferentes).
- Foundational: T016–T019 em paralelo; T013/T014/T015 são migrations e devem ser sequenciados.
- US1: T023–T025 em paralelo; T026 e T027 podem ser sequenciais (auth importa throttle); T028/T029 em paralelo.
- US2: T036–T039 em paralelo; T040 primeiro; depois T044/T047/T050 em paralelo; T048 após T047 (mesmo `static/js/app.js`).
- US3: T054–T056 em paralelo; T057/T058 em paralelo.
- US4: T065–T068 em paralelo; T069 primeiro; depois T070/T077 em paralelo (T077 depende de T014).
- US5: T083/T084 em paralelo; T086/T087 em paralelo após T040; T085 sequencial.
- US6: T094–T098 em paralelo; T099 primeiro; T100 após T099; T101 após T100; T103 após T040/T099.
- US7: T110–T112 em paralelo; T113 primeiro; T114/T115 em paralelo após T113.
- US8: T120 pode começar em paralelo (teste primeiro); T121/T122 em paralelo.
- Polish: T128–T133, T136 e T137 em paralelo; T134 e T138 após T131; T135 depende de todas.

---

## Parallel Example: User Story 2

```bash
# Testes em paralelo
Task: "Testes de modelos/constraints de votação em apps/voting/tests/test_models.py"
Task: "Testes de serviço de cédula em apps/voting/tests/test_ballots.py"
Task: "Testes de integração do fluxo de voto em apps/voting/tests/test_participant_flow.py"
Task: "Testes de concorrência em tests/concurrency/test_ballots.py"

# Implementação paralela após os modelos
Task: "Implementar search_characters em apps/voting/services/filters.py"
Task: "Criar partial HTMX em templates/participant/character_grid.html"
Task: "Criar triggers de cédula em apps/voting/migrations/0002_ballot_triggers.py"
```

---

## Implementation Strategy

### MVP First

1. Concluir Phase 1 (Setup).
2. Concluir Phase 2 (Foundational).
3. Concluir US1 (acesso) e US2 (voto) — o MVP real do produto.
4. **STOP e VALIDAR** com os cenários 5.1, 5.4 e 5.5 do quickstart.
5. Demonstrar/deployar o incremento.

> US1 isolada não entrega valor de produto; o MVP mínimo é Foundational + US1 + US2, usando
> factories para catálogo/votação.

### Incremental Delivery

1. Foundational + US1 → acesso seguro.
2. + US2 → votação funcional (MVP).
3. + US3 → gestão de participantes.
4. + US4 → catálogo e imagens.
5. + US5 → criação/agendamento.
6. + US6 → ciclo de vida automático.
7. + US7 → resultados e privacidade.
8. + US8 → histórico e painel.
9. + Polish → produção.

### Parallel Team Strategy

1. Time conclui Setup + Foundational em conjunto.
2. Depois:
   - Dev A: US1 e US3 (contas/participantes).
   - Dev B: US2 (cédulas) e US7 (resultados).
   - Dev C: US4 (catálogo/imagens) e US6 (scheduler).
   - Dev D: US5 (configuração) e US8 (histórico/UI).
3. Integrar em checkpoints; não iniciar US6 antes de US4/US5.

---

## Notes

- `[P]` indica arquivos diferentes e ausência de dependência de tarefa incompleta.
- Cada história tem critério de teste independente e checkpoint.
- Testes usam PostgreSQL real; SQLite não é suportado.
- Não expor escolhas de cédula em views, logs ou respostas administrativas.
- Imagens sempre locais; nenhuma requisição externa em runtime.
- Dense rank: `1º, 2º, 2º, 3º, 3º`; zero votos não aparecem.
- Registrar as exceções constitucionais em `docs/governance-notes.md` antes do deploy.
- Não iniciar funcionalidades fora do MVP.
