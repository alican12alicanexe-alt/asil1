#!/usr/bin/env python
"""Run the test suite with the standard library only - pytest is not required.

    python run_tests.py            all tests, one process per file
    python run_tests.py -v         verbose, and serial so the output reads
    python run_tests.py --serial   one process, in case a failure needs a pdb
    python run_tests.py test_etcs test_ring    just those files

Run in parallel by default because the suite is dominated by a few files that
step whole railways through a working day, and waiting for them in series is how
a test suite stops being run. One process per file, so nothing can leak state
into anything else either.
"""

import glob
import multiprocessing
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")


def _run_one(name):
    """Run one test module. Returns ``(name, ran, [problems], seconds)``."""
    import io
    sys.path[:0] = [ROOT, TESTS]
    started = time.time()
    result = unittest.TextTestRunner(verbosity=0, stream=io.StringIO()).run(
        unittest.defaultTestLoader.loadTestsFromName(name))
    problems = ["%s\n%s" % (test, trace)
                for test, trace in result.failures + result.errors]
    return name, result.testsRun, problems, time.time() - started


def _modules(argv):
    named = [a for a in argv if not a.startswith("-")]
    if named:
        return named
    return sorted(os.path.basename(p)[:-3]
                  for p in glob.glob(os.path.join(TESTS, "test_*.py")))


def main(argv):
    verbose = "-v" in argv
    serial = verbose or "--serial" in argv
    modules = _modules(argv)

    started = time.time()
    if serial:
        sys.path[:0] = [ROOT, TESTS]
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
        return 0 if result.wasSuccessful() else 1

    with multiprocessing.Pool() as pool:
        results = pool.map(_run_one, modules)

    ran = sum(r[1] for r in results)
    problems = [p for r in results for p in r[2]]
    for name, count, found, seconds in sorted(results, key=lambda r: -r[3])[:3]:
        print("  %6.1fs  %-24s %d tests" % (seconds, name, count))
    for text in problems:
        print("\n" + "=" * 70 + "\n" + text)
    print("\n%d tests in %.1fs, %d file%s, %d problem%s"
          % (ran, time.time() - started, len(results),
             "" if len(results) == 1 else "s",
             len(problems), "" if len(problems) == 1 else "s"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
