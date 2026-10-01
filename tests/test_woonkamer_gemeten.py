"""De gemeten woonkamertemperatuur naast de projectie (v5.27.1).

Gemeld met een schermafdruk van de pagina Klimaat: de kolom "Gemeten" was
overal leeg, met "0 van de 6 uren met zowel een projectie als een meting".
Het traject begint altijd bij NU; voor die uren bestaat nog geen meting, en
voorbije uren zaten er nooit in. Nu wordt per uur bewaard wat de projectie
vooraf zei, en toont de tabel ook de laatste uren met hun meting.

En: "Schakelaar hiervoor op de landingspage" - de knop Airco automaat staat
op Overzicht.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import custom_components.energy_management_system as pkg

TZ = timezone(timedelta(hours=2))
NU = datetime(2026, 10, 1, 14, 20, tzinfo=TZ)


def _traject(vanaf, waarden):
    return [
        {"tijd": (vanaf + timedelta(hours=i)).isoformat(), "kort_termijn_temp_c": w}
        for i, w in enumerate(waarden)
    ]


def test_de_projectie_wordt_per_toekomstig_uur_bewaard(make_coordinator, hass):
    c = make_coordinator({})
    c._onthoud_projectie(_traject(NU.replace(minute=0), [22.6, 22.7, 22.8]), NU)

    # 14:00 is al begonnen - die wordt niet meer overschreven
    assert "2026-10-01T14" not in c.woonkamertemp_voorspeld_per_uur
    assert c.woonkamertemp_voorspeld_per_uur["2026-10-01T15"] == 22.7


def test_een_latere_projectie_overschrijft_tot_het_uur_begint(make_coordinator, hass):
    c = make_coordinator({})
    c._onthoud_projectie(_traject(NU.replace(minute=0), [22.6, 22.7]), NU)
    c._onthoud_projectie(_traject(NU.replace(minute=0), [22.6, 22.9]), NU + timedelta(minutes=30))

    assert c.woonkamertemp_voorspeld_per_uur["2026-10-01T15"] == 22.9


def test_de_tabel_toont_de_voorbije_uren_met_hun_meting(make_coordinator, hass, monkeypatch):
    import custom_components.energy_management_system.coordinator as coord

    monkeypatch.setattr(coord.dt_util, "now", lambda: NU)
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {
        f"2026-10-01T{u:02d}": 22.0 + u / 100 for u in range(6, 15)
    }
    c.woonkamertemp_voorspeld_per_uur = {
        f"2026-10-01T{u:02d}": 22.3 for u in range(6, 15)
    }

    rijen = c._traject_met_metingen(_traject(NU.replace(minute=0), [22.6, 22.7]))

    voorbij = [r for r in rijen if r.get("voorbij")]
    assert len(voorbij) == 6                       # 08:00 - 13:00
    assert voorbij[-1]["gemeten_temp_c"] == 22.13
    assert voorbij[-1]["afwijking_c"] == round(22.3 - 22.13, 1)


def test_na_zes_uren_is_er_een_oordeel(make_coordinator, hass, monkeypatch):
    import custom_components.energy_management_system.coordinator as coord

    monkeypatch.setattr(coord.dt_util, "now", lambda: NU)
    c = make_coordinator({})
    c.woonkamertemp_gemeten_per_uur = {f"2026-10-01T{u:02d}": 22.0 for u in range(6, 15)}
    c.woonkamertemp_voorspeld_per_uur = {f"2026-10-01T{u:02d}": 22.4 for u in range(6, 15)}
    c.climate_forecast_trajectory = _traject(NU.replace(minute=0), [22.6])

    oordeel = c.get_klimaat_projectie_kwaliteit()

    assert oordeel["beschikbaar"] is True
    assert oordeel["gemiddelde_afwijking_c"] == 0.4


def _pagina(pad):
    d = yaml.safe_load((Path(pkg.__file__).parent / "dashboard_template.yaml").read_text())
    return next(v for v in d["views"] if v.get("path") == pad)


def test_de_knop_airco_automaat_staat_op_de_landingspagina():
    assert "switch.woonkamer_energy_management_system_airco_automaat" in str(_pagina("overzicht"))


def test_op_klimaat_staat_het_besluit_zonder_schakelfunctie():
    """Het besluit is daar alleen te lezen; schakelen gebeurt op Overzicht."""
    klimaat = str(_pagina("detail-klimaat"))
    assert "airco_besluit" in klimaat
    assert "airco_automaat" not in klimaat
