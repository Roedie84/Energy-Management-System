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
`dashboards/energy_management_system_dashboard.yaml` — pas de entity_id's aan als jouw
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

De dashboard-kaart (`dashboards/energy_management_system_dashboard.yaml`) bevat nu ook:
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

## v0.17.0 — fix negatief nachtverbruik (teken-conventie batterijsensor)

**Oorzaak gevonden:** niet elke Zendure/SolarFlow-integratie gebruikt
dezelfde teken-conventie voor het batterijvermogen. Waar de aanname was
"positief = ontladen, negatief = laden" (zoals bij de handmatige
laadvermogen-instelling), bleek jouw `Vermogen`-sensor (Schuur → Zendure
Batterij) het **omgekeerde** te doen: negatief = ontladen. Daardoor werd
tijdens het ontladen juist afgetrokken in plaats van opgeteld, wat de
negatieve verbruikswaarden verklaart die je zag.

**Fix:** nieuwe optie **"Teken omdraaien accu-vermogen"** (aan/uit,
standaard uit). Zet deze aan als jouw batterijsensor negatief laat zien
tijdens ontladen. Getest: met deze optie aan wordt -300W (ontladen bij
jouw sensor) correct als +300W meegeteld in de verbruikscorrectie, i.p.v.
het verkeerd aftrekken van daarvoor.

Geldt voor zowel de live correctie als de historische bootstrap.

## v0.17.1 — verbruikswaarden nu in Watt weergegeven (gebruiksvriendelijker)

`sensor.learned_night_consumption` en `sensor.hourly_consumption_profile`
tonen hun state nu in **W** (bv. `318 W`) in plaats van `kW` (bv.
`0.318`). Intern blijft alles gewoon in kW gerekend (nodig voor de
kWh-berekeningen elders) — alleen de weergave is aangepast, dus dit heeft
geen invloed op de logica of de opgeslagen/herstelde geschiedenis.

Nieuw attribuut `profile_watts` op `sensor.hourly_consumption_profile`
(naast het bestaande `profile` in kW, dat ongewijzigd blijft omdat
daaruit na een HA-herstart wordt hersteld). De dashboard-kaart is
bijgewerkt om deze Watt-attributen te tonen.

## v0.17.2 — fix: komende-uren-tabel kwam niet altijd overeen met live status

**Bug:** `sensor.expected_operation_mode` (live, energie-bewust) en de
huidige rij in `sensor.upcoming_schedule` (een prijs-only projectie)
konden voor hetzelfde moment een andere modus tonen — bijvoorbeeld live
`smart_discharging` terwijl de tabel voor datzelfde kwartier `smart` liet
zien. Dit gebeurde zodra de energie-gebaseerde beslissing (beschikbare
kWh) een ander antwoord gaf dan de tijd-gebaseerde projectie.

**Fix:** het kwartier dat "nu" bevat in de tabel gebruikt voortaan altijd
exact dezelfde live beslissing als de `Expected operation mode`-sensor.
Alleen toekomstige kwartieren blijven een projectie (die kan namelijk
niet weten hoeveel beschikbare energie je over een paar uur hebt).

Getest over 8 verschillende tijdstippen in een scenario waar dit eerder
zou mismatchen — nu overal consistent.

## v0.18.0 — uur-voor-uur PV-forecast (Solcast detailedForecast)

Tot nu toe gebruikte de integratie alleen het **dagtotaal** van de
Solcast-voorspelling. Vanaf nu wordt, indien beschikbaar, ook de
`detailedForecast`/`detailedHourly`-attribuut gebruikt (per half uur/uur
`pv_estimate` in kW) om de **verwachte opbrengst tijdens de specifieke
overbrug-periode** (nu tot het goedkoopste blok) te schatten.

Die verwachte opbrengst wordt afgetrokken van de benodigde energie in:
- de energie-brug-check (`sensor.energy_bridge_check`),
- de reductie van het aantal dure kwartieren bij weinig zon.

**Resultaat:** als er over een paar uur alweer zon verwacht wordt, hoeft
de integratie niet onnodig conservatief te zijn — getest tegen een
scenario met een ochtendpiek: zonder deze feature werd 2,76 kWh als
benodigd berekend, mét de PV-forecast (12 kWh verwacht tijdens het
venster) viel dat terug naar 0 kWh nodig.

Nieuw optioneel veld: **Solcast PV-voorspelling sensor (vandaag)** —
naast de al bestaande "morgen"-sensor, zodat ook de resterende uren van
vandaag worden meegenomen. Zonder deze sensoren (of zonder
`detailedForecast`/`detailedHourly`-attribuut) blijft het oude,
conservatieve gedrag (aanname: geen zon) gewoon intact.

**Let op:** de exacte attribuutstructuur (`detailedForecast` met
`period_start`/`pv_estimate` in kW) is specifiek voor de Solcast PV
Forecast-integratie zoals getest. Andere Solcast-varianten kunnen een
andere structuur hebben — check dit zelf via Ontwikkelaarshulpmiddelen
als de PV-correctie geen effect lijkt te hebben.

## v0.18.1 — geleerde bias-correctie ook toegepast op uur-forecast

De uur-voor-uur PV-schatting (`_estimate_pv_kwh_for_period`, zie v0.18.0)
wordt nu automatisch gecorrigeerd met dezelfde geleerde bias die al werd
gebruikt voor de dagtotaal-check (`sensor.pv_forecast_accuracy` →
`learned_bias_percent`). Voorspelt Solcast bij jou structureel te veel of
te weinig, dan wordt dat verschil nu ook doorgerekend in de uur-schatting
die de energie-brug-check en kwartier-reductie gebruiken.

Getest: bij een geleerde bias van -20% (Solcast voorspelt te optimistisch)
wordt een ruwe schatting van 8,0 kWh teruggerekend naar 6,4 kWh; bij +15%
naar 9,2 kWh. Zonder geleerde bias (bv. tijdens de eerste dagen) blijft de
ruwe Solcast-schatting gewoon staan.

## v0.19.0 — per-uur geleerde PV-voorspelling-bias (preciezer dan één dagbias)

**Nieuw:** in plaats van één vaste dagelijkse bias-correctie op de hele
PV-voorspelling toe te passen, monitort de integratie nu continu (elk
kwartier, de hele dag) de werkelijke PV-productie via je live
PV-vermogensensor, en vergelijkt dat per **uur-van-de-dag** met wat
Solcast voor dat specifieke uur voorspelde. Zo leert hij bijvoorbeeld dat
Solcast bij jouw installatie 's ochtends structureel te optimistisch is
(bv. door een boom die vroeg schaduw geeft) maar 's middags prima klopt —
in plaats van dat verschil te middelen tot één te grove correctie.

Deze per-uur-ratio wordt gebruikt in de uur-voor-uur PV-schatting
(`_estimate_pv_kwh_for_period`), met terugval naar de vlakke dagbias voor
uren waar nog onvoldoende geschiedenis is, en geen correctie als er
helemaal geen geleerde data is.

Nieuwe sensor: `sensor.pv_hourly_forecast_bias` (state = ratio voor het
huidige uur, `profile`-attribuut = alle 24 geleerde ratio's).

**Bijgevangen bug tijdens het bouwen hiervan:** het bestaande
uurverbruiksprofiel (`sensor.hourly_consumption_profile`, sinds v0.15.0)
verloor bij elke uur-overgang het laatste kwartier van het afgelopen uur,
wat leidde tot een structurele onderschatting van ongeveer 25% (getest:
bij een constant vermogen van 500W kwam er voorheen geen 12,0 kWh maar
zo'n 9,0 kWh uit over 24 uur). Dit is gefixt door het interval exact op
de uur-grens te splitsen — geverifieerd met een test die nu wél exact
12,0 kWh over 24 uur teruggeeft.

## v0.19.1 — Diagnostiek-export (om te delen voor optimalisatie)

Home Assistant's ingebouwde **Diagnostics**-functie is nu ondersteund:
ga naar **Instellingen → Apparaten & Diensten → Energy Management System
→ drie puntjes (⋮) → Diagnostiek downloaden**. Dit genereert een
JSON-bestand met:

- de huidige configuratie (welke entities gekoppeld zijn),
- de laatste beslissing + reden, verwachte modus, energie-brug-check,
  SoC-bescherming,
- alle geleerde geschiedenis: nachtverbruik, uurverbruiksprofiel,
  Solcast-bias (dag én per uur), overgangs-logboek van de energie-check,
- of de historische bootstrap is gelukt.

Geen geheimen of tokens erin — alleen entity-ID's en geleerde getallen.
Dit bestand kun je direct met mij delen (bijvoorbeeld hier plakken/
uploaden) zodat ik gericht kan zien wat er speelt, zonder dat we steeds
losse Ontwikkelaarshulpmiddelen-schermpjes hoeven te doorlopen.

## v0.20.0 — leesbare live-uitleg ("wat gebeurt er nu en waarom?")

Nieuwe sensor: **`sensor.explanation`**. In plaats van zelf losse
getallen (SoC, beschikbare kWh, reden-code) te moeten combineren, geeft
deze sensor een volledige Nederlandse zin die uitlegt wat de integratie
nu doet en waarom — bijvoorbeeld:

> "De accu heeft nu 3.20 kWh beschikbaar - genoeg om de resterende tijd
> tot het goedkoopste blok te overbruggen (geschat nodig: 2.10 kWh).
> Daarom wordt laden uitgesteld en krijgt teruglevering nu voorrang
> (smart_discharging)."

Dekt alle 7 mogelijke redenen (inclusief SoC-bescherming, winter-laden bij
weinig zon, en de force_manual/learning_only-overrides), getest tegen 5
scenario's.

**Let op:** Home Assistant beperkt sensor-*states* tot 255 tekens, dus de
`state` van deze sensor wordt afgekapt als het nodig is. De **volledige,
onverkorte tekst staat altijd in het `explanation`-attribuut** — gebruik
die in een markdown-kaart (zoals nu ook in de meegeleverde dashboard-kaart
gebeurt) om altijd de complete uitleg te zien.

## v0.20.1 — één geconsolideerd dashboard-bestand

De twee losse dashboard-YAML's (`_debug_card.yaml` en de aparte
`_gecorrigeerd.yaml`) zijn samengevoegd tot **één bestand**:
`dashboards/energy_management_system_dashboard.yaml`. Dat bevat nu al de
correcte, deels `woonkamer_`-geprefixte entity-ID's voor de sensoren die
zijn aangemaakt nadat het apparaat aan een ruimte werd gekoppeld
(`hourly_consumption_profile`, `pv_hourly_forecast_bias`, `explanation`).

**Als jouw installatie geen ruimte-koppeling heeft** (dus geen
`woonkamer_`-voorvoegsel nodig), verwijder dat voorvoegsel dan zelf uit
deze drie regels — check via Ontwikkelaarshulpmiddelen → Staten wat bij
jou klopt.

## v0.20.2 — sanity-check tegen verkeerde Solcast-sensor + bootstrap-gate-bug

**Gevonden via diagnostiek-export:**

1. **Sanity-check tegen verkeerde/verwisselde Solcast-sensor.** Als
   `solar_forecast_sensor_entity` per ongeluk naar een piekvermogen-sensor
   wijst (of iets anders met een veel te hoge waarde) in plaats van de
   dagtotaal-kWh-voorspelling, werd dat eerder stilzwijgend als "kWh"
   geïnterpreteerd — met absurde bias-percentages tot gevolg (500-750%,
   zoals we eerder zagen). Nu wordt elke voorspelling boven 100 kWh/dag
   (`MAX_REASONABLE_DAILY_FORECAST_KWH`) genegeerd, met een duidelijke
   waarschuwing in de logs die naar de configuratie verwijst. Geldt voor
   nieuwe metingen, de historische bootstrap, én de berekening van het
   geleerde typische dagtotaal (bestaande corrupte waarden in de
   geschiedenis worden er nu ook uitgefilterd).

2. **Bootstrap-gate-bug gefixt:** zodra het uurverbruiksprofiel al
   gedeeltelijk gevuld was (bv. slechts 4 van de 24 uur, via live
   leren sinds een update), sloeg de bootstrap de ontbrekende 20 uur
   voorgoed over — de guard keek alleen of de héle verzameling leeg was,
   niet of er nog specifieke uren ontbraken. Getest met exact dit
   scenario: na de fix vult de bootstrap alle 24 uur, zonder de al
   levend-geleerde uren te overschrijven.

Beide problemen zijn gevonden dankzij een gedeelde diagnostiek-export —
precies waar die functie (v0.19.1) voor bedoeld is.

## v0.21.0 — bredere systeemscan in de diagnostiek-export

De diagnostiek-export (v0.19.1) bevat nu ook een **`system_scan`**-sectie:
een gerichte scan van je hele Home Assistant-omgeving op zoek naar
entities die relevant zouden kunnen zijn voor een toekomstige uitbreiding
van dit EMS — niet een blinde dump van alles.

**Wat wordt meegenomen:**
- Alle `climate`- en `humidifier`-entities (airco, warmtepomp, etc.)
- Sensoren met `device_class` power/energy/battery/monetary
- Alles met een herkenbaar sleutelwoord in entity-ID of naam (vaatwasser,
  wasmachine, droger, airco, warmtepomp, boiler, laadpaal, dishwasher,
  washer, dryer, heatpump, ev_charger, wallbox)

**Wat bewust wordt overgeslagen:** lampen, locks, camera's,
aanwezigheidsdetectie, en al het andere dat niets met energiebeheer te
maken heeft.

Elke gevonden entity toont ook `already_used_by_this_integration`, zodat
je in één oogopslag ziet wat er al gekoppeld is en wat nog "vrij" ligt
voor een volgende stap richting een vollediger EMS.

Getest met een gesimuleerde mix van 10 entities — de 5 relevante werden
gevonden, de 5 irrelevante correct genegeerd.

## v0.21.1 — systeemscan uitgebreid met bewoningsdata (beweging, verlichting, lux)

De `system_scan` in de diagnostiek-export neemt nu ook mee:
- **Alle `light`-entities** (verlichting) — voor het correleren van
  gebruikspatronen met bewoning.
- **Bewegings-/aanwezigheidssensoren** (`device_class`: motion,
  occupancy, presence).
- **Lux-/lichtsterkte-sensoren** (`device_class`: illuminance) — handig
  om tegen de Solcast-voorspelling/PV-productie af te zetten, en om
  daglicht-gedreven gebruikspatronen te begrijpen.

Nog steeds bewust buiten beschouwing: locks, camera's, media players, en
al het andere dat niets met energiebeheer of bewoningspatronen te maken
heeft. Getest met een mix van 9 entities — alle 6 relevante gevonden
(inclusief de nieuwe categorieën), de 3 irrelevante correct genegeerd.

## v0.22.0 — financiële tracking (waarde ontladen / kosten netladen)

Twee nieuwe sensoren die de euro-waarde van twee concrete acties bijhouden,
cumulatief en persistent over herstarts heen:

- **`sensor.discharge_value_expensive_quarters`** — de euro-waarde van
  energie die is ontladen tijdens dure kwartieren (energie × prijs op dat
  exacte moment).
- **`sensor.charge_cost_grid_charging`** — de kosten van energie die
  actief vanaf het net is bijgeladen tijdens een goedkoopste blok bij
  weinig zon (winter-laden, v0.18.0).

**Bewuste keuze — dit heet geen "besparing".** Een echte besparing zou een
counterfactual vereisen ("wat was er gebeurd zonder deze integratie?"),
en dat is niet eerlijk te berekenen of te verifiëren. Deze twee getallen
zijn wél hard te onderbouwen: het is simpelweg energie × prijs op het
moment van de actie. Zie het als "de directe monetaire waarde van deze
specifieke acties", niet als een garantie dat je zonder deze integratie
dat bedrag meer kwijt zou zijn geweest.

Getest: een uur durende geforceerde ontlading op 1600W tegen €0,35/kWh
resulteerde in de verwachte cumulatieve waarde (kleine afwijking door het
eenmalige opstart-effect van de tijdmeting, net als bij de andere
leerprocessen in deze integratie).

## v0.22.1 — dag/week/maand-overzicht financiële sensoren

Gebruikt Home Assistant's ingebouwde **Utility Meter**-helper (geen extra
code in de integratie nodig, want beide financiële sensoren zijn al
`state_class: total_increasing`, precies wat Utility Meter nodig heeft).

Nieuw bestand: `dashboards/utility_meter_ems.yaml` — voeg dit toe aan je
`configuration.yaml` (of sluit het in via `utility_meter: !include
dashboards/utility_meter_ems.yaml`), en herstart Home Assistant. Dit maakt
6 nieuwe sensoren: dag/week/maand voor zowel de ontlaadwaarde als de
netlaadkosten.

De dashboard-kaart is bijgewerkt met deze 8 regels (2 totaal-sinds-install
+ 6 periode-sensoren), inclusief een divider tussen de twee categorieën.

**Let op:** de eerste cyclus per meter is altijd incompleet — een
dag-sensor klopt pas vanaf morgen, een maand-sensor pas vanaf de 1e van
volgende maand. Dit is standaard Home Assistant-gedrag, geen bug.

## v0.23.0 — reservering voor nog-komende dure kwartieren in de energie-brug-check

**Gevonden gat (geen leerprobleem, een echte strategische blinde vlek):**
de energie-brug-check rekende alleen uit of er genoeg was om het
**basisverbruik** te overbruggen tot het goedkoopste blok — niet dat er
óók nog een dure kwartier kan volgen waarin je juist actief wilt
ontladen/verkopen. Daardoor kon de accu "genoeg lijken" te hebben voor je
huishouden, terwijl er straks bij het daadwerkelijke prijspiek te weinig
over was om vol vermogen te ontladen (de SoC-bescherming zou het
ontlaadvermogen dan afromen — gemiste winst).

**Fix:** de benodigde energie in de brug-check telt nu ook de energie mee
die nodig is om **alle nog-komende dure kwartieren van vandaag** (vóór
het goedkoopste blok) op volle kracht te kunnen ontladen. Is er
onvoldoende voor zowel basisverbruik als deze geplande ontlading, dan
schakelt de integratie naar `smart` (bijladen toegestaan) in plaats van
`smart_discharging` (laden uitstellen).

Getest: bij een basisverbruik van 50W en 4 dure kwartieren vanavond
(1600W, dus 1,6 kWh) veranderde de beslissing van "genoeg" (1,09 kWh
benodigd) naar "niet genoeg" (2,93 kWh benodigd) bij exact hetzelfde
beschikbare vermogen van 1,8 kWh — precies het scenario waar dit voor
bedoeld is.

## v0.23.1 — opsplitsing zichtbaar in de live-uitleg

`sensor.explanation` toont nu, bij de energie-brug-gerelateerde redenen
(`discharging_window` en `default_smart` met te weinig energie), ook de
**opsplitsing** van het benodigde-energie-getal:

> "Opsplitsing van die 2.93 kWh: 0.95 kWh basisverbruik, minus 0.0 kWh
> verwachte zon, plus 1.6 kWh reservering voor nog-komende dure
> kwartieren vandaag, met 15.0% veiligheidsmarge erover."

Zo kun je zelf verifiëren waar het eindtotaal vandaan komt, in plaats van
alleen het resultaat te zien — vooral handig sinds v0.23.0, waar de
reservering voor dure kwartieren is toegevoegd aan die berekening.

## v0.24.0 — realtime correctie via de aflopende "resterend vandaag"-sensor

Nieuw optioneel veld: **Solcast resterende voorspelling vandaag sensor**
(bv. `sensor.solcast_pv_forecast_resterende_voorspelling_vandaag`) — een
waarde die door Solcast zelf doorlopend wordt bijgesteld op basis van de
daadwerkelijk waargenomen omstandigheden vandaag, en afloopt richting het
einde van de dag.

**Hoe dit wordt gebruikt:** in plaats van deze waarde blind te gebruiken
(wat problemen zou geven bij deelperiodes, want de sensor dekt altijd
"de rest van vandaag" en niet een specifiek tijdvak), berekent de
integratie een **correctie-ratio**: de sensorwaarde gedeeld door onze
eigen som van de resterende dag uit de detailedForecast-data. Die ratio
wordt vervolgens toegepast op elk kwartier/uur-segment van vandaag in de
PV-schatting — ook bij een deelperiode die niet tot middernacht loopt.

Voor het gedeelte van de schatting dat over vandaag heen valt (bv.
morgen), blijft de bestaande per-uur-geleerde of dagelijkse bias-correctie
gewoon van kracht.

Getest tegen drie scenario's: zonder de sensor (ongewijzigd gedrag), met
een lagere resterende-waarde (bv. door bewolking) toegepast op de volledige
resterende periode, én specifiek op een **deelperiode** (de helft van de
resterende uren) — in alle gevallen kwam de schaling exact overeen met de
verwachting.

## v0.25.0 — dynamische ontlaad-reserve + geen laden-uitstel bij actieve zon

**1. Dynamische energie-gebaseerde ontlaad-reserve (i.p.v. vaste SoC%)**

De SoC-bescherming tijdens dure kwartieren gebruikt nu, als je een
beschikbare-energie-sensor hebt ingesteld, een **dynamisch berekende
reserve** in plaats van een vast percentage: "houd minimaal het
geschatte resterende basisverbruik tot het goedkoopste blok aan, plus
10% marge" — precies zoals besproken. Is er meer beschikbaar dan die
reserve, dan wordt er vol vermogen ontladen; is er net iets meer dan de
reserve, dan wordt het vermogen evenredig afgeroomd; is er precies de
reserve (of minder), dan wordt er niet geforceerd ontladen.

Zonder een beschikbare-energie-sensor blijft de oude, vaste SoC%-aanpak
(met `min_soc_percent`) gewoon als terugval werken.

Getest: bij een berekende reserve van 3,08 kWh (2,8 kWh basisverbruik ×
1,10 marge) werd het vermogen exact evenredig afgeroomd naarmate de
beschikbare energie dichter bij die reserve kwam (1600W → 800W bij
precies de helft van de headroom → 0W/geen ontlading bij exact de
reserve).

**2. Geen laden-uitstel meer als er nu actief zon wordt geproduceerd**

`smart_discharging` (laden uitstellen tot het goedkoopste blok) wordt nu
nooit meer geforceerd zolang er op dit moment daadwerkelijk zon wordt
geproduceerd (drempel: 50W, verwaarloosbare ruis daaronder). Zonne-energie
van dit moment is namelijk vergankelijk — niet gebruikt betekent
kwijtgeraakt (geëxporteerd tegen een matige prijs), in tegenstelling tot
duur netladen, dat je wél zinvol kunt uitstellen. In plaats daarvan blijft
de integratie op `smart` zodat de Zendure's eigen logica de beschikbare
zon kan opvangen.

Getest: bij 800W actieve zon bleef de modus `smart` ondanks dat er
normaliter (zonder zon) `smart_discharging` gekozen zou zijn; zonder
actieve zon (0W) werd op exact hetzelfde moment wél `smart_discharging`
gekozen.

## v0.26.0 — meerdaagse zon-vooruitzicht (dag+3, dag+4, ...)

Nieuw optioneel veld: **Solcast dag+3, dag+4, etc. sensoren** — een
meervoudige entity-selector waar je zoveel toekomstige-dag-sensoren kunt
toevoegen als je hebt (bv. `sensor.solcast_pv_forecast_voorspelling_dag_3`,
`_dag_4`, ...), in volgorde.

**Wat dit oplost:** voorheen keek de "weinig zon"-logica alleen naar
morgen. Als er een langere bewolkte periode aankomt (meerdere dagen
achter elkaar weinig zon), moet de integratie voorzichtiger zijn met diep
ontladen vanavond — de accu wordt dan namelijk niet snel weer bijgevuld.

De integratie telt nu het aantal **opeenvolgende** dagen (vanaf morgen)
met weinig verwachte zon, en verhoogt daarmee de dynamische
ontlaad-reserve-marge (v0.25.0): elke extra opeenvolgende lage-zon-dag
voegt 5 procentpunt toe aan de marge (van standaard 10%), tot een maximum
van +20 procentpunt.

Getest: 1 lage-zon-dag → 10% marge (ongewijzigd), 3 opeenvolgende
lage-zon-dagen → marge stijgt naar 25% (10% + 3×5%), en zodra een dag in
de reeks weer voldoende zon toont, stopt de telling daar — precies zoals
bedoeld.

Zonder deze sensoren blijft het gedrag ongewijzigd (alleen morgen wordt
meegewogen, zoals voorheen).

## v0.26.1 — geen kunstmatig plafond meer op de meerdaagse marge

Het vaste maximum van +20 procentpunt (v0.26.0) is verwijderd. De
marge-verhoging schaalt nu puur door met `5 procentpunt × aantal
opeenvolgende lage-zon-dagen`, zonder aparte cap — het "plafond" wordt nu
vanzelf bepaald door hoeveel dag-sensoren je daadwerkelijk hebt
geconfigureerd (bv. met dag 3 t/m 7 kun je tot 6 opeenvolgende dagen
tellen, wat een marge van 10% + 6×5% = 40% oplevert), in plaats van een
los getal dat ik zelf had gekozen.

Getest: 6 opeenvolgende lage-zon-dagen (morgen t/m dag 7) resulteerden in
exact 40% marge op het basisverbruik, zonder af te toppen.

## v0.27.0 — dynamische prijsdrempel, winter-regel, negatieve prijzen

Groot pakket, vier onderdelen:

### 1. Bootstrap-gate-bug in de Solcast-tracker gefixt

Zelfde soort bug als eerder bij het uurverbruiksprofiel: bestaande
(corrupte) `forecast_value_history`/`deviation_history` blokkeerden een
herstart van de bootstrap voorgoed. Nu wordt bestaande data eerst
gefilterd op plausibiliteit; is alles corrupt, dan bootstrapt hij alsnog
vers uit de geschiedenis. Getest: 7 corrupte waarden (2175, 2694, ... kWh)
werden vervangen door echte, correcte historische waarden.

### 2. Dynamische prijsdrempel i.p.v. vaste "4 dure kwartieren"

Er is geen vast aantal kwartieren meer. Een kwartier geldt nu als "duur"
als de prijs binnen de **top 20% van de dagelijkse prijsrange** valt
(versmald naar top 8% bij weinig zon verwacht) — past zich dus aan aan
hoe groot het prijsverschil die dag daadwerkelijk is, in plaats van altijd
precies 4 kwartieren te pakken ongeacht of die eigenlijk wel duur zijn.

De **hoeveelheid** die daadwerkelijk wordt ontladen blijft bepaald door
het al bestaande dynamische-reserve-mechanisme (v0.25.0): "houd genoeg
voor eigen verbruik tot er weer zon is, plus marge" — dat deed al precies
wat gevraagd werd. `sensor.effective_expensive_quarters` toont nu hoeveel
kwartieren vandaag de drempel halen (informatief).

De config-optie `expensive_quarters_count` wordt niet meer gebruikt in de
beslislogica (staat er nog voor eventuele backwards-compatibility, maar
heeft geen effect meer).

### 3. Winter-regel: geen manual-ontladen na grid-laden diezelfde dag

Als de accu vandaag al geforceerd is bijgeladen vanaf het net (winter,
weinig zon), wordt diezelfde dag niet meer geforceerd ontladen bij dure
kwartieren — dat zou gewoon verlies opleveren, geen winst. De vlag reset
automatisch bij een nieuwe dag. Getest: grid-laden 's ochtends blokkeert
het dure-kwartier-ontladen die avond; de volgende dag werkt alles weer
normaal.

### 4. Negatieve-prijs-afhandeling

Nieuw: bij een negatieve energieprijs (hoogste prioriteit, alleen
`force_manual` gaat ervoor):
- De accu laadt actief op het ingestelde vermogen (nieuwe optie
  **"Laadvermogen bij negatieve prijs"**, standaard -2000W).
- De zonnepanelen worden **geleidelijk** (30 seconden, 10 stappen) naar
  0% afgeregeld via de nieuwe optie **"Zonnepaneel-vermogenslimiet
  slider"** (bv. `number.solaredge_i1_active_power_limit`) — niet
  terugleveren tegen een negatieve prijs.
- Zodra de prijs weer positief wordt: panelen geleidelijk terug naar
  100% (ook 30 seconden), en de accu hervat de normale, door de
  integratie bepaalde modus.

De ramp draait als achtergrondtaak (blokkeert de reguliere update-cyclus
niet). Getest: correcte overgang tussen `negative_price` en normale
logica in beide richtingen, inclusief het starten van de ramp-taken.

### Dashboard

Bijgewerkt met de zonnepaneel-vermogenslimiet-sensor en een aangepast
label voor het (nu informatieve) aantal dure kwartieren.

## v0.27.1 — diagnostics.py bijgewerkt met ontbrekende velden

De diagnostiek-export miste een aantal velden die in eerdere versies al
waren toegevoegd aan de code, maar nooit waren doorgevoerd naar
`diagnostics.py`. Nu compleet, inclusief:

- `total_discharge_value_eur` / `total_charge_cost_eur` (financiële
  tracking, v0.22.0 — stond er nog nooit in)
- `last_needed_kwh_breakdown` (opsplitsing van de energie-brug-berekening,
  v0.23.1)
- `last_charge_power_applied`
- `grid_charged_today` (winter-guard-status, v0.27.0)
- `is_negative_price_active` (v0.27.0)

Getest: alle velden komen correct mee en het geheel blijft
JSON-serialiseerbaar.

## v0.28.0 — detectie en zelfcorrectie bij onverwachte netimport

Nieuw: de integratie **detecteert** en **leert** nu van momenten waarop de
dynamische reserve (v0.25.0) achteraf te krap bleek — het antwoord op
"wat als er toch te weinig overblijft om op 0 te blijven?".

**Hoe het werkt:**
- Tijdens elke periode waarin de integratie "zelfvoorzienend" veronderstelt
  (`smart_discharging`, `expensive_quarter`, `expensive_quarter_soc_protected`),
  wordt de rauwe P1/netmeter-waarde gecontroleerd. Onverwachte netimport
  boven 100W betekent: de reserve-schatting voor die dag was te optimistisch.
- Dit wordt per dag bijgehouden (rollend over de laatste 7 dagen, net als
  de andere leerprocessen).
- Elke dag met een gedetecteerde tekortkoming verhoogt de
  ontlaad-reserve-marge met 5 procentpunt, zonder apart plafond (zelfde
  filosofie als de meerdaagse-lage-zon-marge) — de integratie corrigeert
  zichzelf dus automatisch als dit vaker voorkomt.

Nieuwe sensor: **`sensor.reserve_shortfall_days`** — toont het aantal
dagen met een tekortkoming in de laatste week, met de ruwe geschiedenis
als attribuut. De live-uitleg (`sensor.explanation`) vermeldt het ook
expliciet als dit recent is voorgekomen.

**Belangrijk om te weten:** dit is een **reactieve** correctie — de eerste
keer dat de reserve tekortschiet, gebeurt dat gewoon (de integratie kan
niet vooraf weten dat de schatting fout zit). Pas ná detectie wordt de
marge voor toekomstige dagen verhoogd. Dit is dus geen garantie tegen een
eerste keer, maar wel bescherming tegen het herhaaldelijk misgaan.

Getest: detectie bij 150W onverwachte import, correcte dag-rollover naar
de geschiedenis, en de marge-berekening met 3 recente tekortkomingen
(10% → 25%, exact zoals verwacht).

Ook `diagnostics.py` is meteen bijgewerkt met deze nieuwe velden — geleerd
van de vorige keer dat dit werd vergeten.

## v0.28.1 — noodlaad-mechanisme (fix voor lege accu 's nachts)

**Aanleiding:** een gebruiker rapporteerde dat de accu rond 04:00 leeg
raakte terwijl er nog huishoudverbruik nodig was, met ongewenste
netimport tot gevolg. Analyse van diens `energy_bridge_transition_log`
liet zien dat de integratie het al om **middernacht zag aankomen**
(4,84 kWh beschikbaar tegen 9,2 kWh benodigd → "top_up_needed"), maar
niets deed omdat het goedkoopste blok pas om 09:00 begon — buiten dat
blok greep de integratie nooit in, ze wachtte gewoon passief af terwijl
de accu leegliep.

**Kern van het probleem:** de energie-brug-check bepaalt alleen of laden
mag worden **uitgesteld** — bij een tekort viel de integratie terug op
`smart` (Zendure's eigen logica), zonder dat de Zendure wist dat wíj al
een tekort hadden berekend. Onze reserve-bescherming beschermde alleen
tegen onze eigen geforceerde acties, niet tegen normale huishoud-ontlading
buiten het goedkoopste blok.

**Fix — nieuw noodlaad-mechanisme:** als de accu **kritiek laag** staat
(op of onder de ingestelde minimum-SoC, of een kleine kWh-marge zonder
SoC-sensor), begint de integratie **nu al** actief te laden vanaf het net
— ook buiten het goedkoopste blok, ook tijdens een duur kwartier als de
SoC-bescherming daar toch al geen ontlading toestaat. Nieuwe reden:
`emergency_low_battery`, met een duidelijke melding in `sensor.explanation`.

Getest: bij exact het gerapporteerde scenario (SoC 7%, middernacht, ver
van het goedkoopste blok om 09:00) triggert de integratie nu correct
`emergency_low_battery` en laadt actief bij, in plaats van passief
`default_smart` te blijven. Zodra de SoC weer boven het minimum komt,
stopt het noodladen vanzelf.

Ook meegenomen in de winter-guard (`_grid_charged_today`) en de
financiële tracking, zodat noodladen consistent wordt behandeld als elke
andere netlaad-actie.

## v0.29.0 — correctie: het echte probleem was over-ontladen, niet te weinig laden

**Belangrijke correctie op v0.28.1.** De gebruiker die het oorspronkelijke
incident meldde, gaf aan: de accu was **vol** aan het begin van de avond en
dat was ruim voldoende geweest voor de nacht — het probleem was dat er
tijdens het dure kwartier **te veel is teruggeleverd/ontladen**, niet dat
er te weinig was om bij te laden. Het noodlaad-mechanisme van v0.28.1
loste dus het verkeerde probleem op.

**De echte oorzaak:** onze dynamische ontlaad-reserve gebruikte alleen het
**geleerde gemiddelde verbruik per uur** — niet het **live actuele
verbruik**. Als je 's nachts bijvoorbeeld de airco aan hebt, verbruik je
veel meer dan het historische gemiddelde voor dat uur, maar dat zag de
integratie pas terug in het geleerde profiel van morgen — te laat om die
specifieke nacht te beschermen.

**Fix:** de periode-schatting (`_estimate_consumption_kwh_for_period`)
vergelijkt nu het live verbruik met het geleerde gemiddelde voor het
huidige uur. Is het live verbruik hoger (airco, wasmachine, etc.), dan
wordt de **hele resterende schatting evenredig opgeschaald** — minder
headroom om te verkopen, meer reserve voor je eigen verbruik. Getest:
bij 3x hoger live verbruik dan het geleerde gemiddelde steeg de reserve
ook exact 3x (van 1,1 naar 3,3 kWh).

**Het noodlaad-mechanisme (v0.28.1) blijft bestaan, maar nu specifiek
gekoppeld aan de winter-situatie:** het triggert alleen nog als de accu
kritiek laag staat ÉN er weinig zon wordt verwacht (dezelfde detectie als
het winter-netladen-mechanisme, v0.18.0). In de zomer lost de
live-verbruik-correctie het probleem al op (minder ontladen), en vult de
accu zich toch snel weer bij met zon — bijladen is dan niet nodig. Getest:
zelfde kritiek lage SoC (7%) triggert nu geen noodladen bij veel zon
morgen, maar wel bij weinig zon.

## v0.30.0 — tweezijdig zelflerend systeem (niet alleen voorzichtiger, ook scherper)

**Aanleiding:** de vraag "leert het systeem echt op alle fronten?" bracht
een scheefheid aan het licht: de zelfcorrectie van de ontlaad-reserve
(v0.28.0) kon de marge alleen **verhogen** bij een gedetecteerd tekort,
maar nooit **verlagen** als er structureel te veel werd gereserveerd. Op
termijn zou de integratie dus alleen maar voorzichtiger worden, nooit
weer scherper durven verkopen zodra dat verantwoord is.

**Fix — nu tweezijdig:**
- **Tekort-detectie** (ongewijzigd): onverwachte netimport tijdens een
  zelfvoorzienend-veronderstelde periode → marge omhoog.
- **Nieuw: overschot-detectie** — als de beschikbare energie ≥3x hoger
  blijft dan wat daadwerkelijk nodig was, terwijl laden nog steeds werd
  uitgesteld, betekent dat de reserve die dag onnodig conservatief was →
  marge omlaag (3 procentpunt per recente overschot-dag).
- Beide worden verrekend tot één netto-marge, met een ondergrens van
  **-5 procentpunt totale correctie** (nooit minder dan 5% onder de
  basismarge van 10%, dus altijd minimaal 5% marge over blijft).

Nieuwe sensor: **`sensor.reserve_excess_days`** (spiegelbeeld van
`sensor.reserve_shortfall_days`).

Getest: 3 recente overschot-dagen verlaagden de marge naar het
minimum (afgetopt op -5%); een mix van 2 tekorten + 3 overschot-dagen
resulteerde in de correcte netto-marge (+10% - 9% = +1% t.o.v. de basis);
de ondergrens werkte correct bij een extreem overschot-scenario (7 van de
7 dagen).

`diagnostics.py` is meteen meegenomen met de nieuwe velden.

## v0.31.0 — planningstabel houdt nu ook rekening met beschikbare energie

**Aanleiding:** een gebruiker zag `sensor.effective_expensive_quarters` op
**42** staan (10,5 uur!) en de planning toonde een ononderbroken
"manual"-blok van 19:15 tot ver in de volgende dag — met de vrees dat de
accu daardoor al rond het middaguur leeg zou zijn.

**Wat er speelde:** de dynamische prijsdrempel (top 20% van de dagrange)
kan op dagen met een breed "duur plateau" (relatief vlakke prijzen dicht
bij de top) veel meer kwartieren als "duur" classificeren dan
daadwerkelijk zinvol is om te ontladen. De **live beslissing** wordt hier
al tegen beschermd door de dynamische reserve — maar de **planningstabel**
(Overzicht komende uren) hield daar geen rekening mee en toonde dus élk
prijs-kwalificerend kwartier als "manual", ongeacht hoeveel energie er
werkelijk beschikbaar is.

**Fix:** de planning simuleert nu een lopende energiebalans: startend
vanaf de huidige beschikbare kWh, wordt bij elk geprojecteerd
"manual"-kwartier de verwachte ontlading afgetrokken. Zodra de
gesimuleerde balans de (live-verbruik-gecorrigeerde) reserve bereikt,
worden verdere prijs-kwalificerende kwartieren getoond als `smart` in
plaats van `manual` — exact wat de live logica ook zou doen.

Getest: bij een gesimuleerd "duur plateau" van 24+ kwartieren maar slechts
3 kWh beschikbaar, toonde de planning voorheen ~24 manual-kwartieren; na
de fix nog maar **1**, gevolgd door een correcte terugval naar `smart`.

**Resultaat:** wat je in het dashboard ziet, komt nu overeen met wat er
werkelijk gaat gebeuren — geen misleidend lange ontlaadblokken meer die
geen rekening houden met wat je accu daadwerkelijk aankan.

## v0.31.1 — fix: PV-uurbias verloor alle voortgang bij elke herstart

**Gevonden bug:** `sensor.pv_hourly_forecast_bias` bleef na weken nog
steeds volledig leeg (`{}`), terwijl het uurverbruiksprofiel prima vulde.
Oorzaak: het `profile`-attribuut (gebruikt om na een herstart te
herstellen) werd opgebouwd via `learned_pv_hourly_ratio()`, die pas een
waarde teruggeeft zodra een uur **minstens 3 metingen** heeft. Een uur met
1 of 2 metingen werd dus nooit opgeslagen — en ging bij elke Home
Assistant-herstart (waarvan er, met alle updates, behoorlijk wat zijn
geweest) gewoon **verloren**, voordat het ooit de kans kreeg om aan 3
metingen te komen.

**Fix:** nieuwe methode `raw_pv_hourly_avg()` zonder de
minimum-metingen-eis, specifiek voor persistentie. De weergave/besluit­
vorming (`learned_pv_hourly_ratio()`, ongewijzigd) blijft wel pas een
waarde gebruiken bij voldoende vertrouwen — alleen het **opslaan** van
tussentijdse voortgang is losgekoppeld van die eis.

Nieuw attribuut `profile_confident` (het oude gedrag, alleen uren met
genoeg metingen) naast het bestaande `profile` (nu alle uren met minstens
1 meting, voor persistentie).

Getest: een uur met slechts 1 meting werd voorheen nooit opgeslagen (bug
bevestigd), wordt nu wél behouden bij een herstart.

**Voor de duidelijkheid:** dit gold **alleen** voor de PV-uurbias-sensor.
Het uurverbruiksprofiel had deze bug niet (gebruikt een andere,
drempel-vrije methode) en bouwde dus al die tijd al correct op.

## v0.32.0 — volledige audit + zelf-diagnosticerende "learning_health"

**Aanleiding:** terechte feedback dat de PV-uurbias-bug (v0.31.1) eerder
had moeten opvallen uit eerdere diagnostiek-exports, in plaats van pas
na expliciet doorvragen.

**1. Volledige audit uitgevoerd** op hetzelfde patroon (weergave-drempel
die per ongeluk ook persistentie blokkeert): alle 9 persistente sensoren
en beide switches gecontroleerd. Alleen de al gefixte PV-uurbias-sensor
had dit probleem — de rest slaat overal de rauwe data op, los van elke
weergave-drempel.

**2. Nieuwe `learning_health`-sectie in de diagnostiek-export**, die
automatisch signaleert of een leerproces geen voortgang boekt ondanks
voldoende verstreken tijd (bijgehouden via een nieuw `first_seen_date`).
Elke tracker (uurverbruiksprofiel, nachtverbruik, PV-uurbias,
Solcast-nauwkeurigheid) krijgt een `OK`/`SUSPICIOUS`-vlag met een
concrete verklaring, inclusief expliciete verwijzing naar bekende eerdere
bugs als mogelijke oorzaak.

Getest: exact het gerapporteerde scenario (12 dagen geïnstalleerd, 0 uur
PV-uurbias-data) werd meteen correct als `SUSPICIOUS` gemarkeerd, met een
directe verwijzing naar de v0.31.1-bug.

**Ook toegevoegd:** `pv_hourly_bias_profile_raw` (alle uren met
minstens 1 meting) naast de bestaande `_confident`-versie, zodat
gedeeltelijke voortgang ook in de hoofd-diagnostiek zichtbaar is, niet
alleen in de nieuwe health-sectie.

Dit is bedoeld om dit soort problemen voortaan **direct uit een enkele
diagnostiek-export** te kunnen signaleren, zonder dat daar eerst
expliciet naar gevraagd hoeft te worden.
