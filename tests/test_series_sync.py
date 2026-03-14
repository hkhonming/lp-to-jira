import json
import os
import tempfile
import pytest
from unittest.mock import Mock, call, patch

from LpToJira.lp_to_jira import (
    is_series_in_jira,
    sync_series_to_jira,
    lp_to_jira_bug,
    main,
)
from LpToJira.lp_bug import ubuntu_devel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bug(tasks):
    """Build a minimal Mock LP bug with the given list of (target_name, status) pairs."""
    bug = Mock()
    bug.id = 111111
    bug.title = "Test Series Bug"
    bug.description = "A bug description"
    bug.web_link = "https://bugs.launchpad.net/bugs/111111"
    bug.tags = []
    bug.bug_tasks = [
        Mock(bug_target_name=name, status=status, importance="Medium")
        for name, status in tasks
    ]
    return bug


def _make_jira(search_result=None):
    jira = Mock()
    jira.search_issues = Mock(return_value=search_result)
    jira.create_issue = Mock(return_value=Mock(key="TEST-200", id="200"))
    jira.client_info = Mock(return_value="https://jira.example.com")
    jira.add_simple_link = Mock()
    return jira


# ---------------------------------------------------------------------------
# is_series_in_jira
# ---------------------------------------------------------------------------

def test_is_series_in_jira_not_found():
    """Returns (False, None) when no matching subtask exists."""
    bug = Mock()
    bug.id = 42
    jira = Mock()
    jira.search_issues = Mock(return_value=None)

    found, issue = is_series_in_jira(jira, bug, "systemd (Ubuntu Focal)", "PROJ")

    assert found is False
    assert issue is None
    jira.search_issues.assert_called_once()


def test_is_series_in_jira_found_matching_summary():
    """Returns (True, issue) when a subtask with matching summary exists."""
    bug = Mock()
    bug.id = 42
    jira = Mock()

    matching_issue = Mock()
    matching_issue.fields.summary = "LP#42 [systemd (Ubuntu Focal)] Some bug title"
    jira.search_issues = Mock(return_value=[matching_issue])

    found, issue = is_series_in_jira(jira, bug, "systemd (Ubuntu Focal)", "PROJ")

    assert found is True
    assert issue is matching_issue


def test_is_series_in_jira_found_different_task_not_matched():
    """Returns (False, None) when subtasks exist but none match this task_name."""
    bug = Mock()
    bug.id = 42
    jira = Mock()

    other_issue = Mock()
    other_issue.fields.summary = "LP#42 [systemd (Ubuntu Bionic)] Some bug title"
    jira.search_issues = Mock(return_value=[other_issue])

    found, issue = is_series_in_jira(jira, bug, "systemd (Ubuntu Focal)", "PROJ")

    assert found is False
    assert issue is None


# ---------------------------------------------------------------------------
# sync_series_to_jira
# ---------------------------------------------------------------------------

def test_sync_series_creates_subtasks_for_ubuntu_tasks():
    """Creates one subtask per Ubuntu series task."""
    bug = _make_bug([
        ("systemd (Ubuntu Focal)", "New"),
        ("systemd (Ubuntu Bionic)", "Fix Released"),
        ("vim (Debian)", "New"),         # non-Ubuntu → skip
    ])
    jira = _make_jira(search_result=None)  # no existing subtasks
    parent = Mock()
    parent.key = "TEST-100"

    sync_series_to_jira(jira, bug, parent, "TEST", {})

    assert jira.create_issue.call_count == 2
    created_summaries = [
        c.kwargs["fields"]["summary"]
        for c in jira.create_issue.call_args_list
    ]
    assert any("Ubuntu Focal" in s for s in created_summaries)
    assert any("Ubuntu Bionic" in s for s in created_summaries)
    # Debian task must not appear
    assert not any("Debian" in s for s in created_summaries)


def test_sync_series_skips_unknown_series():
    """Tasks with unknown series names are silently skipped."""
    bug = _make_bug([
        ("systemd (Ubuntu Focal)", "New"),
        ("systemd (Ubuntu NoSuchSeries)", "New"),  # unknown → skip
    ])
    jira = _make_jira(search_result=None)
    parent = Mock()
    parent.key = "TEST-100"

    sync_series_to_jira(jira, bug, parent, "TEST", {})

    assert jira.create_issue.call_count == 1


def test_sync_series_includes_devel_series():
    """The generic '(Ubuntu)' task is treated as the development series."""
    bug = _make_bug([
        ("casper (Ubuntu)", "New"),                   # → ubuntu_devel
        ("casper (Ubuntu " + ubuntu_devel + ")", "New"),  # explicit devel
    ])
    jira = _make_jira(search_result=None)
    parent = Mock()
    parent.key = "TEST-100"

    sync_series_to_jira(jira, bug, parent, "TEST", {})

    # Both map to ubuntu_devel; the first one inserts, second is also inserted
    # (they have different task_name strings so both get created)
    assert jira.create_issue.call_count == 2


def test_sync_series_skips_existing_subtask(capsys):
    """Does not create a subtask when one already exists for that series."""
    bug = _make_bug([("systemd (Ubuntu Focal)", "New")])
    existing = Mock()
    existing.key = "TEST-50"
    existing.fields.summary = "LP#111111 [systemd (Ubuntu Focal)] Test Series Bug"
    jira = _make_jira(search_result=[existing])
    parent = Mock()
    parent.key = "TEST-100"

    sync_series_to_jira(jira, bug, parent, "TEST", {})

    jira.create_issue.assert_not_called()
    captured = capsys.readouterr()
    assert "already exists" in captured.out
    assert "TEST-50" in captured.out


def test_sync_series_dry_run_no_creation(capsys):
    """In dry-run mode subtasks are printed but never created."""
    bug = _make_bug([
        ("systemd (Ubuntu Focal)", "New"),
        ("systemd (Ubuntu Bionic)", "New"),
    ])
    jira = _make_jira(search_result=None)

    sync_series_to_jira(jira, bug, None, "TEST", {}, dry_run=True)

    jira.create_issue.assert_not_called()
    captured = capsys.readouterr()
    assert "(dry-run)" in captured.out
    assert "Ubuntu Focal" in captured.out
    assert "Ubuntu Bionic" in captured.out


def test_sync_series_transitions_status():
    """Transitions the new subtask to the mapped JIRA status."""
    bug = _make_bug([("systemd (Ubuntu Focal)", "Fix Released")])
    jira = _make_jira(search_result=None)
    parent = Mock()
    parent.key = "TEST-100"
    status_map = {"Fix Released": "Done", "New": "To Do"}

    sync_series_to_jira(jira, bug, parent, "TEST", status_map)

    jira.transition_issue.assert_called_once_with(
        jira.create_issue.return_value, transition="Done")


def test_sync_series_transition_exception_is_caught(capsys):
    """A failed status transition is logged but does not abort the sync."""
    bug = _make_bug([("systemd (Ubuntu Focal)", "Fix Released")])
    jira = _make_jira(search_result=None)
    jira.transition_issue = Mock(side_effect=Exception("transition failed"))
    parent = Mock()
    parent.key = "TEST-100"
    status_map = {"Fix Released": "Done"}

    sync_series_to_jira(jira, bug, parent, "TEST", status_map)

    captured = capsys.readouterr()
    assert "Could not set status" in captured.out


def test_sync_series_subtask_summary_format():
    """Subtask summary includes LP id, task name in brackets, and bug title."""
    bug = _make_bug([("systemd (Ubuntu Focal)", "New")])
    jira = _make_jira(search_result=None)
    parent = Mock()
    parent.key = "TEST-100"

    sync_series_to_jira(jira, bug, parent, "TEST", {})

    fields = jira.create_issue.call_args.kwargs["fields"]
    assert fields["summary"] == "LP#111111 [systemd (Ubuntu Focal)] Test Series Bug"
    assert fields["issuetype"] == {"name": "Sub-task"}
    assert fields["parent"] == {"key": "TEST-100"}


# ---------------------------------------------------------------------------
# lp_to_jira_bug with sync_all_series
# ---------------------------------------------------------------------------

def _make_opts(sync_all_series=True, dry_run=False):
    opts = Mock()
    opts.user_map = {}
    opts.status_map = {}
    opts.priority_map = {}
    opts.sync_milestone = False
    opts.sync_all_series = sync_all_series
    opts.sync_unmapped_users = False
    opts.dry_run = dry_run
    opts.label = None
    opts.no_lp_tag = True
    opts.lp_link = False
    opts.epic = None
    return opts


def test_lp_to_jira_bug_sync_all_series_disabled():
    """When sync_all_series is False, no subtask search or creation occurs."""
    lp = Mock()
    jira = _make_jira(search_result=None)
    bug = _make_bug([("systemd (Ubuntu Focal)", "New")])
    opts = _make_opts(sync_all_series=False)
    sync = {"jira_project": "TEST"}

    lp_to_jira_bug(lp, jira, bug, sync, opts)

    # create_issue is called once for the parent; search_issues once for parent check
    # No second search_issues call for subtask lookup
    for c in jira.search_issues.call_args_list:
        assert "Sub-task" not in str(c)


def test_lp_to_jira_bug_sync_all_series_enabled_new_issue():
    """With sync_all_series=True, subtasks are created for all Ubuntu series."""
    lp = Mock()
    jira = _make_jira(search_result=None)
    # First call (is_bug_in_jira) → no existing parent
    # Subsequent calls (is_series_in_jira) → no existing subtasks
    jira.search_issues = Mock(return_value=None)
    parent_issue = Mock(key="TEST-10", id="10")
    series_issue1 = Mock(key="TEST-11", id="11")
    series_issue2 = Mock(key="TEST-12", id="12")
    jira.create_issue = Mock(side_effect=[parent_issue, series_issue1, series_issue2])

    bug = _make_bug([
        ("systemd (Ubuntu Focal)", "New"),
        ("systemd (Ubuntu Bionic)", "New"),
        ("vim (Debian)", "New"),          # non-Ubuntu → skip
    ])
    opts = _make_opts(sync_all_series=True)
    sync = {"jira_project": "TEST"}

    lp_to_jira_bug(lp, jira, bug, sync, opts)

    # Parent + 2 series subtasks
    assert jira.create_issue.call_count == 3
    subtask_calls = jira.create_issue.call_args_list[1:]
    subtask_summaries = [c.kwargs["fields"]["summary"] for c in subtask_calls]
    assert any("Ubuntu Focal" in s for s in subtask_summaries)
    assert any("Ubuntu Bionic" in s for s in subtask_summaries)


def test_lp_to_jira_bug_sync_all_series_existing_issue():
    """With sync_all_series=True and an existing parent, subtasks are synced."""
    lp = Mock()
    jira = _make_jira()
    parent_issue = Mock(key="TEST-10", id="10")
    parent_issue.fields.assignee = None
    parent_issue.fields.status.name = "To Do"
    parent_issue.fields.priority = None
    # First search returns the existing parent issue
    series_issue = Mock(key="TEST-11", id="11")
    jira.search_issues = Mock(side_effect=[
        [parent_issue],  # is_bug_in_jira finds parent
        None,            # is_series_in_jira for Focal → not found
    ])
    jira.create_issue = Mock(return_value=series_issue)

    bug = _make_bug([("systemd (Ubuntu Focal)", "New")])
    opts = _make_opts(sync_all_series=True)
    opts.status_map = {"New": "To Do"}
    sync = {"jira_project": "TEST"}

    lp_to_jira_bug(lp, jira, bug, sync, opts)

    jira.create_issue.assert_called_once()
    fields = jira.create_issue.call_args.kwargs["fields"]
    assert fields["parent"] == {"key": "TEST-10"}
    assert "Ubuntu Focal" in fields["summary"]


def test_lp_to_jira_bug_sync_all_series_dry_run(capsys):
    """With dry_run=True and sync_all_series=True, only prints are made."""
    lp = Mock()
    jira = _make_jira(search_result=None)
    bug = _make_bug([("systemd (Ubuntu Focal)", "New")])
    opts = _make_opts(sync_all_series=True, dry_run=True)
    sync = {"jira_project": "TEST"}

    lp_to_jira_bug(lp, jira, bug, sync, opts)

    jira.create_issue.assert_not_called()
    captured = capsys.readouterr()
    assert "(dry-run)" in captured.out
    assert "Ubuntu Focal" in captured.out


# ---------------------------------------------------------------------------
# Config JSON loading: sync_all_series
# ---------------------------------------------------------------------------

def _write_config(config_dict):
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(config_dict, tmp)
    tmp.flush()
    tmp.close()
    return tmp.name


def _make_mock_infra():
    mock_lp = Mock()
    mock_jira = Mock()
    mock_jira_api = Mock()
    mock_jira_api.server = "https://jira.example.com"
    mock_jira_api.login = "user"
    mock_jira_api.token = "token"
    return mock_lp, mock_jira, mock_jira_api


def _make_fake_tasks():
    fake_bug = Mock()
    fake_bug_task = Mock()
    fake_bug_task.bug = fake_bug
    fake_tasks = Mock()
    fake_tasks.__iter__ = Mock(return_value=iter([fake_bug_task]))
    return fake_tasks


def test_config_json_sync_all_series_true():
    """sync_all_series=true in config JSON is reflected in opts."""
    config = {
        "sync_all_series": True,
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "comp"}]
    }
    config_path = _write_config(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()
    captured_opts = []

    def capture(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks",
                   return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    assert captured_opts[0].sync_all_series is True


def test_config_json_sync_all_series_false():
    """sync_all_series=false in config JSON keeps the feature disabled."""
    config = {
        "sync_all_series": False,
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "comp"}]
    }
    config_path = _write_config(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()
    captured_opts = []

    def capture(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks",
                   return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    assert captured_opts[0].sync_all_series is False


def test_config_json_sync_all_series_omitted():
    """Omitting sync_all_series in config JSON defaults to False."""
    config = {
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "comp"}]
    }
    config_path = _write_config(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()
    captured_opts = []

    def capture(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks",
                   return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    assert captured_opts[0].sync_all_series is False
