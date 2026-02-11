# claude-status

Show running Claude Code sessions across Ghostty tabs.

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
claude-status --json               # output as JSON for scripting
claude-status --goto api-server    # focus the Ghostty tab for a session
```

## Focusing Sessions

Use `--goto` to switch to a running session's Ghostty tab:

```
claude-status --goto frontend
```

The argument is a case-insensitive substring match on the project name. If there are multiple matches you'll be asked to be more specific. This uses Ghostty's `ghostty://present-surface/` URL scheme, so it only works for sessions running inside Ghostty.

## How it works

1. Discovers running `claude` processes via `ps`
2. Resolves each process's working directory via `lsof` to determine the project
3. Extracts `GHOSTTY_SURFACE_ID` from the process environment to identify which tab/split each session lives in
4. Classifies status based on CPU usage: **active** (>5% CPU), **idle** (~0% CPU), or **stopped**

## Requirements

- macOS
- Python 3
- No external dependencies
