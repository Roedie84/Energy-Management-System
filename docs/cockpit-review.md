# Kritische review van de cockpit-datalaag

Doel: *"niet bewijzen dat de cockpit mooi werkt, maar proberen hem
doelgericht stuk te krijgen."*

Vijf echte fouten gevonden, twee ontbrekende definities, en drie plekken
waar de cockpit meer belooft dan de gegevens waarmaken. Niets aangepast -
dit is de inventarisatie.

---

## FOUT 1 — De dode band bestond al, en ik gebruikte hem niet

**Punt 2.** Ik schreef "LADEN of ONTLADEN bij 0 W → STANDBY", met exact nul
als grens. Het EMS heeft die grens al:

```python
MIN_BATTERY_POWER_IDLE_W = 25.0        # const.py

def get_battery_power_display(self):
    if abs(vermogen_w) < MIN_BATTERY_POWER_IDLE_W:
        return "rust"
```

Bij 12 W zegt de sensor "rust" en zou de cockpit "ONTLADEN" zeggen. Twee
antwoorden op dezelfde vraag.

**Oplossing uit bestaande logica**: dezelfde constante gebruiken. Geen
zelfgekozen waarde.

---

## FOUT 2 — De volgende actie komt nooit uit het kwartierplan

**Punt 11.** Mijn `_volgende_actie()` zoekt naar sleutels die niet bestaan:

```python
moment = regel.get("moment") or regel.get("tijd")     # bestaan niet
reden  = regel.get("reden")  or regel.get("modus")
```

Het kwartierplan levert: `van`, `tot`, `start`, `modus`, `gewijzigd`,
`prijs_ct`, `soc_procent`, `in_goedkoop_blok`, `tekort` en meer. `moment`
en `tijd` zitten er niet bij, `reden` evenmin.

Gevolg: de lus vindt nooit iets en valt **altijd** terug op het goedkope
blok. "laden 23:00" was dus niet de eerstvolgende geplande verandering,
maar het begin van het goedkope blok - toevallig vaak hetzelfde, en daarom
niet opgevallen.

**Oplossing uit bestaande logica**: de eerste planregel na nu waarvan
`modus` verschilt van de huidige, met `van` als tijd. Dat is per definitie
de eerstvolgende geplande verandering.

---

## FOUT 3 — De capaciteit is geen eenduidige noemer

**Punt 3.** De voorgestelde formule

```
reserve_deel = ondergrens% / 100 + reserve_kwh / capaciteit_kwh
```

klopt alleen als `capaciteit_kwh` de **hele** accu is, van 0 tot 100%. Dat
is niet gegarandeerd:

```python
def bruikbare_capaciteit_kwh(self):
    gemeten = self.gemeten_capaciteit_kwh()      # "de GEMETEN bruikbare capaciteit"
    if gemeten is not None:
        return gemeten
    return self._read_sensor_float(CONF_BATTERY_TOTAL_CAPACITY_SENSOR)  # nominaal
```

Die functie geeft dus **de ene keer de gemeten bruikbare capaciteit en de
andere keer de nominale**, en schakelt stilzwijgend om zodra er genoeg
trenddagen zijn. Een laadstand is een percentage van de fysieke accu; een
bruikbare capaciteit is dat niet. Is de gemeten waarde al ontdaan van de
ondergrens, dan wordt die ondergrens in mijn formule een tweede keer
opgeteld.

**Dit is een ontbrekende definitie, geen rekenfout.** Voor de balk is een
noemer nodig die aantoonbaar 0 tot 100% van het pakket is. Die bestaat:
de nominale capaciteitssensor van de Zendure. En de ondergrens bestaat ook
als echte entiteit: `number.solarflow_2400_ac_min_soc`.

Wat ik NIET ga doen is `bruikbare_capaciteit_kwh()` gebruiken en hopen dat
het goed valt. Wat ik voorstel: de balk uitsluitend tekenen met de nominale
capaciteit en de ondergrens-entiteit, en de balk WEGLATEN als een van beide
ontbreekt.

Openstaande vraag die jij moet beantwoorden of die ik apart moet uitzoeken:
is `gemeten_capaciteit_kwh()` gemeten over 0-100% of over het bruikbare
venster? Zolang dat niet vaststaat, blijft hij uit de balk.

---

## FOUT 4 — "Vrij" kan negatief worden, en dat is nu juist het nieuws

**Punt 4.** De keten:

```
beschikbaar = sensor "SolarFlow Beschikbare Energie"   (kWh, boven de eigen
                                                        ondergrens van het
                                                        apparaat, geklemd op 0)
reserve     = last_reserve_margin_breakdown
              ["reserve_kwh_after_margin"]             (kWh, zelfde referentie)
vrij        = beschikbaar - reserve
```

De randgevallen:

| Geval | beschikbaar | reserve | vrij | Wat de cockpit moet tonen |
|---|---|---|---|---|
| A. laadstand op de ondergrens | 0,00 | 2,01 | −2,01 | **0,00 kWh vrij** én het tekort in de balk |
| B. precies op de reserve | 2,01 | 2,01 | 0,00 | 0,00 - een echte nul |
| C. vol | 7,8 | 2,01 | 5,8 | gewoon |
| D. reserve 0 | 4,9 | 0,00 | 4,9 | gewoon |
| E. reserve > beschikbaar | 0,95 | 4,60 | −3,65 | **0,00 vrij**, tekort zichtbaar |
| F. reserve > capaciteit | — | 9,9 | — | **diagnostisch probleem**, niet wegpoetsen |

Geval F is fysiek onmogelijk: er wordt een reserve gevraagd die niet in de
accu past. Dat stilzwijgend afkappen verbergt een fout in de
reserveberekening. Dat hoort een aandachtspunt te worden, niet een mooi
getal.

Vandaag toont de cockpit in geval A en E gewoon `vrij 0,0 kWh` zonder dat
het tekort ergens uit blijkt, behalve uit de balk. Dat is te zwak.

---

## FOUT 5 — Een kapotte kookplaat zou STORING opleveren

**Punt 7.** Mijn statusmatrix zegt:

```python
if storingen or stuk:        # stuk = get_configuratiecontrole()["aantal_stuk"]
    stand = "STORING"
```

`aantal_stuk` telt **elke** ingestelde entiteit, ook de vrijwillige. Valt de
vaatwasser-sensor weg, dan staat het hele EMS op STORING terwijl de
aansturing perfect draait. Dat is precies de vermenging die jij in punt 7
uitsluit.

De vier verplichte instellingen zijn bekend uit de configuratiestroom:
prijssensor, prijsattribuut, bedrijfsmodus en handmatig vermogen. Daarnaast
zijn het accuvermogen, de P1-meter en de laadstand nodig om te kunnen
sturen.

**Oplossing uit bestaande gegevens**: alleen een kapotte entiteit die de
aansturing nodig heeft leidt tot STORING; de rest tot LET OP.

---

## ONTBREKENDE DEFINITIE 1 — Veroudering van de bron

**Punt 8.** Er zijn drie verschillende begrippen, en ze lopen inderdaad
door elkaar:

| Begrip | Mechanisme | Grens |
|---|---|---|
| bronmeting weg | `_sensor_unavailable_since`, `is_sensor_genuinely_unavailable()` | 15 min |
| coördinatorveld oud | `meting_tijdstippen` + `_meting_is_vers()` | 5 min |
| ronde niet gelukt | `last_successful_update` | 20 min |

Het gat: `_read_sensor_float()` leest de **huidige toestand** uit Home
Assistant en kijkt niet naar de ouderdom daarvan. Een sensor die blijft
hangen op zijn laatste waarde - niet weg, wel bevroren - komt als verse
meting binnen.

Gedeeltelijk vangnet dat al bestaat: `sensor_cadence` meet per sensor hoe
vaak hij beweegt, en de configuratiecontrole meldt een sensor die niets
meer levert. Maar er is **geen bestaande grens voor "deze waarde is te oud"**
op een live sensor.

Ik ga die grens niet zelf kiezen. Voorstel: de cockpit gebruikt wat er wél
is - weg is ONBEKEND - en voor bevroren sensoren blijft de bestaande
cadansmeting het signaal, op de gezondheidspagina.

---

## ONTBREKENDE DEFINITIE 2 — Besluit en waarom zijn niet atomair

**Punt 10.** Twee bronnen, twee momenten:

```
besluit   get_why_now()      berekent bij AANROEP, uit de huidige waarden
uitleg    last_explanation   gezet tijdens de RONDE
```

`get_why_now()` leest prijs, laadstand, beschikbaar en reserve op het moment
dat de plaat wordt getekend. `last_explanation` komt uit de laatste ronde.
Tussen die twee zit tot een ronde verschil, en bij een wissel op het
kwartier kan de plaat een nieuw besluit naast een oude verklaring zetten -
precies wat jij wilt voorkomen.

Er bestaat geen enkele plek waar besluit, uitleg en redenen samen als één
momentopname worden vastgelegd. Dat is de ontbrekende definitie.

**Oplossing uit bestaande logica**: aan het eind van de ronde, waar
`last_explanation` toch al wordt gezet, ook `get_why_now()` aanroepen en de
drie samen wegschrijven. Eén snapshot, één moment. Dat voegt geen nieuwe
grootheid toe; het legt bestaande grootheden op hetzelfde tijdstip vast.

---

## Drie plekken waar de cockpit meer belooft dan hij waarmaakt

**Het label bij de configuratiecontrole (punt 6).** De functie loopt de
ingestelde entiteiten na en oordeelt per stuk: in orde, kapot of slaapt.
Dat is niet "sensoren" en niet "bronnen" - het zijn de koppelingen die in
de configuratie staan. Het label wordt **KOPPELINGEN**.

**"—" tegen ONBEKEND (punt 1).** Nu door elkaar: `_vermogen(None)` geeft
"—", en dat staat op primaire waarden. Jouw regel is scherper en wordt
overgenomen: 0 is een meting, ONBEKEND is geen meting, en "—" alleen voor
bijzaken die mogen verdwijnen.

**Afgeleide waarden (punt 9).** `_huisverbruik_w()` telt net, zon en accu
op. Ontbreekt er één, dan is de som geen huisverbruik meer. Hetzelfde geldt
voor netrichting, accustand en vrij. Die moeten de betrouwbaarheid van hun
invoer erven: één ONBEKEND erin is ONBEKEND eruit.

---

## De statusmatrix na deze review

| Volgorde | Stand | Voorwaarde | Bron |
|---|---|---|---|
| 1 | ONBEKEND | de diagnostiek zelf is niet op te halen | uitzondering uit `get_diagnostic_summary()` |
| 2 | STORING | ronde langer dan 20 min niet gelukt | `last_successful_update` |
| 3 | STORING | interne storing | `internal_failures` |
| 4 | STORING | een voor de aansturing NOODZAKELIJKE entiteit is kapot | `get_configuratiecontrole()` |
| 5 | INGRIJPEN | aandachtspunt met ernst "fout" | `get_diagnostic_summary()` |
| 6 | LET OP | overige aandachtspunten, afwijkende energiebalans, of een niet-noodzakelijke entiteit kapot | idem, `get_energiebalans_controle()` |
| 7 | GOED | geen van bovenstaande | — |

Volledig: elke regel sluit uit wat eronder staat, en regel 7 vangt de rest.
Geen overlap: regel 4 en 6 delen dezelfde bron maar splitsen op
noodzakelijkheid, en die splitsing moet expliciet in de code staan.

---

## De testmatrix

Tweeëntwintig gevallen, elk met: welke primaire waarden zichtbaar zijn,
welke afgeleide, wat ONBEKEND wordt, wat verdwijnt, welke status ontstaat
en waarom.

```
zonnig · nacht met PV exact 0 W · accu standby (12 W, binnen de dode band)
accu laden · accu ontladen · netimport · teruglevering
laadstand onder reserve · precies op reserve · boven reserve
PV-sensor weg · P1-sensor weg · accusensor weg · bronmeting bevroren
energiebalans wijkt af · niet-noodzakelijke entiteit stuk
noodzakelijke entiteit stuk · ronde 25 minuten oud
besluit zonder reden · geen volgende actie · kwartierplan verouderd
reserve niet beschikbaar · capaciteit niet beschikbaar
```

Die matrix wordt de toets, niet het plaatje.
