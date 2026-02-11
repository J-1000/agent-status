#!/usr/bin/env python3
"""Tests for claude-status."""

import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock

# Import claude-status despite the hyphen and no .py extension
import importlib.machinery
import importlib.util

_loader = importlib.machinery.SourceFileLoader(
    "claude_status",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-status"),
)
_spec = importlib.util.spec_from_loader("claude_status", _loader)
cs = importlib.util.module_from_spec(_spec)
_loader.exec_module(cs)


class TestClassifyStatus(unittest.TestCase):
    def test_active_high_cpu(self):
        self.assertEqual(cs.classify_status(15.0, "R+"), "active")

    def test_active_at_threshold(self):
        self.assertEqual(cs.classify_status(5.0, "S+"), "active")

    def test_idle_low_cpu(self):
        self.assertEqual(cs.classify_status(0.1, "S+"), "idle")

    def test_idle_zero_cpu(self):
        self.assertEqual(cs.classify_status(0.0, "S"), "idle")

    def test_stopped_process(self):
        self.assertEqual(cs.classify_status(0.0, "T"), "stopped")

    def test_stopped_overrides_cpu(self):
        self.assertEqual(cs.classify_status(50.0, "T+"), "stopped")


class TestDisambiguateProjects(unittest.TestCase):
    def test_no_duplicates(self):
        sessions = [
            {"project": "api", "cwd": "/home/user/api"},
            {"project": "frontend", "cwd": "/home/user/frontend"},
        ]
        cs.disambiguate_projects(sessions)
        self.assertEqual(sessions[0]["project"], "api")
        self.assertEqual(sessions[1]["project"], "frontend")

    def test_duplicates_get_parent_prefix(self):
        sessions = [
            {"project": "api", "cwd": "/home/user/work/api"},
            {"project": "api", "cwd": "/home/user/personal/api"},
        ]
        cs.disambiguate_projects(sessions)
        self.assertEqual(sessions[0]["project"], "work/api")
        self.assertEqual(sessions[1]["project"], "personal/api")

    def test_mixed_duplicates_and_unique(self):
        sessions = [
            {"project": "api", "cwd": "/a/work/api"},
            {"project": "api", "cwd": "/a/personal/api"},
            {"project": "frontend", "cwd": "/a/frontend"},
        ]
        cs.disambiguate_projects(sessions)
        self.assertEqual(sessions[0]["project"], "work/api")
        self.assertEqual(sessions[1]["project"], "personal/api")
        self.assertEqual(sessions[2]["project"], "frontend")


class TestParseEtime(unittest.TestCase):
    def test_mm_ss(self):
        self.assertEqual(cs.parse_etime("03:42"), 222)

    def test_hh_mm_ss(self):
        self.assertEqual(cs.parse_etime("01:30:00"), 5400)

    def test_dd_hh_mm_ss(self):
        self.assertEqual(cs.parse_etime("2-03:15:30"), 2 * 86400 + 3 * 3600 + 15 * 60 + 30)

    def test_whitespace(self):
        self.assertEqual(cs.parse_etime("  10:05  "), 605)


class TestFormatDuration(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(cs.format_duration(45), "45s")

    def test_minutes(self):
        self.assertEqual(cs.format_duration(120), "2m")

    def test_hours_and_minutes(self):
        self.assertEqual(cs.format_duration(4980), "1h23m")

    def test_hours_exact(self):
        self.assertEqual(cs.format_duration(7200), "2h")

    def test_days_and_hours(self):
        self.assertEqual(cs.format_duration(2 * 86400 + 3 * 3600), "2d3h")

    def test_days_exact(self):
        self.assertEqual(cs.format_duration(86400), "1d")

    def test_none(self):
        self.assertEqual(cs.format_duration(None), "-")

    def test_zero(self):
        self.assertEqual(cs.format_duration(0), "0s")


class TestGetUptime(unittest.TestCase):
    @patch("subprocess.run")
    def test_returns_seconds_and_formatted(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="  02:15:30\n")
        secs, fmt = cs.get_uptime(123)
        self.assertEqual(secs, 2 * 3600 + 15 * 60 + 30)
        self.assertEqual(fmt, "2h15m")

    @patch("subprocess.run")
    def test_process_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        secs, fmt = cs.get_uptime(99999)
        self.assertIsNone(secs)
        self.assertEqual(fmt, "-")

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_ps_not_found(self, _mock):
        secs, fmt = cs.get_uptime(123)
        self.assertIsNone(secs)
        self.assertEqual(fmt, "-")


class TestGetGitBranch(unittest.TestCase):
    @patch("subprocess.run")
    def test_extracts_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        self.assertEqual(cs.get_git_branch("/some/repo"), "main")

    @patch("subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        self.assertIsNone(cs.get_git_branch("/not/a/repo"))

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_installed(self, _mock):
        self.assertIsNone(cs.get_git_branch("/some/dir"))

    def test_none_cwd(self):
        self.assertIsNone(cs.get_git_branch(None))

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=2))
    def test_timeout(self, _mock):
        self.assertIsNone(cs.get_git_branch("/slow/repo"))


class TestFormatTable(unittest.TestCase):
    def test_empty_sessions(self):
        result = cs.format_table([])
        self.assertIn("No active Claude Code sessions found", result)

    @patch.object(cs, "supports_color", return_value=False)
    def test_single_session_no_color(self, _mock):
        sessions = [
            {
                "project": "myproject",
                "status": "active",
                "surface_id": None,
                "tty": "ttys001",
                "branch": "main",
                "uptime": "2h15m",
            }
        ]
        result = cs.format_table(sessions)
        self.assertIn("\u25cf", result)  # active icon
        self.assertIn("myproject", result)
        self.assertIn("main", result)
        self.assertIn("active", result)
        self.assertIn("2h15m", result)
        self.assertIn("ttys001", result)
        self.assertIn("1 session (1 active)", result)

    @patch.object(cs, "supports_color", return_value=False)
    def test_surface_id_shown_when_available(self, _mock):
        sessions = [
            {
                "project": "proj",
                "status": "idle",
                "surface_id": "a1b2c3d4e5f6a7b8",
                "tty": "ttys001",
                "branch": "feature/ui",
                "uptime": "45m",
            }
        ]
        result = cs.format_table(sessions)
        self.assertIn("a1b2c3d4", result)  # truncated to 8 chars
        self.assertNotIn("ttys001", result)  # tty not shown when surface_id exists

    @patch.object(cs, "supports_color", return_value=False)
    def test_no_branch_shows_dash(self, _mock):
        sessions = [
            {
                "project": "proj",
                "status": "idle",
                "surface_id": None,
                "tty": "t1",
                "branch": None,
                "uptime": "5m",
            }
        ]
        result = cs.format_table(sessions)
        self.assertIn("-", result)

    @patch.object(cs, "supports_color", return_value=False)
    def test_summary_counts(self, _mock):
        sessions = [
            {"project": "a", "status": "active", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "1m"},
            {"project": "b", "status": "active", "surface_id": None, "tty": "t2", "branch": "main", "uptime": "2m"},
            {"project": "c", "status": "idle", "surface_id": None, "tty": "t3", "branch": "dev", "uptime": "3m"},
            {"project": "d", "status": "stopped", "surface_id": None, "tty": "t4", "branch": None, "uptime": "4m"},
        ]
        result = cs.format_table(sessions)
        self.assertIn("4 sessions", result)
        self.assertIn("2 active", result)
        self.assertIn("1 idle", result)
        self.assertIn("1 stopped", result)

    @patch.object(cs, "supports_color", return_value=True)
    def test_color_output(self, _mock):
        sessions = [
            {"project": "proj", "status": "active", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "5m"},
        ]
        result = cs.format_table(sessions)
        self.assertIn("\033[32m", result)  # green
        self.assertIn("\033[0m", result)  # reset


class TestFormatJson(unittest.TestCase):
    def test_valid_json(self):
        sessions = [
            {
                "pid": 123,
                "project": "test",
                "cwd": "/tmp/test",
                "status": "active",
                "cpu": 10.5,
                "tty": "ttys000",
                "surface_id": None,
            }
        ]
        result = cs.format_json(sessions)
        parsed = json.loads(result)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["project"], "test")
        self.assertEqual(parsed[0]["status"], "active")

    def test_empty_json(self):
        result = cs.format_json([])
        self.assertEqual(json.loads(result), [])


class TestDiscoverClaudePids(unittest.TestCase):
    @patch("subprocess.run")
    def test_finds_pids(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  123 claude\n  456 claude\n  789 zsh\n",
        )
        pids = cs.discover_claude_pids()
        self.assertEqual(pids, [123, 456])

    @patch("subprocess.run")
    def test_no_processes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="  789 zsh\n")
        pids = cs.discover_claude_pids()
        self.assertEqual(pids, [])

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_ps_not_found(self, _mock):
        pids = cs.discover_claude_pids()
        self.assertEqual(pids, [])


class TestGetProcessInfo(unittest.TestCase):
    @patch("subprocess.run")
    def test_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  123  10.5 R+  ttys000\n  456   0.0 S   ttys001\n",
        )
        info = cs.get_process_info([123, 456])
        self.assertEqual(info[123]["cpu"], 10.5)
        self.assertEqual(info[123]["state"], "R+")
        self.assertEqual(info[123]["tty"], "ttys000")
        self.assertEqual(info[456]["cpu"], 0.0)
        self.assertEqual(info[456]["tty"], "ttys001")

    def test_empty_pids(self):
        info = cs.get_process_info([])
        self.assertEqual(info, {})

    @patch("subprocess.run")
    def test_skips_malformed_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  123  10.5 R+  ttys000\n  bad  NaN S  ttys001\n  short\n",
        )
        info = cs.get_process_info([123])
        self.assertEqual(len(info), 1)
        self.assertIn(123, info)


class TestGetCwd(unittest.TestCase):
    @patch("subprocess.run")
    def test_extracts_cwd(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="p123\nfcwd\nn/Users/test/project\n",
        )
        cwd = cs.get_cwd(123)
        self.assertEqual(cwd, "/Users/test/project")

    @patch("subprocess.run")
    def test_no_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        cwd = cs.get_cwd(123)
        self.assertIsNone(cwd)


class TestGetGhottySurfaceId(unittest.TestCase):
    @patch("subprocess.run")
    def test_extracts_surface_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="123 claude GHOSTTY_SURFACE_ID=a1b2c3d4-e5f6-7890 OTHER_VAR=x\n",
        )
        sid = cs.get_ghostty_surface_id(123)
        self.assertEqual(sid, "a1b2c3d4-e5f6-7890")

    @patch("subprocess.run")
    def test_no_surface_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="123 claude TERM=xterm PATH=/usr/bin\n",
        )
        sid = cs.get_ghostty_surface_id(123)
        self.assertIsNone(sid)


class TestSupportsColor(unittest.TestCase):
    @patch.dict(os.environ, {"NO_COLOR": "1"})
    def test_no_color_env(self):
        self.assertFalse(cs.supports_color())

    @patch.dict(os.environ, {}, clear=True)
    def test_no_tty(self):
        # When stdout is not a TTY (e.g. piped), no color
        with patch.object(sys.stdout, "isatty", return_value=False):
            self.assertFalse(cs.supports_color())


class TestCollectSessions(unittest.TestCase):
    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(120, "2m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value=None)
    @patch.object(cs, "get_cwd", return_value="/home/user/myproject")
    @patch.object(cs, "get_process_info", return_value={
        100: {"cpu": 15.0, "state": "R+", "tty": "ttys000"},
        200: {"cpu": 0.0, "state": "S", "tty": "??"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[100, 200])
    def test_filters_headless(self, *_mocks):
        sessions = cs.collect_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["pid"], 100)
        self.assertEqual(sessions[0]["project"], "myproject")
        self.assertEqual(sessions[0]["status"], "active")
        self.assertEqual(sessions[0]["uptime_seconds"], 120)
        self.assertEqual(sessions[0]["uptime"], "2m")
        self.assertEqual(sessions[0]["branch"], "main")

    @patch.object(cs, "discover_claude_pids", return_value=[])
    def test_no_processes(self, _mock):
        sessions = cs.collect_sessions()
        self.assertEqual(sessions, [])

    @patch.object(cs, "get_git_branch", return_value="dev")
    @patch.object(cs, "get_uptime", return_value=(60, "1m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value=None)
    @patch.object(cs, "get_cwd", side_effect=lambda pid: {
        1: "/home/user/zebra",
        2: "/home/user/alpha",
        3: "/home/user/beta",
    }[pid])
    @patch.object(cs, "get_process_info", return_value={
        1: {"cpu": 0.0, "state": "S", "tty": "ttys000"},
        2: {"cpu": 15.0, "state": "R+", "tty": "ttys001"},
        3: {"cpu": 0.0, "state": "T", "tty": "ttys002"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[1, 2, 3])
    def test_sorted_by_status_then_project(self, *_mocks):
        sessions = cs.collect_sessions()
        self.assertEqual(len(sessions), 3)
        # active first, then idle, then stopped
        self.assertEqual(sessions[0]["status"], "active")
        self.assertEqual(sessions[0]["project"], "alpha")
        self.assertEqual(sessions[1]["status"], "idle")
        self.assertEqual(sessions[1]["project"], "zebra")
        self.assertEqual(sessions[2]["status"], "stopped")
        self.assertEqual(sessions[2]["project"], "beta")


if __name__ == "__main__":
    unittest.main()
