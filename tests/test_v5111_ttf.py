"""v5.111.0: TTF-gasprijs van OilPriceAPI (sleutel in secrets.yaml)."""
from datetime import date
from pathlib import Path

from custom_components.energy_management_system import prijsverwachting as P

BRON = (Path(__file__).resolve().parent.parent / "custom_components" / "energy_management_system"
        / "coordinator.py").read_text(encoding="utf-8")


def test_maand_en_laatste_prijs():
    maand = {"status": "success", "data": {"prices": [
        {"price": 30.0, "code": "DUTCH_TTF_EUR", "created_at": "2026-10-18T16:00:00Z"},
        {"price": 31.0, "code": "DUTCH_TTF_EUR", "created_at": "2026-10-19T16:00:00Z"},
        {"price": 99.0, "code": "BRENT_CRUDE_USD", "created_at": "2026-10-19T16:00:00Z"},
        {"price": None, "created_at": "2026-10-17T16:00:00Z"},
    ]}}
    uit = P.ttf_uit_antwoord(maand)
    assert uit == {date(2026, 10, 18): round(30 * P.M3_PER_MWH, 5), date(2026, 10, 19): round(31 * P.M3_PER_MWH, 5)}
    laatst = {"status": "success", "data": {"price": 33.5, "code": "DUTCH_TTF_EUR",
                                            "created_at": "2026-10-20T17:30:00.000Z"}}
    assert P.ttf_uit_antwoord(laatst) == {date(2026, 10, 20): round(33.5 * P.M3_PER_MWH, 5)}
    assert P.ttf_uit_antwoord(None) == {} and P.ttf_uit_antwoord({"status": "error"}) == {}


def test_een_bron_voor_de_hele_reeks():
    zp = {date(2026, 10, d): 1.8 for d in range(1, 21)}
    kort = {date(2026, 10, d): 0.3 for d in range(10, 21)}
    assert P.kies_gas(kort, zp) == (zp, "zonneplan")
    lang = {date(2026, 9, 1 + d % 30): 0.3 for d in range(25)}
    assert P.kies_gas(lang, zp)[1] == "ttf"
    assert P.kies_gas({}, {}) == ({}, "geen")


def test_sleutel_uit_secrets_en_spaarzaam():
    assert '"oilpriceapi_key"' in BRON and 'f"Token {str(sleutel).strip()}"' in BRON
    assert "timedelta(hours=23)" in BRON and "timedelta(minutes=55)" in BRON
    # de sleutel komt nooit in een log of attribuut
    deel = BRON[BRON.index("async def _ttf_per_dag"):BRON.index("async def _zaai_uit_statistiek")]
    assert "_LOGGER.debug(\"TTF ophalen mislukt (%s): %s\", soort, type(fout).__name__)" in deel
