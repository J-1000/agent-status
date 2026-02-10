# claude-status

Show running Claude Code sessions across Ghostty tabs.

```
$ claude-status

  ● api-server        active    a1b2c3d4
  ◐ frontend          idle      e5f6a7b8
  ● ml-pipeline       active    c9d0e1f2

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
claude-status              # print snapshot and exit
claude-status --watch      # re-print every 2 seconds
claude-status --json       # output as JSON for scripting
```

## How it works

1. Discovers running `claude` processes via `ps`
2. Resolves each process's working directory via `lsof` to determine the project
3. Extracts `GHOSTTY_SURFACE_ID` from the process environment to identify which tab/split each session lives in
4. Classifies status based on CPU usage: **active** (>5% CPU), **idle** (~0% CPU), or **stopped**

## Requirements

- macOS
- Python 3
- No external dependencies
