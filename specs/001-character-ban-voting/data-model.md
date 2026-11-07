# Data Model: Uma Voting

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Database**: PostgreSQL 18
**ORM**: Django 5.2

## 1. Convenções

- Chaves primárias `bigint` autoincrementais (`BigAutoField`).
- Timestamps em UTC (`DateTimeField` com `USE_TZ=True`); apresentação em
  `America/Sao_Paulo`.
- Datas de catálogo em `DateField` ISO (`YYYY-MM-DD`).
- Nomes de tabelas em `snake_case`, prefixados pelo app (`accounts_`, `catalog_`,
  `voting_`).
- Exclusões destrutivas são evitadas: usuários e personagens são desativados/arquivados;
  votações são canceladas, não apagadas.
- Constraints e índices declarados no Django; triggers e funções em migrations `RunSQL`
  específicas de PostgreSQL.
- Toda regra crítica é validada no serviço e reforçada no banco quando a integridade
  puder ser ameaçada por outro caminho.

## 2. Visão geral das entidades

```text
accounts.User 1 ─── N voting.VotingEligibility N ─── 1 voting.Voting
accounts.User 1 ─── N voting.Ballot N ─── 1 voting.Voting
voting.Ballot 1 ─── N voting.BallotChoice N ─── 1 voting.VotingCharacterSnapshot
voting.Voting 1 ─── N voting.VotingCharacterSnapshot 1 ─── N voting.VotingVersionSnapshot
voting.VotingVersionSnapshot 1 ─── N voting.VotingVersionAptitudeSnapshot N ─── 1 catalog.Aptitude
catalog.Character 1 ─── N catalog.CharacterVersion N ─── N catalog.Aptitude
catalog.Character 1 ─── N catalog.ImageAsset (um corrente)
catalog.Character 1 ─── N voting.VotingCharacterSnapshot (via source_character)
catalog.SyncRun 1 ─── N catalog.SyncChange
catalog.CatalogSource 1 ─── N catalog.SyncRun / catalog.ImageAsset
```

## 3. Contas e sessões

### 3.1 `accounts.User`

Usuário único do sistema; administrador e participante compartilham a mesma identidade.
Base: `AbstractBaseUser` (sem e-mail, nome legal ou campos de perfil não utilizados).

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `username` | CharField(150) | Obrigatório; exibição preserva a grafia |
| `password` | CharField(128) | Hash do Django; inutilizável para participantes |
| `is_admin` | BooleanField | Default `False` |
| `is_active` | BooleanField | Default `True`; desativado não autentica |
| `date_joined` | DateTimeField | Auto |
| `last_login` | DateTimeField | Nullable; atualizado pelo Django |

**Regras**:

- `USERNAME_FIELD = 'username'`; `REQUIRED_FIELDS = []`.
- Manager customizado; `get_by_natural_key(username)` usa `username__iexact` para login
  administrativo case-insensitive.
- `UNIQUE (LOWER(username))` — unicidade case-insensitive.
- Administrador: `is_admin=True`, senha utilizável.
- Participante: `is_active=True`, `set_unusable_password()`.
- Usuário desativado não autentica; a sessão é invalidada na próxima requisição pelo
  backend do Django.
- Administrador também pode ser elegível e votar; a mesma linha é usada.
- Não há e-mail, nome legal ou outro dado pessoal no MVP. A interface exibe somente
  `username`.

**Privacidade**: nenhum campo de perfil é exibido a outros participantes.

### 3.2 Sessão

Tabela padrão `django_session`. Sessões em banco, expiração ao fechar o navegador
(`SESSION_EXPIRE_AT_BROWSER_CLOSE=True`), logout por POST e limpeza periódica com
`clearsessions`.

## 4. Catálogo

### 4.1 `catalog.CatalogSource`

Documenta a origem dos dados e das imagens, separando viabilidade técnica de autorização.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `name` | CharField(100) | Ex.: `gametora`, `uma-guide`, `umapyoi`, `curadoria-local` |
| `kind` | CharField(20) | `html`, `api`, `file`, `manual` |
| `base_url` | URLField | Opcional |
| `terms_url` | URLField | Opcional |
| `license_note` | TextField | Obrigatório para fontes externas |
| `enabled` | BooleanField | Default `True` |
| `created_at` | DateTimeField | Auto |

**Regra**: uma fonte externa só é usada em automação quando `license_note` e `terms_url`
estiverem documentados e a autorização tiver sido verificada.

### 4.2 `catalog.Character`

Personagem canônica; uma única opção de votação.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `stable_id` | SlugField(120) | Único; identificador estável (ex.: `tokai-teio`) |
| `display_name` | CharField(150) | Nome exibido |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

**Regras**:

- `stable_id` único e imutável.
- O nome pode ser corrigido via aprovação de sincronização; snapshots preservam o nome
  do momento da abertura.
- Não há exclusão física de personagens com snapshots (`PROTECT`).

### 4.3 `catalog.CharacterVersion`

Versão/lançamento específico de uma personagem.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `character_id` | FK Character | `ON DELETE PROTECT` |
| `stable_id` | SlugField(150) | Único |
| `display_name` | CharField(200) | Nome da versão, uso administrativo |
| `release_date_global` | DateField | Nullable; null = não lançada no Global |
| `source_id` | FK CatalogSource | Nullable |
| `source_url` | URLField | Opcional |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (character_id, stable_id)`.
- Versões com `release_date_global IS NULL` ou `> cutoff` não entram no snapshot.
- Uma personagem elegível é aquela com pelo menos uma versão com
  `release_date_global <= cutoff`.
- Versões não são opções de votação; a opção é sempre a personagem canônica.

### 4.4 `catalog.Aptitude`

Lookup de aptidões.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `category` | CharField(20) | `strategy`, `distance`, `surface` |
| `value` | CharField(20) | Ver valores abaixo |
| `label` | CharField(50) | Rótulo PT-BR para exibição |

**Valores**:

- `strategy`: `front`, `pace`, `late`, `end`
- `distance`: `sprint`, `mile`, `medium`, `long`
- `surface`: `turf`, `dirt`

**Regra**: `UNIQUE (category, value)`.

### 4.5 `catalog.CharacterVersionAptitude`

Associação N:N entre versão e aptidão.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `version_id` | FK CharacterVersion | `ON DELETE CASCADE` |
| `aptitude_id` | FK Aptitude | `ON DELETE PROTECT` |

**Regras**:

- `UNIQUE (version_id, aptitude_id)`.
- Uma versão pode ter mais de uma distância ou superfície; a estratégia é normalmente
  uma, mas o modelo permite mais de uma se o dado de origem vier assim.
- A consolidação da personagem é a união das aptidões de todas as versões elegíveis.

## 5. Imagens

### 5.1 `catalog.ImageAsset`

Arquivo de imagem associado a uma personagem canônica. O histórico é preservado por
novas linhas; arquivos nunca são sobrescritos.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `character_id` | FK Character | `ON DELETE PROTECT` |
| `file_path` | CharField(255) | Único; relativo a `MEDIA_ROOT` |
| `is_current` | BooleanField | Default `False`; um corrente por personagem |
| `status` | CharField(20) | `valid`, `invalid`, `missing` |
| `checksum_sha256` | CharField(64) | Checksum do arquivo normalizado |
| `width` | PositiveIntegerField | Dimensão validada |
| `height` | PositiveIntegerField | Dimensão validada |
| `source_id` | FK CatalogSource | Nullable |
| `source_url` | URLField | Opcional |
| `license_note` | TextField | Origem/condições |
| `validated_at` | DateTimeField | Nullable |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (file_path)`.
- `UNIQUE (character_id) WHERE is_current = TRUE` — uma única imagem principal por
  personagem.
- `ON DELETE PROTECT` a partir de snapshots; assets referenciados nunca são apagados.
- `status='valid'` somente após validação de existência, formato, integridade e dimensões.
- Personagem sem asset corrente válido usa o placeholder; isso não a impede de votar.
- A autorização de uso de imagem externa é revisada manualmente antes de `import_images
  --apply`; o modelo registra `license_note` e origem, sem gate técnico no MVP.
- Nome do arquivo: `characters/<stable_id>/<sha256>.webp`. O checksum garante
  imutabilidade e evita colisões.
- A substituição cria um novo `ImageAsset` e marca o anterior como `is_current=False` em
  uma transação; o arquivo antigo permanece no disco.

## 6. Sincronização do catálogo

### 6.1 `catalog.SyncRun`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `source_id` | FK CatalogSource | Obrigatório |
| `started_at` | DateTimeField | Auto |
| `finished_at` | DateTimeField | Nullable |
| `status` | CharField(20) | `running`, `success`, `partial`, `failed` |
| `summary` | TextField | Resumo legível |
| `error_message` | TextField | Nullable |
| `triggered_by_id` | FK User | Nullable; null = agendador |
| `created_at` | DateTimeField | Auto |

**Regras**:

- Histórico imutável; não é apagado.
- Índice em `started_at` e `status`.
- Uma execução com falha não altera o catálogo.

### 6.2 `catalog.SyncChange`

Mudança detectada por uma sincronização.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `sync_run_id` | FK SyncRun | `ON DELETE PROTECT` |
| `change_type` | CharField(30) | `new_character`, `update_character`, `new_version`, `update_version`, `aptitude_change` |
| `character_id` | FK Character | Nullable |
| `version_id` | FK CharacterVersion | Nullable |
| `payload` | JSONField | Valores propostos normalizados |
| `status` | CharField(20) | `auto_applied`, `pending`, `approved`, `rejected` |
| `reviewed_by_id` | FK User | Nullable |
| `reviewed_at` | DateTimeField | Nullable |
| `review_note` | TextField | Nullable |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `new_character` é aplicado automaticamente (`auto_applied`) quando a personagem é
  elegível no Global.
- Qualquer mudança em personagem existente (`update_character`, `new_version`,
  `update_version`, `aptitude_change`) fica `pending` até aprovação.
- A aprovação aplica o payload em transação única e grava `approved`; a rejeição grava
  `rejected`.
- `payload` deve conter os campos necessários para reaplicar a mudança sem consultar a
  fonte novamente.
- A aprovação nunca altera snapshots de votações existentes.

## 7. Votações

### 7.1 `voting.Voting`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `title` | CharField(200) | Obrigatório |
| `description` | TextField | Opcional |
| `choices_count` | PositiveSmallIntegerField | Default 3; `CHECK > 0` |
| `catalog_cutoff_date` | DateField | Default `2026-12-01`; configurável |
| `opens_at` | DateTimeField | Nullable; obrigatório se `open_mode='automatic'`; informativo e opcional se manual |
| `closes_at` | DateTimeField | Nullable; obrigatório se `close_mode='automatic'`; informativo e opcional se manual |
| `open_mode` | CharField(10) | `manual`, `automatic` |
| `close_mode` | CharField(10) | `manual`, `automatic` |
| `status` | CharField(12) | `draft`, `scheduled`, `open`, `closed`, `cancelled` |
| `created_by_id` | FK User | `ON DELETE PROTECT` |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |
| `eligible_frozen_at` | DateTimeField | Nullable |
| `catalog_frozen_at` | DateTimeField | Nullable |
| `opened_at` | DateTimeField | Nullable |
| `closed_at` | DateTimeField | Nullable |
| `cancelled_at` | DateTimeField | Nullable |

**Constraints**:

- `CHECK (choices_count > 0)`.
- `CHECK (opens_at IS NULL OR closes_at IS NULL OR closes_at > opens_at)`.
- `CHECK (open_mode <> 'automatic' OR opens_at IS NOT NULL)`.
- `CHECK (close_mode <> 'automatic' OR closes_at IS NOT NULL)`.
- `CHECK (status IN ('draft','scheduled','open','closed','cancelled'))`.
- Índices: `(status, opens_at)`, `(status, closes_at)`.

**Regras de edição**:

- Enquanto `draft`, todos os campos de configuração podem ser editados.
- Ao entrar em `scheduled`, a configuração fica imutável (inclusive elegíveis).
- `open`, `closed` e `cancelled` também mantêm a configuração congelada.
- `status`, timestamps de transição e campos de auditoria podem mudar conforme a
  transição; `created_by` é imutável.
- Datas são obrigatórias nos modos automáticos e informativas/opcionais nos modos manuais;
  quando informadas, `closes_at` MUST ser posterior a `opens_at`.
- A abertura manual só é permitida em `draft` com `open_mode='manual'`; a abertura
  automática de `scheduled` é feita pelo scheduler.

### 7.2 `voting.VotingEligibility`

Participantes elegíveis; em rascunho é a seleção editável; a partir de agendada é o
snapshot de elegibilidade.

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `voting_id` | FK Voting | `ON DELETE PROTECT` |
| `user_id` | FK User | `ON DELETE PROTECT` |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (voting_id, user_id)`.
- Índice em `user_id`.
- Inserção/remoção apenas com a votação em `draft` (trigger).
- Novas votações recebem todos os usuários ativos no momento da criação.
- Usuários cadastrados depois não são adicionados automaticamente.
- Desativar usuário não remove linhas de votações existentes.
- Ao abrir, `eligible_frozen_at` é preenchido; a lista não muda mais.
- Usuário desativado permanece na lista congelada e conta como não votante; não
  consegue autenticar.

## 8. Snapshots da votação

Criados na transação de abertura, depois das validações e antes de `status='open'`.
São imutáveis.

### 8.1 `voting.VotingCharacterSnapshot`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `voting_id` | FK Voting | `ON DELETE PROTECT` |
| `source_character_id` | FK Character | `ON DELETE PROTECT` |
| `stable_id` | SlugField(120) | Cópia do identificador |
| `display_name` | CharField(150) | Cópia do nome no momento da abertura |
| `image_asset_id` | FK ImageAsset | Nullable; `ON DELETE PROTECT` |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (voting_id, source_character_id)`.
- `UNIQUE (voting_id, stable_id)`.
- `image_asset_id` aponta para o asset exato usado na abertura; se não havia imagem
  válida, fica null e a interface usa placeholder.
- Sem UPDATE/DELETE; INSERT apenas durante a abertura.

### 8.2 `voting.VotingVersionSnapshot`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `character_snapshot_id` | FK VotingCharacterSnapshot | `ON DELETE CASCADE` |
| `source_version_id` | FK CharacterVersion | `ON DELETE PROTECT` |
| `stable_id` | SlugField(150) | Cópia |
| `release_date_global` | DateField | Cópia |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (character_snapshot_id, source_version_id)`.
- Somente versões com `release_date_global <= cutoff` são copiadas.
- Sem UPDATE/DELETE.

### 8.3 `voting.VotingVersionAptitudeSnapshot`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `version_snapshot_id` | FK VotingVersionSnapshot | `ON DELETE CASCADE` |
| `aptitude_id` | FK Aptitude | `ON DELETE PROTECT` |

**Regras**:

- `UNIQUE (version_snapshot_id, aptitude_id)`.
- Preserva as aptidões por versão, permitindo o filtro "mesma versão" de forma
  reproduzível.
- A visão consolidada da personagem é a união distinta das aptidões de suas versões.

### 8.4 Consulta de filtros

Dado um conjunto de filtros:

1. Dentro da mesma categoria, os valores são OR.
2. Entre categorias, os valores são AND.
3. Uma mesma versão precisa satisfazer todos os critérios de categorias diferentes.
4. A personagem aparece uma vez se qualquer versão satisfizer a combinação.

Implementação: filtrar `VotingVersionAptitudeSnapshot` pelos valores selecionados,
agrupar por `version_snapshot_id`, exigir `COUNT(DISTINCT category) = número de
categorias selecionadas`, depois `DISTINCT` nas personagens.

## 9. Cédulas

### 9.1 `voting.Ballot`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `voting_id` | FK Voting | `ON DELETE PROTECT` |
| `participant_id` | FK User | `ON DELETE PROTECT` |
| `created_at` | DateTimeField | Auto |

**Regras**:

- `UNIQUE (voting_id, participant_id)` — no máximo uma cédula.
- Índice em `participant_id`.
- Sem UPDATE.
- DELETE permitido apenas com votação `open` (exclusão administrativa) ou
  `cancelled` (limpeza do cancelamento).
- Inserção apenas com votação `open` e, quando `close_mode='automatic'`,
  `now() < closes_at`.
- A cédula é definitiva para o participante; somente o administrador pode excluí-la
  enquanto a votação está aberta.

### 9.2 `voting.BallotChoice`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | BigAutoField | PK |
| `ballot_id` | FK Ballot | `ON DELETE CASCADE` |
| `character_snapshot_id` | FK VotingCharacterSnapshot | `ON DELETE PROTECT` |

**Regras**:

- `UNIQUE (ballot_id, character_snapshot_id)` — sem duplicidade.
- `character_snapshot_id` deve pertencer à mesma votação da cédula (trigger).
- A quantidade deve ser exatamente `voting.choices_count` (constraint trigger diferido).
- INSERT apenas com votação `open` e, quando `close_mode='automatic'`, antes de
  `closes_at`; DELETE apenas em exclusão administrativa da cédula (open) ou cancelamento
  (cancelled). Não há exclusão individual de escolha na aplicação.
- Sem UPDATE.

## 10. Agregações e privacidade

### 10.1 Resultados agregados

```text
BallotChoice
  JOIN Ballot ON ballot_id
  JOIN VotingCharacterSnapshot ON character_snapshot_id
  WHERE Ballot.voting_id = :voting
  GROUP BY character_snapshot_id
  COUNT(*) AS votes
```

- Para administradores: permitido com votação `open` ou `closed`.
- Para participantes: somente com votação `closed`; nunca `open`.
- Ranking final: somente `votes > 0`, ordenado por `votes DESC`, usando `DENSE_RANK()`
  para posições `1, 2, 2, 3, 3`.
- Votação `cancelled`: sem resultado oficial.

### 10.2 Participação

```text
VotingEligibility
  LEFT JOIN Ballot ON (voting_id, user_id)
  WHERE voting_id = :voting
```

Retorna `username` e `voted` (boolean), sem qualquer escolha. Permitido a
administradores.

### 10.3 Regras de privacidade

- Nenhuma view administrativa carrega `BallotChoice` ou `Ballot` com `prefetch` de
  escolhas.
- Exclusão administrativa recebe `voting_id` + `participant_id`; localiza a cédula e a
  apaga sem ler as escolhas.
- Logs de aplicação não incluem escolhas, corpo do POST de confirmação ou dumps de
  cédulas.
- Não registrar `Ballot`/`BallotChoice` no Django Admin; o admin customizado é o único
  caminho.
- Backups e acesso direto ao banco são restritos a operadores confiáveis; isso é uma
  limitação operacional documentada.
- A UI administrativa não deve exibir diferenças de agregados antes/depois da exclusão; a
  exclusão ocorre em fluxo dedicado. O risco residual de inferência é aceito na emenda 2.0.0.
- Testes automatizados verificam que páginas administrativas não exibem associações
  participante–personagem.

## 11. Transições de estado

| De | Para | Condição | Efeito |
|---|---|---|---|
| `draft` | `scheduled` | `open_mode=automatic`, `opens_at` futuro, pré-condições válidas | Congela configuração; aguarda scheduler |
| `draft` | `open` | Ação administrativa, `open_mode=manual`, ≥1 elegível, catálogo suficiente | Congela elegíveis e catálogo; cria snapshots |
| `draft` | `cancelled` | Ação administrativa | Sem cédulas; histórico admin |
| `scheduled` | `open` | `opens_at <= now`, scheduler, `open_mode=automatic`, pré-condições válidas | Congela e abre |
| `scheduled` | `cancelled` | Ação administrativa ou falha de pré-condição no scheduler | Cancela sem cédulas |
| `open` | `closed` | Ação administrativa ou `closes_at <= now` com `close_mode=automatic` | Bloqueia novas cédulas; mantém dados |
| `open` | `cancelled` | Ação administrativa | Define `cancelled` e apaga todas as cédulas |
| `closed` | `cancelled` | Ação administrativa | Define `cancelled` e apaga todas as cédulas |
| `cancelled` | — | Terminal | Não aceita transições |

**Observações**:

- `scheduled` é bloqueada para edição, inclusive elegíveis.
- Exclusão individual de cédula só em `open`; cancelamento é a única operação que apaga
  cédulas de votação encerrada.
- A trigger de transição rejeita qualquer transição fora da tabela.

## 12. Invariantes no banco

| Invariante | Mecanismo |
|---|---|
| Username único case-insensitive | `UNIQUE (LOWER(username))` |
| Uma cédula por participante/votação | `UNIQUE (voting_id, participant_id)` |
| Cédula só de participante elegível | Trigger `ballot_eligible_participant` |
| Sem escolhas duplicadas | `UNIQUE (ballot_id, character_snapshot_id)` |
| Escolha pertence à votação da cédula | Trigger `ballot_choice_same_voting` |
| Quantidade exata de escolhas | Constraint trigger diferido `ballot_choice_count` |
| Cédula só em votação aberta e antes do encerramento | Trigger `ballot_insert_open` |
| Cédula imutável | Trigger `ballot_no_update` |
| Exclusão individual só aberta | Trigger `ballot_delete_window` + `ballot_choice_delete_window` |
| Elegibilidade só editável em rascunho | Trigger `eligibility_draft_only` |
| Snapshots imutáveis | Triggers `snapshot_no_update/delete` |
| Imagem do snapshot pertence à personagem | Trigger `snapshot_image_character` |
| Versão do snapshot pertence à personagem | Trigger `snapshot_version_character` |
| Configuração imutável após rascunho | Trigger `voting_config_immutable` |
| Transições permitidas | Trigger `voting_transition` |
| Uma imagem corrente por personagem | Unique parcial `image_current_unique` |
| Asset não apagado se referenciado | FKs `ON DELETE PROTECT` |
| Snapshot de imagem exato | `VotingCharacterSnapshot.image_asset_id` |
| Votação nunca apagada | FKs `ON DELETE PROTECT` |

### 12.1 Triggers de cédula

- `ballot_insert_open`: BEFORE INSERT em `voting_ballot`; exige votação `open` e, quando
  `close_mode='automatic'`, `now() < closes_at`.
- `ballot_eligible_participant`: BEFORE INSERT em `voting_ballot`; exige linha
  correspondente em `voting_votingeligibility` para `(voting_id, participant_id)`.
- `ballot_no_update`: BEFORE UPDATE em `voting_ballot`; rejeita sempre.
- `ballot_delete_window`: BEFORE DELETE em `voting_ballot`; permite se a votação está
  `open` (exclusão administrativa) ou `cancelled` (limpeza); seta a variável local
  `app.ballot_delete='on'` para autorizar a cascata.
- `ballot_choice_insert_open`: BEFORE INSERT em `voting_ballotchoice`; valida votação
  aberta, horário (quando automático) e mesma votação do snapshot.
- `ballot_choice_no_update`: BEFORE UPDATE em `voting_ballotchoice`; rejeita sempre.
- `ballot_choice_delete_window`: BEFORE DELETE em `voting_ballotchoice`; permite se
  `app.ballot_delete='on'` (cascata de exclusão da cédula) ou votação `cancelled`;
  rejeita exclusão individual de escolha.
- `ballot_choice_count`: CONSTRAINT TRIGGER AFTER INSERT OR UPDATE OR DELETE em
  `voting_ballotchoice`, DEFERRABLE INITIALLY DEFERRED; no commit, para cada cédula
  ainda existente, exige `COUNT(*) = voting.choices_count`. Se a cédula foi apagada, não
  valida.

### 12.2 Triggers de votação e snapshot

- `voting_transition`: BEFORE UPDATE em `voting_voting`; compara `OLD.status` e
  `NEW.status` e rejeita transições não permitidas.
- `voting_config_immutable`: BEFORE UPDATE em `voting_voting`; se `OLD.status <> 'draft'`,
  rejeita alteração de título, descrição, `choices_count`, cutoff, datas, modos e
  `created_by_id`.
- `eligibility_draft_only`: BEFORE INSERT/UPDATE/DELETE em
  `voting_votingeligibility`; exige votação em `draft`.
- `snapshot_no_update/delete`: BEFORE UPDATE/DELETE nas três tabelas de snapshot;
  rejeita sempre.
- `snapshot_insert_window`: BEFORE INSERT nas tabelas de snapshot; exige votação em
  `draft` ou `scheduled` (a abertura ocorre antes de `status='open'`).
- `snapshot_image_character`: BEFORE INSERT/UPDATE em `voting_votingcharactersnapshot`;
  se `image_asset_id` não for nulo, exige que o asset pertença a `source_character_id`.
- `snapshot_version_character`: BEFORE INSERT em `voting_votingversionsnapshot`; exige que
  `source_version.character_id` seja o `source_character_id` do snapshot pai.

### 12.3 Imagens

- `image_current_unique`: partial unique index em `(character_id) WHERE is_current`.
- `image_file_path_unique`: unique em `file_path`.
- `image_status_check`: `status IN ('valid','invalid','missing')`.
- `image_dimensions_check`: `width > 0 AND height > 0`.
- A validação de existência no disco é feita por comando; o runtime usa o status e um
  fallback visual.

## 13. Índices recomendados

- `accounts_user`: unique funcional em `LOWER(username)`.
- `voting_voting`: `(status, opens_at)`, `(status, closes_at)`.
- `voting_votingeligibility`: unique `(voting_id, user_id)`, índice `user_id`.
- `voting_votingcharactersnapshot`: unique `(voting_id, source_character_id)`, unique
  `(voting_id, stable_id)`, índice `(voting_id, display_name)`.
- `voting_votingversionsnapshot`: unique `(character_snapshot_id, source_version_id)`.
- `voting_votingversionaptitudesnapshot`: unique `(version_snapshot_id, aptitude_id)`.
- `voting_ballot`: unique `(voting_id, participant_id)`, índice `participant_id`.
- `voting_ballotchoice`: unique `(ballot_id, character_snapshot_id)`, índice
  `character_snapshot_id`.
- `catalog_character`: unique `stable_id`, índice `display_name`.
- `catalog_characterversion`: unique `stable_id`, unique
  `(character_id, stable_id)`, índice `(character_id, release_date_global)`.
- `catalog_characterversionaptitude`: unique `(version_id, aptitude_id)`, índice
  `aptitude_id`.
- `catalog_imageasset`: unique `file_path`, partial unique
  `(character_id) WHERE is_current`, índice `checksum_sha256`.
- `catalog_syncrun`: índice `(status, started_at)`.
- `catalog_syncchange`: índice `(status, created_at)`.

## 14. Retenção e histórico

- Votações nunca são apagadas; canceladas permanecem no histórico administrativo.
- Cédulas de votação cancelada são apagadas definitivamente.
- Cédulas de votação encerrada permanecem para resultados e consulta do participante.
- Snapshots permanecem enquanto a votação existir.
- Assets de imagem antigos permanecem enquanto referenciados por snapshots.
- Sincronizações e aprovações permanecem no histórico.
- Sessões expiradas são limpas periodicamente.
- Backups incluem banco e `media/`.

## 15. Dados iniciais

- `Aptitude`: 4 estratégias + 4 distâncias + 2 superfícies, criadas por data migration.
- `CatalogSource`: `curadoria-local` (file/manual) e, se habilitado, `gametora`/`umapyoi`.
- Nenhum usuário, personagem, imagem ou votação de exemplo em produção.
- Ambiente de desenvolvimento pode usar `seed_demo` explicitamente, nunca em produção.
