# De dataketen achter de cockpit

Gevraagd: *"beoordeel nu eerst kritisch de dataketen achter ieder element dat
op deze cockpit staat"*, met per veld de bron, de eenheid, de maximale
leeftijd, wat de UI toont bij ontbrekende en bij verouderde gegevens, en de
invloed op de algemene toestand.

Dit document is de verantwoording van de cockpit. Staat een veld hier niet
in, dan hoort het niet op het hoofdscherm.

---

## Twee fouten die deze audit blootlegde

### 1. "sensoren 100%" meet iets anders dan het zegt

`get_sensor_health_breakdown()` rekent over `energy_balance_error_history`:
de metingen van de **energiebalanscontrole**. Het percentage zegt dus hoe
vaak die controle een waarde had, niet of je sensoren gezond zijn. Het
label was onjuist.

Wat er wél een uitspraak over doet is `get_configuratiecontrole()`: elke
ingestelde entiteit, met `in_orde`, `stuk` of `slaapt`. Dat is de bron
geworden.

### 2. De reserve stond op de verkeerde plek in de balk

De laadstand is een percentage van de **hele** accu. De reserve is energie
**boven de ondergrens**. Die twee zijn tegen elkaar uitgezet alsof ze
dezelfde nul hadden.

Met een ondergrens van 10% en 8,64 kWh capaciteit hoort 4,60 kWh reserve bij
een laadstand van 10 + 4,60/8,64 = **63%**, niet bij 53%. De balk wees dus
tien procentpunt te laag, precies in het geval waarin het ertoe doet.

Omrekening voortaan expliciet:

```
reserve_deel = ondergrens% / 100 + reserve_kwh / capaciteit_kwh
```

---

## Per veld

| Veld | Bron | Eenheid | Max leeftijd | Ontbreekt | Verouderd |
|---|---|---|---|---|---|
| Status | zie matrix hieronder | — | 1 ronde | ONBEKEND | ONBEKEND |
| Koppelingen | `get_configuratiecontrole()` | aantal | 1 ronde | veld weg | veld weg |
| Balans | `get_energiebalans_controle()` | ✓ / wijkt af | 1 ronde | veld weg | veld weg |
| Voorspelling ±% | `solar_tracker.deviation_stdev_percent()` | % | 14 dagen leerdata | veld weg | veld weg |
| Zon nu | `CONF_PV_POWER_SENSOR` | W | 5 min | — | — |
| Zon verwacht | `CONF_SOLAR_REMAINING_TODAY_SENSOR` | kWh | 30 min | regel weg | regel weg |
| Net nu | `CONF_CONSUMPTION_POWER_SENSOR` (P1) | W | 5 min | ONBEKEND | ONBEKEND |
| Richting net | teken van het netvermogen | INKOOP / TERUGLEVERING | 5 min | ONBEKEND | ONBEKEND |
| Prijs | `huidige_prijs_eur_per_kwh()` | ct/kWh | 15 min | — | — |
| Goedkoop blok | `last_cheap_block_start` | tijd | tot het blok | veld weg | veld weg |
| Huis nu | `_huisverbruik_w()` = net + zon + accu | W | 5 min | ONBEKEND | ONBEKEND |
| Grootste verbruiker | `get_largest_known_consumer()` | naam | 15 min | regel weg | regel weg |
| Laadstand | `accustand_procent()` | % | 5 min | — | — |
| Accuvermogen | `_read_corrected_battery_power()` | W (positief = ontladen) | 5 min | — | — |
| Accustand | teken van het accuvermogen | LADEN/ONTLADEN/STANDBY | 5 min | ONBEKEND | ONBEKEND |
| Reserve | `last_reserve_margin_breakdown` | kWh | 1 ronde | GEEN BLOK | ONBEKEND |
| Capaciteit | `bruikbare_capaciteit_kwh()` | kWh | 1 dag | balk weg | balk weg |
| Ondergrens | `CONF_MIN_SOC_PERCENT` / accu-entiteit | % | — | balk weg | balk weg |
| Vrij | beschikbaar − reserve | kWh | 1 ronde | — | — |
| Dagtotalen | `get_period_overview()` → vandaag | kWh | 1 ronde | regel weg | regel weg |
| Verloop | `dagverloop` van vandaag | kW per uur | 15 min | grafiek weg | grafiek weg |
| EMS-besluit | `get_why_now()["kort"]` | tekst | 1 ronde | ONBEKEND | ONBEKEND |
| Uitleg | `last_explanation` | tekst | 1 ronde | regel weg | regel weg |
| Waarom | `get_why_now()["redenen"]` | tekst | 1 ronde | regel weg | regel weg |
| Volgende actie | `get_quarter_plan()` | tekst + tijd | tot dat kwartier | ONBEKEND | ONBEKEND |
| Aandacht | `get_diagnostic_summary()["aandachtspunten"]` | aantal | 1 ronde | ONBEKEND | ONBEKEND |

"1 ronde" betekent: gezet in de laatste ronde van de coördinator. Ouder dan
`METING_MAX_LEEFTIJD_MINUTEN` (5 minuten) geldt als verouderd, dezelfde
grens die de aansturing zelf gebruikt voor een terugvalwaarde.

**Nooit een nul bij ontbreken.** Een 0 W is een echte meting: de accu die
stilstaat, de zon die niet schijnt. Ontbrekende gegevens tonen een streepje
of ONBEKEND.

---

## De statusmatrix

De eerste regel die past, bepaalt de stand. Alleen bestaande condities:

| Stand | Voorwaarde | Bron |
|---|---|---|
| STORING | een interne storing, of een ingestelde entiteit is kapot | `internal_failures`, `get_configuratiecontrole()["aantal_stuk"]` |
| STORING | de ronde is meer dan 20 minuten niet gelukt | `last_successful_update`, `CONSISTENCY_TICK_STALE_MINUTES` |
| INGRIJPEN | een aandachtspunt met ernst "fout" | `get_diagnostic_summary()["aandachtspunten"]` |
| LET OP | een aandachtspunt van lagere ernst, of de energiebalans wijkt af | idem, `get_energiebalans_controle()["alles_klopt"]` |
| GOED | geen van bovenstaande | — |

Er is bewust **geen** stand op basis van de voorspellingsspreiding: een
onzekere zonverwachting is geen storing, en hij staat al als getal op het
scherm.

---

## Wat er NIET op de cockpit staat, en waarom

- **Een confidence-percentage.** Bestaat niet in het EMS. De gemeten
  spreiding van de zonvoorspelling staat er wel.
- **Waarom de reserve 4,60 kWh is.** Dat is de dynamische reserve met al
  zijn componenten; die uitsplitsing hoort achter een doorklik.
- **Meldingen per 24 uur.** Dat getal verwart naast een status GOED.
- **De lijst aandachtspunten.** Alleen het aantal; de punten zelf staan op
  de gezondheidspagina.

---

## Tegenstrijdigheden die niet stilzwijgend getoond mogen worden

Gevraagd: *"als informatie tijdelijk inconsistent of stale is, toon liever
ONBEKEND of een waarschuwing dan een geloofwaardige maar verkeerde
cockpit"*. Deze combinaties worden gecontroleerd voordat de plaat wordt
getekend:

1. **LADEN of ONTLADEN bij 0 W** — dan STANDBY.
2. **INKOOP of TERUGLEVERING die niet bij de pijlrichting past** — beide uit
   hetzelfde getal afgeleid, dus dit kan alleen fout gaan als de richting
   ergens apart wordt gezet. Een toets bewaakt dat ze één bron delen.
3. **Een besluit zonder waarom** — dan ONBEKEND in plaats van alleen de
   strategie: een besluit zonder motivatie is precies wat deze cockpit niet
   moet tonen.
4. **Een volgende actie die al voorbij is** — een tijd in het verleden
   wordt niet getoond.
5. **Een huisverbruik terwijl een van de drie delen (net, zon, accu)
   ontbreekt** — de som klopt dan niet, dus ONBEKEND.
6. **Status GOED terwijl een ingestelde entiteit kapot is** — uitgesloten
   door de matrix hierboven: dat is STORING.
