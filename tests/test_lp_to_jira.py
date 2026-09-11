import pytest

from unittest.mock import Mock

from LpToJira.lp_to_jira import\
    build_jira_issue,\
    create_jira_issue,\
    get_lp_bug,\
    get_lp_bug_pkg,\
    get_lp_bug_importance,\
    get_all_lp_project_bug_tasks,\
    get_first_matching_assignee,\
    is_bug_in_jira,\
    lp_to_jira_bug,\
    update_bug_in_jira


def test_get_lp_bug(lp):
    # bad bug id
    assert get_lp_bug(lp, 1000000000) == None
    # bad launchpad api
    assert get_lp_bug(None, 123456) == None
    # valid bug
    test_bug = get_lp_bug(lp, 123456)
    assert test_bug.id == 123456
    assert test_bug.title == "test bug"


def test_get_lp_bug_pkg():
    bug = Mock()
    bug.bug_tasks = [Mock(bug_target_name='systemd (Ubuntu)')]

    assert get_lp_bug_pkg(bug) == 'systemd'

    bug = Mock()
    bug.bug_tasks = [Mock(bug_target_name='systemd (Ubuntu Focal)')]

    assert get_lp_bug_pkg(bug) == 'systemd'

    bug = Mock()
    bug.bug_tasks = [Mock(bug_target_name='glibc !@#$)')]

    assert get_lp_bug_pkg(bug) == None

    bug = Mock()
    bug.bug_tasks = [Mock(bug_target_name='systemd (Debian)')]

    assert get_lp_bug_pkg(bug) == None

    bug = Mock()
    bug.bug_tasks = [
        Mock(bug_target_name=n)
        for n in ['systemd (Ubuntu)', 'glibc (Ubuntu)']]

    assert get_lp_bug_pkg(bug) == 'glibc'


def test_get_lp_project_bug_tasks(lp):
    # Very light testing of what the function could do
    # 100% coverage but not necessarly 100% coverage :)
    # TODO: test more date's options
    # TODO: test various status filters

    assert get_all_lp_project_bug_tasks(lp, "badproject") == None

    # project subiquity exists has no bug
    assert get_all_lp_project_bug_tasks(lp, "subiquity") == None

    # project curtin exists and has a bug
    assert get_all_lp_project_bug_tasks(lp, "curtin", 5).id == 123456

    search_tasks_kwargs = lp.projects["curtin"].searchTasks.call_args.kwargs
    assert "Duplicate" in search_tasks_kwargs["status"]


def test_is_bug_in_jira():
    jira = Mock()
    jira.search_issues = Mock(return_value=None)

    bug = Mock()
    bug.id = 123

    assert is_bug_in_jira(jira, bug, "AA") == False

    jira_issue = Mock()
    jira_issue = [Mock(key="key")]

    jira.search_issues = Mock(return_value=jira_issue)
    jira.client_info = Mock(return_value="jira_client_info")

    assert is_bug_in_jira(jira, bug, "AA") == True


def test_build_jira_issue(empty_bug):
    # TODO improve coverage to test for non empty bug
    default_jira_bug = {'project': '',
                        'summary': 'LP#0 [None] ',
                        'description': '',
                        'issuetype': {'name': 'Bug'},
                        'components': [{'name': 'nplan'}]}
    opts = Mock()
    opts.component = 'nplan'

    assert build_jira_issue(None, empty_bug, "", 'Bug', opts=opts) == default_jira_bug

    issuetype = 'Launchpad Bug'
    default_jira_bug['issuetype']['name'] = issuetype

    assert build_jira_issue(None, empty_bug, "", issuetype, opts=opts) == default_jira_bug

def test_create_jira_issue(empty_bug, capsys):
    jira = Mock()

    jira.create_issue = Mock(return_value=Mock(key="001"))
    jira.add_simple_link = Mock(return_value=None)
    jira.client_info = Mock(return_value="jira")

    issue_dict = build_jira_issue(None, empty_bug, 'Bug', "")

    jira_issue = create_jira_issue(jira, issue_dict, empty_bug)

    assert "jira/browse/001" in capsys.readouterr().out

    # TODO: Figure out how to make this test succeed, this helps make
    #       sure the url is created properly
    # assert jira.add_simple_link.assert_called_with(
    #     jira_issue,
    #     object={'url': 'https://', 'title': 'Launchpad Link'})


def test_lp_to_jira_bug(lp, empty_bug):
    config00 = {'jira_project': 'AA'}
    config01 = {'jira_project': 'AA', 'assignees' : [ "userid00", "userid01"]}
    jira = Mock()

    jira_issue = [Mock(key="key")]
    jira.search_issues = Mock(return_value=jira_issue)
    jira.client_info = Mock(return_value="jira")

    lp_to_jira_bug(lp, jira, empty_bug, config00, [''])

    jira.search_issues = Mock(return_value=None)

    for dry_run in [ True, False ]:
        opts = Mock()
        opts.dry_run = dry_run
        opts.label = ""
        lp_to_jira_bug(lp, jira, empty_bug, config00, opts)

        opts.label = "label"
        lp_to_jira_bug(lp, jira, empty_bug, config00, opts)

        opts.no_lp_tag = False
        lp_to_jira_bug(lp, jira, empty_bug, config00, opts)

        opts.lp_link = True
        serie01 = Mock()
        serie01.bug_target_name = "aa"
        serie01.assignee = "https://api.launchpad.net/devel/~userid00"
        serie02 = Mock()
        serie02.bug_target_name = "bb"
        serie02.assignee = "https://api.launchpad.net/devel/~userid02"
        empty_bug.bug_tasks = [ serie01, serie02]
        lp_to_jira_bug(lp, jira, empty_bug, config00, opts)
        lp_to_jira_bug(lp, jira, empty_bug, config01, opts)

# =============================================================================

def test_get_lp_bug_importance():
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical')]
    assert get_lp_bug_importance(bug) == 'Critical'

    bug = Mock()
    bug.bug_tasks = [Mock(importance='High'), Mock(importance='Medium')]
    assert get_lp_bug_importance(bug) == 'High'

    bug = Mock()
    bug.bug_tasks = []
    assert get_lp_bug_importance(bug) is None


def test_build_jira_issue_with_priority_map():
    bug = Mock()
    bug.id = 1
    bug.title = "test bug"
    bug.description = "test description"
    bug.bug_tasks = [Mock(bug_target_name='systemd (Ubuntu)', importance='High')]

    opts = Mock()
    opts.user_map = {}
    opts.priority_map = {'High': 'High', 'Critical': 'Highest'}

    issue_dict = build_jira_issue(None, bug, 'PROJ', 'Bug', None, None, opts)
    assert issue_dict.get('priority') == {'name': 'High'}


def test_build_jira_issue_no_priority_map():
    bug = Mock()
    bug.id = 1
    bug.title = "test bug"
    bug.description = "test description"
    bug.bug_tasks = [Mock(bug_target_name='systemd (Ubuntu)', importance='High')]

    opts = Mock()
    opts.user_map = {}
    opts.priority_map = {}

    issue_dict = build_jira_issue(None, bug, 'PROJ', 'Bug', None, None, opts)
    assert 'priority' not in issue_dict


def test_build_jira_issue_unmapped_importance():
    bug = Mock()
    bug.id = 1
    bug.title = "test bug"
    bug.description = "test description"
    bug.bug_tasks = [Mock(bug_target_name='systemd (Ubuntu)', importance='Wishlist')]

    opts = Mock()
    opts.user_map = {}
    opts.priority_map = {'High': 'High', 'Critical': 'Highest'}

    issue_dict = build_jira_issue(None, bug, 'PROJ', 'Bug', None, None, opts)
    assert 'priority' not in issue_dict


def test_update_bug_in_jira_priority():
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical', assignee=None, status='New')]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'To Do'
    issue.fields.priority.name = 'Medium'

    priority_map = {'Critical': 'Highest', 'High': 'High'}
    status_map = {'New': 'To Do'}

    update_bug_in_jira(jira, bug, issue, [], {}, status_map, priority_map)
    issue.update.assert_called_once_with(fields={'priority': {'name': 'Highest'}})


def test_update_bug_in_jira_priority_already_set():
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical', assignee=None, status='New')]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'To Do'
    issue.fields.priority.name = 'Highest'

    priority_map = {'Critical': 'Highest'}
    status_map = {'New': 'To Do'}

    update_bug_in_jira(jira, bug, issue, [], {}, status_map, priority_map)
    issue.update.assert_not_called()


def test_update_bug_in_jira_no_priority_map():
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical', assignee=None, status='New')]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'To Do'
    issue.fields.priority.name = 'Medium'

    status_map = {'New': 'To Do'}

    update_bug_in_jira(jira, bug, issue, [], {}, status_map)
    issue.update.assert_not_called()


def test_update_bug_in_jira_duplicate_status():
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical', assignee=None, status='Duplicate')]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'To Do'
    issue.fields.priority.name = 'Medium'

    status_map = {'Duplicate': 'Done'}

    update_bug_in_jira(jira, bug, issue, [], {}, status_map)
    jira.transition_issue.assert_called_once_with(issue, transition='Done')


def test_update_bug_in_jira_unmapped_status():
    jira = Mock()
    bug = Mock()
    bug.bug_tasks = [Mock(importance='Critical', assignee=None, status='Duplicate')]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'To Do'
    issue.fields.priority.name = 'Medium'

    update_bug_in_jira(jira, bug, issue, [], {}, {})
    jira.transition_issue.assert_not_called()


def test_get_first_matching_assignee_mode1_match():
    """Mode 1: user_map exists, assignee matches → return (assignee, status)"""
    bug = Mock()
    task = Mock()
    task.assignee = Mock(name='userid00')
    task.assignee.name = 'userid00'
    task.status = 'In Progress'
    bug.bug_tasks = [task]

    assignee, status = get_first_matching_assignee(bug, ['userid00', 'userid01'])
    assert assignee == 'userid00'
    assert status == 'In Progress'


def test_get_first_matching_assignee_mode1_no_match():
    """Mode 1: user_map exists, no assignee match → return (None, None)"""
    bug = Mock()
    task = Mock()
    task.assignee = Mock(name='userid99')
    task.assignee.name = 'userid99'
    task.status = 'In Progress'
    bug.bug_tasks = [task]

    assignee, status = get_first_matching_assignee(bug, ['userid00', 'userid01'])
    assert assignee is None
    assert status is None


def test_get_first_matching_assignee_mode2_no_user_map():
    """Mode 2: user_map empty → return (None, first status)"""
    bug = Mock()
    task = Mock()
    task.assignee = None
    task.status = 'Triaged'
    bug.bug_tasks = [task]

    assignee, status = get_first_matching_assignee(bug, [])
    assert assignee is None
    assert status == 'Triaged'


def test_get_first_matching_assignee_mode3_no_match_falls_back():
    """Mode 3: user_map exists, no match, sync_unmapped_users=True → (None, first status)"""
    bug = Mock()
    task = Mock()
    task.assignee = Mock(name='userid99')
    task.assignee.name = 'userid99'
    task.status = 'Confirmed'
    bug.bug_tasks = [task]

    assignee, status = get_first_matching_assignee(
        bug, ['userid00', 'userid01'], sync_unmapped_users=True)
    assert assignee is None
    assert status == 'Confirmed'


def test_get_first_matching_assignee_mode3_match_still_returns_assignee():
    """Mode 3: user_map exists, assignee matches → still return (assignee, status)"""
    bug = Mock()
    task = Mock()
    task.assignee = Mock(name='userid00')
    task.assignee.name = 'userid00'
    task.status = 'In Progress'
    bug.bug_tasks = [task]

    assignee, status = get_first_matching_assignee(
        bug, ['userid00', 'userid01'], sync_unmapped_users=True)
    assert assignee == 'userid00'
    assert status == 'In Progress'


def test_get_first_matching_assignee_mode3_no_bug_tasks():
    """Mode 3: sync_unmapped_users=True but no bug tasks → (None, None)"""
    bug = Mock()
    bug.bug_tasks = []

    assignee, status = get_first_matching_assignee(
        bug, ['userid00'], sync_unmapped_users=True)
    assert assignee is None
    assert status is None


def test_update_bug_in_jira_sync_unmapped_users():
    """Mode 3: no assignee match but sync_unmapped_users=True → status still updated"""
    jira = Mock()
    bug = Mock()
    task = Mock()
    task.assignee = Mock(name='userid99')
    task.assignee.name = 'userid99'
    task.status = 'New'
    task.importance = 'High'
    bug.bug_tasks = [task]

    issue = Mock()
    issue.key = 'TEST-1'
    issue.fields.assignee = None
    issue.fields.status.name = 'In Progress'
    issue.fields.priority = None

    status_map = {'New': 'To Do'}

    update_bug_in_jira(
        jira, bug, issue, ['userid00'], {}, status_map,
        sync_unmapped_users=True)
    jira.transition_issue.assert_called_once_with(issue, transition='To Do')
