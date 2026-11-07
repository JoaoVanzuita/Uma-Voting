# Contract: Rotas HTTP

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Escopo**: contrato de navegação server-rendered. Todas as páginas são HTML; busca/filtros e
algumas ações administrativas retornam fragmentos HTML via HTMX.

## 1. Convenções

- Todos os POSTs exigem CSRF (`X-CSRFToken` ou campo `csrfmiddlewaretoken`).
- Rotas de participante exigem sessão ativa; rotas de votação exigem elegibilidade.
- Rotas `/admin/...` exigem `user.is_admin=True`, verificado no servidor.
- Erros de formulário retornam a página com mensagens em PT-BR e status 200 (ou 400 para
  requisições HTMX inválidas).
- Conflitos de estado retornam 409; falta de permissão retorna 403; recurso inexistente 404.
- Nenhuma resposta administrativa contém escolhas individuais de cédula.
- Nomes de rota Django usam namespaces `participant:` e `admin:`.

## 2. Rotas públicas

| Método | Caminho | Nome | Entrada | Saída | Notas |
|---|---|---|---|---|---|
| GET | `/entrar/` | `participant:login` | — | Página de login por username | Se já autenticado, redireciona para `/` |
| POST | `/entrar/` | `participant:login` | `username` | 302 `/` ou página com erro | Rejeita username inexistente, inativo ou administrativo |
| GET | `/admin/entrar/` | `admin:login` | — | Página de login administrativo | Username + senha |
| POST | `/admin/entrar/` | `admin:login` | `username`, `password` | 302 `/admin/` ou erro | Somente `is_admin=True` |
| GET | `/health/` | `health` | — | `{"status":"ok","db":"ok"}` | Usado por healthcheck; sem dados sensíveis |

## 3. Rotas de participante

Todas exigem sessão ativa. `voting_id` é validado contra a elegibilidade do usuário.

| Método | Caminho | Nome | Entrada | Saída | Notas |
|---|---|---|---|---|---|
| GET | `/` | `participant:home` | — | Lista de votações abertas/agendadas elegíveis + link do histórico | Estado vazio simples |
| GET | `/historico/` | `participant:history` | — | Votações respondidas/encerradas | Canceladas não aparecem |
| GET | `/votacoes/<int:voting_id>/` | `participant:voting_detail` | — | Página de seleção de personagens | Cards, busca, filtros, contador |
| GET | `/votacoes/<int:voting_id>/personagens/` | `participant:character_grid` | `q`, `strategy`, `distance`, `surface`, `selected` | Fragmento HTML da grade | HTMX; `selected` repete IDs para preservar seleção |
| POST | `/votacoes/<int:voting_id>/revisar/` | `participant:review` | `character_ids` (repetido) | Página de revisão | Valida quantidade, duplicidade, snapshot |
| POST | `/votacoes/<int:voting_id>/confirmar/` | `participant:confirm` | `character_ids` (repetido) | 302 para cédula ou página de erro | Cria cédula definitiva; 409 se já votou |
| GET | `/votacoes/<int:voting_id>/cedula/` | `participant:ballot` | — | Escolhas da própria cédula | Somente do próprio usuário, inclusive admin no modo participante |
| GET | `/votacoes/<int:voting_id>/resultado/` | `participant:result` | — | Ranking final | Somente votação encerrada e elegível |
| POST | `/sair/` | `participant:logout` | — | 302 `/entrar/` | Encerra sessão |
| POST | `/participante/modo-admin/` | `participant:admin_mode` | — | 302 `/admin/` | Somente `is_admin`; alterna a experiência |

## 4. Rotas administrativas

### 4.1 Painel e modo

| Método | Caminho | Nome | Notas |
|---|---|---|---|
| GET | `/admin/` | `admin:dashboard` | Resumo, votações em andamento, atalhos |
| POST | `/admin/modo-participante/` | `admin:participant_mode` | Alterna para a experiência de participante |
| POST | `/admin/sair/` | `admin:logout` | Encerra sessão administrativa |

### 4.2 Participantes

| Método | Caminho | Nome | Notas |
|---|---|---|---|
| GET | `/admin/participantes/` | `admin:participant_list` | Lista e pesquisa |
| GET/POST | `/admin/participantes/novo/` | `admin:participant_create` | Cadastro individual |
| GET/POST | `/admin/participantes/<int:user_id>/editar/` | `admin:participant_edit` | Edição |
| POST | `/admin/participantes/<int:user_id>/desativar/` | `admin:participant_deactivate` | Desativa; não altera votações existentes |
| GET/POST | `/admin/participantes/importar/` | `admin:participant_import` | Upload CSV, validação e prévia; importação atômica |

### 4.3 Catálogo

| Método | Caminho | Nome | Notas |
|---|---|---|---|
| GET | `/admin/catalogo/` | `admin:catalog_status` | Estado, última sincronização, imagens |
| POST | `/admin/catalogo/sincronizar/` | `admin:catalog_sync` | Executa sincronização manual de fonte de arquivo |
| GET | `/admin/catalogo/sincronizacoes/<int:sync_id>/` | `admin:catalog_sync_detail` | Prévia e histórico |
| POST | `/admin/catalogo/mudancas/<int:change_id>/aprovar/` | `admin:catalog_approve` | Aprova mudança pendente |
| POST | `/admin/catalogo/mudancas/<int:change_id>/rejeitar/` | `admin:catalog_reject` | Rejeita mudança pendente |
| GET | `/admin/catalogo/personagens/` | `admin:catalog_characters` | Consulta de personagens/aptidões |
| GET | `/admin/catalogo/imagens/` | `admin:catalog_images` | Estado das imagens; ausentes/inválidas |
| POST | `/admin/catalogo/imagens/validar/` | `admin:catalog_images_validate` | Executa validação e mostra relatório |

### 4.4 Votações

| Método | Caminho | Nome | Notas |
|---|---|---|---|
| GET | `/admin/votacoes/` | `admin:voting_list` | Lista e filtros por estado |
| GET/POST | `/admin/votacoes/nova/` | `admin:voting_create` | Criação/configuração |
| GET/POST | `/admin/votacoes/<int:voting_id>/editar/` | `admin:voting_edit` | Somente em rascunho |
| GET | `/admin/votacoes/<int:voting_id>/` | `admin:voting_detail` | Detalhe, elegíveis, ações |
| POST | `/admin/votacoes/<int:voting_id>/abrir/` | `admin:voting_open` | Abertura manual |
| POST | `/admin/votacoes/<int:voting_id>/encerrar/` | `admin:voting_close` | Encerramento manual |
| POST | `/admin/votacoes/<int:voting_id>/cancelar/` | `admin:voting_cancel` | Cancela em qualquer estado; apaga cédulas |
| GET | `/admin/votacoes/<int:voting_id>/resultados/` | `admin:voting_results` | Agregados; sem escolhas |
| GET | `/admin/votacoes/<int:voting_id>/participacao/` | `admin:voting_participation` | Quem votou/não votou; sem escolhas |
| POST | `/admin/votacoes/<int:voting_id>/cedulas/<int:user_id>/excluir/` | `admin:ballot_delete` | Exclusão enquanto aberta; sem leitura das escolhas; sem diff de agregados |

## 5. Regras de autorização

- `participant:*`: qualquer usuário autenticado e ativo, inclusive administrador em modo
  participante.
- `admin:*`: `is_admin=True`; a verificação ocorre em mixin/decorator no servidor.
- Votação específica: o usuário precisa estar em `VotingEligibility` daquela votação.
- Cédula própria: filtro obrigatório por `participant_id = request.user.id`, inclusive para
  administrador no modo participante.
- Nenhuma rota administrativa expõe escolhas individuais, inclusive as do próprio admin; a
  cédula própria do admin só é acessível pela rota `participant:ballot`.
- Resultado de participante: somente `voting.status='closed'`.
- Canceladas: 404 para participantes; visíveis apenas no admin.
- Administrador em modo participante não perde permissões administrativas; o modo é apenas
  de apresentação. Nenhuma tela participante expõe agregados durante a votação.

## 6. Respostas HTMX

- `GET /votacoes/<id>/personagens/` retorna apenas o fragmento da grade, com:
  - cards com imagem/placeholder, nome e checkbox;
  - estado `checked` conforme `selected`;
  - contador e resumo de seleção atualizados via `hx-swap-oob` ou região separada;
  - `aria-live` para leitores de tela.
- Ações administrativas destrutivas usam `hx-confirm` e retornam o fragmento atualizado ou
  um redirecionamento `HX-Redirect`.
- Requisições HTMX sem permissão retornam 403; sessão expirada retorna `HX-Redirect` para
  `/entrar/`.

## 7. Códigos de erro

| Situação | Status | Corpo |
|---|---|---|
| Formulário inválido | 200/400 | Página com erros por campo |
| Não autenticado | 302 | Redireciona para login |
| Sem permissão administrativa | 403 | Página 403 em PT-BR |
| Votação inexistente/cancelada para participante | 404 | Página 404 em PT-BR |
| Participante não elegível | 403 | Mensagem específica |
| Cédula já existente | 409 | Mensagem "Você já enviou uma cédula" |
| Votação não está aberta | 409 | Mensagem de estado |
| Cédula com quantidade/duplicidade inválida | 200/400 | Revisão com erros |
| Erro interno | 500 | Página genérica sem dados sensíveis |
