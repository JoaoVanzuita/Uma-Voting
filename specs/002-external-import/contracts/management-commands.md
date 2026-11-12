# Contract: Comandos de Gerenciamento da Importação Externa

**Feature**: `002-external-import`
**Date**: 2026-11-12

## 1. Convenções

- Todos os comandos usam `python manage.py <comando>`.
- Saída legível por padrão; `--json` quando indicado.
- Código de saída `0` em sucesso, `1` em erro de negócio e `2` em erro inesperado.
- Comandos não registram credenciais, cookies ou escolhas de cédula.
- Nenhum comando é executado no processo Gunicorn.

## 2. `run_import_worker`

Worker de importação externa.

```bash
python manage.py run_import_worker --interval 5
python manage.py run_import_worker --once
python manage.py run_import_worker --once --json
```

### 2.1 Opções

| Opção | Tipo | Padrão | Descrição |
|---|---|---|---|
| `--interval` | inteiro (segundos) | `5` | Intervalo de polling quando não há jobs |
| `--once` | flag | `False` | Executa no máximo um ciclo e encerra |
| `--json` | flag | `False` | Emite o resumo do ciclo em JSON |

### 2.2 Ciclo

1. Adquire advisory lock global (`pg_try_advisory_lock`).
   - Se não adquirir, outro worker está ativo; dorme e tenta novamente.
2. `mark_stale_jobs()`.
3. `claim_next_job()`.
4. Se houver job:
   - `run_import_job(job.pk, worker_id)`;
   - registra resultado;
   - repete imediatamente o ciclo (pode haver fila).
5. Se não houver job:
   - dorme `--interval` segundos.
6. `--once` encerra após um ciclo, mesmo sem job.
7. Libera o advisory lock ao encerrar.

### 2.3 Saída

Texto:

```text
Ciclo concluído: 1 job processado; 0 stale; 0 erro(s).
```

JSON:

```json
{
  "worker_id": "import-worker-1",
  "stale_jobs": 0,
  "processed": [
    {
      "job_id": 42,
      "source": "umamusume-global",
      "kind": "full",
      "status": "success",
      "catalog": {"new_characters": 2, "updated_characters": 3},
      "images": {"created": 80, "replaced": 2, "reused": 3, "errors": 0}
    }
  ],
  "errors": []
}
```

### 2.4 Códigos de saída

| Código | Situação |
|---|---|
| `0` | Ciclo concluído, com ou sem job |
| `1` | Job processado terminou em `failed` por erro de fonte/dados |
| `2` | Erro inesperado do worker |

`partial` e `cancelled` não tornam o ciclo falho; o job registra o resultado.

### 2.5 Sinais

- `SIGTERM`/`SIGINT`: encerra o loop após o item atual; o job em andamento fica `running` e será
  recuperado como stale se o processo não concluir.
- Não usar `kill -9` como operação normal.

### 2.6 Logs

Logger `apps.catalog.imports`:

```text
import_job.claimed job_id=42 source=umamusume-global kind=full
import_job.phase.started job_id=42 phase=catalog
import_job.phase.finished job_id=42 phase=catalog duration_ms=48210
import_job.completed job_id=42 status=success duration_ms=512300
```

Campos: `job_id`, `source`, `kind`, `phase`, `status`, `progress_done`, `progress_total`,
`duration_ms`, `error` resumido.

## 3. Comandos existentes

Permanecem sem alteração de contrato:

- `import_catalog --file ... --source ... [--apply]`
- `import_images --manifest ... --source-dir ... [--apply]`
- `validate_images`
- `sync_catalog`
- `create_admin`

O fluxo externo é aditivo. O fallback manual continua disponível se uma fonte mudar ou a
importação externa for desabilitada.

## 4. Operação no compose

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

- Um único serviço `import-worker` é suficiente.
- Escalar para mais de uma réplica é permitido, mas o advisory lock garante uma execução por vez.
- O worker não serve HTTP.
- O worker compartilha `media_data` com `web`.

## 5. Diagnóstico

```bash
# acompanhar o worker
docker compose logs -f import-worker

# executar um ciclo único
docker compose exec import-worker python manage.py run_import_worker --once

# ver jobs presos (via shell)
docker compose exec web python manage.py shell -c "
from apps.catalog.models import ImportJob
print(list(ImportJob.objects.filter(status__in=['queued','running']).values('id','source__name','status','heartbeat_at')))
"
```

- Execuções `running` sem heartbeat são marcadas como `failed` no próximo ciclo.
- O administrador pode repetir pela interface.
- O kill switch é `EXTERNAL_IMPORT_ENABLED=False`.
