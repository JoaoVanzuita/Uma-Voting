# Operações — Uma Voting

**Data**: 2026-11-07
**Constituição**: 2.0.0

## 1. Ambientes

- **Desenvolvimento**: Docker Compose com `compose.override.yaml`, Django `runserver` e
  PostgreSQL local.
- **Staging temporário**: `config.settings.staging` (herda de `dev`) apontando para um banco
  separado, útil para testes ponta a ponta sem tocar nos dados de desenvolvimento.
- **Produção**: `compose.yaml` + `compose.prod.yaml`, Gunicorn, scheduler, Caddy e PostgreSQL.
- **Variáveis**: `.env` não versionado; consulte `.env.example`.

### 1.1 Staging temporário

```bash
# cria o banco (uma vez)
docker compose exec db createdb -U uma_voting uma_voting_staging

# migrations, cache e admin no banco de staging
DJANGO_SETTINGS_MODULE=config.settings.staging ./scripts/dev.sh
```

O sufixo do banco pode ser trocado com `STAGING_POSTGRES_DB`. Para descartar o ambiente:

```bash
docker compose exec db dropdb -U uma_voting uma_voting_staging
```


## 2. Deploy e release

```bash
docker compose -f compose.yaml -f compose.prod.yaml build
docker compose -f compose.yaml -f compose.prod.yaml run --rm release
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

O serviço `release` executa `migrate`, `collectstatic` e `createcachetable` uma vez. Migrations
não rodam no entrypoint de cada worker.

## 3. Scheduler e sincronização

- **Transições de votação**: container `scheduler` executa
  `python manage.py run_scheduler --interval 60`.
- **Sincronização de catálogo**: cron/systemd diário às 03:00 chamando
  `scripts/sync_catalog.sh`; o scheduler de votos não sincroniza catálogo.
- **Sessões**: `clearsessions` diário via cron/systemd.
- **Idempotência**: transições usam lock de banco e podem ser repetidas com segurança.

Exemplo de cron (horário de `America/Sao_Paulo`):

```cron
0 3 * * * cd /app && CATALOG_FILE=/app/var/catalog.csv ./scripts/sync_catalog.sh
30 3 * * * cd /app && python manage.py clearsessions
```

Sincronização manual:

```bash
CATALOG_FILE=/app/var/catalog.csv ./scripts/sync_catalog.sh
python manage.py import_catalog --file catalog.csv --source curadoria-local --apply
```

## 4. Backups e restauração

```bash
# banco e mídia (usa POSTGRES_* do ambiente)
./scripts/backup.sh

# restauração (ambiente limpo)
RESTORE_CONFIRM=sim ./scripts/restore.sh \
  /backups/db-AAAAMMDDTHHMMSSZ.dump /backups/media-AAAAMMDDTHHMMSSZ.tar.gz
```

- Retenção: 30 backups diários + 12 mensais, fora do host.
- Testar restauração trimestralmente em ambiente limpo.
- Incluir banco e `media/` no mesmo procedimento.

```cron
15 2 * * * cd /app && ./scripts/backup.sh
```

## 5. Revisão manual de licença de imagens

Antes de aplicar um manifesto externo:

1. Conferir origem, termos e autorização de uso.
2. Registrar a decisão no runbook/checklist.
3. Só então executar `import_images --apply`.
4. O MVP não bloqueia tecnicamente a importação; a revisão é responsabilidade administrativa
   (risco G5 aceito).

## 6. Medições de aceitação

| Critério | Procedimento | Meta |
|---|---|---|
| SC-001 | Cronometrar admin criando, configurando e agendando uma votação | <5 min |
| SC-002 | Cronometrar participante concluindo uma cédula | <3 min |
| SC-010 | Medir busca/filtros com 500 personagens | <1 s |

Registrar data, operador, ambiente e duração neste documento.

- **2026-11-07 — SC-001 (pré-validação)**: fluxo automatizado de criação, edição, ajuste de
  elegíveis e agendamento executado no ambiente de teste em 0,6 s. A medição manual de UX com
  operador será registrada na validação final (T134).
- **2026-11-07 — SC-002 (pendente)**: fluxo de cédula coberto por testes de integração; medição
  manual com participante deve ser registrada antes do deploy.
- **2026-11-07 — SC-010 (pendente)**: procedimento: importar catálogo com 500 personagens,
  abrir votação, medir busca por nome e combinação de três filtros no navegador; registrar
  duração. O grid usa `loading="lazy"` nas imagens e a busca é filtrada no servidor por HTMX.

## 7. Saúde, logs e monitoramento

- Healthcheck: `GET /health/` (aplicação + banco).
- Logs em stdout com request ID; rotação pelo Docker.
- Monitorar uptime, disco, último backup e erros 5xx.
- Não registrar escolhas de cédula, senhas ou corpos de confirmação.

## 8. Rollback e incidentes

1. Interromper o tráfego ou colocar em manutenção.
2. Restaurar a imagem/tag anterior.
3. Restaurar banco/mídia se houver migração ou corrupção.
4. Validar health, login, votação e resultados.
5. Registrar o incidente e a causa.

## 9. Rotação de segredos

- Rotacionar `SECRET_KEY` com janela de manutenção e invalidação de sessões.
- Rotacionar credenciais de banco e do proxy.
- Nunca commitar `.env` ou certificados privados.

## 10. Importação externa de catálogo e imagens

### 10.1 Worker

- Serviço `import-worker` no Compose: `python manage.py run_import_worker --interval 5`.
- Não serve HTTP; compartilha o volume `media_data` com `web`.
- Cada ciclo: advisory lock global, stale recovery, claim do job mais antigo e processamento.
- Diagnóstico de um ciclo:

```bash
docker compose exec import-worker python manage.py run_import_worker --once --json
```

### 10.2 Variáveis

| Variável | Padrão | Uso |
|---|---|---|
| `EXTERNAL_IMPORT_ENABLED` | `False` | Kill switch global; bloqueia novas execuções |
| `EXTERNAL_IMPORT_HTTP_TIMEOUT` | `15` | Timeout por requisição (segundos) |
| `EXTERNAL_IMPORT_MAX_IMAGE_BYTES` | `5242880` | Limite por imagem (bytes) |
| `EXTERNAL_IMPORT_CONCURRENCY` | `4` | Downloads simultâneos |
| `EXTERNAL_IMPORT_STALE_SECONDS` | `600` | Tempo sem heartbeat para considerar órfã |

- O kill switch bloqueia criação de jobs na interface e no serviço; catálogo, imagens e votações
  existentes continuam funcionando.
- A interface mostra o bloqueio como texto discreto, sem banner.

### 10.3 Cancelamento e recuperação

- `queued`: cancelamento encerra a execução imediatamente.
- `running`/imagens: encerra entre um item e outro, preservando o que já foi gravado.
- `running`/catálogo: nenhuma alteração é aplicada depois da solicitação.
- Execução `running` sem heartbeat por `EXTERNAL_IMPORT_STALE_SECONDS` é marcada como `failed`
  no próximo ciclo do worker.
- Repetição cria uma nova execução (`partial`, `failed` ou `cancelled`); a anterior não muda.

### 10.4 Logs

Logger `apps.catalog.imports`, sem credenciais, cookies ou escolhas de cédula:

```text
import_job.created job_id=42 source=umamusume-global kind=full
import_job.claimed job_id=42 source=umamusume-global kind=full worker=...
import_job.phase.started job_id=42 phase=catalog
import_job.phase.finished job_id=42 phase=images errors=0 cancelled=False
import_job.completed job_id=42 status=success error=
import_job.stale job_id=42
```

### 10.5 Diagnóstico

| Sintoma | Ação |
|---|---|
| Fonte inelegível no painel | Conferir `enabled` e `adapter` da fonte |
| "Importação externa desabilitada" | Ajustar `EXTERNAL_IMPORT_ENABLED` e reiniciar `web` e `import-worker` |
| Job `queued` parado | Verificar se o `import-worker` está ativo |
| Job `running` sem progresso | Aguardar stale recovery ou reiniciar o worker |
| `failed` no catálogo | Verificar disponibilidade do portal oficial/GameTora e os logs |
| `partial` com erros de imagem | Ver o relatório do job; repetir ou corrigir a fonte |
| Muitos HTTP 429 | Reduzir `EXTERNAL_IMPORT_CONCURRENCY` e tentar novamente |

### 10.6 Licença

- `CatalogSource.license_note` e `ImageAsset.license_note` permanecem como metadados internos.
- A interface de importação externa não exibe, não solicita confirmação e não bloqueia por
  licença.
- O fluxo manual por CSV mantém a revisão de licença descrita na seção 5.

## 11. Staging com acesso externo (ngrok)

```bash
./scripts/staging.sh                    # staging + túnel ngrok
./scripts/staging.sh --no-tunnel        # apenas local
./scripts/staging.sh --fresh            # recria o banco de staging
./scripts/staging.sh --reset-admin      # redefine a senha do admin
./scripts/staging.sh --domain meu.ngrok.app
```

- Usa `config.settings.staging` e o banco `uma_voting_staging`.
- Aplica migrations, garante cache e inicia o worker de importação (`--quiet`).
- Abre o túnel ngrok, lê a URL pública e exporta `DJANGO_ALLOWED_HOSTS` e
  `DJANGO_CSRF_TRUSTED_ORIGINS` antes de subir o Django.
- `Ctrl+C` encerra Django, worker e túnel.
- `EXTERNAL_IMPORT_ENABLED` é forçado para `True` neste ambiente; defina a variável no
  ambiente para outro valor.
- O túnel expõe o site publicamente: use apenas para validação e encerre ao terminar.

## 12. Limpeza do staging

Para entregar o ambiente limpo a um administrador, preservando usuários e fontes:

```bash
DJANGO_SETTINGS_MODULE=config.settings.staging \
  python manage.py shell < scripts/reset_staging.py
rm -rf media/characters
```

O script remove votações, cédulas, snapshots, catálogo, imagens e histórico de importação.
As triggers de proteção são desativadas apenas dentro da transação e reativadas ao final.

