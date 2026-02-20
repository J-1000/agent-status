# agent-status — PRD

## Problem

When running multiple Claude Code and Codex instances across Ghostty tabs and splits, there's no quick way to see which sessions are active, idle, or waiting for input without cycling through each one manually.

## Solution

A single CLI command (`agent-status`) that prints a snapshot of all running Claude/Codex sessions, showing which project each belongs to, what Ghostty surface it lives in, and whether it's actively working or idle.

## Non-Goals

- No persistent daemon or background process
- No TUI framework or interactive UI
- No built-in todo/task management
- No auto-switching to tabs (can be added later as a natural extension)

## How It Works

### Discovery

1. Scan for running `claude` and `codex` processes using `ps -ax`
2. For each process, resolve the working directory via `lsof -a -p <pid> -d cwd -Fn` to determine the project
3. Read the process environment via `ps -p <pid> -wwwE` to extract `GHOSTTY_SURFACE_ID` (Ghostty injects this env var into each shell session)
4. Read CPU usage via `ps -p <pid> -o %cpu=` to determine active vs idle (kernel-smoothed average, no manual sampling needed)

### Status Classification

| Status | Condition | Display |
|---|---|---|
| **active** | CPU usage at or above threshold (`>= 5%`) | `●` green |
| **idle** | CPU usage below threshold (`< 5%`), process alive | `◐` yellow |
| **stopped** | Process in stopped state | `■` grey |

### Output Format

```
$ agent-status

  ● api-server        main        active    2h15m   a1b2c3d4
  ◐ frontend          feature/ui  idle      45m     e5f6a7b8
  ● ml-pipeline       main        active    1h02m   c9d0e1f2

  3 sessions (2 active, 1 idle)
```

Columns: status icon, project name (derived from directory basename), git branch, status label, uptime, Ghostty surface ID (truncated). If two projects share the same basename, disambiguate by prepending the parent directory (e.g. `work/api-server`).

If the terminal supports color, use ANSI colors for the status icons. Fall back to plain text gracefully.

### Surface Identification

Ghostty sets environment variables per surface (e.g. `GHOSTTY_SURFACE_ID`). The tool reads these from the process environment via `ps -p <pid> -wwwE` and parses out the variable. Surface IDs are opaque UUIDs — display them as a truncated 8-character hex prefix. There is no known public API to map surface IDs to tab indices, so don't attempt that mapping in v1.

## CLI Interface

```
agent-status                      # default: print snapshot and exit
agent-status --watch              # re-print every 2 seconds (like `watch`)
agent-status --watch --interval 5 # custom refresh interval (> 0)
agent-status --watch --interval-active 0.5 --interval-idle 5 # adaptive polling by status
agent-status --json               # output as JSON for scripting/piping
agent-status --json-v2            # output stable metadata envelope (schema + timestamp)
agent-status --watch --json       # stream JSON snapshots (no screen clear)
agent-status --goto <project>     # focus the Ghostty tab for a session
agent-status --watch --alert      # notify when a session goes active → idle
```

### Tab Switching (`--goto`)

`agent-status --goto <project>` focuses the Ghostty surface running the matching session. Matching is case-insensitive with this priority: exact name, then prefix, then substring. Behavior:

- **0 matches:** prints an error and lists available sessions (exit 1)
- **Multiple matches:** prints matching sessions and asks to be more specific (exit 1)
- **Match has no surface ID:** prints an error explaining it's not in Ghostty (exit 1)
- **Single match:** calls `open "ghostty://present-surface/<surface_id>"` to focus the tab (exit 0)

### Watch Alerts (`--alert`)

`agent-status --watch --alert` fires notifications when a session transitions from **active** to **idle** (agent finished working, waiting for input). Behavior:

- Tracks each session's status by PID between watch cycles
- On active→idle transition: terminal bell (one per cycle) + macOS desktop notification (one per session) via `osascript`
- First cycle never alerts (no previous state to compare)
- Silently ignored without `--watch`
- Transitioned rows show a `<- done` marker in the table output
- Other transitions (idle→active, active→stopped, new/disappeared sessions) are ignored

## Technical Decisions

- **Language:** Bash or Python. Bash is fine since the macOS introspection commands (`ps`, `lsof`) have straightforward output. Python if parsing gets messy. Pick whichever you'll iterate on faster.
- **No dependencies:** Avoid external packages. Use only standard library / coreutils.
- **Single file:** The entire tool should be one script, installable by copying it to `~/bin/`.
- **macOS only:** Uses `ps` and `lsof` for process introspection. No Linux support needed for v1.

## Open Questions to Resolve During Implementation

1. **What exactly does `GHOSTTY_SURFACE_ID` contain?** Test by running `env | grep GHOSTTY` in different tabs and splits. Determine whether the value encodes tab index, split position, or is just an opaque UUID.
2. **Does `ps -wwwE` reliably show the full environment?** Verify that `GHOSTTY_SURFACE_ID` appears in the output for Claude/Codex processes. If not, investigate alternatives like `KERN_PROCARGS2` sysctl.
3. **How do Claude Code and Codex spawn processes?** They may fork child processes for tools, so we need to identify the right parent PID to avoid double-counting. Check the process tree.
4. **Is `%cpu` from `ps` reliable for status?** Waiting for user input should show low CPU while active responses should show noticeable CPU. Validate this assumption.

## Future Extensions

- ~~**Configurable activity threshold:** Add `--cpu-threshold` (and optional env fallback) so active/idle classification is tunable per machine/workload.~~ ✓ Shipped as `--cpu-threshold` / `AGENT_STATUS_CPU_THRESHOLD` (legacy `CLAUDE_STATUS_CPU_THRESHOLD` also accepted)
- ~~**Stable machine-readable JSON envelope:** Add version/timestamp metadata (possibly via `--json-v2`) to make integrations safer over time.~~ ✓ Shipped as `--json-v2`
- ~~**Smarter `--goto` matching:** Prioritize exact match, then prefix, then substring to reduce ambiguity without losing convenience.~~ ✓ Shipped with case-insensitive tiered match precedence
- ~~**Adaptive watch polling:** Optional backoff or split intervals for active vs idle to reduce process-inspection overhead.~~ ✓ Shipped as `--interval-active` / `--interval-idle`
- **Configurable alert events:** Allow notifying on additional transitions (`active->idle`, `active->stopped`, etc.) with cooldown controls.
- **Additional edge-case tests:** Expand coverage around malformed env output, partial process-info rows, and transition behavior under watch mode.
- **Registration wrapper:** A `cc` alias that registers sessions with richer metadata (task description, start time) into a shared file
- ~~**Watch mode with alerts:** Notify (terminal bell or desktop notification) when a session goes from active to idle (meaning the agent finished and is waiting for you)~~ ✓ Shipped as `--alert`
- **Task integration:** Read a `tasks.md` file and display alongside sessions
