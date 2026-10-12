"""v5.87 (leerronde 12-10, dagafsluiting).

L-EMS-017 (akkoord Ruud 11-10 20:18): het spaarplan rekent tot het blok met
dezelfde behoefte als de verkooptoets - één bron. Aanleiding 10-10 18:34:
spaarplan 8,1 kWh nodig tot het blok, verkooptoets <= 5,5, werkelijk 4,58.
De verkooptoets zelf verandert niet (geen extra verkoop).

L-EMS-020 (meetbaarheid): sprongen in de reserve worden vastgelegd met de
uitsplitsing ervoor en erna (H-EMS-10: 0,6-1,9 kWh binnen minuten).
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    PRICE_SCALE_FACTOR,
    RESERVE_SPRONGEN_MAX,
)

TZ = timezone(timedelta(hours=2))
AVOND = datetime(2026, 10, 10, 18, 30, tzinfo=TZ)
BLOK = datetime(2026, 10, 11, 10, 45, tzinfo=TZ)


def _reeks():
    kwartieren, moment = [], AVOND
    while moment < BLOK + timedelta(hours=2):
        uur = moment.hour
        prijs = 0.44 if (18 <= uur < 21 or 7 <= uur < 9) else 0.30
        kwartieren.append(
            (moment, moment + timedelta(minutes=15), prijs * PRICE_SCALE_FACTOR)
        )
        moment += timedelta(minutes=15)
    return kwartieren


def _stel_in(c, beschikbaar=7.0, uitsplitsing=None, blok=BLOK):
    c.smart_charging_supported = lambda: True
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c._piek_vervangprijs = lambda entries, blok: None   # alleen tot het blok

    def segmenten(begin, eind, veilig=True):
        uren = (eind - begin).total_seconds() / 3600
        return [(0.5 * uren, 0.0)]                        # 500 W, geen zon

    c._segmenten_verbruik_zon = segmenten
    c.last_cheap_block_start = blok
    c.last_reserve_margin_breakdown = uitsplitsing
    return c


def test_spaarplan_neemt_de_behoefte_van_de_verkooptoets(make_coordinator, hass):
    """Eigen schatting 18:30 -> 10:45 x 0,5 kW = 8,125 kWh; de verkooptoets
    zegt 5,5 (zonder het deel na het blok). Met 7,0 kWh in de accu haalt hij
    het blok dan WEL: geen spaarplan meer dat alleen dure kwartieren dekt."""
    c = _stel_in(make_coordinator({}), uitsplitsing={
        "needed_kwh_before_margin": 6.7, "lange_horizon_extra_kwh": 1.2,
    })

    plan = c.spaarplan(AVOND, _reeks(), BLOK)

    assert plan["behoefte_bron"] == "verkooptoets"
    assert plan["spaarplan_eigen_tot_blok_kwh"] == pytest.approx(8.12, abs=0.01)
    assert plan["nodig_tot_blok_kwh"] == pytest.approx(5.5, abs=0.01)
    assert plan["actief"] is False
    assert plan["reden"] == "de accu haalt het goedkope blok"


def test_echt_tekort_blijft_een_spaarplan(make_coordinator, hass):
    """Zegt de verkooptoets ook dat het niet past, dan spaart het plan zoals
    voorheen - met het verkooptoetsgetal als totaal."""
    c = _stel_in(make_coordinator({}), beschikbaar=3.0, uitsplitsing={
        "needed_kwh_before_margin": 5.5, "lange_horizon_extra_kwh": 0.0,
    })

    plan = c.spaarplan(AVOND, _reeks(), BLOK)

    assert plan["actief"] is True
    assert plan["nodig_kwh"] == pytest.approx(5.5, abs=0.01)
    assert plan["tekort_kwh"] == pytest.approx(2.5, abs=0.01)
    # De duurste kwartieren (44 ct) krijgen de lading eerst.
    assert plan["gedekt"][0].startswith("18:30")


def test_zonder_uitsplitsing_de_eigen_schatting(make_coordinator, hass):
    c = _stel_in(make_coordinator({}), uitsplitsing=None)

    plan = c.spaarplan(AVOND, _reeks(), BLOK)

    assert plan["behoefte_bron"] == "spaarplan (eigen schatting)"
    assert plan["nodig_tot_blok_kwh"] == pytest.approx(8.12, abs=0.01)
    assert plan["actief"] is True


def test_ander_blok_dan_de_verkooptoets_eigen_schatting(make_coordinator, hass):
    c = _stel_in(
        make_coordinator({}),
        uitsplitsing={"needed_kwh_before_margin": 5.5, "lange_horizon_extra_kwh": 0.0},
        blok=BLOK + timedelta(days=1),
    )

    plan = c.spaarplan(AVOND, _reeks(), BLOK)

    assert plan["behoefte_bron"] == "spaarplan (eigen schatting)"
    assert plan["nodig_tot_blok_kwh"] == pytest.approx(8.12, abs=0.01)


def test_verkooptoets_verandert_niet(make_coordinator, hass):
    """De verkooptoets leest de uitsplitsing, niet het spaarplan: na een
    spaarplan blijven `nodig_tot_blok_kwh` en de reserve gelijk."""
    c = _stel_in(make_coordinator({}), uitsplitsing={
        "needed_kwh_before_margin": 6.7, "lange_horizon_extra_kwh": 1.2,
    })
    voor = c._nodig_tot_en_na_blok_kwh()
    c.spaarplan(AVOND, _reeks(), BLOK)
    assert c._nodig_tot_en_na_blok_kwh() == voor


def _uits(reserve, nodig, regel_w=20, ronde=1):
    return {
        "ronde": ronde, "reserve_kwh_after_margin": reserve,
        "needed_kwh_before_margin": nodig, "lange_horizon_extra_kwh": 1.0,
        "regelverschuiving_w": regel_w, "total_percent": 25.0,
        "airco_ochtend_extra_kwh": 0.0, "airco_gebruik_extra_kwh": 0.0,
        "temperatuur_extra_kwh": 0.0, "ongekapt_kwh": reserve,
        "bodem_bindend": False, "boven_capaciteit": False,
    }


def test_reservesprong_wordt_vastgelegd_met_onderdelen(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 11, 21, 42, tzinfo=TZ)
    blok = datetime(2026, 10, 12, 11, 30, tzinfo=TZ)
    c._noteer_reserve_sprong(nu, blok, _uits(4.98, 3.98), _uits(6.85, 5.48, regel_w=130))

    assert len(c.reserve_sprongen) == 1
    s = c.reserve_sprongen[0]
    assert s["reserve_kwh_after_margin"] == [4.98, 6.85]
    assert s["regelverschuiving_w"] == [20, 130]
    assert s["uren_tot_blok"] == pytest.approx(13.8, abs=0.01)
    assert s["bijdragen_kwh"]["regelverschuiving_x_uren_kwh"] == pytest.approx(1.518, abs=0.001)
    assert s["grootste_onderdeel"] == "regelverschuiving_x_uren_kwh"
    attr = c.sturing_meetattributen()
    assert attr["reserve_sprongen_aantal"] == 1


def test_kleine_verandering_geen_sprong(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 11, 21, 42, tzinfo=TZ)
    c._noteer_reserve_sprong(nu, None, _uits(4.98, 3.98), _uits(5.20, 4.15))
    c._noteer_reserve_sprong(nu, None, {}, _uits(9.0, 7.0))       # na herstart
    assert c.reserve_sprongen == []


def test_sprongen_begrensd(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 11, 21, 0, tzinfo=TZ)
    for i in range(RESERVE_SPRONGEN_MAX + 5):
        c._noteer_reserve_sprong(
            nu + timedelta(minutes=i), None, _uits(4.0, 3.0), _uits(5.0, 4.0)
        )
    assert len(c.reserve_sprongen) == RESERVE_SPRONGEN_MAX


def test_verkoopkwartieren_in_attributen(make_coordinator):
    c = make_coordinator({})
    c.dagverloop = {
        "2026-10-11": [
            {"tijd": "19:45", "marge_bij_export_min_kwh": 0.12, "beschikbaar_kwh": 6.4},
            {"tijd": "20:00", "marge_bij_export_min_kwh": None},
        ]
    }
    attr = c.sturing_meetattributen()
    assert [r["tijd"] for r in attr["verkoopkwartieren"]] == ["19:45"]
    assert attr["verkoopkwartieren"][0]["marge_bij_export_min_kwh"] == 0.12


def test_nabeschouwing_compact_in_attributen(make_coordinator):
    c = make_coordinator({})
    c.nabeschouwingen = [
        {"datum": "2026-10-11", "te_becijferen": True, "accu_leverde_op_eur": 0.5,
         "gemist_eur": 0.2, "grootste_verschillen": [{"tijd": "19:45"}]},
    ]
    attr = c.sturing_meetattributen()
    assert attr["nabeschouwing_7d"] == [
        {"datum": "2026-10-11", "te_becijferen": True,
         "accu_leverde_op_eur": 0.5, "gemist_eur": 0.2}
    ]
