"""De kern van de diagnostiek, leesbaar voor de assistent (v5.14).

Gevraagd: *"Nu moet ik telkens de diagnostiek downloaden, je hebt al toegang
tot vele entiteiten van HA, kunnen we het zo maken dat jij de diagnostiek
rechtstreeks uitleest?"*

De connector geeft alleen TOESTANDEN door - geen attributen, geen bestanden
- en een toestand mag hoogstens 255 tekens zijn. Drie sensoren zetten de
kern van de export in die ruimte.
"""
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "opslag_echt.json"


def _verplicht():
    from test_alles_uitgevraagd import _maximaal

    return _maximaal()


def test_elke_regel_past_in_een_toestand(make_coordinator, hass):
    c = make_coordinator(_verplicht())

    for soort in ("gezondheid", "sturing", "leren"):
        regel = c.diagnose_regel(soort)
        assert regel, soort
        assert len(regel) <= 255, (soort, len(regel))


def test_de_gezondheidsregel_bevat_de_kern(make_coordinator, hass):
    c = make_coordinator(_verplicht())
    regel = c.diagnose_regel("gezondheid")

    for sleutel in ("fout", "storing", "zelfctl", "bestand", "config"):
        assert sleutel in regel, (sleutel, regel)


def test_een_onderdeel_dat_omvalt_breekt_de_regel_niet(make_coordinator, hass):
    """Anders valt precies bij een storing de sensor om die de storing had
    moeten laten zien."""
    c = make_coordinator(_verplicht())

    def kapot():
        raise RuntimeError("stuk")

    c.get_analyse = kapot
    regel = c.diagnose_regel("gezondheid")

    assert "fout ?" in regel
    assert "storing" in regel


def test_de_regels_op_de_echte_toestand(make_coordinator, hass):
    if not FIXTURE.exists():
        pytest.skip("geen echte toestand in tests/fixtures")
    c = make_coordinator(_verplicht())
    c._apply_persisted_state(json.loads(FIXTURE.read_text()))

    for soort in ("gezondheid", "sturing", "leren"):
        regel = c.diagnose_regel(soort)
        assert len(regel) <= 255, (soort, len(regel), regel)
        # "?" betekent dat een onderdeel omviel; op een echte toestand mag
        # dat nergens gebeuren. Een "-" (geen waarde) mag wel: in de toets
        # zijn er geen live sensoren.
        assert "?" not in regel, (soort, regel)


def test_de_meldingensensor_en_de_regel_delen_een_bron(make_coordinator, hass):
    """Twee plekken die hetzelfde tellen, lopen vroeg of laat uiteen."""
    from custom_components.energy_management_system.sensor import MeldingenSensor

    c = make_coordinator(_verplicht())
    c.meldingen_laatste_24u = lambda: 7

    assert MeldingenSensor(c, "x").native_value == 7
    assert "meld24u 7" in c.diagnose_regel("leren")
