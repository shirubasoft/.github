import importlib.util
from pathlib import Path
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'scripts' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ComposeIdentityTests(unittest.TestCase):
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
