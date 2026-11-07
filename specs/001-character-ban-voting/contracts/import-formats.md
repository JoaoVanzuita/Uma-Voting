# Contract: Formatos de Importação

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Codificação**: UTF-8, sem BOM, separador vírgula, quebras LF ou CRLF.
**Tamanho máximo**: 5 MB por arquivo.

## 1. Participantes (`participants.csv`)

### 1.1 Formato

```csv
username
SpecialWeek
TokaiTeio
SilenceSuzuka
```

- Cabeçalho `username` é opcional, mas recomendado.
- Exatamente uma coluna.
- Linhas vazias são ignoradas.
- Espaços nas extremidades são removidos.
- Username não pode conter vírgula, aspas não balanceadas ou caracteres de controle.
- Comprimento: 1–150 caracteres.
- Unicidade case-insensitive, tanto dentro do arquivo quanto contra o banco.

### 1.2 Erros

Relatório por linha:

| Linha | Valor | Erro |
|---|---|---|
| 3 | `specialweek` | Username já existe (diferente apenas por maiúsculas/minúsculas) |
| 5 | ` ` | Username vazio |
| 7 | `a,b` | Vírgula não suportada no username |

A importação é atômica: se houver qualquer erro, nada é gravado.

## 2. Catálogo (`catalog.csv`)

### 2.1 Formato

Uma linha por versão de personagem.

```csv
character_stable_id,character_name,version_stable_id,version_name,release_date_global,strategy,distances,surfaces
tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),2025-06-26,pace,medium;long,turf
tokai-teio,Tokai Teio,tokai-teio-peak-joy,Tokai Teio (Peak Joy),2025-07-24,pace,mile;medium,turf
special-week,Special Week,special-week-original,Special Week (Original),2025-06-26,pace,medium;long,turf;dirt
```

### 2.2 Colunas

| Coluna | Obrigatória | Regras |
|---|---|---|
| `character_stable_id` | Sim | Slug `[a-z0-9-]+`, único por personagem |
| `character_name` | Sim | Nome de exibição; consistente entre linhas da mesma personagem |
| `version_stable_id` | Sim | Slug único globalmente |
| `version_name` | Sim | Nome administrativo da versão |
| `release_date_global` | Não | `YYYY-MM-DD` ou vazio; vazio = não lançada no Global |
| `strategy` | Sim | `front`, `pace`, `late` ou `end` |
| `distances` | Sim | Lista separada por `;`: `sprint`, `mile`, `medium`, `long` |
| `surfaces` | Sim | Lista separada por `;`: `turf`, `dirt` |

### 2.3 Regras de validação

- `character_stable_id` e `version_stable_id` devem ser slugs estáveis; não usar nome
  traduzido como identificador.
- O mesmo `version_stable_id` não pode aparecer duas vezes.
- Todas as linhas de uma personagem devem ter o mesmo `character_name`.
- `release_date_global` deve ser uma data válida e não futura além da data de corte
  configurada para a votação (o catálogo pode conter datas futuras; a votação filtra).
- Linhas com todas as versões sem data Global são ignoradas e reportadas; não criam
  personagem elegível.
- Aptidões devem pertencer às categorias/valores permitidos.
- Pelo menos uma distância e uma superfície por versão.

### 2.4 Comportamento de sincronização

- Personagem inexistente com ao menos uma versão Global: criada automaticamente.
- Personagem existente com qualquer diferença: `SyncChange` pendente.
- Versão nova de personagem existente: pendente.
- Correção de aptidão: pendente.
- Nenhuma alteração afeta snapshots de votações existentes.

### 2.5 Exemplo de erros

```text
Linha 4: version_stable_id duplicado "tokai-teio-original"
Linha 8: estratégia inválida "Pace" (use front, pace, late ou end)
Linha 9: character_name divergente para "special-week"
Linha 12: data inválida "26/06/2025" (use AAAA-MM-DD)
```

## 3. Manifesto de imagens (`images.csv`)

### 3.1 Formato

```csv
character_stable_id,file,source,source_url,license_note
tokai-teio,portraits/tokai-teio.png,gametora,https://gametora.com/umamusume/characters/100301-tokai-teio,"Referência visual; verificar autorização"
special-week,portraits/special-week.webp,curadoria-local,,"Acervo local autorizado"
```

### 3.2 Colunas

| Coluna | Obrigatória | Regras |
|---|---|---|
| `character_stable_id` | Sim | Deve existir no catálogo |
| `file` | Sim | Caminho relativo a `--source-dir`; `.png`, `.jpg`, `.jpeg` ou `.webp` |
| `source` | Não | Nome da `CatalogSource`; default `curadoria-local` |
| `source_url` | Não | URL de origem, quando conhecida |
| `license_note` | Condicional | Obrigatória para fonte externa |
| `is_current` | Não | Default `true`; use `false` para importar histórico |

### 3.3 Regras

- Apenas uma entrada por personagem com `is_current=true`.
- Arquivo deve existir, abrir no Pillow e ter conteúdo válido.
- Rejeitar caminhos absolutos, `..` ou symlinks que escapem de `--source-dir`.
- Dimensões mínimas: 128 × 128; destino final 256 × 256.
- Imagem é convertida para WebP e normalizada com `ImageOps.pad` (fundo neutro ou
  transparente), sem distorção.
- Checksum SHA-256 do arquivo normalizado define o nome final.
- Se o checksum já existir para a personagem, reutiliza o asset.
- Se já houver imagem corrente, ela é marcada `is_current=false`; o arquivo antigo
  permanece.
- Duplicidade de checksum entre personagens diferentes gera aviso para revisão.
- Imagem de fonte externa exige revisão e aprovação manual de licença registrada no runbook
  antes de `--apply`. O sistema não aplica gate técnico de licença no MVP.
- `--dry-run` mostra prévia; `--apply` grava.

### 3.4 Placeholder

- Arquivo local: `static/img/character-placeholder.webp` (ou SVG).
- Dimensões 256 × 256.
- `alt` genérico: "Imagem não disponível".
- O placeholder não é associado a nenhum asset; é fallback de apresentação.

## 4. Relatório de importação (JSON)

```json
{
  "file": "catalog.csv",
  "source": "curadoria-local",
  "dry_run": true,
  "total_rows": 120,
  "valid_rows": 118,
  "new_characters": 3,
  "pending_changes": 7,
  "ignored": 2,
  "errors": [
    {"line": 14, "field": "release_date_global", "message": "Data inválida"}
  ]
}
```

- Nenhum segredo ou escolha de cédula aparece no relatório.
- O relatório pode ser salvo em `var/reports/` e consultado pelo admin.
