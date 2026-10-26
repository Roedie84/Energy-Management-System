"""L-EMS-039: de dagbesparing is onbeschikbaar vóór de eerste ronde, zodat hij
bij een herstart geen ongecorrigeerd dagcijfer schrijft (26-10 07:12, 07:47,
10:27: -1,30 / -0,69 / -0,41, 30 s later de goede waarde)."""
from types import SimpleNamespace

from custom_components.energy_management_system.sensor import (
    CounterfactualSavingsSensor,
)


def _coord(**kw):
    return SimpleNamespace(
        get_savings_correction=lambda: {
            "correctie_beschikbaar": True,
            "besparing_gecorrigeerd_eur": 0.42,
        },
        counterfactual_cost_today_eur=1.0,
        actual_cost_today_eur=1.69,
        **kw,
    )


def test_onbeschikbaar_voor_eerste_ronde():
    s = CounterfactualSavingsSensor(_coord(_wacht_op_eerste_ronde=True), "e")
    assert s.available is False


def test_beschikbaar_na_eerste_ronde():
    s = CounterfactualSavingsSensor(_coord(_wacht_op_eerste_ronde=False), "e")
    assert s.available is True
    assert s.native_value == 0.42


def test_zonder_vlag_beschikbaar():
    assert CounterfactualSavingsSensor(_coord(), "e").available is True
