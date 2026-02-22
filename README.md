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
agent-status --watch --alert --alert-on active->stopped # notify on additional transitions
agent-status --watch --alert --alert-cooldown 10 # suppress repeat alerts for 10s
agent-status --no-task            # hide registered task column in table output
agent-status --task-width 32      # set max task column width
agent-status --registry-compact   # compact the registry file and exit
agent-status --registry-keep 500  # keep last 500 registry entries on compact
agent-status --cpu-threshold 2.5  # tune active/idle classification
```

## Alerts

Use `--alert` with `--watch` to get notified when a Claude/Codex session transitions from **active** to **idle** (i.e., the agent finished working and is waiting for input). Fires a terminal bell and a macOS desktop notification for each session.

To alert on other transitions, pass `--alert-on` with one or more `from->to` transitions (comma-separated or repeated):

```
agent-status --watch --alert --alert-on active->idle,active->stopped
agent-status --watch --alert --alert-on idle->active --alert-on active->stopped
```

Use `--alert-cooldown SECS` to suppress repeated alerts for the same session/transition within a time window.

## Task Column

If you register sessions via `cc`, the table output includes a task column by default.
Hide it with `--no-task` or adjust width via `--task-width CHARS`.

## Registration Wrapper

Use the `cc` wrapper to register a session with metadata (task description + start time) before launching Claude/Codex:

```
./cc --task "fix auth regression" -- claude
./cc --task "ship onboarding copy" -- codex --model gpt-5
```

Registrations are appended to `~/.agent-status/registrations.jsonl` by default. Override with `AGENT_STATUS_REGISTRY` or `cc --registry PATH`.

## Registry Cleanup

Use `agent-status --registry-compact` to prune invalid entries and keep the last N valid lines (default 1000).
Override the file with `--registry-path` and set retention with `--registry-keep`.

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
4. Deduplicates nested Claude/Codex parent-child process chains to avoid double-counting a single session
5. Extracts `GHOSTTY_SURFACE_ID` from the process environment to identify which tab/split each session lives in (`ps -wwwE` with `ps -eww -o command=` fallback)
6. Reads process uptime via `ps etime`
7. Classifies status based on CPU usage and process state:
   - **stopped** if process state includes `T`
   - **active** if CPU is `>= threshold` (default `5%`)
   - **idle** otherwise (`< threshold`)

You can set the threshold with `--cpu-threshold` or `AGENT_STATUS_CPU_THRESHOLD`.
`CLAUDE_STATUS_CPU_THRESHOLD` is still accepted for backward compatibility.

## Requirements

- macOS
- Python 3
- No external dependencies
