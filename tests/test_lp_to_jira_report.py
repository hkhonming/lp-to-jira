from unittest.mock import Mock
from unittest.mock import patch


from LpToJira.lp_to_jira_report import \
    find_issues_in_project,\
    get_bug_id,\
    merge_lp_data_with_jira_issues,\
    sync_release,\
    sync_title


def test_get_bug_id():
    assert get_bug_id("") == ""
    assert get_bug_id("LP#32165987") == "32165987"
    assert get_bug_id("LP#32165987 This is a bug") == "32165987"
    assert get_bug_id("  LP#32165987 This is a bug") == "32165987"
    assert get_bug_id("LP#32165987This is a bug") == "32165987"
    assert get_bug_id("LP#32165987 [test] This is a bug") == "32165987"
    assert get_bug_id("[SRU] LP#32165987 [test This is a bug") == "32165987"

    assert get_bug_id("LP #32165987 [test] This is a bug") == ""


def test_find_issues_in_project(issue):
    assert find_issues_in_project(None, "FR") == []

    api = Mock()
    jira_issue1 = Mock()
    jira_issue1.fields = Mock()
    jira_issue1.fields.summary = "LP#123456 [jira] Default JIRA Bug"
    jira_issue1.key = "KEY-001"
    jira_issue1.fields.status = Mock()
    jira_issue1.fields.status.name = "In Progress"

    jira_issue2 = Mock()
    jira_issue2.fields = Mock()
    jira_issue2.fields.summary = "Random bug not imported"

    api.search_issues = Mock()
    api.search_issues.side_effect = [[jira_issue1, jira_issue2], None]

    assert find_issues_in_project(api, "FOO") == [issue]


def test_sync_title(issue, jira, lp):
    assert not sync_title(None, None, None)

    # This should do a successful title change as issue
    # has different title than the corresponding bug in LP
    assert sync_title(issue, jira, lp)
    assert issue['Summary'] == "LP#123456 [jira] test bug"

    bad_issue = {
                'JIRA ID': "KEY-002",
                'Summary': "LP123456 jira Bug",
                'Status': "In Progress",
                'LaunchPad ID': '123456'
            }

    assert not sync_title(bad_issue, jira, lp)


def test_merge_lp_data_with_jira_issues():
    assert merge_lp_data_with_jira_issues(None, None, []) == []

    jira_db = [
        {'JIRA ID': "KEY-001",
         'Summary': "LP1111 jira Bug",
         'Status': "In Progress",
         'LaunchPad ID': '1111'},
        {'JIRA ID': "KEY-002",
         'Summary': "LP2222 jira Bug",
         'Status': "In Progress",
         'LaunchPad ID': '2222'},
        {'JIRA ID': "KEY-003",
         'Summary': "LP3333 jira Bug",
         'Status': "In Progress",
         'LaunchPad ID': '3333'}
         ]


def test_sync_release_duplicate(issue):
    jira = Mock()
    jira_issue = Mock()
    jira_issue.fields = Mock()
    jira_issue.fields.status = Mock()
    jira_issue.fields.status.name = "In Progress"
    jira.issue = Mock(return_value=jira_issue)
    jira.add_comment = Mock()
    jira.transition_issue = Mock()

    duplicate_target = Mock()
    duplicate_target.id = 9999
    lp_bug_obj = Mock()
    lp_bug_obj.duplicate_of = duplicate_target
    lp = Mock()
    lp.bugs = {123456: lp_bug_obj}

    fake_lp_bug = Mock()
    fake_lp_bug.affected_packages = []
    fake_lp_bug.affected_series = Mock(return_value=[])
    fake_lp_bug.package_detail = Mock(return_value="")

    with patch('LpToJira.lp_to_jira_report.lp_bug', return_value=fake_lp_bug):
        assert sync_release(issue, jira, lp)

    jira.transition_issue.assert_called_once_with(jira_issue, transition='Done')
    assert "duplicate" in jira.add_comment.call_args[0][1].lower()
