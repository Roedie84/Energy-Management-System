"""v5.127.3: het oplopende besparingstotaal is onbeschikbaar vóór de eerste
ronde, zodat de maandmeter geen opstartwaarde als beginstand neemt
(24-10 07:41, 25-10 06:00 en 17:25)."""
from types import SimpleNamespace

from custom_components.energy_management_system.sensor import (
    CounterfactualSavingsTotalSensor,
)


def _coord(**kw):
    return SimpleNamespace(besparing_totaal_gecorrigeerd_eur=lambda: 42.3284, **kw)


def test_onbeschikbaar_voor_eerste_ronde():
    s = CounterfactualSavingsTotalSensor(_coord(_wacht_op_eerste_ronde=True), "e")
    assert s.available is False


def test_beschikbaar_na_eerste_ronde():
    s = CounterfactualSavingsTotalSensor(_coord(_wacht_op_eerste_ronde=False), "e")
    assert s.available is True
    assert s.native_value == 42.3284


def test_zonder_vlag_beschikbaar():
    assert CounterfactualSavingsTotalSensor(_coord(), "e").available is True
