# Implementation Plan: Uma Voting — Votações de Banimento de Personagens

**Branch**: `001-character-ban-voting` | **Date**: 2026-11-07 | **Spec**:
`specs/001-character-ban-voting/spec.md`

**Input**: Feature specification from `specs/001-character-ban-voting/spec.md` and the
technical direction approved for the MVP.

## Summary

Construir um monólito Django server-rendered para votações de banimento em uma comunidade
fechada. O sistema cobre autenticação de administradores e participantes, gestão de
participantes, catálogo canônico com versões e aptidões, acervo local de imagens,
votações com snapshots imutáveis, cédulas definitivas, resultados agregados com posições
densas e agendamento automático sem navegador.

A direção tecnológica inicial é confirmada com ajustes: Django 5.2 LTS, Python 3.14,
PostgreSQL 18, HTMX 2.0, Bootstrap 5.3, Gunicorn e Caddy, tudo em Docker Compose. O
catálogo é sincronizado por um motor agnóstico de fonte, com importação de arquivo como
caminho operacional do MVP; scraping do GameTora fica condicionado a autorização. Imagens
são locais, content-addressed e preservadas por snapshots.

As regras críticas ficam em serviços de domínio, transações com locks de linha e um
conjunto pequeno de constraints/triggers PostgreSQL. A privacidade das cédulas é garantida
por separação de serviços, ausência de acesso administrativo às escolhas e testes
automatizados.

## Technical Context

**Language/Version**: Python 3.14.x (3.14.10 na pesquisa)

**Primary Dependencies**: Django 5.2 LTS (5.2.18), Gunicorn 23.x, psycopg 3.x, Pillow,
django-environ, uv; HTMX 2.0.11, Bootstrap 5.3.8, Caddy 2.x; pytest 9.x, pytest-django
4.14, factory_boy, freezegun, Ruff.

**Storage**: PostgreSQL 18.6 (dados, sessões e cache de throttle); sistema de arquivos
local para `media/characters/` (volume Docker); arquivos estáticos coletados em
`staticfiles/`.

**Testing**: pytest + pytest-django em PostgreSQL real; testes unitários, integração,
concorrência e tempo; Playwright opcional para E2E dos fluxos críticos.

**Target Platform**: Linux containers via Docker Compose; navegadores modernos
(Chrome/Edge/Firefox/Safari, duas últimas versões); sem suporte a IE.

**Project Type**: Aplicação web monolítica server-rendered (Django Templates + HTMX).

**Performance Goals**:
- busca/filtros de personagens < 1 s para 500 personagens;
- páginas administrativas < 2 s em condições normais;
- 100 participantes ativos, 5 votações simultâneas e 500 personagens;
- transições automáticas dentro de 1 minuto do horário configurado.

**Constraints**:
- interface em PT-BR, responsiva e acessível (WCAG 2.2 AA como referência);
- fuso `America/Sao_Paulo`, timestamps armazenados em UTC;
- imagens locais, sem dependência externa em runtime;
- sem frontend separado, microsserviços, Redis, Celery ou fila;
- privacidade das cédulas e integridade histórica não negociáveis;
- uma única instância/host no MVP.

**Scale/Scope**: ~100 participantes ativos, até 500 personagens canônicas, até 5 votações
simultâneas, 3 escolhas por padrão, ~10 telas de participante e ~12 telas administrativas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Status | Evidência no plano |
|---|---|---|
| I. Simplicidade Funcional | PASS | Monólito Django; sem SPA, microsserviços, fila ou Redis. Caddy e scheduler são as únicas peças adicionais, justificadas abaixo. |
| II. Integridade das Votações | PASS (emenda 2.0.0) | Serviços transacionais, `SELECT FOR UPDATE`/`FOR SHARE`, unique constraints, triggers de imutabilidade e contagem, snapshots, agendador idempotente. Exclusão administrativa enquanto aberta é exceção constitucional explícita. |
| III. Privacidade das Cédulas | PASS (emenda 2.0.0) | Serviços administrativos não importam `BallotChoice`; cédula do admin no modo participante acessível somente a ele; exclusão por participante; logs sem escolhas; testes de privacidade. Risco residual de inferência por agregados explicitamente aceito, com mitigação. |
| IV. Catálogo e Imagens | PASS | Identidade canônica estável, versões consolidadas, imagens locais content-addressed, placeholder, snapshots imutáveis. |
| V. Segurança Proporcional | PASS (emenda 2.0.0) | Admin com senha; participante por username como baixa garantia, com limitação documentada na interface; username admin rejeitado no fluxo de participante; CSRF, sessão, HTTPS, throttle e autorização server-side. |
| VI. Experiência Consistente | PASS | Design system integral, PT-BR, responsivo, acessibilidade e estados claros. |
| VII. Manutenibilidade | PASS | Apps Django com serviços separados, testes dos fluxos críticos, documentação de decisões, mídia independente. |
| Escopo Controlado | PASS | Somente o MVP aprovado; sem modalidades futuras, notificações ou APIs públicas. |

**Notas de governança (emenda constitucional 2.0.0 aprovada)**:

- **Integridade da cédula**: a emenda 2.0.0 autoriza a exclusão administrativa enquanto a
  votação está aberta (FR-071/FR-073), sem leitura das escolhas e com novo envio pelo participante.
  A exclusão após o encerramento continua proibida.
- **Autenticação de participante**: a emenda 2.0.0 separa os níveis de assurance. Admin exige
  senha; participante usa username-only como baixa garantia em comunidade fechada, com aviso na
  interface e na documentação.
- **Inferência por agregação**: a emenda 2.0.0 aceita explicitamente o risco residual de
  comparação manual de agregados, com mitigação: a UI não exibe diferenças, os logs não registram
  escolhas e a exclusão ocorre em fluxo dedicado.


**Post-design re-check**: PASS com a emenda 2.0.0. Nenhuma violação não documentada. As escolhas
de complexidade abaixo são justificadas e não contrariam a constituição.

## Project Structure

### Documentation (this feature)

```text
specs/001-character-ban-voting/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── http-routes.md
│   ├── domain-services.md
│   ├── management-commands.md
│   └── import-formats.md
└── tasks.md              # gerado por /speckit.tasks, não por este comando
```

### Source Code (repository root)

```text
.
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── compose.yaml
├── compose.override.yaml          # desenvolvimento
├── compose.prod.yaml              # produção
├── Caddyfile
├── .env.example
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   ├── prod.py
│   │   └── test.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/
│   │   ├── models.py
│   │   ├── managers.py
│   │   ├── forms.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services/
│   │   │   ├── auth.py
│   │   │   ├── throttle.py
│   │   │   └── participants.py
│   │   ├── management/commands/create_admin.py
│   │   ├── migrations/
│   │   └── tests/
│   ├── catalog/
│   │   ├── models.py
│   │   ├── forms.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services/
│   │   │   ├── sync.py
│   │   │   ├── importers.py
│   │   │   ├── images.py
│   │   │   └── queries.py
│   │   ├── management/commands/
│   │   │   ├── import_catalog.py
│   │   │   ├── sync_catalog.py
│   │   │   ├── approve_catalog_change.py
│   │   │   ├── reject_catalog_change.py
│   │   │   ├── import_images.py
│   │   │   └── validate_images.py
│   │   ├── migrations/
│   │   └── tests/
│   ├── voting/
│   │   ├── models.py
│   │   ├── forms.py
│   │   ├── urls.py
│   │   ├── views/
│   │   │   ├── participant.py
│   │   │   └── admin.py
│   │   ├── services/
│   │   │   ├── lifecycle.py
│   │   │   ├── snapshots.py
│   │   │   ├── ballots.py
│   │   │   ├── filters.py
│   │   │   ├── results.py
│   │   │   └── scheduler.py
│   │   ├── management/commands/
│   │   │   ├── process_voting_transitions.py
│   │   │   └── run_scheduler.py
│   │   ├── migrations/
│   │   └── tests/
│   └── core/
│       ├── views.py               # health
│       ├── middleware.py          # request id, modo admin/participante
│       ├── context_processors.py
│       ├── templatetags/
│       └── tests/
├── templates/
│   ├── base.html
│   ├── components/
│   ├── participant/
│   ├── admin/
│   └── errors/
├── static/
│   ├── css/
│   │   ├── tokens.css
│   │   ├── base.css
│   │   ├── components.css
│   │   └── pages.css
│   ├── js/app.js
│   ├── vendor/
│   │   ├── bootstrap/
│   │   ├── htmx/
│   │   └── lucide/
│   ├── fonts/inter/
│   └── img/character-placeholder.webp
├── media/                         # runtime; volume Docker; não versionado
│   └── characters/
├── scripts/
│   ├── release.sh
│   ├── backup.sh
│   └── restore.sh
├── tests/
│   ├── integration/
│   ├── concurrency/
│   └── e2e/
├── docs/
│   ├── design-system.md
│   ├── operations.md
│   ├── governance-notes.md
│   └── security-review.md
└── specs/001-character-ban-voting/
```

**Structure Decision**: um único projeto Django com três apps de domínio
(`accounts`, `catalog`, `voting`) e um app de infraestrutura (`core`). Regras de negócio
ficam em `services/`; views apenas orquestram. Templates e estáticos são compartilhados no
nível do projeto. Imagens gerenciadas em `media/characters/` (volume), separadas de
`static/` (CSS/JS/fontes/placeholder). Não há frontend separado.

## Complexity Tracking

Nenhuma violação não registrada. A emenda constitucional 2.0.0 está documentada acima e em
`docs/governance-notes.md`; as adições abaixo são justificadas por requisitos explícitos e têm
alternativa mais simples considerada.

| Adição | Por que é necessária | Alternativa simples rejeitada |
|---|---|---|
| Container `scheduler` | Transições automáticas sem navegador e com recuperação após indisponibilidade | Cron do host é viável, mas menos portátil no Compose; APScheduler no web duplicaria execuções |
| Triggers PostgreSQL | Integridade de snapshots, cédulas e transições não pode depender só da aplicação | Validação apenas no serviço não protege SQL direto nem corridas |
| Caddy | HTTPS automático, static/media e cabeçalhos de segurança com pouca configuração | Django servindo mídia/estáticos em produção não é adequado; Nginx + Certbot exige mais configuração |
| `media/characters/` content-addressed | Imutabilidade de imagens históricas sem copiar arquivos por votação | `static/` embutido exigiria rebuild para trocar imagem; sobrescrever quebraria snapshots |
| Throttle com `DatabaseCache` | Rate limiting compartilhado entre workers sem Redis | Cache em memória não é compartilhado entre processos |
| Rejeitar login de participante para usernames admin | Evita impersonação do voto do administrador | Permitir username-only para admin quebraria a separação de autenticação |
| Admin customizado sem Django Admin | Evita exposição acidental de `BallotChoice` | Registrar modelos no Django Admin criaria caminho de leitura indevido |

## Implementation Phases

Cada fase é um incremento verificável; nenhuma funcionalidade fora do MVP é iniciada.

### Fase 0 — Fundação

- Estrutura Django, `pyproject.toml`, `uv.lock`, Dockerfile, Compose base/dev/prod.
- Settings separados (`base`, `dev`, `prod`, `test`), `.env.example`, timezone.
- Templates base, tokens CSS do design system, Bootstrap/HTMX/Inter/Lucide vendorizados.
- Healthcheck, logging, CI (lint, testes, `check --deploy`, build).
- **Critério de saída**: aplicação sobe, health responde, CI verde, layout base responsivo.

### Fase 1 — Contas e autenticação

- `accounts.User`, manager, unicidade case-insensitive.
- Login admin (senha), login participante (username), rejeição de admin no fluxo
  participante, logout, sessão, throttle.
- Alternância admin ↔ participante.
- Testes de auth/autorização/sessão/CSRF.
- **Critério de saída**: cenários 5.1 do quickstart passam.

### Fase 2 — Participantes

- CRUD, pesquisa, desativação.
- A área de participantes gerencia contas não administrativas; administradores são
  provisionados por comando e aparecem apenas na elegibilidade/participação.
- Importação CSV atômica com relatório por linha.
- Inclusão padrão em novas votações; congelamento em rascunho/agendada.
- **Critério de saída**: cenário 5.2 passa; importação inválida não grava nada.

### Fase 3 — Catálogo

- Modelos de personagem, versão, aptidão, fonte, sync e mudanças pendentes.
- Importador CSV/JSON, validação, prévia, auto-add de novas personagens, aprovação.
- Data de corte e consultas de elegibilidade/consolidação.
- **Critério de saída**: cenário 5.3 passa; snapshots antigos não mudam.

### Fase 4 — Imagens

- `ImageAsset`, asset corrente, placeholder.
- Comandos `import_images` e `validate_images`.
- Administração de estado de imagens.
- Testes de arquivo ausente/inválido, duplicidade, associação e preservação.
- **Critério de saída**: cenário 5.9 passa; nenhuma dependência externa em runtime.

### Fase 5 — Ciclo de vida e snapshots

- `Voting`, `VotingEligibility`, snapshots, transições.
- Constraints/triggers PostgreSQL.
- Abertura, encerramento, cancelamento, scheduler e recuperação.
- Testes de concorrência e tempo.
- **Critério de saída**: cenários 5.7 e 5.8 (parte de estado) passam.

### Fase 6 — Cédulas

- Home do participante com votações elegíveis e estado vazio.
- Seleção com busca/filtros HTMX, contador, revisão, confirmação.
- Envio transacional, validação de quantidade/duplicidade/snapshot.
- Consulta da própria cédula; exclusão administrativa sem leitura de escolhas.
- Testes de concorrência, duplo envio, envio após encerramento.
- **Critério de saída**: cenários 5.1 (home), 5.4, 5.5 e 5.6 passam.

### Fase 7 — Resultados e privacidade

- Agregação, participação, dense rank, resultados de participante/admin.
- Testes de privacidade e ranking com empates.
- **Critério de saída**: cenário 5.8 passa; auditoria de privacidade sem achados.

### Fase 8 — Administração e histórico

- Dashboard, listas, atalhos, histórico administrativo e histórico de participante (a home já
  existe desde a Fase 6).
- Ajustes de UX, responsividade e acessibilidade em todas as telas.
- **Critério de saída**: checklist visual do design system aplicado.

### Fase 9 — Endurecimento e operação

- HTTPS/CSP/headers, backups, restauração testada, runbook, health/monitoramento.
- E2E opcional; revisão de dependências; `check --deploy`.
- **Critério de saída**: deploy de produção reproduzível; restore validado em ambiente
  limpo.

## Critical Flows and Transaction Boundaries

### Abertura de votação

```text
BEGIN
  SELECT voting FOR UPDATE
  validar status, elegíveis >= 1, personagens >= choices_count
  criar snapshots de personagens/versões/aptidões
  UPDATE voting SET status='open', opened_at, frozen_at
COMMIT
```

- Falha manual: erro de domínio, sem alteração.
- Falha automática: `status='cancelled'`, `cancelled_at`, sem cédulas.

### Envio de cédula

```text
BEGIN
  SELECT voting FOR SHARE
  validar status='open' e, se close_mode='automatic', now() < closes_at
  validar quantidade exata, IDs distintos, todos no snapshot
  INSERT ballot
  INSERT ballot_choice x N
COMMIT  -- constraint trigger valida contagem; unique valida duplicidade
```

- Conflito de duplicidade: 409 "já votou".
- Encerramento concorrente: `FOR UPDATE` do encerramento espera os envios `FOR SHARE`.
- Trigger de horário é a última barreira.

### Exclusão administrativa

```text
BEGIN
  SELECT voting FOR UPDATE
  validar status='open' e, se close_mode='automatic', now() < closes_at
  DELETE ballot WHERE voting_id AND participant_id
COMMIT
```

- Não carrega choices; não notifica; não audita autoria; não exibe diferenças de agregados
  antes/depois da exclusão. A exceção é constitucional desde a emenda 2.0.0.

### Encerramento

```text
BEGIN
  SELECT voting FOR UPDATE
  validar status='open'
  UPDATE voting SET status='closed', closed_at
COMMIT
```

- Cédulas permanecem; exclusões individuais passam a ser bloqueadas.

### Cancelamento

```text
BEGIN
  SELECT voting FOR UPDATE
  UPDATE voting SET status='cancelled', cancelled_at
  DELETE ballots (trigger permite no estado cancelled)
COMMIT
```

- Funciona em rascunho, agendada, aberta e encerrada.
- Histórico administrativo preservado; participantes não veem.

### Scheduler

```text
pg_try_advisory_lock('uma_voting_scheduler')
para cada votação devida (FOR UPDATE SKIP LOCKED):
  abrir, encerrar ou cancelar conforme regra e horário
  commit individual
liberar lock
```

- Recuperação: abre se ainda há janela; cancela se a janela inteira passou; encerra
  votação aberta com encerramento perdido.
- Idempotente e independente de navegador.

## Security Plan

- **Admin**: username + senha, hash do Django, `is_admin=True`, throttle.
- **Participante**: username-only como baixa garantia; limitação documentada na interface e na
  documentação; username de admin rejeitado no fluxo de participante; sem cadastro público.
- **Privacidade**: exclusão administrativa sem leitura de escolhas; sem diff de agregados na UI;
  logs sem escolhas; teste de privacidade dedicado. O admin que vota no modo participante só
  acessa a própria cédula pela rota de participante; nenhuma visão administrativa expõe escolhas
  de outros participantes nem as do próprio admin.
- **Sessão**: backend de banco, expira ao fechar o navegador, logout POST, rotação de
  sessão no login, cookies `HttpOnly`/`Secure`/`SameSite=Lax`.
- **CSRF**: middleware padrão; todos os POSTs; HTMX envia `X-CSRFToken`.
- **Autorização**: mixins/decorators server-side; elegibilidade por votação; cédula
  própria filtrada por `request.user`, inclusive para administrador no modo participante.
- **HTTPS**: Caddy com TLS automático; `SECURE_SSL_REDIRECT`, HSTS, cookies seguros,
  `SECURE_PROXY_SSL_HEADER`.
- **Headers**: CSP `default-src 'self'; script-src 'self'; style-src 'self'
  'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';
  frame-ancestors 'none'; base-uri 'self'; form-action 'self'`. O `style-src` inline é
  permitido apenas para compatibilidade com componentes Bootstrap; scripts inline são
  proibidos. Validar as diretivas mínimas na implementação.
- **Abuso**: throttle de login com `DatabaseCache`; limites de upload; timeouts do proxy;
  validação de tamanho/tipo de arquivo.
- **Entrada**: Django Forms/ORM; validação server-side; sem SQL interpolado; uploads com
  Pillow e limites.
- **XSS**: autoescape de templates; evitar `safe`; CSP como defesa adicional.
- **Logs**: sem senhas, escolhas ou corpos de confirmação; request ID; transições e
  sincronizações registradas.
- **Segredos**: `.env` não versionado; `SECRET_KEY` forte; rotação documentada.
- **Dependências**: versões pinadas; `pip-audit`/revisão mensal; atualização de patches.

## Catalog and Images Strategy

- Motor de sincronização agnóstico de fonte com adaptador de arquivo no MVP.
- GameTora: referência principal de curadoria; sem scraping automático até autorização e
  verificação de viabilidade. A importação de arquivo é o caminho operacional do MVP (FR-092).
- uma.guide: referência de conferência manual.
- umapyoi.net: candidato secundário, com crédito e verificação de cobertura/direitos.
- Novas personagens elegíveis: aplicadas automaticamente; alterações existentes: pendentes
  de aprovação; histórico em `SyncRun`/`SyncChange`.
- Snapshot na abertura: personagens, versões e aptidões; data de corte aplicada.
- Imagens: `media/characters/<stable-id>/<sha256>.webp`; WebP 256 × 256; `ImageOps.pad`
  sem distorção; placeholder; comandos de importação/validação; assets antigos preservados.
- Direitos: origem/licença registradas; disponibilidade pública não é autorização;
  revisão manual obrigatória antes de `--apply`; sem gate técnico no MVP; deployment privado não
  elimina a necessidade de permissão.
- Backup: banco + `media/`; restauração testada.

## Testing Strategy

- **Unitários**: serviços de lifecycle, ballots, filters, results, sync, images; ranking;
  validação de CSV; state machine.
- **Integração**: rotas, auth, autorização, CSRF, sessão, fluxos de voto, exclusão,
  cancelamento, resultados, snapshots, scheduler, imagens.
- **Concorrência**: envio duplo, envio vs encerramento, exclusão vs encerramento, abertura
  vs cancelamento, scheduler concorrente.
- **Tempo**: `freezegun` para abertura/encerramento/recuperação; `closes_at` e timezone.
- **Privacidade**: nenhuma resposta admin contém escolhas; logs não contêm escolhas;
  participante só vê a própria cédula; exclusão administrativa sem diff de agregados.
- **Exclusão administrativa**: teste dedicado de FR-071–FR-075 (sem escolhas, sem
  notificação/auditoria, re-voto e bloqueio após encerramento).
- **Reprodutibilidade**: recalcular resultados a partir de snapshots/cédulas após mutação de
  catálogo/imagens e comparar com o original.
- **Medições manuais**: SC-001/SC-002 no quickstart; SC-010 com 500 personagens.
- **Banco**: PostgreSQL real; triggers e constraints testados; SQLite proibido.
- **E2E opcional**: Playwright para login, voto, resultados, mobile 360 px e teclado.
- **CI**: lint, `makemigrations --check`, testes, `check --deploy`, build Docker.

## Deployment and Operations

- **Compose**: `db`, `release`, `web`, `scheduler`, `caddy`.
- **Release**: `migrate`, `collectstatic`, `createcachetable` uma vez, antes de web/scheduler
  (`service_completed_successfully`).
- **Web**: Gunicorn WSGI, sem código montado em produção; healthcheck `/health/`.
- **Scheduler**: loop de 60 s; logs; reinício automático.
- **Caddy**: TLS automático, `/static/*` e `/media/*`, CSP/headers, compressão.
- **Volumes**: `postgres_data`, `media_data`, `static_data`, `caddy_data`, `caddy_config`.
- **Migrations**: etapa de release; nunca no entrypoint de cada worker.
- **Sincronização periódica**: cron/systemd diário às 03:00 chamando `sync_catalog`; o
  `run_scheduler` é dedicado a transições de votação, não a catálogo.
- **Backups**: `pg_dump -Fc` + tar de `media/`; 30 diários + 12 mensais; armazenamento
  fora do host; teste de restore trimestral.
- **Logs**: stdout, rotação Docker; request ID; sem dados sensíveis.
- **Medições manuais**: SC-001/SC-002 no quickstart; SC-010 com 500 personagens; registrar em
  `docs/operations.md`.
- **Licenças de imagem**: revisão manual registrada antes de `--apply`; sem gate técnico no MVP.
- **Monitoramento básico**: healthcheck, uptime, disco, último backup, erros 5xx.
- **Runbook**: `docs/operations.md` com deploy, rollback, restore, rotação de segredos e
  resposta a incidentes.

## Risks and Open Decisions

| Risco/decisão | Impacto | Mitigação/próximo passo |
|---|---|---|
| GameTora sem API/termos claros | Catálogo | Importação manual; contatar mantenedores; adaptador futuro |
| Direitos de imagens | Jurídico/reputacional | Acervo local documentado; revisão manual obrigatória; sem gate técnico no MVP (risco aceito); placeholder |
| Auth por username | Segurança | Limitação documentada na interface; sem cadastro público; throttle; admin exige senha (emenda 2.0.0) |
| Inferência por agregação + exclusão | Privacidade | Risco residual aceito na emenda 2.0.0; sem diff na UI; logs sem escolhas; teste de privacidade |
| Medições SC-001/SC-002/SC-010 | Qualidade | Medição manual registrada no quickstart/operations; sem automação no MVP |
| Revisão manual de cadastro/username | Qualidade | Checklist em `docs/security-review.md`; sem teste dedicado (risco baixo aceito) |
| Scheduler em container único | Disponibilidade | Healthcheck, logs, reinício, lock e idempotência |
| Triggers PostgreSQL | Manutenção | Migrations explícitas, testes de invariantes, documentação |
| Curadoria manual do catálogo | Atualização | Prévia, validação, aprovação e histórico |
| Imagens ausentes/inválidas | UX | Placeholder e relatório administrativo |
| Single host | Disponibilidade | Backups, restore testado, monitoramento; fora do MVP HA |
| Frequência de sincronização | Operação | Default diário 03:00 + manual; ajustável |
| Provedor/domínio | Deploy | Definir antes da Fase 9; Caddy usa `DOMAIN` |
| Sem notificações | UX | Fora do escopo aprovado |
| Timezone/DST | Datas | UTC no banco; `America/Sao_Paulo` na apresentação |

## Generated Artifacts

- `research.md` — decisões, versões, fontes e alternativas.
- `data-model.md` — entidades, constraints, triggers, índices e transições.
- `contracts/http-routes.md` — rotas e autorização.
- `contracts/domain-services.md` — serviços e invariantes.
- `contracts/management-commands.md` — comandos operacionais.
- `contracts/import-formats.md` — CSV/manifestos e validação.
- `quickstart.md` — cenários de validação ponta a ponta.
- `docs/governance-notes.md` — registro da emenda 2.0.0 e riscos aceitos.
- `docs/security-review.md` — checklist de segurança e privacidade.
- `docs/operations.md` — deploy, backups, scheduler, medições e licenças.

**Next command**: `/speckit.tasks` para decompor em tarefas executáveis.
