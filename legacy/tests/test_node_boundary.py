"""Release acceptance includes the actual Node HTTP send routes."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class NodeBoundaryTests(unittest.TestCase):
    def test_node_practice_routes(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PERSON5_PYTHON=sys.executable)
        result = subprocess.run(['node', '--test', 'tests/node_quality.test.mjs'], cwd=root,
                                env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
