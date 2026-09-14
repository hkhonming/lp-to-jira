#!/usr/bin/python3
# The purpose of lp-to-jira is to take a launchad bug ID and create a new Entry in JIRA in a given project


import os
import json
import getpass
import time

from jira import JIRA
import requests

REQUEST_TIMEOUT = 30
ATLASSIAN_ACCESSIBLE_RESOURCES_URL = \
    'https://api.atlassian.com/oauth/token/accessible-resources'
ATLASSIAN_EX_JIRA_PREFIX = 'https://api.atlassian.com/ex/jira/'

class jira_api():
    def __init__(self,
                 credstore="{}/.jira.token".format(os.path.expanduser('~')),
                 oauth_credstore=None):
        snap_home = os.getenv("SNAP_USER_COMMON")
        if snap_home:
            self.credstore = "{}/.jira.token".format(snap_home)
            self.oauth_credstore = "{}/.jira.oauth".format(snap_home)
        else:
            self.credstore = credstore
            if oauth_credstore:
                self.oauth_credstore = oauth_credstore
            else:
                self.oauth_credstore = "{}/.jira.oauth".format(
                    os.path.expanduser('~'))

        self.auth_method = self._get_env(
            'LP_TO_JIRA_JIRA_AUTH_METHOD',
            'JIRA_AUTH_METHOD') or self._get_config_auth_method() or 'token'
        self.auth_method = self.auth_method.lower()
        self.server = None
        self.login = None
        self.token = None
        self.client_id = None
        self.client_secret = None
        self.cloud_id = None
        self.token_url = 'https://auth.atlassian.com/oauth/token'
        self.oauth_access_data = None

        if self.auth_method == 'token':
            self._load_token_auth()
        elif self.auth_method == 'oauth':
            self._load_oauth_auth()
        else:
            raise ValueError(
                "Unsupported JIRA authentication method: {}".format(
                    self.auth_method))

    def _get_env(self, *names):
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        return None

    def _load_json_config(self, config_path):
        with open(config_path) as f:
            return json.load(f)

    def _get_config_auth_method(self):
        for config_path in [self.credstore, self.oauth_credstore]:
            try:
                config = self._load_json_config(config_path)
            except (FileNotFoundError, json.JSONDecodeError):
                continue
            if config.get('jira-auth-method'):
                return config.get('jira-auth-method')
        return None

    def _load_token_auth(self):
        config = {}
        try:
            config = self._load_json_config(self.credstore)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        self.server = self._get_env(
            'LP_TO_JIRA_JIRA_SERVER',
            'JIRA_SERVER') or config.get('jira-server')
        self.login = self._get_env(
            'LP_TO_JIRA_JIRA_LOGIN',
            'JIRA_LOGIN') or config.get('jira-login')
        self.token = self._get_env(
            'LP_TO_JIRA_JIRA_TOKEN',
            'JIRA_TOKEN') or config.get('jira-token')

        if self.server and self.login and self.token:
            return

        print('JIRA credential information file {} could not be found or parsed.'.format(self.credstore))
        print('')
        gather_token = input(
            'Do you want to enter your JIRA credentials now? (Y/n) ')
        if gather_token == 'n':
            raise ValueError("JIRA API isn't initialized")
        self.server = self.server or input(
            'Please enter your jira server address : ')
        self.login = self.login or input(
            'Please enter your email login for JIRA : ')
        self.token = self.token or getpass.getpass(
            'Please enter your JIRA credential : ')
        save_token = input('Do you want to save those credentials for future use or lp-to-jira? (Y/n) ')
        if save_token != 'n':
            try:
                data = {}
                data['jira-server'] = self.server
                data['jira-login'] = self.login
                data['jira-token'] = self.token
                with open(self.credstore,'w+') as f:
                    json.dump(data,(f))
            except (FileNotFoundError, json.JSONDecodeError):
                raise ValueError("JIRA API isn't initialized")

    def _load_oauth_auth(self):
        config = {}
        try:
            config = self._load_json_config(self.oauth_credstore)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        self.server = self._get_env(
            'LP_TO_JIRA_JIRA_SERVER',
            'JIRA_SERVER') or config.get('jira-server')
        self.client_id = self._get_env(
            'JIRA_CLIENT_ID',
            'LP_TO_JIRA_JIRA_OAUTH_CLIENT_ID',
            'JIRA_OAUTH_CLIENT_ID') or config.get('jira-oauth-client-id')
        self.client_secret = self._get_env(
            'JIRA_CLIENT_SECRET',
            'LP_TO_JIRA_JIRA_OAUTH_CLIENT_SECRET',
            'JIRA_OAUTH_CLIENT_SECRET') or config.get('jira-oauth-client-secret')
        self.cloud_id = self._get_env(
            'JIRA_CLOUD_ID',
            'LP_TO_JIRA_JIRA_CLOUD_ID',
            'JIRA_OAUTH_CLOUD_ID') or config.get('jira-cloud-id')
        self.token_url = self._get_env(
            'LP_TO_JIRA_JIRA_OAUTH_TOKEN_URL',
            'JIRA_OAUTH_TOKEN_URL') or config.get(
                'jira-oauth-token-url',
                self.token_url)

        if self.server and self.client_id and self.client_secret:
            return

        raise ValueError(
            "JIRA OAuth configuration is incomplete. "
            "Set OAuth credentials with environment variables or {}.".format(
                self.oauth_credstore))

    def get_jira_client_kwargs(self):
        if self.auth_method == 'oauth':
            auth = self.get_oauth_access_data()
            return {'server': self.get_oauth_server(auth), 'token_auth': auth['token']}

        return {'basic_auth': (self.login, self.token)}

    def get_oauth_access_data(self):
        if self.oauth_access_data:
            expires_at = self.oauth_access_data.get('expires_at', 0)
            if expires_at > time.time():
                return self.oauth_access_data

        response = requests.post(
            self.token_url,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials',
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get('access_token')
        if not token:
            raise ValueError('No OAuth access token returned by Atlassian')
        expires_in = payload.get('expires_in', 0)

        resources = requests.get(
            ATLASSIAN_ACCESSIBLE_RESOURCES_URL,
            headers={
                'Authorization': ''.join(['Bearer ', token]),
                'Accept': 'application/json',
            },
            timeout=REQUEST_TIMEOUT,
        )
        resources.raise_for_status()
        cloud_ids = {
            resource['url'].rstrip('/'): resource['id']
            for resource in resources.json()
            if resource.get('url') and resource.get('id')
        }

        self.oauth_access_data = {
            'token': token,
            'cloud_ids': cloud_ids,
            'expires_at': time.time() + max(0, expires_in - 60),
        }
        return self.oauth_access_data

    def get_oauth_server(self, auth):
        if self.server and self.server.startswith(ATLASSIAN_EX_JIRA_PREFIX):
            return self.server

        if self.cloud_id:
            return '{}{}'.format(ATLASSIAN_EX_JIRA_PREFIX, self.cloud_id)

        cloud_id = auth['cloud_ids'].get(self.server.rstrip('/'))
        if not cloud_id:
            raise ValueError(
                'Unable to find Atlassian cloud ID for {}'.format(
                    self.server))
        return '{}{}'.format(ATLASSIAN_EX_JIRA_PREFIX, cloud_id)

    def create_client(self):
        jira_client_kwargs = self.get_jira_client_kwargs()
        server = jira_client_kwargs.pop('server', self.server)
        return JIRA(server, **jira_client_kwargs)