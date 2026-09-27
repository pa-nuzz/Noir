import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LocalStartupTests(unittest.TestCase):
    def test_settings_load_without_database_environment(self):
        env = os.environ.copy()
        for name in ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT'):
            env.pop(name, None)
        env['DJANGO_SETTINGS_MODULE'] = 'core.settings'

        result = subprocess.run(
            [
                sys.executable,
                '-c',
                (
                    'import django; django.setup(); '
                    'from django.conf import settings; '
                    'print(settings.DATABASES["default"]["ENGINE"])'
                ),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.sqlite3')
