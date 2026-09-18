"""Een onbetrouwbare weerbron valt uit het ensemble (v5.3).

Gemeten op 18 september, beide bronnen:

    weather.forecast_thuis      74,5% over 200 waarnemingen  indicatief
    weather.openweathermap      74,5% over 200 waarnemingen  indicatief

De beoordeling bestond al - 80% goed, 60% bruikbaar, daaronder
onbetrouwbaar - maar `RELIABILITY_UNRELIABLE` werd NERGENS gebruikt om
een bron te weren. Elke bron met een bewolkingsmeting kwam in
`cloud_readings`, ongeacht zijn oordeel. De status was een label, geen
poort.

En er was een tweede gat: de tak die de BESTE bron kiest, werkt alleen
als de bronnen ONDERLING meer dan 25 procentpunt verschillen. Twee
slechte bronnen die het met elkaar eens zijn, werden dus allebei
meegenomen en nooit bevraagd - precies de situatie hierboven.

Dat is de tegenhanger van wat er deze weken zes keer is opgeruimd: een
controle die maar één kant op kan. Er was een drempel die een bron
goedkeurt en geen die hem afkeurt.

Nu wel, met twee veiligheidsregels: er moeten genoeg waarnemingen zijn,
en de laatste bron valt nooit uit - geen voorspelling is erger dan een
matige.
"""
import pytest


def _bron(c, entity_id, percentage, waarnemingen=200):
    c.weather_source_agreement = dict(c.weather_source_agreement or {})
    c.weather_source_agreement[entity_id] = [
        True if i < round(waarnemingen * percentage / 100) else False
        for i in range(waarnemingen)
    ]


def test_een_slechte_bron_valt_uit_het_ensemble(make_coordinator, hass):
    from custom_components.energy_management_system.const import (
        WEATHER_ENSEMBLE_AGREEMENT_USABLE_PERCENT,
    )

    c = make_coordinator({})
    _bron(c, "weather.goed", 85.0)
    _bron(c, "weather.slecht", 40.0)

    uit = c.weerbronnen_voor_het_ensemble(["weather.goed", "weather.slecht"])

    assert uit["gebruikt"] == ["weather.goed"]
    assert uit["geweerd"] == ["weather.slecht"]
    assert WEATHER_ENSEMBLE_AGREEMENT_USABLE_PERCENT == 60.0


def test_bij_te_weinig_waarnemingen_blijft_een_bron_meedoen(make_coordinator, hass):
    """Een bron met tien waarnemingen op 40% is geen slechte bron, dat is
    een bron die nog niets heeft bewezen."""
    c = make_coordinator({})
    _bron(c, "weather.goed", 85.0)
    _bron(c, "weather.nieuw", 40.0, waarnemingen=10)

    uit = c.weerbronnen_voor_het_ensemble(["weather.goed", "weather.nieuw"])

    assert uit["geweerd"] == []


def test_de_laatste_bron_valt_nooit_uit(make_coordinator, hass):
    """Geen voorspelling is erger dan een matige."""
    c = make_coordinator({})
    _bron(c, "weather.slecht", 30.0)
    _bron(c, "weather.slechter", 25.0)

    uit = c.weerbronnen_voor_het_ensemble(["weather.slecht", "weather.slechter"])

    assert uit["gebruikt"], "alles geweerd - dan is er geen voorspelling meer"
    assert "geen enkele bron" in uit["reden"].lower() or "laatste" in uit["reden"].lower()


def test_de_huidige_situatie_verandert_niet(make_coordinator, hass):
    """Beide bronnen op 74,5% - dat is boven de 60, dus geen van beide
    valt uit. De poort verandert vandaag dus NIETS aan de sturing; hij
    grijpt pas in als een bron werkelijk wegzakt."""
    c = make_coordinator({})
    _bron(c, "weather.forecast_thuis", 74.5)
    _bron(c, "weather.openweathermap", 74.5)

    uit = c.weerbronnen_voor_het_ensemble(
        ["weather.forecast_thuis", "weather.openweathermap"]
    )

    assert uit["geweerd"] == []
    assert len(uit["gebruikt"]) == 2


def test_het_weren_wordt_gemeld(make_coordinator, hass):
    """Niet stil: als een bron uit het ensemble valt, hoort dat gezegd te
    worden - anders verandert de voorspelling zonder dat iemand weet
    waarom."""
    from custom_components.energy_management_system.const import (
        NOTIFICATION_TYPES,
    )

    soorten = {t[0] for t in NOTIFICATION_TYPES}

    assert "weerbron_geweerd" in soorten


def test_een_bron_zonder_beoordeling_blijft_meedoen(make_coordinator, hass):
    c = make_coordinator({})
    c.weather_source_agreement = {}

    uit = c.weerbronnen_voor_het_ensemble(["weather.onbekend"])

    assert uit["gebruikt"] == ["weather.onbekend"]


def test_de_poort_zit_in_het_ensemble(make_coordinator, hass):
    """De ratel: het weren moet in het pad zitten dat de bewolking
    bepaalt, niet alleen in een los overzicht. Dat was precies de fout -
    de status bestond en werd nergens gebruikt."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    i = bron.index("def _weer_de_slechte_bronnen")
    j = bron.index("\n    def ", i + 10)

    assert "weerbronnen_voor_het_ensemble" in bron[i:j]
