# claude-status

Show running Claude Code and Codex sessions across Ghostty tabs.

```
$ claude-status

  ● api-server        main        active    2h15m   a1b2c3d4
  ◐ frontend          feature/ui  idle      45m     e5f6a7b8
  ● ml-pipeline       main        active    1h02m   c9d0e1f2

  3 sessions (2 active, 1 idle)
```

## Install

Copy the script somewhere on your PATH:

```sh
cp claude-status ~/bin/
chmod +x ~/bin/claude-status
```

## Usage

```
claude-status                      # print snapshot and exit
claude-status --watch              # re-print every 2 seconds
claude-status --watch --interval 5 # re-print every 5 seconds
claude-status --watch --interval 0.5 # interval must be > 0
claude-status --json               # output as JSON for scripting
claude-status --watch --json       # stream JSON snapshots (no screen clear)
claude-status --goto api-server    # focus the Ghostty tab for a session
claude-status --watch --alert      # get notified when a session finishes
claude-status --cpu-threshold 2.5  # tune active/idle classification
```

## Alerts

Use `--alert` with `--watch` to get notified when a Claude/Codex session transitions from **active** to **idle** (i.e., the agent finished working and is waiting for input). Fires a terminal bell and a macOS desktop notification for each session.

## Focusing Sessions

Use `--goto` to switch to a running session's Ghostty tab:

```
claude-status --goto frontend
```

The argument is a case-insensitive project match. Matching priority is: exact project name, then prefix match, then substring match. If there are multiple matches at the selected tier you'll be asked to be more specific. This uses Ghostty's `ghostty://present-surface/` URL scheme, so it only works for sessions running inside Ghostty.

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

You can set the threshold with `--cpu-threshold` or `CLAUDE_STATUS_CPU_THRESHOLD`.

## Requirements

- macOS
- Python 3
- No external dependencies
