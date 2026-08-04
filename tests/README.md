# Testsuite

Een permanente pytest-suite die de belangrijkste, ooit handmatig
geverifieerde scenario's vastlegt als automatische regressietests -
zodat toekomstige wijzigingen niet per ongeluk iets breken dat al eens
gefixt is.

## Draaien

```bash
pip install pytest --break-system-packages
cd energy_management_system  # repo-root
python3 -m pytest -v
```

Werkt zonder een echte Home Assistant-installatie: `conftest.py` bouwt
een minimale mock van de benodigde `homeassistant.*`-modules, zodat de
integratie op de normale manier (met haar eigen relatieve imports)
geïmporteerd en getest kan worden.

## Wat wordt getest

| Bestand | Dekt |
|---|---|
| `test_price_threshold.py` | Dynamische "duur"-prijsdrempel (top-fractie i.p.v. vast aantal) |
| `test_winter_guard_and_emergency_charge.py` | Winter-guard (geen dubbele verkoop na netladen) + noodladen alleen bij weinig zon |
| `test_negative_price_and_hysteresis.py` | Negatieve-prijs-afhandeling + hysterese tegen flikkeren |
| `test_efficiency_learning.py` | Zelflerend accu-rendement + PV-uurbias-persistentie |
| `test_worst_case_reserve.py` | **De belangrijkste veiligheidsfix**: diepste-tekort-reserve i.p.v. netto-eindsaldo, plus live-verbruikscorrectie |
| `test_price_priority_and_scheduling.py` | Prijs-prioriteit bij beperkte headroom + discharge_start-ordeningsfix |
| `test_unit_conversion.py` | Automatische Wh/MWh → kWh-conversie |
| `test_structural_integrity.py` | AST-gebaseerde scan die de twee historische "verweesde klasse"-regressies had gevangen |
| `test_consumption_floor.py` | Ontlaadvermogen zakt nooit onder het live huishoudverbruik (v0.59.0) |
| `test_decision_visibility.py` | Extra diagnostiek-zichtbaarheid: prijslaag, prijs-prioriteit-hold-off, SoC-taper-fallback, reserve-marge-breakdown (v0.60.0) |
| `test_startup_timing.py` | Wachten op volledige HA-opstart vóór de eerste dataophaal |

## Waarom dit de moeite waard is

Twee van de bugs die tijdens de ontwikkeling zijn gevonden (v0.34.3 en
v0.40.1) ontstonden doordat een bewerking per ongeluk een bestaande
methode/klasse beschadigde bij het toevoegen van nieuwe code ernaast.
Beide compileerden probleemloos — pas bij daadwerkelijk gebruik (Home
Assistant-opstart) kwamen ze aan het licht. `test_structural_integrity.py`
is specifiek ontworpen om precies dit soort fouten automatisch te
vangen, zonder dat daar een live HA-instantie voor nodig is. Getest door
beide historische bugs tijdelijk opnieuw te introduceren: beide werden
meteen gevangen, met dezelfde foutmelding als destijds in productie.
