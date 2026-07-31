# Energy Management System

Home Assistant custom integration die de Zendure batterij automatisch aanstuurt op
basis van dynamische energieprijzen — zonder dat je zelf losse hulp-sensoren
("duurste kwartier", "goedkoopste blok") hoeft te bouwen. Je wijst één
prijssensor aan (bv. de Zonneplan elektriciteitstarief-sensor) en de integratie
berekent zelf:

- of het huidige kwartier een van de duurste kwartieren van vandaag is,
- wanneer het goedkoopste aaneengesloten blok van N uur begint (upcoming),
- en stuurt op basis daarvan de Zendure operation mode (`smart`,
  `smart_discharging`, `manual`) aan.

Dit vervangt de originele YAML-automation door een eigen control-loop
(`coordinator.py`) die elke 15 minuten en bij elke wijziging van de prijssensor
opnieuw beslist.

## Vereisten

Een sensor met een `forecast`-attribuut: een lijst van entries met
`datetime` + een prijsveld. Standaard getest tegen de
[Zonneplan ONE integratie](https://github.com/fsaris/home-assistant-zonneplan-one)
(`sensor.zonneplan_current_electricity_tariff`), die zowel
`electricity_price` (incl. belasting) als `electricity_price_excl_tax`
levert per kwartier.

> Gebruik je een andere leverancier/integratie (Nordpool, ENTSO-e,
> EnergyZero)? Die leveren vaak uurprijzen i.p.v. kwartierprijzen en/of
> andere attribuutnamen in hun `forecast`-lijst. De integratie leidt de
> interval-lengte automatisch af uit de data, maar de prijs-attribuutnaam
> (`price_attribute` in de config) moet dan wel overeenkomen met wat jouw
> sensor daadwerkelijk levert — check dit via **Ontwikkelaarshulpmiddelen →
> Staten** op je prijssensor.

## Entities die de integratie aanmaakt

| Entity | Vervangt | Doel |
|---|---|---|
| `switch.<naam>_force_manual` | `input_boolean.accu_laden_forceer_manual` | Zet aan om de control-loop volledig te negeren |
| `number.<naam>_preload_offset` | `input_number.zendure_preload_offset_uur` | Uren offset t.o.v. start van het goedkoopste blok |

## Installatie via HACS (custom repository)

1. HACS → drie puntjes rechtsboven → **Custom repositories**.
2. URL: `https://github.com/Roedie84/Energy-Management-System`, categorie **Integration**.
3. Installeer, herstart Home Assistant.
4. **Instellingen → Apparaten & Diensten → Integratie toevoegen → Energy Management System**.
5. Vul in:
   - **Dynamische prijssensor** — bv. `sensor.zonneplan_current_electricity_tariff`
   - **Te gebruiken prijs** — incl. of excl. belasting
   - **Zendure operation select entity** — bv. `select.zendure_manager_operation`
   - **Zendure manual power number entity** — bv. `number.zendure_manager_manual_power`
   - **Ontlaadvermogen tijdens duurste kwartier (W)** — standaard 1600
   - **Aantal duurste kwartieren per dag** — standaard 4 (= 1 uur)
   - **Lengte goedkoopste blok (uren)** — standaard 4

Alle velden zijn later aan te passen via de **Configureren**-knop op de integratie (options flow).

## Logica (kort)

```
force_manual actief?            -> niets doen, gebruiker heeft controle
huidig kwartier bij de N duurste van vandaag?  -> manual + ingesteld ontlaadvermogen
nu < (start goedkoopste blok + preload-offset)? -> smart_discharging
anders                                          -> smart
```

Het goedkoopste blok wordt gezocht over alle beschikbare (aaneengesloten)
forecast-kwartieren vanaf nu — dus niet gebonden aan "vandaag", waardoor
het ook correct werkt rond middernacht.

## Ontwikkelen / lokaal testen

Kopieer `custom_components/energy_management_system` naar de `custom_components`
map van je Home Assistant config, of symlink de map tijdens ontwikkeling.

```bash
ln -s $(pwd)/custom_components/energy_management_system /path/to/homeassistant/config/custom_components/energy_management_system
```

## Bekende beperkingen / ideeën voor later

- Geen State-of-Charge check: de accu kan nu tot een negatief punt ontladen als de
  Zendure zelf geen ondergrens afdwingt.
- Geen hysterese: bij snel wisselende prijzen kan de mode elke 15 minuten omslaan.
- Zonneplan levert de "tomorrow"-forecast vaak pas 's middags — tot die tijd
  zoekt de integratie het goedkoopste blok alleen binnen de al bekende data.
- `iot_class: local_polling` — pas aan naar `local_push` als je alles alleen op
  state-events wil laten draaien zonder de 15-minuten timer.

## Zelflerend gedrag (v0.7.0+)

De integratie leert zichzelf twee dingen bij, puur op basis van eigen waarnemingen:

1. **Nachtverbruik** — tijdens elk ontlaadvenster (van `discharge_start_hour` tot
   het goedkoopste blok) wordt het huishoudverbruik (P1-vermogen) bemonsterd en
   geïntegreerd tot een energiewaarde. Na afloop van elke nacht wordt dat
   toegevoegd aan een rollend gemiddelde over de laatste 7 nachten
   (`sensor.learned_night_consumption`). Dit gemiddelde vervangt de live
   momentopname bij het berekenen van het aantal benodigde dure kwartieren
   bij weinig verwachte zon.
2. **Solcast-voorspellingsbias** — de dagelijkse vergelijking tussen voorspelde
   en werkelijke PV-opbrengst (zie hierboven) wordt nu ook bijgehouden over de
   laatste 7 dagen. Het gemiddelde afwijkingspercentage corrigeert automatisch
   de ruwe Solcast-voorspelling voordat die tegen de "weinig zon"-drempel wordt
   gelegd.

Beide leerprocessen bouwen historie op via `RestoreEntity`, dus een
Home Assistant-herstart kost geen geleerde data (al gaat een eventueel actief
ontlaadvenster op het moment van herstart wel verloren voor die ene nacht).

## Learning-only modus (geen aansturing)

Zet `switch.learning_only_no_control` aan om de integratie te laten
doorrekenen en leren, zonder ooit commando's naar de Zendure-entities te
sturen. Handig om het gedrag een paar dagen te observeren voordat je het
vertrouwt met de daadwerkelijke besturing. Wat de integratie *zou* hebben
gedaan, staat in `sensor.simulated_action`.

## Debug/diagnose-entities

Naast de bestaande besturingsentities voegt de integratie een set
diagnostische sensoren toe (zichtbaar onder "Diagnostiek" bij het apparaat):

- `sensor.cheapest_block_start` — start van het laatst berekende goedkoopste blok
- `sensor.discharge_window_start` — start van het ontlaadvenster vannacht
- `sensor.effective_expensive_quarters` — het daadwerkelijk gebruikte aantal
  dure kwartieren (kan lager zijn dan de configuratie bij weinig zon)
- `sensor.last_decision_reason` — waarom de laatste modus is gekozen
- `sensor.simulated_action` — wat er zou zijn gedaan (alleen relevant bij
  learning-only)
- `sensor.learned_night_consumption` — het geleerde gemiddelde nachtverbruik
- `sensor.pv_forecast_accuracy` — afwijking Solcast vs. werkelijke opbrengst,
  inclusief geleerde bias

Een kant-en-klare Lovelace-kaart om deze te tonen staat in
`dashboards/energy_management_system_debug_card.yaml` — pas de entity_id's aan als jouw
installatie een andere naamgeving gebruikt.

## Overzicht komende uren (v0.8.0+)

`sensor.upcoming_schedule` bevat een projectie van wat de integratie
verwacht te gaan doen, over alle beschikbare prijsdata (meestal ~24-36 uur
vooruit, afhankelijk van wat je prijssensor levert):

- **`timeline`**-attribuut: elk kwartier apart (tijd, prijs, modus, of het
  een duur kwartier is).
- **`transitions`**-attribuut: dezelfde data samengevoegd tot blokken per
  modus (bv. "01:00-09:00 → smart_discharging") — veel overzichtelijker
  voor een dashboard.

**Belangrijke beperking:** dit is een projectie, geen garantie. Het
goedkoopste blok en het ontlaadvenster worden herberekend op basis van de
op dit moment bekende forecast; de échte coordinator herberekent dit continu
bij elke update. Voor de huidige dag klopt dit vrijwel altijd, voor de dag
erna kan het iets verschuiven zodra er nieuwe prijsdata binnenkomt (bv.
zodra Zonneplan de forecast voor morgen bijwerkt).

Het "aantal duurste kwartieren" voor toekomstige dagen (buiten vandaag)
gebruikt het normale geconfigureerde aantal, niet de zon-gereduceerde
waarde — die reductie is namelijk specifiek voor het overbruggen van
vannacht.

## Volledig dynamisch (v0.9.0+)

Drie voorheen vaste instellingen zijn nu volledig data-gedreven:

1. **Start ontlaadvenster** — niet langer een vast klokuur
   (`discharge_start_hour` is verwijderd), maar automatisch: het venster
   begint zodra het laatste dure kwartier van vandaag eindigt, en loopt tot
   het goedkoopste blok begint.
2. **Breedte goedkoopste blok** — niet langer een vaste blokduur
   (`cheap_block_hours` is verwijderd uit de configuratie), maar
   automatisch gedetecteerd: de integratie zoekt de natuurlijke breedte van
   het prijsdal rond het goedkoopste moment (drempel = 20% van de
   dagelijkse prijsrange boven het minimum). Een brede vallei van 4 uur
   wordt dus ook als 4 uur herkend; een scherpe dip van 15 minuten blijft
   15 minuten.
3. **"Weinig zon"-drempel** — wordt zodra er minimaal 3 dagen geschiedenis
   is, geleerd als 40% van je eigen typische Solcast-voorspelling, in
   plaats van een vast getal. De geconfigureerde `low_solar_threshold_kwh`
   blijft alleen gelden als fallback tijdens de eerste dagen (cold start).

**Gevolg voor bestaande installaties:** de `number.discharge_start_hour`-
entity is verwijderd en het `cheap_block_hours`-configuratieveld bestaat
niet meer. Na het updaten hoef je niets opnieuw in te stellen — de
integratie werkt vanaf nu volledig automatisch op basis van de prijsdata en
opgebouwde leergeschiedenis.

## Live monitoring dashboard (v0.9.1+)

`sensor.expected_operation_mode` toont altijd wat de prijs/zon-logica puur
zou kiezen (`smart`, `smart_discharging`, `manual`) — onafhankelijk van
`force_manual` of `learning_only`. Zet deze naast de daadwerkelijke Zendure
`select.zendure_manager_operation`-entity in een history-graph om in één
oogopslag te zien wanneer en waarom de realiteit van het plan afwijkt.

De dashboard-kaart (`dashboards/energy_management_system_debug_card.yaml`) bevat nu ook:
- Een "Nu"-overzicht met accu-SoC, beschikbare kWh, verwachte vs.
  werkelijke modus, en huidig verbruik.
- Een grafiek die verwachte vs. werkelijke modus over de laatste 48 uur
  toont.
- Een grafiek met SoC, beschikbare kWh en verbruik over de laatste 48 uur.

## Energie-gebaseerde laadbeslissing (v0.10.0+)

In plaats van charging uit te stellen op basis van een vast tijdstip
("na het duurste kwartier"), gebruikt de integratie nu — als je
`available_energy_sensor_entity` hebt ingesteld (bv.
`sensor.solarflow_2400_ac_available_kwh`) — een energie-gebaseerde check:

```
benodigde energie = (geleerd of live verbruik) × resterende uren tot
                     het goedkoopste blok × 1.15 (veiligheidsmarge)

genoeg beschikbaar?  -> smart_discharging (laden uitstellen, teruglevering
                        bevoordelen tijdens de huidige, duurdere periode)
te weinig beschikbaar? -> smart (Zendure mag alsnog bijladen)
```

Dit voorkomt dat de accu onnodig vroeg (tegen een hogere prijs) begint met
laden vanuit teruglevering, terwijl er straks tijdens het goedkoopste blok
toch voldoende geladen kan worden. Zonder deze sensor valt de integratie
terug op de oude tijd-gebaseerde regel (uitstellen vanaf het einde van de
dure kwartieren).

Nieuwe diagnostische sensor: `sensor.energy_bridge_check` (staat:
`enough_to_postpone` / `top_up_needed`, met `available_kwh` en `needed_kwh`
als attributen).

## Overgangs-logboek energie-check (v0.10.1+)

`sensor.energy_bridge_check` heeft nu ook een `transition_log`-attribuut:
telkens als de beslissing wisselt (van "genoeg energie" naar "moet
bijladen" of andersom), wordt het exacte tijdstip + de `available_kwh`/
`needed_kwh` op dat moment vastgelegd (laatste 50 overgangen, persistent
over herstarts). Zo kun je achteraf controleren of de omschakeling op een
logisch moment gebeurde, zonder dat je continu moet meekijken.

## v0.11.0 — winter-laden, SoC-bescherming, prijsweergave-fix, historische bootstrap

**1. Actief bijladen tijdens het goedkoopste blok bij weinig zon (winter)**
Als er weinig zon wordt verwacht (dezelfde dynamische drempel als bij de
kwartier-reductie), zet de integratie tijdens het goedkoopste blok zelf de
Zendure actief op `manual` met het geconfigureerde laadvermogen (standaard
-2000W), in plaats van te vertrouwen op de "smart"-modus die mogelijk niet
proactief vanaf het net bijlaadt. Zodra er wél voldoende zon wordt
verwacht, blijft "smart" gewoon leidend tijdens het goedkoopste blok.

**2. SoC-bescherming tijdens dure kwartieren**
Nieuw veld: **Accu SoC sensor** + **Minimale SoC (%)** (standaard 15%).
Het ontlaadvermogen tijdens dure kwartieren schaalt lineair af naarmate de
SoC de minimumgrens nadert (volledig vermogen boven grens+15%, geleidelijk
naar 0 tussen grens+15% en de grens, geen geforceerd ontladen meer onder
de grens — dan valt hij terug op `smart`). Zichtbaar via
`sensor.battery_protection`.

**3. Prijsweergave-fix**
De timeline/transitions-attributen van `sensor.upcoming_schedule` tonen nu
`price_per_kwh` (echte €/kWh, bv. `0.3728`) in plaats van de ruwe
Zonneplan-schaalwaarde (`3728480.0`). De dashboard-kaart is bijgewerkt.

**4. Historische bootstrap**
Bij eerste opstart (of na een update, zolang er nog geen live-geleerde
data is) probeert de integratie de leergeschiedenis te vullen vanuit
Home Assistant's eigen recorder-geschiedenis:
- Nachtverbruik: gemiddeld vermogen in een vast 01:00-08:00-venster per
  dag, laatste 7 dagen (benadering — de exacte historische
  ontlaadvensters zijn niet retroactief bekend).
- Solar-voorspelling: voorspelling vs. werkelijke opbrengst per dag,
  laatste 7 dagen, op basis van de sensor-staat rond 23:59:50.

Dit is best-effort en volledig defensief: als de recorder niet
beschikbaar is, te weinig geschiedenis heeft, of er iets misgaat, doet de
integratie gewoon niets extra's en leert hij vanaf nu verder zoals
voorheen. Zichtbaar via `bootstrapped_from_history` op
`sensor.learned_night_consumption` en `sensor.pv_forecast_accuracy`.

> **Let op:** de bootstrap-logica is getest tegen een gesimuleerde
> recorder in een sandbox-omgeving, niet tegen een echte Home
> Assistant-installatie. Controleer na de update in de logs (zoek op
> "Bootstrapped") of het gelukt is, en check de `bootstrapped_from_history`-
> attributen.

## v0.13.0 — correctie huishoudverbruik voor accu-invloed op P1-meter

**Probleem:** je P1-meter meet het netto vermogen op de aansluiting. Als de
accu op dat moment ontlaadt, dekt dat een deel van je huishoudverbruik af
— de P1-meter toont dan een veel lagere waarde dan je werkelijke verbruik.
Omgekeerd toont hij een hogere waarde als de accu laadt.

**Oplossing:** nieuw optioneel veld **Accu vermogen sensor**
(`sensor.zendure_batterij_vermogen`, positief = ontladen, negatief = laden
— zelfde teken-conventie als het handmatige laadvermogen). Zodra
ingevuld, wordt overal waar het huishoudverbruik gebruikt wordt (live
tracking, geleerd nachtverbruik, de energie-brug-check, en de historische
bootstrap) gecorrigeerd:

```
werkelijk verbruik = P1-vermogen + accu-vermogen
```

Getest tegen twee scenario's (ontladen en laden) en tegen de historische
bootstrap — in alle gevallen wordt het werkelijke verbruik nu correct
teruggerekend in plaats van de door de accu vertekende P1-waarde.

Zonder deze sensor blijft de oude (minder nauwkeurige) aanpak gewoon
werken — dit is dus een optionele verbetering, geen verplichte wijziging.

## v0.14.0 — PV-productie meegenomen in verbruikscorrectie

De verbruikscorrectie uit v0.13.0 houdt nu ook rekening met live
PV-productie, niet alleen de accu. Nieuw optioneel veld: **Live
PV-productievermogen sensor** (bv. `sensor.solaredge_i1_ac_power`).

Volledige energiebalans:
```
werkelijk verbruik = P1-vermogen + accu-vermogen + PV-productievermogen
```

Getest tegen twee scenario's (accu laadt deels uit zon met netto import,
en een volledig zelfvoorzienend scenario met alleen export) — in beide
gevallen wordt het werkelijke verbruik nu correct teruggerekend, ook
tijdens de uren dat de zon meespeelt. Zonder deze sensor blijft de
eerdere (P1 + accu) correctie gewoon werken.

De historische bootstrap past dezelfde 3-bron-correctie nu ook toe op
oude data, via een efficiënte tijd-gesynchroniseerde matching tussen alle
drie de sensoren.

## v0.15.0 — volledig 24-uurs verbruiksprofiel (niet meer alleen 's nachts)

De integratie monitorde tot nu toe alleen het verbruik tijdens het
ontlaadvenster (meestal 's nachts). In herfst/winter kan de relevante
"overbrug-periode" tot het goedkoopste blok echter ook overdag vallen,
waar het verbruikspatroon anders is dan 's nachts.

**Nieuw:** de integratie monitort nu **continu, de hele dag door**, en
bouwt een geleerd gemiddelde verbruik per uur-van-de-dag op (0-23u,
rollend gemiddelde over de laatste 7 dagen per uur). Bij het schatten van
de benodigde energie om een periode te overbruggen (voor de
kwartier-reductie én de energie-brug-check), wordt nu het exacte
uur-voor-uur profiel gebruikt in plaats van één vast gemiddelde — dit
werkt correct ongeacht of de periode 's nachts, overdag, of een mix
daarvan overspant.

Getest met een 3-daagse simulatie (ochtendpiek/dagdal/avondpiek/nacht) —
het profiel leert exact het juiste patroon per uur, en de schatting voor
een periode die avond+nacht+ochtend overspant kwam exact uit. De
historische bootstrap bouwt dit profiel nu ook met terugwerkende kracht op
uit alle 24 uur, niet meer alleen het 01:00-08:00-venster.

Nieuwe sensor: `sensor.hourly_consumption_profile` (state = huidig uur,
`profile`-attribuut = alle 24 geleerde waarden). Valt automatisch terug op
het oude gedrag (vast nachtgemiddelde / live meting) zolang het profiel
nog niet voor alle relevante uren gevuld is.

## v0.16.0 — fix absurd hoge Solcast-afwijkingen

**Oorzaak:** de voorspelling voor "morgen" werd vastgelegd op hetzelfde
moment als de vergelijking (23:59:50) — precies het moment waarop sommige
forecast-sensoren "omslaan" (voorspelling voor morgen wordt voorspelling
voor vandaag, en er start een nieuwe/instabiele waarde voor de nieuwe
"morgen"). Dat leverde soms een piepklein/instabiel getal op, wat bij de
deling in de afwijking-berekening tot waarden van 500-700% leidde.

**Fix:**
1. Vastleggen en vergelijken zijn nu twee aparte momenten: de voorspelling
   voor morgen wordt om **20:00** vastgelegd (ruim voor de omslag, als de
   voorspelling allang stabiel is), en pas om 23:59:50 vergeleken met de
   werkelijke opbrengst.
2. Een sanity-filter (`MAX_REASONABLE_DEVIATION_PERCENT = 200%`) negeert
   elke afwijking die toch nog onmogelijk hoog is — zowel bij nieuwe
   metingen als bij de historische bootstrap. Dit geldt ook voor **al
   opgeslagen** corrupte waarden: die worden simpelweg genegeerd bij het
   berekenen van de geleerde bias, en worden vanzelf uit de rollende
   geschiedenis geduwd zodra er nieuwe (nu wel correcte) metingen
   binnenkomen.

Getest tegen exact het scenario uit de praktijk (600%+ afwijkingen) — de
geleerde bias valt correct terug op `None` totdat er weer valide data is,
in plaats van een absurd getal te blijven tonen.

**Geen actie nodig na deze update** — de bestaande foutieve waarden lossen
zichzelf op na verloop van dagen; je hoeft niets handmatig te resetten.

## v0.16.1 — fix 500-fout bij openen van Configureren (options flow)

Op Home Assistant 2025.12+ gaf het openen van **Instellingen → Energy
Management System → Configureren** een 500 Internal Server Error. Oorzaak:
de integratie wees `self.config_entry` handmatig toe in de options-flow
`__init__`, wat sinds HA 2025.12 een `AttributeError` oplevert omdat
`config_entry` daar een automatisch ingevulde, alleen-lezen eigenschap is
geworden (een bekend probleem dat meerdere custom integraties trof, o.a.
LocalTuya). Fix: de handmatige toewijzing is verwijderd — Home Assistant
vult `self.config_entry` nu vanzelf in, volgens de door HA zelf
aanbevolen migratie-aanpak.

## v0.16.2 — fix: uurprofiel-bootstrap werd overgeslagen bij bestaande nachtverbruik-geschiedenis

**Bug:** de historische bootstrap-functie stopte meteen zodra
`night_consumption_history` (de oude, losse nachtvenster-meting) al
gevuld was — óók als het nieuwe 24-uurs `hourly_consumption_profile` nog
volledig leeg was. Voor iedereen die al vóór v0.15.0 had geleerd, werd
het uurprofiel dus nooit met terugwerkende kracht gevuld, en moest het
vanaf nul live opbouwen (uur voor uur, dag na dag).

**Fix:** beide leerprocessen worden nu onafhankelijk van elkaar
gecontroleerd en gebootstrapt. Getest: met een bestaande (niet-lege)
`night_consumption_history` bootstrapt het uurprofiel nu alsnog correct
voor alle 24 uur, zonder de bestaande nachtverbruik-geschiedenis aan te
raken.

**Let op — entity-ID's met apparaat/ruimte-voorvoegsel:** als je apparaat
aan een ruimte is gekoppeld (bv. "Woonkamer"), krijgen entities een
voorvoegsel zoals `sensor.woonkamer_energy_management_system_...`. Check
dit altijd via Ontwikkelaarshulpmiddelen → Staten voordat je de
dashboard-YAML plakt, en pas de entity-ID's zo nodig aan.
