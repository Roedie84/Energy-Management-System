<div align="center">

# Energy Management System

**Home Assistant-integratie die een thuisaccu aanstuurt op dynamische energieprijzen — en zichzelf bijleert.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://hacs.xyz)
[![Version](https://img.shields.io/badge/versie-3.34.0-blue.svg?style=flat-square)](CHANGELOG.md)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.6.0%2B-41BDF5.svg?style=flat-square)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-2639%20groen-brightgreen.svg?style=flat-square)](tests)
[![License](https://img.shields.io/badge/licentie-MIT-lightgrey.svg?style=flat-square)](LICENSE)

</div>

---

> **In short (EN)** — A Home Assistant integration that controls a home
> battery (Zendure SolarFlow and similar) on quarter-hourly dynamic
> electricity prices. It decides when to charge, discharge, sell or hold,
> using a self-learning consumption profile, a worst-case night reserve
> and solar forecasts. Documentation is in Dutch because the integration
> targets the Dutch market specifically: quarter-hourly pricing, the
> `salderingsregeling`, and Dutch-language notifications.

---

## Inhoud

- [Wat doet het](#wat-doet-het)
- [Kenmerken](#kenmerken)
- [Vereisten](#vereisten)
- [Installatie](#installatie)
- [Configuratie](#configuratie)
- [Dashboard](#dashboard)
- [Hoe de beslislogica werkt](#hoe-de-beslislogica-werkt)
- [Zelflerend gedrag](#zelflerend-gedrag)
- [Meldingen](#meldingen)
- [Diensten](#diensten)
- [Diagnostiek en probleemoplossing](#diagnostiek-en-probleemoplossing)
- [Ontwikkeling](#ontwikkeling)
- [Licentie en aansprakelijkheid](#licentie-en-aansprakelijkheid)

---

## Wat doet het

Met een dynamisch energiecontract verschilt de stroomprijs per kwartier —
soms met een factor vijf op één dag. Een thuisaccu kan daarvan
profiteren, maar alleen als hij op de juiste momenten laadt en ontlaadt.

Deze integratie neemt die beslissing elke vijf minuten, op basis van:

- de prijzen van de komende uren, zoveel als je leverancier levert;
- de zonvoorspelling, gecorrigeerd met wat jouw panelen werkelijk doen;
- je eigen verbruikspatroon per uur van de week;
- hoeveel energie er in de accu moet blijven om de nacht te overbruggen.

Je wijst een prijssensor aan, een `select` voor de accumodus en een
`number` voor het vermogen. De rest — welk kwartier duur genoeg is,
hoeveel reserve er nodig is, wanneer laden beter kan wachten — rekent en
leert de integratie zelf.

**Getest tegen** een Zendure SolarFlow 2400 AC met drie AB3000X-modules,
een SolarEdge-omvormer, Solcast-voorspelling en een Zonneplan-contract
met kwartierprijzen. Andere combinaties zijn mogelijk maar niet getest.

---

## Kenmerken

### Aansturing

| | |
|---|---|
| **Dynamische prijsdrempel** | Geen vast aantal dure uren, maar een drempel die meebeweegt met de prijsspreiding van die dag — met een vangnet tegen één extreme uitschieter |
| **Prijsprioriteit** | De duurste kwartieren gaan eerst, niet chronologisch |
| **Nachtreserve** | Berekend op het *diepste* tekort onderweg, niet op het eindsaldo |
| **Zonopvang uitstellen** | Laadt later op de dag als de ochtendzon meer opbrengt op het net dan de middagzon |
| **Winter-guard** | Verkoopt niet op een dag waarop er van het net is geladen |
| **Huishoudverbruik-vloer** | Ontlaadt nooit minder dan het huis vraagt tijdens een duur kwartier |
| **Accukoeling** | Stuurt een ventilator aan op accutemperatuur, met hysterese |

### Zelflerend

| | |
|---|---|
| **Verbruiksprofiel** | Per uur van de week, met live correctie die uitdooft over de horizon |
| **Accurendement** | Per halve slag gemeten: laden en ontladen apart |
| **Zonvoorspelling** | Leert de afwijking van je voorspeller per uur |
| **PV-installatieprofiel** | Leidt oriëntatie en hellingshoek af uit heldere dagen |
| **Apparaatherkenning (NILM)** | Herkent apparaten aan hun verbruikspatroon en meldt afwijkingen |
| **Aanwezigheid** | Thuis, weg of slapend — uit bewegingssensoren, tv en verlichting |
| **Waterverbruik** | Herkent waar het water heen ging, met correctiemogelijkheid |

### Bewaking

| | |
|---|---|
| **Zonstandcontrole** | Rekent de zonnestand na uit tijd en plaats en vergelijkt met de sensor |
| **Ingangscontrole** | Meldt een sensor die bestaat maar het benodigde attribuut niet levert |
| **Terugval-duur** | Meldt hoe lang een noodloop al draait |
| **Plantoetsing** | Vergelijkt dagelijks wat het plan beloofde met wat het werd |
| **Proefstand** | Vijf kandidaten die meerekenen maar niets sturen, met wat ze zouden opleveren |
| **Meetkwaliteit** | Per grootheid: gemeten, geschat, of nog onvoldoende data |

---

## Vereisten

### Verplicht

Een **prijssensor** met een `forecast`-attribuut: een lijst met per entry
een tijdstip en een prijsveld. Getest tegen de
[Zonneplan ONE-integratie](https://github.com/fsaris/home-assistant-zonneplan-one),
die zowel `price_tax_included` als `price_tax_excluded` per kwartier
levert.

> **Andere leverancier?** Nordpool, ENTSO-e en EnergyZero leveren vaak
> uurprijzen en andere attribuutnamen. De intervallengte wordt
> automatisch afgeleid, maar de naam van het prijsveld moet kloppen met
> wat jouw sensor levert — controleer dat via **Ontwikkelaarshulpmiddelen
> → Staten**.

Daarnaast een `select`-entiteit voor de accumodus en een
`number`-entiteit voor het handmatige vermogen.

### Optioneel

Alle overige sensoren zijn optioneel en schakelen elk iets bij. Zonder
zonvoorspelling werkt de prijsaansturing gewoon; zonder
capaciteitssensor vervalt alleen de capaciteitsbewuste telling. De
integratie meldt zelf welke functies nog niet beschikbaar zijn en wat
daarvoor nodig is.

---

## Installatie

### Via HACS (aanbevolen)

1. HACS → drie puntjes rechtsboven → **Custom repositories**
2. URL: `https://github.com/Roedie84/Energy-Management-System`,
   categorie **Integration**
3. Zoek **Energy Management System** en installeer
4. Herstart Home Assistant
5. **Instellingen → Apparaten & Services → Integratie toevoegen** →
   *Energy Management System*

### Handmatig

Kopieer `custom_components/energy_management_system/` naar je
`config/custom_components/`-map en herstart Home Assistant.

### Dashboard koppelen

Bij het opstarten wordt `energy_management_system_dashboard.yaml` naar je
configuratiemap gekopieerd. Koppel dat bestand in `configuration.yaml`:

```yaml
lovelace:
  dashboards:
    ems-dashboard:
      mode: yaml
      filename: energy_management_system_dashboard.yaml
      title: Energy Management System
      icon: mdi:home-battery
      show_in_sidebar: true
```

Het dashboard gebruikt
[Mushroom Cards](https://github.com/piitaya/lovelace-mushroom).

---

## Configuratie

Alles wordt ingesteld via de gebruikersinterface — geen YAML nodig.

### Verplicht

| Veld | Betekenis |
|---|---|
| `price_sensor_entity` | Prijssensor met `forecast`-attribuut |
| `price_attribute` | Welk prijsveld binnen elke entry (incl. of excl. belasting) |
| `operation_select_entity` | De `select` die de accumodus zet |
| `manual_power_number_entity` | De `number` voor het handmatige vermogen (positief = ontladen) |

### Vermogens en drempels

| Veld | Standaard | Betekenis |
|---|---|---|
| `manual_discharge_power` | 1600 W | Basisvermogen tijdens een duur kwartier |
| `manual_charge_power` | −2000 W | Vermogen bij netladen |
| `negative_price_charge_power` | −2000 W | Vermogen bij een negatieve prijs |
| `min_soc_percent` | 15% | Ondergrens waaronder niet meer geforceerd wordt ontladen |
| `battery_round_trip_efficiency_percent` | 90% | Terugval tot er genoeg metingen zijn |
| `low_solar_threshold_kwh` | 5,0 kWh | Terugval-drempel voor "weinig zon" |
| `salderen_end_date` | 2026-12-31 | Wanneer de salderingsregeling vervalt |

### Sensoren voor extra nauwkeurigheid

| Veld | Schakelt bij |
|---|---|
| `available_energy_sensor_entity` | Dynamische reserve, uitstelbeslissing op energie |
| `battery_soc_sensor_entity` | SoC-taper op het ontlaadvermogen, noodladen |
| `consumption_power_sensor_entity` | Live verbruikscorrectie, grootverbruikerdetectie |
| `battery_power_sensor_entity` | Correctie van de P1-meting, rendement leren |
| `pv_power_sensor_entity` | Correctie van de P1-meting, exporttoewijzing |
| `solar_today_forecast_sensor_entity` | Zonvoorspelling per half uur (Solcast) |
| `sun_azimuth_sensor_entity` / `sun_elevation_sensor_entity` | Installatieprofiel, beschaduwing, zonstandcontrole |
| `battery_total_capacity_sensor_entity` | Capaciteitsbewuste telling, slijtagekosten |
| `battery_temperature_sensor_entity` + `battery_cooling_fan_switch_entity` | Accukoeling |
| `dishwasher_start_in_entity` / `washing_machine_end_at_entity` | Gepland witgoedverbruik in de reserve |

De volledige lijst staat in de configuratiestroom zelf, met uitleg per
veld.

---

## Dashboard

Vierentwintig pagina's: een landingspagina met drie kolommen, en
subpagina's per onderwerp.

| Pagina | Inhoud |
|---|---|
| **Overzicht** | Status, live cijfers, modus, besturing, "waarom doe je dit nu" |
| **Planning** | Kwartierplanning, komend schema, uitstelplan, plantoetsing |
| **Kosten** | Vandaag/week/maand, prijstoets, vergelijking met de leverancier |
| **Besparing** | Opbrengst, CO₂, cycli, zelfvoorziening |
| **PV / zon** | Opwek, installatieprofiel, voorspelkwaliteit |
| **Accu** | Celspreiding, temperatuur, uitbreidingsadvies |
| **Rendement** | Laden en ontladen apart, verouderingsdrijvers |
| **Aanwezigheid** | Wie er thuis is, met tijdlijn en dagtotalen |
| **Meetkwaliteit** | Betrouwbaarheid per grootheid, wat nog niet bepaald is |
| **Proefstand** | Kandidaten die meerekenen maar niets sturen |
| **Visueel** | Plattegrond met energiestromen |

---

## Hoe de beslislogica werkt

Elke vijf minuten wordt deze boom van boven naar beneden doorlopen; de
eerste regel die van toepassing is bepaalt de actie:

```
Force manual aan?                        → niets doen, jij hebt controle
Negatieve prijs?                         → hard laden, panelen afregelen
Dit kwartier duur genoeg?
  ├─ prijsprioriteit staat het toe?      → ontladen op manual
  ├─ accu kritiek laag en weinig zon?    → noodladen
  └─ anders                              → smart (accu beschermen)
Weinig zon en nu het goedkoopste blok?   → netladen
Accu kritiek laag en weinig zon?         → noodladen
Vóór het goedkoopste blok, genoeg over?  → smart_discharging
Anders                                   → smart
```

### De prijsdrempel

Geen vast aantal kwartieren maar een drempel die meebeweegt: standaard de
bovenste 20% van de prijsspreiding van die dag, bij weinig verwachte zon
verscherpt naar 8%. Daarnaast een ruimere tweede laag (45%) die alleen
wordt gebruikt als er ná reservering voor de echte piek nog capaciteit
over is.

**Vangnet tegen uitschieters:** één extreme piek rekt de spreiding op en
tilt de drempel mee omhoog. Is de hoogste prijs meer dan tweemaal de
mediaan, dan geldt ook een mediaanmaat en wint de ruimste van de twee.

### De nachtreserve

Berekend op het **diepste tekort onderweg** — meestal net voor
zonsopkomst — en niet op het eindsaldo. Een grote verwachte zondag zou
anders een reëel tekort ervóór verbergen.

De marge daarop is zelfcorrigerend: elke dag waarop de accu onverwacht
leeg raakte verhoogt hem, elke dag met structureel overschot verlaagt hem.

### Vermogensbegrenzing

Het ontlaadvermogen wordt per tick geschaald op de resterende reserve,
maar zakt nooit onder het actuele huisverbruik — anders koop je tijdens
een duur kwartier alsnog stroom in tegen piekprijs.

---

## Zelflerend gedrag

| Wat | Hoe |
|---|---|
| **Verbruik per uur** | Mediaan over de laatste veertien waarnemingen per uur |
| **Nachtverbruik** | Apart geleerd, want dat bepaalt de reserve |
| **Accurendement** | Per halve slag: laden en ontladen apart, alleen stukken van minimaal 1,5 kWh |
| **Zonafwijking** | Per uur, want een bias verschilt sterk over de dag |
| **Bedtijd** | Uit de slaapsensor, voor de nachtherkenning |
| **Apparaatverbruik** | Per herkend apparaat, met CUSUM-afwijkingsdetectie |

Alle geleerde waarden overleven een herstart. Waar er nog te weinig
metingen zijn wordt dat expliciet gemeld, in plaats van een geraden getal
te tonen.

---

## Meldingen

Ruim twintig soorten, elk apart aan of uit te zetten met een eigen
dempingsvenster. **Alleen de zes oorspronkelijke staan standaard aan** —
twintig meldingen die zichzelf aanzetten is een garantie dat je er binnen
een week niets meer van leest.

Meldingen kunnen in het **Achterhoeks** worden verstuurd, gespeld volgens
de WALD-richtlijn van het Staring Instituut.

Een uitgezette melding wordt nog wél in de geschiedenis vastgelegd —
uitzetten is niet hetzelfde als weggooien.

---

## Diensten

| Dienst | Waarvoor |
|---|---|
| `confirm_nilm_device` | Een herkend apparaat bevestigen |
| `reject_nilm_device` | Een kandidaat afwijzen |
| `unconfirm_nilm_device` | Een bevestiging terugdraaien |
| `confirm_nilm_duplicate_pair` | Twee sensoren als hetzelfde apparaat markeren |
| `dismiss_nilm_duplicate_pair` | Een duplicaatsuggestie wegklikken |
| `accept_nilm_device_drift` | Een hoger verbruik als nieuw normaal ijken |
| `confirm_water_source` | Corrigeren waar een waterverbruik heen ging |

---

## Diagnostiek en probleemoplossing

Bij problemen: **Instellingen → Apparaten & Services → Energy Management
System → drie puntjes → Diagnostiek downloaden**. Dat bestand bevat de
volledige toestand, inclusief waarom elke beslissing is genomen.

Twee dashboardpagina's zijn specifiek daarvoor bedoeld:

- **Meetkwaliteit** — wat is gemeten, wat is geschat, wat ontbreekt nog.
  De lijst *"nog niet bepaald"* is gesplitst in **wachten op
  waarnemingen** (er is niets mis) en **vraagt een handeling** (er
  ontbreekt een sensor of instelling).
- **Proefstand** — wat een nieuwe rekenregel zou hebben opgeleverd,
  voordat hij iets mag sturen.

### Veelvoorkomend

<details>
<summary><strong>De integratie doet niets</strong></summary>

Controleer of `Learning only` uitstaat. In die stand rekent alles door
maar wordt de accu niet aangestuurd — bedoeld om eerst te kijken of de
beslissingen kloppen voordat je ze laat uitvoeren.
</details>

<details>
<summary><strong>Een waarde blijft op "nog niet bepaald" staan</strong></summary>

Kijk op de Meetkwaliteit-pagina in welke stapel hij staat. *Wachten*
betekent dat er nog te weinig metingen zijn — sommige leerroutines
hebben weken nodig. *Doen* betekent dat er iets ontbreekt, met erbij wát.
</details>

<details>
<summary><strong>De prijzen kloppen niet</strong></summary>

Op de Kosten-pagina staat een toets die de gemiddelde afnameprijs van je
leverancier vergelijkt met de eigen kwartierprijzen. Valt die buiten het
bereik, dan wordt er een ander prijsveld gelezen dan waarvoor je betaalt.
</details>

<details>
<summary><strong>Het dashboard verandert niet na een update</strong></summary>

Het bestand wordt bij elke start opnieuw gekopieerd, maar Home Assistant
leest het alleen als je dashboard in YAML-modus staat. Controleer de
versie onderaan het bestand en ververs de browser hard (Ctrl+F5).
</details>

<details>
<summary><strong>De accu doet iets onverwachts</strong></summary>

Op de landingspagina staat *"Waarom doe je dit nu?"* met de getallen die
de beslissing daadwerkelijk namen — prijs, drempel, accustand, reserve.
Die tekst wordt opgebouwd uit de gebruikte waarden en kan dus niet iets
anders zeggen dan wat er gebeurde.
</details>

---

## Ontwikkeling

```bash
python -m venv .venv && .venv/bin/pip install pytest homeassistant
.venv/bin/python -m pytest
```

**2496 tests**, allemaal groen. De testsuite is niet alleen dekking maar
ook documentatie: elke test legt vast *welke waarneming* aanleiding gaf
tot een regel. Een falende test vertelt daardoor niet alleen dát er iets
stuk is, maar waarom die regel er ooit kwam.

Structurele bewaking die permanent meeloopt:

- elk veld dat toestand opbouwt moet bewaard zijn, door een sensor
  teruggezet worden, of expliciet als vluchtig benoemd zijn **met reden**
- elke coordinator-methode die een entiteit aanroept moet bestaan
- geen `datetime.now()`, `utcnow()` of `date.today()` — alleen de
  tijdzone van Home Assistant
- geen dubbele doelen of onbereikbare pagina's in het dashboard
- geen enkele pagina langer dan de leesbaarheidsgrens

Zie [`CHANGELOG.md`](CHANGELOG.md) voor alle wijzigingen en
[`docs/ONTWIKKELING.md`](docs/ONTWIKKELING.md) voor de achtergrond per
beslissing — waarom een regel er kwam, welke waarneming eraan voorafging
en welke aannames onderweg fout bleken.

---

## Licentie en aansprakelijkheid

MIT — zie [`LICENSE`](LICENSE).

> **Let op.** Deze integratie stuurt een thuisaccu aan met vermogens tot
> 2000 W. Ze is gebouwd voor en getest op één specifieke opstelling.
> Controleer de beslissingen zelf voordat je erop vertrouwt, en gebruik
> de stand `Learning only` om eerst mee te kijken zonder dat er iets
> geschakeld wordt.
>
> Dit project is niet verbonden aan Zendure, Zonneplan, SolarEdge of
> Solcast.
