import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'scripts' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ComposeIdentityTests(unittest.TestCase):
    def test_health_check_identifies_the_deployer_and_does_not_read_bodies(self):
        deploy = module('deploy')
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch.object(deploy.urllib.request, 'urlopen', return_value=response) as request:
            deploy.check_url('https://example.test/health')
        self.assertEqual('shirubasoft-aspire-deploy/1.0', request.call_args.args[0].get_header('User-agent'))
        response.__enter__.return_value.read.assert_not_called()

    def test_rewrites_only_the_explicit_project_argument(self):
        args = ['compose', '-f', '/tmp/out/docker-compose.yaml', '--project-name', 'aspire-homelab-aabbccdd',
                '--env-file', '/tmp/out/.env.staging', 'up', '-d', '--remove-orphans']
        expected = args.copy()
        expected[4] = 'auth-staging'
        self.assertEqual(expected, module('docker').arguments(args, 'auth-staging'))

    def test_rejects_missing_ambiguous_and_foreign_project_arguments(self):
        for args in (['compose', 'up'], ['compose', '-p', 'other', 'up'],
                     ['compose', '--project-name', 'other', 'up'],
                     ['compose', '--project-name', 'aspire-a', '--project-name', 'aspire-b'],
                     ['compose', '--project-name']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                module('docker').arguments(args, 'auth-staging')

    def test_build_and_engine_commands_are_unchanged(self):
        for args in (['build', '-t', 'app', '.'], ['load'], ['info']):
            self.assertEqual(args, module('docker').arguments(args, 'auth-staging'))

    def test_parameters_are_explicit_and_names_are_normalized(self):
        deploy = module('deploy')
        self.assertEqual({'Parameters__auth_secret': 'value'}, deploy.parameter_environment({'auth-secret': 'value'}))
        for value in ({'auth-secret': ''}, {'bad_name': 'value'}, {'x': None}):
            with self.assertRaises(RuntimeError):
                deploy.parameter_environment(value)

    def test_empty_ci_secret_input_is_named(self):
        deploy = module('deploy')
        environment = {'DEPLOY_ENVIRONMENT': 'staging', 'DEPLOY_PROJECT': 'auth-staging',
                       'DEPLOY_DOCKER_HOST': 'ssh://deploy@example.test', 'DEPLOY_KNOWN_HOSTS': 'host key',
                       'DEPLOY_URL': 'https://example.test', 'ASPIRE_PARAMETERS': '{}', 'ASPIRE_SECRET_PARAMETERS': ''}
        with patch.dict(deploy.os.environ, environment, clear=True), patch.object(deploy.sys, 'argv', ['deploy.py']), \
             patch.object(deploy, 'deploy') as run_deploy, self.assertRaises(SystemExit) as exit:
            deploy.main()
        self.assertEqual('Empty deployment input: ASPIRE_SECRET_PARAMETERS', str(exit.exception))
        run_deploy.assert_not_called()
