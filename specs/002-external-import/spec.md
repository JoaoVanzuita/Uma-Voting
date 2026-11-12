# Feature Specification: Importação de Catálogo e Imagens de Fontes Externas

**Feature Branch**: `002-external-import`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Quero que exista um fluxo para importar catálogo e imagens de fontes externas diretamente na interface, sem importar arquivos. Defina o que seria necessário para isso."

## Clarifications

### Session 2026-11-12

- Q: A importação deve ser síncrona ou assíncrona? → A: Assíncrona desde o início, com acompanhamento de progresso na interface.
- Q: O GameTora entra no escopo? → A: Sim. O GameTora é dependência do conector da fonte Global, usado para datas de lançamento e aptidões.
- Q: As imagens devem ser baixadas automaticamente? → A: Sim. O sistema baixa, valida e normaliza as imagens durante a importação.
- Q: A importação deve gerar prévia/aprovação ou aplicar automaticamente? → A: Aplica automaticamente, sem etapa de prévia ou aprovação administrativa.
- Q: O que acontece se a coleta do catálogo falhar no meio? → A: A fase de catálogo é atômica: nenhuma personagem, versão ou aptidão é gravada e a execução termina como falha.
- Q: O que acontece se parte das imagens falhar? → A: As imagens válidas são preservadas, as demais são reportadas e a execução termina como parcial.
- Q: O administrador pode informar uma URL de fonte? → A: Não. Somente fontes previamente suportadas pelo sistema podem ser selecionadas.
- Q: Como tratar fontes desabilitadas ou sem conector na interface? → A: O painel de fontes mostra todas as fontes cadastradas, com situação e motivo; o seletor do formulário de importação lista somente fontes habilitadas com conector disponível.
- Q: O cancelamento interrompe a coleta do catálogo? → A: O critério de interrupção em até 1 item vale para a fase de imagens. Na fase de catálogo, o cancelamento é verificado antes da aplicação e nenhuma alteração é gravada após a solicitação.
- Q: Qual é o limite entre erro e aviso no catálogo? → A: Falha sistêmica, schema global inválido, conflito de identidade ou de versão são erros que abortam a fase. Detalhe 404, metadados opcionais ausentes e data desconhecida são avisos; a personagem é ignorada e as demais continuam.
- Q: Como garantir as invariantes da execução de importação? → A: Além do advisory lock e das transações, invariantes viáveis são reforçadas por constraints e trigger de imutabilidade terminal no banco.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Importar o catálogo de uma fonte externa pela interface (Priority: P1)

Um administrador acessa a área de catálogo, escolhe uma fonte externa já suportada, seleciona
"catálogo" e confirma. O sistema enfileira a importação, busca os dados na fonte, aplica as
novas personagens, versões e aptidões automaticamente e informa o resultado. Nenhum arquivo é
enviado pelo administrador.

**Why this priority**: o catálogo é a base de todas as votações. Sem um caminho de atualização
que não dependa de acesso ao servidor, a operação fica bloqueada para administradores.

**Independent Test**: cadastrar a fonte suportada, executar uma importação de catálogo e
verificar que as personagens novas e as atualizações foram aplicadas, com o relatório
disponível na interface.

**Acceptance Scenarios**:

1. **Given** um administrador autenticado e uma fonte externa habilitada, **When** seleciona a
   fonte, o modo "catálogo" e confirma, **Then** o sistema cria uma execução, redireciona para o
   acompanhamento e exibe o estado inicial.
2. **Given** uma execução de catálogo em andamento, **When** a coleta termina sem erros,
   **Then** personagens, versões e aptidões novas ou alteradas são aplicadas automaticamente e
   registradas para auditoria.
3. **Given** uma execução concluída, **When** o administrador abre o detalhe, **Then** vê
   quantas personagens foram criadas, atualizadas e ignoradas, além de avisos e erros.
4. **Given** uma fonte indisponível, **When** a execução tenta coletar os dados, **Then** ela
   falha sem gravar alterações parciais e exibe uma mensagem compreensível.
5. **Given** uma personagem com data de lançamento futura, **When** o catálogo é aplicado,
   **Then** ela é mantida no catálogo com a data futura e continua sujeita à data de corte das
   votações.
6. **Given** uma votação com snapshot existente, **When** uma importação de catálogo é
   aplicada, **Then** o snapshot, as cédulas e os resultados da votação permanecem inalterados.

---

### User Story 2 - Baixar e associar imagens automaticamente (Priority: P1)

Na mesma importação, ou em uma importação somente de imagens, o administrador escolhe se quer
todas as imagens ou apenas as personagens sem imagem válida. O sistema baixa as imagens da
fonte, valida, normaliza e associa à personagem canônica, sem upload manual.

**Why this priority**: o catálogo sem imagens prejudica a experiência de votação; o fluxo
manual atual exige acesso ao servidor e preparação de arquivos.

**Independent Test**: executar uma importação de imagens para personagens já existentes e
verificar que cada personagem elegível passa a ter uma imagem corrente válida ou um erro
explícito.

**Acceptance Scenarios**:

1. **Given** personagens já importadas e sem imagem, **When** o administrador executa uma
   importação de imagens com escopo "apenas faltantes", **Then** o sistema baixa e associa as
   imagens faltantes.
2. **Given** uma personagem com imagem corrente válida, **When** a importação com escopo
   "apenas faltantes" é executada, **Then** a imagem existente não é baixada nem substituída.
3. **Given** uma imagem remota inválida, grande demais ou indisponível, **When** o sistema
   tenta importá-la, **Then** a personagem é reportada com erro e as demais continuam.
4. **Given** uma imagem já existente com o mesmo conteúdo, **When** a importação é repetida,
   **Then** o arquivo é reutilizado, sem duplicar o asset.
5. **Given** uma imagem nova para uma personagem que já tinha imagem corrente, **When** a
   importação aplica, **Then** a nova passa a ser corrente, a anterior é preservada como
   histórica e o arquivo antigo não é apagado.
6. **Given** uma importação completa concluída, **When** o administrador valida o acervo,
   **Then** todas as imagens importadas estão válidas e nenhuma personagem importada ficou sem
   imagem, salvo erros reportados.
7. **Given** um participante acessando o catálogo após uma importação, **When** as imagens são
   exibidas, **Then** todas vêm do acervo local e nenhuma requisição externa é feita.

---

### User Story 3 - Acompanhar e controlar importações (Priority: P2)

O administrador acompanha o andamento, vê o passo atual, consulta o histórico, cancela uma
execução em andamento e repete uma execução que falhou.

**Why this priority**: a coleta externa pode demorar e falhar; sem visibilidade o administrador
não sabe se pode continuar nem como corrigir.

**Independent Test**: iniciar uma importação, observar a atualização de progresso, cancelar
outra execução e repetir uma execução falha.

**Acceptance Scenarios**:

1. **Given** uma execução recém-criada, **When** o administrador abre o detalhe, **Then** vê o
   estado "na fila" e o progresso é atualizado automaticamente sem recarregar a página.
2. **Given** uma execução em andamento, **When** o administrador solicita cancelamento,
   **Then** o sistema interrompe entre um item e outro, preserva o que já foi aplicado e marca a
   execução como cancelada.
3. **Given** uma execução com falha, **When** o administrador solicita repetição, **Then** uma
   nova execução é criada com a mesma fonte e o mesmo modo.
4. **Given** execuções anteriores, **When** o administrador abre o histórico, **Then** vê
   fonte, modo, situação, progresso, início, fim e quem disparou.
5. **Given** uma execução interrompida por queda do processo, **When** o sistema detecta que
   não há mais sinal de vida, **Then** a execução é marcada como falha e pode ser repetida.
6. **Given** execuções anteriores com falha, **When** o administrador abre o painel de fontes,
   **Then** vê a última falha conhecida de cada fonte e o motivo resumido.

---

### User Story 4 - Diagnosticar e manter fontes externas (Priority: P3)

O administrador consulta quais fontes externas estão disponíveis, vê a licença registrada,
verifica a conectividade e entende por que uma fonte não pode ser usada.

**Why this priority**: a importação depende de fontes externas que podem mudar; o diagnóstico
reduz tentativas repetidas e facilita a manutenção.

**Independent Test**: abrir a lista de fontes, executar a verificação de uma fonte disponível e
de uma fonte indisponível, e confirmar as mensagens exibidas.

**Acceptance Scenarios**:

1. **Given** uma fonte habilitada com conector suportado, **When** o administrador abre o painel
   de fontes, **Then** a fonte aparece com nome, nota de licença, última execução e pode ser
   selecionada no formulário de importação.
2. **Given** uma fonte sem conector ou desabilitada, **When** o administrador abre o painel,
   **Then** ela aparece com situação e motivo, mas não pode ser selecionada no formulário de
   importação.
3. **Given** uma fonte selecionada, **When** o administrador solicita a verificação,
   **Then** o sistema testa a disponibilidade e informa sucesso ou o motivo da falha.
4. **Given** uma fonte externa sem nota de licença, **When** o administrador tenta importar,
   **Then** a importação é bloqueada com mensagem sobre a revisão de licença.

---

### Edge Cases

- A fonte oficial responde, mas o GameTora está indisponível.
- A fonte oficial retorna uma lista vazia.
- A fonte muda o formato ou remove um campo esperado.
- Duas personagens da fonte normalizam para o mesmo identificador estável.
- Uma personagem existe na fonte, mas não tem data de lançamento global.
- Uma data retornada pelo GameTora é estimada ou futura.
- Uma versão já pertence a outra personagem.
- A imagem remota retorna erro HTTP, conteúdo que não é imagem ou tamanho acima do limite.
- A imagem remota é válida, mas menor que o tamanho mínimo aceito.
- O mesmo conteúdo de imagem é usado por mais de uma personagem.
- O administrador clica em importar duas vezes ou duas abas.
- Uma execução é cancelada depois de aplicar parte das imagens.
- O processo de importação cai no meio da execução.
- O disco de mídia fica indisponível durante a gravação de uma imagem.
- O recurso de importação externa está desabilitado por configuração.
- Um usuário sem perfil administrativo tenta acessar as rotas de importação.
- A fonte é desabilitada depois que uma execução já foi enfileirada.
- O limite de tempo da requisição HTTP é atingido.
- A fonte aplica limite de requisições ou bloqueia o agente do sistema.

## Requirements *(mandatory)*

### Functional Requirements

#### Acesso e habilitação

- **FR-001**: O sistema MUST permitir que somente administradores autenticados criem, consultem,
  cancelem e repitam importações externas.
- **FR-002**: O sistema MUST verificar a permissão no servidor em todas as rotas e ações.
- **FR-003**: O sistema MUST oferecer uma chave de configuração para desabilitar globalmente a
  importação externa sem remover dados já importados.
- **FR-004**: O sistema MUST permitir importar somente fontes previamente suportadas; o
  administrador MUST NOT informar URL, caminho de arquivo ou credencial de fonte.
- **FR-005**: O sistema MUST exigir que a fonte tenha uma nota de licença registrada antes de
  permitir a importação de imagens.
- **FR-006**: O sistema MUST exibir a nota de licença da fonte antes da confirmação da
  importação.

#### Fontes e coleta

- **FR-007**: O sistema MUST manter um catálogo de fontes externas suportadas, cada uma com
  identificador, nome, tipo, URL base, nota de licença e situação habilitada.
- **FR-008**: O sistema MUST possuir um conector específico para a fonte Global de Umamusume,
  usando o portal oficial para elenco e imagens e o GameTora para datas de lançamento e
  aptidões.
- **FR-009**: O conector MUST coletar, no mínimo: identificador estável da personagem, nome,
  identificador e nome da versão, data de lançamento global, estratégia, distâncias e
  superfícies.
- **FR-010**: O conector MUST baixar a imagem oficial da personagem quando não houver imagem
  corrente válida ou quando o escopo solicitado for "todas".
- **FR-011**: O sistema MUST limitar a coleta a domínios previamente autorizados pelo conector.
- **FR-012**: O sistema MUST aplicar limite de tempo, número máximo de tentativas e limite de
  tamanho por resposta.
- **FR-013**: O sistema MUST registrar avisos quando algum dado esperado estiver ausente, sem
  interromper a execução por dados opcionais.
- **FR-014**: O sistema MUST tratar falha sistêmica da fonte oficial ou do GameTora
  (indisponibilidade, lista vazia ou schema global inválido), conflito de identidade estável e
  conflito de versão como erro que aborta a fase de catálogo. Falhas isoladas de um item
  (detalhe 404, metadados opcionais ausentes ou data de lançamento desconhecida) MUST ser
  registradas como aviso; a personagem MUST ser ignorada e as demais MUST continuar.

#### Catálogo

- **FR-015**: O sistema MUST criar personagens, versões e aptidões ausentes automaticamente.
- **FR-016**: O sistema MUST atualizar nome da personagem, nome da versão, data de lançamento
  global e aptidões quando a fonte divergir do catálogo atual.
- **FR-017**: O sistema MUST aplicar todas as alterações de catálogo automaticamente, sem exigir
  prévia ou aprovação administrativa.
- **FR-018**: O sistema MUST registrar cada alteração aplicada em histórico de auditoria,
  identificando a execução, a fonte, o tipo da alteração e quem disparou.
- **FR-019**: O sistema MUST NOT criar mudanças pendentes de aprovação no fluxo de importação
  externa.
- **FR-020**: O sistema MUST manter o fluxo de importação manual por arquivo com o comportamento
  atual, incluindo a revisão de alterações em personagens existentes.
- **FR-021**: A aplicação do catálogo MUST ser atômica: qualquer erro — sistêmico, de schema,
  de conflito de identidade ou versão, ou de gravação — MUST impedir a gravação integral daquela
  execução. Avisos de item não são erros e não impedem a aplicação das demais personagens.
- **FR-022**: O sistema MUST ignorar personagens sem data de lançamento global, registrando-as
  como ignoradas no relatório.
- **FR-023**: O sistema MUST impedir que um identificador estável de personagem seja duplicado
  ou que uma versão já associada a outra personagem seja reatribuída silenciosamente; o conflito
  MUST ser reportado como erro.
- **FR-024**: O sistema MUST preservar os snapshots de votações existentes; nenhuma importação
  pode alterar apresentação histórica.
- **FR-025**: O sistema MUST garantir que importações repetidas não criem personagens, versões
  ou aptidões duplicadas.

#### Imagens

- **FR-026**: O sistema MUST baixar as imagens automaticamente durante a execução, sem upload
  manual.
- **FR-027**: O sistema MUST permitir dois escopos de imagens: todas as personagens do catálogo
  ou apenas personagens sem imagem corrente válida.
- **FR-028**: O sistema MUST validar o conteúdo da imagem antes de gravá-la.
- **FR-029**: O sistema MUST normalizar a imagem para o formato, dimensões e codificação
  definidos pelo acervo local.
- **FR-030**: O sistema MUST calcular e registrar o checksum do conteúdo normalizado.
- **FR-031**: O sistema MUST reutilizar um arquivo já existente quando o checksum coincidir.
- **FR-032**: O sistema MUST preservar imagens anteriores ao substituir a imagem corrente.
- **FR-033**: O sistema MUST manter no máximo uma imagem corrente por personagem.
- **FR-034**: O sistema MUST registrar a origem, a URL de origem e a nota de licença de cada
  imagem importada.
- **FR-035**: O sistema MUST continuar a importação das demais imagens quando uma falhar e
  reportar cada falha de forma isolada.
- **FR-036**: O sistema MUST reportar personagens que ficaram sem imagem válida ao final.
- **FR-037**: O sistema MUST NOT depender de serviços externos para exibir imagens durante o uso
  normal do sistema.

#### Execução e estado

- **FR-038**: O sistema MUST executar importações de forma assíncrona, sem manter a requisição
  HTTP aberta durante a coleta.
- **FR-039**: O sistema MUST representar uma execução em um dos estados: na fila, em execução,
  sucesso, parcial, falha ou cancelada.
- **FR-040**: O sistema MUST registrar o modo da execução: somente catálogo, somente imagens ou
  catálogo e imagens.
- **FR-041**: O sistema MUST executar, no modo completo, o catálogo antes das imagens.
- **FR-042**: O sistema MUST processar uma importação por vez, mantendo as demais na fila.
- **FR-043**: O sistema MUST registrar progresso total, progresso concluído, fase atual e passo
  atual.
- **FR-044**: O sistema MUST atualizar o sinal de vida da execução periodicamente enquanto o
  processo estiver ativo.
- **FR-045**: O sistema MUST permitir cancelamento de execuções na fila ou em andamento.
- **FR-046**: O cancelamento MUST ser verificado entre imagens e, na fase de catálogo, antes da
  aplicação; a coleta em curso não é interrompida, mas nenhuma alteração de catálogo é gravada
  depois da solicitação.
- **FR-047**: O sistema MUST permitir repetir uma execução com falha, parcial ou cancelada,
  criando uma nova execução.
- **FR-048**: O sistema MUST detectar execuções sem sinal de vida e marcá-las como falhas.
- **FR-049**: O sistema MUST gravar um relatório final com contagens, avisos e erros por
  personagem e por imagem.
- **FR-050**: O sistema MUST impedir que uma execução concluída seja alterada ou reaberta.

#### Interface e acompanhamento

- **FR-051**: O sistema MUST oferecer uma tela para iniciar a importação, com seleção de fonte,
  modo e escopo de imagens.
- **FR-052**: O seletor de fonte do formulário de importação MUST listar somente fontes
  habilitadas e com conector disponível. O painel de fontes MUST exibir todas as fontes
  cadastradas, incluindo desabilitadas e sem conector, com situação e motivo.
- **FR-053**: O sistema MUST exibir, para cada fonte cadastrada, a última execução, a situação e
  a data; quando houver falha, MUST exibir também o motivo resumido da última falha.
- **FR-054**: O sistema MUST exibir o detalhe da execução com progresso, fase, passo atual,
  contagens, avisos e erros.
- **FR-055**: A tela de detalhe MUST atualizar o progresso automaticamente enquanto a execução
  estiver ativa.
- **FR-056**: O sistema MUST oferecer um histórico de execuções com fonte, modo, situação,
  progresso, datas e administrador responsável.
- **FR-057**: O sistema MUST oferecer ações de cancelar e repetir quando aplicáveis, ocultando-as
  quando a execução estiver em estado terminal.
- **FR-058**: O sistema MUST apresentar mensagens em português brasileiro, com causa e próximo
  passo compreensíveis.
- **FR-059**: O sistema MUST oferecer uma verificação de disponibilidade da fonte antes ou
  independentemente de uma importação.
- **FR-060**: O sistema MUST indicar claramente quando a importação externa estiver desabilitada
  por configuração.

#### Segurança e auditoria

- **FR-061**: O sistema MUST restringir a coleta a conexões HTTPS para os domínios autorizados.
- **FR-062**: O sistema MUST rejeitar redirecionamentos para domínios não autorizados.
- **FR-063**: O sistema MUST rejeitar respostas que excedam os limites de tamanho definidos.
- **FR-064**: O sistema MUST validar imagens com biblioteca dedicada e limitar a quantidade de
  pixels processados.
- **FR-065**: O sistema MUST derivar caminhos de armazenamento de identificadores estáveis
  validados, nunca do nome bruto retornado pela fonte.
- **FR-066**: O sistema MUST registrar quem iniciou, cancelou ou repetiu cada execução.
- **FR-067**: O sistema MUST NOT registrar credenciais, cookies ou conteúdo de cédulas nos logs
  de importação.
- **FR-068**: O sistema MUST tratar todo conteúdo externo como não confiável.

#### Operação e integridade

- **FR-069**: O sistema MUST manter a importação por arquivo disponível como caminho alternativo.
- **FR-070**: O sistema MUST permitir diagnosticar a última falha de cada fonte no histórico.
- **FR-071**: O sistema MUST preservar dados históricos de execuções e relatórios.
- **FR-072**: O sistema MUST documentar a operação do processo de importação, os limites e a
  forma de recuperação.
- **FR-073**: O sistema MUST continuar funcionando para participantes mesmo quando a importação
  externa estiver indisponível ou desabilitada.
- **FR-074**: O sistema MUST registrar em log as transições de estado e as falhas da execução,
  sem dados sensíveis.

### Key Entities *(include if feature involves data)*

- **Fonte externa**: origem suportada de catálogo e imagens. Possui nome, tipo, URL base, nota
  de licença, situação habilitada e identificação do conector que sabe coletá-la.
- **Execução de importação**: tentativa de importar uma fonte. Possui fonte, modo, estado, fase,
  progresso, relatório, erro, quem disparou e datas de criação, início, sinal de vida e fim.
- **Relatório de importação**: resultado estruturado da execução, com contagens de catálogo,
  contagens de imagens, avisos e erros por item.
- **Personagem / Versão**: entidades do catálogo canônico criadas ou atualizadas pela
  importação; versões continuam subordinadas à personagem.
- **Imagem**: arquivo local associado à personagem, com origem, URL, licença, checksum e estado
  de validade.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um administrador consegue iniciar uma importação completa em até 3 interações,
  sem enviar arquivo, executar comando ou acessar o servidor.
- **SC-002**: Uma importação completa de 85 personagens e 85 imagens conclui em até 10 minutos
  em uma conexão de 10 Mbps, sem intervenção manual.
- **SC-003**: 100% das alterações de catálogo de uma importação externa são aplicadas e
  registradas em auditoria ao final de uma execução bem-sucedida.
- **SC-004**: 0 mudanças pendentes de aprovação são criadas pelo fluxo de importação externa.
- **SC-005**: Uma segunda importação idêntica cria 0 personagens duplicadas, 0 versões
  duplicadas e 0 imagens duplicadas.
- **SC-006**: 100% das imagens importadas com sucesso são válidas, locais e normalizadas para o
  padrão do acervo.
- **SC-007**: O progresso de uma execução fica visível na interface em até 5 segundos após o
  início.
- **SC-008**: O cancelamento interrompe a fase de imagens em até 1 item após a solicitação; na
  fase de catálogo, nenhuma alteração é aplicada após a solicitação.
- **SC-009**: 100% das tentativas de acesso às rotas de importação por usuários não
  administradores são bloqueadas.
- **SC-010**: 0 requisições a serviços externos de imagem ocorrem durante o uso normal por
  participantes.
- **SC-011**: Uma falha na fase de catálogo deixa 0 personagens, versões ou aptidões gravadas
  parcialmente.
- **SC-012**: 100% das falhas de item apresentam fonte, personagem ou imagem e motivo
  compreensível.
- **SC-013**: Uma execução interrompida sem sinal de vida é marcada como falha em até 10
  minutos e pode ser repetida.
- **SC-014**: O uso normal do sistema permanece inalterado quando a importação externa está
  desabilitada.
- **SC-015**: 100% das importações concluídas preservam integralmente snapshots, cédulas e
  resultados de votações existentes.

## Out of Scope

- Cadastro ou edição de fontes externas pela interface.
- Agendamento automático de importações externas.
- Prévia ou aprovação manual antes da aplicação.
- Edição manual dos dados coletados antes de aplicar.
- Importação simultânea de múltiplas fontes.
- Suporte a fontes além das previamente implementadas em código.
- Fila externa, Celery ou Redis.
- Importação de participantes, votações ou cédulas.

## Assumptions

- O servidor de aplicação possui saída HTTPS para os domínios das fontes suportadas.
- O portal oficial Global e o GameTora continuam disponíveis e com formato compatível; mudanças
  de formato exigem atualização do conector.
- As imagens continuam sujeitas à revisão manual de licença; a nota de licença é registrada e
  exibida, mas não substitui a autorização de uso.
- A importação é iniciada manualmente por um administrador; agendamento automático de
  importações externas está fora do escopo desta versão.
- O cadastro de novas fontes é feito por código (novo conector), não pela interface.
- O fluxo de importação por arquivo permanece disponível e não é alterado.
- O sistema processa uma importação externa por vez; filas adicionais podem aguardar.
- Personagens com lançamento futuro são importadas normalmente e continuam filtradas pela data
  de corte das votações.
- O GameTora é usado apenas para os dados que não existem na fonte oficial: datas de lançamento
  global e aptidões.
- A normalização de imagens segue o padrão já existente do acervo local.
- A aplicação externa pode falhar ou limitar requisições; tentativas e limites são parte do
  fluxo normal.
- A interface e as mensagens permanecem em português brasileiro.
