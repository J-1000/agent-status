# Status Quo

Last updated: 2026-02-22

## Current behavior

- Discovers `claude` and `codex` processes via `ps`.
- Filters to TTY-attached sessions (`tty` not `??`/empty).
- Resolves CWD via `lsof`, git branch via `git rev-parse`, and uptime via `ps etime`.
- Classifies status:
  - `stopped` when process state contains `T`
  - `active` when CPU is `>= threshold` (default `5.0`)
  - `idle` otherwise
- CPU threshold is configurable via `--cpu-threshold` or `AGENT_STATUS_CPU_THRESHOLD` (legacy `CLAUDE_STATUS_CPU_THRESHOLD` is also accepted).
- `--watch --json` emits JSON snapshots without screen-clear escape codes.
- `--json-v2` emits a stable JSON envelope (`schema_version`, `generated_at`, `sessions`).
- `--alert` in watch mode notifies on `active -> idle` transitions.
- `--alert-on` and `--alert-cooldown` allow configuring alerted transitions and cooldowns.
- `--goto` matches by project with priority: exact, then prefix, then substring.
- `--goto` focuses matching Ghostty surface when available.
- `--watch` supports adaptive polling with `--interval-active` and `--interval-idle`.
- `cc` wrapper registers sessions with task metadata in `~/.agent-status/registrations.jsonl`.
- Table output includes registered task column by default; `--no-task` and `--task-width` control it.
- `--registry-compact` trims the registry file to the most recent entries.

## Input constraints

- `--interval` must be strictly greater than `0`.
- `--interval-active` and `--interval-idle` must be strictly greater than `0` when provided.

## Review findings status

- Finding 1 (notification injection risk): fixed by passing project via `osascript` argv.
- Finding 2 (`--watch --json` ANSI screen clear pollution): fixed by skipping clear in JSON watch mode.
- Finding 3 (malformed `etime` crash): fixed by tolerant parsing + fallback to unknown uptime.
- Finding 4 (negative interval runtime failure): fixed by argparse validation.

## Verification baseline

- Unit tests: `python3 -m unittest -q`
- Latest observed result: `147 tests`, `OK`

## PRD open-question validation

- Added reproducible checker: `scripts/validate-prd-assumptions.sh`
- Run it while you have live `claude`/`codex` sessions in Ghostty to verify:
  - `GHOSTTY_SURFACE_ID` shape across tabs/splits
  - `ps -wwwE` visibility, with `ps -eww -o command=` fallback
  - parent/child PID chains for nested-session de-duplication
  - `%cpu` behavior while idle vs actively generating

## Test coverage expansion

- Added edge-case coverage for:
  - partial/malformed `ps` process-info rows
  - `GHOSTTY_SURFACE_ID` fallback extraction behavior
  - watch-loop transition behavior across first/second cycles
