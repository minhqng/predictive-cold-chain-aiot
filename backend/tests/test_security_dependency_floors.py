"""Project-owned lock/trust-store policy; no exploit or third-party benchmark."""

from importlib.metadata import version
from pathlib import Path
import ssl
import tomllib

import certifi
from packaging.version import Version
import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package,minimum", [("certifi", "2026.10.19"), ("opentelemetry-api", "1.45.1")])
def test_locked_installed_and_declared_security_floors(package, minimum):
    assert Version(version(package)) >= Version(minimum), "installed environment contains the affected dependency"
    lock = tomllib.loads((BACKEND / "uv.lock").read_text())
    locked_versions = [row["version"] for row in lock["package"] if row["name"] == package]
    assert locked_versions and all(Version(value) >= Version(minimum) for value in locked_versions)
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert package + ">=" + minimum in project["tool"]["uv"]["constraint-dependencies"]


def test_project_certifi_trust_store_omits_the_compromised_emsign_root():
    context = ssl.create_default_context(cafile=certifi.where())
    names = {value for certificate in context.get_ca_certs() for group in certificate["subject"]
             for key, value in group if key == "commonName"}
    assert "emSign ECC Root CA - G3" not in names
