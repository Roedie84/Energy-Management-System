"""v5.62: lichtere sensorattributen, zelfde dashboard.

Live op 9 oktober: de zelfbeoordelingssensor droeg ~204 kB aan attributen
(30 dagen plantoetsing met elke dag dezelfde toelichting, 120 logboekregels,
een weekprofiel per halfuur, een SVG die geen kaart meer las, ...). Home
Assistant stuurt dat bij elke toestand naar elke open browser en vergelijkt
het met de vorige: "Updating state ... took 2.3 seconds". Home Assistant
raadt aan ruim onder de 16 kB te blijven.

Nu:
- de zelfbeoordeling draagt alleen wat het dashboard van hem leest;
- de grote pagina's staan elk op een eigen pagina-sensor, die alleen zijn
  eigen deel uitrekent;
- van de lange lijsten gaat alleen mee wat een kaart toont (14 dagen
  plantoetsing, 40 logboekregels, de kolommen van de tabel);
- de volledige set staat in de diagnostiek.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

import custom_components.energy_management_system as pkg
from custom_components.energy_management_system import sensor as m

MAP = Path(pkg.__file__).parent
GRENS = 16 * 1024
GACS = "sensor.woonkamer_energy_management_system_gacs_zelfbeoordeling"


def _grootte(waarde) -> int:
    return len(json.dumps(waarde, ensure_ascii=False, default=str))


def _pagina(c, attribuut):
    rij = next(r for r in m.DASHBOARD_PAGINA_SENSOREN if attribuut in r[3])
    return m.DashboardPaginaSensor(c, "x", *rij)


def _paginas(c):
    return [m.DashboardPaginaSensor(c, "x", *rij) for rij in m.DASHBOARD_PAGINA_SENSOREN]


def _entity_id(rij) -> str:
    naam = re.sub(r"[^a-z0-9]+", "_", rij[1].lower()).strip("_")
    return f"sensor.woonkamer_energy_management_system_{naam}"


# --- live-grote gegevens (vorm en omvang van 9 oktober) ------------------

TEKST = "De voorspelling telt alleen de opbrengst van de verkoopkwartieren; " * 3


def _plan_regel(dag: int) -> dict:
    return {
        "datum": f"2026-09-{dag:02d}",
        "opgenomen_om": "08:00",
        "zon": {"voorspeld_kwh": 12.6, "werkelijk_kwh": 11.87, "afwijking_procent": -5.8},
        "verkocht": {"voorspeld_kwh": 3.53, "werkelijk_kwh": 0.74, "afwijking_procent": -79.0},
        "opbrengst": {
            "voorspeld_eur": 1.32,
            "werkelijk_eur": -0.9,
            "vergelijkbaar": False,
            "toelichting": TEKST,
            "_afwijking_ongeldig": -168.5,
        },
        "import": {"voorspeld_kwh": 0, "werkelijk_kwh": 0.5},
        "laagste_soc": {"voorspeld_procent": 31, "werkelijk_procent": 58},
        "tekort_kwartieren_voorspeld": 0,
        "verkoopkwartieren_voorspeld": 3,
        "oordeel": "Afwijking: verkocht -79%.",
    }


def _logboek():
    return {
        "regels": [
            {
                "moment": f"2026-10-09T{u % 24:02d}:{u % 60:02d}:00+02:00",
                "prio": ("kritiek", "aandacht", "info")[u % 3],
                "soort": "besluit",
                "tekst": f"Besluit {u}: accu ontlaadt naar het huis tijdens een duur kwartier",
                "detail": "x" * 140,
            }
            for u in range(120)
        ],
        "aantallen": {"kritiek": 40, "aandacht": 40, "info": 40},
        "totaal": 120,
        "toelichting": "Nieuwste bovenaan.",
    }


def _proefstand():
    return {
        "toelichting": "Rekent mee, stuurt niets. " * 10,
        "samenvatting": {"oordeel": "Nog niemand klaar.", "aantal": 14, "meet_nog": 9, "winst_onbekend": 3},
        "rekentijd_ms": {f"k{i}": 0.1 for i in range(14)},
        "kandidaten": [
            {
                "naam": f"Kandidaat {i}",
                "waarde": "4.2 ct/kWh",
                "status": "betrouwbaar",
                "onderbouwing": "3 modules à € 729 over 51.840 kWh doorzet. " * 2,
                "betrouwbaarheid": "Het cyclusaantal is een belofte van de fabrikant.",
                "zou_veranderen": "Zon opslaan en later gebruiken moet meer opleveren.",
                "zou_hebben_opgeleverd": {
                    "te_becijferen": True,
                    "bedrag_per_dag_eur": -0.236,
                    "bedrag_per_jaar_eur": -86.12,
                    "dagen": 8,
                    "totaal_eur": -1.89,
                    "uitgesloten_uitschieters": [
                        {"datum": f"2026-09-{d:02d}", "doorzet_kwh": 348.3} for d in range(10, 20)
                    ],
                    "toelichting": "Over 8 dag(en) is er 44.7 kWh door de accu gegaan. " * 3,
                },
                "boven_theoretisch_maximum": False,
                "meting_betrouwbaar": True,
                "winst_becijferd": True,
                "mag_meesturen": False,
                "gereedheid": "voldoet nog niet aan de eis",
                "gereedheid_uitleg": "Meting en winst zijn becijferd, maar ... " * 5,
                "toelating": {"voldoet": False, "wat_ontbreekt": ["a" * 60] * 4, "advies": "b" * 140},
            }
            for i in range(14)
        ],
    }


def _aanwezigheid():
    return {
        "beschikbaar": True,
        "sensoren": 6,
        "nu": "thuis",
        "minuten_zonder_beweging": 3,
        "halfuren_geleerd": 313,
        "typisch_thuis_percentage": 71,
        "lichten_ingesteld": 2,
        "licht_aan": None,
        "slaapsensor_ingesteld": True,
        "typische_bedtijd": "23:10",
        "bedtijden_geleerd": 12,
        "laatst_gezien": [
            {"naam": f"Beweging {i}", "tijd": "2026-10-09T14:00:00+02:00", "minuten_geleden": i}
            for i in range(12)
        ],
        "tijdlijn": [
            {
                "dag": "09-10",
                "van": "07:00",
                "tot": "08:00",
                "staat": "thuis",
                "duur_minuten": 60,
                "duur": "1u00",
                "aanleiding": "beweging woonkamer (sensor.beweging_woonkamer)",
                "loopt_nog": False,
            }
            for _ in range(30)
        ],
        "tijdlijn_totaal": 400,
        "per_dag": [{"dag": f"0{d}-10", "thuis_uur": 14, "weg_uur": 2, "slaapt_uur": 8} for d in range(1, 8)],
        "profiel": {f"{d}-{h:02d}:{mm:02d}": 0.71 for d in range(7) for h in range(24) for mm in (0, 30)},
    }


def _smart_charging():
    return {
        "beschikbaar": True,
        "kwartieren": 136,
        "kwartieren_met_tekort": 102,
        "kwartieren_smart_charging_beter": 63,
        "totaal_voordeel_eur": 0.04,
        "duurste_prijs_venster_ct": 34.4,
        "kwartieren_gedekt_door_zon": 34,
        "waarde_later_ct_per_kwh": 24.7,
        "rendement_procent": 84.2,
        "slijtage_ct_per_kwh": 4.2,
        "toelichting": "Per kwartier: dekt de zon het huis niet, ... " * 8,
        "rijen": [
            {
                "van": f"{(14 + i // 4) % 24:02d}:{15 * (i % 4):02d}",
                "prijs_ct": 20.7,
                "zon_kwh": 0.0,
                "verbruik_kwh": 0.11,
                "tekort_kwh": 0.11 if i < 102 else 0.0,
                "kosten_nu_ct": 2.3,
                "hoogste_prijs_hierna_ct": 34.4,
                "waarde_later_ct_per_kwh": 24.7,
                "voordeel_eur": 0.0004,
                "smart_charging_beter": i % 2 == 0,
            }
            for i in range(136)
        ],
    }


def _kwartierplanning():
    return [
        {
            "van": f"{(14 + i // 4) % 24:02d}:{15 * (i % 4):02d}",
            "dag": "",
            "prijs_ct": 20.7,
            "zon_kwh": 0.1,
            "modus": "smart",
            "soc_procent": 22,
            "cumulatief_eur": 0,
            "gewijzigd": False,
            "eerst_voorspeld": "smart",
            "tekort": False,
        }
        for i in range(136)
    ]


def _live_groot(make_coordinator):
    """De echte opgeslagen toestand, aangevuld tot de omvang van live."""
    from tests.test_alles_uitgevraagd import _echte_toestand, _maximaal
    from tests.test_v5571_snelheid import _vul

    c = make_coordinator(_maximaal())
    try:
        c._apply_persisted_state(_echte_toestand())
    except pytest.skip.Exception:
        pass
    _vul(c)
    c.plan_review_history = [_plan_regel(d) for d in range(1, 31)]
    c.get_event_log = lambda *a, **k: _logboek()
    c.get_proefstand = lambda *a, **k: _proefstand()
    c.get_presence_overview = lambda *a, **k: _aanwezigheid()
    c.get_smart_charging_proefplanning = lambda *a, **k: _smart_charging()
    c.get_quarter_plan_compact = lambda *a, **k: _kwartierplanning()
    return c


# --- omvang ---------------------------------------------------------------


def test_de_zelfbeoordeling_blijft_onder_16_kb(make_coordinator, hass):
    c = _live_groot(make_coordinator)

    attributen = m.GacsAssessmentSensor(c, "x").extra_state_attributes

    assert _grootte(attributen) < GRENS, _grootte(attributen)


def test_voor_en_na(make_coordinator, hass):
    """Wat er eerst op één sensor stond, staat nu verdeeld en ingekort:
    samen ruim de helft minder, en de zelfbeoordeling zelf een fractie."""
    c = _live_groot(make_coordinator)

    voor = _grootte(m.gacs_volledig(c))
    gacs = _grootte(m.GacsAssessmentSensor(c, "x").extra_state_attributes)
    paginas = {p._attr_name: _grootte(p.extra_state_attributes) for p in _paginas(c)}

    assert voor > 150 * 1024
    assert gacs < voor / 8
    assert gacs + sum(paginas.values()) < voor * 0.6


def test_de_paginas_zijn_klein_behalve_de_twee_kwartiertabellen(make_coordinator, hass):
    """Kwartierplanning en de smart-charging-proef tonen elk tot ~136
    kwartieren in een tabel; die regels zijn de inhoud. Ze staan elk op een
    eigen sensor, zonder recorder, en worden niet groter dan nodig."""
    c = _live_groot(make_coordinator)

    for p in _paginas(c):
        grootte = _grootte(p.extra_state_attributes)
        if p._attr_name in ("Kwartierplanning", "Smart charging proef"):
            assert grootte < 30 * 1024, (p._attr_name, grootte)
        else:
            assert grootte < GRENS, (p._attr_name, grootte)


def test_de_smart_charging_proef_draagt_alleen_de_getoonde_rijen(make_coordinator, hass):
    c = _live_groot(make_coordinator)

    proef = _pagina(c, "smart_charging_proef").extra_state_attributes["smart_charging_proef"]

    assert len(proef["rijen"]) == 102  # alleen de kwartieren met een tekort
    assert set(proef["rijen"][0]) == {
        "van", "prijs_ct", "zon_kwh", "tekort_kwh",
        "hoogste_prijs_hierna_ct", "smart_charging_beter", "voordeel_eur",
    }
    assert proef["totaal_voordeel_eur"] == 0.04


def test_plantoetsing_14_dagen_nieuwste_eerst(make_coordinator, hass):
    c = _live_groot(make_coordinator)

    p = _pagina(c, "plantoetsing").extra_state_attributes["plantoetsing"]

    assert p["dagen"] == 30  # de samenvatting telt nog steeds alles
    assert len(p["dagen_overzicht"]) == 14
    assert p["dagen_overzicht"][0]["datum"] == "2026-09-30"
    assert "toelichting" not in p["dagen_overzicht"][0]["opbrengst"]
    assert p["dagen_overzicht"][0]["verkocht"] == {"voorspeld_kwh": 3.53, "werkelijk_kwh": 0.74}


def test_logboek_40_regels_met_kort_detail(make_coordinator, hass):
    c = _live_groot(make_coordinator)

    log = _pagina(c, "logboek").extra_state_attributes["logboek"]

    assert len(log["regels"]) == 40
    assert log["aantallen"] == {"kritiek": 40, "aandacht": 40, "info": 40}
    assert all(len(r["detail"]) <= 70 for r in log["regels"])
    assert log["regels"][0]["tekst"].startswith("Besluit 0")


# --- het dashboard ziet hetzelfde ----------------------------------------


def _dashboard_teksten() -> list[str]:
    uit = []

    def loop(x):
        if isinstance(x, dict):
            for w in x.values():
                loop(w)
        elif isinstance(x, list):
            for w in x:
                loop(w)
        elif isinstance(x, str):
            uit.append(x)

    loop(yaml.safe_load((MAP / "dashboard_template.yaml").read_text(encoding="utf-8")))
    return uit


def _gelezen_attributen() -> dict[str, set[str]]:
    gelezen: dict[str, set[str]] = {}
    for tekst in _dashboard_teksten():
        for entiteit, sleutel in re.findall(r"state_attr\('(sensor\.[a-z0-9_]+)',\s*'([a-z0-9_]+)'\)", tekst):
            gelezen.setdefault(entiteit, set()).add(sleutel)
    return gelezen


def test_lijsten_en_sjabloon_kloppen_met_elkaar():
    """Elk attribuut dat het dashboard van de zelfbeoordeling of een
    pagina-sensor leest, staat in diens lijst - en andersom staat er niets
    in een lijst dat niemand leest."""
    gelezen = _gelezen_attributen()

    assert gelezen[GACS] == set(m.GACS_DASHBOARD_SLEUTELS) - {"gacs_fout", "rekentijd_ms"}
    for rij in m.DASHBOARD_PAGINA_SENSOREN:
        assert gelezen.get(_entity_id(rij)) == set(rij[3]), rij[1]
    alle = set(m.GACS_DASHBOARD_SLEUTELS)
    for rij in m.DASHBOARD_PAGINA_SENSOREN:
        assert not alle & set(rij[3]), rij[1]  # nergens dubbel
        alle |= set(rij[3])


def _sleutels_per_variabele(tekst: str) -> dict[tuple[str, str], set[str]]:
    """(entiteit, attribuut) -> sleutels die het sjabloon daarbinnen leest,
    ook in een lus over een lijst ervan (`for r in p.get('rijen')`)."""
    uit: dict[tuple[str, str], set[str]] = {}
    for naam, entiteit, attribuut in re.findall(
        r"\{%-?\s*set\s+(\w+)\s*=\s*\(?state_attr\('([^']+)',\s*'([^']+)'\)", tekst
    ):
        namen = {naam}
        for _ in range(3):
            patroon = "|".join(map(re.escape, namen))
            namen |= set(re.findall(rf"\{{%-?\s*set\s+(\w+)\s*=\s*\(?(?:{patroon})\b", tekst))
            namen |= set(re.findall(rf"\{{%-?\s*for\s+(\w+)\s+in\s+\(?(?:{patroon})\b", tekst))
        for n in namen:
            uit.setdefault((entiteit, attribuut), set()).update(
                s
                for s in set(re.findall(rf"\b{n}\.get\('(\w+)'", tekst))
                | set(re.findall(rf"(?<![\w.]){n}\.(\w+)\b(?!\()", tekst))
                if s not in ("get", "items", "keys", "values")
            )
    return uit


def _alle_sleutels(waarde) -> set[str]:
    if isinstance(waarde, dict):
        uit = set(waarde)
        for w in waarde.values():
            uit |= _alle_sleutels(w)
        return uit
    if isinstance(waarde, list):
        uit = set()
        for w in waarde:
            uit |= _alle_sleutels(w)
        return uit
    return set()


def test_het_inkorten_laat_niets_weg_wat_een_kaart_leest(make_coordinator, hass):
    """Elke sleutel die een kaart leest en die in de volledige gegevens
    staat, staat ook in wat de sensor doorgeeft."""
    c = _live_groot(make_coordinator)
    volledig = m.gacs_volledig(c)
    doorgegeven = {GACS: m.GacsAssessmentSensor(c, "x").extra_state_attributes}
    for rij in m.DASHBOARD_PAGINA_SENSOREN:
        doorgegeven[_entity_id(rij)] = m.DashboardPaginaSensor(c, "x", *rij).extra_state_attributes

    gemist = []
    for tekst in _dashboard_teksten():
        for (entiteit, attribuut), sleutels in _sleutels_per_variabele(tekst).items():
            if entiteit not in doorgegeven:
                continue
            had = _alle_sleutels(volledig.get(attribuut))
            heeft = _alle_sleutels(doorgegeven[entiteit].get(attribuut))
            gemist += [f"{attribuut}.{s}" for s in sleutels if s in had and s not in heeft]
    assert not gemist, sorted(set(gemist))


def test_niets_veranderd_aan_wat_niet_wordt_ingekort(make_coordinator, hass):
    c = _live_groot(make_coordinator)
    volledig = m.gacs_volledig(c)
    gacs = m.GacsAssessmentSensor(c, "x").extra_state_attributes

    for sleutel in ("samenvattingen", "zelfcontrole", "verbetermogelijkheden", "prijstoets"):
        assert gacs[sleutel] == volledig[sleutel], sleutel
    assert _pagina(c, "kwartierplanning").extra_state_attributes["kwartierplanning"] == _kwartierplanning()


# --- alles staat nog in de diagnostiek -----------------------------------


def test_de_diagnostiek_heeft_de_volledige_set(make_coordinator, hass):
    c = _live_groot(make_coordinator)

    volledig = m.gacs_volledig(c)

    for sleutel in ("eisen", "overzichtstatus", "meet_stuurt_niet", "kwartierplanning", "logboek", "rekentijd_ms"):
        assert sleutel in volledig, sleutel
    assert len(volledig["plantoetsing"]["dagen_overzicht"]) == 30
    assert len(volledig["logboek"]["regels"]) == 120
    bron = (MAP / "diagnostics.py").read_text(encoding="utf-8")
    assert '"gacs_zelfbeoordeling_volledig"' in bron


# --- elke sensor rekent alleen zijn eigen deel ---------------------------


def test_de_zelfbeoordeling_rekent_de_paginas_niet_mee(make_coordinator, hass):
    c = make_coordinator({})
    aangeroepen = []
    c.get_quarter_plan_compact = lambda *a, **k: aangeroepen.append("kwartier") or []
    c.get_event_log = lambda *a, **k: aangeroepen.append("logboek") or {}

    m.GacsAssessmentSensor(c, "x").extra_state_attributes

    assert aangeroepen == []


def test_een_pagina_rekent_alleen_zichzelf_en_een_keer_per_toestand(make_coordinator, hass):
    c = make_coordinator({})
    aangeroepen = []
    c.get_topic_summaries = lambda: aangeroepen.append("samenvattingen") or {}
    c.get_quarter_plan_compact = lambda *a, **k: aangeroepen.append("kwartier") or [{"van": "14:00"}]
    s = _pagina(c, "kwartierplanning")

    assert s.native_value == 1
    s.extra_state_attributes

    assert aangeroepen == ["kwartier"]


def test_paginas_gaan_niet_naar_de_recorder():
    for rij in m.DASHBOARD_PAGINA_SENSOREN:
        assert m.DashboardPaginaSensor._unrecorded_attributes == m.GEEN_ATTRIBUTEN_IN_RECORDER
    assert m.GacsAssessmentSensor._unrecorded_attributes == m.GEEN_ATTRIBUTEN_IN_RECORDER


@pytest.mark.asyncio
async def test_de_paginas_worden_aangemaakt(make_coordinator, hass):
    from tests.test_alles_uitgevraagd import _alle_entiteiten

    c = make_coordinator({})
    entiteiten = await _alle_entiteiten(hass, c)

    namen = {e._attr_name for e in entiteiten if isinstance(e, m.DashboardPaginaSensor)}
    assert namen == {rij[1] for rij in m.DASHBOARD_PAGINA_SENSOREN}
    ids = [e._attr_unique_id for e in entiteiten if hasattr(e, "_attr_unique_id")]
    assert len(ids) == len(set(ids))


def test_een_pagina_ruimt_geen_fout_van_de_beoordeling_op(make_coordinator, hass):
    c = make_coordinator({})
    c.get_gacs_assessment = lambda: (_ for _ in ()).throw(KeyError("stuk"))

    m.GacsAssessmentSensor(c, "x").extra_state_attributes
    for p in _paginas(c):
        p.extra_state_attributes

    assert "gacs_beoordeling" in c.internal_failures
