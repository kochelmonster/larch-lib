"""
runs all unittests
"""
from __future__ import print_function
import sys
import os
import coverage
from sarge import run
from pathlib import Path
try:
    import win32api
except ImportError:
    pass
else:
    def terminate_handler(type_):
        return type_ == 0

    win32api.SetConsoleCtrlHandler(terminate_handler, True)


def install_coverage():
    site_package = Path(coverage.__file__).parent.parent.resolve()
    with open(os.path.join(site_package, "coverage.pth"), "wb") as f:
        f.write(b"import coverage; coverage.process_startup()")


def run_all(report=True):
    install_coverage()

    root_dir = Path(__file__).parent.resolve()
    environ = {
        "COVERAGE_PROCESS_START": str(root_dir / ".coveragerc"),
        "PYTHONHASHSEED": "0"
    }

    with open(root_dir / "tests.txt", "r") as f:
        tests = f.read().strip().splitlines()

    cv = coverage.Coverage()
    cv.erase()

    for t in tests:
        if t.startswith("#end"):
            break
        if t.startswith("#"):
            continue
        print("="*len(t))
        print(t)
        path = root_dir / t
        status = run("python {} -v".format(path), env=environ).returncode
        if status != 0:
            print("stopped execution", status)
            return 1

    if report:
        cv.combine()
        cv.report(show_missing=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_all("--no-report" not in sys.argv))
