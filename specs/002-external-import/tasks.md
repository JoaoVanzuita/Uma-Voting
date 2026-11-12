# Tasks: Importação de Catálogo e Imagens de Fontes Externas

**Input**: Design documents from `specs/002-external-import/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`,
`quickstart.md`

**Tests**: incluídos porque o fluxo altera catálogo, imagens e operação administrativa. Escrever
os testes de cada história antes da implementação correspondente.

**Organization**: tarefas agrupadas por história de usuário para permitir implementação e teste
independentes.

**Regra de fidelidade**: tipos, tamanhos, nulabilidade, enums e invariantes seguem
`data-model.md`; rotas seguem `contracts/http-routes.md`; serviços seguem
`contracts/domain-services.md`; conectores seguem `contracts/source-adapters.md`.

## Format: `[ID] [P?] [Story] Descrição`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história de usuário (`US1`–`US4`)
- Todo task inclui caminho de arquivo exato

## Path Conventions

Projeto Django único na raiz do repositório:

- aplicações em `apps/`
- configuração em `config/`
- templates em `templates/`
- estáticos em `static/`
- mídia em `media/`
- testes em `apps/*/tests/` e `tests/`

---

## Phase 1: Setup (Infraestrutura Compartilhada)

**Purpose**: configuração, fixtures, compose e base de testes.

- [X] T001 Adicionar as variáveis `EXTERNAL_IMPORT_ENABLED`, `EXTERNAL_IMPORT_HTTP_TIMEOUT`, `EXTERNAL_IMPORT_MAX_IMAGE_BYTES`, `EXTERNAL_IMPORT_CONCURRENCY` e `EXTERNAL_IMPORT_STALE_SECONDS` em `config/settings/base.py` e `.env.example`
- [X] T002 Configurar o logger `apps.catalog.imports` em `config/settings/base.py`, com formato sem dados sensíveis
- [X] T003 Adicionar o serviço `import-worker` em `compose.yaml`, com `manage.py run_import_worker --interval 5` e volume `media_data`
- [X] T004 [P] Criar fixtures HTTP em `apps/catalog/tests/fixtures/sources/` (`official_characters.json`, `official_character_detail.json`, `gametora_cards.json`, `gametora_release.json`)
- [X] T005 [P] Desabilitar `EXTERNAL_IMPORT_ENABLED` por padrão em `config/settings/test.py` e impedir chamadas de rede reais nos testes
- [X] T006 [P] Adicionar factories de `CatalogSource` com `adapter`, `ImportJob`, `SyncRun` e `SyncChange` em `tests/factories.py`

---

## Phase 2: Foundational (Pré-requisitos Bloqueantes)

**Purpose**: modelos, serviços e worker compartilhados por todas as histórias.

**⚠️ CRITICAL**: nenhuma história deve começar antes desta fase.

- [X] T007 Adicionar `adapter` (`SlugField(50, blank=True, db_index=True)`) e `options` (`JSONField(default=dict, blank=True)`) a `CatalogSource` em `apps/catalog/models.py`
- [X] T008 Criar `ImportJob` em `apps/catalog/models.py` com campos, enums, `Meta.ordering`, índices, constraints e invariantes de `data-model.md` §4
- [X] T009 Adicionar `origin` (`manual|external`, default `manual`) a `SyncRun` em `apps/catalog/models.py`
- [X] T010 Gerar `apps/catalog/migrations/0004_catalogsource_adapter_importjob.py` com as alterações de T007–T009, incluindo constraints e índice único parcial
- [X] T011 Criar `apps/catalog/migrations/0005_seed_umamusume_global.py` com `get_or_create` por `name`, atualizando `adapter`, `kind` e `base_url` somente quando vazios e preservando `license_note` já revisada; não usar defaults que sobrescrevam a licença
- [X] T012 [P] Criar `apps/catalog/services/sources/base.py` com `ExternalSourceAdapter`, `ImageCandidate`, `ImageFetchError`, `SourceCheckResult` e exceções
- [X] T013 [P] Criar `apps/catalog/services/sources/registry.py` com `ADAPTERS`, `get_adapter`, `get_adapter_class`, `available_sources` e `is_supported`
- [X] T014 Criar `apps/catalog/services/sources/http.py` com HTTPS, allowlist, bloqueio de IP privado, redirects, timeout, limite de bytes, retries e cache por execução
- [X] T015 [P] Escrever testes do cliente HTTP em `apps/catalog/tests/test_source_http.py` (allowlist, HTTPS, redirect, IP privado, timeout, tamanho, retry)
- [X] T016 Refatorar `apps/catalog/services/sync.py` para expor `sync_from_report(report, source, *, triggered_by=None, apply_all=False, origin=...)`, mantendo `sync_from_file` como wrapper
- [X] T017 [P] Escrever testes de `sync_from_report` em `apps/catalog/tests/test_sync.py`: modo manual inalterado, `apply_all=True` sem pendências e `origin` correto
- [X] T018 Refatorar `apps/catalog/services/images.py` para extrair `store_image_bytes(character, data, *, source, source_url, license_note, is_current=True)` e fazer `import_images` usá-lo
- [X] T019 [P] Escrever testes de `store_image_bytes` em `apps/catalog/tests/test_images.py`: normalização, checksum, reutilização, substituição, limites e erros
- [X] T020 Criar `apps/catalog/services/imports.py` com `create_import_job`, `request_cancel`, `request_retry`, `mark_stale_jobs` e `claim_next_job`
- [X] T021 [P] Escrever testes de ciclo de vida em `apps/catalog/tests/test_import_jobs.py`: criação, duplicidade ativa, cancelamento, retry, stale e claim
- [X] T022 Criar `apps/catalog/management/commands/run_import_worker.py` com `--interval`, `--once`, `--json`, advisory lock e loop de claim
- [X] T023 Criar esqueletos de rotas em `apps/catalog/urls.py` e views em `apps/catalog/views.py` para iniciar, listar, detalhar, status, cancelar, repetir e verificar fonte
- [X] T024 [P] Criar `templates/admin/catalog/import_form.html`, `import_detail.html`, `import_list.html` e `_import_status.html` seguindo o admin existente
- [X] T025 [P] Criar `static/js/catalog-import.js` com polling de status, atualização de progresso e parada em estado terminal
- [X] T026 Adicionar `ImportJobForm` em `apps/catalog/forms.py` com fonte, modo e escopo
- [X] T027 Adicionar o painel "Fontes externas" em `templates/admin/catalog/status.html` e o contexto correspondente em `apps/catalog/views.py`

**Checkpoint**: modelos, serviços, worker, rotas e templates base prontos.

---

## Phase 3: User Story 1 — Importar o catálogo pela interface (Priority: P1) 🎯 MVP

**Goal**: administrador seleciona a fonte e o modo catálogo; o sistema coleta e aplica
automaticamente, com progresso e relatório.

**Independent Test**: criar a fonte e um job de catálogo com HTTP mockado; verificar personagens,
versões, aptidões, `SyncRun.origin=external`, `SyncChange.auto_applied` e zero pendências.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T028 [P] [US1] Testar parsing da lista e do detalhe oficial em `apps/catalog/tests/test_source_umamusume_global.py`
- [X] T029 [US1] Testar parsing de cards, build ID, datas e aptidões do GameTora no mesmo arquivo
- [X] T030 [P] [US1] Testar fase de catálogo em `apps/catalog/tests/test_import_worker.py`: sucesso, lista vazia, GameTora indisponível, conflito de versão, `stable_id` duplicado, detalhe 404 como aviso e falha atômica
- [X] T031 [P] [US1] Testar criação e detalhe do job em `apps/catalog/tests/test_ui_admin_import.py`
- [X] T032 [US1] Testar permissão, CSRF, fonte desabilitada, fonte sem conector e kill switch no mesmo arquivo

### Implementation for User Story 1

- [X] T033 [US1] Implementar `UmamusumeGlobalAdapter.fetch_catalog()` em `apps/catalog/services/sources/umamusume_global.py` com lista e detalhe oficiais
- [X] T034 [US1] Implementar descoberta de cards, build ID e JSON do GameTora no mesmo módulo, com cache e fallback
- [X] T035 [US1] Implementar mapeamento de aptidões, `stable_id`, versão `-original`, data global e avisos no mesmo módulo
- [X] T036 [US1] Implementar `run_catalog_phase()` em `apps/catalog/services/imports.py` com `sync_from_report(apply_all=True, origin=external)` e vínculo `job.sync_run`
- [X] T037 [US1] Preencher `report["catalog"]` com contagens de mudanças, ignoradas, avisos e erros
- [X] T038 [US1] Implementar `catalog_import` em `apps/catalog/views.py` para GET do formulário e POST de criação, com redirect para job existente quando já houver execução ativa da mesma fonte
- [X] T039 [US1] Implementar `catalog_import_detail` e o template `import_detail.html` com relatório de catálogo, última falha da fonte e link para `catalog_sync_detail`
- [X] T040 [US1] Conectar `run_import_worker` à fase de catálogo e registrar transições no logger `apps.catalog.imports`
- [X] T041 [US1] Tratar falhas sistêmicas, schema inválido e conflitos de identidade/versão com mensagens PT-BR e status `failed` sem escrita parcial, mantendo avisos de item como não fatais

**Checkpoint**: catálogo externo funcional e testável isoladamente.

---

## Phase 4: User Story 2 — Baixar e associar imagens (Priority: P1)

**Goal**: baixar imagens automaticamente, normalizar, associar e reportar falhas isoladas.

**Independent Test**: com personagens existentes e HTTP mockado, executar job de imagens e
verificar `ImageAsset` corrente válido, checksum, reutilização e relatório de erros.

### Tests for User Story 2 ⚠️

- [X] T042 [P] [US2] Testar `iter_images` em `apps/catalog/tests/test_source_umamusume_global.py`: URL oficial, escopo `all` e `missing`, 404 e timeout
- [X] T043 [P] [US2] Testar fase de imagens em `apps/catalog/tests/test_import_worker.py`: sucesso, parcial, imagem inválida, tamanho excessivo e personagem sem imagem
- [X] T044 [P] [US2] Testar idempotência e substituição de imagem em `apps/catalog/tests/test_images.py`
- [X] T045 [P] [US2] Testar escopo padrão e opções do formulário em `apps/catalog/tests/test_ui_admin_import.py`

### Implementation for User Story 2

- [X] T046 [US2] Implementar `iter_images()` no conector com URL oficial, `source_url`, licença e escopo
- [X] T047 [US2] Implementar download concorrente limitado no conector, convertendo falhas em `ImageFetchError`
- [X] T048 [US2] Implementar `run_images_phase()` em `apps/catalog/services/imports.py` com progresso, heartbeat e `store_image_bytes`
- [X] T049 [US2] Preencher `report["images"]` com criadas, substituídas, reutilizadas, ignoradas, avisos e erros
- [X] T050 [US2] Encadear catálogo → imagens no modo `full` e impedir imagens quando o catálogo falhar
- [X] T051 [US2] Adicionar link para `/admin/catalogo/imagens/` e para `validate_images` no detalhe do job
- [X] T052 [US2] Garantir que o escopo `missing` não baixe imagem de personagem com asset corrente válido

**Checkpoint**: catálogo e imagens funcionam de ponta a ponta.

---

## Phase 5: User Story 3 — Acompanhar e controlar importações (Priority: P2)

**Goal**: progresso em tempo real, histórico, cancelamento, repetição e recuperação de execução
órfã.

**Independent Test**: iniciar job, observar status via JSON, cancelar outro e repetir um job
falho; simular worker interrompido e verificar stale recovery.

### Tests for User Story 3 ⚠️

- [X] T053 [P] [US3] Testar endpoint de status em `apps/catalog/tests/test_ui_admin_import.py`: campos, percentual, terminal e `no-store`
- [X] T054 [P] [US3] Testar cancelamento, repetição e 409 em `apps/catalog/tests/test_import_jobs.py`
- [X] T055 [P] [US3] Testar stale recovery e heartbeat em `apps/catalog/tests/test_import_worker.py`
- [X] T056 [US3] Testar histórico, filtros e paginação em `apps/catalog/tests/test_ui_admin_import.py`

### Implementation for User Story 3

- [X] T057 [US3] Implementar `catalog_import_status` em `apps/catalog/views.py` retornando o JSON de `contracts/http-routes.md` §4
- [X] T058 [US3] Implementar `catalog_import_cancel` e `catalog_import_retry` com validação de estado
- [X] T059 [US3] Implementar `catalog_import_list` com filtros por status e fonte
- [X] T060 [US3] Implementar `mark_stale_jobs` no início de cada ciclo do worker, definindo `phase=finished` e registrando log
- [X] T061 [US3] Implementar checagem de `cancel_requested` entre itens nas imagens e antes da aplicação no catálogo, preservando o que já foi aplicado
- [X] T062 [US3] Implementar polling em `static/js/catalog-import.js` com parada em estado terminal e fallback sem JavaScript
- [X] T063 [US3] Adicionar ações de cancelar/repetir no template apenas quando aplicáveis
- [X] T064 [US3] Garantir que execuções terminais não sejam alteradas e que repetição crie novo job

**Checkpoint**: operação completa de execuções.

---

## Phase 6: User Story 4 — Diagnosticar e manter fontes (Priority: P3)

**Goal**: verificar disponibilidade, diagnosticar fonte indisponível e respeitar o kill switch
com aviso discreto.

**Independent Test**: verificar fonte disponível e indisponível, confirmar que a licença não
bloqueia a importação e desabilitar a feature por configuração.

### Tests for User Story 4 ⚠️

- [ ] T065 [P] [US4] Testar `check_source` e a rota de verificação em `apps/catalog/tests/test_import_jobs.py` e `test_ui_admin_import.py`
- [ ] T066 [US4] Testar bloqueio por `EXTERNAL_IMPORT_ENABLED=False` e ausência de bloqueio por licença
- [ ] T067 [US4] Testar exibição de todas as fontes no painel e de somente fontes elegíveis no seletor

### Implementation for User Story 4

- [ ] T068 [US4] Implementar `check_source()` e `catalog_source_check` com timeout curto, mensagem resumida e diagnóstico de fonte desabilitada que possua conector
- [ ] T069 [US4] Exibir no painel todas as fontes com nome, última execução, situação, conector e motivo da última falha; o seletor do formulário usa apenas fontes elegíveis
- [ ] T070 [US4] Remover a confirmação de licença do fluxo externo e exibir o kill switch como aviso discreto (sem banner de alerta)
- [ ] T071 [US4] Implementar o kill switch na view, no serviço e na interface
- [ ] T072 [US4] Documentar no próprio painel como resolver fonte sem conector ou desabilitada

**Checkpoint**: diagnóstico e manutenção de fontes disponíveis.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T073 [P] Atualizar `docs/operations.md` com worker, variáveis, logs, cancelamento, stale recovery e kill switch
- [ ] T074 [P] Atualizar `.env.example` e `README.md` com o novo fluxo
- [ ] T075 [P] Revisar segurança: SSRF, redirect, IP privado, limites, Pillow, caminhos e logs
- [ ] T076 [P] Adicionar testes de concorrência para advisory lock e claim em `apps/catalog/tests/test_import_worker.py`
- [ ] T077 Executar `ruff check`, `python manage.py makemigrations --check`, `python manage.py check` e a suíte completa
- [ ] T078 Validar o quickstart em staging com banco `uma_voting_staging` e worker dedicado
- [ ] T079 [P] Adicionar smoke E2E opcional do fluxo administrativo em `tests/e2e/`
- [ ] T080 Revisar mensagens PT-BR, acessibilidade da barra de progresso e estados vazios

---

## Phase 8: Hardening de Cobertura (CRITICAL/HIGH)

**Purpose**: fechar as lacunas críticas e altas identificadas na análise antes do deploy.

- [ ] T081 [US1] Criar teste de regressão de snapshots em `tests/integration/test_external_import_snapshot.py`: votação com snapshot/cédula, importação aplicada, snapshot e resultado inalterados
- [ ] T082 [US2] Criar teste de isolamento de mídia em `tests/integration/test_external_import_isolation.py`: páginas de participante e catálogo não fazem requisições externas de imagem
- [ ] T083 [US3] Adicionar consulta da última falha por fonte em `apps/catalog/services/imports.py` e usá-la no painel de fontes
- [ ] T084 [US3] Cobrir todas as transições de estado com log estruturado em `apps/catalog/services/imports.py`: criada, claimed, fase, concluída, cancelada, stale e retry
- [ ] T085 [US3] Criar `apps/catalog/migrations/0006_importjob_terminal_trigger.py` com triggers que bloqueiam `UPDATE` de execução terminal e `DELETE` de execuções
- [ ] T086 [US3] Testar constraints, índice único parcial e triggers de `ImportJob` em `apps/catalog/tests/test_import_job_model.py`

**Checkpoint**: lacunas CRITICAL/HIGH cobertas e verificadas.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias.
- **US1 (Phase 3)**: depende da Foundational.
- **US2 (Phase 4)**: depende da Foundational e da fase de catálogo para o modo `full`.
- **US3 (Phase 5)**: depende da Foundational e de pelo menos um tipo de job (US1 ou US2).
- **US4 (Phase 6)**: depende da Foundational.
- **Polish (Phase 7)**: depende das histórias desejadas.
- **Hardening (Phase 8)**: depende de US1, US2 e US3; deve ser concluído antes do deploy.

### User Story Dependencies

- **US1 (P1)**: entrega o MVP de catálogo externo.
- **US2 (P1)**: pode começar após a Foundational para o modo `images`; integra com US1 no modo
  `full`.
- **US3 (P2)**: integra com US1/US2 para progresso e operação.
- **US4 (P3)**: independente, mas usa o registry e os serviços da Foundational.

### Within Each User Story

- Testes primeiro; devem falhar antes da implementação.
- Modelos antes de serviços.
- Serviços antes de views.
- Views antes de templates.
- Worker antes do teste de integração ponta a ponta.

### Parallel Opportunities

- T004, T005 e T006 no Setup.
- T012, T013, T015, T017, T019 e T021 na Foundational, respeitando dependências de arquivo.
- T024 e T025 podem rodar em paralelo.
- T028 e T030 em paralelo; T029 após T028; T031 e T032 em sequência no mesmo arquivo.
- T042–T045 (testes US2) em paralelo.
- T053–T055 (testes US3) em paralelo; T056 após T053 no mesmo arquivo.
- T065 e T066 em paralelo; T067 após T065 no mesmo arquivo.
- T073–T075 no polish.
- T081 e T082 em paralelo; T083 e T084 em paralelo; T085 e T086 em sequência.

---

## Parallel Example: User Story 1

```bash
# Testes primeiro
Task: "Testar parsing oficial em apps/catalog/tests/test_source_umamusume_global.py"
Task: "Testar fase de catálogo em apps/catalog/tests/test_import_worker.py"
Task: "Testar UI em apps/catalog/tests/test_ui_admin_import.py"

# Depois, conector e serviço
Task: "Implementar fetch_catalog em apps/catalog/services/sources/umamusume_global.py"
Task: "Implementar run_catalog_phase em apps/catalog/services/imports.py"
Task: "Implementar views em apps/catalog/views.py"
```

## Parallel Example: User Story 2

```bash
Task: "Testar iter_images em test_source_umamusume_global.py"
Task: "Testar fase de imagens em test_import_worker.py"
Task: "Testar idempotência em test_images.py"
```

---

## Implementation Strategy

### MVP First (US1)

1. Concluir Setup e Foundational.
2. Implementar US1.
3. Validar: catálogo externo aplicado automaticamente, zero pendências, relatório visível.
4. Deploy/demonstração.

### Incremental Delivery

1. US1 → catálogo externo.
2. US2 → imagens automáticas.
3. US3 → operação e recuperação.
4. US4 → diagnóstico e endurecimento.
5. Hardening → snapshots, isolamento de mídia, constraints e logs.
6. Polish → documentação e validação final.

### Parallel Team Strategy

1. Time conclui Setup + Foundational.
2. Depois:
   - Dev A: US1 (conector + catálogo).
   - Dev B: US2 (imagens) usando o mesmo contrato.
   - Dev C: US3 (status/cancelamento) após o modelo de job.
   - Dev D: US4 (diagnóstico) e docs.
3. Integrar no modo `full` ao final de US1 + US2.

---

## Notes

- `[P]` = arquivos diferentes, sem dependência de tarefa incompleta.
- `[Story]` mapeia a tarefa para a história de usuário.
- Não alterar o comportamento do fluxo CSV existente.
- Não introduzir Celery, Redis ou dependência HTTP nova.
- Toda chamada externa deve passar pelo cliente HTTP allowlisted.
- Nenhum teste acessa a internet.
- T081 (snapshots) e T082 (isolamento de mídia) são critérios CRITICAL e não devem ser removidos.
- Commitar após cada tarefa ou grupo lógico.
