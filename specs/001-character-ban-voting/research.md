# Research: Uma Voting — Decisões Técnicas e Investigação de Fontes

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Status**: Phase 0 complete
**Scope**: resolver as decisões técnicas e as dependências externas antes do desenho detalhado.

## 1. Resumo executivo

A direção inicial (Django + Django Templates + HTMX + Bootstrap 5 + PostgreSQL + Docker
Compose) é viável e adequada ao MVP. O plano confirma a direção com quatro ajustes:

1. **Django 5.2 LTS** em vez da versão mais recente (6.1), para reduzir risco de atualização e
   manter compatibilidade oficial com o ferramental de testes.
2. **HTMX 2.0.x** em vez do recém-lançado HTMX 4.0, preservando o ecossistema estável e a
   documentação consolidada; a migração para 4.x fica para depois do MVP.
3. **Caddy** como reverse proxy de produção, em vez de Nginx + Certbot, para HTTPS automático,
   arquivos estáticos/mídia e cabeçalhos de segurança com pouca configuração.
4. **Importação de arquivo como caminho operacional principal do catálogo no MVP**, porque não foi
   encontrada API pública nem autorização explícita de uso no GameTora. A automação de scraping
   fica condicionada a permissão e a uma verificação de viabilidade; a arquitetura já nasce com
   adaptadores de fonte para permitir essa evolução.

Não há frontend separado, microsserviços, fila ou Redis. O agendador é um comando de gerenciamento
executado por um container dedicado, com lock de banco para idempotência.

## 2. Stack e versões

### 2.1 Decisão

| Componente | Versão alvo | Papel |
|---|---|---|
| Python | 3.14.x (3.14.10 na pesquisa) | Runtime |
| Django | 5.2 LTS (5.2.18 na pesquisa) | Framework web, ORM, auth, templates |
| PostgreSQL | 18.6 | Banco relacional, constraints, triggers, locks |
| HTMX | 2.0.11 | Interações parciais server-rendered |
| Bootstrap | 5.3.8 | Grid e componentes base |
| Gunicorn | linha 23.x, versão exata fixada no lock | Servidor WSGI |
| Caddy | 2.x | HTTPS, reverse proxy, static/media |
| uv | versão estável fixada no lock | Dependências e lockfile |
| pytest + pytest-django | pytest 9.x; pytest-django 4.14 | Testes |
| Ruff | versão estável fixada no lock | Lint e formatação |

### 2.2 Racional

- **Django 5.2 LTS**: suporte de segurança até abril de 2028; o MVP não exige recursos exclusivos
  do Django 6.x. A compatibilidade oficial do pytest-django 4.14 cobre Django 5.2 e 6.0; isso
  reduz atrito de tooling. O plano prevê upgrade para Django 6.2 LTS em 2027.
- **Python 3.14**: suportado pelo Django 5.2.18; evita depender de suporte recém-adicionado ao
  Python 3.15.
- **PostgreSQL 18.6**: versão estável atual; PostgreSQL 19 ainda estava em RC na data da pesquisa,
  portanto não deve ser usado em produção.
- **HTMX 2.0.11**: o HTMX 4.0.1 é estável, mas foi lançado em agosto de 2026 com mudanças
  profundas (fetch, herança explícita, eventos renomeados). A linha 2.x continua suportada. Para o
  MVP, a linha 2.x oferece menor risco e mais exemplos com Django.
- **Bootstrap 5.3.8**: última versão estável da linha 5; o Bootstrap 6 ainda estava em alpha.
- **Caddy**: HTTPS automático e configuração curta; uma única peça a mais no Compose, justificada
  por TLS, static/media e cabeçalhos. Nginx + Certbot seria a alternativa se o ambiente já
  possuísse Nginx consolidado.
- **Sem Node/npm no build**: Bootstrap, HTMX, Inter e ícones são arquivos estáticos versionados no
  repositório. Isso elimina uma toolchain de frontend e mantém o deploy simples.

### 2.3 Alternativas consideradas

- **Django 6.1.2**: mais recente, mas suporte até dezembro de 2027 e compatibilidade de testes
  menos consolidada; exigiria upgrade em pouco tempo.
- **FastAPI/Flask + frontend separado**: rejeitado por contrariar a simplicidade e a direção
  server-rendered.
- **HTMX 4.0.1**: rejeitado para o MVP por maturidade e mudanças incompatíveis; pode ser adotado
  após o MVP.
- **Bootstrap 6 alpha**: rejeitado por não ser estável.
- **Redis/Celery/django-q2**: rejeitados por adicionarem serviços e complexidade operacional sem
  necessidade para uma comunidade pequena.
- **Node/Vite**: rejeitado; CSS próprio com tokens e arquivos vendorizados bastam.

## 3. Autenticação e sessões

### 3.1 Decisão

- Um único modelo de usuário (`accounts.User`) com `is_admin`, `is_active` e username único
  case-insensitive.
- Administradores autenticam com username + senha (backend padrão do Django).
- Participantes autenticam somente por username, por meio de uma view dedicada que localiza um
  usuário **ativo e não administrador** e chama `login()` diretamente.
- **Username de administrador é rejeitado no login de participante**; o administrador deve usar a
  tela administrativa com senha e, depois, alternar para a experiência de participante.
- Sessões em banco (`django.contrib.sessions.backends.db`), com
  `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`, logout por POST e limpeza periódica de sessões expiradas.
- CSRF em todos os POSTs; cookies `HttpOnly`, `Secure` em produção, `SameSite=Lax`.
- Throttle de tentativas de login com `DatabaseCache` (compartilhado entre workers), por IP e
  username, sem dependência de Redis.

### 3.2 Racional

A limitação do username-only é consciente e documentada. Rejeitar usernames administrativos no
fluxo de participante evita que alguém que conheça o username de um administrador assuma a
identidade participante dele. O administrador já autenticado pode alternar para a experiência de
participante sem novo login.

### 3.3 Alternativas consideradas

- **Permitir que administradores entrem só com username no fluxo de participante**: rejeitado por
  permitir impersonação do voto do administrador.
- **Dois modelos separados (Admin e Participante)**: rejeitado por duplicar identidade e dificultar
  o requisito "administrador também é participante".
- **Cookies assinados sem sessão em banco**: rejeitado porque dificulta revogação e logout
  consistente.
- **django-axes**: rejeitado por adicionar tabelas e configuração; o throttle simples com
  `DatabaseCache` cobre o contexto.

## 4. Persistência, constraints e concorrência

### 4.1 Decisão

- PostgreSQL é obrigatório também em testes; SQLite não é usado, pois os invariantes críticos
  dependem de triggers, `FOR UPDATE`/`FOR SHARE` e índices funcionais.
- Username case-insensitive: `UniqueConstraint(Lower("username"))`, que gera índice único
  funcional. A exibição preserva a grafia cadastrada.
- Integridade crítica no banco:
  - uma cédula por participante/votação (`UNIQUE`);
  - uma escolha por personagem na cédula (`UNIQUE`);
  - snapshot de personagem pertence à votação da cédula (trigger);
  - quantidade exata de escolhas (constraint trigger diferido no commit);
  - cédula só é inserida com votação aberta e antes do encerramento (trigger);
  - cédula/choices não podem ser alterados; exclusão individual só com votação aberta, e exclusão
    em massa apenas no cancelamento (trigger);
  - snapshots e elegibilidade imutáveis após o congelamento (triggers);
  - transições de estado permitidas e configuração imutável após o rascunho (trigger);
  - uma imagem corrente por personagem (unique parcial).
- Concorrência:
  - envio de cédula: `SELECT ... FOR SHARE` na votação, permitindo envios concorrentes;
  - abertura, encerramento, cancelamento e exclusão administrativa: `SELECT ... FOR UPDATE`;
  - `UNIQUE (votação, participante)` como última barreira contra duplo envio;
  - o trigger de `closes_at` impede aceitar cédula depois do horário mesmo se o agendador atrasar.
- O agendador usa `pg_try_advisory_lock` para evitar execuções simultâneas e processa cada votação
  em transação própria, com operações idempotentes.

### 4.2 Racional

A constituição exige integridade garantida pelo banco. Os triggers são poucos e concentrados nos
invariantes que não podem depender apenas da aplicação. A combinação de locks de linha, unique
constraints e triggers cobre concorrência entre envio, exclusão, abertura e encerramento.

### 4.3 Alternativas consideradas

- **Somente validação na aplicação**: rejeitada; não protege contra caminhos alternativos nem
  contra corridas.
- **CITEXT**: viável, mas exige extensão e não é necessária; o índice funcional é suficiente.
- **Serializar todos os envios com `FOR UPDATE`**: funcionaria, mas reduz concorrência sem
  necessidade; `FOR SHARE` + unique é melhor.
- **Otimistic locking com versão**: mais código e tratamento de retry; locks de linha são mais
  simples para o volume previsto.
- **Triggers para todas as regras**: rejeitado por duplicar lógica e dificultar manutenção; apenas
  invariantes críticos vão para o banco.

## 5. Agendamento

### 5.1 Decisão

- Comando `process_voting_transitions` (execução única e idempotente) e comando
  `run_scheduler` (loop com intervalo de 60 s).
- Em Docker Compose, um serviço `scheduler` usa a mesma imagem do `web` e executa
  `python manage.py run_scheduler --interval 60`.
- Alternativa operacional: cron/systemd timer chamando `process_voting_transitions` a cada minuto.
- Lock de banco com `pg_try_advisory_lock`; cada votação é processada em transação própria.
- Regras de recuperação:
  - abertura automática perdida, com encerramento ainda no futuro → abre imediatamente;
  - janela inteira perdida → cancela automaticamente, sem cédulas;
  - votação já aberta com encerramento perdido → encerra imediatamente;
  - abertura automática sem elegíveis ou sem personagens suficientes → cancela automaticamente.
- `closes_at` só é obrigatório quando o encerramento é automático. Encerramento manual não depende
  do relógio; a data pode existir como referência, mas não dispara transição.

### 5.2 Racional

Não é necessário Celery/Redis para uma única instância com poucas votações. Um loop de 60 s atende
ao critério de 1 minuto. O lock e a idempotência tornam a operação segura mesmo com reinícios.

### 5.3 Alternativas consideradas

- **Celery + Redis**: rejeitado por adicionar broker, worker e complexidade de operação.
- **django-q2**: rejeitado pelo mesmo motivo; o volume não justifica.
- **Cron do host apenas**: viável, mas o Compose fica menos autossuficiente; o container scheduler
  é mais portátil.
- **APScheduler embutido no processo web**: rejeitado porque múltiplos workers duplicariam
  execuções e o processo web não é o lugar adequado.

## 6. Catálogo: investigação das fontes

### 6.1 GameTora

- As páginas públicas de personagem exibem nome, versões, data de lançamento Global (quando
  lançada), aptidões de superfície/distância/estratégia e indicam quando a personagem ainda não
  foi lançada no Global. Exemplo consultado: páginas de Tokai Teio, Agnes Tachyon e personagens
  ainda não globais.
- Não foi encontrada documentação de API pública estável. O site se declara não afiliado e informa
  que os materiais de Umamusume são copyright da Cygames. Há CLA para contribuições e política de
  privacidade, mas não foi localizada uma autorização de scraping/redistribuição.
- **Decisão**: não automatizar scraping no MVP sem autorização. O GameTora permanece a referência
  de curadoria; o caminho operacional é importação de arquivo revisado.

### 6.2 uma.guide

- Lista personagens e permite alternar Global/JP; é um recurso fan-made, não afiliado à Cygames,
  com aviso de marcas e conteúdo da Cygames. Não foi encontrada API pública documentada.
- **Decisão**: usar como referência de conferência manual e possível origem de dados curados; não
  automatizar sem termos claros.

### 6.3 umapyoi.net

- Possui API pública documentada para personagens, imagens, outfits e outros dados, com limites de
  10 req/s, 500 req/min, 7.200 req/h e 172.800 req/dia, e pede crédito ao site.
- É orientada à versão japonesa e à franquia; não substitui a necessidade de datas de lançamento
  Global e critérios de corte do projeto.
- **Decisão**: candidata a fonte secundária de identidade/metadados e imagens, sujeita a crédito,
  verificação de cobertura Global e, principalmente, direitos sobre as imagens. Não é dependência
  do MVP.

### 6.4 Repositórios comunitários

- Há repositórios com dados e ferramentas (por exemplo, umamusumedb, UmamusumeExplorer,
  UmaViewer, UmaTools). Licenças de código (MIT/GPL etc.) não transferem automaticamente direitos
  sobre assets da Cygames. Vários projetos exigem instalação local do jogo e não redistribuem
  assets.
- **Decisão**: usar apenas como referência técnica/formatos; não presumir licença de imagens.

### 6.5 Estratégia adotada para o MVP

- Implementar um motor de sincronização **agnóstico de fonte**, com um adaptador de arquivo
  (CSV/JSON) como fonte operacional principal.
- O arquivo de catálogo é curado a partir do GameTora/uma.guide e revisado por administrador.
- Novas personagens canônicas elegíveis (lançadas no Global) podem ser aplicadas automaticamente;
  qualquer alteração em personagem existente (nome, datas, versões, aptidões) fica pendente de
  aprovação.
- Adaptadores GameTora/umapyoi.net podem ser adicionados depois, atrás da mesma interface, quando
  houver autorização/termos e validação de cobertura.
- A data de corte é aplicada na abertura; o snapshot preserva versões e aptidões daquele momento.

### 6.6 Riscos

- Dados do GameTora podem mudar de estrutura ou ficar indisponíveis.
- Curadoria manual tem custo operacional e risco de erro humano; mitigação: validação, prévia,
  aprovação e histórico.
- Cobertura de personagens Global pode não ser completa em fontes comunitárias.
- Direitos de imagem não são resolvidos pela disponibilidade pública.

## 7. Imagens: investigação e estratégia

### 7.1 Fontes candidatas

| Fonte | Cobertura | Estrutura | Automação | Licença/termos | Risco |
|---|---|---|---|---|---|
| GameTora | Personagens JP/Global, retratos e galeria | HTML; sem API pública encontrada | Baixa (scraping não autorizado) | Conteúdo Cygames; sem autorização de redistribuição localizada | Médio/alto |
| uma.guide | Personagens Global/JP | HTML; sem API pública encontrada | Baixa | Fan-made, não afiliado; conteúdo Cygames | Médio |
| umapyoi.net | Personagens, imagens, outfits (foco JP) | API pública documentada e rate limits | Média/alta | Pede crédito; imagens continuam Cygames | Médio |
| Repositórios GitHub | Variável | Assets/arquivos variados | Variável | Licença do código não cobre assets | Médio/alto |
| Acervo local curado | Controlado pelo projeto | Arquivos WebP + manifesto | Manual | Documentar origem e permissão | Baixo (se autorizado) |

### 7.2 Decisão

- **Fonte principal operacional**: acervo local curado, com manifesto de origem e status de
  validação. Não há download automático no MVP.
- **FR-092 alinhado**: o GameTora permanece a referência principal de curadoria; a importação de
  arquivo é o caminho operacional do MVP até autorização/viabilidade do GameTora.
- **Alternativa técnica**: importar candidatos do umapyoi.net ou de repositório comunitário apenas
  após verificar termos e direitos; a importação é sempre por manifesto e prévia.
- **Fallback**: placeholder local para imagem ausente/inválida; a personagem continua utilizável.
- **Não presumir** que uma imagem pública pode ser redistribuída. O projeto deve obter permissão
  ou manter o acervo restrito ao uso privado da comunidade, com registro da origem.
- **Revisão manual de licença**: antes de `import_images --apply`, o administrador MUST revisar e
  registrar a autorização no runbook. O MVP não aplica gate técnico de licença (decisão G5 C);
  a limitação fica documentada em `docs/operations.md`.
- Armazenamento em `media/characters/<stable-id>/<sha256>.webp`, com nomes content-addressed e
  imutáveis; o banco guarda o caminho relativo, checksum, dimensões, origem, licença e status.
- Imagens antigas nunca são sobrescritas; snapshots apontam para o asset exato.
- Conversão/padronização por comando de gerenciamento com Pillow: 256 × 256, WebP, `ImageOps.pad`
  (conter sem distorcer) ou imagem pré-enquadrada; qualidade configurável.
- Validação: existência, formato, integridade, dimensões, associação, órfãos, duplicidades por
  checksum, referências quebradas e personagens sem imagem.
- Backup do diretório `media/` junto com o banco; restauração testada.

### 7.3 Racional

Separar viabilidade técnica de autorização é obrigatório pela constituição. Um pipeline manual com
manifesto e validação é mais simples e seguro do que scraping não autorizado, e ainda permite
automação futura.

## 8. Ranking e privacidade

### 8.1 Ranking

- O exemplo aprovado `1º, 2º, 2º, 3º, 3º` é **dense rank**: posições consecutivas sem saltos.
- Implementar com `DENSE_RANK()` (ou cálculo em Python) sobre a contagem decrescente de votos.
- Personagens com zero votos não aparecem no resultado final (clarificação de 2026-11-07).
- Empates são exibidos integralmente; não há desempate por nome ou outro atributo.

### 8.2 Privacidade

- Nenhuma view, formulário ou consulta administrativa acessa `BallotChoice` individual.
- A exclusão administrativa de cédula é feita por votação + participante, sem carregar escolhas.
- Resultados usam agregação por personagem; participação usa `EXISTS` por elegível.
- Logs não registram escolhas nem o corpo do POST de confirmação.
- Testes de privacidade verificam que respostas administrativas não contêm nomes de personagens
  associados a participantes.
- Mitigação C3: a UI não exibe diferenças de agregados antes/depois da exclusão; a emenda 2.0.0
  aceita explicitamente o risco residual de inferência por comparação manual.
- O banco e os backups são acessíveis apenas a operadores confiáveis; isso é uma limitação
  operacional documentada, não uma funcionalidade administrativa.

## 9. Interface

- Django Templates + Bootstrap 5.3.8 + CSS próprio com os tokens de `docs/design-system.md`.
- HTMX 2.0.11 apenas para busca/filtros de personagens, contador e ações administrativas simples.
- Sem SPA, sem framework JS, sem Node no build.
- Inter auto-hospedada; Lucide em sprite SVG local; Bootstrap/HTMX vendorizados.
- Componentes e estados seguem o design system: botões, formulários, cards de votação/personagem,
  busca/filtros, contador, mensagens, estados vazios, responsividade e acessibilidade WCAG 2.2 AA.
- Imagens com `loading="lazy"`, dimensões fixas, `alt` e fallback via JS (sem `onerror` inline, por
  CSP).
--Acessibilidade: foco visível, navegação por teclado, `aria-live` para contador/mensagens,
  contraste, alvos de toque e respeito a `prefers-reduced-motion`.
- CSP com `script-src 'self'`; `style-src` pode usar `'unsafe-inline'` apenas para componentes
  Bootstrap, a validar na implementação. Sem scripts inline próprios.

## 10. Testes

- `pytest` + `pytest-django` + `factory_boy` + `freezegun`.
- PostgreSQL real em testes (Docker/CI), pois triggers e locks não existem em SQLite.
- Testes unitários: serviços, ranking, filtros, validação de CSV, imagens, state machine.
- Testes de integração: rotas, auth/autorização, CSRF, sessão, fluxos de voto, exclusão,
  cancelamento, resultados, privacidade, snapshots, scheduler.
- Testes de concorrência: threads/transações concorrentes para envio duplo, envio vs encerramento,
  exclusão vs encerramento, abertura vs cancelamento.
- Testes de tempo: `freezegun` para abertura/encerramento/recuperação.
- **E2E opcional**: Playwright para 3–5 fluxos críticos e verificação de responsividade/acessibilidade
  básica. Não é pré-requisito para o MVP, mas é recomendado antes do deploy.
- **Medições manuais**: SC-001/SC-002 no quickstart e SC-010 com 500 personagens; registrar em
  `docs/operations.md` (decisões G2 A e G4 B).
- Cobertura mínima: não definir percentual artificial; exigir cobertura dos fluxos críticos e dos
  invariantes listados na especificação.

## 11. Implantação

- Docker Compose com `db`, `release`, `web`, `scheduler` e `caddy`.
- `release` executa `migrate`, `collectstatic` e `createcachetable` uma vez, antes de web/scheduler.
- `web` com Gunicorn (WSGI), sem código-fonte montado em produção.
- `caddy` serve `/static/*` e `/media/*`, faz TLS automático e aplica cabeçalhos de segurança.
- Volumes: `postgres_data`, `media_data`, `static_data`, `caddy_data`, `caddy_config`.
- Backups: `pg_dump -Fc` + tar do volume de mídia, com retenção e restauração documentadas.
- Logs em stdout, rotação do Docker, healthcheck `/health/` e verificação de disco/backup.
- Migrações nunca rodam automaticamente em cada worker; são etapa de release.
- Variáveis de ambiente em `.env`; segredos não versionados.

## 12. Decisões em aberto e riscos residuais

| Item | Situação | Próximo passo |
|---|---|---|
| Autorização para scraping/redistribuição GameTora | Não localizada | Contatar mantenedores; manter importação manual |
| Direitos das imagens | Não presumidos | Obter permissão ou manter acervo privado documentado |
| Fonte de imagens definitiva | Curadoria local | Validar cobertura e qualidade; considerar umapyoi.net se autorizado |
| FR-092 / fonte do catálogo | Alinhado | GameTora referência; arquivo operacional no MVP |
| Licença de imagens sem gate técnico | Aceito (G5 C) | Revisão manual em `docs/operations.md` |
| Medições SC-001/SC-002/SC-010 | Manuais (G2 A/G4 B) | Quickstart/operations |
| Cadastro público/username sem teste dedicado | Aceito (M3 B) | Checklist em `docs/security-review.md` |
| Frequência da sincronização periódica | Não definida na spec | Default diário (03:00 America/Sao_Paulo) + manual |
| Provedor/host de produção e domínio | Não definido | Definir antes do deploy; Caddy usa `DOMAIN` |
| Retenção de backups | Não definida | 30 diários + 12 mensais, fora do host |
| Upgrade Django 6.2 LTS | Planejado | Reavaliar em 2027, antes do fim do suporte da 5.2 |

## 13. Fontes consultadas

- Django 5.2/6.1 releases e suporte: <https://www.djangoproject.com/download/>,
  <https://docs.djangoproject.com/en/stable/releases/> (consultado em 2026-11-07).
- PostgreSQL releases: <https://www.postgresql.org/support/versioning/> (2026-11-07).
- Python releases: <https://www.python.org/downloads/> (2026-11-07).
- HTMX releases: <https://github.com/bigskysoftware/htmx/releases> (2026-11-07).
- Bootstrap releases: <https://getbootstrap.com/docs/5.3/> (2026-11-07).
- pytest-django: <https://pypi.org/project/pytest-django/> (2026-11-07).
- GameTora, páginas de personagens e avisos: <https://gametora.com/umamusume/characters>
  (2026-11-07).
- uma.guide, personagens e aviso: <https://uma.guide/characters> e
  <https://uma.guide/about/> (2026-11-07).
- umapyoi.net, documentação da API e limites: <https://api.umapyoi.net/docs/> (2026-11-07).
- Caddy vs Nginx para Django: <https://caddyserver.com/docs/> e referências de deploy
  consultadas em 2026-11-07.
