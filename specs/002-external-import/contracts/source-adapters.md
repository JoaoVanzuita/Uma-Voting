# Contract: Conectores de Fontes Externas

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Escopo**: contrato dos conectores que coletam catálogo e imagens, e regras do cliente HTTP.

## 1. Convenções

- Um conector por fonte externa, registrado em código.
- O conector nunca recebe URL, caminho ou credencial do usuário.
- Todo acesso à rede passa pelo cliente HTTP compartilhado.
- Conteúdo externo é não confiável.
- O conector não grava no banco; quem grava são os serviços de catálogo e imagem.
- Fixtures de teste não fazem rede.

## 2. Protocolo

```python
class ExternalSourceAdapter(Protocol):
    key: str
    display_name: str
    allowed_hosts: tuple[str, ...]

    def fetch_catalog(self) -> CatalogParseReport: ...
    def iter_images(
        self,
        characters: Iterable[Character],
        *,
        only_missing: bool,
    ) -> Iterator[ImageResult]: ...
    def check(self) -> SourceCheckResult: ...
```

### 2.1 `key`

Identificador estável usado em `CatalogSource.adapter`. Não muda quando a fonte muda de URL.

### 2.2 `fetch_catalog`

Retorna um `CatalogParseReport` com:

- `total_rows`: quantidade de linhas lógicas;
- `rows`: `CatalogRow` com identificador, nome, versão, data e aptidões;
- `characters`: agrupamento por personagem;
- `errors`: erros que impedem a aplicação;
- `ignored_lines`: linhas ignoradas.

Regras:

- Erros de rede, JSON inválido, campo obrigatório ausente, schema global inválido ou conflito de
  identidade/versão levantam `SourceError`.
- Dados opcionais ausentes geram aviso no relatório, não erro.
- Personagem sem data de lançamento global entra no relatório e é ignorada pela aplicação.
- O conector não aplica nada.

### 2.3 `iter_images`

Retorna um iterador de `ImageCandidate | ImageFetchError`.

```python
@dataclass(frozen=True)
class ImageCandidate:
    character_stable_id: str
    data: bytes
    source_url: str
    content_type: str = ""


@dataclass(frozen=True)
class ImageFetchError:
    character_stable_id: str
    source_url: str
    message: str
```

Regras:

- Baixa a imagem e entrega os bytes; o worker chama `store_image_bytes`.
- Falha de uma imagem vira `ImageFetchError`, sem interromper as demais.
- O conector respeita o escopo: `only_missing=True` não deve baixar imagem de personagem que já
  tem imagem corrente válida.
- Concorrência interna limitada pela configuração.
- O checksum e a normalização ficam no serviço de imagens.

### 2.4 `check`

```python
@dataclass(frozen=True)
class SourceCheckResult:
    ok: bool
    message: str
    checked_at: datetime
```

Verifica apenas disponibilidade e formato básico; não baixa catálogo completo nem imagens.

## 3. Cliente HTTP

### 3.1 Interface

```python
class HttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: tuple[str, ...],
        timeout: float,
        max_bytes: int,
        user_agent: str,
        retries: int = 3,
    ): ...

    def get_bytes(self, url: str, *, max_bytes: int | None = None) -> bytes: ...
    def get_text(self, url: str, *, max_bytes: int | None = None) -> str: ...
    def get_json(self, url: str, *, max_bytes: int | None = None) -> Any: ...
```

### 3.2 Regras obrigatórias

- Esquema `https`.
- Host na `allowed_hosts`.
- Resolver DNS e rejeitar:
  - loopback (`127.0.0.0/8`, `::1`);
  - faixas privadas (`10/8`, `172.16/12`, `192.168/16`, `fc00::/7`);
  - link-local (`169.254/16`, `fe80::/10`);
  - multicast e reservadas.
- Redirecionamentos: no máximo 3; cada destino revalidado.
- `User-Agent` identificável, configurável.
- Timeout de conexão e leitura.
- Limite de bytes por resposta; abortar ao exceder.
- Retry com backoff exponencial para timeout, 429 e 5xx.
- Não repetir POST; o cliente é somente leitura.
- Cache em memória por execução para URLs repetidas.
- Sem cookies persistentes.
- Erros viram `SourceHTTPError` com status, URL e motivo resumido.

## 4. Conector `umamusume-global`

### 4.1 Hosts permitidos

```python
allowed_hosts = (
    "en-portal.g.kuroco.app",
    "en-portal.g.kuroco-img.app",
    "umamusume.com",
    "gametora.com",
)
```

### 4.2 Catálogo

1. `GET https://en-portal.g.kuroco.app/rcms-api/4/characters`
   - extrair `payload["umamusume"]`;
   - para cada item: `slug`, `subject`.
2. `GET https://en-portal.g.kuroco.app/rcms-api/4/characters/{slug}`
   - extrair `details.download.icon` (fallback:
     `https://en-portal.g.kuroco-img.app/files/user/character/{slug}/{slug}_icon.png`);
   - extrair `details.visual` apenas para metadados de apoio.
3. Descobrir cards do GameTora (nesta ordem):
   - `GET https://gametora.com/data/manifests/umamusume.json` e usar a chave
     `character-cards` para montar `/data/umamusume/character-cards.<hash>.json`;
   - se o manifesto falhar, `GET https://gametora.com/umamusume/characters`, localizar o chunk
     `/_next/static/chunks/...js` que referencia o manifesto e repetir a montagem;
   - último recurso: URL fixa documentada no código (pode ficar obsoleta).
   - `404` no card JSON indica mudança de estrutura do GameTora e é erro de dados, não de
     disponibilidade.
4. `GET` do JSON de cards:
   - campos `card_id`, `char_id`, `name_en`, `url_name`, `release_en`, `aptitude`.
5. Descobrir build ID:
   - `"buildId":"..."` no HTML;
   - `GET https://gametora.com/_next/data/{buildId}/umamusume/characters/{url_name}.json`
     quando `release_en` estiver ausente.
6. Montar `CatalogRow`:
   - `character_stable_id = slugify(name)`;
   - `version_stable_id = f"{stable_id}-original"`;
   - `version_name = f"{name} (Original)"`;
   - `release_date_global` = menor data entre os cards; se ausente, estimar pelo banner EN;
   - `strategy = best_strategy(grades)`;
   - `distances = best_values(grades, DISTANCE_KEYS)`;
   - `surfaces = best_values(grades, SURFACE_KEYS)`.
7. Se dois registros normalizarem para o mesmo `stable_id`, levantar `SourceDataError`; não
   escolher silenciosamente um deles.

### 4.3 Aptidões

Ordem dos valores em `aptitude`:

```text
turf, dirt, sprint, mile, medium, long, front, pace, late, end
```

Seleção:

- estratégia: melhor grau entre `front`, `pace`, `late`, `end`;
- distância: valores com grau S ou A; se nenhum, os de melhor grau;
- superfície: valores com grau S ou A; se nenhum, os de melhor grau.

### 4.4 Imagens

- URL: `details.download.icon` ou fallback.
- `source_url`: `https://umamusume.com/characters/{slug}/`.
- `license_note`: copiada de `CatalogSource.license_note`.
- Formato esperado: PNG; o serviço de imagens valida e normaliza.
- Escopo `missing`: pular personagens com `ImageAsset(is_current=True, status=valid)`.

### 4.5 Falhas

**Erro fatal da fase** — aborta a aplicação do catálogo e o job termina `failed`:

| Situação | Resultado |
|---|---|
| Lista oficial vazia | `SourceDataError` |
| Todos os detalhes oficiais falham | `SourceUnavailableError` |
| GameTora indisponível ou sem cards | `SourceUnavailableError`/`SourceDataError` |
| Schema global inválido | `SourceDataError` |
| Duas personagens normalizam para o mesmo `stable_id` | `SourceDataError` |
| Versão já pertence a outra personagem | `SourceDataError`/`ImportIssue` |
| Timeout/429/5xx persistente na lista ou no GameTora | `SourceHTTPError` |

**Aviso de item** — a personagem é ignorada e as demais continuam:

| Situação | Resultado |
|---|---|
| Detalhe oficial 404 | Aviso; personagem não entra no catálogo |
| Card sem metadados do GameTora | Aviso; personagem ignorada |
| Aptidões inesperadas ou incompletas | Aviso; personagem ignorada |
| Sem data de lançamento global | Aviso; personagem ignorada pela regra do catálogo |
| Imagem 404, inválida ou acima do limite | `ImageFetchError`; job pode terminar `partial` |

A distinção é normativa: erros compõem `report.errors` e disparam a atomicidade; avisos compõem
`report.warnings` e nunca impedem a aplicação das demais personagens.

## 5. Registry

```python
ADAPTERS = {
    "umamusume-global": UmamusumeGlobalAdapter,
}
```

- `get_adapter(source)` instancia o conector.
- `available_sources()` filtra fontes habilitadas com chave registrada.
- Sem descoberta dinâmica de pacotes.
- Adicionar uma fonte = adicionar um módulo + registrar a chave + criar/atualizar
  `CatalogSource`.

## 6. Testes

Fixtures em `apps/catalog/tests/fixtures/sources/`:

| Arquivo | Conteúdo |
|---|---|
| `official_characters.json` | Lista oficial reduzida |
| `official_character_detail.json` | Detalhe com ícone |
| `gametora_cards.json` | Cards com datas e aptidões |
| `gametora_release.json` | Banners EN estimados |

Casos obrigatórios:

- parsing feliz da lista e do detalhe;
- slug determinístico e colisão;
- personagem sem data;
- data estimada;
- aptidões S/A e fallback por melhor grau;
- GameTora ausente;
- lista oficial vazia;
- imagem 404, content-type errado, tamanho excessivo;
- allowlist, redirect e IP privado no cliente HTTP;
- `check()` com sucesso e falha.

Nenhum teste acessa a internet; o cliente HTTP é injetado/mockado.
