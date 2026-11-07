<!--
Sync Impact Report
Version change: 1.0.0 → 2.0.0 (MAJOR: redefinição de MUSTs nos Princípios II, III e V)
Modified principles:
  - II. Integridade das Votações: exceção de exclusão administrativa enquanto a votação está aberta
  - III. Privacidade das Cédulas: risco residual de inferência por comparação de agregados aceito
  - V. Segurança Proporcional: separação entre assurance administrativa e acesso de participante
Added sections: nenhuma
Removed sections: nenhuma
Templates requiring updates: nenhum (templates e comandos leem a constituição em tempo de execução)
Amendment record: `docs/governance-notes.md`
Follow-up TODOs: nenhum
-->

# Constituição do Uma Voting

## Propósito

O Uma Voting é um sistema web para organizar votações de banimento de personagens de
Umamusume: Pretty Derby em uma comunidade fechada.

O desenvolvimento MUST priorizar simplicidade, confiabilidade, facilidade de manutenção e uma
experiência de utilização clara, tanto para participantes quanto para administradores. A aplicação
MUST resolver o problema atual sem introduzir complexidade desnecessária e sem antecipar
funcionalidades que não fazem parte do escopo aprovado.

## Princípios Fundamentais

### I. Simplicidade Funcional

- A aplicação MUST implementar somente as funcionalidades necessárias ao escopo aprovado.
- Funcionalidades futuras MUST NOT ser implementadas apenas porque poderiam ser úteis
  posteriormente.
- Os fluxos MUST ser curtos, as interfaces autoexplicativas e as operações previsíveis.
- Abstrações, configurações e camadas arquiteturais MUST ter necessidade demonstrável; sem essa
  justificativa, MUST NOT ser adicionadas.

**Racional**: a comunidade é fechada e a manutenção tende a ser pequena e esporádica. Cada
abstração ou opção adicional aumenta o custo de entendimento e de correção sem entregar valor
proporcional.

### II. Integridade das Votações (INEGOCIÁVEL)

- As regras de negócio MUST ser aplicadas no servidor, independentemente de validações feitas na
  interface.
- A elegibilidade dos participantes e o catálogo de personagens MUST ser congelados no momento da
  abertura da votação, formando um snapshot imutável.
- Uma cédula confirmada MUST ser definitiva para o participante; ela MUST NOT ser alterada,
  substituída ou reaberta pelo participante.
- Exceção operacional: enquanto a votação estiver aberta, o administrador MAY excluir uma cédula
  sem acessar as escolhas, e o participante MAY enviar uma nova cédula. A exclusão administrativa
  MUST NOT ocorrer após o encerramento e MUST NOT expor as escolhas.
- As transições de estado da votação MUST ser consistentes e protegidas contra concorrência por
  meio de transações e restrições do banco de dados.
- Os resultados MUST ser reproduzíveis a partir dos dados preservados, sem depender de estado
  efêmero ou de cálculos externos.

**Racional**: uma votação de banimento só tem legitimidade se todas as cédulas contarem sob as
mesmas regras e se o resultado puder ser auditado e reproduzido tempos depois.

### III. Privacidade das Cédulas (INEGOCIÁVEL)

- Administradores MUST poder consultar participação e resultados agregados.
- Administradores MUST NOT poder consultar as escolhas individuais de cada participante.
- Participantes MUST poder consultar somente a própria cédula.
- Resultados parciais MUST NOT ser apresentados aos participantes durante a votação.
- Mecanismos de auditoria e registro MUST NOT criar, para administradores, um caminho de leitura
  que associe um participante às suas escolhas.
- A exclusão administrativa de cédula enquanto a votação está aberta é permitida sem acesso às
  escolhas. A aplicação MUST NOT exibir diferenças entre agregados antes/depois da exclusão nem
  registrar escolhas. O risco residual de inferência por comparação manual de agregados é
  explicitamente aceito nesta versão, com mitigação documentada e teste de privacidade.

**Racional**: o voto de banimento é uma decisão sensível dentro de uma comunidade pequena. A
privacidade protege os participantes de pressão social e preserva a confiança no processo.

### IV. Consistência do Catálogo e das Imagens

- Cada personagem canônica MUST possuir identidade estável no catálogo.
- Versões diferentes de uma mesma personagem MUST NOT criar opções independentes de votação.
- As imagens MUST ser associadas à personagem canônica.
- A aplicação MUST utilizar imagens armazenadas localmente e MUST NOT depender de serviços externos
  durante a utilização normal.
- Atualizações do catálogo MUST NOT modificar retroativamente snapshots de votações existentes.
- Imagens ausentes ou inválidas MUST NOT comprometer o funcionamento do sistema; a interface MUST
  apresentar uma alternativa segura.

**Racional**: o catálogo é a base de comparação entre votações. Identidade estável e snapshots
preservados permitem comparar resultados históricos; imagens locais garantem disponibilidade e
consistência visual.

### V. Segurança Proporcional

- A aplicação MUST aplicar autenticação, autorização, proteção de sessão, proteção contra CSRF e
  validação de entrada adequadas ao contexto de uma comunidade fechada.
- Mecanismos de segurança MUST NOT ser desproporcionais ao uso previsto nem introduzir dependências
  externas desnecessárias.
- A autenticação administrativa MUST exigir um fator efetivo (senha).
- O acesso de participante por username é um mecanismo de baixa garantia para uma comunidade
  fechada; MUST NOT ser apresentado como autenticação forte e MUST ter essa limitação documentada
  na interface e na documentação.
- Operações administrativas MUST ser restritas a administradores, verificadas no servidor.

**Racional**: a aplicação lida com identidade e privacidade de voto, mas opera em um contexto
controlado. A proteção deve cobrir os riscos reais sem transformar o acesso em uma barreira
desproporcional.

### VI. Experiência Consistente

- Toda a interface MUST estar em português brasileiro.
- O sistema MUST ser responsivo e utilizável em telas pequenas.
- Componentes equivalentes MUST apresentar comportamentos e aparência consistentes.
- Estados de carregamento, erro, sucesso e ausência de conteúdo MUST ser claros e compreensíveis.
- Acessibilidade MUST ser considerada desde o início, incluindo contraste, navegação por teclado,
  foco visível e áreas de toque.

**Racional**: participantes votam ocasionalmente e administradores operam o sistema sob demanda.
Uma interface previsível reduz erros e a necessidade de suporte.

### VII. Manutenibilidade

- O código MUST ser legível, modular e testável.
- Regras de negócio MUST permanecer separadas da apresentação.
- O banco de dados MUST garantir a integridade dos dados por meio de chaves, restrições e
  transações.
- Os fluxos críticos MUST possuir testes automatizados, incluindo autenticação, autorização,
  abertura e encerramento de votação, envio de cédula e apuração.
- Decisões técnicas e limitações relevantes MUST ser documentadas.
- Imagens, dados do catálogo e snapshots MUST ser organizados de forma independente.

**Racional**: a integridade das votações depende de o comportamento continuar correto ao longo do
tempo. Testes e separação de responsabilidades tornam as mudanças verificáveis.

## Escopo Controlado

O MVP contempla:

- Participantes e administradores.
- Autenticação e autorização.
- Gerenciamento de participantes.
- Catálogo de personagens e aptidões.
- Gerenciamento do acervo local de imagens.
- Criação e gerenciamento de votações.
- Envio e consulta de cédulas.
- Resultados agregados.
- Agendamento automático.
- Histórico.

Qualquer ampliação de escopo MUST ser justificada e aprovada explicitamente antes da implementação.
Funcionalidades fora do MVP MUST NOT ser iniciadas sem essa autorização.

## Critérios de Qualidade e Diretrizes de Desenvolvimento

Toda funcionalidade MUST:

1. Possuir comportamento definido.
2. Respeitar as permissões de acesso.
3. Ser validada no servidor.
4. Possuir testes adequados à sua criticidade.
5. Apresentar feedback compreensível.
6. Não comprometer dados históricos.
7. Não introduzir dependências externas desnecessárias.

O desenvolvimento MUST seguir estas diretrizes:

- Implementar em incrementos pequenos.
- Não ignorar requisitos aprovados.
- Não alterar regras de negócio silenciosamente.
- Resolver divergências entre documentação e implementação antes de prosseguir.
- Não substituir decisões funcionais por conveniências técnicas.
- Não iniciar funcionalidades fora do MVP sem autorização.

## Idioma e Localização

- A interface e a documentação funcional MUST estar em português brasileiro.
- O fuso horário padrão MUST ser `America/Sao_Paulo`.
- Datas e horários MUST ser apresentados de forma compreensível ao usuário.
- Datas em documentação e registros técnicos MUST seguir o formato ISO `YYYY-MM-DD`.

## Princípio de Evolução

A arquitetura MUST permitir evolução futura sem antecipar sua implementação. A prioridade é
entregar um sistema funcional, confiável, simples e fácil de manter, preservando a integridade das
votações, do catálogo, das imagens e dos dados históricos.

## Governança

- Esta constituição supersede as demais práticas do projeto. Em caso de conflito entre esta
  constituição e qualquer outro documento, esta constituição prevalece.
- Emendas MUST ser propostas por escrito, com justificativa, princípios afetados e plano de
  migração quando houver impacto em dados ou comportamento existente.
- Emendas MUST ser aprovadas pelos mantenedores do projeto antes de entrarem em vigor.
- Emendas aprovadas MUST ser registradas em `docs/governance-notes.md`, com versão, data,
  princípios afetados e justificativa.
- Todo plano, tarefa, revisão de código e pull request MUST verificar a conformidade com esta
  constituição. Desvios MUST ser justificados e registrados explicitamente.
- A complexidade adicionada MUST ser justificada em termos de necessidade demonstrável.
- O guia de interface em `docs/design-system.md` orienta apresentação e interação, mas MUST NOT
  alterar regras de negócio nem autorizar funcionalidades fora do escopo.
- Em caso de ambiguidade ou conflito entre documentação e implementação, a divergência MUST ser
  resolvida e registrada antes de prosseguir.

**Version**: 2.0.0 | **Ratified**: 2026-11-07 | **Last Amended**: 2026-11-07
