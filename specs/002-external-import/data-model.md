# Data Model: Importação de Catálogo e Imagens de Fontes Externas

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Database**: PostgreSQL 18
**ORM**: Django 5.2

## 1. Convenções

- Chaves primárias `bigint` autoincrementais (`BigAutoField`).
- Timestamps em UTC (`DateTimeField` com `USE_TZ=True`); apresentação em
  `America/Sao_Paulo`.
- Estados e tipos usam `TextChoices`; valores persistidos em `snake_case`.
- Relatórios são `JSONField`; não há tabela por item nesta versão.
- Operações críticas rodam em `transaction.atomic()`.
- Execuções terminais (`success`, `partial`, `failed`, `cancelled`) são imutáveis.
- Nenhum campo novo expõe escolhas de cédula.

## 2. Visão geral das entidades

```text
catalog.CatalogSource 1 ─── N catalog.ImportJob
catalog.CatalogSource 1 ─── N catalog.SyncRun
catalog.ImportJob     1 ─── 0..1 catalog.SyncRun
catalog.SyncRun       1 ─── N catalog.SyncChange
catalog.Character     1 ─── N catalog.CharacterVersion
catalog.Character     1 ─── N catalog.ImageAsset (um corrente)
```

`ImportJob` é a fila durável e o histórico da importação externa. `SyncRun` continua sendo o
registro da aplicação do catálogo e o vínculo com as mudanças auditadas.

## 3. `catalog.CatalogSource` (alterações)

| Campo | Tipo | Regras |
|---|---|---|
| `adapter` | `SlugField(50)` | `blank=True`; `db_index=True`; vazio significa que a fonte não participa da importação externa |
| `options` | `JSONField` | `default=dict`, `blank=True`; parâmetros não sensíveis do conector |

Campos existentes preservados: `name`, `kind`, `base_url`, `terms_url`, `license_note`,
`enabled`, `created_at`.

### 3.1 Regras

- Uma fonte só pode ser usada na importação externa se:
  - `enabled=True`;
  - `adapter` não vazio;
  - existir um conector registrado para o valor de `adapter`;
- `adapter` não é `unique` porque mais de uma fonte pode reutilizar o mesmo conector com
  `options` diferentes.
- `options` não pode conter credenciais.

### 3.2 Dados iniciais

A migration `0005_seed_umamusume_global.py` cria/atualiza:

| Campo | Valor |
|---|---|
| `name` | `umamusume-global` |
| `kind` | `api` |
| `adapter` | `umamusume-global` |
| `base_url` | `https://umamusume.com/characters/` |
| `license_note` | `Imagens © Cygames, Inc. Uso interno; revisar autorização antes de publicar.` |
| `enabled` | `True` |

## 4. `catalog.ImportJob` (novo)

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `source` | FK `CatalogSource` | `on_delete=PROTECT`, `related_name="import_jobs"` |
| `kind` | `CharField(20)` | `catalog`, `images`, `full`; obrigatório |
| `status` | `CharField(20)` | `queued`, `running`, `success`, `partial`, `failed`, `cancelled`; default `queued` |
| `phase` | `CharField(20)` | `queued`, `catalog`, `images`, `finished`; default `queued` |
| `options` | `JSONField` | `default=dict`; ex.: `{"image_scope": "missing"}` |
| `progress_total` | `PositiveIntegerField` | default `0` |
| `progress_done` | `PositiveIntegerField` | default `0` |
| `current_step` | `CharField(200)` | `blank=True`; texto curto para a UI |
| `report` | `JSONField` | `default=dict`; schema em §4.3 |
| `error_message` | `TextField` | `blank=True`; causa resumida |
| `cancel_requested` | `BooleanField` | default `False` |
| `attempts` | `PositiveSmallIntegerField` | default `0` |
| `heartbeat_at` | `DateTimeField` | `null=True`, `blank=True` |
| `started_at` | `DateTimeField` | `null=True`, `blank=True` |
| `finished_at` | `DateTimeField` | `null=True`, `blank=True` |
| `created_at` | `DateTimeField` | `auto_now_add=True` |
| `triggered_by` | FK `settings.AUTH_USER_MODEL` | `on_delete=PROTECT`, `null=True`, `blank=True`, `related_name="catalog_import_jobs"` |
| `cancelled_by` | FK `settings.AUTH_USER_MODEL` | `on_delete=PROTECT`, `null=True`, `blank=True`, `related_name="cancelled_catalog_import_jobs"` |
| `cancel_requested_at` | `DateTimeField` | `null=True`, `blank=True` |
| `retry_of` | FK `self` | `on_delete=SET_NULL`, `null=True`, `blank=True`, `related_name="retries"` |
| `sync_run` | OneToOne `SyncRun` | `on_delete=SET_NULL`, `null=True`, `blank=True`, `related_name="import_job"` |

### 4.1 Meta

Usar `Q` e `F` de `django.db.models`.

```python
ordering = ["-created_at"]
indexes = [
    models.Index(fields=["status", "created_at"], name="catalog_import_status_idx"),
    models.Index(fields=["source", "-created_at"], name="catalog_import_source_idx"),
]
constraints = [
    models.CheckConstraint(
        condition=Q(kind__in=["catalog", "images", "full"]),
        name="import_job_kind_check",
    ),
    models.CheckConstraint(
        condition=Q(status__in=["queued", "running", "success", "partial", "failed", "cancelled"]),
        name="import_job_status_check",
    ),
    models.CheckConstraint(
        condition=Q(phase__in=["queued", "catalog", "images", "finished"]),
        name="import_job_phase_check",
    ),
    models.CheckConstraint(
        condition=Q(progress_done__lte=F("progress_total")),
        name="import_job_progress_check",
    ),
    models.CheckConstraint(
        condition=(
            (
                Q(status__in=["success", "partial", "failed", "cancelled"])
                & Q(finished_at__isnull=False)
                & Q(phase="finished")
            )
            | (
                ~Q(status__in=["success", "partial", "failed", "cancelled"])
                & Q(finished_at__isnull=True)
                & ~Q(phase="finished")
            )
        ),
        name="import_job_terminal_check",
    ),
    models.CheckConstraint(
        condition=(
            ~Q(status="cancelled")
            | (Q(cancelled_by__isnull=False) & Q(cancel_requested_at__isnull=False))
        ),
        name="import_job_cancelled_check",
    ),
    models.UniqueConstraint(
        models.Value(1),
        condition=Q(status="running"),
        name="uniq_import_job_running",
    ),
]
```

### 4.2 Enums

**Kind**

| Valor | Significado |
|---|---|
| `catalog` | Somente catálogo |
| `images` | Somente imagens, para personagens já existentes |
| `full` | Catálogo e, em seguida, imagens |

**Status**

| Valor | Significado | Terminal |
|---|---|---|
| `queued` | Aguardando worker | Não |
| `running` | Em execução | Não |
| `success` | Concluída sem erros | Sim |
| `partial` | Concluída com erros isolados | Sim |
| `failed` | Não concluída | Sim |
| `cancelled` | Interrompida por solicitação | Sim |

**Phase**

| Valor | Significado |
|---|---|
| `queued` | Ainda não iniciou |
| `catalog` | Coletando/aplicando catálogo |
| `images` | Baixando/gravando imagens |
| `finished` | Execução encerrada |

### 4.3 Schema de `report`

```json
{
  "catalog": {
    "total_rows": 85,
    "characters": 85,
    "new_characters": 2,
    "updated_characters": 3,
    "new_versions": 4,
    "updated_versions": 1,
    "aptitude_changes": 2,
    "ignored": 0,
    "warnings": [],
    "errors": []
  },
  "images": {
    "total": 85,
    "created": 80,
    "replaced": 2,
    "reused": 3,
    "skipped": 0,
    "warnings": [],
    "errors": [
      {
        "character": "special-week",
        "url": "https://...",
        "message": "Imagem indisponível (HTTP 404)."
      }
    ]
  },
  "sync_run_id": 12
}
```

Regras:

- Chaves ausentes ou `null` são tratadas como zero/lista vazia na UI.
- `errors` de catálogo usam `{"line", "field", "message"}`.
- `errors` de imagem usam `{"character", "url", "message"}`.
- O relatório é gravado ao final; durante a execução a UI usa `progress_*` e `current_step`.

### 4.4 Máquina de estados

```text
queued ──claim──> running ──sucesso──> success
   │                 │
   │                 ├──erros isolados──> partial
   │                 ├──falha fatal─────> failed
   │                 └──cancelamento────> cancelled
   └──cancelamento──> cancelled
```

Regras:

- `queued → running` somente via worker.
- `running → success|partial|failed|cancelled` somente ao encerrar a execução.
- `failed|partial|cancelled → queued` não é permitido; repetição cria novo `ImportJob`.
- `success` não pode ser repetido automaticamente; o administrador pode iniciar uma nova
  importação.

### 4.5 Invariantes

- No máximo uma execução `running` por vez (advisory lock global + índice único parcial).
- `progress_done <= progress_total` quando `progress_total > 0`.
- `finished_at` preenchido se e somente se o status for terminal.
- `sync_run` só é preenchido quando a fase de catálogo concluiu.
- `error_message` não vazio quando `status=failed`.
- `triggered_by` obrigatório para execuções criadas pela interface.
- `status=cancelled` ⇒ `cancelled_by` preenchido e `cancel_requested_at` preenchido.
- `retry_of` preenchido quando a execução foi criada por repetição; `triggered_by` identifica
  quem repetiu.

### 4.6 Reforço no banco

As invariantes viáveis são garantidas por constraints; as demais são reforçadas por trigger e
transação.

| Mecanismo | Garantia |
|---|---|
| `import_job_kind_check`, `import_job_status_check`, `import_job_phase_check` | Somente valores previstos nos enums |
| `import_job_progress_check` | `progress_done` nunca excede `progress_total` |
| `import_job_terminal_check` | Estado terminal tem `finished_at` e `phase=finished`; estado não terminal não tem |
| `import_job_cancelled_check` | `status=cancelled` exige `cancelled_by` e `cancel_requested_at` |
| `uniq_import_job_running` | No máximo uma execução `running` simultânea |
| Trigger `catalog_importjob_terminal_immutable` | Bloqueia `UPDATE` de linhas em estado terminal |
| Trigger `catalog_importjob_no_delete` | Bloqueia `DELETE` de execuções, preservando o histórico |

O trigger de imutabilidade permite a transição de `running` para um estado terminal, mas bloqueia
qualquer alteração posterior. O advisory lock global continua sendo o mecanismo de exclusão mútua
entre workers; o índice parcial protege contra SQL direto e concorrência fora do worker.

`finished_at` e `phase=finished` MUST ser gravados no mesmo `UPDATE` que leva a execução ao estado
terminal, incluindo o cancelamento de uma execução `queued`.

## 5. `catalog.SyncRun` (alteração)

| Campo | Tipo | Regras |
|---|---|---|
| `origin` | `CharField(20)` | `manual` ou `external`; default `manual` |

- `origin=external` para execuções criadas por `ImportJob`.
- `origin=manual` para o fluxo CSV existente e comandos.
- `status` continua `running`, `success`, `partial`, `failed`.
- No fluxo externo com aplicação automática, o status final é `success` se não houver mudanças
  pendentes (e não haverá, por definição).

## 6. `catalog.SyncChange` (sem alteração estrutural)

- Mudanças do fluxo externo usam `status=auto_applied`.
- `sync_run` aponta para o `SyncRun` criado pelo job.
- `payload` guarda os dados aplicados, como hoje.
- Nenhum `SyncChange` do fluxo externo fica com `status=pending`.

## 7. `catalog.Character`, `CharacterVersion`, `Aptitude` (sem alteração estrutural)

- Identidade e regras de unicidade permanecem.
- A importação externa usa os mesmos payloads do CSV.
- Conflitos de versão entre personagens continuam sendo erro de aplicação.
- Personagens sem data global são ignoradas.
- Snapshots de votações não são tocados.

## 8. `catalog.ImageAsset` (sem alteração estrutural)

- `file_path` continua único e content-addressed.
- `checksum_sha256` continua indexado.
- `source`, `source_url` e `license_note` são preenchidos pelo conector.
- `status` continua `valid`, `invalid` ou `missing`.
- `is_current` continua com no máximo um por personagem.

## 9. Retenção e histórico

- `ImportJob` e `SyncRun` são preservados indefinidamente.
- O relatório JSON faz parte do histórico e não é apagado ao repetir uma execução.
- Imagens antigas permanecem em `media/` como histórico.
- Nenhuma execução terminal é editada; correções geram nova execução.

## 10. Consultas e índices de apoio

- Última execução por fonte: `source_id` + `-created_at`.
- Fila: `status='queued'` + `created_at` ascendente.
- Histórico: `-created_at`.
- Execuções órfãs: `status='running'` + `heartbeat_at < now() - intervalo`.
- Relatório e detalhe: carregamento por PK com `select_related("source", "triggered_by",
  "sync_run")`.

## 11. Dados iniciais e migrations

| Migration | Conteúdo |
|---|---|
| `0004_catalogsource_adapter_importjob.py` | `CatalogSource.adapter`, `CatalogSource.options`, `ImportJob`, `SyncRun.origin`, constraints e índice único parcial |
| `0005_seed_umamusume_global.py` | Fonte `umamusume-global` com conector e licença |
| `0006_importjob_terminal_trigger.py` | Triggers de imutabilidade terminal e bloqueio de `DELETE` |

A migration de seed é idempotente: usa `get_or_create` por `name`, atualiza `adapter`, `kind` e
`base_url` somente quando estiverem vazios e preserva uma `license_note` já revisada manualmente.
Ela não sobrescreve a licença com o valor padrão.
