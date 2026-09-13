"""De lange horizon gaat sturen (v3.99.18).

Gevraagd: "Kunnen we de rijpe integreren? En dan monitoren middels de
diagnostiek wat het werkelijk heeft opgeleverd?"

De proefstandkandidaat "Verder vooruitkijken bij de reserve" (v3.11.0)
rekent elke ronde twee reserves uit: tot het eerstvolgende goedkope blok
(kort) en tot het eind van de bekende prijzen (lang). Na twee weken:
mediaan 1,48 kWh extra, en op de momenten met verschil was extra laden
in het blok goedkoper dan later van het net kopen. Dat is de enige
kandidaat die ja zegt - en hij verklaart de vier ochtenden onder de
bodem: een goedkoop blok om twaalf uur 's middags, een bewolkte dag, en
om vijf uur 's ochtends is er niets meer voor de nacht daarna.

De reserve gebruikt nu `max(kort, lang)`. De kandidaat blijft meten wat
de KORTE reserve zou zijn geweest, zodat het verschil zichtbaar blijft.
En het dagrecord legt vast wat er werkelijk gebeurde: laagste laadstand
in de ochtend, netimport 's nachts, en wat de lange horizon die dag
extra vasthield. Dat is de meting waarmee over een week te zeggen is of
het heeft geloond.
"""
from datetime import datetime, timedelta, timezone

import pytest

NU = datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc)
BLOK = NU + timedelta(hours=16)


def _reserve(c, kort, lang, aan=True):
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.last_cheap_block_start = BLOK
    c.lange_horizon_actief = aan
    c._lange_reserve_extra_kwh = max(0.0, lang - kort)
    c._estimate_worst_case_deficit_kwh = lambda now, tot: kort
    return c._get_dynamic_discharge_reserve_kwh(NU, BLOK)


def test_de_lange_horizon_verhoogt_de_reserve(make_coordinator, hass):
    c = make_coordinator({})

    zonder = _reserve(c, kort=3.0, lang=4.5, aan=False)
    met = _reserve(c, kort=3.0, lang=4.5, aan=True)

    assert met > zonder
    assert c.last_reserve_margin_breakdown["lange_horizon_extra_kwh"] == pytest.approx(1.5, abs=0.01)
    # 1,5 kWh extra vóór de marge; erna dus 1,5 x de margefactor.
    marge = c.last_reserve_margin_breakdown["total_percent"]
    assert met - zonder == pytest.approx(1.5 * (1 + marge / 100), abs=0.05)


def test_uit_is_het_oude_gedrag(make_coordinator, hass):
    c = make_coordinator({})
    _reserve(c, kort=3.0, lang=4.5, aan=False)

    assert c.last_reserve_margin_breakdown["lange_horizon_extra_kwh"] == 0.0


def test_geen_verschil_geen_effect(make_coordinator, hass):
    c = make_coordinator({})
    met = _reserve(c, kort=3.0, lang=3.0, aan=True)
    zonder = _reserve(c, kort=3.0, lang=3.0, aan=False)

    assert met == pytest.approx(zonder, abs=0.001)


def test_de_meting_blijft_de_korte_reserve_meten(make_coordinator, hass):
    """De kandidaat moet het tegenfeitelijke blijven zien, anders is het

    verschil na inschakeling niet meer te meten.
    """
    c = make_coordinator({})
    c.lange_horizon_actief = True
    c.last_cheap_block_start = BLOK
    c.last_cheap_block_end = BLOK + timedelta(hours=2)
    c._estimate_worst_case_deficit_kwh = lambda now, tot: 3.0 if tot == BLOK else 4.5
    c.lange_reserve_history = []
    entries = [(BLOK - timedelta(hours=1), None, 3000), (BLOK, None, 500), (BLOK + timedelta(hours=3), None, 3500)]

    c._meet_lange_reserve(NU, entries)

    r = c.lange_reserve_history[-1]
    assert r["reserve_kort_kwh"] == 3.0
    assert r["extra_kwh"] == 1.5
    assert c._lange_reserve_extra_kwh == 1.5


def test_het_dagrecord_legt_de_ochtend_vast(make_coordinator, hass):
    c = make_coordinator({})
    c._lange_horizon_extra_vandaag = 1.5
    c._laagste_soc_ochtend = 31.0
    c._netimport_nacht_kwh = 0.4

    record = c._lange_horizon_dagrecord()

    assert record == {"lange_horizon_extra_kwh": 1.5, "laagste_soc_ochtend": 31.0, "netimport_nacht_kwh": 0.4}


def test_de_ochtendmeting_leest_de_sensor(make_coordinator, hass):
    """v3.99.19: `accustand_procent` is een METHODE, en de ochtendmeting

    van v3.99.18 las hem als veld - een methode-object, en dan een
    TypeError bij de eerste ronde tussen 03:00 en 09:00. De volledige
    suite ving dat niet, omdat niets die ronde met echte waarden draaide.
    """
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    hass.states.set("sensor.soc", "31")
    c._laagste_soc_ochtend = None

    c._volg_de_ochtend(datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc))
    hass.states.set("sensor.soc", "28")
    c._volg_de_ochtend(datetime(2026, 9, 9, 5, 0, tzinfo=timezone.utc))

    assert c._laagste_soc_ochtend == 28.0
