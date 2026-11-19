# Uma Voting — Sistema de Design

> Direção visual: **Identidade editorial** — uma identidade original para uma
> comunidade competitiva de Umamusume: Pretty Derby, inspirada em corrida,
> preparação e eventos, sem reproduzir interfaces, símbolos ou padrões visuais
> proprietários do jogo ou de ferramentas existentes.

**Idioma:** português brasileiro (PT-BR)

**Tema inicial:** claro
**Objetivo:** transformar a votação em uma etapa reconhecível de campeonato,
não em um formulário genérico, preservando clareza e acessibilidade.

## 1. Fundamento da identidade

O Uma Voting deve lembrar um programa de corrida contemporâneo: calmo, preciso
e energético. A identidade é construída por três sinais visuais discretos:

1. **Pista abstrata:** linhas curvas, segmentos e marcações em baixa opacidade.
2. **Informação editorial:** títulos, índices, faixas e metadados organizam a
   tela como um evento, não como um dashboard corporativo.
3. **Elenco em destaque:** os retratos das personagens ancoram o contexto de
   Umamusume, mas controles e resultados mantêm prioridade funcional.

O usuário deve perceber “competição organizada” antes de perceber decoração.

### O que comunicar

- Uma etapa comunitária organizada, e não um produto financeiro ou CRUD.
- Movimento e competição sem neon, HUD de jogo ou agressividade visual.
- Prazos, estados e resultados fáceis de escanear.
- Personagens como assunto; interface como infraestrutura silenciosa.

### Limites de originalidade

- Não copiar layouts, componentes, iconografia, códigos de cor, nomes de
  sistemas visuais ou assets de interface do jogo, wikis ou simuladores.
- Não usar vocabulário específico como elemento de marca. Os labels continuam
  genéricos: “votação”, “escolhas”, “resultado” e “histórico”.
- Não usar troféus, ferraduras, bandeiras, hipódromos literais ou “speed lines”
  como ornamento recorrente.
- Não transformar a aplicação em uma vitrine de cards colecionáveis.

## 2. Princípios de composição

1. **Informação antes de decoração.** Ação, título, estado e prazo aparecem
   antes de qualquer recurso temático.
2. **Um pulso por viewport.** Só um elemento de alto destaque por tela:
   votação atual, ação administrativa ou topo de resultado.
3. **Pista, não fantasia literal.** Curvas e faixas são abstratas.
4. **Retrato com propósito.** Imagem melhora reconhecimento; nunca compete com
   a ação principal, o nome ou o ranking.
5. **Cor orienta.** Violeta organiza interação; coral dá energia; cores
   semânticas permanecem exclusivas de estados.
6. **Densidade contextual.** Participante privilegia foco e imagem;
   administração privilegia varredura e operação.
7. **Originalidade sistêmica.** A marca vem dos tokens e composições próprios,
   não de uma referência superficial.

## 3. Tokens visuais

### 3.1 Paleta

| Papel | Token | Valor | Aplicação |
|---|---|---:|---|
| Canvas | `--color-canvas` | `#F7F5F2` | Fundo quente e discreto. |
| Superfície | `--color-surface` | `#FFFEFC` | Cards, menus, campos e painéis. |
| Apoio | `--color-surface-muted` | `#F0EDF4` | Faixas, agrupamentos e fundos de retrato. |
| Tinta | `--color-ink` | `#28243A` | Títulos e texto principal. |
| Texto auxiliar | `--color-muted` | `#6A6578` | Metadados e ajuda. |
| Violeta de pista | `--color-primary` | `#5646A8` | CTA, foco e seleção. |
| Violeta profundo | `--color-primary-strong` | `#40337F` | Hover e texto em fundo suave. |
| Coral de impulso | `--color-accent` | `#C85B6F` | Índice e destaque editorial não semântico. |
| Azul de apoio | `--color-support` | `#3B759A` | Informação secundária. |
| Linha | `--color-border` | `#E2DDE8` | Divisores e contornos passivos. |
| Linha ativa | `--color-border-strong` | `#8D849D` | Limite de controles interativos. |
| Sucesso | `--color-success` | `#18745C` | Confirmação e estado positivo. |
| Atenção | `--color-warning` | `#8A5709` | Prazo, pendência e cuidado. |
| Perigo | `--color-danger` | `#A63E55` | Erro e ação destrutiva. |

```css
:root {
  --color-primary-soft: #eeebfa;
  --color-accent-soft: #f9e9ec;
  --color-support-soft: #e8f1f6;
  --color-success-soft: #e6f3ee;
  --color-warning-soft: #f8efdf;
  --color-danger-soft: #f8e9ed;
  --color-track-line: rgb(86 70 168 / 12%);
}
```

#### Regras de cor

- Violeta é a única cor de ação principal.
- Coral não comunica erro, urgência ou seleção: é apenas acento editorial.
- Verde, amarelo e vermelho expressam somente estados semânticos.
- Não usar mais de uma superfície colorida forte por agrupamento.
- Todo significado expresso por cor deve ter texto e/ou ícone complementar.
- Garantir WCAG 2.2 AA para texto e 3:1 para limites de controles.

### 3.2 Tipografia

A tipografia é contemporânea e funcional. A fonte local Inter pode continuar
como padrão; não introduzir uma fonte decorativa para “parecer anime”.

| Estilo | Desktop | Mobile | Peso | Uso |
|---|---:|---:|---:|---|
| Display | 32 px | 26 px | 700 | Página e votação em destaque. |
| Título de seção | 20 px | 18 px | 650/700 | Blocos de conteúdo. |
| Título de card | 16 px | 16 px | 650 | Votações e personagens. |
| Corpo | 14 px | 14 px | 400 | Conteúdo corrente. |
| Legenda | 12 px | 12 px | 500 | Metadados e etiquetas. |
| Índice | 11 px | 11 px | 700 | Etapa e sobrelinha. |

- Usar números tabulares em prazos, contadores, posições e votos.
- Usar caixa alta somente em índices/sobrelinhas, com `letter-spacing` entre
  `0.06em` e `0.1em`.
- Títulos permanecem em frase normal; evitar caixa alta integral.
- O nome da personagem tem prioridade sobre atributos e metadados.

### 3.3 Escala, formas e elevação

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;

  --radius-control: 10px;
  --radius-card: 16px;
  --radius-pill: 999px;
  --control-height: 44px;
  --touch-target: 44px;

  --shadow-card: 0 1px 2px rgb(40 36 58 / 5%), 0 8px 20px rgb(40 36 58 / 5%);
  --shadow-raised: 0 12px 28px rgb(40 36 58 / 10%);
  --focus-ring: 0 0 0 3px rgb(64 51 127 / 25%);
}
```

- Cards usam raio de 16 px; painéis densos podem usar 12 px.
- Superfícies normais usam borda ou sombra, nunca ambas de forma forte.
- Hover pode elevar até 2 px e reforçar a borda.
- Alvos interativos têm no mínimo 44 × 44 px.

## 4. Assinaturas visuais

### 4.1 Motivo de pista

O motivo de pista é uma camada decorativa de fundo, não conteúdo. Pode aparecer
no card de votação em destaque, no cabeçalho de resultado e em um estado vazio
discreto. Nunca usar em listas, formulários, tabelas ou sob textos longos.

Ele deve ter uma ou duas curvas finas abstratas, com opacidade máxima de 12%:

```css
.track-motif::before {
  position: absolute;
  inset: auto -8% -42% 32%;
  width: 78%;
  height: 150%;
  border: 1px solid var(--color-track-line);
  border-radius: 50%;
  content: "";
  pointer-events: none;
}
```

Não usar bitmap externo, pistas realistas, logos, números de cavalo ou símbolos
do jogo.

### 4.2 Faixa de etapa

A faixa de etapa é o principal sinal autoral: uma linha de 4 px ou faixa de
8 px na borda de um card/painel, acompanhada de uma sobrelinha curta.

```text
ETAPA 02 · VOTAÇÃO ABERTA
ENCERRA EM 04H 18M
3 ESCOLHAS POR PARTICIPANTE
```

- Votação em destaque: faixa violeta e pequeno ponto coral.
- Agendada: faixa de atenção, sem coral.
- Encerrada: faixa neutra; o ranking ganha a hierarquia.
- Administração: aplicar somente em ações que precisam de atenção.
- Sobrelinhas não substituem título e não duplicam badge/metadados.

### 4.3 Retratos

As imagens de personagem usam uma moldura consistente:

- fundo `--color-surface-muted`;
- `object-fit: contain`, sem recorte agressivo;
- legenda/nome sempre fora da imagem;
- borda de 1 px e raio de 12–14 px;
- placeholder com silhueta simples, nunca emoji.

Na grade, retratos são utilitários. Em votação em destaque e resultado podem
ser maiores, mas não podem ocupar mais de 35% da largura de conteúdo no desktop
nem deslocar nome, votos ou ação.

## 5. Componentes

### 5.1 Marca e navegação

A marca é tipográfica: `Uma Voting` em tinta, com marcador abstrato próprio
(por exemplo, duas curvas interrompidas). O wordmark permanece textual e
acessível.

- Participante: cabeçalho compacto, claro, com linha inferior fina.
- Item ativo: fundo violeta suave e texto violeta profundo; não apenas
  sublinhado.
- Administração: sidebar neutra e faixa/índice somente na área ativa.
- As duas áreas pertencem ao mesmo sistema, mas não têm a mesma densidade.

### 5.2 Botões

| Variante | Aparência | Uso |
|---|---|---|
| Primário | Fundo violeta e texto branco | Uma ação principal por contexto. |
| Secundário | Superfície clara e borda forte | Voltar, consultar, alternativa. |
| Terciário | Sem caixa; fundo suave no hover | Navegação e ação auxiliar. |
| Perigo | Fundo vermelho semântico | Cancelamento e exclusão confirmados. |

- Coral nunca é CTA.
- Preferir verbos diretos: “Abrir votação”, “Revisar escolhas”, “Confirmar
  voto”, “Ver resultado”.
- Loading preserva largura do botão e bloqueia reenvio.
- Ícones sozinhos apenas para ações universais, com nome acessível.

### 5.3 Cards de votação

Evitar uma parede homogênea de cards.

**Card em destaque**

- Um único item prioritário na home.
- Horizontal no desktop e empilhado no mobile.
- Faixa de etapa, título, prazo, quantidade de escolhas e CTA.
- Pode ter motivo de pista e retrato lateral opcional.
- Descrição limitada a duas linhas.

**Card de lista**

- Sem hero, textura ou imagem apenas decorativa.
- Mostra estado, título, prazo e ação.
- Mantém altura previsível; descrição é opcional e truncada.

### 5.4 Grade de personagens

O grid deve parecer uma escalação organizada, não uma loja.

- 3 colunas no mobile compacto; 4 no mobile amplo; 5 no tablet; 6 no desktop;
  7 apenas no desktop amplo, se os nomes continuarem legíveis.
- Toda opção possui retrato, nome e indicador circular de seleção.
- Seleção: borda violeta, fundo suave, check visível e número de ordem da
  escolha. Nunca depender só de cor ou sombra.
- No limite, opções não selecionadas permanecem legíveis, porém
  indisponíveis; não devem sumir.
- Busca fica sempre visível. Filtros ficam recolhidos e chips só representam
  filtros ativos.

### 5.5 Barra de escolhas

A barra persistente é o resumo decisório:

- exibe “2 de 3 escolhas” e miniaturas das escolhas atuais;
- coloca CTA à direita no desktop e o mantém visível no mobile;
- ao atingir o limite, orienta: “Limite atingido. Desmarque uma escolha para
  alterar.”;
- usa superfície clara e elevação discreta, sem faixa decorativa.

### 5.6 Resultados

Resultados devem ser editoriais e comparáveis.

- Topo com faixa de etapa, estado encerrado, participação agregada e data.
- Primeiras posições podem ter índice ampliado e detalhe coral mínimo; evitar
  medalhas, troféus e ouro/prata/bronze literais.
- Cada linha: posição, retrato limitado, nome, quantidade e barra proporcional
  acessível.
- Barras usam violeta; empates mantêm a mesma posição.
- Não ampliar retratos a ponto de prejudicar a leitura do ranking.

### 5.7 Administração

A administração é uma mesa de organização, não uma versão cinza do
participante.

- Dashboard começa por “ação necessária” e votação em andamento; saúde de
  catálogo vem depois.
- Métricas usam número, frase curta e link de destino. Evitar muitos cards
  iguais empilhados.
- Tabelas têm cabeçalho discreto, linhas confortáveis e ações alinhadas.
- Risco usa cores semânticas e texto objetivo; nunca coral.
- Formulários usam seções com legenda e texto introdutório, sem motivo de pista.

### 5.8 Badges, alertas e estados vazios

- Badges são compactos e textuais; status não é oportunidade de decoração.
- Alertas usam fundo suave e incluem ação quando necessário.
- Estados vazios podem trazer pequeno marcador de pista abstrato, não uma
  ilustração dominante. Explicam a situação e, quando cabível, oferecem uma
  única próxima ação.

## 6. Composição por área

### Participante

**Home:** cabeçalho; título/contexto; uma votação atual em destaque quando
existir; demais votações em lista; histórico separado da ação presente.

**Seleção:** retorno e sobrelinha; metadados compactos; busca/filtros; grid;
barra persistente de escolhas.

**Revisão e resultado:** largura de leitura de 760–860 px. Aviso de confirmação
é claro, mas menor que as escolhas. Resultado prioriza comparação, sem hero
gráfico que prejudique o ranking.

### Administração

- Sidebar de 224 px em desktop e drawer abaixo de 1024 px.
- Conteúdo máximo de 1200 px; formulários limitados a 760 px.
- Topbar tem título, contexto e no máximo duas ações expostas.
- No mobile, tabelas operacionais viram cards com título e ação visíveis.

## 7. Responsividade e movimento

| Faixa | Largura | Regra principal |
|---|---:|---|
| Mobile compacto | 360–479 px | Uma coluna, grid de 3, CTA persistente. |
| Mobile amplo | 480–767 px | Grid de 4, filtros recolhidos. |
| Tablet | 768–1023 px | Grid de 5 e drawer administrativo. |
| Desktop | 1024–1279 px | Grid de 6 e sidebar. |
| Desktop amplo | 1280 px+ | Até 7 colunas e respiro extra. |

- Transições duram 120–180 ms e servem apenas a foco, hover, filtro e seleção.
- Não animar listas completas, ranking ou retratos.
- Respeitar `prefers-reduced-motion: reduce`.
- Conteúdo e ações essenciais não podem depender de hover.

## 8. Acessibilidade

- Alvo: WCAG 2.2 AA.
- Controles e alvos de toque com pelo menos 44 × 44 px.
- Foco de 2 px com `--focus-ring`, nunca encoberto pela barra persistente.
- Retratos informativos usam `alt` com nome; motivos decorativos usam
  `alt=""` ou ficam fora da árvore de acessibilidade.
- Seleção tem estado textual/programático além de borda e cor.
- Chips, drawer, filtros e mensagens preservam semântica nativa e retorno de
  foco adequado.
- Nunca inserir prazo, estado ou resultado somente dentro de imagens.

## 9. Checklist de revisão

- [x] A tela parece um evento de corrida sem citar ou copiar UI do jogo?
- [x] Há apenas um elemento de alto destaque na primeira viewport?
- [x] Coral aparece como acento, não CTA ou estado semântico?
- [x] O motivo de pista é discreto e não interfere com leitura?
- [x] Retratos melhoram reconhecimento e têm moldura consistente?
- [x] Título, prazo, estado e ação são escaneáveis sem imagem?
- [x] Labels funcionais permanecem genéricos e em PT-BR?
- [x] Teclado, contraste, loading, erro e mobile foram verificados?
- [x] A administração mantém eficiência e densidade operacional?

### 9.1 Decisões finais

**Etapa.** A faixa de etapa fica restrita à votação atual do participante e ao resultado. A
administração usa o marcador de marca e o índice da topbar; formulários, tabelas e listas não
recebem faixa nem motivo de pista.

**Coral.** `--color-accent` é exclusivamente decorativo: marcador de marca, ponto da faixa de
etapa, detalhe de posição no ranking e traço de índice. Não é usado em CTA, estado, erro, foco ou
texto pequeno. Seu contraste de 4,02:1 sobre superfície clara não atende AA para texto.

**Peso tipográfico.** 700 fica reservado a título de página, índices e números de métrica; 600 a
títulos de seção/card, botões e badges; 500 a rótulos e ênfase curta; 400 ao corpo. Não há pesos
sintéticos nem texto abaixo de 11 px.

## 10. Implementação sugerida

`static/css/tokens.css` concentra tokens. Componentes compartilhados ficam em
`components.css`; composições de participante e administração, em suas folhas
de página. O motivo de pista deve ser uma única classe utilitária reutilizável
(`.track-motif`), nunca regras duplicadas em templates.

Ordem de adoção:

1. Atualizar tokens de cor, elevação, raio e tipografia.
2. Criar marca, faixa de etapa e motivo de pista abstrato.
3. Recompôr home e cards em destaque/lista.
4. Atualizar grid e barra persistente com miniaturas resumidas.
5. Recompôr resultado e dashboard administrativo.
6. Validar contraste, teclado e responsividade em cada etapa.

Este guia orienta apenas apresentação e interação. Não altera regras de negócio,
permissões, elegibilidade, privacidade de votos ou catálogo.
