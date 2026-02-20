# Status Quo

Last updated: 2026-02-20

## Current behavior

- Discovers `claude` and `codex` processes via `ps`.
- Filters to TTY-attached sessions (`tty` not `??`/empty).
- Resolves CWD via `lsof`, git branch via `git rev-parse`, and uptime via `ps etime`.
- Classifies status:
  - `stopped` when process state contains `T`
  - `active` when CPU is `>= threshold` (default `5.0`)
  - `idle` otherwise
- CPU threshold is configurable via `--cpu-threshold` or `CLAUDE_STATUS_CPU_THRESHOLD`.
- `--watch --json` emits JSON snapshots without screen-clear escape codes.
- `--json-v2` emits a stable JSON envelope (`schema_version`, `generated_at`, `sessions`).
- `--alert` in watch mode notifies on `active -> idle` transitions.
- `--goto` matches by project with priority: exact, then prefix, then substring.
- `--goto` focuses matching Ghostty surface when available.
- `--watch` supports adaptive polling with `--interval-active` and `--interval-idle`.

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
- Latest observed result: `121 tests`, `OK`
