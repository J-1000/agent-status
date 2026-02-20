#!/usr/bin/env python3
"""Tests for agent-status."""

import json
import io
import os
import subprocess
import sys
import unittest
from argparse import Namespace
from unittest.mock import patch, MagicMock

# Import agent-status despite the hyphen and no .py extension
import importlib.machinery
import importlib.util

_loader = importlib.machinery.SourceFileLoader(
    "agent_status",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-status"),
)
_spec = importlib.util.spec_from_loader("agent_status", _loader)
cs = importlib.util.module_from_spec(_spec)
_loader.exec_module(cs)


class TestSendBell(unittest.TestCase):
    def test_writes_bell_to_stdout(self):
        mock_stdout = MagicMock()
        with patch.object(cs.sys, "stdout", mock_stdout):
            cs.send_bell()
        mock_stdout.write.assert_called_once_with("\a")
        mock_stdout.flush.assert_called_once()


class TestSendNotification(unittest.TestCase):
    @patch("subprocess.run")
    def test_calls_osascript_with_project(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        cs.send_notification({"project": "my-api"})
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertIn("display notification", args[2])
        self.assertEqual(args[3], "my-api")

    @patch("subprocess.run")
    def test_project_passed_as_arg_not_interpolated(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        project = 'my-api" & do shell script "echo pwned" & "'
        cs.send_notification({"project": project})
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertIn("item 1 of argv", args[2])
        self.assertEqual(args[3], project)
        self.assertNotIn(project, args[2])

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_osascript_not_found_silenced(self, _mock):
        cs.send_notification({"project": "test"})  # should not raise

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=5))
    def test_osascript_timeout_silenced(self, _mock):
        cs.send_notification({"project": "test"})  # should not raise

    @patch("subprocess.run")
    def test_nonzero_exit_silenced(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        cs.send_notification({"project": "test"})  # should not raise


class TestDetectTransitions(unittest.TestCase):
    def test_active_to_idle_detected(self):
        prev = {100: "active"}
        sessions = [{"pid": 100, "status": "idle"}]
        self.assertEqual(cs.detect_transitions(prev, sessions), {100})

    def test_idle_to_active_ignored(self):
        prev = {100: "idle"}
        sessions = [{"pid": 100, "status": "active"}]
        self.assertEqual(cs.detect_transitions(prev, sessions), set())

    def test_active_to_stopped_ignored(self):
        prev = {100: "active"}
        sessions = [{"pid": 100, "status": "stopped"}]
        self.assertEqual(cs.detect_transitions(prev, sessions), set())

    def test_new_session_ignored(self):
        prev = {}
        sessions = [{"pid": 100, "status": "idle"}]
        self.assertEqual(cs.detect_transitions(prev, sessions), set())

    def test_disappeared_session_ignored(self):
        prev = {100: "active"}
        sessions = []
        self.assertEqual(cs.detect_transitions(prev, sessions), set())

    def test_multiple_transitions(self):
        prev = {100: "active", 200: "active", 300: "idle"}
        sessions = [
            {"pid": 100, "status": "idle"},
            {"pid": 200, "status": "idle"},
            {"pid": 300, "status": "active"},
        ]
        self.assertEqual(cs.detect_transitions(prev, sessions), {100, 200})

    def test_empty_previous(self):
        sessions = [{"pid": 100, "status": "idle"}]
        self.assertEqual(cs.detect_transitions({}, sessions), set())


class TestAlertTransitions(unittest.TestCase):
    @patch.object(cs, "send_notification")
    @patch.object(cs, "send_bell")
    def test_no_transitions_no_calls(self, mock_bell, mock_notif):
        cs.alert_transitions([], set())
        mock_bell.assert_not_called()
        mock_notif.assert_not_called()

    @patch.object(cs, "send_notification")
    @patch.object(cs, "send_bell")
    def test_single_transition(self, mock_bell, mock_notif):
        sessions = [{"pid": 100, "project": "api"}]
        cs.alert_transitions(sessions, {100})
        mock_bell.assert_called_once()
        mock_notif.assert_called_once_with({"pid": 100, "project": "api"})

    @patch.object(cs, "send_notification")
    @patch.object(cs, "send_bell")
    def test_multiple_transitions_one_bell(self, mock_bell, mock_notif):
        sessions = [
            {"pid": 100, "project": "api"},
            {"pid": 200, "project": "web"},
        ]
        cs.alert_transitions(sessions, {100, 200})
        mock_bell.assert_called_once()
        self.assertEqual(mock_notif.call_count, 2)


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

    def test_respects_custom_threshold(self):
        self.assertEqual(cs.classify_status(3.0, "S+", cpu_threshold=2.5), "active")


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

    def test_invalid_format_returns_none(self):
        self.assertIsNone(cs.parse_etime("not-a-time"))

    def test_invalid_numeric_parts_return_none(self):
        self.assertIsNone(cs.parse_etime("2-xx:15:30"))


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

    @patch("subprocess.run")
    def test_malformed_etime_returns_unknown(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="bad-value\n")
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
        self.assertIn("No active Claude/Codex sessions found", result)

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


    @patch.object(cs, "supports_color", return_value=False)
    def test_transition_marker_shown(self, _mock):
        sessions = [
            {"pid": 100, "project": "proj", "status": "idle", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "5m"},
        ]
        result = cs.format_table(sessions, transitioned_pids={100})
        self.assertIn("<- done", result)

    @patch.object(cs, "supports_color", return_value=False)
    def test_no_marker_when_none(self, _mock):
        sessions = [
            {"pid": 100, "project": "proj", "status": "idle", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "5m"},
        ]
        result = cs.format_table(sessions)
        self.assertNotIn("<- done", result)

    @patch.object(cs, "supports_color", return_value=False)
    def test_no_marker_when_empty(self, _mock):
        sessions = [
            {"pid": 100, "project": "proj", "status": "idle", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "5m"},
        ]
        result = cs.format_table(sessions, transitioned_pids=set())
        self.assertNotIn("<- done", result)

    @patch.object(cs, "supports_color", return_value=True)
    def test_transition_marker_color(self, _mock):
        sessions = [
            {"pid": 100, "project": "proj", "status": "idle", "surface_id": None, "tty": "t1", "branch": "main", "uptime": "5m"},
        ]
        result = cs.format_table(sessions, transitioned_pids={100})
        self.assertIn("\033[33m<- done\033[0m", result)


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

    def test_json_v2_envelope(self):
        sessions = [{"pid": 123, "project": "test"}]
        result = cs.format_json_v2(sessions, generated_at="2026-02-20T12:00:00Z")
        parsed = json.loads(result)
        self.assertEqual(parsed["schema_version"], 1)
        self.assertEqual(parsed["generated_at"], "2026-02-20T12:00:00Z")
        self.assertEqual(parsed["sessions"], sessions)


class TestDiscoverClaudePids(unittest.TestCase):
    @patch("subprocess.run")
    def test_finds_pids(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  123 claude\n  456 codex\n  789 zsh\n",
        )
        pids = cs.discover_claude_pids()
        self.assertEqual(pids, [123, 456])

    @patch("subprocess.run")
    def test_ignores_non_target_processes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  111 codex-cli\n  222 claude-helper\n  333 codex\n",
        )
        pids = cs.discover_claude_pids()
        self.assertEqual(pids, [333])

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


class TestGetParentMap(unittest.TestCase):
    @patch("subprocess.run")
    def test_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  123     1\n  456   123\n",
        )
        self.assertEqual(cs.get_parent_map([123, 456]), {123: 1, 456: 123})

    def test_empty_pids(self):
        self.assertEqual(cs.get_parent_map([]), {})

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_ps_not_found(self, _mock):
        self.assertEqual(cs.get_parent_map([123]), {})


class TestDedupeNestedPids(unittest.TestCase):
    def test_nested_child_removed(self):
        pids = [100, 200]
        parent_map = {100: 1, 200: 100}
        self.assertEqual(cs.dedupe_nested_pids(pids, parent_map), [100])

    def test_siblings_retained(self):
        pids = [100, 200]
        parent_map = {100: 1, 200: 1}
        self.assertEqual(cs.dedupe_nested_pids(pids, parent_map), [100, 200])

    def test_handles_parent_cycle(self):
        pids = [100, 200]
        parent_map = {100: 200, 200: 100}
        self.assertEqual(cs.dedupe_nested_pids(pids, parent_map), [])


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


class TestGetCwds(unittest.TestCase):
    @patch("subprocess.run")
    def test_parses_multi_pid_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="p123\nfcwd\nn/Users/test/project\np456\nfcwd\nn/home/user/other\n",
        )
        result = cs.get_cwds([123, 456])
        self.assertEqual(result, {123: "/Users/test/project", 456: "/home/user/other"})

    def test_empty_pids(self):
        result = cs.get_cwds([])
        self.assertEqual(result, {})

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_lsof_not_found(self, _mock):
        result = cs.get_cwds([123])
        self.assertEqual(result, {})

    @patch("subprocess.run")
    def test_lsof_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = cs.get_cwds([123])
        self.assertEqual(result, {})

    @patch("subprocess.run")
    def test_pid_with_no_cwd_line(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="p123\nfcwd\nn/Users/test/project\np456\n",
        )
        result = cs.get_cwds([123, 456])
        self.assertEqual(result, {123: "/Users/test/project"})


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

    @patch("subprocess.run")
    def test_falls_back_to_eww_command(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="123 claude TERM=xterm\n"),
            MagicMock(returncode=0, stdout="123 claude GHOSTTY_SURFACE_ID=deadbeef-1111\n"),
        ]
        sid = cs.get_ghostty_surface_id(123)
        self.assertEqual(sid, "deadbeef-1111")
        self.assertEqual(mock_run.call_count, 2)


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
    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(120, "2m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value=None)
    @patch.object(cs, "get_cwds", return_value={100: "/home/user/myproject"})
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

    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "discover_claude_pids", return_value=[])
    def test_no_processes(self, *_mocks):
        sessions = cs.collect_sessions()
        self.assertEqual(sessions, [])

    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "get_git_branch", return_value="dev")
    @patch.object(cs, "get_uptime", return_value=(60, "1m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value=None)
    @patch.object(cs, "get_cwds", return_value={
        1: "/home/user/zebra",
        2: "/home/user/alpha",
        3: "/home/user/beta",
    })
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

    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(60, "1m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value="surf-abc")
    @patch.object(cs, "get_cwds", return_value={100: "/home/user/proj"})
    @patch.object(cs, "get_process_info", return_value={
        100: {"cpu": 5.0, "state": "R+", "tty": "ttys000"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[100])
    def test_cache_populated_on_first_call(self, *_mocks):
        cache = {}
        cs.collect_sessions(cache=cache)
        self.assertIn(100, cache)
        self.assertEqual(cache[100]["cwd"], "/home/user/proj")
        self.assertEqual(cache[100]["surface_id"], "surf-abc")

    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(60, "1m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value="surf-abc")
    @patch.object(cs, "get_cwds", return_value={})
    @patch.object(cs, "get_process_info", return_value={
        100: {"cpu": 5.0, "state": "R+", "tty": "ttys000"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[100])
    def test_cache_reused_on_second_call(self, mock_pids, mock_info, mock_cwds, mock_sid, *_):
        cache = {100: {"cwd": "/home/user/proj", "surface_id": "surf-abc"}}
        sessions = cs.collect_sessions(cache=cache)
        # get_cwds should NOT be called (no new PIDs)
        mock_cwds.assert_not_called()
        # get_ghostty_surface_id should NOT be called (cached)
        mock_sid.assert_not_called()
        self.assertEqual(sessions[0]["cwd"], "/home/user/proj")
        self.assertEqual(sessions[0]["surface_id"], "surf-abc")

    @patch.object(cs, "get_parent_map", return_value={})
    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(60, "1m"))
    @patch.object(cs, "get_ghostty_surface_id", return_value=None)
    @patch.object(cs, "get_cwds", return_value={})
    @patch.object(cs, "get_process_info", return_value={
        200: {"cpu": 0.0, "state": "S", "tty": "ttys001"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[200])
    def test_stale_pids_pruned_from_cache(self, *_mocks):
        cache = {
            100: {"cwd": "/old/path", "surface_id": "old-surf"},
            200: {"cwd": "/home/user/proj", "surface_id": None},
        }
        cs.collect_sessions(cache=cache)
        self.assertNotIn(100, cache)
        self.assertIn(200, cache)

    @patch.object(cs, "get_git_branch", return_value="main")
    @patch.object(cs, "get_uptime", return_value=(120, "2m"))
    @patch.object(cs, "get_ghostty_surface_id", side_effect=[None, None])
    @patch.object(cs, "get_cwds", return_value={100: "/home/user/proj", 200: "/home/user/proj"})
    @patch.object(cs, "get_parent_map", return_value={100: 1, 200: 100})
    @patch.object(cs, "get_process_info", return_value={
        100: {"cpu": 15.0, "state": "R+", "tty": "ttys000"},
        200: {"cpu": 10.0, "state": "R+", "tty": "ttys000"},
    })
    @patch.object(cs, "discover_claude_pids", return_value=[100, 200])
    def test_dedupes_nested_sessions(self, *_mocks):
        sessions = cs.collect_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["pid"], 100)


class TestFocusGhottySurface(unittest.TestCase):
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(cs.focus_ghostty_surface("abc-123"))
        mock_run.assert_called_once_with(
            ["open", "ghostty://present-surface/abc-123"],
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(cs.focus_ghostty_surface("abc-123"))

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_open_not_found(self, _mock):
        self.assertFalse(cs.focus_ghostty_surface("abc-123"))


class TestParseArgs(unittest.TestCase):
    @patch("sys.argv", ["agent-status", "--alert"])
    def test_alert_flag_true(self):
        args = cs.parse_args()
        self.assertTrue(args.alert)

    @patch("sys.argv", ["agent-status"])
    def test_alert_flag_default_false(self):
        args = cs.parse_args()
        self.assertFalse(args.alert)

    @patch("sys.argv", ["agent-status", "--interval", "0"])
    def test_interval_zero_rejected(self):
        with patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cs.parse_args()

    @patch("sys.argv", ["agent-status", "--interval", "-1"])
    def test_interval_negative_rejected(self):
        with patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cs.parse_args()

    @patch("sys.argv", ["agent-status", "--cpu-threshold", "2.5"])
    def test_cpu_threshold_flag(self):
        args = cs.parse_args()
        self.assertEqual(args.cpu_threshold, 2.5)

    @patch("sys.argv", ["agent-status", "--cpu-threshold", "-0.1"])
    def test_cpu_threshold_negative_rejected(self):
        with patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cs.parse_args()

    @patch("sys.argv", ["agent-status", "--json-v2"])
    def test_json_v2_flag(self):
        args = cs.parse_args()
        self.assertTrue(args.json_v2)

    @patch("sys.argv", ["agent-status", "--interval-active", "0.5", "--interval-idle", "5"])
    def test_adaptive_interval_flags(self):
        args = cs.parse_args()
        self.assertEqual(args.interval_active, 0.5)
        self.assertEqual(args.interval_idle, 5.0)

    @patch("sys.argv", ["agent-status", "--interval-active", "0"])
    def test_interval_active_zero_rejected(self):
        with patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cs.parse_args()

    @patch("sys.argv", ["agent-status", "--interval-idle", "-1"])
    def test_interval_idle_negative_rejected(self):
        with patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cs.parse_args()


class TestResolveWatchInterval(unittest.TestCase):
    def _args(self, interval=2.0, interval_active=None, interval_idle=None):
        return Namespace(
            interval=interval,
            interval_active=interval_active,
            interval_idle=interval_idle,
        )

    def test_defaults_to_base_interval(self):
        args = self._args(interval=2.0)
        sessions = [{"status": "idle"}]
        self.assertEqual(cs.resolve_watch_interval(args, sessions), 2.0)

    def test_uses_active_interval_when_active_present(self):
        args = self._args(interval=2.0, interval_active=0.5)
        sessions = [{"status": "active"}, {"status": "idle"}]
        self.assertEqual(cs.resolve_watch_interval(args, sessions), 0.5)

    def test_uses_idle_interval_when_no_active(self):
        args = self._args(interval=2.0, interval_idle=5.0)
        sessions = [{"status": "idle"}, {"status": "stopped"}]
        self.assertEqual(cs.resolve_watch_interval(args, sessions), 5.0)

    def test_empty_sessions_use_idle_interval_if_set(self):
        args = self._args(interval=2.0, interval_idle=6.0)
        self.assertEqual(cs.resolve_watch_interval(args, []), 6.0)


class TestResolveCpuThreshold(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_uses_default_when_no_arg_or_env(self):
        args = Namespace(cpu_threshold=None)
        self.assertEqual(cs.resolve_cpu_threshold(args), cs.DEFAULT_CPU_THRESHOLD)

    @patch.dict(os.environ, {cs.CPU_THRESHOLD_ENV_VAR: "2.25"}, clear=True)
    def test_uses_env_when_arg_missing(self):
        args = Namespace(cpu_threshold=None)
        self.assertEqual(cs.resolve_cpu_threshold(args), 2.25)

    @patch.dict(os.environ, {cs.LEGACY_CPU_THRESHOLD_ENV_VAR: "1.75"}, clear=True)
    def test_uses_legacy_env_when_new_var_missing(self):
        args = Namespace(cpu_threshold=None)
        self.assertEqual(cs.resolve_cpu_threshold(args), 1.75)

    @patch.dict(os.environ, {cs.CPU_THRESHOLD_ENV_VAR: "oops"}, clear=True)
    @patch.object(cs.sys, "stderr", new_callable=io.StringIO)
    def test_invalid_env_falls_back_to_default(self, mock_stderr):
        args = Namespace(cpu_threshold=None)
        self.assertEqual(cs.resolve_cpu_threshold(args), cs.DEFAULT_CPU_THRESHOLD)
        self.assertIn("Ignoring invalid", mock_stderr.getvalue())

    @patch.dict(os.environ, {cs.CPU_THRESHOLD_ENV_VAR: "-1"}, clear=True)
    @patch.object(cs.sys, "stderr", new_callable=io.StringIO)
    def test_negative_env_falls_back_to_default(self, mock_stderr):
        args = Namespace(cpu_threshold=None)
        self.assertEqual(cs.resolve_cpu_threshold(args), cs.DEFAULT_CPU_THRESHOLD)
        self.assertIn("Ignoring invalid", mock_stderr.getvalue())

    @patch.dict(os.environ, {cs.CPU_THRESHOLD_ENV_VAR: "1.5"}, clear=True)
    def test_arg_wins_over_env(self):
        args = Namespace(cpu_threshold=4.0)
        self.assertEqual(cs.resolve_cpu_threshold(args), 4.0)


class TestHandleGoto(unittest.TestCase):
    def _make_session(self, project, surface_id="surf-1234"):
        return {
            "pid": 100,
            "project": project,
            "cwd": f"/home/user/{project}",
            "branch": "main",
            "status": "active",
            "cpu": 10.0,
            "tty": "ttys000",
            "surface_id": surface_id,
            "uptime_seconds": 60,
            "uptime": "1m",
        }

    @patch.object(cs, "focus_ghostty_surface", return_value=True)
    @patch.object(cs, "collect_sessions")
    def test_exact_match_focuses(self, mock_collect, mock_focus):
        mock_collect.return_value = [self._make_session("api-server")]
        result = cs.handle_goto("api-server")
        self.assertEqual(result, 0)
        mock_focus.assert_called_once_with("surf-1234")

    @patch.object(cs, "focus_ghostty_surface", return_value=True)
    @patch.object(cs, "collect_sessions")
    def test_case_insensitive_substring(self, mock_collect, mock_focus):
        mock_collect.return_value = [self._make_session("api-server")]
        result = cs.handle_goto("API")
        self.assertEqual(result, 0)
        mock_focus.assert_called_once_with("surf-1234")

    @patch.object(cs, "focus_ghostty_surface", return_value=True)
    @patch.object(cs, "collect_sessions")
    def test_exact_match_beats_other_prefix_matches(self, mock_collect, mock_focus):
        mock_collect.return_value = [
            self._make_session("api"),
            self._make_session("api-server"),
            self._make_session("api-worker"),
        ]
        result = cs.handle_goto("api")
        self.assertEqual(result, 0)
        mock_focus.assert_called_once_with("surf-1234")

    @patch.object(cs, "collect_sessions")
    def test_no_match(self, mock_collect):
        mock_collect.return_value = [self._make_session("api-server")]
        result = cs.handle_goto("nonexistent")
        self.assertEqual(result, 1)

    @patch.object(cs, "collect_sessions")
    def test_multiple_matches(self, mock_collect):
        mock_collect.return_value = [
            self._make_session("api-server"),
            self._make_session("api-worker"),
        ]
        result = cs.handle_goto("api")
        self.assertEqual(result, 1)

    @patch.object(cs, "collect_sessions")
    def test_no_surface_id(self, mock_collect):
        mock_collect.return_value = [self._make_session("api-server", surface_id=None)]
        result = cs.handle_goto("api-server")
        self.assertEqual(result, 1)


class TestFindProjectMatches(unittest.TestCase):
    def setUp(self):
        self.sessions = [
            {"project": "api"},
            {"project": "api-server"},
            {"project": "worker-api"},
            {"project": "frontend"},
        ]

    def test_prefers_exact_matches(self):
        mode, matches = cs.find_project_matches(self.sessions, "api")
        self.assertEqual(mode, "exact")
        self.assertEqual([s["project"] for s in matches], ["api"])

    def test_uses_prefix_when_no_exact(self):
        mode, matches = cs.find_project_matches(self.sessions, "front")
        self.assertEqual(mode, "prefix")
        self.assertEqual([s["project"] for s in matches], ["frontend"])

    def test_uses_substring_when_no_prefix(self):
        mode, matches = cs.find_project_matches(self.sessions, "ker-a")
        self.assertEqual(mode, "substring")
        self.assertEqual([s["project"] for s in matches], ["worker-api"])

    def test_returns_none_for_empty_query(self):
        mode, matches = cs.find_project_matches(self.sessions, "   ")
        self.assertIsNone(mode)
        self.assertEqual(matches, [])


class TestMainWatchBehavior(unittest.TestCase):
    @patch.object(cs.sys, "stdout", new_callable=MagicMock)
    @patch.object(cs.time, "sleep", side_effect=KeyboardInterrupt)
    @patch.object(cs, "format_json", return_value="[]\n")
    @patch.object(cs, "collect_sessions", return_value=[])
    @patch.object(cs, "clear_screen")
    @patch.object(cs, "parse_args", return_value=Namespace(
        watch=True, interval=1.0, interval_active=None, interval_idle=None,
        json_output=True, json_v2=False, alert=False, goto=None, cpu_threshold=None
    ))
    def test_watch_json_does_not_clear_screen(
        self, _mock_args, mock_clear, _mock_collect, _mock_format_json, _mock_sleep, _mock_stdout
    ):
        cs.main()
        mock_clear.assert_not_called()

    @patch.object(cs.sys, "stdout", new_callable=MagicMock)
    @patch.object(cs.time, "sleep", side_effect=KeyboardInterrupt)
    @patch.object(cs, "format_table", return_value="table\n")
    @patch.object(cs, "collect_sessions", return_value=[])
    @patch.object(cs, "clear_screen")
    @patch.object(cs, "parse_args", return_value=Namespace(
        watch=True, interval=1.0, interval_active=None, interval_idle=None,
        json_output=False, json_v2=False, alert=False, goto=None, cpu_threshold=None
    ))
    def test_watch_table_clears_screen(
        self, _mock_args, mock_clear, _mock_collect, _mock_format_table, _mock_sleep, _mock_stdout
    ):
        cs.main()
        mock_clear.assert_called_once()

    @patch.object(cs.sys, "stdout", new_callable=MagicMock)
    @patch.object(cs.time, "sleep", side_effect=KeyboardInterrupt)
    @patch.object(cs, "format_json_v2", return_value="{}\n")
    @patch.object(cs, "collect_sessions", return_value=[])
    @patch.object(cs, "clear_screen")
    @patch.object(cs, "parse_args", return_value=Namespace(
        watch=True, interval=1.0, interval_active=None, interval_idle=None,
        json_output=False, json_v2=True, alert=False, goto=None, cpu_threshold=None
    ))
    def test_watch_json_v2_does_not_clear_screen(
        self, _mock_args, mock_clear, _mock_collect, mock_format_json_v2, _mock_sleep, _mock_stdout
    ):
        cs.main()
        mock_clear.assert_not_called()
        mock_format_json_v2.assert_called_once()


if __name__ == "__main__":
    unittest.main()
