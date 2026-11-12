# Research: Importação de Catálogo e Imagens de Fontes Externas

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Status**: Phase 0 complete
**Escopo**: resolver as decisões técnicas da importação externa antes do desenho detalhado.

## 1. Resumo executivo

A feature é viável com a stack atual e sem novas dependências de runtime. As decisões aprovadas
em 2026-11-12 são:

1. Execução **assíncrona desde o início**.
2. **GameTora** como dependência do conector Global.
3. **Download automático** de imagens.
4. **Aplicação automática** do catálogo, sem prévia ou aprovação.

A arquitetura escolhida é:

```text
Interface admin → ImportJob (PostgreSQL) → run_import_worker → conector da fonte
                                                        ├→ sync_from_report(apply_all=True)
                                                        └→ store_image_bytes()
```

Não há Celery, Redis, fila externa ou processo por requisição. O worker usa o mesmo padrão do
`scheduler` de votações: comando de gerenciamento em container dedicado com advisory lock no
PostgreSQL.

## 2. Fontes externas

### 2.1 Portal oficial Global

O portal oficial expõe um CMS com endpoints JSON. O script
`scripts/fetch_global_assets.py` já os utiliza:

| Uso | URL | Observação |
|---|---|---|
| Lista de personagens | `https://en-portal.g.kuroco.app/rcms-api/4/characters` | Retorna `umamusume` com `slug`, `subject` e dados de apresentação |
| Detalhe | `https://en-portal.g.kuroco.app/rcms-api/4/characters/{slug}` | Retorna `details` com dados complementares |
| Página pública | `https://umamusume.com/characters/{slug}/` | Referência para a URL de origem |
| Ícone | URL presente no payload oficial | PNG 400×400 com transparência |

**Decisão**: usar o portal oficial como fonte primária de identidade, nome e imagem. A URL de
origem registrada em `ImageAsset` é a página pública da personagem.

### 2.2 GameTora

O GameTora não expõe uma API pública estável; o script atual usa os JSONs internos do site:

| Uso | URL | Observação |
|---|---|---|
| Página de personagens | `https://gametora.com/umamusume/characters` | Usada para descobrir build ID e chunk de cards |
| Cards | `/data/umamusume/character-cards.<hash>.json` | Nome do arquivo tem hash de conteúdo; há fallback fixo no script |
| Detalhe por personagem | `https://gametora.com/_next/data/{buildId}/umamusume/characters/{url_name}.json` | Usado para datas estimadas de banners EN |
| Build ID | `"buildId":"..."` no HTML | Muda a cada deploy do GameTora |

O script usa o GameTora para:

- datas de lançamento global (`release_en`);
- aptidões (estratégia, distância, superfície);
- estimativa de data a partir de banners EN quando `release_en` está ausente.

**Decisão**: manter o GameTora como dependência, isolado atrás do conector. Riscos:

- mudança de HTML/JSON interna;
- bloqueio de agente ou rate limit;
- ausência de contrato público e de garantia de disponibilidade;
- condições de uso não documentadas de forma estável.

Mitigações: allowlist de domínios, User-Agent identificável, concorrência limitada, cache por
execução, fixtures de teste, mensagem de falha clara e atualização pontual do conector.

### 2.3 Alternativas consideradas

| Fonte | Situação | Decisão |
|---|---|---|
| `umapyoi.net` | API documentada, mas sem adaptador implementado no projeto | Fora do escopo desta versão |
| Repositórios comunitários | Dados inconsistentes e sem garantia de atualização | Não usar como fonte primária |
| Curadoria manual por CSV | Já existe e funciona | Mantido como fallback e caminho alternativo |
| Scraping genérico por URL | SSRF, fragilidade e custo de manutenção | Rejeitado; somente conectores em código |

## 3. Execução assíncrona

### 3.1 Decisão

Fila no PostgreSQL + worker em comando de gerenciamento.

```text
ImportJob(status=queued)
    ↓
run_import_worker --interval 5
    ↓ advisory lock global + select_for_update(skip_locked=True)
ImportJob(status=running)
    ↓
fase catálogo → fase imagens → relatório
```

### 3.2 Alternativas

| Alternativa | Problema |
|---|---|
| Síncrono na requisição | 85 personagens + 85 imagens excedem o timeout de 60 s do Gunicorn; usuário perde a resposta |
| Thread dentro do Gunicorn | Sem garantia de vida, sem observabilidade, reinício do worker mata a execução |
| Celery + Redis | Nova infraestrutura e dependência; contraria a simplicidade e o padrão atual |
| `subprocess` por requisição | Difícil de controlar, sem fila, risco de duplicação |
| Worker com advisory lock | Reutiliza padrão existente, sem dependência nova, com fila durável no banco |

### 3.3 Claim e concorrência

- Advisory lock global de importação para garantir uma execução por vez.
- `select_for_update(skip_locked=True)` para claim seguro.
- `heartbeat_at` atualizado a cada item.
- Execução `running` sem heartbeat por 10 minutos é marcada como `failed`.
- `attempts` registra tentativas de claim; repetição manual cria novo job e zera o contador.

## 4. Aplicação automática do catálogo

### 4.1 Decisão

O fluxo externo aplica todas as mudanças automaticamente (`apply_all=True`), incluindo
atualizações de personagens existentes. Cada mudança gera `SyncChange(status=auto_applied)` para
auditoria, mas nenhuma fica pendente.

### 4.2 Racional

- Decisão explícita do mantenedor em 2026-11-12.
- O catálogo é derivado de fonte externa; exigir aprovação item a item tornaria a operação
  inviável para 85 personagens.
- Snapshots de votações existentes são imutáveis, então a aplicação não altera histórico.
- O relatório e o `SyncChange` preservam rastreabilidade.

### 4.3 Fluxo manual preservado

`sync_from_file(..., apply_all=False)` continua com o comportamento atual: personagens novas são
aplicadas; alterações em existentes ficam pendentes. A UI de CSV existente não muda.

## 5. Imagens

### 5.1 Decisão

Baixar automaticamente durante a execução, validar e normalizar com o pipeline existente.

Pipeline:

```text
URL remota
  → limite de bytes/timeout
  → Pillow verify/load
  → limite de pixels
  → normalização WebP 256×256
  → SHA-256
  → media/characters/<stable_id>/<sha256>.webp
  → ImageAsset (is_current, source, source_url, license_note)
```

### 5.2 Regras preservadas

- Um asset corrente por personagem.
- Imagem anterior vira histórica; arquivo não é apagado.
- Checksum igual reutiliza o arquivo existente.
- `license_note` obrigatório para fonte externa.
- Imagem inválida não impede as demais.

### 5.3 Escopos

- `all`: baixa todas as personagens do catálogo.
- `missing`: apenas personagens sem `ImageAsset` corrente com `status=valid`.

O escopo `missing` é o padrão para reimportações e reduz requisições.

## 6. Cliente HTTP

### 6.1 Decisão

Usar `urllib` da biblioteca padrão, encapsulado em `apps/catalog/services/sources/http.py`.

Motivos:

- nenhuma dependência nova;
- o script atual já usa `urllib` com retries;
- superfície pequena e controlada.

### 6.2 Regras

- HTTPS obrigatório.
- Allowlist por conector.
- User-Agent identificável.
- Timeout de conexão/leitura.
- Limite de bytes por resposta.
- Retry com backoff para timeout, 429 e 5xx.
- Redirecionamentos limitados e validação do host final.
- Bloqueio de IPs privados, loopback, link-local e multicast.
- Cache em memória por execução para evitar requisições repetidas.

## 7. Modelo de dados

### 7.1 `ImportJob`

Fila e histórico da execução. Ver `data-model.md` §3.

### 7.2 `CatalogSource`

Ganha `adapter` e `options`. O `adapter` liga a fonte ao conector registrado em código.

### 7.3 `SyncRun`

Ganha `origin` (`manual`/`external`) para distinguir a origem no histórico.

## 8. Segurança

- Sem URL informada pelo usuário.
- Allowlist fixa por conector.
- Conteúdo externo tratado como não confiável.
- Imagens validadas e normalizadas antes de gravar.
- Caminho derivado de `stable_id` validado.
- Rotas administrativas com CSRF e `admin_required`.
- Licença exibida e registrada.
- Logs sem credenciais, cookies ou escolhas de cédula.

## 9. Operação

- Novo serviço `import-worker` no compose.
- Compartilha `media_data` com `web`.
- Sem cron obrigatório; worker ocioso quando não há jobs.
- Kill switch `EXTERNAL_IMPORT_ENABLED`.
- Documentação em `docs/operations.md`.
- Backups já cobrem banco e mídia.

## 10. Riscos residuais

| Risco | Mitigação |
|---|---|
| GameTora bloquear o agente | Allowlist, UA, limite de requisições, mensagem clara e atualização do conector |
| Mudança de schema oficial | Fixtures e contract tests |
| Fonte retornar dados ambíguos | Relatório de conflitos; aplicação atômica falha sem gravar |
| Imagem maliciosa | Limite de bytes/pixels, Pillow, formatos permitidos, normalização |
| Worker interrompido | Heartbeat, stale recovery e retry idempotente |
| Uso indevido de imagens | Licença obrigatória e revisão manual |
| Catálogo crescer muito | Progresso, concorrência limitada e timeout |

## 11. Referências internas

- `scripts/fetch_global_assets.py` — implementação atual da coleta oficial + GameTora.
- `apps/catalog/services/importers.py` — contrato de parsing do catálogo.
- `apps/catalog/services/sync.py` — aplicação, histórico e aprovação.
- `apps/catalog/services/images.py` — validação, normalização e importação.
- `apps/voting/services/scheduler.py` — padrão de worker com advisory lock.
- `compose.yaml` — serviço `scheduler` e volumes.
- `specs/001-character-ban-voting/research.md` — investigação original das fontes.
