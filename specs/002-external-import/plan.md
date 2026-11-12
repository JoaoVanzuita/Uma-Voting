# Implementation Plan: Importação de Catálogo e Imagens de Fontes Externas

**Branch**: `002-external-import` | **Date**: 2026-11-12 | **Spec**:
`specs/002-external-import/spec.md`

**Input**: Feature specification from `specs/002-external-import/spec.md` e decisões de projeto
registradas na sessão de 2026-11-12.

## Summary

Adicionar um fluxo administrativo, totalmente web, para importar catálogo e imagens diretamente
de fontes externas suportadas, sem upload ou preparação de arquivos. O administrador escolhe a
fonte, o modo (catálogo, imagens ou completo) e o escopo de imagens; o sistema cria uma execução
assíncrona, coleta os dados no servidor, aplica o catálogo automaticamente e baixa, valida,
normaliza e associa as imagens.

A implementação reaproveita o máximo possível do que já existe:

- `apps/catalog/services/importers.py` define o contrato de dados do catálogo
  (`CatalogParseReport`, `CatalogRow`, `CatalogCharacter`);
- `apps/catalog/services/sync.py` concentra a aplicação do catálogo, o histórico
  (`SyncRun`/`SyncChange`) e o fluxo de aprovação;
- `apps/catalog/services/images.py` concentra validação, normalização WebP 256×256, checksum,
  content-addressing e as regras de imagem corrente;
- `apps/voting/services/scheduler.py` já demonstra o padrão de worker em container dedicado com
  advisory lock no PostgreSQL;
- o container `scheduler` e o padrão de comando de gerenciamento existentes orientam o novo
  worker.

O novo fluxo não introduz Celery, Redis, fila externa ou dependência HTTP de terceiros. A fila é
o próprio PostgreSQL (`ImportJob`) e o worker é um comando Django executado em container
dedicado.

## Technical Context

**Language/Version**: Python 3.14.x

**Primary Dependencies**: Django 5.2 LTS (5.2.18), psycopg 3.x, Pillow, django-environ, Gunicorn
23.x, `urllib` da biblioteca padrão para HTTP, pytest 9.x, pytest-django 4.14, factory_boy,
freezegun e Ruff.

**Storage**: PostgreSQL 18.6 para catálogo, histórico e fila de execução; sistema de arquivos
local em `media/characters/` para imagens normalizadas; volume Docker compartilhado entre `web`,
`import-worker` e `scheduler`.

**Testing**: pytest + pytest-django em PostgreSQL real; unitários de conector e cliente HTTP com
fixtures gravadas; integração de serviço, worker e rotas; testes de concorrência para lock e
claim; Playwright opcional para o fluxo administrativo.

**Target Platform**: Linux containers via Docker Compose; navegadores modernos suportados pelo
projeto.

**Project Type**: Aplicação web monolítica server-rendered (Django Templates + HTMX).

**Performance Goals**:
- importação completa de 85 personagens e 85 imagens em até 10 minutos em conexão de 10 Mbps;
- progresso atualizado na interface em até 5 segundos;
- páginas administrativas de importação em menos de 2 segundos;
- worker processa uma importação por vez, com concorrência interna limitada para download de
  imagens;
- nenhum impacto perceptível no tempo de resposta das páginas de participantes.

**Constraints**:
- sem Celery, Redis, fila externa ou nova dependência de runtime;
- uma importação externa simultânea no sistema;
- coleta somente de domínios allowlisted em código;
- imagens continuam locais após a importação; participantes não fazem requisições externas;
- aplicação automática das alterações de catálogo no fluxo externo;
- interface, mensagens e documentação em PT-BR;
- operação administrativa restrita a administradores autenticados;
- compatibilidade com o fluxo manual por CSV existente.

**Scale/Scope**:
- catálogo atual de 85 personagens e 85 imagens;
- horizonte de até 500 personagens canônicas;
- uma fonte externa implementada nesta versão (`umamusume-global`);
- uma execução por vez, com histórico ilimitado de execuções.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Evidência |
|---|---|---|
| I. Simplicidade Funcional | PASS | Reutiliza serviços existentes, worker padrão do projeto e PostgreSQL como fila. Novo modelo e conector têm necessidade demonstrável: o pedido é operar sem acesso ao servidor. |
| II. Integridade das Votações | PASS | Nenhuma alteração em cédulas ou snapshots. Importações não modificam votações existentes; snapshots permanecem imutáveis. |
| III. Privacidade das Cédulas | PASS | Importação não acessa, registra ou expõe escolhas de cédula. |
| IV. Consistência do Catálogo e das Imagens | PASS COM RESSALVA | A aplicação continua usando imagens locais no uso normal. A dependência externa existe apenas durante a importação administrativa, sob demanda. Identidade estável, checksum e snapshots são preservados. |
| V. Segurança Proporcional | PASS | Acesso administrativo com senha, CSRF, allowlist de domínios, limites de tamanho/tempo, validação de imagem e auditoria. Sem dependência externa desnecessária para participantes. |
| VI. Experiência Consistente | PASS | Fluxo em PT-BR, estados de fila/execução/sucesso/parcial/falha/cancelado, progresso e mensagens acionáveis; design segue o admin existente. |
| VII. Manutenibilidade | PASS | Conector isolado por fonte, serviços testáveis, migrações, contratos e testes com fixtures; invariantes de `ImportJob` reforçadas por constraints e trigger; fluxo manual permanece como fallback. |
| Escopo Controlado | PASS | Ampliação de escopo aprovada explicitamente em 2026-11-12: importação assíncrona, GameTora como dependência, download automático de imagens e aplicação automática. |

**Ressalva registrada**: o Princípio IV exige imagens locais e nenhuma dependência externa durante
o uso normal. A feature mantém essa garantia: a rede só é usada quando um administrador dispara
uma importação. O sistema continua operando com o acervo local se a fonte estiver indisponível.

## Complexity Tracking

Nenhuma violação constitucional não justificada. As adições abaixo são necessárias para o fluxo
aprovado e têm alternativa mais simples considerada.

| Adição | Por que é necessária | Alternativa simples rejeitada |
|---|---|---|
| `ImportJob` + worker em comando Django | Fila durável e execução assíncrona sem manter requisição HTTP aberta | Síncrono estoura o timeout; thread no Gunicorn não sobrevive a restart; Celery/Redis adiciona infraestrutura |
| Conector + registry em código | Permitir somente fontes suportadas e impedir URL arbitrária | Scraping por URL informada cria SSRF e manutenção inviável |
| `CatalogSource.adapter` e `options` | Ligar a fonte ao conector e parametrizar sem credenciais | Tabela separada de configuração seria complexidade sem uso nesta versão |
| `sync_from_report(apply_all=True)` | Reutilizar aplicação, auditoria e transações do catálogo | Duplicar o motor de importação criaria dois caminhos de regra |
| `SyncRun.origin` | Distinguir importação externa do fluxo manual no histórico | Inferir por `triggered_by` é ambíguo e não cobre execuções automáticas |
| `store_image_bytes` | Reutilizar validação, normalização, checksum e content-addressing para arquivo e URL | Duplicar o pipeline de imagem criaria divergência de formato e validação |
| Constraints + trigger de `ImportJob` | Impedir estado terminal mutável, múltiplas execuções `running` e progresso inconsistente | Validação apenas no serviço não protege SQL direto nem concorrência |
| Serviço `import-worker` no compose | Worker isolado do Gunicorn, com volume de mídia compartilhado | Executar no container `web` compete com o tráfego e perde a execução em restart |

## Project Structure

### Documentation (this feature)

```text
specs/002-external-import/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── http-routes.md
│   ├── domain-services.md
│   ├── source-adapters.md
│   └── management-commands.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/catalog/
├── models.py                         # CatalogSource.adapter/options; ImportJob; SyncRun.origin
├── forms.py                          # ImportJobForm
├── views.py                          # iniciar, listar, detalhar, status, cancelar, repetir
├── urls.py                           # rotas admin de importação
├── migrations/
│   ├── 0004_catalogsource_adapter_importjob.py
│   ├── 0005_seed_umamusume_global.py
│   └── 0006_importjob_terminal_trigger.py
├── services/
│   ├── imports.py                    # criação, claim, execução, cancelamento, retry, stale
│   ├── sync.py                       # sync_from_report(..., apply_all=True)
│   ├── images.py                     # store_image_bytes + import via candidatos
│   └── sources/
│       ├── __init__.py
│       ├── base.py                   # protocolo, dataclasses e erros
│       ├── registry.py               # key -> conector
│       ├── http.py                   # cliente HTTP allowlisted, limites e retries
│       └── umamusume_global.py       # portal oficial + GameTora
├── management/commands/
│   └── run_import_worker.py
└── tests/
    ├── test_import_job_model.py
    ├── test_import_jobs.py
    ├── test_import_worker.py
    ├── test_source_http.py
    ├── test_source_umamusume_global.py
    ├── test_ui_admin_import.py
    └── fixtures/sources/
        ├── official_characters.json
        ├── official_character_detail.json
        ├── gametora_cards.json
        └── gametora_release.json

templates/admin/catalog/
├── import_form.html
├── import_detail.html
├── import_list.html
└── _import_status.html

static/js/
└── catalog-import.js

tests/integration/
├── test_external_import_snapshot.py
└── test_external_import_isolation.py

config/settings/
├── base.py                           # EXTERNAL_IMPORT_*
└── test.py                           # desabilita rede por padrão nos testes

scripts/
└── fetch_global_assets.py            # passa a importar o conector; continua CLI de debug

compose.yaml                          # serviço import-worker
.env.example                          # variáveis da importação
docs/operations.md                    # operação, diagnóstico e recuperação
```

**Structure Decision**: manter o monólito Django e o app `catalog` como dono do domínio de
catálogo. O conector externo fica em `apps/catalog/services/sources/` porque é uma implementação
de infraestrutura de coleta, não uma regra de votação. O worker fica em `management/commands/`
para reutilizar o padrão operacional já usado por `run_scheduler`.

## Implementation Phases

### Fase 0 — Fundação

- Adicionar `adapter` e `options` a `CatalogSource`.
- Criar `ImportJob` e a migration correspondente, incluindo constraints e trigger de
  imutabilidade terminal.
- Adicionar `origin` a `SyncRun`.
- Criar data migration da fonte `umamusume-global` com `adapter="umamusume-global"` e nota de
  licença.
- Criar protocolo, registry e cliente HTTP de fonte.
- Refatorar `sync_from_file` para `sync_from_report` com opção `apply_all`.
- Refatorar `import_images` para expor `store_image_bytes`.
- Criar comando `run_import_worker` com advisory lock e claim.
- Configurar settings, logging, compose e `.env.example`.
- Criar factories e fixtures de teste.

### Fase 1 — Catálogo externo (US1)

- Implementar `UmamusumeGlobalAdapter.fetch_catalog()`.
- Implementar criação de `ImportJob` pela view.
- Implementar fase de catálogo no worker.
- Implementar relatório de catálogo.
- Criar tela de início, detalhe e status.
- Cobrir com testes de conector, serviço, worker e rota.

### Fase 2 — Imagens (US2)

- Implementar `iter_images()` no conector.
- Implementar escopo `all` e `missing`.
- Implementar download concorrente controlado, validação e `store_image_bytes`.
- Implementar relatório de imagens e link para validação do acervo.
- Cobrir com testes de imagem, falha isolada e idempotência.

### Fase 3 — Operação de execuções (US3)

- Implementar progresso via polling JSON.
- Implementar cancelamento, repetição e recuperação de execução órfã.
- Implementar histórico e filtros, incluindo última falha por fonte.
- Implementar atualização automática da tela de detalhe.
- Cobrir com testes de estados, concorrência, constraints, snapshots e 409.

### Fase 4 — Diagnóstico e endurecimento (US4)

- Implementar verificação de disponibilidade da fonte.
- Exibir todas as fontes no painel, com última execução, situação e motivo; o seletor do
  formulário lista apenas fontes elegíveis.
- Bloquear novas execuções pelo kill switch com aviso discreto, sem banners de alerta.
- Aplicar limites, allowlist, bloqueio de IP privado e validação de redirecionamento.
- Atualizar documentação operacional.
- Executar revisão de segurança e validação de quickstart.

## Critical Flows and Transaction Boundaries

### Criação da execução

1. A view valida permissão, CSRF, fonte habilitada, conector registrado e configuração global.
2. O painel de fontes exibe todas as fontes cadastradas, com situação e último resultado; o
   seletor do formulário usa apenas fontes habilitadas com conector registrado.
3. `create_import_job()` cria `ImportJob(status=queued, phase=queued)` em transação.
4. Se já existir execução ativa para a mesma fonte, a view redireciona para a execução existente
   com mensagem informativa, em vez de duplicar.
5. Redireciona para o detalhe; nenhuma coleta acontece na requisição.

### Claim e lock do worker

1. O worker adquire um advisory lock global de importação.
2. Seleciona a execução mais antiga com `status=queued` usando
   `select_for_update(skip_locked=True)`.
3. Marca `running`, incrementa `attempts`, grava `started_at` e `heartbeat_at`.
4. Libera o lock de linha e mantém o advisory lock até o fim da execução.
5. Se não houver execução, dorme pelo intervalo configurado.

### Fase de catálogo

1. Conector coleta dados oficiais e do GameTora.
2. Monta `CatalogParseReport` em memória, aplicando as mesmas validações do CSV.
3. Erros sistêmicos, schema global inválido e conflitos de identidade/versão abortam a fase sem
   gravar. Avisos de item (detalhe 404, metadados opcionais ausentes, data desconhecida) são
   acumulados; a personagem é ignorada e as demais continuam.
4. `sync_from_report(report, source, apply_all=True, triggered_by=job.triggered_by,
   origin=SyncRun.Origin.EXTERNAL)` roda em uma única transação.
5. Cada mudança gera `SyncChange(status=auto_applied)` para auditoria.
6. `SyncRun.status=success`, `origin=external`; o ID é vinculado ao `ImportJob`.

### Fase de imagens

1. Lista personagens do catálogo (ou apenas as sem imagem válida, conforme escopo).
2. Atualiza `progress_total` e `current_step`.
3. Baixa imagens com concorrência limitada e timeout por requisição.
4. Valida e normaliza em memória; cada gravação ocorre em transação própria.
5. Erros de imagem são acumulados no relatório e não interrompem as demais.
6. Ao final, define `success` se não houve erro, `partial` se houve erro isolado e `failed` se a
   fase não pôde ser iniciada.

### Cancelamento

1. A view chama `request_cancel` para execuções `queued` ou `running`.
2. Na fila, a execução é marcada `cancelled` imediatamente; o worker não a inicia.
3. Na fase de imagens, a view marca `cancel_requested=True`; o worker verifica a flag entre
   itens e encerra com `cancelled` em até 1 item.
4. Na fase de catálogo, a flag é verificada antes da aplicação; a coleta em curso não é abortada,
   mas nenhuma alteração é gravada após a solicitação.
5. O que já foi aplicado é preservado; o relatório registra o ponto de parada.

### Falha e recuperação

- `failed` quando a fase de catálogo falha ou quando o worker não consegue iniciar a execução.
- `partial` quando o catálogo conclui e uma ou mais imagens falham.
- Execução `running` sem `heartbeat_at` recente é marcada como `failed`, com `phase=finished`,
  por rotina do worker.
- `retry` cria uma nova execução com os mesmos parâmetros; a anterior permanece no histórico.

## Security Plan

### Superfície e permissões

- Todas as rotas novas usam `@admin_required`.
- POST obrigatório para criar, cancelar e repetir; CSRF em todos os formulários.
- Nenhuma rota aceita URL, host, credencial ou caminho de arquivo do usuário.
- Configuração global `EXTERNAL_IMPORT_ENABLED` atua como kill switch.

### SSRF e rede

- Allowlist de hosts por conector, definida em código.
- Somente HTTPS.
- Redirecionamentos limitados; host final precisa estar na allowlist.
- Resolução DNS validada para bloquear loopback, link-local, multicast e faixas privadas.
- Timeout de conexão e leitura, limite de bytes por resposta e limite de itens por execução.
- User-Agent identificável e taxa de requisições controlada.

### Conteúdo externo

- JSON e HTML tratados como não confiáveis; parsing tolerante a campos ausentes.
- Imagens validadas com Pillow (`verify()` + `load()`), limite de pixels e formatos permitidos.
- Conversão para WebP 256×256, remoção de metadados e checksum do resultado.
- Caminho de destino derivado de `Character.stable_id` já validado como slug.
- Nenhum nome, URL ou mensagem remota é usado diretamente em caminho de arquivo.

### Invariantes no banco

- `ImportJob` MUST ter `CheckConstraint` para `kind`, `status`, `phase`, progresso
  (`progress_done <= progress_total`), consistência de `finished_at`/`phase` e preenchimento de
  `cancelled_by`/`cancel_requested_at` quando `status=cancelled`.
- Um índice único parcial MUST impedir mais de uma execução `running` simultânea.
- Um trigger MUST impedir `UPDATE` e `DELETE` de execuções em estado terminal, preservando o
  histórico.
- O advisory lock continua sendo o mecanismo de exclusão mútua entre workers; as constraints
  reforçam a integridade mesmo em SQL direto.

### Licença e auditoria

- `CatalogSource.license_note` é um metadado interno, sem exibição ou bloqueio no fluxo externo.
- `ImageAsset` registra `source`, `source_url` e `license_note`, quando cadastrada.
- `ImportJob` registra `triggered_by`, timestamps, tentativas e relatório.
- `SyncRun.origin` distingue importação manual de externa.

### Rate limit e disponibilidade

- No máximo 6 downloads simultâneos por padrão.
- Retry com backoff exponencial para 429, 5xx e timeouts.
- Falha da fonte não afeta páginas de participantes; o acervo local continua servindo.
- Importação não roda no processo Gunicorn.

## Testing Strategy

### Unitários

- Cliente HTTP: allowlist, HTTPS, redirecionamento, timeout, tamanho máximo, retry.
- Conector oficial: parsing da lista, detalhe, normalização de nome e slug.
- Conector GameTora: cards, build ID, datas e aptidões, fallback de data.
- Regras de aplicação automática: `sync_from_report(apply_all=True)` gera `auto_applied` e zero
  pendências.
- `store_image_bytes`: normalização, checksum, reutilização, substituição e erros.
- Relatório: contagens e serialização.
- Invariantes de `ImportJob`: constraints, índice parcial e trigger de imutabilidade terminal.

### Integração

- Criação de job pela view com fonte válida, inválida e desabilitada.
- Painel de fontes exibe todas; formulário lista somente fontes elegíveis.
- Worker executando catálogo e imagens com HTTP mockado.
- Matriz erro × aviso: falha sistêmica aborta; detalhe 404/metadados ausentes geram aviso.
- Catálogo atômico: falha no meio não deixa dados parciais.
- Snapshots de votação existentes permanecem inalterados após importação.
- Nenhuma requisição externa de imagem nas páginas de participante.
- Imagens parciais: uma falha não impede as demais.
- Cancelamento: imagens em até 1 item; catálogo não aplica após a solicitação.
- Repetição, stale recovery e concorrência.
- Permissões e CSRF.
- Idempotência: duas execuções seguidas.
- Última falha por fonte e logs estruturados de transição.

### Fixtures

- Respostas reais reduzidas da API oficial e do GameTora em
  `apps/catalog/tests/fixtures/sources/`.
- Nenhum teste acessa a internet.
- Testes de worker usam `transaction=True` quando necessário.

### E2E opcional

- Administrador inicia importação, vê progresso, abre detalhe e valida que personagens e imagens
  aparecem no catálogo.

## Deployment and Operations

- Novo serviço `import-worker` no `compose.yaml`:

  ```yaml
  import-worker:
    <<: *app
    command: ["python", "manage.py", "run_import_worker", "--interval", "5"]
    depends_on:
      db:
        condition: service_healthy
      release:
        condition: service_completed_successfully
    volumes:
      - media_data:/app/media
  ```

- Migrations são executadas pelo serviço `release`, como hoje.
- O worker compartilha o volume `media_data` com `web`.
- Não é necessário cron para importação manual; o worker fica ocioso quando não há jobs.
- Logs do worker incluem `job_id`, fonte, fase, progresso e erros, sem dados sensíveis.
- O kill switch permite desligar a feature sem remover código ou dados.
- Backups continuam cobrindo banco e `media/`; relatórios ficam no banco.

## Risks and Open Decisions

| Risco | Impacto | Mitigação |
|---|---|---|
| GameTora muda HTML/JSON ou bloqueia o agente | Catálogo falha | Conector isolado, fixtures, mensagem clara, verificação de fonte, atualização pontual |
| Portal oficial muda o schema | Catálogo falha | Contract tests com fixtures e validação explícita de campos obrigatórios |
| Fonte limita requisições | Importação lenta ou parcial | Concorrência limitada, backoff, cache por execução |
| Imagens sem autorização de uso | Risco jurídico | Metadados de origem e URL registrados no acervo; revisão operacional fora do fluxo |
| Worker cai no meio | Execução órfã | Heartbeat, stale recovery e retry idempotente |
| Catálogo muito maior que 85 personagens | Execução longa | Progresso, concorrência controlada e limites |
| Fonte muda nome canônico | Duplicidade de personagem | `stable_id` determinístico + relatório de conflitos; revisão manual |
| Importação automática aplica dado errado | Catálogo incorreto | Auditoria em `SyncChange`, relatório detalhado, possibilidade de corrigir na fonte e reimportar |
| Download de imagem maliciosa | Consumo de memória ou arquivo inválido | Limite de bytes/pixels, Pillow, formatos permitidos, normalização |
| DNS rebinding | Conexão para IP não previsto após a validação | Allowlist, HTTPS e validação do IP resolvido; risco residual aceito no contexto interno |
| Duas importações simultâneas | Conflito e rate limit | Advisory lock global e uma execução por vez |

**Decisões fechadas em 2026-11-12**:

1. Execução assíncrona desde o início.
2. GameTora como dependência do conector Global.
3. Download automático de imagens.
4. Aplicação automática do catálogo, sem prévia ou aprovação.

**Fora de escopo**:

- Cadastro de fontes pela interface.
- Agendamento automático de importações externas.
- Edição manual de dados coletados antes da aplicação.
- Suporte a múltiplas fontes simultâneas.
- Fila externa, Celery ou Redis.

## Generated Artifacts

- `specs/002-external-import/spec.md`
- `specs/002-external-import/plan.md`
- `specs/002-external-import/research.md`
- `specs/002-external-import/data-model.md`
- `specs/002-external-import/quickstart.md`
- `specs/002-external-import/contracts/http-routes.md`
- `specs/002-external-import/contracts/domain-services.md`
- `specs/002-external-import/contracts/source-adapters.md`
- `specs/002-external-import/contracts/management-commands.md`
- `specs/002-external-import/checklists/requirements.md`
- `specs/002-external-import/tasks.md`
