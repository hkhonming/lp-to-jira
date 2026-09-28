import json
import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from LpToJira.lp_to_jira import (
    build_jira_comment_from_lp,
    sync_comments_to_jira,
    lp_to_jira_bug,
    main,
)


def _make_message(content, author="Jane Doe", date=datetime(2024, 1, 2, 3, 4, 5)):
    message = Mock()
    message.content = content
    message.owner = Mock(display_name=author)
    message.date_created = date
    return message


def _make_bug(contents):
    bug = Mock()
    bug.id = 123456
    bug.web_link = "https://bugs.launchpad.net/bugs/123456"
    # First message is always the bug description
    bug.messages = [_make_message("description")] + [
        _make_message(c) for c in contents]
    return bug


def test_build_jira_comment_from_lp():
    bug = _make_bug([])
    body = build_jira_comment_from_lp(bug, _make_message("hello"), 3)

    assert "[LP#123456 comment #3|https://bugs.launchpad.net/bugs/123456/comments/3]" in body
    assert "Jane Doe" in body
    assert "2024-01-02 03:04:05 UTC" in body
    assert "{noformat}\nhello\n{noformat}" in body


def test_build_jira_comment_from_lp_escapes_and_truncates():
    bug = _make_bug([])
    body = build_jira_comment_from_lp(
        bug, _make_message("a{noformat}b" + "x" * 40000), 1)

    assert body.count("{noformat}") == 2
    assert "[... truncated ...]" in body
    assert len(body) < 32767


def test_build_jira_comment_from_lp_unknown_owner():
    bug = _make_bug([])
    message = _make_message("hello")
    type(message).owner = property(lambda self: (_ for _ in ()).throw(Exception()))
    body = build_jira_comment_from_lp(bug, message, 1)

    assert "*Unknown*" in body


def test_sync_comments_to_jira_adds_all_comments():
    bug = _make_bug(["first", "second"])
    jira = Mock()
    jira.comments = Mock(return_value=[])
    issue = Mock(key="AA-1")

    assert sync_comments_to_jira(jira, bug, issue) == 2
    assert jira.add_comment.call_count == 2
    bodies = [c[0][1] for c in jira.add_comment.call_args_list]
    assert "LP#123456 comment #1|" in bodies[0] and "first" in bodies[0]
    assert "LP#123456 comment #2|" in bodies[1] and "second" in bodies[1]
    # Description (first LP message) is never synced as a comment
    assert not any("description" in b for b in bodies)


def test_sync_comments_to_jira_skips_already_synced():
    bug = _make_bug(["first", "second"])
    jira = Mock()
    jira.comments = Mock(return_value=[
        Mock(body=build_jira_comment_from_lp(bug, bug.messages[1], 1))])
    issue = Mock(key="AA-1")

    assert sync_comments_to_jira(jira, bug, issue) == 1
    jira.add_comment.assert_called_once()
    assert "comment #2|" in jira.add_comment.call_args[0][1]


def test_sync_comments_to_jira_marker_not_prefix_matched():
    # Comment #1 marker must not be considered present because of comment #10
    bug = _make_bug(["c%d" % i for i in range(1, 11)])
    jira = Mock()
    jira.comments = Mock(return_value=[
        Mock(body=build_jira_comment_from_lp(bug, bug.messages[10], 10))])

    assert sync_comments_to_jira(jira, bug, Mock(key="AA-1")) == 9


def test_sync_comments_to_jira_no_comments():
    bug = _make_bug([])
    jira = Mock()

    assert sync_comments_to_jira(jira, bug, Mock()) == 0
    jira.comments.assert_not_called()
    jira.add_comment.assert_not_called()


def test_sync_comments_to_jira_dry_run(capsys):
    bug = _make_bug(["first"])
    jira = Mock()
    jira.comments = Mock(return_value=[])

    assert sync_comments_to_jira(jira, bug, Mock(key="AA-1"), dry_run=True) == 1
    jira.add_comment.assert_not_called()
    assert "(dry-run) Would sync LP#123456 comment #1" in capsys.readouterr().out


def test_sync_comments_to_jira_dry_run_new_issue():
    bug = _make_bug(["first", "second"])
    jira = Mock()

    assert sync_comments_to_jira(jira, bug, None, dry_run=True) == 2
    jira.comments.assert_not_called()
    jira.add_comment.assert_not_called()


def _make_opts(sync_comments):
    opts = Mock()
    opts.user_map = {}
    opts.status_map = {}
    opts.priority_map = {}
    opts.dry_run = False
    opts.sync_unmapped_users = False
    opts.sync_only_existing = False
    opts.sync_milestone = False
    opts.sync_comments = sync_comments
    opts.debug = False
    opts.label = ""
    opts.lp_link = False
    opts.no_lp_tag = True
    opts.epic = None
    return opts


@pytest.mark.parametrize("sync_comments,expected", [(True, 1), (False, 0), (None, 0)])
def test_lp_to_jira_bug_existing_issue_sync_comments(lp, sync_comments, expected):
    bug = _make_bug(["first"])
    bug.duplicate_of = None
    bug.bug_tasks = []

    existing_issue = Mock(key="AA-1")
    existing_issue.fields.assignee = None
    existing_issue.fields.priority = None
    jira = Mock()
    jira.search_issues = Mock(return_value=[existing_issue])
    jira.comments = Mock(return_value=[])

    lp_to_jira_bug(lp, jira, bug, {'jira_project': 'AA'}, _make_opts(sync_comments))

    assert jira.add_comment.call_count == expected


def test_lp_to_jira_bug_new_issue_sync_comments(lp):
    bug = _make_bug(["first", "second"])
    bug.duplicate_of = None
    bug.bug_tasks = []
    bug.title = "title"
    bug.description = "description"

    new_issue = Mock(key="AA-2", id="2")
    jira = Mock()
    jira.search_issues = Mock(return_value=None)
    jira.create_issue = Mock(return_value=new_issue)
    jira.client_info = Mock(return_value="jira")
    jira.comments = Mock(return_value=[])

    lp_to_jira_bug(lp, jira, bug, {'jira_project': 'AA'}, _make_opts(True))

    assert jira.add_comment.call_count == 2
    assert all(c[0][0] is new_issue for c in jira.add_comment.call_args_list)


def _run_main(config, extra_args=None):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    fake_task = Mock()
    fake_task.bug = Mock()
    captured_opts = []

    mock_jira_api = Mock(server="https://jira.example.com", login="user", token="token")

    try:
        with patch("LpToJira.lp_to_jira.Launchpad"), \
             patch("LpToJira.lp_to_jira.JIRA"), \
             patch("LpToJira.lp_to_jira.jira_api", return_value=mock_jira_api), \
             patch("LpToJira.lp_to_jira.get_all_lp_project_bug_tasks", return_value=[fake_task]), \
             patch("LpToJira.lp_to_jira.lp_to_jira_bug",
                   side_effect=lambda *a: captured_opts.append(a[4])):
            main((extra_args or []) + ["--config-json", config_path])
    finally:
        os.unlink(config_path)

    assert len(captured_opts) == 1
    return captured_opts[0]


BASE_CONFIG = {
    "status_map": {},
    "user_map": {},
    "project": [{"launchpad_project": "testproject", "jira_project": "TEST"}],
}


def test_config_json_sync_comments_enabled():
    opts = _run_main(dict(BASE_CONFIG, sync_comments=True))
    assert opts.sync_comments is True


def test_config_json_sync_comments_disabled():
    opts = _run_main(dict(BASE_CONFIG, sync_comments=False))
    assert opts.sync_comments is False


def test_config_json_without_sync_comments_key():
    opts = _run_main(BASE_CONFIG)
    assert not opts.sync_comments


def test_cli_sync_comments_overrides_config():
    opts = _run_main(dict(BASE_CONFIG, sync_comments=False), ["--sync-comments"])
    assert opts.sync_comments is True
