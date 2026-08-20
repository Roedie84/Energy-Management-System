"""Wanneer een kandidaat mag meesturen (v3.42.0).

Gevraagd na de constatering dat de proefstand een museum is geworden:
negen kandidaten, waarvan er meerdere weken op "klaar om mee te doen"
staan, en er is er nog nooit één doorgestroomd.

Wat ontbrak was geen bewijs maar een AFSPRAAK. Zonder criterium vooraf
wordt het altijd "nog even een week" - en dat is precies wat er de
afgelopen weken gebeurde.

Deze toelating besluit niets. Ze zegt wat er nog ontbreekt, en zodra er
niets meer ontbreekt, zegt ze dat ook.
"""
from custom_components.energy_management_system.const import (
    PROEFSTAND_EIS_AANDEEL_GUNSTIG_PROCENT,
    PROEFSTAND_EIS_DAGEN,
    PROEFSTAND_EIS_METINGEN,
    PROEFSTAND_EIS_VOORDEEL_CT_PER_KWH,
)


def _kandidaat(**opbrengst):
    basis = {
        "te_becijferen": True,
        "aandeel_gunstig_procent": 100.0,
        "momenten_met_verschil": 300,
        "mediaan_voordeel_ct_per_kwh": 2.8,
    }
    basis.update(opbrengst)
    return {"naam": "test", "status": "betrouwbaar"}, basis


def _oordeel(c, dagen=20, **opbrengst):
    c.reserve_daily_records = [{"date": f"d{i}"} for i in range(dagen)]
    kandidaat, opbr = _kandidaat(**opbrengst)
    return c._proefstand_toelating(kandidaat, opbr)


# --- de sterkste kandidaat van vandaag -------------------------------


def test_the_strongest_candidate_would_pass_with_enough_days(
    make_coordinator, hass
):
    """"Verder vooruitkijken bij de reserve": 300 van de 300 gunstig,

    mediaan voordeel 2,8 ct/kWh. Met genoeg dagen eronder voldoet die.
    """
    oordeel = _oordeel(make_coordinator({}))

    assert oordeel["voldoet"] is True
    assert oordeel["wat_ontbreekt"] == []
    assert "één tegelijk" in oordeel["advies"]


def test_three_hundred_measurements_on_one_day_is_one_day(
    make_coordinator, hass
):
    """De valkuil van deze proefstand: een kandidaat meet elk kwartier,

    dus driehonderd metingen kunnen uit één etmaal komen.
    """
    oordeel = _oordeel(make_coordinator({}), dagen=3)

    assert oordeel["voldoet"] is False
    assert any("dagen gemeten" in r for r in oordeel["wat_ontbreekt"])


# --- de kandidaten die het niet halen --------------------------------


def test_a_candidate_that_is_favourable_half_the_time_fails(
    make_coordinator, hass
):
    """Een gunstig gemiddelde over een reeks die de helft van de tijd

    geld kost, is een gok.
    """
    oordeel = _oordeel(make_coordinator({}), aandeel_gunstig_procent=55.0)

    assert oordeel["voldoet"] is False
    assert any("55%" in r for r in oordeel["wat_ontbreekt"])


def test_hold_for_tomorrow_fails_on_every_count(make_coordinator, hass):
    """"Vasthouden voor morgen": -15,4 ct/kWh, bij 0 van de 200 metingen

    voordeliger. Dat is geen twijfelgeval.
    """
    oordeel = _oordeel(
        make_coordinator({}),
        aandeel_gunstig_procent=0.0,
        metingen=200,
        momenten_met_verschil=None,
        mediaan_voordeel_ct_per_kwh=None,
        bedrag_per_kwh_ct=-15.4,
    )

    assert oordeel["voldoet"] is False
    assert len(oordeel["wat_ontbreekt"]) >= 2


def test_too_few_measurements_fails(make_coordinator, hass):
    oordeel = _oordeel(make_coordinator({}), momenten_met_verschil=12)

    assert oordeel["voldoet"] is False
    assert any("12 metingen" in r for r in oordeel["wat_ontbreekt"])


def test_a_benefit_inside_the_noise_fails(make_coordinator, hass):
    """Een halve cent voordeel is niet te onderscheiden van meetruis."""
    oordeel = _oordeel(make_coordinator({}), mediaan_voordeel_ct_per_kwh=0.5)

    assert oordeel["voldoet"] is False
    assert any("voordeel 0.5" in r for r in oordeel["wat_ontbreekt"])


def test_an_uncomputed_candidate_says_so(make_coordinator, hass):
    oordeel = _oordeel(
        make_coordinator({}),
        aandeel_gunstig_procent=None,
        mediaan_voordeel_ct_per_kwh=None,
        bedrag_per_kwh_ct=None,
    )

    assert oordeel["voldoet"] is False
    assert any("niet becijferd" in r for r in oordeel["wat_ontbreekt"])


# --- de eis zelf -----------------------------------------------------


def test_the_thresholds_are_strict_on_purpose():
    """Een kandidaat die gaat meesturen verandert wat de accu doet, en

    dat is niet terug te draaien voor de dag die al voorbij is.
    """
    assert PROEFSTAND_EIS_AANDEEL_GUNSTIG_PROCENT >= 80.0
    assert PROEFSTAND_EIS_METINGEN >= 100
    assert PROEFSTAND_EIS_DAGEN >= 7
    assert PROEFSTAND_EIS_VOORDEEL_CT_PER_KWH > 0


def test_every_candidate_carries_the_verdict(make_coordinator, hass):
    """Op de kaart hoort bij elke kandidaat te staan wat er nog

    ontbreekt - anders blijft "bijna" een eindstation.
    """
    c = make_coordinator({})
    overzicht = c.get_proefstand()

    for kandidaat in overzicht.get("kandidaten", []):
        assert "toelating" in kandidaat, kandidaat["naam"]
        assert "voldoet" in kandidaat["toelating"]
