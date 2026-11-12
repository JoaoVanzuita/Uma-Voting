# Contract: Serviços de Domínio da Importação Externa

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Princípio**: views apenas orquestram entrada/saída; regras de fila, aplicação e imagem ficam em
serviços testáveis; o banco reforça as invariantes críticas.

## 1. Convenções

- Serviços ficam em `apps/catalog/services/`.
- Operações que alteram estado crítico usam `transaction.atomic()`.
- Serviços recebem IDs e valores primitivos; não recebem `request`.
- Erros de negócio usam exceções específicas, traduzidas para PT-BR na view.
- Nenhum serviço registra escolhas de cédula.
- Nenhum serviço faz chamada de rede dentro de uma transação longa.
- O worker é o único que executa coleta; a view apenas cria/consulta/cancela/repete.

## 2. Exceções

```python
class ImportJobError(Exception): ...
class ImportJobStateError(ImportJobError): ...       # 409
class ImportSourceError(ImportJobError): ...         # fonte inválida/sem conector
class ImportDisabledError(ImportJobError): ...       # kill switch
class SourceError(Exception): ...                    # base de falhas de coleta
class SourceHTTPError(SourceError): ...              # status, timeout, tamanho, redirect
class SourceDataError(SourceError): ...              # JSON/HTML inesperado
class SourceUnavailableError(SourceError): ...       # check() falhou
```

## 3. Registry de conectores

### 3.1 `apps.catalog.services.sources.registry`

```python
def get_adapter(source: CatalogSource, *, require_enabled: bool = True) -> ExternalSourceAdapter: ...
def get_adapter_class(key: str) -> type[ExternalSourceAdapter] | None: ...
def available_sources() -> QuerySet[CatalogSource]: ...
def is_supported(source: CatalogSource) -> bool: ...
```

Regras:

- `get_adapter` levanta `ImportSourceError` se `source.adapter` estiver vazio ou não registrado.
- Com `require_enabled=True` (padrão), também exige `source.enabled=True`.
- `check_source` usa `require_enabled=False` para diagnosticar fontes desabilitadas.
- `available_sources()` retorna fontes `enabled=True` com `adapter` registrado; é usado pelo
  seletor do formulário, não pelo painel de diagnóstico.
- O registry é preenchido em tempo de importação do módulo, sem descoberta dinâmica de pacotes.

## 4. Criação e operação de execuções

### 4.1 `create_import_job(source, kind, *, options, triggered_by) -> ImportJob`

Valida:

- `settings.EXTERNAL_IMPORT_ENABLED` é `True`;
- `source.enabled` é `True`;
- existe conector para `source.adapter`;
- `kind` em `catalog|images|full`;
- `image_scope` em `missing|all`.

Comportamento:

- Em transação, cria `ImportJob(status=queued, phase=queued)`.
- Se já existir job `queued|running` para a mesma fonte, retorna o existente
  (`already_active=True`) em vez de criar outro.
- Não faz chamada de rede.
- Não grava catálogo ou imagem.

### 4.2 `request_cancel(job, admin) -> ImportJob`

- `queued` → `cancelled`, `finished_at=now`, `phase=finished`, `cancelled_by=admin`,
  `cancel_requested_at=now`, `current_step="Cancelada antes de iniciar"`.
- `running` → `cancel_requested=True`, `cancelled_by=admin`, `cancel_requested_at=now`;
  não altera status até o worker encerrar.
- Terminal → `ImportJobStateError`.
- `cancelled_by` registra o administrador responsável pelo cancelamento.

### 4.3 `request_retry(job, admin) -> ImportJob`

- Permitido para `partial|failed|cancelled`.
- Bloqueado para `queued|running`.
- Usa `create_import_job` para validar configuração e duplicata ativa.
- Cria novo `ImportJob` com a mesma fonte, `kind` e `options`.
- `attempts=0`, `triggered_by=admin`, `retry_of=job`.
- Não copia relatório nem vínculo `sync_run`.
- Se já houver execução ativa da mesma fonte, retorna a existente sem criar outra.
- Retorna o novo job.

### 4.4 `mark_stale_jobs(now=None, threshold=600) -> int`

- Busca `status=running` com `heartbeat_at` nulo ou anterior a `now - threshold`.
- Marca `failed`, `finished_at=now`, `phase=finished`,
  `error_message="Execução interrompida sem sinal de vida."`.
- Retorna a quantidade afetada.
- Executado no início de cada ciclo do worker.

### 4.5 `claim_next_job(worker_id) -> ImportJob | None`

- Requer advisory lock global já adquirido pelo comando.
- Seleciona o `queued` mais antigo com `select_for_update(skip_locked=True)`.
- Atualiza `status=running`, `phase=catalog|images` conforme `kind`, `started_at=now`,
  `heartbeat_at=now`, `attempts += 1`.
- Retorna `None` se não houver job.

### 4.6 `run_import_job(job_id, worker_id) -> ImportJob`

Orquestra a execução:

```python
job = ImportJob.objects.select_related("source").get(pk=job_id)
adapter = get_adapter(job.source)

if job.kind in {Kind.CATALOG, Kind.FULL}:
    run_catalog_phase(job, adapter)
if job.kind in {Kind.IMAGES, Kind.FULL} and job.status not in TERMINAL:
    run_images_phase(job, adapter)
```

- Atualiza `heartbeat_at` e `progress_done` a cada item.
- Respeita `cancel_requested` entre itens.
- Define status final:
  - `success` se nenhuma fase teve erro;
  - `partial` se catálogo concluiu e houve erro isolado de imagem;
  - `failed` se catálogo falhou ou a fase não pôde iniciar;
  - `cancelled` se cancelamento solicitado.
- Grava `report`, `finished_at`, `error_message` e `phase=finished`.
- Em qualquer exceção inesperada, marca `failed` e registra log com `job_id`.

### 4.7 `run_catalog_phase(job, adapter) -> SyncRun | None`

1. `phase=catalog`, `current_step="Coletando catálogo"`.
2. `report = adapter.fetch_catalog()`.
3. Erros sistêmicos, schema global inválido e conflitos de identidade/versão compõem
   `report.errors` e abortam a fase. Avisos de item (detalhe 404, metadados opcionais ausentes,
   data desconhecida) são acumulados em `report.warnings`; a personagem é ignorada e as demais
   continuam.
4. Verifica `cancel_requested`; se solicitado, encerra a fase sem aplicar.
5. Se `report.has_errors`: falha a fase sem gravar.
6. `sync_run = sync_from_report(report, job.source, triggered_by=job.triggered_by,
   apply_all=True, origin=SyncRun.Origin.EXTERNAL)`.
7. Vincula `job.sync_run = sync_run`.
8. Preenche `report["catalog"]` com contagens.
9. `phase=images` se `kind=full`; caso contrário, mantém `phase=catalog` até a finalização do
   job.

Falha sistêmica da fonte oficial ou do GameTora, schema inválido ou conflito de
identidade/versão ⇒ `SourceError`/`ImportIssue` ⇒ fase falha ⇒ job `failed`.

### 4.8 `run_images_phase(job, adapter) -> None`

1. `phase=images`.
2. Determina personagens:
   - `all`: todas as personagens;
   - `missing`: personagens sem `ImageAsset(is_current=True, status=valid)`.
3. `progress_total = len(characters)`, `progress_done=0`.
4. Itera candidatos de `adapter.iter_images(characters, only_missing=...)`.
5. Para cada imagem:
   - verifica `cancel_requested`; se solicitado, encerra a fase com `cancelled`;
   - atualiza `current_step`;
   - chama `store_image_bytes(...)` em transação própria;
   - incrementa `progress_done`;
   - atualiza `heartbeat_at`.
6. Erros são acumulados em `report["images"]["errors"]`; não interrompem.
7. Sinaliza `partial` se houve erro e `success` caso contrário; o status final é consolidado em
   `run_import_job`.

## 5. Aplicação do catálogo

### 5.1 `sync_from_report(report, source, *, triggered_by=None, apply_all=False, origin=SyncRun.Origin.MANUAL) -> SyncRun`

Extraído de `sync_from_file`.

- `apply_all=False`: comportamento atual (novas personagens aplicadas; alterações pendentes).
- `apply_all=True`: todas as mudanças planejadas são aplicadas; cada uma gera
  `SyncChange(status=auto_applied)`; nenhuma fica pendente.
- `origin` é gravado no `SyncRun`.
- Tudo em uma única transação.
- Erros de parsing/planejamento criam `SyncRun(status=failed)` sem alterar catálogo.
- `sync_from_file` passa a chamar `sync_from_report(..., apply_all=False)`.

### 5.2 Contagens do relatório

Para cada `PlannedChange` aplicada, incrementar:

- `new_characters` para `NEW_CHARACTER`;
- `updated_characters` para `UPDATE_CHARACTER`;
- `new_versions` para `NEW_VERSION`;
- `updated_versions` para `UPDATE_VERSION`;
- `aptitude_changes` para `APTITUDE_CHANGE`.

`ignored` conta `report.ignored_characters`.

## 6. Armazenamento de imagens

### 6.1 `store_image_bytes(character, data, *, source, source_url, license_note, is_current=True, max_bytes=None, require_license=True) -> ImageStoreResult`

Extraído do miolo de `import_images`.

Responsabilidades:

- validar formato e integridade com Pillow;
- aplicar `max_bytes` (ou `MAX_IMAGE_BYTES` quando omitido) e `MAX_PIXELS`;
- exigir `license_note` quando `require_license=True` e a fonte não for `curadoria-local`
  (mantido apenas para o fluxo manual por CSV);
- normalizar para WebP 256×256;
- calcular SHA-256;
- calcular destino `characters/<stable_id>/<sha256>.webp`;
- reutilizar asset existente com mesmo checksum;
- se `is_current`, desmarcar a imagem corrente anterior;
- preservar arquivo antigo;
- criar/atualizar `ImageAsset` com `source`, `source_url`, `license_note`;
- gravar arquivo de forma atômica (`tempfile` + `os.replace`);
- retornar `action` (`create|replace|reuse`), `checksum`, `destination`, `message`.

Erros:

- `ValueError` para imagem inválida, formato não permitido, dimensões fora do padrão ou bytes
  acima do limite.
- `OSError` para falha de disco.

O chamador (worker) converte esses erros em item do relatório e continua.

### 6.2 `import_images(manifest, source_dir, *, dry_run=True)`

Mantido para compatibilidade. Passa a usar `store_image_bytes` internamente, sem mudança de
comportamento observável.

## 7. Verificação de fonte

### 7.1 `check_source(source) -> SourceCheckResult`

- Executa `adapter.check()` com timeout curto.
- Retorna `{ok: bool, message: str, checked_at: datetime}`.
- Não cria job, não grava catálogo/imagens.
- Funciona para fonte desabilitada que possua conector, permitindo diagnóstico; `get_adapter` é
  chamado com `require_enabled=False`.
- `ImportSourceError` se a fonte não tiver conector.

## 8. Logging

Logger: `apps.catalog.imports`.

Eventos:

- `import_job.created`, `claimed`, `phase.started`, `phase.finished`, `completed`,
  `cancelled`, `stale`, `retry_requested`.
- Campos: `job_id`, `source`, `kind`, `status`, `phase`, `progress_done`, `progress_total`,
  `duration_ms`, `error` (resumido).
- Nunca registrar credenciais, cookies, corpo de resposta ou escolhas de cédula.

## 9. Invariantes no banco

- `ImportJob` tem `CheckConstraint` para `kind`, `status`, `phase`, progresso, consistência de
  estado terminal e cancelamento.
- `uniq_import_job_running` impede mais de uma execução `running` simultânea.
- Trigger `catalog_importjob_terminal_immutable` bloqueia `UPDATE` de execução em estado
  terminal; trigger `catalog_importjob_no_delete` bloqueia `DELETE`.
- `finished_at` e `phase=finished` são gravados no mesmo `UPDATE` que leva ao estado terminal.
- O advisory lock global continua sendo o mecanismo de exclusão mútua entre workers; as
  constraints são a última linha de defesa contra SQL direto.

## 10. Idempotência

- `create_import_job` não duplica job ativo da mesma fonte.
- `sync_from_report(apply_all=True)` pode ser repetido: personagens/versões existentes são
  atualizadas, não duplicadas.
- `store_image_bytes` reutiliza checksum existente.
- Repetir uma execução cria novo job; não altera o anterior.
- Cancelar e repetir é seguro; o catálogo é atômico e as imagens são por item.

## 11. Dependências entre serviços

```text
views
  └── imports.create_import_job / request_cancel / request_retry
        └── registry.get_adapter
worker
  └── imports.claim_next_job / run_import_job / mark_stale_jobs
        ├── sources.<adapter>.fetch_catalog / iter_images / check
        ├── sync.sync_from_report(apply_all=True)
        └── images.store_image_bytes
```
