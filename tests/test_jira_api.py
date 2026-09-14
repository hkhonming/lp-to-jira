import json

import pytest

from LpToJira.jira_api import jira_api


def test_jira_api_uses_token_auth_by_default(tmp_path):
    credstore = tmp_path / ".jira.token"
    credstore.write_text(
        json.dumps(
            {
                "jira-server": "https://jira.example.com",
                "jira-login": "user@example.com",
                "jira-token": "token-value",
            }
        )
    )

    api = jira_api(credstore=str(credstore))

    assert api.auth_method == "token"
    assert api.server == "https://jira.example.com"
    assert api.login == "user@example.com"
    assert api.token == "token-value"
    assert api.get_jira_client_kwargs() == {
        "basic_auth": ("user@example.com", "token-value")
    }


def test_jira_api_uses_oauth_env_config(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_AUTH_METHOD", "oauth")
    monkeypatch.setenv("JIRA_OAUTH_SERVER", "https://jira.example.com")
    monkeypatch.setenv("JIRA_OAUTH_CLIENT_ID", "consumer-key")
    monkeypatch.setenv("JIRA_OAUTH_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("JIRA_OAUTH_TOKEN", "access-token")
    monkeypatch.setenv("JIRA_OAUTH_TOKEN_SECRET", "access-token-secret")
    monkeypatch.setenv("JIRA_OAUTH_SIGNATURE_METHOD", "RSA-SHA1")

    api = jira_api(
        credstore=str(tmp_path / ".jira.token"),
        oauthstore=str(tmp_path / ".jira.oauth"),
    )

    assert api.auth_method == "oauth"
    assert api.server == "https://jira.example.com"
    assert api.login is None
    assert api.token is None
    assert api.get_jira_client_kwargs() == {
        "oauth": {
            "consumer_key": "consumer-key",
            "key_cert": "private-key",
            "access_token": "access-token",
            "access_token_secret": "access-token-secret",
            "signature_method": "RSA-SHA1",
        }
    }


def test_jira_api_keeps_token_auth_as_default_when_oauth_env_exists(monkeypatch, tmp_path):
    credstore = tmp_path / ".jira.token"
    credstore.write_text(
        json.dumps(
            {
                "jira-server": "https://jira.example.com",
                "jira-login": "user@example.com",
                "jira-token": "token-value",
            }
        )
    )
    monkeypatch.setenv("JIRA_OAUTH_SERVER", "https://oauth.example.com")
    monkeypatch.setenv("JIRA_OAUTH_CLIENT_ID", "consumer-key")
    monkeypatch.setenv("JIRA_OAUTH_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("JIRA_OAUTH_TOKEN", "access-token")
    monkeypatch.setenv("JIRA_OAUTH_TOKEN_SECRET", "access-token-secret")

    api = jira_api(credstore=str(credstore), oauthstore=str(tmp_path / ".jira.oauth"))

    assert api.auth_method == "token"
    assert api.server == "https://jira.example.com"
    assert api.get_jira_client_kwargs() == {
        "basic_auth": ("user@example.com", "token-value")
    }


def test_jira_api_uses_oauth_file_aliases_when_selected(tmp_path):
    oauthstore = tmp_path / ".jira.oauth"
    oauthstore.write_text(
        json.dumps(
            {
                "server": "https://jira.example.com",
                "client_id": "consumer-key",
                "private_key": "private-key",
                "token": "access-token",
                "token_secret": "access-token-secret",
            }
        )
    )

    api = jira_api(
        credstore=str(tmp_path / ".jira.token"),
        oauthstore=str(oauthstore),
        auth_method="oauth",
    )

    assert api.server == "https://jira.example.com"
    assert api.get_jira_client_kwargs() == {
        "oauth": {
            "consumer_key": "consumer-key",
            "key_cert": "private-key",
            "access_token": "access-token",
            "access_token_secret": "access-token-secret",
        }
    }


def test_jira_api_prompts_and_saves_oauth_config(tmp_path, monkeypatch):
    oauthstore = tmp_path / ".jira.oauth"
    answers = iter(
        [
            "Y",
            "https://jira.example.com",
            "consumer-key",
            "access-token",
            "access-token-secret",
            "private-key",
            "",
            "Y",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    api = jira_api(
        credstore=str(tmp_path / ".jira.token"),
        oauthstore=str(oauthstore),
        auth_method="oauth",
    )

    assert api.get_jira_client_kwargs()["oauth"]["consumer_key"] == "consumer-key"
    assert json.loads(oauthstore.read_text()) == {
        "jira-server": "https://jira.example.com",
        "consumer_key": "consumer-key",
        "access_token": "access-token",
        "access_token_secret": "access-token-secret",
        "key_cert": "private-key",
    }


def test_jira_api_rejects_unknown_auth_method(tmp_path):
    with pytest.raises(ValueError, match="Unsupported JIRA auth method"):
        jira_api(
            credstore=str(tmp_path / ".jira.token"),
            oauthstore=str(tmp_path / ".jira.oauth"),
            auth_method="unknown",
        )
