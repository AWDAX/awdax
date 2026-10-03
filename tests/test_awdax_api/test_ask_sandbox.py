"""AI-written analysis code: real maths runs; every way out of the sandbox is refused before it runs."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ask_sandbox  # noqa: E402
from ask_sandbox import UnsafeCode, run, validate  # noqa: E402

ROWS = [
    {"brand": "Tata", "year": 2023, "sales": 100.0},
    {"brand": "Tata", "year": 2024, "sales": 150.0},
    {"brand": "MG", "year": 2023, "sales": 80.0},
    {"brand": "MG", "year": 2024, "sales": 60.0},
]


class SandboxRunsMathsTests(unittest.TestCase):
    def test_growth_per_brand(self):
        src = (
            "def answer(rows):\n"
            "    by = {}\n"
            "    for r in rows:\n"
            "        by.setdefault(r['brand'], {})[r['year']] = r['sales']\n"
            "    return [{'brand': b, 'growth_pct': round((v[2024] - v[2023]) / v[2023] * 100, 2)} for b, v in sorted(by.items())]\n"
        )
        self.assertEqual(run(src, ROWS), [{"brand": "MG", "growth_pct": -25.0}, {"brand": "Tata", "growth_pct": 50.0}])

    def test_statistics_and_math(self):
        src = "def answer(rows):\n    xs = [r['sales'] for r in rows]\n    return {'stdev': round(statistics.stdev(xs), 3), 'root': math.sqrt(16)}\n"
        self.assertEqual(run(src, ROWS), {"stdev": 38.622, "root": 4.0})  # sqrt(4475 / 3)

    def test_a_runtime_error_is_reported_not_raised_raw(self):
        with self.assertRaises(ValueError) as cm:
            run("def answer(rows):\n    return 1 / 0\n", ROWS)
        self.assertIn("ZeroDivisionError", str(cm.exception))

    def test_an_endless_loop_is_stopped(self):
        with mock.patch.object(ask_sandbox, "TIMEOUT_S", 1), self.assertRaises(ValueError) as cm:
            run("def answer(rows):\n    while True:\n        pass\n", ROWS)
        self.assertIn("too long", str(cm.exception))

    def test_a_memory_bomb_is_killed_by_the_memory_limit(self):
        # Review finding: 3 GB in under a second when only POSIX had limits. Now the job / RLIMIT stops it.
        bomb = "def answer(rows):\n    l = []\n    for i in range(30):\n        l.append('a' * 100000000)\n    return len(l)\n"
        with self.assertRaises(ValueError) as cm:
            run(bomb, ROWS)
        self.assertIn("MemoryError", str(cm.exception))  # stopped by the memory limit, not by waiting out the clock

    def test_an_oversized_result_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            run("def answer(rows):\n    return 'a' * 5000000\n", ROWS)
        self.assertIn("too large", str(cm.exception))


class SandboxRefusesEscapesTests(unittest.TestCase):
    ESCAPES = {
        "import": "def answer(rows):\n    import os\n    return os.getcwd()\n",
        "dunder import": "def answer(rows):\n    return __import__('os')\n",
        "open": "def answer(rows):\n    return open('x').read()\n",
        "eval": "def answer(rows):\n    return eval('1')\n",
        "getattr": "def answer(rows):\n    return getattr(rows, 'x')\n",
        "class walk": "def answer(rows):\n    return ().__class__.__bases__\n",
        "f-string dunder": "def answer(rows):\n    return f'{rows.__class__}'\n",
        "format string": "def answer(rows):\n    return '{0.__class__}'.format(rows)\n",
        "globals": "def answer(rows):\n    return globals()\n",
        "type": "def answer(rows):\n    return type(rows)\n",
        "statistics import leak": "def answer(rows):\n    return statistics.random.random()\n",
        "frame": "def answer(rows):\n    g = (x for x in rows)\n    return g.gi_frame\n",
        "huge power": "def answer(rows):\n    return 10 ** 10 ** 10\n",
        "huge list": "def answer(rows):\n    return [0] * 10 ** 9\n",
        "nested def": "def answer(rows):\n    def f():\n        return 1\n    return f()\n",
        "class": "class X:\n    pass\n",
        "two functions": "def answer(rows):\n    return 1\ndef other():\n    return 2\n",
        "rebind builtin": "def answer(rows):\n    len = 3\n    return len\n",
        "unknown name": "def answer(rows):\n    return os\n",
        "nested too deep": "def answer(rows):\n    return " + "-" * 3000 + "1\n",
    }

    def test_every_escape_is_refused_before_running(self):
        for name, src in self.ESCAPES.items():
            with self.subTest(name), mock.patch("ask_sandbox.subprocess.Popen") as spawn:
                with self.assertRaises(UnsafeCode):
                    run(src, ROWS)
                spawn.assert_not_called()

    def test_imports_of_the_provided_modules_are_tolerated_and_no_others(self):
        # Models write these despite being told not to (seen live from nemotron-3-ultra).
        src = (
            "def answer(rows):\n"
            "    import statistics\n"
            "    import math\n"
            "    from statistics import median as med\n"
            "    xs = [r['sales'] for r in rows]\n"
            "    return [med(xs), round(math.sqrt(statistics.mean(xs)), 2)]\n"
        )
        self.assertEqual(run(src, ROWS), [90.0, 9.87])
        for bad in ("import os", "from os import path", "from statistics import sys", "import math, os", "import math as m"):
            with self.subTest(bad), self.assertRaises(UnsafeCode):
                run(f"def answer(rows):\n    {bad}\n    return 1\n", ROWS)

    def test_plain_helpers_are_allowed(self):
        validate("def answer(rows):\n    xs = sorted((r.get('sales') or 0 for r in rows), reverse=True)\n    return {'top': xs[:2], 'n': len(xs)}\n")


if __name__ == "__main__":
    unittest.main()
