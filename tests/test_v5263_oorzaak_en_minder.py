"""v5.263.0 (Ruud 26-11, ideeen uit Sentient): de oorzaak van een wijziging
vastleggen, en de knop "Minder hiervan" in meldingen."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.energy_management_system import oorzaak
from custom_components.energy_management_system.const import (
    LOG_PRIO_KRITIEK, LOG_PRIORITEITEN, MELDING_MINDER_ACTIE, MELDING_MINDER_KEER,
    NOTIFICATION_TYPES, PERSISTED_PLAIN_FIELDS,
)

NU = datetime(2026, 11, 26, 8, 0, tzinfo=timezone(timedelta(hours=1)))


def test_de_oorzaak_uit_de_context():
    ctx = lambda **k: SimpleNamespace(user_id=None, parent_id=None, **k) if not k else SimpleNamespace(**{"user_id": None, "parent_id": None, **k})
    assert oorzaak.uit_context(ctx(), door_ems=True) == oorzaak.EMS
    assert oorzaak.uit_context(ctx(), eigen_automatisering=True) == oorzaak.EIGEN_AUTOMATISERING
    assert oorzaak.uit_context(ctx(user_id="abc")) == oorzaak.PERSOON
    assert oorzaak.uit_context(ctx(parent_id="xyz")) == oorzaak.AUTOMATISERING
    assert oorzaak.uit_context(ctx()) == oorzaak.APPARAAT
    assert oorzaak.uit_context(None) == oorzaak.APPARAAT


def test_de_lijst_blijft_kort():
    lijst = []
    for i in range(oorzaak.MAX_REGELS + 5):
        lijst = oorzaak.bijgewerkt(lijst, oorzaak.regel(str(i), ("off", 21), ("heat", 21), oorzaak.PERSOON))
    assert len(lijst) == oorzaak.MAX_REGELS and lijst[-1]["moment"] == str(oorzaak.MAX_REGELS + 4)
    assert lijst[-1]["tekst"].startswith("iemand")


def test_beide_worden_bewaard():
    assert "airco_wijzigingen" in PERSISTED_PLAIN_FIELDS and "melding_minder" in PERSISTED_PLAIN_FIELDS


def _gewone_soort():
    return next(s[0] for s in NOTIFICATION_TYPES if LOG_PRIORITEITEN.get(s[0]) != LOG_PRIO_KRITIEK)


def _kritieke_soort():
    return next((s[0] for s in NOTIFICATION_TYPES if LOG_PRIORITEITEN.get(s[0]) == LOG_PRIO_KRITIEK), None)


def test_de_knop_staat_op_een_gewone_melding_en_niet_op_een_kritieke(make_coordinator, hass):
    c = make_coordinator({})
    knop = c._melding_minder_knop(_gewone_soort())
    assert knop == [{"action": f"{MELDING_MINDER_ACTIE}|{_gewone_soort()}", "title": "Minder hiervan"}]
    assert c._melding_minder_knop(None) == [] and c._melding_minder_knop("bestaat_niet") == []
    if _kritieke_soort():
        assert c._melding_minder_knop(_kritieke_soort()) == []


def test_drie_tikken_zetten_de_soort_uit(make_coordinator, hass):
    c = make_coordinator({})
    soort = _gewone_soort()
    c.set_notification_enabled(soort, True)
    verstuurd = []
    c._ontdekking_stuur = lambda *a, **k: verstuurd.append(a)
    actie = f"{MELDING_MINDER_ACTIE}|{soort}"
    for i in range(MELDING_MINDER_KEER - 1):
        uit = c.melding_minder_antwoord(actie, NU + timedelta(days=i))
        assert uit["geteld"] and not uit["uitgezet"]
        assert c.notification_enabled[soort] is True
    uit = c.melding_minder_antwoord(actie, NU + timedelta(days=5))
    assert uit["uitgezet"] and c.notification_enabled[soort] is False
    assert len(verstuurd) == 1 and c.melding_minder[soort] == []


def test_oude_tikken_tellen_niet_mee(make_coordinator, hass):
    c = make_coordinator({})
    soort = _gewone_soort()
    c.set_notification_enabled(soort, True)
    c._ontdekking_stuur = lambda *a, **k: None
    actie = f"{MELDING_MINDER_ACTIE}|{soort}"
    c.melding_minder_antwoord(actie, NU)
    c.melding_minder_antwoord(actie, NU + timedelta(days=1))
    uit = c.melding_minder_antwoord(actie, NU + timedelta(days=45))
    assert uit["tikken"] == 1 and not uit["uitgezet"] and c.notification_enabled[soort] is True


def test_een_andere_knop_en_een_kritieke_soort(make_coordinator, hass):
    c = make_coordinator({})
    assert c.melding_minder_antwoord("EUFY_GEZICHT|x|y") is None
    assert c.melding_minder_antwoord("") is None
    assert c.melding_minder_antwoord(f"{MELDING_MINDER_ACTIE}|bestaat_niet", NU)["geteld"] is False
    kritiek = _kritieke_soort()
    if kritiek:
        c.set_notification_enabled(kritiek, True)
        for _ in range(5):
            assert c.melding_minder_antwoord(f"{MELDING_MINDER_ACTIE}|{kritiek}", NU)["geteld"] is False
        assert c.notification_enabled[kritiek] is True
