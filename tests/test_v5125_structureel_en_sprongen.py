"""v5.125.0 (leerronde 24-10): twee meet-/rapportageverbeteringen.

L-EMS-032 - plantoetsing: "structureel" ook bij een vaste richting. Op 23-10
zei het oordeel "De zonvoorspelling loopt niet structureel uit de pas" terwijl
14 van 14 dagen minder zon brachten dan voorspeld (gemiddeld -20,0 %, precies
op de tolerantie van 20). Alleen de tekst verandert; niets stuurt hierop.

L-EMS-033 - de reservesprongen gaan mee in de opslag. Op 23-10 waren ze twee
keer na een herstart weg (06:09, 07:39) en nog eens om 14:54; de attributen
staan niet in de recorder.
"""
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system.const import PERSISTED_FIELDS

TZ = timezone(timedelta(hours=2))

# De zonafwijkingen uit `plantoetsing.dagen_overzicht` van 23-10 07:40
# (09..22-10): allemaal negatief, gemiddeld ~ -20 %.
ECHT_23_10 = [-4.0, -18.0, -7.4, -29.0, -12.2, -13.7, -6.0, -40.3,
              -39.5, -11.0, -8.9, -24.9, -19.8, -45.3]


def test_vaste_richting_heet_structureel_ook_onder_de_tolerantie(make_coordinator):
    c = make_coordinator({})
    reeks = [-8.0] * 13 + [-6.0]  # gemiddeld -7,9 %: ruim binnen 20 %
    tekst = c._duid_plan_review(reeks, [])
    assert "structureel te hoog" in tekst
    assert "14 van 14" in tekst
    assert "mediaan -8%" in tekst


def test_de_reeks_van_23_10_heet_structureel_te_hoog(make_coordinator):
    c = make_coordinator({})
    tekst = c._duid_plan_review(ECHT_23_10, [])
    assert "structureel te hoog" in tekst


def test_een_dag_de_andere_kant_op_is_nog_steeds_structureel(make_coordinator):
    """24-10: 23-10 bracht +3,6 %, de 13 dagen ervoor negatief."""
    c = make_coordinator({})
    tekst = c._duid_plan_review([3.6] + ECHT_23_10[1:], [])
    assert "structureel te hoog" in tekst
    assert "13 van 14" in tekst


def test_te_laag_aan_de_andere_kant(make_coordinator):
    c = make_coordinator({})
    tekst = c._duid_plan_review([9.0, 7.0, 12.0, 6.0, 8.0, 11.0, 10.0, -2.0], [])
    assert "structureel te laag" in tekst
    assert "7 van 8" in tekst


def test_gemengd_of_klein_blijft_niet_structureel(make_coordinator):
    c = make_coordinator({})
    gemengd = [-10.0, 8.0, -6.0, 7.0, -9.0, 5.0, -4.0, 6.0]
    klein = [-2.0, -3.0, -1.0, -4.0, -2.5, -3.5, -1.5, -2.0]  # mediaan < 5 %
    for reeks in (gemengd, klein):
        assert c._duid_plan_review(reeks, []) == (
            "De zonvoorspelling loopt niet structureel uit de pas."
        )


def test_te_weinig_dagen_voor_een_richting(make_coordinator):
    """Vijf dagen is genoeg voor het gemiddelde, niet voor de richting."""
    c = make_coordinator({})
    assert c._duid_plan_review([-8.0] * 6, []) == (
        "De zonvoorspelling loopt niet structureel uit de pas."
    )


def test_groot_gemiddelde_blijft_de_oude_tekst(make_coordinator):
    c = make_coordinator({})
    tekst = c._duid_plan_review([-35.0] * 7, [])
    assert "gemiddeld -35% over 7 dagen" in tekst


def _uits(reserve, nodig):
    return {
        "reserve_kwh_after_margin": reserve, "needed_kwh_before_margin": nodig,
        "lange_horizon_extra_kwh": 0.0, "regelverschuiving_w": 10,
        "live_correctie_extra_kwh": 0.0,
    }


def test_reservesprongen_staan_in_de_opslag():
    assert PERSISTED_FIELDS["_reserve_sprongen"]["type"] == "plain"


def test_reservesprongen_overleven_een_herstart(make_coordinator):
    c = make_coordinator({})
    nu = datetime(2026, 10, 23, 12, 33, tzinfo=TZ)
    blok = datetime(2026, 10, 23, 23, 15, tzinfo=TZ)
    c._noteer_reserve_sprong(nu, blok, _uits(6.42, 5.1), _uits(7.89, 6.3))
    assert len(c.reserve_sprongen) == 1

    opgeslagen = c._collect_persisted_state()
    assert opgeslagen["_reserve_sprongen"][0]["tijd"] == "2026-10-23T12:33:00+02:00"

    na = make_coordinator({})
    assert na.reserve_sprongen == []
    na._apply_persisted_state({"_reserve_sprongen": opgeslagen["_reserve_sprongen"]})
    assert len(na.reserve_sprongen) == 1
    assert na.reserve_sprongen[0]["reserve_kwh_after_margin"] == [6.42, 7.89]
    assert na.sturing_meetattributen()["reserve_sprongen_aantal"] == 1


def test_onleesbare_opslag_geeft_een_lege_lijst(make_coordinator):
    c = make_coordinator({})
    c._apply_persisted_state({"_reserve_sprongen": "kapot"})
    assert c.reserve_sprongen == []
    c._apply_persisted_state({"_reserve_sprongen": [{"tijd": "x"}, 3, None]})
    assert c.reserve_sprongen == [{"tijd": "x"}]
