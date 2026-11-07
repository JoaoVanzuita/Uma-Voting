# Umam Voting --- Design System

> Guia visual e de interação para orientar o desenvolvimento da
> interface do Uma Voting.
> Idioma da interface: **português brasileiro (PT-BR)**.
> Direção visual: **minimalista, moderna, funcional e responsiva**.
> Tema: **light-first**.

## 1. Princípios

1.  Clareza antes de decoração: cada tela deve deixar evidente seu
    propósito e sua ação principal.
2.  Simplicidade: evitar excesso de painéis, bordas, cores, ícones e
    informações simultâneas.
3.  Consistência: componentes equivalentes devem ter a mesma aparência e
    comportamento.
4.  Hierarquia: títulos, conteúdo, metadados e ações precisam ser
    facilmente diferenciados.
5.  Feedback: ações, carregamentos, erros e confirmações devem ter
    estados visuais claros.
6.  Responsividade: projetar para telas pequenas e ampliar
    progressivamente para desktop.
7.  Acessibilidade: considerar contraste, teclado, foco e áreas de toque
    desde o início.
8.  Conteúdo em destaque: personagens, nomes e informações da votação
    devem prevalecer sobre elementos decorativos.

Este documento orienta a apresentação e a interação. Não altera regras
de negócio nem autoriza funcionalidades fora do escopo do produto.

## 2. Identidade visual

A interface deve transmitir organização e simplicidade, usando uma base
neutra e um tom violeta como destaque.

**Preferir** - Fundos neutros e superfícies brancas. - Bordas discretas
e sombras muito suaves. - Espaçamento generoso e alinhamentos
consistentes. - Ícones simples, usados somente quando ajudarem a
compreensão. - Animações curtas e funcionais, quando necessárias.

**Evitar** - Gradientes decorativos. - Sombras fortes ou muitos níveis
de elevação. - Muitas cores de destaque na mesma tela. - Animações
desnecessárias. - Ícones sem função clara. - Painéis e cards quando uma
lista simples for suficiente.

Usar tema claro no MVP. Tema escuro não é necessário.

## 3. Cores

  Token                     Valor       Aplicação
  ------------------------- ----------- ----------------------------------------
  `--color-white`           `#FFFFFF`   Superfícies principais, cards e campos
  `--color-surface`         `#F5F6FA`   Fundo secundário e áreas de apoio
  `--color-ink`             `#202431`   Texto principal e títulos
  `--color-primary`         `#7771D8`   Ações primárias, seleção e destaque
  `--color-primary-hover`   `#655FC5`   Hover de ações primárias
  `--color-muted`           `#747B8C`   Texto secundário e metadados
  `--color-border`          `#E5E7EF`   Bordas e divisores
  `--color-success`         `#27845D`   Sucesso e confirmação
  `--color-warning`         `#C58A32`   Atenção e pendências
  `--color-danger`          `#C64F5B`   Erros e ações destrutivas
  `--color-info`            `#5484C7`   Mensagens informativas

### Regras de aplicação

-   Usar `--color-ink` para texto principal e `--color-muted` para
    informações secundárias.
-   Reservar a cor primária para ações principais, seleção e orientação.
-   Usar vermelho somente para erros e ações destrutivas.
-   Não comunicar estados apenas por cor: combinar cor com texto, ícone
    ou rótulo.
-   Verificar contraste dos pares realmente utilizados, inclusive texto
    sobre botões, badges e fundos coloridos.

### Variáveis CSS iniciais

``` css
:root {
  color-scheme: light;

  --color-white: #ffffff;
  --color-surface: #f5f6fa;
  --color-ink: #202431;
  --color-primary: #7771d8;
  --color-primary-hover: #655fc5;
  --color-muted: #747b8c;
  --color-border: #e5e7ef;
  --color-success: #27845d;
  --color-warning: #c58a32;
  --color-danger: #c64f5b;
  --color-info: #5484c7;

  --font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;

  --radius-card: 10px;
  --radius-control: 8px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
}
```

## 4. Tipografia

Fonte preferencial: **Inter**, com fallback para fontes sans-serif do
sistema.

  Uso                  Tamanho   Peso
  ------------------ --------- ------
  Título de página       28 px    700
  Título de seção        20 px    600
  Título de card         16 px    600
  Texto padrão           14 px    400
  Texto auxiliar         12 px    400
  Texto de botão         14 px    600

### Diretrizes

-   Manter hierarquia tipográfica consistente.
-   Usar frases curtas e linguagem direta em PT-BR.
-   Evitar textos auxiliares longos quando o próprio rótulo puder
    explicar o controle.
-   Não reduzir excessivamente o texto em telas mobile.
-   Usar números tabulares quando isso facilitar a leitura de contadores
    e resultados.

## 5. Espaçamento, dimensões e elevação

Escala base de espaçamento:

  Token          Valor
  ------------ -------
  `space-1`       4 px
  `space-2`       8 px
  `space-3`      12 px
  `space-4`      16 px
  `space-6`      24 px
  `space-8`      32 px
  `space-12`     48 px

Dimensões e formas:

-   Cards: raio de borda de 10 px.
-   Botões e controles: raio de 8 px.
-   Campos e controles: altura mínima de 40 px.
-   Alvos de toque: preferencialmente pelo menos 44 × 44 px.
-   Bordas finas e discretas.
-   Sombras suaves, apenas quando necessárias para separar superfícies.

Manter espaçamento consistente entre títulos, conteúdo, grupos de campos
e ações. Evitar compactar excessivamente formulários e cards.

## 6. Layout e navegação

### Estrutura geral

-   Usar uma largura de conteúdo confortável e centralizada.
-   Manter cabeçalhos compactos.
-   Separar claramente navegação, conteúdo e ações.
-   Evitar múltiplas barras de navegação ou cabeçalhos empilhados sem
    necessidade.
-   Manter o contexto da página visível em telas menores.

### Área do participante

Navegação simples com: - Votações disponíveis. - Histórico. -
Identificação pelo username. - Ação de logout.

A página inicial deve priorizar as votações abertas e agendadas
disponíveis ao participante. O histórico deve ficar separado.

### Área administrativa

-   Sidebar em desktop.
-   Navegação compacta ou recolhível em telas menores.
-   Seções principais: Dashboard, Participantes, Catálogo e Votações.
-   Acesso explícito para alternar à experiência de participante.
-   Ações frequentes devem ser fáceis de localizar, sem sobrecarregar o
    dashboard.

## 7. Componentes

### 7.1 Botões

Variantes:

-   **Primário:** ação principal da tela; fundo na cor primária e texto
    com contraste adequado.
-   **Secundário:** ação alternativa; aparência neutra, contorno ou
    fundo discreto.
-   **Destrutivo:** ações como cancelar votação; usar cor de perigo e
    confirmação quando apropriado.
-   **Discreto/terciário:** ações auxiliares, sem competir com a ação
    principal.

Estados obrigatórios: - Normal. - Hover. - Focus visível. - Active. -
Disabled. - Loading.

Regras: - Usar verbos claros: "Criar votação", "Salvar", "Confirmar
voto". - Não usar vários botões primários concorrentes na mesma área. -
Exibir indicador de carregamento e impedir envios repetidos durante
processamento. - Não depender apenas de ícones para ações importantes.

### 7.2 Formulários

-   Cada campo deve ter rótulo visível e associado ao controle.
-   Placeholder é exemplo ou orientação complementar, não substituto do
    rótulo.
-   Agrupar campos relacionados.
-   Apresentar erros próximos ao campo correspondente.
-   Preservar valores preenchidos quando ocorrer erro de validação.
-   Indicar campos obrigatórios de forma consistente.
-   Usar mensagens curtas, específicas e acionáveis.

### 7.3 Cards de votação

Um card deve apresentar somente informações necessárias para decidir se
o usuário deseja acessar a votação, como:

-   Título.
-   Descrição curta, quando houver.
-   Estado da votação.
-   Prazo ou datas relevantes.
-   Situação do participante, quando aplicável.
-   Ação principal para abrir ou consultar.

Usar badges discretos para estados. Não repetir a mesma informação em
texto e badge sem necessidade.

### 7.4 Cards de personagem

-   Imagem com proporção consistente.
-   Nome legível.
-   Estado selecionado claramente identificável.
-   Área clicável confortável.
-   Foco de teclado visível.
-   Não depender apenas de mudança de cor para indicar seleção.

A grade deve adaptar o número de colunas à largura disponível. Imagens
devem manter dimensões consistentes para evitar saltos no layout.

### 7.5 Busca e filtros

-   Busca por nome com resposta instantânea.
-   Campo de busca facilmente identificável.
-   Filtros combináveis apresentados de forma compacta.
-   Em telas pequenas, filtros podem ficar recolhidos em um painel.
-   Deve ser fácil perceber quais filtros estão ativos e limpar a
    seleção.
-   A aplicação dos filtros não deve duplicar personagens.

### 7.6 Contadores e progresso

-   Exibir escolhas realizadas e limite permitido de forma clara, por
    exemplo: "2 de 3 escolhas".
-   Atualizar o contador imediatamente após seleção ou remoção.
-   Quando o limite for atingido, explicar visualmente por que novas
    escolhas não podem ser adicionadas.
-   Não usar indicadores de progresso decorativos sem significado
    funcional.

### 7.7 Mensagens e confirmações

Criar padrões para: - Sucesso. - Informação. - Atenção. - Erro. - Estado
vazio. - Confirmação de ação irreversível.

Mensagens devem ser objetivas e explicar, quando necessário, como
prosseguir.

Para o envio da cédula, destacar que a confirmação torna o voto
definitivo. A confirmação deve ser clara, sem linguagem alarmista.

## 8. Estados de interface

Todo componente interativo deve considerar, quando aplicável:

  Estado            Comportamento visual
  ----------------- -----------------------------------------------------
  Normal            Aparência padrão
  Hover             Destaque sutil em dispositivos com ponteiro
  Focus             Contorno de foco claramente visível
  Active/Selected   Seleção perceptível e consistente
  Disabled          Aparência atenuada e interação bloqueada
  Loading           Indicador de processamento e prevenção de repetição
  Success           Confirmação positiva
  Error             Indicação de erro e orientação para correção
  Empty             Mensagem simples explicando que não há conteúdo

### Estados vazios

-   Não deixar áreas vazias sem explicação.
-   Usar uma frase curta e contextual.
-   Evitar ilustrações grandes ou chamadas promocionais.
-   Quando não houver votações disponíveis, apresentar somente uma
    mensagem simples, sem destacar votações futuras.

### Estados de votação

Usar rótulos textuais consistentes para rascunho, agendada, aberta,
encerrada e cancelada. A cor pode reforçar o estado, mas não substitui o
rótulo.

## 9. Responsividade

Breakpoints de referência:

  Faixa                Largura
  --------- ------------------
  Mobile      abaixo de 768 px
  Tablet          768--1023 px
  Desktop      1024 px ou mais

### Mobile

-   Uma coluna para conteúdo principal quando necessário.
-   Cards de personagem em grade compacta, mas com alvos de toque
    confortáveis.
-   Filtros recolhíveis.
-   Navegação administrativa compacta.
-   Botões principais acessíveis sem rolagem excessiva.
-   Formulários em coluna única.
-   Evitar tabelas largas; converter em listas ou cards quando isso
    melhorar a leitura.

### Tablet

-   Usar grades com número intermediário de colunas.
-   Permitir navegação administrativa compacta.
-   Manter formulários e tabelas dentro da largura disponível.

### Desktop

-   Aproveitar o espaço horizontal sem esticar linhas de texto
    excessivamente.
-   Usar sidebar administrativa.
-   Grades de personagens com mais colunas.
-   Manter largura máxima confortável para leitura.

### Regras gerais

-   Não depender de hover para revelar informação ou permitir ações.
-   Evitar rolagem horizontal da página.
-   Testar em larguras intermediárias, não apenas nos breakpoints
    exatos.
-   Preservar a ordem lógica e a hierarquia do conteúdo em todos os
    tamanhos.

## 10. Acessibilidade

Alvo de referência: **WCAG 2.2 nível AA**, dentro do escopo razoável do
MVP.

Requisitos:

-   Contraste adequado para texto e componentes.
-   Navegação por teclado.
-   Foco visível e não encoberto.
-   Labels programaticamente associados aos campos.
-   Botões e links com nomes acessíveis.
-   Texto alternativo para imagens informativas.
-   Estados e erros não comunicados somente por cor.
-   Alvos de toque confortáveis.
-   Ordem de foco coerente com a ordem visual.
-   Mensagens de validação compreensíveis.
-   Respeitar `prefers-reduced-motion` caso existam animações.

## 11. Ícones e imagens

-   Preferir uma biblioteca consistente de ícones, como Lucide.
-   Usar ícones familiares e acompanhados de texto quando a ação não for
    universalmente reconhecível.
-   Não misturar estilos de ícones.
-   Imagens de personagens devem preservar proporção e não ser
    distorcidas.
-   Definir fallback para imagens ausentes ou inválidas.
-   Usar texto alternativo adequado.
-   Não usar imagens genéricas como se fossem retratos oficiais das
    personagens.

## 12. Diretrizes de implementação

A direção técnica visual inicialmente prevista é:

-   Bootstrap 5 para grid e componentes básicos.
-   CSS próprio com variáveis para aplicar os tokens deste documento.
-   Django Templates para estrutura das páginas.
-   HTMX para interações pontuais, mantendo a experiência integrada.
-   Inter como fonte principal.
-   Lucide para ícones.

Essas tecnologias são uma recomendação de implementação, não uma
exigência do design system. Caso o plano técnico escolha alternativas,
preservar os tokens, padrões, estados e comportamentos definidos aqui.

### Organização sugerida do CSS

Separar, de forma compatível com a estrutura do projeto:

1.  Tokens e variáveis.
2.  Tipografia e estilos base.
3.  Layout e responsividade.
4.  Componentes.
5.  Estados e utilitários.
6.  Ajustes específicos de páginas.

Evitar estilos duplicados e seletores excessivamente específicos.
Componentes devem reutilizar os mesmos tokens.

## 13. Checklist de revisão visual

Antes de considerar uma tela concluída, verificar:

-   [ ] A ação principal está evidente?
-   [ ] A hierarquia de títulos e conteúdo está clara?
-   [ ] O espaçamento segue a escala definida?
-   [ ] Cores e tipografia usam os tokens?
-   [ ] Estados de hover, foco, loading, erro e disabled foram
    considerados?
-   [ ] A tela funciona em mobile, tablet e desktop?
-   [ ] Não existe rolagem horizontal desnecessária?
-   [ ] A navegação por teclado funciona?
-   [ ] Contraste e foco são perceptíveis?
-   [ ] Textos estão em PT-BR e são objetivos?
-   [ ] Há feedback para ações importantes?
-   [ ] A tela evita elementos decorativos ou funcionalidades não
    previstas?

## 14. Critério de qualidade

A interface estará alinhada a este design system quando for visualmente
consistente, simples de compreender, responsiva e acessível; quando os
componentes compartilharem padrões de aparência e comportamento; e
quando a apresentação apoiar os fluxos do produto sem introduzir
complexidade ou alterar as regras funcionais.
