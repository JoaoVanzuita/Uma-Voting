# Feature Specification: Uma Voting — Votações de Banimento de Personagens

**Feature Branch**: `001-character-ban-voting`

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "Aplicação web para organizar votações de banimento de personagens de Umamusume: Pretty Derby em uma comunidade fechada, com administradores que gerenciam participantes, catálogo, imagens e votações, e participantes elegíveis que acessam por username e confirmam uma cédula definitiva."

## Clarifications

### Session 2026-11-07

- Q: O que deve acontecer quando chega o horário de abertura automática de uma votação agendada, mas ela está sem participantes elegíveis? → A: A votação é cancelada automaticamente, sem cédulas, e permanece apenas no histórico administrativo.
- Q: Se o sistema ficar indisponível e perder o horário de abertura ou encerramento automático, o que deve acontecer quando voltar a operar? → A: Se a votação nunca foi aberta e toda a janela passou, é cancelada automaticamente sem cédulas. Se já estava aberta, o encerramento atrasado é aplicado ao recuperar, preservando as cédulas existentes.
- Q: Quando o participante combina filtros de categorias diferentes, como a personagem deve ser considerada? → A: Dentro da mesma categoria, vale qualquer valor selecionado (OU); entre categorias, uma mesma versão precisa atender a todos os valores (E); a personagem aparece uma vez se qualquer versão satisfizer a combinação.
- Q: Na tela de resultado final, quais personagens devem ser listadas? → A: Somente personagens com pelo menos 1 voto; empates entre votados são todos exibidos e, sem votos, o resultado fica vazio.
- Q: Se a data de corte deixar menos personagens elegíveis do que a quantidade de escolhas exigida, a votação pode abrir? → A: Não. A abertura manual é bloqueada; a automática é cancelada, como na ausência de elegíveis.
- Q: As datas de abertura e encerramento são obrigatórias em todos os modos? → A: São obrigatórias nos modos automáticos; nos modos manuais, são informativas e podem ser omitidas.
- Q: Qual deve ser a data de corte padrão ao criar uma votação? → A: A data atual no momento da criação; o administrador pode alterá-la manualmente.
- Q: O administrador que vota como participante pode consultar a própria cédula? → A: Sim, somente pela rota de participante; nenhuma visão administrativa expõe escolhas, inclusive as do próprio administrador.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Acessar o sistema conforme o perfil (Priority: P1)

Um administrador entra com username e senha e chega à área administrativa. Um participante
informa apenas o username e chega à experiência de participante. Ambos conseguem encerrar a
sessão, e a sessão termina quando o navegador é fechado.

**Why this priority**: sem acesso confiável e distinção correta de permissões, nenhum outro fluxo
do sistema pode funcionar com segurança.

**Independent Test**: cadastrar um administrador e um participante ativo, autenticar cada perfil,
verificar as áreas permitidas e encerrar a sessão.

**Acceptance Scenarios**:

1. **Given** um administrador cadastrado, **When** informa username e senha corretos, **Then**
   acessa a área administrativa.
2. **Given** um participante ativo, **When** informa um username existente, **Then** acessa a
   experiência de participante com as votações para as quais é elegível.
3. **Given** um username inexistente, **When** tenta acessar, **Then** o acesso é negado com
   mensagem compreensível e nenhuma sessão é criada.
4. **Given** um administrador autenticado, **When** alterna para a experiência de participante,
   **Then** passa a navegar como participante, pode votar com contagem normal, consulta somente
   a própria cédula e pode retornar à área administrativa.
5. **Given** um usuário autenticado, **When** seleciona logout, **Then** a sessão é encerrada e o
   acesso às áreas restritas é bloqueado.
6. **Given** uma sessão ativa, **When** o navegador é fechado e reaberto, **Then** o usuário deve
   se autenticar novamente.
7. **Given** a página de login de participante, **When** ela é exibida, **Then** mostra o aviso de
   que o username identifica o cadastro, mas não comprova a identidade da pessoa.

---

### User Story 2 - Votar em uma votação aberta (Priority: P1)

Um participante elegível acessa uma votação aberta, encontra personagens por cards, busca e
filtros, seleciona exatamente a quantidade de escolhas permitida, revisa a cédula, recebe o aviso
de que ela é definitiva e confirma o envio. Depois, pode consultar a própria cédula sem alterá-la.

**Why this priority**: é o fluxo central do produto; sem ele, a votação não existe.

**Independent Test**: abrir uma votação com catálogo congelado, entrar como participante elegível,
selecionar as escolhas, confirmar e verificar que a cédula foi registrada e não pode ser alterada.

**Acceptance Scenarios**:

1. **Given** um participante elegível e uma votação aberta, **When** acessa a votação, **Then**
   vê os cards das personagens com imagem ou placeholder, nome e filtros disponíveis.
2. **Given** a tela de seleção, **When** digita parte do nome ou combina filtros, **Then** a lista
   é atualizada e cada personagem canônica aparece no máximo uma vez.
3. **Given** a quantidade configurada de escolhas, **When** seleciona personagens distintas e
   tenta adicionar uma duplicada, **Then** a duplicidade é impedida.
4. **Given** escolhas válidas, **When** avança para a revisão, **Then** vê todas as escolhas, o
   limite configurado e o aviso de que a cédula é definitiva.
5. **Given** a revisão, **When** confirma o envio, **Then** recebe feedback de sucesso e a cédula
   passa a constar como respondida.
6. **Given** uma cédula já confirmada, **When** tenta enviar outra, **Then** o sistema impede novo
   envio e permite apenas consultar a cédula existente.
7. **Given** uma votação aberta, **When** o participante consulta a própria cédula, **Then** vê
   suas escolhas, mas não vê resultados parciais.

---

### User Story 3 - Administrar participantes (Priority: P2)

Um administrador cadastra, pesquisa, edita, desativa e importa participantes por CSV, mantendo
usernames únicos e sem diferenciar maiúsculas de minúsculas.

**Why this priority**: a elegibilidade das votações depende de uma base de participantes correta.

**Independent Test**: cadastrar participantes individualmente e por CSV, pesquisar, editar,
desativar e verificar a inclusão automática em uma nova votação.

**Acceptance Scenarios**:

1. **Given** a área de participantes, **When** o administrador cadastra um username inédito,
   **Then** o participante é criado ativo.
2. **Given** um username já existente, **When** o administrador tenta cadastrá-lo com outra
   combinação de maiúsculas e minúsculas, **Then** o cadastro é rejeitado com mensagem clara.
3. **Given** participantes cadastrados, **When** o administrador pesquisa por parte do username,
   **Then** os resultados correspondentes são listados.
4. **Given** um participante ativo, **When** o administrador o desativa, **Then** ele deixa de
   acessar o sistema e de ser incluído em novas votações, sem alterar votações já abertas ou
   encerradas.
5. **Given** um arquivo CSV com inconsistências, **When** o administrador tenta importar, **Then**
   o sistema apresenta as inconsistências por linha e não importa parcialmente os dados.
6. **Given** uma votação em rascunho, **When** o administrador adiciona ou remove elegíveis,
   **Then** a lista é atualizada enquanto a votação permanecer em rascunho.

---

### User Story 4 - Manter o catálogo e as imagens (Priority: P2)

Um administrador acompanha a sincronização do catálogo, visualiza prévias de mudanças, aprova
alterações em personagens existentes, importa dados de contingência e identifica personagens com
imagem ausente ou inválida.

**Why this priority**: a votação só é justa se o catálogo e as imagens representarem corretamente
as personagens elegíveis.

**Independent Test**: executar uma sincronização que adicione uma personagem e altere outra,
verificar a prévia, aprovar a alteração e confirmar que apenas novas votações são afetadas.

**Acceptance Scenarios**:

1. **Given** uma sincronização com uma personagem nova e elegível, **When** a prévia é aplicada,
   **Then** a personagem é adicionada ao catálogo.
2. **Given** uma sincronização que altera dados de uma personagem existente, **When** a prévia é
   exibida, **Then** a alteração fica pendente de aprovação administrativa.
3. **Given** uma alteração pendente, **When** o administrador aprova, **Then** o catálogo é
   atualizado sem modificar snapshots de votações existentes.
4. **Given** uma personagem sem imagem ou com imagem inválida, **When** o administrador consulta o
   catálogo, **Then** consegue identificá-la e vê o placeholder correspondente na interface.
5. **Given** uma importação de contingência com inconsistências, **When** o administrador a
   executa, **Then** vê a prévia e as inconsistências antes de confirmar.
6. **Given** uma imagem válida já associada, **When** uma sincronização de dados é executada,
   **Then** a imagem não é substituída automaticamente sem validação.

---

### User Story 5 - Criar e configurar votações (Priority: P2)

Um administrador cria uma votação com título, descrição, quantidade de escolhas, elegíveis, data
de corte do catálogo, datas, modos de abertura e encerramento.

**Why this priority**: é a etapa que prepara qualquer votação futura e define as regras que serão
congeladas na abertura.

**Independent Test**: criar uma votação em rascunho, configurar os campos, ajustar elegíveis e
verificar as validações de abertura.

**Acceptance Scenarios**:

1. **Given** a área de votações, **When** o administrador cria uma votação sem informar a
   quantidade de escolhas, **Then** o padrão de três escolhas é aplicado.
2. **Given** uma votação em rascunho, **When** o administrador configura título, descrição, data
   de corte, datas e modos de abertura e encerramento, **Then** as configurações são salvas,
   sendo as datas obrigatórias nos modos automáticos e informativas nos modos manuais.
3. **Given** uma votação sem participantes elegíveis ou com personagens insuficientes para a
   quantidade de escolhas, **When** o administrador tenta abri-la, **Then** a abertura é bloqueada
   com explicação.
4. **Given** uma votação com abertura automática configurada, **When** o administrador escolhe
   "Salvar e agendar", **Then** a votação é criada e passa ao estado agendada em uma única ação e
   fica bloqueada para edição. Se as pré-condições não forem atendidas, permanece em rascunho com
   as pendências exibidas.
5. **Given** uma votação já aberta, **When** o administrador tenta alterar suas configurações,
   **Then** a alteração é bloqueada.

---

### User Story 6 - Operar o ciclo de vida da votação (Priority: P3)

Um administrador abre, acompanha, encerra ou cancela votações. As transições automáticas ocorrem
nos horários configurados mesmo sem usuários conectados. Enquanto a votação está aberta, o
administrador pode excluir cédulas.

**Why this priority**: o ciclo de vida garante que as regras congeladas na abertura sejam mantidas
até o encerramento e que cancelamentos não deixem dados residuais.

**Independent Test**: criar e abrir uma votação, excluir uma cédula, encerrar a votação e verificar
o bloqueio de novas exclusões; em paralelo, testar abertura e encerramento automáticos.

**Acceptance Scenarios**:

1. **Given** uma votação agendada, **When** chega o horário de abertura e ninguém está conectado,
   **Then** a votação é aberta e os elegíveis e o catálogo são congelados.
2. **Given** uma votação aberta, **When** chega o horário de encerramento e ninguém está
   conectado, **Then** a votação é encerrada e não aceita mais cédulas.
3. **Given** uma votação aberta, **When** o administrador exclui uma cédula, **Then** ela deixa de
   contar nos resultados e na participação, e o participante pode votar novamente.
4. **Given** uma votação aberta, **When** o administrador tenta excluir uma cédula após o
   encerramento, **Then** a exclusão é bloqueada.
5. **Given** uma votação em qualquer estado, **When** o administrador a cancela, **Then** todas as
   cédulas são eliminadas definitivamente, a votação permanece no histórico administrativo e não
   aparece para participantes.
6. **Given** duas transições concorrentes, **When** aberturas ou encerramentos simultâneos são
   solicitados, **Then** apenas uma transição válida é aplicada.
7. **Given** uma votação agendada sem participantes elegíveis ou com personagens insuficientes
   para a quantidade de escolhas, **When** chega o horário de abertura, **Then** a votação é
   cancelada automaticamente, sem cédulas, e permanece no histórico administrativo.
8. **Given** uma votação agendada cujo horário de abertura passou enquanto o sistema estava
   indisponível, **When** o sistema volta a operar antes do encerramento, **Then** a votação abre
   imediatamente.
9. **Given** uma votação agendada cuja janela inteira passou enquanto o sistema estava
   indisponível, **When** o sistema volta a operar, **Then** a votação é cancelada automaticamente,
   sem cédulas.

---

### User Story 7 - Consultar resultados e participação (Priority: P3)

Administradores acompanham resultados agregados e quem votou ou não votou durante a votação.
Participantes não veem resultados parciais e, após o encerramento, veem o resultado geral ordenado,
com todos os empates entre personagens com votos exibidos.

**Why this priority**: resultados confiáveis e privacidade das escolhas são a finalidade da
votação; porém dependem dos fluxos anteriores.

**Independent Test**: registrar cédulas, verificar os agregados administrativos, tentar acessar
resultados como participante durante a votação e conferir o ranking após o encerramento.

**Acceptance Scenarios**:

1. **Given** uma votação aberta com cédulas, **When** o administrador consulta os resultados,
   **Then** vê a contagem agregada por personagem, sem qualquer escolha individual.
2. **Given** uma votação aberta, **When** o administrador consulta a participação, **Then** vê
   quais elegíveis votaram e quais não votaram, incluindo administradores elegíveis, sem
   escolhas.
3. **Given** uma votação aberta, **When** o participante tenta consultar resultados, **Then** os
   resultados parciais não são exibidos.
4. **Given** uma votação encerrada, **When** um participante elegível consulta os resultados,
   **Then** vê o ranking geral com as posições e todos os empates entre personagens com votos.
5. **Given** personagens com a mesma quantidade de votos, **When** o ranking é apresentado,
   **Then** elas ocupam a mesma posição, sem critério adicional de desempate.
6. **Given** uma votação cancelada, **When** qualquer usuário consulta resultados, **Then** não há
   resultado oficial.

---

### User Story 8 - Consultar histórico e painel administrativo (Priority: P4)

Participantes encontram votações respondidas ou encerradas em uma área de histórico. O
administrador usa um painel com indicadores de participantes, votações e catálogo, votações em
andamento e atalhos.

**Why this priority**: complementa a experiência e facilita a operação, mas não é pré-requisito
para votar ou apurar.

**Independent Test**: acessar o painel administrativo, conferir os indicadores e votações em
andamento e verificar o histórico de um participante após responder e após o encerramento.

**Acceptance Scenarios**:

1. **Given** um administrador autenticado, **When** acessa o painel, **Then** vê total de
   participantes ativos, votações abertas e agendadas, mudanças de catálogo pendentes, imagens
   ausentes/inválidas, últimas votações e atalhos administrativos.
2. **Given** um participante que já votou, **When** acessa a área de histórico, **Then** encontra a
   votação respondida separada das votações disponíveis.
3. **Given** uma votação encerrada, **When** o participante elegível consulta o histórico, **Then**
   vê a votação e pode consultar a própria cédula e o resultado geral.
4. **Given** uma votação cancelada, **When** o administrador consulta o histórico administrativo,
   **Then** encontra a votação; **When** um participante consulta o histórico, **Then** não a
   encontra.

### Edge Cases

- Username inexistente, inativo ou com diferença apenas de maiúsculas/minúsculas.
- Participante desativado com sessão ativa: o acesso deve ser negado na próxima operação
  protegida, sem alterar votações já abertas ou encerradas.
- Votação sem elegíveis ou com personagens insuficientes para a quantidade de escolhas na abertura
  manual: a abertura é bloqueada. Na abertura automática: a votação é cancelada automaticamente,
  sem cédulas.
- Abertura e encerramento no mesmo instante ou com datas invertidas, quando informadas.
- Votação agendada cujo horário passa enquanto o sistema estava indisponível: se o encerramento
  ainda não passou, abre imediatamente; se toda a janela passou, é cancelada automaticamente, sem
  cédulas. Votação já aberta com encerramento perdido é encerrada imediatamente ao recuperar.
- Duas tentativas simultâneas de envio de cédula pelo mesmo participante.
- Cédula com quantidade diferente da configurada, personagem duplicada ou personagem fora do
  snapshot.
- Exclusão de cédula concorrente com o encerramento da votação.
- Cancelamento de votação aberta com cédulas já registradas.
- Tentativa de consultar cédula de outro participante ou de acessar votação sem elegibilidade.
- Personagem com múltiplas versões e aptidões diferentes; filtros que correspondem apenas a uma
  versão.
- Personagem lançada depois da data de corte, ou anunciada e não lançada até o corte.
- Catálogo atualizado após a abertura de uma votação.
- Imagem ausente, corrompida ou com proporção diferente da referência.
- Arquivo CSV vazio, com cabeçalho inválido, linhas duplicadas ou caracteres inesperados.
- Importação de catálogo com personagens novas e alterações simultâneas.
- Ranking com empates em todas as posições.
- Votação encerrada sem nenhuma cédula registrada.

## Requirements *(mandatory)*

### Functional Requirements

#### Acesso, autenticação e sessão

- **FR-001**: O sistema MUST autenticar administradores com username e senha.
- **FR-002**: O sistema MUST autenticar participantes informando somente o username, sem senha.
- **FR-003**: O sistema MUST negar acesso a username inexistente com mensagem compreensível,
  sem criar sessão.
- **FR-004**: O sistema MUST tratar usernames como únicos e sem diferenciação entre maiúsculas e
  minúsculas.
- **FR-005**: O sistema MUST exibir o username conforme cadastrado, usando a comparação
  normalizada apenas para unicidade e autenticação.
- **FR-006**: A sessão MUST permanecer ativa até o logout ou o fechamento do navegador.
- **FR-007**: O sistema MUST oferecer logout claro em todas as áreas autenticadas.
- **FR-008**: O sistema MUST NOT permitir cadastro público de participantes ou administradores.
- **FR-009**: O administrador MUST poder alternar explicitamente entre a área administrativa e a
  experiência de participante.
- **FR-010**: O sistema MUST verificar permissões no servidor em toda operação protegida.
- **FR-011**: O administrador MUST poder votar como participante, e seu voto MUST contar
  normalmente. No modo participante, ele MUST seguir as mesmas regras de privacidade do
  participante e MAY consultar somente a própria cédula.
- **FR-012**: O sistema MUST permitir que um participante acesse somente votações para as quais
  seja elegível.
- **FR-013**: A documentação e a interface MUST deixar explícito que a autenticação por username
  não comprova a identidade do participante e não constitui autenticação forte.
- **FR-014**: A interface MUST identificar participantes somente pelo username, sem expor outros
  dados pessoais.

#### Participantes

- **FR-015**: O administrador MUST poder cadastrar, listar, pesquisar, editar e desativar
  participantes.
- **FR-016**: O sistema MUST validar a unicidade case-insensitive do username no cadastro e na
  edição.
- **FR-017**: O sistema MUST permitir a importação de participantes por arquivo CSV.
- **FR-018**: A importação CSV MUST validar o arquivo e apresentar todas as inconsistências por
  linha, de forma compreensível.
- **FR-019**: A importação CSV MUST ser atômica: qualquer inconsistência MUST impedir a importação
  integral e MUST NOT deixar cadastros parciais.
- **FR-020**: Toda nova votação MUST incluir por padrão todos os participantes ativos existentes
  no momento de sua criação, incluindo administradores ativos que também podem votar.
- **FR-021**: Participantes cadastrados depois da criação de uma votação MUST NOT ser adicionados
  automaticamente a essa votação.
- **FR-022**: O administrador MUST poder adicionar ou remover participantes elegíveis enquanto a
  votação estiver em rascunho.
- **FR-023**: A lista de elegíveis MUST ser congelada na abertura da votação.
- **FR-024**: Desativar um participante MUST NOT alterar retroativamente votações já abertas ou
  encerradas.
- **FR-025**: Participante desativado MUST NOT conseguir autenticar nem ser incluído em novas
  votações.

#### Votações: configuração e estados

- **FR-026**: Cada votação MUST possuir título, descrição, quantidade de escolhas permitidas,
  participantes elegíveis, data de corte do catálogo, modo de abertura, modo de encerramento e
  estado. Data e hora de abertura e encerramento MUST ser obrigatórias quando o respectivo modo
  for automático e MAY ser informativas ou ausentes quando o modo for manual.
- **FR-027**: A quantidade padrão de escolhas por participante MUST ser três, configurável
  individualmente em cada votação.
- **FR-028**: A quantidade de escolhas MUST ser um número inteiro positivo compatível com o
  catálogo da votação.
- **FR-029**: O sistema MUST permitir múltiplas votações simultâneas.
- **FR-030**: Cada votação MUST estar em um dos estados: rascunho, agendada, aberta, encerrada ou
  cancelada.
- **FR-031**: O sistema MUST impedir a abertura de votação sem pelo menos um participante elegível
  e sem personagens elegíveis suficientes para a quantidade de escolhas configurada; na abertura
  automática, a votação MUST ser cancelada automaticamente nesses casos.
- **FR-032**: A votação agendada MUST ficar bloqueada para edição.
- **FR-033**: Na abertura, o sistema MUST congelar os participantes elegíveis e o catálogo de
  personagens aplicável à data de corte.
- **FR-034**: Depois de aberta, as configurações da votação MUST NOT ser alteradas.
- **FR-035**: O administrador MUST poder cancelar uma votação em qualquer estado.
- **FR-036**: O cancelamento MUST eliminar definitivamente todas as cédulas da votação.
- **FR-037**: Votações canceladas MUST permanecer no histórico administrativo.
- **FR-038**: Votações canceladas MUST NOT aparecer para participantes e MUST NOT possuir
  resultado oficial.
- **FR-039**: As transições de estado MUST ser consistentes e protegidas contra concorrência.
- **FR-040**: O sistema MUST validar datas de abertura e encerramento quando informadas,
  impedindo configurações inválidas.
- **FR-041**: O sistema MUST aplicar a data de corte do catálogo configurada em cada votação.
- **FR-042**: O modo de abertura manual MUST permitir que o administrador abra a votação
  explicitamente.
- **FR-043**: O modo de abertura automático MUST abrir a votação na data e hora configuradas
  quando houver ao menos um participante elegível e personagens elegíveis suficientes para a
  quantidade de escolhas; caso contrário, MUST cancelar a votação automaticamente, sem cédulas.
- **FR-044**: O modo de encerramento manual MUST permitir que o administrador encerre a votação
  explicitamente.
- **FR-045**: O modo de encerramento automático MUST encerrar a votação na data e hora
  configuradas.
- **FR-046**: As transições automáticas MUST ocorrer mesmo sem usuários conectados e MUST ser
  recuperadas ao retomar a operação: se a votação já estava aberta e o encerramento passou, MUST
  ser encerrada imediatamente; se a abertura atrasada ainda tiver janela, MUST abrir
  imediatamente; se toda a janela passou sem abertura, a votação MUST ser cancelada
  automaticamente, sem cédulas.

#### Experiência de votação

- **FR-047**: A página inicial do participante MUST exibir somente votações abertas e agendadas
  para as quais ele seja elegível.
- **FR-048**: Votações respondidas ou encerradas MUST ser exibidas em área separada de histórico.
- **FR-049**: Quando não houver votações disponíveis, a página inicial MUST exibir somente uma
  mensagem simples, sem destacar votações futuras.
- **FR-050**: A seleção de personagens MUST apresentar cards com imagem e nome.
- **FR-051**: A seleção MUST oferecer busca instantânea por nome.
- **FR-052**: A seleção MUST oferecer filtros combináveis por estratégia/posição, distância e
  superfície.
- **FR-053**: A interface MUST exibir contador de escolhas e o limite configurado.
- **FR-054**: A interface MUST indicar visualmente as personagens selecionadas.
- **FR-055**: O sistema MUST impedir a seleção da mesma personagem mais de uma vez.
- **FR-056**: Cada personagem canônica MUST aparecer no máximo uma vez, independentemente da
  quantidade de versões ou de filtros correspondentes.
- **FR-057**: Antes do envio, o participante MUST revisar todas as escolhas.
- **FR-058**: Antes da confirmação, o sistema MUST avisar explicitamente que a cédula será
  definitiva.
- **FR-059**: O envio MUST exigir confirmação explícita do participante.
- **FR-060**: Após a confirmação, o sistema MUST apresentar feedback de sucesso.
- **FR-061**: O participante MUST NOT poder alterar uma cédula confirmada.
- **FR-062**: O participante MUST poder consultar a própria cédula enquanto a votação estiver
  aberta e após o encerramento.
- **FR-063**: O sistema MUST NOT exibir resultados parciais a participantes.

#### Cédulas

- **FR-064**: Cada participante MUST possuir no máximo uma cédula por votação.
- **FR-065**: A cédula MUST conter exatamente a quantidade configurada de escolhas.
- **FR-066**: A cédula MUST NOT conter personagens duplicadas.
- **FR-067**: A validação da cédula MUST ocorrer no servidor.
- **FR-068**: A cédula MUST aceitar somente personagens presentes no snapshot da votação.
- **FR-069**: O sistema MUST aceitar cédulas somente enquanto a votação estiver aberta.
- **FR-070**: Administradores MUST NOT visualizar as escolhas individuais da cédula de outro
  participante em nenhuma visão administrativa. A cédula do próprio administrador, quando ele
  vota no modo participante, MUST ser acessível somente a ele pela rota de participante.
- **FR-071**: Enquanto a votação estiver aberta, o administrador MUST poder excluir cédulas.
- **FR-072**: Uma cédula excluída MUST deixar de contar nos resultados e na participação.
- **FR-073**: Após a exclusão da própria cédula, o participante MUST poder votar novamente.
- **FR-074**: O sistema MUST NOT notificar o participante sobre a exclusão administrativa de sua
  cédula.
- **FR-075**: O sistema MUST NOT manter registro administrativo específico de quem excluiu a
  cédula ou de quando ela foi excluída.
- **FR-076**: Após o encerramento, o sistema MUST bloquear a exclusão individual de cédulas. O
  cancelamento da votação, permitido em qualquer estado, elimina todas as cédulas e não produz
  resultado oficial.

#### Resultados

- **FR-077**: Durante a votação, administradores MUST ver resultados agregados.
- **FR-078**: Durante a votação, administradores MUST poder consultar quem votou e quem não votou.
- **FR-079**: Administradores MUST NOT consultar as escolhas individuais de outros participantes
  por meio de resultados, participação ou qualquer outra visão administrativa.
- **FR-080**: Participantes MUST NOT ver resultados parciais durante a votação.
- **FR-081**: Após o encerramento, participantes elegíveis MUST ver os resultados gerais.
- **FR-082**: Após o encerramento, o participante MUST continuar podendo consultar a própria
  cédula.
- **FR-083**: Os resultados MUST ser ordenados por quantidade de votos.
- **FR-084**: Personagens com a mesma quantidade de votos MUST ocupar a mesma posição.
- **FR-085**: Todos os personagens empatados com pelo menos um voto MUST ser exibidos;
  personagens sem votos MUST NOT ser listados no resultado final.
- **FR-086**: O sistema MUST NOT aplicar critério adicional de desempate.
- **FR-087**: Resultados MUST ser reproduzíveis a partir dos dados preservados.
- **FR-088**: Votações canceladas MUST NOT produzir resultado oficial para participantes.

#### Catálogo e sincronização

- **FR-089**: Cada personagem canônica MUST possuir identidade estável no catálogo.
- **FR-090**: Cada personagem canônica MUST representar uma única opção de votação.
- **FR-091**: Versões diferentes da mesma personagem MUST NOT ser opções independentes.
- **FR-092**: A referência principal de curadoria do catálogo MUST ser o GameTora. A importação
  de arquivo MUST ser o caminho operacional do MVP até que a viabilidade técnica e as condições de
  uso do GameTora sejam verificadas e autorizadas.
- **FR-093**: A data de corte padrão do catálogo MUST ser a data atual no momento da criação da
  votação, configurável por votação.
- **FR-094**: Somente personagens efetivamente lançadas no servidor Global até a data de corte
  MUST ser elegíveis.
- **FR-095**: Personagens anunciadas ou previstas, mas não lançadas até o corte, MUST ficar de
  fora.
- **FR-096**: Lançamentos posteriores ao corte MUST NOT entrar na votação correspondente.
- **FR-097**: As aptidões MUST ser consolidadas entre todas as versões lançadas no Global até a
  data de corte.
- **FR-098**: O catálogo MUST classificar estratégia/posição em Front, Pace, Late e End; distância
  em Sprint, Mile, Medium e Long; e superfície em Turf e Dirt.
- **FR-099**: Os filtros de aptidão MUST ser combináveis: dentro da mesma categoria, a seleção
  MUST funcionar como OU; entre categorias, MUST funcionar como E.
- **FR-100**: A personagem MUST aparecer quando ao menos uma versão elegível atender
  simultaneamente a todos os filtros de categorias diferentes, mas MUST aparecer somente uma vez.
- **FR-101**: A sincronização MUST seguir o modelo híbrido: novas personagens elegíveis podem ser
  adicionadas automaticamente, e alterações em personagens existentes MUST ficar pendentes de
  aprovação administrativa.
- **FR-102**: O sistema MUST permitir sincronização periódica e manual.
- **FR-103**: O sistema MUST apresentar prévia das mudanças antes da aplicação.
- **FR-104**: O sistema MUST manter histórico de sincronizações e aprovações.
- **FR-105**: O sistema MUST permitir importação de contingência com prévia e apresentação de
  inconsistências.
- **FR-106**: Correções de aptidões MUST afetar somente novas votações.
- **FR-107**: Cada votação MUST congelar uma cópia das personagens e aptidões elegíveis no momento
  da abertura.
- **FR-108**: Atualizações posteriores do catálogo MUST NOT alterar votações existentes.

#### Imagens das personagens

- **FR-109**: Cada personagem canônica MUST possuir uma única imagem principal associada,
  independentemente da quantidade de versões.
- **FR-110**: A aplicação MUST armazenar as imagens localmente.
- **FR-111**: As imagens MUST ser organizadas em diretório próprio, separadas dos dados do
  catálogo e dos snapshots.
- **FR-112**: A aplicação MUST NOT depender de sites externos para exibir imagens durante a
  utilização normal.
- **FR-113**: A ausência de imagem MUST NOT impedir a utilização da personagem.
- **FR-114**: O sistema MUST exibir um placeholder padronizado para imagens ausentes ou inválidas.
- **FR-115**: Cada imagem MUST estar inequivocamente associada à personagem canônica correta.
- **FR-116**: A viabilidade técnica, as condições de uso e a autorização de redistribuição das
  fontes de imagem MUST ser verificadas antes do uso.
- **FR-117**: A disponibilidade pública de uma imagem MUST NOT ser tratada como autorização
  automática para redistribuição.
- **FR-118**: O sistema MUST preferir o formato WebP para as imagens locais.
- **FR-119**: A nomenclatura dos arquivos MUST usar identificador estável da personagem e MUST NOT
  usar o nome traduzido como identificador.
- **FR-120**: A imagem MUST ser associada à personagem canônica, não às versões.
- **FR-121**: O administrador MUST poder identificar personagens sem imagem ou com imagem
  inválida.
- **FR-122**: As imagens MUST seguir dimensões e proporções consistentes, com referência inicial
  de 256 × 256 pixels.
- **FR-123**: As imagens MUST NOT ser distorcidas; o enquadramento e o preenchimento MUST seguir
  regras consistentes.
- **FR-124**: Atualizações e substituições de imagem MUST ser controladas e validadas.
- **FR-125**: A sincronização de dados MUST NOT substituir automaticamente imagens válidas sem
  validação.
- **FR-126**: Cada votação MUST preservar a referência da imagem utilizada por cada personagem no
  momento da abertura.
- **FR-127**: Alterações futuras do catálogo MUST NOT modificar a apresentação histórica de
  votações existentes.
- **FR-128**: Arquivos de imagem antigos MUST NOT ser removidos enquanto snapshots dependerem
  deles.

#### Administração

- **FR-129**: O painel administrativo MUST apresentar: total de participantes ativos, votações
  abertas, votações agendadas, mudanças de catálogo pendentes, imagens ausentes ou inválidas e as
  últimas votações.
- **FR-130**: A área de participantes MUST oferecer listagem, pesquisa, cadastro, edição,
  desativação e importação CSV.
- **FR-131**: A área de catálogo MUST oferecer estado da sincronização, data da última
  sincronização, sincronização manual, importação de contingência, prévia de mudanças, aprovação
  de alterações, consulta de personagens e aptidões, estado das imagens e identificação de imagens
  ausentes ou inválidas.
- **FR-132**: A área de votações MUST oferecer criação e configuração, gerenciamento de elegíveis,
  agendamento, abertura, encerramento, acompanhamento de agregados, consulta de participação,
  exclusão de cédulas enquanto aberta e cancelamento.

#### Requisitos não funcionais

- **FR-133**: A interface MUST estar em português brasileiro.
- **FR-134**: A interface MUST ser responsiva em desktop, tablet e mobile.
- **FR-135**: O fuso horário padrão MUST ser `America/Sao_Paulo`.
- **FR-136**: O sistema MUST preservar a integridade dos dados em todas as operações.
- **FR-137**: As transições automáticas MUST ocorrer independentemente do navegador ou de usuários
  conectados.
- **FR-138**: A segurança MUST ser proporcional ao contexto de comunidade fechada.
- **FR-139**: A aplicação MUST utilizar imagens locais, sem dependência externa em tempo de
  execução.
- **FR-140**: O sistema MUST preservar historicamente catálogo, aptidões e referências de imagens.
- **FR-141**: A acessibilidade MUST ser tratada como objetivo de qualidade desde o início.
- **FR-142**: A interface MUST apresentar estados claros de carregamento, erro, sucesso e ausência
  de conteúdo.
- **FR-143**: A busca e os filtros de personagens MUST responder de forma imediata à interação do
  usuário.

### Key Entities

- **Administrador**: usuário com credenciais próprias e permissões administrativas; também pode
  participar de votações como participante. Quando vota, sua cédula é privada e acessível
  somente a ele pela experiência de participante.
- **Participante**: pessoa cadastrada por um administrador, identificada por username único e
  case-insensitive, com estado ativo ou desativado.
- **Sessão**: período autenticado de um usuário, encerrado por logout ou fechamento do navegador.
- **Personagem canônica**: identidade estável que representa uma única opção de votação.
- **Versão de personagem**: lançamento específico de uma personagem, com data de lançamento no
  servidor Global e aptidões próprias; não é uma opção separada.
- **Aptidão**: categoria de estratégia/posição, distância ou superfície associada a uma versão e
  consolidada para a personagem canônica.
- **Imagem principal**: imagem única associada a uma personagem canônica, armazenada localmente,
  com estado válido, ausente ou inválido.
- **Votação**: evento com título, descrição, quantidade de escolhas, elegíveis, data de corte,
  datas quando aplicáveis, modos de abertura e encerramento e estado.
- **Snapshot de elegibilidade**: conjunto imutável de participantes elegíveis congelado na abertura.
- **Snapshot de catálogo**: cópia imutável das personagens, aptidões e referências de imagens
  congelada na abertura.
- **Cédula**: registro único de um participante em uma votação, com exatamente a quantidade
  configurada de escolhas distintas; definitiva após confirmação.
- **Escolha da cédula**: personagem canônica selecionada em uma cédula.
- **Sincronização/importação**: execução de atualização do catálogo, com origem, prévia, mudanças
  pendentes, aprovações e inconsistências.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um administrador consegue criar, configurar e agendar uma votação completa em menos
  de 5 minutos.
- **SC-002**: Um participante elegível consegue concluir uma cédula em menos de 3 minutos.
- **SC-003**: 100% das cédulas inválidas — quantidade incorreta, personagem duplicada, personagem
  fora do snapshot, votação encerrada ou segundo envio — são rejeitadas pelo sistema.
- **SC-004**: Aberturas e encerramentos automáticos ocorrem dentro de 1 minuto do horário
  configurado, mesmo sem usuários conectados.
- **SC-005**: Nenhum administrador consegue obter as escolhas individuais de uma cédula por
  qualquer tela, relatório ou consulta de participação.
- **SC-006**: 100% dos resultados podem ser recalculados de forma idêntica a partir dos dados
  preservados.
- **SC-007**: Atualizações de catálogo, aptidões ou imagens produzem zero alterações na
  apresentação histórica de votações existentes.
- **SC-008**: 100% das personagens exibem imagem ou placeholder, com zero requisições a serviços
  externos de imagem durante o uso normal.
- **SC-009**: 100% das inconsistências de um arquivo CSV são identificadas por linha com mensagem
  compreensível, e nenhum cadastro parcial é criado.
- **SC-010**: A busca por nome e a combinação de filtros apresentam resultados em menos de 1
  segundo para um catálogo de até 500 personagens canônicas.
- **SC-011**: Todas as telas permanecem utilizáveis em larguras de 360 px até desktop.
- **SC-012**: Todas as telas estão em português brasileiro e permitem navegação por teclado com
  foco visível.

## Assumptions

- O sistema atende uma única comunidade fechada, com cerca de 100 participantes ativos, até 500
  personagens canônicas e até 5 votações simultâneas.
- Contas de administrador são provisionadas previamente pelos mantenedores do projeto; não há
  cadastro público.
- A autenticação de participantes por username é uma limitação consciente: comprova apenas que o
  username existe, não a identidade da pessoa. Administradores usam senha.
- A sessão é encerrada quando o navegador é fechado, conforme o comportamento de sessão de
  navegador, ou por logout explícito.
- A importação CSV é atômica: qualquer linha inválida impede a importação integral e todas as
  inconsistências são apresentadas para correção.
- A cédula deve conter exatamente a quantidade configurada de escolhas, não uma quantidade menor.
- Resultados gerais após o encerramento ficam disponíveis aos participantes elegíveis para aquela
  votação.
- Votações canceladas aparecem somente no histórico administrativo e não possuem resultado
  oficial.
- A ordenação com empates segue a posição densa (dense rank): `1º, 2º, 2º, 3º, 3º`, sem
  desempate.
- O resultado final lista somente personagens com pelo menos um voto; personagens sem votos não
  aparecem e, se não houver votos, o resultado é vazio.
- A exclusão administrativa de cédula não gera notificação nem registro de autoria ou horário,
  por decisão de escopo. A exclusão e o novo envio são uma exceção aprovada à regra de cédula
  definitiva; a interface não exibe diferenças de agregados antes/depois da exclusão.
- O administrador que vota como participante tem uma cédula privada, acessível somente a ele pela
  experiência de participante; nenhuma visão administrativa expõe escolhas, inclusive as do
  próprio administrador.
- O GameTora é a referência principal de curadoria; a importação de arquivo é o caminho
  operacional do MVP. A automação do GameTora fica condicionada à verificação de viabilidade
  técnica, condições de uso e autorização. Caso nenhuma fonte seja viável, o catálogo pode ser
  mantido administrativamente.
- A verificação de autorização de uso das imagens é manual no MVP. O sistema registra origem e
  nota de licença, mas não bloqueia tecnicamente a importação; a aplicação do manifesto depende de
  revisão e aprovação administrativa registrada.
- A referência inicial de padronização das imagens é 256 × 256 pixels, sem distorção.
- Datas e horários são operados e apresentados no fuso `America/Sao_Paulo`.
- As datas de abertura e encerramento são obrigatórias quando o respectivo modo é automático;
  nos modos manuais, são informativas e podem ser omitidas.
- Não há requisito de notificações por e-mail, push ou mensagens externas.
- Na abertura manual, a votação permanece em rascunho até a ação do administrador; na abertura
  automática, passa ao estado agendada e abre no horário configurado.
- Na abertura automática sem participantes elegíveis ou sem personagens suficientes para a
  quantidade de escolhas, a votação é cancelada automaticamente, sem cédulas, e permanece somente
  no histórico administrativo.
- Se o sistema ficar indisponível durante uma janela agendada, a abertura é recuperada quando
  ainda houver tempo até o encerramento; se toda a janela tiver passado, a votação é cancelada
  automaticamente, sem cédulas. Se a votação já estava aberta, o encerramento atrasado é aplicado
  ao recuperar, sem cancelar as cédulas existentes.
- Filtros de categorias diferentes são combinados com E e exigem uma mesma versão que atenda a
  todos os critérios; dentro da mesma categoria, a combinação é OU.
- A votação encerrada sem cédulas apresenta resultado vazio, sem erro.
