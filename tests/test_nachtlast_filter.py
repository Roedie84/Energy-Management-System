"""De nachtlastmeting mat vooral zichzelf (v5.6).

Uit de export van 18 september: 122 sensoren gemeten, en de top bestond
vrijwel volledig uit dingen die geen apparaat zijn.

    2139 W  ..._piekvermogen              de integratie ZELF
    2037 W  solcast_..._piek_vandaag      een VOORSPELLING
    2000 W  ..._inverse_max_power         een INSTELLING
    1032 W  solcast_..._piek_morgen       een voorspelling voor morgen
     274 W  ..._learned_night_consumption de uitkomst van deze meting zelf
     268 W  accu_totaal_ontlaadvermogen
     254 W  pack_input / output_home / bat_in_out / net_power
             - vier sensoren, EEN stroom

Drie fouten door elkaar:

1. De meting las haar EIGEN sensoren terug als waren het apparaten.
   `piekvermogen`, `learned_night_consumption` en
   `huishoudverbruik_werkelijk` zijn uitvoer van deze integratie. Dat is
   dezelfde klasse als de naamcollisies van v4.18 en v4.19, maar dan
   tussen de meting en haar eigen sensor.

2. Voorspellingen tellen als verbruik. De Solcast-sensoren hebben
   `device_class: power` en eenheid W, maar ze voorspellen zonopbrengst.

3. Dezelfde stroom werd meerdere keren geteld: vier accusensoren op
   254 W, plus achttien `_fase_1`-duplicaten naast hun totaal.

Gevolg: de apparaataanwijzing - die op zes van acht nachten stond - mat
grotendeels ruis. Was hij "klaar" gemeld, dan was de grootste
nachtverbruiker een voorspellingssensor geweest.

Met het filter blijven er 48 over, en die lijst is meteen zinnig:
meterkast 17,4 W, hoge kast 8,8 W, cv-ketel 6,3 W.
"""
import pytest


def _meet(c, hass, sensoren):
    for entity_id, watt in sensoren.items():
        hass.states.set(entity_id, str(watt), {"unit_of_measurement": "W"})


def test_eigen_sensoren_tellen_niet_mee(make_coordinator, hass):
    c = make_coordinator({})

    for entity_id in (
        "sensor.woonkamer_energy_management_system_piekvermogen",
        "sensor.energy_management_system_learned_night_consumption",
        "sensor.woonkamer_energy_management_system_huishoudverbruik_werkelijk",
    ):
        assert c._telt_mee_als_nachtlast(entity_id) is False, entity_id


def test_voorspellingen_tellen_niet_mee(make_coordinator, hass):
    c = make_coordinator({})

    for entity_id in (
        "sensor.solcast_pv_forecast_voorspelling_piek_vandaag",
        "sensor.solcast_pv_forecast_huidig_vermogen",
        "sensor.power_production_next_12hours",
    ):
        assert c._telt_mee_als_nachtlast(entity_id) is False, entity_id


def test_de_accu_en_de_meter_tellen_niet_mee(make_coordinator, hass):
    """Vier sensoren op 254 W is een stroom, vier keer geteld."""
    c = make_coordinator({})

    for entity_id in (
        "sensor.solarflow_2400_ac_pack_input_power",
        "sensor.solarflow_2400_ac_output_home_power",
        "sensor.solarflow_2400_ac_bat_in_out",
        "sensor.zendure_manager_power",
        "sensor.p1_meter_3c39e724275e_active_power",
        "sensor.solaredge_grid_power",
        "sensor.all_standby_power",
    ):
        assert c._telt_mee_als_nachtlast(entity_id) is False, entity_id


def test_per_fase_duplicaten_tellen_niet_mee(make_coordinator, hass):
    """`_fase_1` staat naast het totaal van dezelfde meter."""
    c = make_coordinator({})

    assert c._telt_mee_als_nachtlast("sensor.vaatwasser_vermogen_fase_1") is False
    assert c._telt_mee_als_nachtlast("sensor.vaatwasser_vermogen") is True


def test_echte_apparaten_tellen_wel_mee(make_coordinator, hass):
    """De 48 die overblijven - dit is het sluipverbruik dat je zoekt."""
    c = make_coordinator({})

    for entity_id in (
        "sensor.meterkast_vermogen",
        "sensor.hoge_kast_vermogen",
        "sensor.cv_ketel_vermogen",
        "sensor.koelkast_schuur_vermogen",
        "sensor.diepvries_schuur_vermogen",
        "sensor.iptv_vermogen",
        "sensor.eetkamer_lamp_1_power",
        "sensor.shellyplug_s_80646f8107d3_power",
    ):
        assert c._telt_mee_als_nachtlast(entity_id) is True, entity_id


def test_het_filter_wordt_in_de_meting_gebruikt(make_coordinator, hass):
    """De ratel: het filter moet in het meetpad zitten, niet alleen in
    een los overzicht - dat was bij de weerbronstatus precies de fout."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _meet_nachtelijke_basislast")
    j = bron.index("\n    def ", i + 10)

    assert "_telt_mee_als_nachtlast" in bron[i:j]


def test_de_uitsluitingen_staan_benoemd():
    """Zichtbaar wat er waarom niet meetelt - anders is over een jaar
    niet meer te zien waarom een sensor ontbreekt."""
    from custom_components.energy_management_system.const import (
        NACHTLAST_UITGESLOTEN_PATRONEN,
    )

    assert len(NACHTLAST_UITGESLOTEN_PATRONEN) >= 8
    for patroon, reden in NACHTLAST_UITGESLOTEN_PATRONEN.items():
        assert reden, patroon


def test_een_gemeten_nacht_houdt_alleen_apparaten_over(make_coordinator, hass):
    c = make_coordinator({})
    kandidaten = {
        "sensor.meterkast_vermogen": 17.4,
        "sensor.cv_ketel_vermogen": 6.3,
        "sensor.woonkamer_energy_management_system_piekvermogen": 2139.0,
        "sensor.solcast_pv_forecast_voorspelling_piek_vandaag": 2037.0,
        "sensor.vaatwasser_vermogen_fase_1": 0.9,
    }

    over = {s for s in kandidaten if c._telt_mee_als_nachtlast(s)}

    assert over == {"sensor.meterkast_vermogen", "sensor.cv_ketel_vermogen"}


def test_de_al_gemeten_nachten_worden_opgeschoond(make_coordinator, hass):
    """De les van v4.17.1: instroom repareren en de voorraad laten staan
    is maar half werk. Daar bleven driehonderd oude paren de ijklijn
    wekenlang blokkeren.

    Hier is het erger: de acht al gemeten nachten bevatten elk 122
    sensoren, waarvan de grootste een voorspelling is. Zonder opschonen
    zou de apparaataanwijzing straks "klaar" melden met die rommel erin.
    """
    c = make_coordinator({})

    c._apply_persisted_state(
        {
            "nachtlast_per_apparaat": {
                "2026-09-18": {
                    "sensor.meterkast_vermogen": 17.4,
                    "sensor.cv_ketel_vermogen": 6.3,
                    "sensor.woonkamer_energy_management_system_piekvermogen": 2139.0,
                    "sensor.solcast_pv_forecast_voorspelling_piek_vandaag": 2037.0,
                    "sensor.vaatwasser_vermogen_fase_1": 0.9,
                }
            }
        }
    )

    over = c.nachtlast_per_apparaat["2026-09-18"]
    assert set(over) == {"sensor.meterkast_vermogen", "sensor.cv_ketel_vermogen"}


def test_een_nacht_die_helemaal_leeg_raakt_verdwijnt(make_coordinator, hass):
    """Anders blijft er een lege nacht staan die als gemeten telt."""
    c = make_coordinator({})

    c._apply_persisted_state(
        {
            "nachtlast_per_apparaat": {
                "2026-09-17": {"sensor.solcast_pv_forecast_huidig_vermogen": 12.0},
                "2026-09-18": {"sensor.meterkast_vermogen": 17.4},
            }
        }
    )

    assert "2026-09-17" not in c.nachtlast_per_apparaat
    assert "2026-09-18" in c.nachtlast_per_apparaat
