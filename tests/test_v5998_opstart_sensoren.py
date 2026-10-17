"""v5.99.8: zware sensoren schrijven vóór de eerste ronde niets zwaars.

16-10 bij het opstarten: "Updating state for sensor.energy_management_system_
upcoming_schedule took 0.616 seconds" en gacs_zelfbeoordeling 0.406 s."""
from types import SimpleNamespace

from custom_components.energy_management_system.sensor import (
    GacsAssessmentSensor, UpcomingTimelineSensor, _voor_eerste_ronde,
)


class _Coord(SimpleNamespace):
    def get_plan_blokken(self, now=None):  # pragma: no cover - mag niet
        raise AssertionError("plan opgebouwd vóór de eerste ronde")


def test_upcoming_wacht_op_eerste_ronde():
    c = _Coord(_wacht_op_eerste_ronde=True)
    s = UpcomingTimelineSensor(c, "e")
    assert s.native_value == 0
    assert s.extra_state_attributes == {"transitions": []}


def test_gacs_wacht_op_eerste_ronde():
    c = _Coord(_wacht_op_eerste_ronde=True)
    assert GacsAssessmentSensor(c, "e").extra_state_attributes == {}


def test_zonder_vlag_gewoon():
    assert not _voor_eerste_ronde(SimpleNamespace())
    assert _voor_eerste_ronde(SimpleNamespace(_wacht_op_eerste_ronde=True))


def test_eerste_ronde_zet_vlag_uit():
    from custom_components.energy_management_system.coordinator import (
        EnergyManagementSystemCoordinator as C,
    )
    from datetime import datetime, timezone
    z = SimpleNamespace(_wacht_op_eerste_ronde=True)
    C._begin_ronde_cache(z, datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert z._wacht_op_eerste_ronde is False
