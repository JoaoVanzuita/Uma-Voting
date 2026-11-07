# Contract: Serviços de Domínio

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Princípio**: regras de negócio em serviços; views apenas orquestram entrada/saída; o banco
reforça invariantes críticos.

## 1. Convenções

- Serviços são funções ou classes em `apps/<app>/services/`.
- Toda operação que altera estado crítico roda em `transaction.atomic()`.
- Erros de negócio usam exceções específicas (`DomainError` e subclasses), traduzidas para
  mensagens PT-BR na view.
- Serviços recebem IDs e valores primitivos; não recebem `request` (exceto o serviço de
  login, que precisa da sessão).
- Serviços administrativos nunca retornam `BallotChoice` nem carregam escolhas.

## 2. Contas e acesso

### 2.1 `accounts.services.create_admin(username, password)`

- Cria usuário com `is_admin=True`, `is_active=True` e senha utilizável.
- Valida username único case-insensitive.
- Uso: comando `create_admin` e provisionamento inicial.

### 2.2 `accounts.services.authenticate_admin(username, password)`

- Usa `django.contrib.auth.authenticate`.
- Exige `is_admin=True` e `is_active=True`.
- Retorna o usuário ou `None`; não revela qual condição falhou.
- Aplica throttle por IP + username.

### 2.3 `accounts.services.login_participant(request, username)`

- Normaliza e busca usuário por `username__iexact`.
- Rejeita:
  - username inexistente;
  - usuário inativo;
  - usuário com `is_admin=True` (deve usar o login administrativo).
- A mensagem de falha é genérica e não revela se o username existe, está inativo ou é
  administrativo; o link para o acesso administrativo fica visível na página.
- Em sucesso, chama `login(request, user, backend=...)` e registra `last_login`.
- Aplica throttle por IP.
- **Limitação documentada**: username não comprova identidade; o serviço só verifica
  existência e estado.

### 2.4 `accounts.services.logout(request)`

- Chama `django.contrib.auth.logout`.
- Invalida a sessão e redireciona.

### 2.5 `accounts.services.throttle_login(scope, ip, username=None)`

- Usa `DatabaseCache`; janela de 5 minutos.
- Limites iniciais:
  - login administrativo: 5 falhas por IP + username, 20 por IP;
  - login de participante: 20 tentativas por IP.
- Retorna `allowed`/`retry_after`.
- Não registra senha.

## 3. Participantes

### 3.1 `participants.services.create_participant(username)`

- Cria usuário `is_admin=False`, `is_active=True`, `set_unusable_password()`.
- Valida unicidade case-insensitive.
- Não cria cadastro público.

### 3.2 `participants.services.update_participant(user, username)`

- Atualiza username com a mesma validação de unicidade.
- Rejeita usuários `is_admin=True`; contas administrativas são provisionadas por comando e
  não são editáveis pela área de participantes.
- Não altera votações existentes.

### 3.3 `participants.services.deactivate_participant(user)`

- Rejeita usuários `is_admin=True`.
- Define `is_active=False`.
- Não remove `VotingEligibility` de votações existentes.
- Sessões ativas são invalidadas na próxima requisição pelo backend.

### 3.4 `participants.services.import_participants(csv_file) -> ImportReport`

- Formato: uma coluna `username`, cabeçalho opcional.
- Valida:
  - arquivo não vazio;
  - tamanho máximo (ex.: 1 MB);
  - encoding UTF-8;
  - linhas vazias ignoradas;
  - username obrigatório;
  - duplicidades no arquivo (case-insensitive);
  - duplicidades com o banco (case-insensitive).
- **Atômico**: qualquer inconsistência impede toda a importação.
- Retorna `ImportReport(valid_rows, errors=[{line, message}], imported_count)`.
- A view mostra o relatório; o admin confirma a importação somente se não houver erros.

## 4. Catálogo

### 4.1 `catalog.services.sync_from_file(path, source) -> SyncRun`

1. Abre a transação.
2. Cria `SyncRun` com status `running`.
3. Parseia e valida o arquivo (ver contrato de formatos).
4. Para cada personagem:
   - inexistente e com versão Global → cria personagem/versões/aptidões e registra
     `SyncChange(auto_applied)`;
   - existente com diferenças → registra `SyncChange(pending)` com payload proposto;
   - sem diferenças → ignora.
5. Atualiza `SyncRun` com `success`/`partial` e resumo.
6. Em erro de parsing, `failed` e rollback das alterações de catálogo; o `SyncRun` de
   falha é preservado.
- Novas versões de personagem existente são `pending` (não auto-aplicadas).
- A sincronização nunca altera snapshots de votações.

### 4.2 `catalog.services.approve_change(change, admin) -> None`

- Exige `change.status='pending'`.
- Aplica o payload em transação:
  - cria/atualiza personagem, versões e aptidões;
  - atualiza `character.updated_at`;
  - marca `approved`, `reviewed_by`, `reviewed_at`.
- Rejeita payload inválido sem alterar o catálogo.

### 4.3 `catalog.services.reject_change(change, admin, note) -> None`

- Exige `pending`; marca `rejected`, `reviewed_by`, `reviewed_at`, `review_note`.

### 4.4 `catalog.services.eligible_versions(character, cutoff) -> QuerySet`

- Retorna versões com `release_date_global <= cutoff`.
- Uma personagem é elegível se o queryset não for vazio.

### 4.5 `catalog.services.consolidated_aptitudes(character, cutoff) -> set[Aptitude]`

- União distinta das aptidões das versões elegíveis.
- Usada para exibição; o filtro usa a granularidade de versão.

### 4.6 `catalog.services.search_characters(voting, filters, query, selected_ids)`

- Opera sobre `VotingCharacterSnapshot` (não no catálogo atual).
- Filtros: dentro da categoria OR; entre categorias AND; mesma versão.
- Busca por `display_name` com `icontains`.
- Retorna personagens distintas, com `selected` calculado.
- Nunca retorna duplicatas.

## 5. Imagens

### 5.1 `catalog.services.validate_image_asset(asset) -> ImageValidation`

- Verifica:
  - arquivo existe em `MEDIA_ROOT/file_path`;
  - extensão/formato permitido;
  - Pillow abre e verifica integridade;
  - dimensões/proporção consistentes;
  - checksum corresponde (se registrado);
  - personagem associada existe.
- Atualiza `status`, `width`, `height`, `validated_at`.
- Retorna `valid`, `invalid` ou `missing` com motivo.

### 5.2 `catalog.services.validate_all_images() -> ImageValidationReport`

- Itera assets e personagens.
- Detecta:
  - personagens sem asset corrente válido;
  - assets inválidos/ausentes;
  - referências quebradas;
  - arquivos órfãos no diretório;
  - checksums duplicados entre personagens diferentes;
  - mais de um asset corrente (deve ser impossível pelo índice).
- Retorna relatório agregado; a view administrativa exibe.

### 5.3 `catalog.services.import_images(manifest, source_dir, dry_run) -> ImageImportReport`

1. Lê o manifesto (`character_stable_id`, `file`, `source`, `source_url`,
   `license_note`).
2. Valida personagem e arquivo.
3. Abre com Pillow; converte para WebP 256 × 256 com `ImageOps.pad` (sem distorção) ou
   respeita imagem já padronizada.
4. Calcula SHA-256 do arquivo normalizado.
5. Destino: `characters/<stable_id>/<sha256>.webp`.
6. Em `dry_run`, retorna inclusões, substituições, duplicidades e erros sem alterar o
   banco.
7. Em `apply`:
   - grava o arquivo de forma atômica (tmp + rename);
   - cria `ImageAsset` e marca o anterior como `is_current=False`;
   - nunca sobrescreve arquivo existente com mesmo checksum (reutiliza);
   - não apaga arquivos antigos.
- Cada item é aplicado em transação própria; uma falha não impede os demais. O relatório
  lista aplicados, rejeitados e motivos.

## 6. Votações: ciclo de vida

### 6.1 `voting.services.create_voting(data, admin) -> Voting`

- Cria em `draft`.
- Adiciona todos os usuários ativos como elegíveis, incluindo administradores que também podem
  votar.
- Valida `choices_count > 0`, datas e modos; datas são obrigatórias nos modos automáticos e
  informativas/opcionais nos modos manuais.
- `catalog_cutoff_date` default `2026-12-01`.

### 6.2 `voting.services.update_voting(voting, data) -> Voting`

- Exige `status='draft'`.
- Valida campos e mantém elegíveis; aplica a mesma regra de datas do `create_voting`.
- Não permite alterar `created_by`.

### 6.3 `voting.services.schedule_voting(voting) -> Voting`

- Exige `status='draft'` e `open_mode='automatic'`.
- Exige `opens_at` no futuro e `closes_at` válido; datas obrigatórias apenas nos modos
  automáticos correspondentes.
- Exige ≥1 elegível e catálogo suficiente para `choices_count`.
- Define `status='scheduled'`.
- A configuração e os elegíveis ficam bloqueados.

### 6.4 `voting.services.open_voting(voting, trigger) -> Voting`

Transação:

1. `SELECT ... FOR UPDATE` na votação.
2. Exige `status='draft'` com `trigger='admin'` e `open_mode='manual'`, ou
   `status='scheduled'` com `trigger='scheduler'` e `open_mode='automatic'`.
3. Exige ≥1 elegível e ≥`choices_count` personagens elegíveis; se `close_mode='automatic'`,
   exige `closes_at > now()`.
4. Cria snapshots de personagens, versões e aptidões.
5. Define `eligible_frozen_at`, `catalog_frozen_at`, `opened_at`, `status='open'`.
6. Commit.

A ação administrativa de abrir não é exposta para votações agendadas; essas são abertas
pelo scheduler no horário. Se o administrador quiser antecipar, deve editar o modo para
manual enquanto a votação ainda estiver em rascunho.

Se a validação falhar:

- abertura manual: lança `PreconditionError`, sem alterar estado;
- abertura automática: `cancel_voting` com motivo `no_eligible`/`insufficient_catalog`.

### 6.5 `voting.services.close_voting(voting, trigger) -> Voting`

1. `SELECT ... FOR UPDATE`.
2. Exige `status='open'`.
3. Define `closed_at` e `status='closed'`.
4. Commit.

### 6.6 `voting.services.cancel_voting(voting, admin=None, reason=None) -> Voting`

1. `SELECT ... FOR UPDATE`.
2. Se já `cancelled`, no-op idempotente.
3. Define `status='cancelled'`, `cancelled_at`, motivo.
4. Apaga todas as `Ballot` (cascade em choices), permitido pelo trigger no estado
   `cancelled`.
5. Commit.
- Funciona em `draft`, `scheduled`, `open` e `closed`.
- Votação permanece no histórico administrativo; não aparece para participantes.

### 6.7 `voting.services.process_due_transitions(now=None) -> SchedulerReport`

1. Adquire `pg_try_advisory_lock`.
2. Busca votações devidas com `SELECT ... FOR UPDATE SKIP LOCKED`:
   - `scheduled` + `open_mode='automatic'` + `opens_at <= now`;
   - `open` + `close_mode='automatic'` + `closes_at <= now`.
3. Para cada:
   - se `scheduled` e `closes_at` já passou (quando automático) → cancelar;
   - se `scheduled` e ainda há janela → abrir; se pré-condições falharem → cancelar;
   - se `open` e `closes_at` passou → encerrar.
4. Registra resultados; erros em uma votação não impedem as demais.
5. Libera o lock.
- Idempotente: repetir a chamada não duplica transições.
- Executa sem navegador/requisição.

## 7. Cédulas

### 7.1 `voting.services.submit_ballot(voting, participant, character_ids) -> Ballot`

Transação:

1. `SELECT ... FOR SHARE` na votação (bloqueia contra encerramento/cancelamento).
2. Verifica `status='open'`, `now() < closes_at` (quando `close_mode='automatic'`) e
   elegibilidade.
3. Verifica se já existe cédula (`UNIQUE`); se sim, `AlreadyVotedError`.
4. Valida:
   - quantidade exata = `choices_count`;
   - IDs distintos;
   - todos os IDs existem em `VotingCharacterSnapshot` da votação.
5. Cria `Ballot` + `BallotChoice` em uma transação.
6. Retorna a cédula.
- Corridas: unique constraint e trigger de contagem são as barreiras finais.
- Não lê nem retorna escolhas de outros participantes.

### 7.2 `voting.services.get_own_ballot(voting, participant) -> Ballot|None`

- Filtra por `voting` e `participant`; retorna escolhas apenas do próprio usuário, inclusive
  quando o usuário é administrador no modo participante.
- Nunca aceita `ballot_id` de outro participante.
- Nenhuma visão administrativa chama este serviço para outro usuário.

### 7.3 `voting.services.delete_ballot_admin(voting, participant, admin) -> None`

Transação:

1. `SELECT ... FOR UPDATE` na votação.
2. Exige `status='open'` e, quando `close_mode='automatic'`, `now() < closes_at`.
3. Localiza `Ballot` por `voting_id` + `participant_id`; se não existir, no-op.
4. Apaga a cédula (cascade choices).
5. Commit.
- Não carrega `BallotChoice`; não registra escolhas; não notifica o participante.
- A view/UI não exibe diferenças de agregados antes/depois da exclusão; a operação ocorre em
  fluxo dedicado. Exceção constitucional da emenda 2.0.0.
- Após exclusão, o participante pode votar novamente.

## 8. Resultados

### 8.1 `voting.services.aggregate_results(voting) -> list[ResultRow]`

- `BallotChoice` agrupado por `character_snapshot_id`, `COUNT(*)`.
- Retorna `stable_id`, `display_name`, `image_asset`, `votes`.
- Permitido ao admin em `open`/`closed`; ao participante somente em `closed`.
- Nunca inclui `participant_id` nem escolhas individuais, inclusive as do próprio admin.

### 8.2 `voting.services.participation(voting) -> list[ParticipationRow]`

- `VotingEligibility` + `EXISTS(Ballot)`.
- Retorna `username`, `voted`.
- Somente admin.

### 8.3 `voting.services.rank_results(rows) -> list[RankedRow]`

- Filtra `votes > 0` para o resultado final.
- Ordena por `votes DESC`, `display_name` apenas como ordenação estável de apresentação
  (não como desempate de posição).
- Posição densa: `1, 2, 2, 3, 3`.
- Empates com a mesma posição são todos retornados.
- Votação cancelada: lista vazia/erro de domínio.

## 9. Privacidade e logging

- Serviços administrativos importam apenas `Ballot` para contagem/existência; não
  importam `BallotChoice` em views/relatórios.
- Nenhum serviço administrativo retorna escolhas; a rota de participante retorna somente a
  cédula do próprio `request.user`, inclusive para admin no modo participante.
- Logs de transição registram `voting_id`, estado anterior/novo, gatilho e timestamp.
- Logs de cédula registram apenas `voting_id`, `participant_id` e sucesso/falha; nunca
  `character_ids`.
- Erros de validação de cédula não incluem a lista de escolhas em logs.
