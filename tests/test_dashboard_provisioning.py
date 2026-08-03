"""Auto-provision the example dashboard on every setup (v0.52.0).

Always overwrites, on the explicit understanding (agreed with the
person maintaining this integration) that any manual dashboard change
is fed back first so it can be folded into the bundled template before
shipping.
"""
import os
import tempfile

from custom_components.energy_management_system import (
    DASHBOARD_FILENAME,
    _copy_dashboard_template,
)


class _FakeConfig:
    def __init__(self, path: str):
        self._path = path

    def path(self, filename: str) -> str:
        return os.path.join(self._path, filename)


class _FakeHass:
    def __init__(self, path: str):
        self.config = _FakeConfig(path)


def test_copies_the_template_when_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        hass = _FakeHass(tmpdir)
        destination = os.path.join(tmpdir, DASHBOARD_FILENAME)

        assert not os.path.exists(destination)
        _copy_dashboard_template(hass)
        assert os.path.exists(destination)

        with open(destination) as f:
            content = f.read()
        assert "Energy Management System" in content


def test_overwrites_an_existing_file_with_the_latest_template():
    with tempfile.TemporaryDirectory() as tmpdir:
        hass = _FakeHass(tmpdir)
        destination = os.path.join(tmpdir, DASHBOARD_FILENAME)

        with open(destination, "w") as f:
            f.write("an old or manually-edited version")

        _copy_dashboard_template(hass)

        with open(destination) as f:
            content = f.read()
        assert content != "an old or manually-edited version"
        assert "Energy Management System" in content
