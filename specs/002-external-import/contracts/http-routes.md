# Contract: Rotas HTTP da Importação Externa

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Escopo**: rotas administrativas server-rendered e endpoint JSON de progresso.

## 1. Convenções

- Todas as rotas exigem `user.is_admin=True`, verificado no servidor (`@admin_required`).
- Todos os POSTs exigem CSRF.
- Nenhuma rota aceita upload de arquivo, URL de fonte, host, credencial ou caminho.
- Erros de formulário usam mensagens em PT-BR via `django.contrib.messages`.
- `404` para execução/fonte inexistente; `403` para não administrador; `409` para ação inválida
  no estado atual.
- Ações que alteram estado são sempre POST.
- Nomes de rota usam o namespace `admin:`.

## 2. Rotas

| Método | Caminho | Nome | Entrada | Saída | Notas |
|---|---|---|---|---|---|
| GET | `/admin/catalogo/` | `admin:catalog_status` | — | Página de catálogo com painel de fontes externas | Painel exibe todas as fontes, inclusive inelegíveis |
| GET | `/admin/catalogo/importar/` | `admin:catalog_import` | — | Formulário de importação | Seletor lista somente fontes elegíveis |
| POST | `/admin/catalogo/importar/` | `admin:catalog_import` | `source`, `kind`, `image_scope` | `302` para o detalhe da execução | Cria `ImportJob` e retorna imediatamente |
| GET | `/admin/catalogo/importacoes/` | `admin:catalog_import_list` | `status?`, `source?`, `page?` | Histórico paginado | Ordenado por `-created_at` |
| GET | `/admin/catalogo/importacoes/<int:job_id>/` | `admin:catalog_import_detail` | — | Detalhe com progresso e relatório | Atualização automática enquanto ativo |
| GET | `/admin/catalogo/importacoes/<int:job_id>/status/` | `admin:catalog_import_status` | — | JSON de progresso | Usado pelo polling |
| POST | `/admin/catalogo/importacoes/<int:job_id>/cancelar/` | `admin:catalog_import_cancel` | — | `302` para o detalhe | `409` se terminal |
| POST | `/admin/catalogo/importacoes/<int:job_id>/repetir/` | `admin:catalog_import_retry` | — | `302` para o novo detalhe | `409` se ainda ativo |
| POST | `/admin/catalogo/fontes/<int:source_id>/verificar/` | `admin:catalog_source_check` | — | `302` para o detalhe da fonte ou catálogo | Verifica disponibilidade sem importar; funciona para fonte desabilitada com conector |

## 3. Formulário de criação

### 3.1 Campos

| Campo | Tipo | Obrigatório | Regras |
|---|---|---|---|
| `source` | select | Sim | Apenas fontes `enabled=True`, com `adapter` registrado |
| `kind` | select | Sim | `catalog`, `images`, `full` |
| `image_scope` | select | Condicional | `missing` (padrão) ou `all`; usado quando `kind` inclui imagens |

### 3.2 Validação

- Fonte inexistente, desabilitada ou sem conector: erro de formulário.
- `EXTERNAL_IMPORT_ENABLED=False`: erro "Importação externa desabilitada."
- A licença não é exibida nem usada como critério de bloqueio.
- `image_scope` inválido é normalizado para `missing`.
- Se já existir execução `queued` ou `running` para a mesma fonte, redireciona para ela com
  mensagem informativa, sem criar duplicata.

### 3.3 Efeito

```text
ImportJob.objects.create(
    source=source,
    kind=kind,
    status=queued,
    phase=queued,
    options={"image_scope": image_scope},
    triggered_by=request.user,
)
```

Nenhuma chamada de rede acontece na requisição.

## 4. Endpoint de status

`GET /admin/catalogo/importacoes/<job_id>/status/`

### 4.1 Resposta `200`

```json
{
  "id": 42,
  "status": "running",
  "status_label": "Em execução",
  "phase": "images",
  "phase_label": "Imagens",
  "progress": {
    "done": 40,
    "total": 170,
    "percent": 23
  },
  "current_step": "Baixando imagem de Special Week",
  "cancel_requested": false,
  "error": "",
  "started_at": "2026-11-12T13:00:00Z",
  "finished_at": null,
  "detail_url": "/admin/catalogo/importacoes/42/"
}
```

### 4.2 Regras

- `percent` é `0` quando `total=0`.
- `error` é resumido; o detalhe completo fica no relatório.
- Para estados terminais, `finished_at` é preenchido.
- O endpoint não retorna conteúdo de imagens, credenciais ou dados de participantes.
- Cache-Control: `no-store`.

### 4.3 Erros

| Situação | Status |
|---|---|
| Não administrador | `403` |
| Job inexistente | `404` |
| Método diferente de GET | `405` |

## 5. Cancelamento

`POST /admin/catalogo/importacoes/<job_id>/cancelar/`

- `queued`: marca `cancelled` imediatamente; worker não inicia.
- `running`: marca `cancel_requested=True`.
  - Fase de imagens: worker encerra entre itens, em até 1 item.
  - Fase de catálogo: worker verifica antes da aplicação e não grava alterações após a
    solicitação; a coleta em curso não é abortada.
- `success|partial|failed|cancelled`: `409` com mensagem "Execução já encerrada."
- Retorna `302` para o detalhe.

## 6. Repetição

`POST /admin/catalogo/importacoes/<job_id>/repetir/`

- Permitido para `partial`, `failed` e `cancelled`.
- Bloqueado para `queued` e `running` com `409`.
- Copia `source`, `kind` e `options`; cria novo `ImportJob` com `triggered_by=request.user`.
- Não altera a execução original.
- Retorna `302` para o detalhe da nova execução.

## 7. Verificação de fonte

`POST /admin/catalogo/fontes/<source_id>/verificar/`

- Executa apenas `adapter.check()`; não cria `ImportJob` e não grava catálogo/imagens.
- Funciona para fonte desabilitada que possua conector, para diagnóstico.
- Limite curto de tempo (mesmo timeout do cliente HTTP).
- Sucesso: mensagem "Fonte disponível."
- Falha: mensagem com motivo resumido.
- Retorna `302` para `/admin/catalogo/`.
- `404` se a fonte não existir; `409` se a fonte não tiver conector.

## 8. Detalhe da execução

A página de detalhe exibe:

- fonte, modo, escopo, status, fase e progresso;
- passo atual;
- quem disparou, quem cancelou (quando aplicável), execução de origem (quando repetição),
  início, fim e tentativas;
- última falha da fonte, com motivo resumido;
- relatório de catálogo (contagens, avisos, erros);
- relatório de imagens (contagens, erros por personagem);
- link para o `SyncRun` e para as mudanças aplicadas;
- link para `/admin/catalogo/imagens/`;
- ações de cancelar/repetir quando aplicáveis.

Enquanto o status for `queued` ou `running`, o front-end consulta o endpoint de status a cada 3
segundos e atualiza os campos sem recarregar a página. Ao atingir estado terminal, o polling
para.

## 9. Acessibilidade e mensagens

- Barra de progresso com `role="progressbar"`, `aria-valuenow`, `aria-valuemin` e
  `aria-valuemax`.
- Mensagens de erro associadas ao formulário.
- Ações destrutivas (cancelar) pedem confirmação.
- Textos em PT-BR, sem jargão técnico desnecessário.
