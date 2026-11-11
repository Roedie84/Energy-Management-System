"""Nederlandse opmaak op de detailpagina's van het dashboard (v5.217.0).

Ruud 11-11 ("volledige audit" - "Ja graag doen"): de detailpagina's toonden
getallen met een punt (962 keer op 28 pagina's), "EUR" of het euroteken
achter het bedrag, datums als 2026-04-01 en interne namen. De teksten komen
deels uit sjablonen (`{{ states(...) }} kWh`) en deels uit Python; één plek
vangt beide: elk tekstsjabloon (`primary`, `secondary`, `content`) in
`dashboard_template.yaml` staat in

    {% set ems_u %} ...het sjabloon... {% endset %}{{ ems_u | regex_replace(KOMMA) ... }}

De patronen hieronder zijn dezelfde als in het sjabloon (daar met dubbele
backslashes, zoals Jinja ze leest); `tests/test_v5217_dashboard_opmaak.py`
houdt ze gelijk en toetst wat ze wel en niet raken.

Zuiver, zonder Home Assistant.
"""
from __future__ import annotations

import re

#: Een punt tussen cijfers wordt een komma. Niet in een versie (5.214.0), een
#: IP-adres, een entiteit (sensor.x_1.5), een tijd met dubbele punt, een
#: adresparameter (v=5.1) of een getal dat al Nederlands is (1.593,5).
KOMMA = (r"(?<![\w.:/=])(\d+)\.(\d+)(?!\d|\.\d|,\d)", r"\1,\2")
#: "4,45 €" wordt "€ 4,45"; niet als het teken bij het volgende getal hoort
#: ("in 2027 € 1,22").
EURO = (r"(-?)(\d[\d,]*)\s?€(?!\s?-?\d)", r"\1€ \2")
#: 2026-04-01 wordt 01-04-2026.
DATUM = (r"\b(20\d\d)-(\d\d)-(\d\d)\b", r"\3-\2-\1")

KOP = "{% set ems_u %}"
VELDEN = ("primary", "secondary", "content")


def _jinja(tekst: str) -> str:
    return tekst.replace("\\", "\\\\").replace("'", "\\'")


def filter_tekst(patroon: tuple[str, str]) -> str:
    """Het `regex_replace`-filter zoals het in het sjabloon staat."""
    return f" | regex_replace('{_jinja(patroon[0])}', '{_jinja(patroon[1])}')"


def staart(euro: bool = False, datum: bool = False, modus: bool = False, buiten: bool = False) -> str:
    """Het slot van een gewikkeld sjabloon."""
    s = "{% endset %}{{ ems_u"
    if modus:
        s += " | replace('smart_charging (sparen)', 'bewaren') | replace('smart_charging', 'bewaren')"
    if buiten:
        s += " | replace('_buitentemperatuur', ' buitentemperatuur')"
    s += filter_tekst(KOMMA)
    if euro:
        s += " | replace('EUR', '€')" + filter_tekst(EURO)
    if datum:
        s += filter_tekst(DATUM)
    return s + " }}"


def wikkel(sjabloon: str, **vlaggen) -> str:
    """Een tekstsjabloon in de opmaak; een al gewikkeld sjabloon blijft staan."""
    if sjabloon.startswith(KOP):
        return sjabloon
    return KOP + sjabloon + staart(**vlaggen)


def kern(sjabloon: str) -> str:
    """Het sjabloon zonder de opmaak eromheen (voor toetsen die de omvang meten)."""
    if not sjabloon.startswith(KOP) or "{% endset %}{{ ems_u" not in sjabloon:
        return sjabloon
    return sjabloon[len(KOP):sjabloon.rindex("{% endset %}{{ ems_u")]


def opmaak(tekst: str, euro: bool = True, datum: bool = True) -> str:
    """Dezelfde opmaak in Python (voor toetsen en voor teksten buiten het dashboard)."""
    tekst = re.sub(KOMMA[0], KOMMA[1], tekst)
    if euro:
        tekst = re.sub(EURO[0], EURO[1], tekst.replace("EUR", "€"))
    if datum:
        tekst = re.sub(DATUM[0], DATUM[1], tekst)
    return tekst
