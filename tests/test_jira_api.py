import json

from unittest.mock import Mock

import LpToJira.jira_api as jira_api_module


def test_jira_api_create_client_uses_token_auth_by_default(tmp_path, monkeypatch):
    token_file = tmp_path / ".jira.token"
    token_file.write_text(json.dumps({
        'jira-server': 'https://jira.example.com',
        'jira-login': 'user@example.com',
        'jira-token': 'api-token',
    }))

    monkeypatch.delenv('SNAP_USER_COMMON', raising=False)
    monkeypatch.delenv('LP_TO_JIRA_JIRA_AUTH_METHOD', raising=False)
    monkeypatch.delenv('JIRA_AUTH_METHOD', raising=False)

    jira_client = Mock(return_value='jira-client')
    monkeypatch.setattr(jira_api_module, 'JIRA', jira_client)

    api = jira_api_module.jira_api(credstore=str(token_file))

    assert api.create_client() == 'jira-client'
    jira_client.assert_called_once_with(
        'https://jira.example.com',
        basic_auth=('user@example.com', 'api-token'))


def test_jira_api_create_client_uses_oauth_config(tmp_path, monkeypatch):
    oauth_file = tmp_path / ".jira.oauth"
    oauth_file.write_text(json.dumps({
        'jira-auth-method': 'oauth',
        'jira-server': 'https://api.atlassian.com/ex/jira/cloud-id',
        'jira-oauth-client-id': 'oauth-client-id',
        'jira-oauth-client-secret': 'oauth-client-secret',
    }))

    response = Mock()
    response.json = Mock(return_value={
        'access_token': 'variable-length-oauth-access-token-value',
        'expires_in': 3600,
        'token_type': 'Bearer',
    })
    response.raise_for_status = Mock()

    jira_client = Mock(return_value='jira-client')
    monkeypatch.setattr(jira_api_module.requests, 'post', Mock(return_value=response))
    monkeypatch.setattr(jira_api_module, 'JIRA', jira_client)
    monkeypatch.delenv('SNAP_USER_COMMON', raising=False)
    monkeypatch.delenv('LP_TO_JIRA_JIRA_AUTH_METHOD', raising=False)
    monkeypatch.delenv('JIRA_AUTH_METHOD', raising=False)

    api = jira_api_module.jira_api(
        credstore=str(tmp_path / ".jira.token"),
        oauth_credstore=str(oauth_file))

    assert api.create_client() == 'jira-client'
    jira_api_module.requests.post.assert_called_once_with(
        'https://auth.atlassian.com/oauth/token',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'client_id': 'oauth-client-id',
            'client_secret': 'oauth-client-secret',
            'grant_type': 'client_credentials',
        },
        timeout=30,
    )
    jira_client.assert_called_once_with(
        'https://api.atlassian.com/ex/jira/cloud-id',
        token_auth='variable-length-oauth-access-token-value')


def test_jira_api_supports_env_only_oauth_configuration(tmp_path, monkeypatch):
    response = Mock()
    response.json = Mock(return_value={'access_token': 'oauth-token-from-env'})
    response.raise_for_status = Mock()

    jira_client = Mock(return_value='jira-client')
    monkeypatch.setattr(jira_api_module.requests, 'post', Mock(return_value=response))
    monkeypatch.setattr(jira_api_module, 'JIRA', jira_client)
    monkeypatch.delenv('SNAP_USER_COMMON', raising=False)
    monkeypatch.setenv('LP_TO_JIRA_JIRA_AUTH_METHOD', 'oauth')
    monkeypatch.setenv(
        'LP_TO_JIRA_JIRA_SERVER',
        'https://api.atlassian.com/ex/jira/env-cloud-id')
    monkeypatch.setenv('LP_TO_JIRA_JIRA_OAUTH_CLIENT_ID', 'env-client-id')
    monkeypatch.setenv(
        'LP_TO_JIRA_JIRA_OAUTH_CLIENT_SECRET',
        'env-client-secret')

    api = jira_api_module.jira_api(
        credstore=str(tmp_path / ".jira.token"),
        oauth_credstore=str(tmp_path / ".jira.oauth"))

    assert api.create_client() == 'jira-client'
    jira_client.assert_called_once_with(
        'https://api.atlassian.com/ex/jira/env-cloud-id',
        token_auth='oauth-token-from-env')
