"""v5.210.0: Zendure zelf herladen, prijsverwachting onthouden, pv-terugtoets."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import homeassistant.helpers as ha_helpers

from custom_components.energy_management_system import coordinator as C

dt_util = C.dt_util
from custom_components.energy_management_system.const import (
    ZENDURE_HERLAAD_NA_MINUTEN,
    ZENDURE_HERLAAD_PAUZE_MINUTEN,
)

Coord = C.EnergyManagementSystemCoordinator
REDEN = "De Zendure-integratie ziet de accu als offline (status 0): geen verbinding."


def _coord(minuten_offline, learning=False):
    c = Coord.__new__(Coord)
    c.hass = MagicMock()
    c.learning_only = learning
    c.aansturing_onbereikbaar = {
        "reden": REDEN,
        "sinds": (dt_util.now() - timedelta(minutes=minuten_offline)).isoformat(),
    }
    c._zendure_statusentiteiten = lambda: ["sensor.zendure_connection_status"]
    return c


def _register(entry_id="abc"):
    reg = MagicMock()
    reg.async_get.return_value = SimpleNamespace(config_entry_id=entry_id)
    nep = SimpleNamespace(async_get=lambda hass: reg)
    return patch.object(ha_helpers, "entity_registry", nep, create=True)


def test_herlaadt_na_vijf_minuten_offline():
    c = _coord(ZENDURE_HERLAAD_NA_MINUTEN + 1)
    with _register():
        assert c._zendure_zelf_herladen(REDEN) is True
    c.hass.config_entries.async_reload.assert_called_once_with("abc")
    assert len(c._zendure_herladingen) == 1


def test_niet_binnen_vijf_minuten():
    c = _coord(ZENDURE_HERLAAD_NA_MINUTEN - 2)
    with _register():
        assert c._zendure_zelf_herladen(REDEN) is False
    c.hass.config_entries.async_reload.assert_not_called()


def test_hooguit_een_keer_per_uur():
    c = _coord(30)
    with _register():
        assert c._zendure_zelf_herladen(REDEN) is True
        assert c._zendure_zelf_herladen(REDEN) is False
        c._zendure_herladen_om = dt_util.now() - timedelta(minutes=ZENDURE_HERLAAD_PAUZE_MINUTEN + 1)
        assert c._zendure_zelf_herladen(REDEN) is True
    assert c.hass.config_entries.async_reload.call_count == 2


def test_alleen_bij_zendure_offline_en_niet_in_leermodus():
    c = _coord(30)
    with _register():
        assert c._zendure_zelf_herladen("De accu-entiteit is onbeschikbaar") is False
    c = _coord(30, learning=True)
    with _register():
        assert c._zendure_zelf_herladen(REDEN) is False


def test_zonder_config_entry_gebeurt_niets():
    c = _coord(30)
    with _register(entry_id=None):
        assert c._zendure_zelf_herladen(REDEN) is False
    c.hass.config_entries.async_reload.assert_not_called()


def test_dagoverzicht_noemt_de_herlading():
    c = _coord(30)
    assert c._dagoverzicht_zendure_herladen() == ""
    with _register():
        c._zendure_zelf_herladen(REDEN)
    assert "zelf herladen" in c._dagoverzicht_zendure_herladen()


def test_prijsverwachting_wordt_per_kwartier_onthouden():
    c = Coord.__new__(Coord)
    c.prijsverwachting = {"gemaakt": "x", "dagen": {}}
    c._prijs_keuze = {}
    teller = {"n": 0}

    def reken():
        teller["n"] += 1
        return {"n": teller["n"]}

    c._bereken_prijsverwachting = reken
    assert c.get_prijsverwachting() == {"n": 1}
    assert c.get_prijsverwachting() == {"n": 1}
    assert teller["n"] == 1
    c.prijsverwachting = {"gemaakt": "y", "dagen": {}}
    assert c.get_prijsverwachting() == {"n": 2}


def test_prijsverwachting_opnieuw_in_een_nieuw_kwartier():
    c = Coord.__new__(Coord)
    c.prijsverwachting = {"gemaakt": "x", "dagen": {}}
    c._prijs_keuze = {}
    c._bereken_prijsverwachting = MagicMock(side_effect=[{"a": 1}, {"a": 2}])
    nu = dt_util.now()
    with patch.object(C.dt_util, "now", return_value=nu):
        assert c.get_prijsverwachting() == {"a": 1}
    with patch.object(C.dt_util, "now", return_value=nu + timedelta(minutes=16)):
        assert c.get_prijsverwachting() == {"a": 2}


RIJEN = [
    ("2026-10-28", 9.33, 7.95), ("2026-10-29", 7.43, 3.68), ("2026-10-30", 6.71, 5.3),
    ("2026-10-31", 4.14, 4.94), ("2026-11-01", 2.82, 1.83), ("2026-11-02", 2.39, 1.99),
    ("2026-11-03", 5.09, 4.96), ("2026-11-04", 6.01, 6.62), ("2026-11-05", 7.81, 7.49),
    ("2026-11-06", 7.85, 7.33), ("2026-11-07", 4.9, 5.67), ("2026-11-08", 2.67, 0.58),
    ("2026-11-09", 5.01, 6.39), ("2026-11-10", 3.51, 1.78),
]


def test_pv_terugtoets_op_de_gemeten_dagen():
    uit = Coord._pv_snelle_correctie_toets(RIJEN)
    assert uit["beschikbaar"] and uit["dagen"] == 9
    assert uit["fout_nu_kwh_per_dag"] == 0.88
    assert uit["fout_snel_kwh_per_dag"] == 0.99
    assert uit["beter"] is False and uit["stuurt"] is False


def test_pv_terugtoets_te_weinig_dagen():
    assert Coord._pv_snelle_correctie_toets(RIJEN[:7])["beschikbaar"] is False


def test_pv_terugtoets_ziet_een_vaste_afwijking():
    rijen = [(f"d{i:02d}", 10.0, 8.0) for i in range(12)]
    uit = Coord._pv_snelle_correctie_toets(rijen)
    assert uit["beter"] is True and uit["fout_snel_kwh_per_dag"] == 0.0


def test_plan_kwaliteit_bevat_de_terugtoets():
    hist = [{"datum": d, "zon": {"voorspeld_kwh": v, "werkelijk_kwh": w}} for d, v, w in RIJEN]
    assert Coord._pv_plan_kwaliteit(hist)["snellere_correctie"]["dagen"] == 9
