import json
import os
import tempfile
import pytest
from unittest.mock import Mock, patch

from LpToJira.lp_to_jira import (
    get_lp_bug_milestone,
    ensure_jira_version,
    sync_milestone_to_jira,
    lp_to_jira_bug,
    main
)


def test_get_lp_bug_milestone_with_milestone():
    """Test extracting milestone from a bug that has one"""
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    assert get_lp_bug_milestone(bug) == "ubuntu-22.04"


def test_get_lp_bug_milestone_without_milestone():
    """Test extracting milestone from a bug without one"""
    bug = Mock()
    task = Mock()
    task.milestone = None
    bug.bug_tasks = [task]
    
    assert get_lp_bug_milestone(bug) is None


def test_get_lp_bug_milestone_no_milestone_attribute():
    """Test extracting milestone when task doesn't have milestone attribute"""
    bug = Mock()
    task = Mock(spec=[])  # Task without milestone attribute
    bug.bug_tasks = [task]
    
    assert get_lp_bug_milestone(bug) is None


def test_get_lp_bug_milestone_multiple_tasks():
    """Test extracting milestone from bug with multiple tasks"""
    bug = Mock()
    
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    
    task1 = Mock()
    task1.milestone = None
    
    task2 = Mock()
    task2.milestone = milestone
    
    bug.bug_tasks = [task1, task2]
    
    assert get_lp_bug_milestone(bug) == "ubuntu-22.04"


def test_ensure_jira_version_existing():
    """Test ensuring a version that already exists"""
    jira = Mock()
    existing_version = Mock()
    existing_version.name = "ubuntu-22.04"
    
    jira.get_project_version_by_name = Mock(return_value=existing_version)
    
    result = ensure_jira_version(jira, "TEST", "ubuntu-22.04")
    
    assert result == existing_version
    jira.get_project_version_by_name.assert_called_once_with("TEST", "ubuntu-22.04")
    jira.create_version.assert_not_called()


def test_ensure_jira_version_create_new():
    """Test creating a new version when it doesn't exist"""
    jira = Mock()
    jira.get_project_version_by_name = Mock(side_effect=Exception("Not found"))
    
    new_version = Mock()
    new_version.name = "ubuntu-22.04"
    jira.create_version = Mock(return_value=new_version)
    
    result = ensure_jira_version(jira, "TEST", "ubuntu-22.04")
    
    assert result == new_version
    jira.create_version.assert_called_once()
    call_args = jira.create_version.call_args
    assert call_args.kwargs['name'] == "ubuntu-22.04"
    assert call_args.kwargs['project'] == "TEST"


def test_ensure_jira_version_dry_run():
    """Test ensuring a version in dry-run mode"""
    jira = Mock()
    jira.get_project_version_by_name = Mock(side_effect=Exception("Not found"))
    
    result = ensure_jira_version(jira, "TEST", "ubuntu-22.04", dry_run=True)
    
    assert result is None
    jira.create_version.assert_not_called()


def test_ensure_jira_version_none_name():
    """Test ensuring a version with None name"""
    jira = Mock()
    
    result = ensure_jira_version(jira, "TEST", None)
    
    assert result is None
    jira.get_project_version_by_name.assert_not_called()


def test_sync_milestone_to_jira_no_milestone():
    """Test syncing when bug has no milestone"""
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(milestone=None)]
    issue = Mock()
    
    sync_milestone_to_jira(jira, bug, issue, "TEST")
    
    # Should not attempt to update issue
    issue.update.assert_not_called()


def test_sync_milestone_to_jira_with_milestone():
    """Test syncing a milestone to JIRA"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup JIRA version
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Setup issue without the milestone
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    issue.fields.fixVersions = []
    
    sync_milestone_to_jira(jira, bug, issue, "TEST")
    
    # Should update the issue with the milestone
    issue.update.assert_called_once()
    call_args = issue.update.call_args
    assert 'fixVersions' in call_args.kwargs['fields']
    assert call_args.kwargs['fields']['fixVersions'] == [{'name': 'ubuntu-22.04'}]


def test_sync_milestone_to_jira_already_has_milestone():
    """Test syncing when issue already has the milestone"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup JIRA version
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Setup issue that already has the milestone
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    existing_version = Mock()
    existing_version.name = "ubuntu-22.04"
    issue.fields.fixVersions = [existing_version]
    
    sync_milestone_to_jira(jira, bug, issue, "TEST")
    
    # Should not update the issue since it already has the milestone
    issue.update.assert_not_called()


def test_sync_milestone_to_jira_dry_run():
    """Test syncing in dry-run mode"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup issue
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    issue.fields.fixVersions = []
    
    sync_milestone_to_jira(jira, bug, issue, "TEST", dry_run=True)
    
    # Should not update the issue in dry-run mode
    issue.update.assert_not_called()


def test_sync_milestone_to_jira_add_to_existing():
    """Test syncing milestone when issue has other versions"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup JIRA version
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Setup issue with a different version
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    existing_version = Mock()
    existing_version.name = "ubuntu-20.04"
    issue.fields.fixVersions = [existing_version]
    
    sync_milestone_to_jira(jira, bug, issue, "TEST")
    
    # Should add the new milestone while keeping existing ones
    issue.update.assert_called_once()
    call_args = issue.update.call_args
    fix_versions = call_args.kwargs['fields']['fixVersions']
    assert len(fix_versions) == 2
    # Both versions should be dictionaries for proper JSON serialization
    assert fix_versions[0] == {'name': 'ubuntu-20.04'}
    assert fix_versions[1] == {'name': 'ubuntu-22.04'}


def test_lp_to_jira_bug_milestone_disabled_by_default():
    """Test that milestone sync is disabled by default"""
    lp = Mock()
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    bug.id = 123456
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    task.bug_target_name = "systemd (Ubuntu)"
    bug.bug_tasks = [task]
    bug.tags = []
    bug.web_link = "https://example.com"
    bug.title = "Test Bug"
    bug.description = "Test Description"
    
    # Mock JIRA search to return no existing issue
    jira.search_issues = Mock(return_value=None)
    jira.create_issue = Mock(return_value=Mock(key="TEST-123", id="123"))
    jira.add_simple_link = Mock()
    jira.client_info = Mock(return_value="https://jira.example.com")
    
    # Create opts with sync_milestone disabled
    opts = Mock()
    opts.dry_run = False
    opts.label = None
    opts.no_lp_tag = True
    opts.lp_link = False
    opts.sync_milestone = False  # Disabled by default
    opts.user_map = {}
    opts.status_map = {}
    opts.priority_map = {}
    opts.epic = None
    
    sync = {'jira_project': 'TEST'}
    
    # Call lp_to_jira_bug
    lp_to_jira_bug(lp, jira, bug, sync, opts)
    
    # Verify that issue was created
    jira.create_issue.assert_called_once()
    # Verify that get_project_version_by_name was not called (milestone sync didn't run)
    if hasattr(jira, 'get_project_version_by_name'):
        assert not jira.get_project_version_by_name.called


def test_lp_to_jira_bug_milestone_enabled():
    """Test that milestone sync works when enabled"""
    lp = Mock()
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    bug.id = 123456
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    task.bug_target_name = "systemd (Ubuntu)"
    bug.bug_tasks = [task]
    bug.tags = []
    bug.web_link = "https://example.com"
    bug.title = "Test Bug"
    bug.description = "Test Description"
    
    # Mock JIRA search to return no existing issue
    jira.search_issues = Mock(return_value=None)
    jira_issue = Mock(key="TEST-123", id="123")
    jira_issue.fields = Mock()
    jira_issue.fields.fixVersions = []
    jira.create_issue = Mock(return_value=jira_issue)
    jira.add_simple_link = Mock()
    jira.client_info = Mock(return_value="https://jira.example.com")
    
    # Mock version creation
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Create opts with sync_milestone enabled
    opts = Mock()
    opts.dry_run = False
    opts.label = None
    opts.no_lp_tag = True
    opts.lp_link = False
    opts.sync_milestone = True  # Enabled
    opts.user_map = {}
    opts.status_map = {}
    opts.priority_map = {}
    opts.epic = None
    
    sync = {'jira_project': 'TEST'}
    
    # Call lp_to_jira_bug
    lp_to_jira_bug(lp, jira, bug, sync, opts)
    
    # Verify that milestone sync ran (version was checked)
    jira.get_project_version_by_name.assert_called_once_with('TEST', 'ubuntu-22.04')
    # Verify issue was updated with milestone
    jira_issue.update.assert_called_once()


def test_sync_milestone_debug_disabled_by_default(capsys):
    """Test that debug messages are not shown by default"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup JIRA version
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Setup issue without the milestone
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    issue.fields.fixVersions = []
    
    # Call without debug flag (default)
    sync_milestone_to_jira(jira, bug, issue, "TEST")
    
    # Capture output
    captured = capsys.readouterr()
    
    # Verify no DEBUG messages in output
    assert "DEBUG:" not in captured.out


def test_sync_milestone_debug_enabled(capsys):
    """Test that debug messages are shown when debug flag is enabled"""
    jira = Mock()
    
    # Setup bug with milestone
    bug = Mock()
    milestone = Mock()
    milestone.name = "ubuntu-22.04"
    task = Mock()
    task.milestone = milestone
    bug.bug_tasks = [task]
    
    # Setup JIRA version
    jira_version = Mock()
    jira_version.name = "ubuntu-22.04"
    jira.get_project_version_by_name = Mock(return_value=jira_version)
    
    # Setup issue without the milestone
    issue = Mock()
    issue.key = "TEST-123"
    issue.fields = Mock()
    issue.fields.fixVersions = []
    
    # Call with debug flag enabled
    sync_milestone_to_jira(jira, bug, issue, "TEST", debug=True)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Verify DEBUG messages are in output
    assert "DEBUG: current_versions = []" in captured.out
    assert "DEBUG: current_versions type = <class 'list'>" in captured.out


def _write_config_tempfile(config_dict):
    """Write config_dict as JSON to a NamedTemporaryFile and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(config_dict, tmp)
    tmp.flush()
    tmp.close()
    return tmp.name


def _make_mock_infra():
    """Return (mock_lp, mock_jira, mock_jira_api) with standard stubs."""
    mock_lp = Mock()
    mock_jira = Mock()
    mock_jira_api = Mock()
    mock_jira_api.server = "https://jira.example.com"
    mock_jira_api.login = "user"
    mock_jira_api.token = "token"
    return mock_lp, mock_jira, mock_jira_api


def _make_fake_tasks():
    """Return a fake iterable of one bug task."""
    fake_bug = Mock()
    fake_bug_task = Mock()
    fake_bug_task.bug = fake_bug
    fake_tasks = Mock()
    fake_tasks.__iter__ = Mock(return_value=iter([fake_bug_task]))
    return fake_tasks


def test_config_json_sync_milestone_sets_flag():
    """Test that sync_milestone=true in config JSON is applied to opts passed to lp_to_jira_bug."""
    config = {
        "sync_milestone": True,
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "testcomponent"}]
    }
    config_path = _write_config_tempfile(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()

    captured_opts = []

    def capture_opts(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks", return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture_opts):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    assert captured_opts[0].sync_milestone is True


def test_config_json_sync_milestone_disabled():
    """Test that sync_milestone=false in config JSON keeps milestone syncing disabled."""
    config = {
        "sync_milestone": False,
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "testcomponent"}]
    }
    config_path = _write_config_tempfile(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()

    captured_opts = []

    def capture_opts(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks", return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture_opts):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    assert captured_opts[0].sync_milestone is False


def test_config_json_without_sync_milestone_key():
    """Test that omitting sync_milestone in config JSON leaves the CLI default (False)."""
    config = {
        "status_map": {},
        "user_map": {},
        "project": [{"launchpad_project": "testproject", "jira_project": "TEST",
                     "issue_type": "Bug", "component": "testcomponent"}]
    }
    config_path = _write_config_tempfile(config)
    mock_lp, mock_jira, mock_jira_api = _make_mock_infra()
    fake_tasks = _make_fake_tasks()

    captured_opts = []

    def capture_opts(lp, jira, bug, sync_config, opts):
        captured_opts.append(opts)

    try:
        with patch("LpToJira.lp_to_jira.Launchpad") as mock_lp_class, \
             patch("LpToJira.lp_to_jira.JIRA") as mock_jira_class, \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks", return_value=fake_tasks), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug", side_effect=capture_opts):
            mock_lp_class.login_with.return_value = mock_lp
            mock_jira_class.return_value = mock_jira
            main(["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    # CLI default for --sync-milestone is False
    assert captured_opts[0].sync_milestone is False
