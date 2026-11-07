# Uma Voting

Sistema web para organizar votações de banimento de personagens de
Umamusume: Pretty Derby em uma comunidade fechada.

Monólito Django server-rendered (Django Templates + HTMX + Bootstrap), com
PostgreSQL, Gunicorn e Caddy em Docker Compose.

## Documentação

- Especificação: `specs/001-character-ban-voting/spec.md`
- Plano técnico: `specs/001-character-ban-voting/plan.md`
- Tarefas: `specs/001-character-ban-voting/tasks.md`
- Quickstart: `specs/001-character-ban-voting/quickstart.md`
- Operação: `docs/operations.md`
- Design system: `docs/design-system.md`

## Desenvolvimento

```bash
cp .env.example .env
uv sync
docker compose up --build
```

A documentação completa de operação será consolidada na fase de endurecimento.
