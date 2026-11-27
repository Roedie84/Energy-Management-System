"""v5.265.0 (Ruud 26-11: "Hoe nauwkeurig is nu het airco-verbruik?" -
"Akkoord"): het berekende vermogen elke dag nameten op de P1-meter."""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import airco_ijking as ij
from custom_components.energy_management_system import airco_ritme as ar

T0 = datetime(2026, 11, 26, 5, 0, tzinfo=timezone(timedelta(hours=1)))


def _speel(model, reeks, start=T0, storing=lambda i: False):
    """reeks = [(hz, [l1, l2, l3])] per minuut."""
    blok = ij.nieuw_blok(start)
    for i, (hz, fasen) in enumerate(reeks):
        blok = ij.ronde(model, blok, start + timedelta(minutes=i), hz=hz, fasen_w=fasen, storing=storing(i))
    return blok


def _dag(w_per_hz=24.0):
    # een uur rust, dan twee uur draaien op 40 Hz, op fase 2
    rust = [(0.0, [60.0, 44.0, 50.0])] * 60
    aan = [(40.0, [60.0, 44.0 + w_per_hz * 40.0, 50.0])] * 120
    return rust + aan + [(0.0, [60.0, 44.0, 50.0])] * 31


def test_de_meter_tegen_de_berekening():
    model = ij.leeg()
    _speel(model, _dag())
    uit = ij.overzicht(model, 26.1, -119.0)
    assert uit["fase"] == 2 and uit["blokken"] == 12, uit
    # meter 960 W, berekend 925 W
    assert uit["afwijking_procent"] == -3.6 and uit["afwijking_stabiel_procent"] == -3.6, uit
    assert uit["gemeten_kwh"] == 1.92 and uit["berekend_kwh"] == 1.85, uit
    assert uit["oordeel"] == "nog te weinig metingen"


def test_de_helling_van_de_meter():
    model = ij.leeg()
    rust = [(0.0, [60.0, 44.0, 50.0])] * 60
    aan = []
    for hz in (30.0, 45.0, 60.0, 75.0):
        aan += [(hz, [60.0, 44.0 + 24.0 * hz - 90.0, 50.0])] * 60
    _speel(model, rust + aan + [(0.0, [60.0, 44.0, 50.0])] * 31)
    uit = ij.overzicht(model, 26.1, -119.0)
    assert uit["meter_w_per_hz"] == 24.0 and uit["meter_basis_w"] == -90.0, uit
    # twee blokken midden in de draaibeurt hebben te weinig rust binnen twee uur
    assert uit["oordeel"] == "nog te weinig metingen" and uit["blokken"] == 22


def test_zonder_rust_vooraf_en_met_storing_telt_een_blok_niet():
    model = ij.leeg()
    _speel(model, [(40.0, [60.0, 1000.0, 50.0])] * 61)          # geen rustwaarde bekend
    assert model["blokken"] == [] and len(model["wacht"]) == 6
    model = ij.leeg()
    _speel(model, _dag(), storing=lambda i: i >= 60)              # Quooker of kookplaat aan
    assert model["blokken"] == [] and len(model["rust"]) == 6 and model["wacht"] == []
    model = ij.leeg()
    _speel(model, [(0.0, [60.0, None, 50.0])] * 30)               # fase onbekend
    assert model["rust"] == []


def test_geen_duidelijke_fase_geen_oordeel():
    model = ij.leeg()
    rust = [(0.0, [60.0, 44.0, 50.0])] * 60
    aan = [(40.0, [560.0, 544.0, 50.0])] * 61                    # twee fasen bewegen even hard mee
    _speel(model, rust + aan)
    uit = ij.overzicht(model, 26.1, -119.0)
    assert "fase" not in uit and uit["oordeel"] == "nog geen fase herkend"
    assert ij.overzicht(None, 26.1, -119.0)["oordeel"] == "nog geen metingen"


def test_het_blijft_bewaard_in_het_dagritme():
    ritme = ar.leeg()
    _speel(ritme["ijking"], _dag())
    na = ar.geldig(dict(ritme))
    assert len(na["ijking"]["blokken"]) == 12
    assert ar.geldig({"ijking": "kapot"})["ijking"] == ij.leeg()


def test_de_lijsten_groeien_niet_door():
    model = ij.leeg()
    reeks = []
    for _ in range(80):
        reeks += [(0.0, [60.0, 44.0, 50.0])] * 20 + [(40.0, [60.0, 1004.0, 50.0])] * 100
    _speel(model, reeks)
    assert len(model["rust"]) <= ij.RUST_BEWAREN and len(model["blokken"]) <= ij.BLOKKEN_BEWAREN


def test_de_coordinator_meet_mee_en_toont_het(make_coordinator, hass):
    c = make_coordinator({})
    c.config = dict(c.config or {}, phase_power_sensor_entities=["sensor.l1", "sensor.l2", "sensor.l3"],
                    quooker_power_sensor_entity="sensor.quooker")
    ritme = ar.leeg()
    for i, (hz, fasen) in enumerate(_dag()):
        for naam, w in zip(("sensor.l1", "sensor.l2", "sensor.l3"), fasen):
            hass.states.set(naam, str(w), {})
        hass.states.set("sensor.quooker", "0", {})
        c._airco_ijking_ronde(T0 + timedelta(minutes=i), ritme, hz)
    assert len(ritme["ijking"]["blokken"]) == 12
    c.airco_ritme = ritme
    assert c.get_airco_vermogen()["ijking_p1"]["fase"] == 2
    # een kapotte fase breekt de ronde niet
    hass.states.set("sensor.l2", "unavailable", {})
    c._airco_ijking_ronde(T0 + timedelta(hours=4), ritme, 40.0)


def test_een_lange_draaibeurt_wacht_op_de_rust_erna():
    """De compressor draait vier uur aan een stuk: de blokken van na de
    eerste twee uur krijgen hun rustwaarde van het rustblok erna."""
    model = ij.leeg()
    rust = [(0.0, [60.0, 44.0, 50.0])] * 30
    aan = [(40.0, [60.0, 1004.0, 50.0])] * 240
    blok = _speel(model, rust + aan)
    assert len(model["blokken"]) == 11 and len(model["wacht"]) == 12
    _speel(model, [(0.0, [60.0, 44.0, 50.0])] * 31, start=T0 + timedelta(minutes=270))
    # het laatste blok voor de pauze is door het wisselen van `_speel` niet gesloten
    # en twee blokken in het midden liggen verder dan twee uur van elke rust
    assert len(model["blokken"]) == 21 and len(model["wacht"]) == 2
    assert all(b["extra_w"][1] == 960.0 for b in model["blokken"])


def test_de_accu_op_een_andere_fase_stemt_niet_tegen():
    """27-11 (dagcontrole): na 15 blokken geen fase herkend. De accu op fase 1
    volgt het huis en levert terug wat de airco op fase 2 vraagt."""
    model = ij.leeg()
    rust = [(0.0, [60.0, 44.0, 50.0])] * 60
    aan = []
    for hz in (30.0, 45.0, 60.0):
        w = 24.0 * hz - 90.0
        aan += [(hz, [60.0 - w, 44.0 + w, 50.0])] * 40
    _speel(model, rust + aan + [(0.0, [60.0, 44.0, 50.0])] * 31)
    uit = ij.overzicht(model, 26.1, -119.0)
    assert uit["fase"] == 2 and uit["meter_w_per_hz"] == 24.0, uit


def test_een_fase_die_niet_met_de_frequentie_meebeweegt_is_het_niet():
    model = ij.leeg()
    rust = [(0.0, [60.0, 44.0, 50.0])] * 60
    aan = []
    for k, hz in enumerate((30.0, 60.0, 30.0, 60.0, 30.0, 60.0)):
        # fase 3 trekt veel meer, maar juist als de compressor laag draait
        aan += [(hz, [60.0, 44.0, 50.0 + (2000.0 if hz < 40 else 200.0)])] * 20
    _speel(model, rust + aan + [(0.0, [60.0, 44.0, 50.0])] * 31)
    assert "fase" not in ij.overzicht(model, 26.1, -119.0)
