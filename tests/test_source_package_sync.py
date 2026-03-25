import pytest

from unittest.mock import Mock

from LpToJira.lp_to_jira import (
    get_source_package_bug_tasks,
    get_bug_subscriber_names,
    bug_has_matching_subscriber,
)


class TestGetSourcePackageBugTasks:
    """Tests for get_source_package_bug_tasks function"""

    def test_valid_source_package(self):
        """Test querying bugs from a valid source package"""
        lp = Mock()
        distro = Mock()
        source_pkg = Mock()
        bug_tasks = Mock()

        lp.distributions = {'ubuntu': distro}
        distro.getSourcePackage.return_value = source_pkg
        source_pkg.searchTasks.return_value = bug_tasks

        result = get_source_package_bug_tasks(lp, 'ubuntu', 'rocm')

        assert result == bug_tasks
        distro.getSourcePackage.assert_called_once_with(name='rocm')

    def test_invalid_distribution(self):
        """Test with non-existent distribution"""
        lp = Mock()
        lp.distributions = {}

        result = get_source_package_bug_tasks(lp, 'nonexistent', 'rocm')

        assert result is None

    def test_invalid_package(self):
        """Test with non-existent package"""
        lp = Mock()
        distro = Mock()
        lp.distributions = {'ubuntu': distro}
        distro.getSourcePackage.return_value = None

        result = get_source_package_bug_tasks(lp, 'ubuntu', 'nonexistent')

        assert result is None

    def test_with_days_filter(self):
        """Test that days parameter is passed correctly"""
        lp = Mock()
        distro = Mock()
        source_pkg = Mock()

        lp.distributions = {'ubuntu': distro}
        distro.getSourcePackage.return_value = source_pkg
        source_pkg.searchTasks.return_value = []

        get_source_package_bug_tasks(lp, 'ubuntu', 'rocm', days=7)

        # Verify modified_since was set in searchTasks call
        call_args = source_pkg.searchTasks.call_args
        assert 'modified_since' in call_args.kwargs
        assert call_args.kwargs['modified_since'] is not None

    def test_status_filter_applied(self):
        """Test that status filter is applied"""
        lp = Mock()
        distro = Mock()
        source_pkg = Mock()

        lp.distributions = {'ubuntu': distro}
        distro.getSourcePackage.return_value = source_pkg
        source_pkg.searchTasks.return_value = []

        get_source_package_bug_tasks(lp, 'ubuntu', 'rocm')

        call_args = source_pkg.searchTasks.call_args
        assert 'status' in call_args.kwargs
        assert 'New' in call_args.kwargs['status']
        assert 'Fix Released' in call_args.kwargs['status']


class TestGetBugSubscriberNames:
    """Tests for get_bug_subscriber_names function"""

    def test_get_subscribers(self):
        """Test extracting subscriber names from a bug"""
        bug = Mock()
        bug.id = 123

        sub1 = Mock()
        sub1.person = Mock()
        sub1.person.name = 'bullwinkle-team'

        sub2 = Mock()
        sub2.person = Mock()
        sub2.person.name = 'johndoe'

        bug.subscriptions = [sub1, sub2]

        result = get_bug_subscriber_names(bug)

        assert len(result) == 2
        assert 'bullwinkle-team' in result
        assert 'johndoe' in result

    def test_empty_subscriptions(self):
        """Test bug with no subscribers"""
        bug = Mock()
        bug.id = 123
        bug.subscriptions = []

        result = get_bug_subscriber_names(bug)

        assert result == []

    def test_subscription_error_handling(self):
        """Test that errors are handled gracefully"""
        bug = Mock()
        bug.id = 123
        bug.subscriptions = Mock()
        bug.subscriptions.__iter__ = Mock(side_effect=Exception("API error"))

        result = get_bug_subscriber_names(bug)

        assert result == []


class TestBugHasMatchingSubscriber:
    """Tests for bug_has_matching_subscriber function"""

    def test_no_filter_returns_true(self):
        """Test that no filter returns True for any bug"""
        bug = Mock()
        bug.id = 123
        bug.subscriptions = []

        result = bug_has_matching_subscriber(bug, subscribers=None)
        assert result is True

        result = bug_has_matching_subscriber(bug, subscribers=[])
        assert result is True

    def test_matching_subscriber(self):
        """Test subscriber filter matching"""
        bug = Mock()
        bug.id = 123

        sub = Mock()
        sub.person = Mock()
        sub.person.name = 'bullwinkle-team'
        bug.subscriptions = [sub]

        result = bug_has_matching_subscriber(bug, subscribers=['bullwinkle-team'])
        assert result is True

    def test_no_matching_subscriber(self):
        """Test subscriber filter not matching"""
        bug = Mock()
        bug.id = 123

        sub = Mock()
        sub.person = Mock()
        sub.person.name = 'other-team'
        bug.subscriptions = [sub]

        result = bug_has_matching_subscriber(bug, subscribers=['bullwinkle-team'])
        assert result is False

    def test_multiple_subscribers_one_match(self):
        """Test with multiple subscribers where one matches"""
        bug = Mock()
        bug.id = 123

        sub1 = Mock()
        sub1.person = Mock()
        sub1.person.name = 'other-team'

        sub2 = Mock()
        sub2.person = Mock()
        sub2.person.name = 'bullwinkle-team'

        bug.subscriptions = [sub1, sub2]

        result = bug_has_matching_subscriber(bug, subscribers=['bullwinkle-team'])
        assert result is True

    def test_multiple_filters_or_logic(self):
        """Test that multiple filter entries use OR logic"""
        bug = Mock()
        bug.id = 123

        sub = Mock()
        sub.person = Mock()
        sub.person.name = 'johndoe'
        bug.subscriptions = [sub]

        result = bug_has_matching_subscriber(
            bug, subscribers=['bullwinkle-team', 'johndoe'])
        assert result is True

    def test_user_and_team_treated_same(self):
        """Test that users and teams are treated the same"""
        bug = Mock()
        bug.id = 123

        # User subscription
        sub = Mock()
        sub.person = Mock()
        sub.person.name = 'johndoe'
        bug.subscriptions = [sub]

        # Filter works for user
        result = bug_has_matching_subscriber(bug, subscribers=['johndoe'])
        assert result is True

        # Team subscription
        team_sub = Mock()
        team_sub.person = Mock()
        team_sub.person.name = 'bullwinkle-team'
        bug.subscriptions = [team_sub]

        # Filter works for team
        result = bug_has_matching_subscriber(bug, subscribers=['bullwinkle-team'])
        assert result is True
