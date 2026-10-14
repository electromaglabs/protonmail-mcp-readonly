"""BDD: integrationstester kräver -m integration (efterfix-verktyg).

Testerna kör bara pytest --collect-only i en underprocess; inget test i
tests/integration körs och Bridge kontaktas aldrig.
"""
import shlex
import subprocess
import sys
from pathlib import Path

from pytest_bdd import scenarios, when, then, parsers

scenarios("efterfix_verktyg_integration_opt_in.feature")

ROOT = Path(__file__).resolve().parents[2]


def _collect(extra: list[str]) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *extra],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode in (0, 5), proc.stdout + proc.stderr
    return [line for line in proc.stdout.splitlines() if "::" in line]


@when(parsers.parse('jag samlar in testerna med "{command}"'), target_fixture="collected")
def collect(command):
    args = shlex.split(command)
    assert args[0] == "pytest"
    return _collect(args[1:])


@then("ska inget insamlat test ligga i tests/integration")
def none_integration(collected):
    assert not [t for t in collected if t.startswith("tests/integration/")]


@then("ska enhetstester ha samlats in")
def has_unit(collected):
    assert any(t.startswith("tests/unit/") for t in collected)


@then("ska tests/integration/test_smtp.py ha samlats in")
def has_smtp(collected):
    assert any(t.startswith("tests/integration/test_smtp.py::") for t in collected)


@then("ska inget insamlat test ligga utanför tests/integration")
def only_integration(collected):
    assert collected
    assert all(t.startswith("tests/integration/") for t in collected)
