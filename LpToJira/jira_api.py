#!/usr/bin/python3
# The purpose of lp-to-jira is to take a launchad bug ID and create a new Entry in JIRA in a given project


import json
import os


class jira_api():
    def __init__(self, credstore=None, oauthstore=None, auth_method=None):
        base_dir = os.getenv("SNAP_USER_COMMON") or os.path.expanduser('~')
        self.credstore = credstore or "{}/.jira.token".format(base_dir)
        self.oauthstore = oauthstore or "{}/.jira.oauth".format(base_dir)
        self.auth_method = (auth_method or os.getenv("JIRA_AUTH_METHOD", "token")).lower()
        self.server = None
        self.login = None
        self.token = None
        self.oauth = None

        if self.auth_method == "token":
            self._load_token_config()
        elif self.auth_method == "oauth":
            self._load_oauth_config()
        else:
            raise ValueError(
                "Unsupported JIRA auth method '{}'. Use 'token' or 'oauth'.".format(
                    self.auth_method
                )
            )

    def get_jira_client_kwargs(self):
        if self.auth_method == "oauth":
            return {"oauth": self.oauth}

        return {"basic_auth": (self.login, self.token)}

    def _load_token_config(self):
        config = self._load_json_file(self.credstore)
        if config is not None:
            try:
                self.server = config['jira-server']
                self.login = config['jira-login']
                self.token = config['jira-token']
                return
            except (KeyError, TypeError):
                pass

        print(
            'JIRA Token information file {} could not be found or parsed.'.format(
                self.credstore
            )
        )
        print('')
        gather_token = input('Do you want to enter your JIRA token information now? (Y/n) ')
        if gather_token == 'n':
            raise ValueError("JIRA API isn't initialized")
        self.server = input('Please enter your jira server address : ')
        self.login = input('Please enter your email login for JIRA : ')
        self.token = input(
            'Please enter your JIRA API Token (see https://id.atlassian.com/manage-profile/security/api-tokens) : '
        )
        save_token = input(
            'Do you want to save those credentials for future use or lp-to-jira? (Y/n) '
        )
        if save_token != 'n':
            self._save_json_file(
                self.credstore,
                {
                    'jira-server': self.server,
                    'jira-login': self.login,
                    'jira-token': self.token,
                },
            )

    def _load_oauth_config(self):
        config = self._normalize_oauth_config(self._load_json_file(self.oauthstore) or {})
        config.update(self._load_oauth_env_config())

        if self._has_required_oauth_config(config):
            self.server = config['jira-server']
            self.oauth = {
                'consumer_key': config['consumer_key'],
                'key_cert': config['key_cert'],
                'access_token': config['access_token'],
                'access_token_secret': config['access_token_secret'],
            }
            if config.get('signature_method'):
                self.oauth['signature_method'] = config['signature_method']
            return

        print(
            'JIRA OAuth information file {} could not be found, parsed, or completed from the environment.'.format(
                self.oauthstore
            )
        )
        print('')
        gather_oauth = input('Do you want to enter your JIRA OAuth information now? (Y/n) ')
        if gather_oauth == 'n':
            raise ValueError("JIRA API isn't initialized")

        self.server = input('Please enter your jira server address : ')
        self.oauth = {
            'consumer_key': input('Please enter your JIRA OAuth consumer key / client id : '),
            'access_token': input('Please enter your JIRA OAuth access token : '),
            'access_token_secret': input('Please enter your JIRA OAuth access token secret : '),
            'key_cert': input('Please enter your JIRA OAuth private key / key cert : '),
        }
        signature_method = input(
            'Please enter your JIRA OAuth signature method or leave blank for the jira library default : '
        )
        if signature_method:
            self.oauth['signature_method'] = signature_method

        save_oauth = input(
            'Do you want to save those OAuth credentials for future use with lp-to-jira? (Y/n) '
        )
        if save_oauth != 'n':
            data = {'jira-server': self.server}
            data.update(self.oauth)
            self._save_json_file(self.oauthstore, data)

    def _load_json_file(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_json_file(self, path, data):
        try:
            with open(path, 'w+') as f:
                json.dump(data, f)
        except (FileNotFoundError, json.JSONDecodeError):
            raise ValueError("JIRA API isn't initialized")

    def _load_oauth_env_config(self):
        return self._normalize_oauth_config(
            {
                'jira-server': os.getenv('JIRA_OAUTH_SERVER') or os.getenv('JIRA_SERVER'),
                'consumer_key': os.getenv('JIRA_OAUTH_CONSUMER_KEY') or os.getenv('JIRA_OAUTH_CLIENT_ID'),
                'key_cert': os.getenv('JIRA_OAUTH_KEY_CERT') or os.getenv('JIRA_OAUTH_PRIVATE_KEY'),
                'access_token': os.getenv('JIRA_OAUTH_ACCESS_TOKEN') or os.getenv('JIRA_OAUTH_TOKEN'),
                'access_token_secret': (
                    os.getenv('JIRA_OAUTH_ACCESS_TOKEN_SECRET')
                    or os.getenv('JIRA_OAUTH_TOKEN_SECRET')
                ),
                'signature_method': os.getenv('JIRA_OAUTH_SIGNATURE_METHOD'),
            }
        )

    def _normalize_oauth_config(self, config):
        if not isinstance(config, dict):
            return {}

        normalized = {}
        aliases = {
            'jira-server': ['jira-server', 'server'],
            'consumer_key': ['consumer_key', 'client_id'],
            'key_cert': ['key_cert', 'private_key'],
            'access_token': ['access_token', 'token'],
            'access_token_secret': ['access_token_secret', 'token_secret'],
            'signature_method': ['signature_method'],
        }

        for key, names in aliases.items():
            for name in names:
                value = config.get(name)
                if value:
                    normalized[key] = value
                    break

        return normalized

    def _has_required_oauth_config(self, config):
        required_fields = (
            'jira-server',
            'consumer_key',
            'key_cert',
            'access_token',
            'access_token_secret',
        )
        return all(config.get(field) for field in required_fields)