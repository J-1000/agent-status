# agent-status

Show running Claude Code and Codex sessions across Ghostty tabs.

```
$ agent-status

  ● api-server        main        active    2h15m   a1b2c3d4
  ◐ frontend          feature/ui  idle      45m     e5f6a7b8
  ● ml-pipeline       main        active    1h02m   c9d0e1f2

  3 sessions (2 active, 1 idle)
```

## Install

Copy the script somewhere on your PATH:

```sh
cp agent-status ~/bin/
chmod +x ~/bin/agent-status
```

## Usage

```
agent-status                      # print snapshot and exit
agent-status --watch              # re-print every 2 seconds
agent-status --watch --interval 5 # re-print every 5 seconds
agent-status --watch --interval 0.5 # interval must be > 0
agent-status --watch --interval-active 0.5 --interval-idle 5 # adaptive polling
agent-status --json               # output as JSON for scripting
agent-status --json-v2            # output versioned JSON envelope with metadata
agent-status --watch --json       # stream JSON snapshots (no screen clear)
agent-status --watch --json-v2    # stream versioned JSON envelopes
agent-status --goto api-server    # focus the Ghostty tab for a session
agent-status --watch --alert      # get notified when a session finishes
agent-status --cpu-threshold 2.5  # tune active/idle classification
```

## Alerts

Use `--alert` with `--watch` to get notified when a Claude/Codex session transitions from **active** to **idle** (i.e., the agent finished working and is waiting for input). Fires a terminal bell and a macOS desktop notification for each session.

## Focusing Sessions

Use `--goto` to switch to a running session's Ghostty tab:

```
agent-status --goto frontend
```

The argument is a case-insensitive project match. Matching priority is: exact project name, then prefix match, then substring match. If there are multiple matches at the selected tier you'll be asked to be more specific. This uses Ghostty's `ghostty://present-surface/` URL scheme, so it only works for sessions running inside Ghostty.

## JSON Output

- `--json`: array of session objects (legacy format)
- `--json-v2`: stable envelope:
  - `schema_version`
  - `generated_at` (UTC ISO-8601)
  - `sessions`
- in watch mode, both JSON formats stream snapshots without screen clears

## Adaptive Watch Polling

When using `--watch`, you can tune polling frequency by activity:

- `--interval-active`: used when any session is `active`
- `--interval-idle`: used when no sessions are `active`
- falls back to `--interval` when per-state intervals are not provided

## How it works

1. Discovers running `claude` and `codex` processes via `ps`
2. Resolves each process's working directory via `lsof` to determine the project
3. Detects the git branch for each project via `git rev-parse`
4. Extracts `GHOSTTY_SURFACE_ID` from the process environment to identify which tab/split each session lives in
5. Reads process uptime via `ps etime`
6. Classifies status based on CPU usage and process state:
   - **stopped** if process state includes `T`
   - **active** if CPU is `>= threshold` (default `5%`)
   - **idle** otherwise (`< threshold`)

You can set the threshold with `--cpu-threshold` or `AGENT_STATUS_CPU_THRESHOLD`.
`CLAUDE_STATUS_CPU_THRESHOLD` is still accepted for backward compatibility.

## Requirements

- macOS
- Python 3
- No external dependencies
