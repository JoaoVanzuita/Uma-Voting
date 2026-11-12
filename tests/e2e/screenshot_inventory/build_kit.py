"""Monta o kit de contexto para refatoração de interface.

Lê o manifesto gerado pelo fluxo Playwright, copia as documentações e as
capturas para ``ui-refactor-kit/`` e renomeia cada imagem com o ID estável da
tela/componente usado em ``docs/screen-inventory.md``.

Uso:
    python tests/e2e/screenshot_inventory/build_kit.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "var" / "screenshots" / "manifest.json"
FLOW = ROOT / "var" / "screenshots" / "flow.json"
KIT = ROOT / "ui-refactor-kit"
SCREENSHOTS_SOURCE = ROOT / "var" / "screenshots" / "png"

GROUP_ORDER = [
    "Autenticação",
    "Infraestrutura",
    "Administração",
    "Catálogo",
    "Votações",
    "Participante",
    "Componentes",
    "Responsivo",
]

GENERIC_STATES = {"", "padrao", "componente"}


def slugify(value: str) -> str:
    value = value.replace("×", "x")
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "captura"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_name(used: set[str], base: str) -> str:
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def display_filename(entry: dict) -> str:
    capture_id = entry["id"]
    title = slugify(entry["title"])
    state = slugify(entry.get("state", ""))
    parts = [capture_id, title]
    if state and state not in GENERIC_STATES:
        parts.append(state)
    filename = "-".join(parts) + ".png"
    if len(filename) > 140:
        filename = filename[:136].rstrip("-") + ".png"
    return filename


def copy_static_context() -> None:
    docs_target = KIT / "docs"
    specs_target = KIT / "specs" / "001-character-ban-voting"
    shutil.copytree(ROOT / "docs", docs_target)
    shutil.copytree(ROOT / "specs" / "001-character-ban-voting", specs_target)


def copy_screenshots(entries: list[dict]) -> list[dict]:
    used_by_group: dict[str, set[str]] = {}
    records: list[dict] = []
    checksums: list[str] = []

    for entry in entries:
        source = SCREENSHOTS_SOURCE / Path(entry["file"]).name
        if not source.exists():
            raise FileNotFoundError(f"Captura não encontrada: {source}")

        group_slug = slugify(entry["group"])
        group_dir = KIT / "screenshots" / group_slug
        group_dir.mkdir(parents=True, exist_ok=True)
        used = used_by_group.setdefault(group_slug, set())
        filename = unique_name(used, display_filename(entry))
        destination = group_dir / filename
        shutil.copy2(source, destination)

        relative = destination.relative_to(KIT).as_posix()
        checksum = sha256(destination)
        checksums.append(f"{checksum}  {relative}")
        records.append(
            {
                "capture_id": entry["id"],
                "screen_id": entry["screen"],
                "group": entry["group"],
                "group_slug": group_slug,
                "file": relative,
                "source_file": entry["file"],
                "title": entry["title"],
                "state": entry["state"],
                "description": entry["description"],
                "url": entry["url"],
                "viewport": entry["viewport"],
                "selector": entry.get("selector"),
                "notes": entry.get("notes", ""),
                "sha256": checksum,
            }
        )

    (KIT / "screenshots" / "checksums.sha256").write_text(
        "\n".join(checksums) + "\n",
        encoding="utf-8",
    )
    return records


def write_csv(records: list[dict]) -> None:
    fields = [
        "screen_id",
        "capture_id",
        "group",
        "file",
        "title",
        "state",
        "description",
        "url",
        "viewport",
        "notes",
    ]
    with (KIT / "screenshots.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            viewport = row["viewport"] or {}
            row["viewport"] = f"{viewport.get('width', '?')}x{viewport.get('height', '?')}"
            writer.writerow(row)


def write_json(records: list[dict], source_manifest: dict) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_manifest": "var/screenshots/manifest.json",
        "source_manifest_generated_at": source_manifest.get("generated_at"),
        "capture_count": len(records),
        "failure_count": len(source_manifest.get("failures", [])),
        "groups": dict(Counter(record["group"] for record in records)),
        "screenshots": records,
    }
    (KIT / "screenshots.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_index(records: list[dict]) -> None:
    lines = [
        "# Índice de capturas",
        "",
        "Cada arquivo começa com o ID estável usado em `docs/screen-inventory.md`.",
        "Os componentes usam `C01–C30` e as capturas responsivas usam `R01–R11`.",
        "",
        f"Total: **{len(records)} capturas**.",
        "",
    ]
    for group in GROUP_ORDER:
        group_records = sorted(
            (record for record in records if record["group"] == group),
            key=lambda record: record["capture_id"],
        )
        if not group_records:
            continue
        lines.append(f"## {group} ({len(group_records)})")
        lines.append("")
        lines.append("| Arquivo | Tela | Estado | Descrição |")
        lines.append("|---|---|---|---|")
        for record in group_records:
            relative = Path(record["file"]).relative_to("screenshots").as_posix()
            screen_label = (
                record["capture_id"] if record["screen_id"] in {"C", "R"} else record["screen_id"]
            )
            lines.append(
                "| [{}]({}) | `{}` | {} | {} |".format(
                    Path(record["file"]).name,
                    relative,
                    screen_label,
                    record["state"].replace("|", "\\|"),
                    record["description"].replace("|", "\\|"),
                )
            )
        lines.append("")
    (KIT / "screenshots" / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def write_readme(records: list[dict], source_manifest: dict) -> None:
    counts = Counter(record["group"] for record in records)
    count_rows = "\n".join(
        f"| {group} | {counts.get(group, 0)} | `screenshots/{slugify(group)}/` |"
        for group in GROUP_ORDER
    )
    examples = "\n".join(
        [
            "| ID | Arquivo no kit |",
            "|---|---|",
            "| `A01` | `screenshots/autenticacao/A01-01-login-de-participante.png` |",
            "| `P02` | `screenshots/participante/"
            "P02-01-selecao-de-personagens-votacao-aberta.png` |",
            "| `C01` | `screenshots/componentes/C01-card-de-autenticacao.png` |",
            "| `R01` | `screenshots/responsivo/R01-login-de-participante-movel-390x844.png` |",
        ]
    )
    total_line = (
        f"Total: **{len(records)} capturas**, "
        f"**{len(source_manifest.get('failures', []))} falhas** na captura."
    )
    readme = f"""# Kit de contexto — refatoração de interface do Uma Voting

Este kit reúne o contexto funcional, o inventário de telas e as capturas visuais
da aplicação para orientar uma refatoração de interface em outro agente.

## Conteúdo

- `docs/functionalities.md` — o que o sistema faz, regras de negócio e rastreabilidade de FRs.
- `docs/screen-inventory.md` — todas as telas, componentes, rotas, estados e contratos técnicos.
- `docs/design-system.md`, `docs/operations.md`, `docs/security-review.md` e
  `docs/governance-notes.md` — documentos referenciados pelos dois arquivos principais.
- `specs/001-character-ban-voting/` — especificação, modelo de dados e contratos citados
  pelas documentações.
- `screenshots/` — {len(records)} capturas organizadas por grupo, com nomes ligados
  aos IDs das telas.
- `screenshots/INDEX.md` — índice navegável por grupo.
- `screenshots.csv` e `screenshots.json` — metadados completos para uso por ferramentas.
- `flow.json` — fases do fluxo de teste que produziu as capturas.

## Como ler

1. Comece por `docs/functionalities.md` para entender regras, perfis e ciclo de vida.
2. Use `docs/screen-inventory.md` para localizar a tela pelo ID (`A01`, `P02`, `D05`, `V03` etc.).
3. Abra a captura correspondente em `screenshots/` usando o prefixo do ID.
4. Consulte `screenshots/INDEX.md` ou `screenshots.csv` para ver todos os estados capturados.

## Convenção dos nomes

O nome de cada imagem começa com o ID estável da documentação, seguido de um slug
do título e, quando relevante, do estado capturado.

{examples}

- Telas: `A01–A02`, `P01–P08`, `D01–D08`, `V01–V06`, `I01–I07`.
- Componentes: `C01–C30`.
- Responsivo: `R01–R11`.

## Cobertura

| Grupo | Capturas | Pasta |
|---|---:|---|
{count_rows}

{total_line}

## Contexto das capturas

- As capturas foram produzidas por `tests/e2e/screenshot_inventory/run.sh` em uma
  instância isolada (`127.0.0.1:8001`) com banco clonado.
- Os registros de cenário usam o prefixo `[SCREENSHOT]`; eles existem apenas no banco
  isolado e não fazem parte dos dados funcionais da aplicação.
- As credenciais e os dados de cenário são locais e não representam produção.
- O fluxo cobre sessões simultâneas de participante e administrador, HTMX, erros de
  formulário, importação CSV, sincronização com pendências, 403/404/500, modo
  participante e viewports móvel/tablet.

## Pontos de atenção visual

- **P06 / C13**: o template de resultado do participante usa `.result-item` sem regra
  CSS dedicada; as imagens preservam o tamanho intrínseco. O comportamento está
  registrado no manifesto e em `docs/screen-inventory.md` §20.
- **P02**: o resumo de seleção é fixo no rodapé na aplicação. Nas capturas de página
  inteira ele foi posicionado estaticamente para não sobrepor o grid; a nota está no
  `screenshots.json`.

## Prompt sugerido para o próximo agente

> Use `docs/functionalities.md` e `docs/screen-inventory.md` como fonte de verdade
> funcional e estrutural. Consulte as capturas pelo ID da tela (`A01`, `P02`, `D05`,
> `V03` etc.) e por `screenshots/INDEX.md`. Preserve rotas, permissões, estados,
> validações server-side, acessibilidade e os contratos de view documentados.
> Proponha a refatoração visual em etapas, mantendo a compatibilidade funcional e
> justificando decisões de design com os componentes e estados já inventariados.

## Reprodutibilidade

O kit foi gerado a partir de `var/screenshots/manifest.json` (captura de
{source_manifest.get("generated_at", "data desconhecida")}) pelo script
`tests/e2e/screenshot_inventory/build_kit.py`. As documentações foram copiadas sem
alteração; os links relativos entre `docs/` e `specs/` foram preservados.
"""
    (KIT / "README.md").write_text(readme, encoding="utf-8")


def verify(records: list[dict]) -> None:
    expected = {record["file"] for record in records}
    actual = {path.relative_to(KIT).as_posix() for path in (KIT / "screenshots").rglob("*.png")}
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(f"Divergência de capturas. Faltando={missing} Extra={extra}")

    for record in records:
        source = SCREENSHOTS_SOURCE / Path(record["source_file"]).name
        destination = KIT / record["file"]
        if sha256(source) != sha256(destination):
            raise RuntimeError(f"Checksum divergente: {record['file']}")

    # As documentações principais devem ser cópias byte a byte.
    for name in ("functionalities.md", "screen-inventory.md"):
        if sha256(ROOT / "docs" / name) != sha256(KIT / "docs" / name):
            raise RuntimeError(f"Documentação alterada na cópia: {name}")


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit(
            "Manifesto não encontrado. Execute tests/e2e/screenshot_inventory/run.sh primeiro."
        )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["screenshots"]
    if not entries:
        raise SystemExit("O manifesto não contém capturas.")

    if KIT.exists():
        shutil.rmtree(KIT)
    KIT.mkdir(parents=True)

    copy_static_context()
    shutil.copy2(FLOW, KIT / "flow.json")
    records = copy_screenshots(entries)
    write_csv(records)
    write_json(records, manifest)
    write_index(records)
    write_readme(records, manifest)
    verify(records)

    print(f"Kit criado em {KIT}")
    print(f"  docs copiados: {len(list((KIT / 'docs').glob('*.md')))}")
    print(f"  capturas copiadas: {len(records)}")
    print(f"  índice: {KIT / 'screenshots' / 'INDEX.md'}")
    print(f"  metadados: {KIT / 'screenshots.csv'} e {KIT / 'screenshots.json'}")


if __name__ == "__main__":
    main()
