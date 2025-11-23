import pytest
from unittest.mock import Mock, patch

from LpToJira.lp_to_jira import (
    get_lp_bug_milestone,
    ensure_jira_version,
    sync_milestone_to_jira,
    lp_to_jira_bug
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
    opts.epic = None
    
    sync = {'jira_project': 'TEST'}
    
    # Call lp_to_jira_bug
    lp_to_jira_bug(lp, jira, bug, sync, opts)
    
    # Verify that milestone sync ran (version was checked)
    jira.get_project_version_by_name.assert_called_once_with('TEST', 'ubuntu-22.04')
    # Verify issue was updated with milestone
    jira_issue.update.assert_called_once()
