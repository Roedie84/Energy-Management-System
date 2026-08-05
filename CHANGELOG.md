# Changelog — Energy Management System

Volledige, chronologische ontwikkelgeschiedenis van deze integratie. Voor
een beschrijving van hoe de integratie *nu* werkt, zie README.md — dit
bestand is puur historisch archief.

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

## v0.33.0 — accu-rendement meegenomen in de PV-aftrek

Nieuw optioneel veld: **Accu-rendement (%)** (standaard 90%, pas aan naar
jouw eigen ~80%).

**Waar dit wél toe doet:** de verwachte zon-opbrengst wordt afgetrokken
van wat je nog aan reserve nodig hebt (zowel in de dynamische
ontlaad-reserve als de energie-brug-check). Als die zon eerst de accu
inlaadt voordat je het weer gebruikt, gaat een deel verloren via het
rendement — we waren dus iets te optimistisch over hoeveel die
verwachte zon je reserve daadwerkelijk verlicht. De aftrek wordt nu
vermenigvuldigd met het geconfigureerde rendement, een bewust
conservatieve aanpak (we kunnen niet exact scheiden welke zon direct je
huishouden voedt vs. via de accu gaat, dus we passen het rendement toe op
de hele aftrek — dat onderschat het effect van zon eerder dan het te
overschatten).

**Waar dit géén aanpassing kreeg (met reden):**
- Financiële tracking (waarde ontladen / netlaadkosten): we meten steeds
  het werkelijk toegepaste vermogen op het moment zelf, niet een
  "wat erin gaat moet eruit komen"-aanname — rendementsverlies zit daar
  al impliciet in verwerkt.
- Beschikbare-energie-sensor: die komt van de Zendure zelf en geeft
  vermoedelijk al de bruikbare (dus al gecorrigeerde) capaciteit.

Getest: bij 80% rendement werd een ruwe PV-schatting van 6,0 kWh correct
teruggebracht naar 4,8 kWh aftrek.

## v0.34.0 — zelflerend accu-rendement (i.p.v. handmatig ingesteld)

**Aanleiding:** de vraag of de integratie het werkelijke accu-rendement
(~80%) ook zelf kan afleiden, in plaats van dat je het handmatig moet
schatten en instellen.

**Hoe het werkt:** de integratie houdt continu bij hoeveel energie er
daadwerkelijk **in** de accu gaat (laden) en **uit** komt (ontladen), via
je batterijvermogen-sensor, en vergelijkt dat met de werkelijke
verandering in beschikbare energie:

> geladen_kWh × rendement = ontladen_kWh + verandering_beschikbare_kWh

Zodra er genoeg geladen energie is verzameld voor een betrouwbare meting
(minimaal 1 kWh per meting, om ruis te vermijden), wordt er een nieuwe
rendement-schatting toegevoegd aan een rollend gemiddelde (7 dagen, zelfde
patroon als de andere leerprocessen). Onmogelijke uitschieters (buiten
50-100%, vrijwel zeker een sensor-hapering) worden genegeerd.

**Voorrang:** zodra er genoeg metingen zijn (minimaal 3), wint het
**geleerde** rendement automatisch van de handmatig ingestelde
config-waarde in de PV-aftrek-berekening (v0.33.0). Zonder genoeg
metingen blijft de configuratiewaarde gewoon de terugval.

Nieuwe sensor: **`sensor.learned_battery_efficiency`** (met de losse
metingen als attribuut). Ook meegenomen in de `learning_health`-controle
uit v0.32.0, zodat je meteen ziet als dit leerproces vastzit.

Getest: een gesimuleerde volledige laad/ontlaad-cyclus op exact 80%
rendement werd door de integratie zelf ook exact als 80,0% herkend — en
dat geleerde getal kreeg vervolgens correct voorrang boven een
(expres afwijkend ingestelde) config-waarde van 95%.

**Vereist:** zowel `battery_power_sensor_entity` als
`available_energy_sensor_entity` moeten ingesteld zijn — zonder een van
beide kan dit niet leren (en blijft de handmatige config-waarde gewoon
gebruikt worden, zoals voorheen).

## v0.34.1 — fix: "no_forecast_data" ondanks zichtbaar geldige prijsdata

**Aanleiding:** een gebruiker zag `no_forecast_data` in het dashboard,
terwijl de onderliggende Zonneplan-sensor aantoonbaar een volledig
correcte `forecast`-lijst had (tientallen kwartieren met geldige
start/eind-tijden en prijzen).

**Vermoedelijke oorzaak:** `dt_util.parse_datetime()` verwacht een
**tekst-string** als invoer. Als de Zonneplan-integratie is bijgewerkt en
`start_date`/`end_date` sindsdien als **al-geparste Python-datetime-
objecten** aanlevert in plaats van tekst (onzichtbaar in elke YAML/JSON-
weergave, die altijd tekst toont), faalt die aanroep stilzwijgend op elk
item — met precies "geen bruikbare data" tot gevolg, ook al ziet de
brondata er prima uit.

**Fix:** nieuwe helper `_parse_forecast_datetime()` die zowel tekst-
strings als al-geparste datetime-objecten accepteert, in plaats van
alleen tekst te verwachten. Getest: beide varianten worden nu correct
verwerkt, zonder het bestaande (tekst-)gedrag te breken.

**Kanttekening:** ik kon niet 100% hard bevestigen dat dit exact de
oorzaak was (de gedeelde data was een YAML-weergave, die het onderliggende
Python-type altijd als tekst toont, ongeacht wat het echt is) — maar de
fix is veilig sowieso, en lost precies deze klasse van fout op. Mocht het
probleem hierna nog steeds optreden, dan weten we dat de oorzaak elders
zit en gaan we verder zoeken.

## v0.34.2 — fout-tracering toegevoegd bij achtergrondtaken

**Aanleiding:** een gebruiker zag naast de "no_forecast_data"-melding ook
een nietszeggende `Task exception was never retrieved (task: None)`-fout
in de logs, drie keer opgetreden — zonder enige stacktrace of details om
de daadwerkelijke oorzaak te achterhalen.

**Gevonden gat:** `async_update()` (aangeroepen als achtergrondtaak bij
elke periodieke tick én elke statuswijziging van gekoppelde entiteiten)
had **geen enkele foutafhandeling**. Een onverwachte fout ergens in de
update-logica verdween daardoor spoorloos, op deze content-loze
asyncio-melding na — onmogelijk om te diagnosticeren.

**Fix:** `async_update()` vangt nu alle onverwachte fouten af en logt de
**volledige Python-foutmelding met stacktrace** (via `_LOGGER.exception`),
in plaats van dat de fout onzichtbaar verdwijnt. De vorige status blijft
gewoon staan tot de volgende geslaagde update.

**Voor de gebruiker die dit meldde:** dit lost het "no_forecast_data"-
probleem zelf nog niet direct op, maar zorgt dat de **volgende keer** dat
dit gebeurt, de logs eindelijk de echte oorzaak tonen (bestandsnaam, regel
en het exacte type fout) in plaats van een leeg "task: None". Zodra dat
zich voordoet: deel die volledige stacktrace, dan kunnen we de
onderliggende oorzaak definitief vinden.

## v0.34.3 — kritieke regressie gefixt: `_read_corrected_consumption_power` was per ongeluk verwijderd

**De daadwerkelijke oorzaak van de "no_forecast_data"-melding**, dankzij
de volledige stacktrace die de v0.34.2-fix eindelijk zichtbaar maakte:

```
AttributeError: 'EnergyManagementSystemCoordinator' object has no
attribute '_read_corrected_consumption_power'.
```

**Wat er misging:** bij het toevoegen van het zelflerende accu-rendement
(v0.34.0) is per ongeluk de `def`-regel van de bestaande methode
`_read_corrected_consumption_power` overschreven, waardoor de docstring
en implementatie van die methode los kwamen te hangen en per ongeluk als
dode/onbereikbare code binnen een andere (nieuwe) property terechtkwamen.
Python's compiler accepteerde dit stilzwijgend (geen syntaxfout — het was
gewoon onbereikbare code binnen een functie-body), dus de fout kwam pas
aan het licht bij daadwerkelijk gebruik: elke berekening die deze methode
aanriep, crashte met een `AttributeError`, wat de coordinator liet
stoppen halverwege de update — precies op het punt waar hij normaal de
prijsvoorspelling zou verwerken, vandaar de misleidende
"no_forecast_data"-melding (de update crashte namelijk vóórdat dat
specifieke stukje ooit bereikt kon worden bij een latere,
gedeeltelijk geslaagde tick).

**Fix:** de methode is hersteld met zijn eigen `def`-regel, exact zoals
hij hoorde te zijn.

**Extra controle uitgevoerd:** een volledige AST-scan van het hele
bestand, die alle `self.<methode>()`-aanroepen vergelijkt met alle
daadwerkelijk gedefinieerde methoden — bevestigt dat dit de **enige**
zo'n regressie was, nergens anders in het bestand.

**Getest:** de methode geeft na de fix weer correct het gecorrigeerde
verbruik terug (300+500+100=900W in een testscenario), en een volledige
update-cyclus draait weer zonder te crashen.

Dank aan de gebruiker die dit heeft gemeld en, cruciaal, de volledige
stacktrace heeft gedeeld zodra die beschikbaar was — zonder die
stacktrace (mogelijk gemaakt door de v0.34.2-fix) was dit vrijwel
onmogelijk geweest om te vinden.

## v0.35.0 — hysterese tegen flikkerende energie-brug-beslissing

**Aanleiding:** een gebruiker zag in het overgangs-logboek 10 wisselingen
tussen "genoeg energie" en "te weinig" binnen anderhalf uur, inclusief een
onmogelijke negatieve beschikbare energie (-0,09 kWh) — de beslissing
"twijfelde" continu rond het omslagpunt in plaats van stabiel te blijven.

**Twee fixes:**

1. **Negatieve beschikbare energie wordt geklemd op 0.** Fysiek
   onmogelijk, vrijwel zeker sensorruis rond een lege accu — voorheen liet
   dit de vergelijking onnodig verschuiven.

2. **Hysterese (dode zone) rond de drempel.** In plaats van precies op
   het omslagpunt te vergelijken, vereist een wissel nu een duidelijke
   marge (minimaal 0,15 kWh, of 10% van de benodigde energie): als de
   integratie aan het uitstellen was, moet het tekort eerst duidelijk
   zijn voordat er weer wordt bijgeladen; als de integratie aan het
   bijladen was, moet er eerst duidelijk genoeg overschot zijn voordat
   het uitstellen weer wordt hervat.

Getest: exact het geobserveerde patroon (available_kwh wisselend tussen
0,00 en -0,09 kWh, 9 metingen over anderhalf uur) resulteerde voorheen in
bijna constant wisselen, en blijft nu volledig stabiel.

**Nog steeds relevant om te weten:** het noodladen (v0.29.0) grijpt bewust
niet in als er geen weinig-zon-verwachting is (zomer-scenario) — als de
accu dan toch leegloopt, is dat een bewuste afweging (snel weer bijgevuld
door zon) in plaats van een bug. Mocht dit vaker frustreren, is dat een
apart gesprek waard over of die grens moet verschuiven.

## v0.36.0 — structurele extra marge tegen de onbeschermde "smart"-periode

**Vervolg op het incident van v0.35.0.** Analyse van de financiële
tracking (discharge-waarde steeg met €2,22 tussen twee metingen, tegen
~€0,32-0,36/kWh) bevestigde: er is die avond ~6,5 kWh verkocht tijdens
het dure-kwartier-blok — de reserve werd **correct** gerespecteerd tot
precies de grens. Het probleem zat in wat **daarna** gebeurde: zodra het
dure kwartier voorbij is, gaat de integratie terug naar `smart`-modus,
waarin de Zendure's eigen logica het huishoudverbruik dekt — volledig
buiten onze reserve-bescherming om. Die nacht is de accu dus verder
leeggetrokken zonder dat wij daar iets tegen konden doen.

**Fix:** een nieuwe, structurele extra marge van **+15 procentpunt**
(bovenop de bestaande 10% basis en de andere geleerde correcties) in de
ontlaad-reserve-berekening, specifiek om deze onbeschermde periode te
compenseren — minder verkopen tijdens het dure kwartier zelf, zodat er
meer buffer overblijft voor wat er daarna, buiten onze controle, nog
wordt verbruikt.

Getest: de reserve-marge steeg van 10% naar 25% in een representatief
scenario, wat in de praktijk zo'n 0,4 kWh minder verkoop betekent per
duur kwartier-avond — een bewuste, structurele trade-off tussen iets
minder verdienen en betrouwbaarder zelfvoorzienend blijven.

**Werkt samen met de bestaande zelflerende correcties** (tekort-/
overschot-detectie, v0.30.0) — die blijven de marge verder verfijnen
bovenop deze nieuwe structurele basis.

## v0.37.0 — correctie: smart_discharging blokkeert zon niet (verkeerde aanname uit v0.25.0 hersteld)

**Belangrijke correctie.** In v0.25.0 bouwden we een uitzondering: "forceer
nooit `smart_discharging` zolang er actief zon wordt geproduceerd" — de
aanname was dat `smart_discharging` zonne-energie zou blokkeren/missen.

**Die aanname bleek onjuist.** Op deze Zendure-hardware (2400AC, 3
accu's) blokkeert `smart_discharging` de zon niet — het stuurt de zon
gewoon rechtstreeks naar het net (export) in plaats van de accu op te
laden, en de accu helpt dan alleen bij verbruikspieken. Zon wordt dus in
**beide** modi nuttig gebruikt; alleen de bestemming (opslaan vs.
verkopen) verschilt. De uitzondering blokkeerde daardoor precies het
gewenste gedrag: zon verkopen tegen een redelijke prijs nú, in plaats van
'm op te slaan voor een moment dat toch al goedkoper wordt.

**Fix:** de uitzondering is volledig verwijderd. De normale prijs-/
reserve-logica bepaalt nu weer zelf of het `smart_discharging` (zon
verkopen) of `smart` (zon opslaan) wordt, ongeacht of er op dat moment
toevallig zon wordt geproduceerd.

Getest: bij een normale (niet-duur) prijs, actieve zon, en vóór het
goedkoopste blok, kiest de integratie nu correct `discharging_window`
(zon gaat het net op) in plaats van geforceerd `smart` (zon zou worden
opgeslagen).

## v0.38.0 — fix: eenheid-mismatch bij Wh-sensoren (werkelijke PV-opbrengst)

**Gevonden bij het uitzoeken waarom de PV-voorspelling-vergelijking nooit
nieuwe resultaten opleverde:** `sensor.solaredge_energy_today` rapporteert
in **Wh** (Watt-uur), niet **kWh** — bevestigd via de status-attributen
(`unit_of_measurement: Wh`, waarde `1694.0`). Onze code las dit getal
altijd rechtstreeks in alsof het al kWh was, een factor 1000 te groot.
Elke vergelijking werd daardoor terecht (door onze eigen
plausibiliteitscontrole) afgewezen als onmogelijke uitschieter — vandaar
dat er nooit nieuwe, geldige afwijkingen werden bijgeschreven.

**Fix:** zowel `_read_float` (solar_forecast.py) als
`_read_sensor_float` (coordinator.py, gebruikt door vrijwel alles) kijken
nu naar het `unit_of_measurement`-attribuut van een sensor, en zetten
automatisch **Wh → kWh** (delen door 1000) en **MWh → kWh** (keer 1000)
om. Vermogensensoren (W) en sensoren zonder eenheid-attribuut blijven
ongewijzigd — de conversie triggert alleen specifiek op "wh"/"mwh".

Ook de historische bootstrap (`async_bootstrap_from_history`) is
bijgewerkt om dezelfde conversie toe te passen op de werkelijke-opbrengst-
sensor.

**Getest:** exact jouw waarde (1694,0 Wh) wordt nu correct gelezen als
1,694 kWh. Volledige regressietest bevestigt dat vermogensensoren (W),
percentages, en sensoren zonder eenheid-attribuut ongewijzigd blijven —
alleen echte Wh/MWh-sensoren worden nu automatisch omgerekend.

**Verwacht effect:** vanaf vanavond (23:59:50) zou de eerste geldige
vergelijking eindelijk moeten lukken, en vervolgens dagelijks verder
opbouwen zoals bedoeld.

## v0.39.0 — fix: smart_discharging verscheen nooit bij een ongebruikelijk prijspatroon

**Gevonden:** `discharge_start` (23:45) lag ná `cheap_block_start` (14:00)
— een onmogelijke, lege tijdspanne, waardoor `smart_discharging` nooit
kon verschijnen. Oorzaak: `_compute_dynamic_discharge_start` zocht "het
laatste dure kwartier van vandaag" zonder rekening te houden met dagen
waarin het goedkoopste blok **overdag** valt (zon-gedreven dip) gevolgd
door een **latere avondpiek** — dan ligt die "laatste dure periode" ná
het eerstvolgende goedkope blok, wat de venster-berekening omkeert.

**Fix:** `_compute_dynamic_discharge_start` houdt nu alleen rekening met
dure kwartieren die vóór `cheap_block_start` liggen. Getest: in een
normaal patroon (avond duur → nacht goedkoop) verschijnt
`smart_discharging` gewoon weer (bevestigd met 4 kwartieren in een
testscenario); bij het ongebruikelijke patroon van vandaag levert de
berekening nu terecht `None` op (geen geldig venster) in plaats van een
kapotte, omgekeerde tijdspanne.

## Nieuwe sensor: live prijsvergelijking

Om voortaan zelf te kunnen controleren of de integratie dezelfde prijs
ziet als de Zonneplan-sensor: nieuwe sensor
**`sensor.current_price_used_by_integration`**, die exact de prijs toont
die de integratie op dit moment gebruikt voor haar beslissing — direct
vergelijkbaar met de actuele status van je Zonneplan-sensor.

## Dashboard bijgewerkt

De financiële kaart is vervangen door de door de gebruiker zelf
gecorrigeerde versie (enkele utility_meter-entiteitsnamen kwamen niet
overeen met wat er daadwerkelijk in HA staat). De nieuwe prijs-
vergelijkingssensor is toegevoegd aan de "Actuele beslissing"-kaart.

## v0.40.0 — headroom prioritair naar de duurste kwartieren, niet chronologisch

**Aanleiding:** de vraag om écht op de duurste kwartieren te ontladen,
niet gewoon een blok van x uren. Bij een langdurige avondpiek met
oplopende prijzen (bv. 0,317 → 0,364 €/kWh over 5 uur) verbruikte de
beperkte headroom zich voorheen **chronologisch**: de eerste kwartieren
die de dynamische drempel haalden "wonnen", ook al kwamen er later
diezelfde piek nog duurdere kwartieren aan.

**Fix:** nieuwe methode `_is_worth_discharging_now()` rangschikt alle
resterende dure kwartieren van vandaag op prijs, en berekent hoeveel
kwartieren de huidige headroom daadwerkelijk aankan. Alleen als "nu" tot
die duurste, betaalbare kwartieren behoort, wordt er ontladen — anders
wordt de headroom bewust bewaard voor een beter moment later diezelfde
piek.

Getest: bij een piek van 0,317 tot 0,364 €/kWh met headroom voor slechts
~2 kwartieren, hield de integratie correct in bij 18:30 (relatief
goedkoop binnen de piek) en ontlaadde ze wél vol vermogen bij 20:27
(bijna de topprijs) — exact het "duurste eerst"-gedrag.

**Werkt samen met** de bestaande reserve-bescherming: als er sowieso geen
headroom is (reserve al opgesoupeerd), blijft dat de eerste blokkade;
deze nieuwe check is een extra laag daarbovenop, specifiek voor het
prioriteren wélke kwartieren de beschikbare headroom mogen gebruiken.

## Aanvulling op v0.40.0: planningstabel toont nu ook prijs-prioriteit

De planningstabel (Overzicht komende uren) simuleerde headroom-verbruik
nog steeds chronologisch. Bijgewerkt zodat de simulatie **ook** eerst de
duurste kwartieren van elke dag rangschikt en de headroom daaraan
toewijst — exact hetzelfde principe als de live beslissing (v0.40.0),
zodat wat je in het dashboard ziet overeenkomt met wat er echt gaat
gebeuren.

Getest: bij dezelfde 5-uur-piek (0,317 → 0,3637 → 0,317 €/kWh) met
headroom voor ~13 kwartieren, toont de planning nu correct de 13
kwartieren rond de piekprijs (19:15-22:15), niet de eerste 13
chronologische kwartieren vanaf 18:30.

## v0.40.1 — kritieke regressie gefixt: sensor-setup crashte volledig

**Oorzaak van "veel entiteiten niet beschikbaar":** bij het toevoegen van
`CurrentPricePerKwhSensor` (v0.39.0) is exact hetzelfde soort fout gemaakt
als eerder bij `_read_corrected_consumption_power` (v0.34.3) — de
`__init__`/`native_value`/`extra_state_attributes` van de bestaande
`CheapestBlockStartSensor` raakten losgekoppeld van hun eigen klasse en
belandden per ongeluk in de nieuwe `CurrentPricePerKwhSensor`. Resultaat:
`CheapestBlockStartSensor(coordinator, entry_id)` miste een verplicht
argument, waardoor **de hele sensor-platform-setup crashte** bij het
opstarten — vandaar dat zoveel entiteiten (niet alleen de nieuwe) als
"niet beschikbaar" verschenen.

**Fix:** beide klassen hersteld met hun eigen, correcte `__init__`.

**Extra controle:** een volledige AST-scan over **alle** bestanden
(sensor.py, coordinator.py, diagnostics.py, config_flow.py, switch.py,
solar_forecast.py) bevestigt dat dit de enige zo'n regressie was.

**Getest:** alle drie betrokken sensoren (`CheapestBlockStartSensor`,
`CurrentPricePerKwhSensor`, `DischargeWindowStartSensor`) daadwerkelijk
runtime geïnstantieerd (niet alleen gecompileerd) — allemaal correct,
met werkende `native_value`.

**Les:** dit is de tweede keer dat een str_replace-bewerking een
bestaande klasse per ongeluk beschadigde bij het toevoegen van nieuwe
code ernaast. Voortaan extra alert op deze specifieke faalmodus bij het
invoegen van nieuwe sensor-klassen vlak naast bestaande.

## v0.40.2 — fix: attributen van upcoming_schedule te groot voor de recorder

**Gevonden in de logs:** "State attributes for
sensor.energy_management_system_upcoming_schedule exceed maximum size of
16384 bytes" — 593 keer gelogd. Oorzaak: het `timeline`-attribuut bevatte
**elk los kwartier** (tot ~48 uur vooruit = ~150+ items), wat de
16KB-grens van Home Assistant's recorder overschrijdt. Gevolg: de
geschiedenis van deze sensor werd niet opgeslagen (wel de live status,
dus het dashboard bleef werken, maar de historische grafiek niet).

**Fix:** het `timeline`-attribuut is verwijderd — het werd nergens
gebruikt (het dashboard leest alleen het veel kleinere, samengevatte
`transitions`-attribuut). Getest met een realistisch 48-uurs scenario:
21.896 bytes (oud, boven de limiet) → 754 bytes (nieuw, ruim eronder).

**Voor de duidelijkheid:** `sensor.cloudems_battery_schedule` in dezelfde
foutmelding hoort bij CloudEMS, niet bij deze integratie — die val ik
buiten mijn verantwoordelijkheid, gezien je CloudEMS toch wilt
verwijderen.

## v0.41.0 — verouderde dubbele reservering verwijderd (8,4 kWh → 0,0 kWh)

**Aanleiding:** de opsplitsing in het dashboard toonde 8,4 kWh
"reservering dure kwartieren" — veel te veel, terecht bevraagd.

**Oorzaak:** `_estimate_upcoming_discharge_kwh()` (v0.23.0) telde alle
resterende dure kwartieren van vandaag bij elkaar op tegen **vol
vermogen** (1600W), als extra reservering bovenop de basisbehoefte. Dit
was destijds nodig omdat er geen andere bescherming was tegen "te veel
verkopen tijdens dure kwartieren". Maar sinds v0.31.0/v0.40.0 wordt de
daadwerkelijke ontlading tijdens dure kwartieren al **zelf begrensd**
door de headroom-check en prijs-prioriteit — die zal nooit onder de
reserve-drempel zakken, per ontwerp. De aparte reservering telde dus
dezelfde bescherming **dubbel**, en blies de benodigde energie
onnodig op.

**Fix:** de aparte reservering is verwijderd (nu altijd 0,0 kWh, veld
blijft zichtbaar in de opsplitsing voor transparantie/consistentie). De
nu-overbodige functie `_estimate_upcoming_discharge_kwh()` is ook
verwijderd.

Getest: opsplitsing toont nu correct `reservering_dure_kwartieren_kwh:
0.0` in plaats van een opgeblazen waarde.

**Effect:** de energie-brug-check (en dus de smart_discharging-beslissing)
wordt hiermee minder onnodig conservatief — er wordt niet langer
gewacht met het uitstellen van laden vanwege een dubbeltellende
reservering die niet meer nodig is.

## v0.41.1 — dashboard-fix: woonkamer-voorvoegsel voor de prijsvergelijkingssensor

`sensor.current_price_used_by_integration` (v0.39.0) kreeg, net als
eerdere nieuwe sensoren, het `woonkamer_`-voorvoegsel toegewezen. Het
dashboard-bestand is bijgewerkt naar
`sensor.woonkamer_energy_management_system_current_price_used_by_integration`.

## v0.42.0 — planning gebruikt nu altijd verse beschikbare-energie-data

**Aanleiding:** de zorg over lange "manual"-blokken in de planning bleef
bestaan, ook na de prijs-prioriteit van v0.40.0.

**Gevonden oorzaak:** de planningsprojectie gebruikte
`self.last_available_kwh`, die alleen wordt bijgewerkt als de
energie-brug-check die specifieke tick daadwerkelijk (volledig)
doorloopt — dat gebeurt niet altijd (bv. midden op de dag, ver van elk
beslismoment). Als die waarde stale/`None` was, viel de
aftopping-logica volledig terug op de oude, ongelimiteerde prijs-only
projectie — vandaar dat het lange blok bleef verschijnen ondanks de
v0.40.0-fix.

**Fix:** de planning leest nu altijd een **verse** meting van de
beschikbare-energie-sensor, los van wat de energie-brug-check die tick
wel of niet heeft bijgewerkt.

Getest met realistische meerdaagse prijsdata (goedkoopste blok correct
wijzend naar de volgende dag, niet naar "nu"): bij 3,9 kWh beschikbaar
tegen een ~19 uur lange overbruggingsperiode werd het volledige
"manual"-blok terecht afgetopt naar 0 kwartieren.

## v0.43.0 — reserve beschermt nu het diepste punt, niet alleen het eindsaldo

**De kernvraag die dit blootlegde:** "dit lange blok zorgt er toch voor
dat mijn accu te leeg is om 's nachts nul op de meter te houden?" — en
daar zat een echt, structureel probleem achter.

**Het probleem:** de reserve-berekening telde verbruik minus verwachte
zon op tot **één netto-getal over de hele overbruggingsperiode** (bv. nu
tot morgen 11:15). Maar zon komt alleen overdag binnen — als de
verwachte zonopbrengst voor morgen groot genoeg is, kan het netto-saldo
er prima uitzien (of zelfs op 0 uitkomen), terwijl er 's nachts, vóórdat
de zon opkomt, alsnog een reëel tekort is. Het totaalgetal verborg dit
dieptepunt volledig.

**Fix:** nieuwe methode `_estimate_worst_case_deficit_kwh()` loopt uur
voor uur door de overbruggingsperiode heen en houdt het **cumulatieve
tekort** bij (verbruik minus zon per uur, nooit onder 0 geklemd — een
overschot aan zon overdag kan een eerder nachtelijk tekort niet met
terugwerkende kracht compenseren). De reserve wordt nu bepaald door het
**diepste punt** dat onderweg wordt bereikt (meestal vlak vóór
zonsopkomst), niet het eindsaldo.

Getest met een realistisch scenario (11+ kWh zon verwacht, geconcentreerd
tussen 8:00-16:00, nul zon 's nachts): de oude methode gaf 0,0 kWh
reserve, de nieuwe methode identificeerde correct 2,475 kWh nachtelijk
tekort. In de volledige beslissingscyclus resulteerde dit in een
planning die het lange avondblok correct aftopte naar 14 kwartieren in
plaats van bijna het hele blok (~20 kwartieren).

**Dit is waarschijnlijk de daadwerkelijke, onderliggende oorzaak** van
meerdere eerdere meldingen over een te snel lege accu — niet opgelost
door losse marges of noodladen, maar door de reserve-berekening zelf
fundamenteel correct te maken.

## v0.43.1 — live-verbruikscorrectie ontbrak in de nieuwe diepste-tekort-berekening

**Terechte vraag:** is de nieuwe 2,475 kWh-reserve (v0.43.0) dynamisch,
en houdt die rekening met bv. de airco die een keer 's nachts aanstaat?

**Antwoord: nog niet volledig.** De nieuwe
`_estimate_worst_case_deficit_kwh()` gebruikte alleen het **geleerde
gemiddelde per uur** - de live-verbruikscorrectie die we bij het
airco-scenario bouwden (v0.29.0) was hier niet toegepast.

**Fix:** dezelfde live-verbruikscorrectie toegevoegd - als het huidige
live verbruik hoger is dan het geleerde gemiddelde voor dit uur, wordt
de **hele** diepste-tekort-berekening evenredig opgeschaald, niet alleen
het huidige uur.

Getest: bij 3x hoger live verbruik (airco aan) steeg de berekende
reserve ook exact 3x (van 2,475 naar 7,425 kWh) - identiek aan het
effect dat we destijds voor de gewone reserve-berekening bevestigden.

**Dus ja, dit getal is nu écht dynamisch**: het wordt elke ~15 minuten
opnieuw berekend, en reageert direct op ongebruikelijk hoog actueel
verbruik zoals de airco, niet alleen op historische gemiddelden.

## v0.44.0 — update-interval verlaagd van 15 naar 5 minuten

**Aanleiding:** de wens voor een zo responsief mogelijk systeem — de
reactieve live-verbruikscorrectie (v0.29.0/v0.43.1) kan nu binnen 5
minuten in plaats van 15 minuten reageren op bv. de airco die aanslaat.

**Gecontroleerd voor het wijzigen:** het interval wordt op één plek
zowel als klok-timer als in de vermogensberekening gebruikt
(`_get_soc_scaled_discharge_power`). Die berekening is intern
consistent: bij een korter interval staat hij terecht een hoger
*instantaan* vermogen toe voor dezelfde headroom, omdat er ook sneller
opnieuw wordt gecontroleerd — geen bug, maar noodzakelijk gevolg van
vaker bijsturen. De leerprocessen (rendement, verbruiksprofiel) gebruiken
al de werkelijk verstreken tijd (niet een aanname van 15 minuten), dus
die zijn ongevoelig voor deze wijziging.

**Overweging om te weten:** de Zendure ontvangt hiermee 3x zo vaak een
her-bevestiging van de modus/het vermogen (elke 5 in plaats van 15
minuten). Dit zou probleemloos moeten werken (dit is normaal voor
dit soort besturing), maar ik kan niet met zekerheid zeggen hoe de
Zendure-hardware zelf omgaat met vaker herhaalde commando's — mocht je
iets vreemds merken (bv. schokkerig schakelen), dan is dit de eerste
plek om naar te kijken en eventueel terug te zetten naar 15 (of een
tussenwaarde als 10).

## v0.44.1 — diagnostiek uitgebreid: exacte planning-cijfers zichtbaar

**Aanleiding:** een lang "manual"-blok op zondagavond, terwijl
`last_available_kwh` in de diagnostiek `None` toonde — leek op een
kapotte sensor, maar bleek uiteindelijk een rode haring: dat veld wordt
doelbewust op `None` gezet zodra "nu" al in/na het goedkoopste blok ligt
(dan is de energie-brug-check niet meer relevant). De sensor zelf bleek
prima te werken (7,776 kWh).

**Probleem:** hierdoor was het onmogelijk om met zekerheid vast te
stellen welke cijfers de **planningstabel** (die sinds v0.42.0 een eigen,
verse meting gebruikt) daadwerkelijk had gebruikt op het moment van de
diagnostiek-export.

**Fix:** twee nieuwe diagnostiekvelden, die exact vastleggen wat de
planning gebruikte: `last_projection_available_kwh` en
`last_projection_reserve_kwh`. Voortaan direct te zien of de planning
wél of niet over bruikbare cijfers beschikte, zonder giswerk.

## v0.45.0 — wacht op volledige HA-opstart vóór de eerste dataophaal

**Aanleiding:** de terugkerende "No usable forecast entries"-meldingen,
telkens precies rond het moment van een Home Assistant-herstart —
was het mogelijk dat de integratie te snel data opvroeg, vóórdat andere
integraties (zoals Zonneplan) klaar waren met opstarten?

**Bevestigd: ja.** `async_setup()` riep meteen `async_update()` aan
tijdens het eigen opstarten, zonder te wachten tot Home Assistant zelf
volledig was opgestart. Bij een koude boot kan onze integratie sneller
klaar zijn met haar eigen setup dan de Zonneplan-integratie, waardoor de
prijssensor nog geen `forecast`-attribuut heeft op het moment dat wij
ernaar vragen — precies de waargenomen fout, en precies waarom die
zichzelf altijd na een paar tellen oploste.

**Fix:** de integratie checkt nu of Home Assistant al volledig draait
(`hass.state == CoreState.running`). Zo ja (bv. bij het herladen van de
integratie zelf, niet een volledige HA-herstart): meteen data ophalen
zoals voorheen. Zo nee (koude boot): wacht netjes op het
`EVENT_HOMEASSISTANT_STARTED`-signaal, zodat alle andere integraties
eerst de kans krijgen om te laden.

Getest: beide paden (koude boot → wacht correct; HA al actief → meteen
update) gedragen zich exact zoals bedoeld.

**Verwacht effect:** de "No usable forecast entries"-meldingen bij
opstarten zouden hiermee (grotendeels) moeten verdwijnen.

## v0.45.1 — permanente testsuite toegevoegd (pytest)

**Aanleiding:** de vraag hoe ik zelf tegen de integratie aankijk bracht
een eerlijk antwoord naar boven: complexiteit is inmiddels het grootste
risico, en we testten dit hele traject ad-hoc met eenmalige scriptjes
die na gebruik weer verdwenen. Twee regressies (v0.34.3, v0.40.1)
ontstonden allebei doordat een bewerking per ongeluk een bestaande
klasse/methode beschadigde — beide compileerden probleemloos en kwamen
pas aan het licht bij daadwerkelijk gebruik.

**Toegevoegd: een echte, blijvende testsuite** (`tests/`, 25 tests, alle
groen), inclusief:
- Alle belangrijke scenario's uit dit hele traject vastgelegd als
  automatische regressietest (dynamische prijsdrempel, winter-guard,
  noodladen, negatieve prijzen, hysterese, rendement-leren,
  **diepste-tekort-reserve** (de belangrijkste veiligheidsfix),
  prijs-prioriteit, eenheid-conversie, opstart-timing).
- Een AST-gebaseerde structurele check die **specifiek** het soort fout
  vangt dat de twee historische regressies veroorzaakte (een verweesde
  methode/klasse na een bewerking) — geen live Home Assistant nodig.
  **Gevalideerd** door beide historische bugs tijdelijk opnieuw in te
  voeren: allebei meteen gevangen, met dezelfde foutmelding als destijds
  in productie.
- Een lichtgewicht mock van de benodigde `homeassistant`-modules
  (`tests/conftest.py`), zodat de integratie op de normale manier (eigen
  relatieve imports) getest wordt, zonder een echte HA-installatie nodig
  te hebben.
- GitHub Actions-workflow (`tests.yml`) die de suite automatisch draait
  bij elke push/pull request.

**Draaien:** `pip install pytest && python3 -m pytest -v` vanuit de
repo-root. Zie `tests/README.md` voor een overzicht per bestand.

## v0.46.0 — vakantiemodus

**Aanleiding:** tijdens vakantie is het huishoudverbruik compleet anders
— zonder aanpassing zou de integratie ofwel te veel reserveren (als ze
het normale profiel blijft gebruiken) ofwel het geleerde "normale"
profiel vervuilen met weken lage vakantiedata, wat na thuiskomst weer
tijd zou kosten om te herstellen.

**Nieuw: `switch.vacation_mode`.** Zet 'm aan vóór vertrek, uit bij
thuiskomst. Doet twee dingen tegelijk:

1. **Verbruiksinschatting verlaagd** — alle verbruiksschattingen
   (inclusief de diepste-tekort-reserve, v0.43.0) worden vermenigvuldigd
   met een instelbare reductiefactor, standaard **60%** (dus 40% van het
   normale verbruik wordt aangenomen). Aan te passen via de nieuwe optie
   **"Vakantie-verbruiksreductie (%)"**.
2. **Verbruiksleren gepauzeerd** — het uurverbruiksprofiel en het
   nachtvenster-gemiddelde worden niet bijgewerkt tijdens vakantiemodus,
   zodat de geleerde "normale" gegevens niet vervuild raken. PV-bias en
   accu-rendement blijven wél gewoon leren (die zijn niet
   verbruiksafhankelijk).

Getest (nu ook als permanente regressietest,
`tests/test_vacation_mode.py`): bij de standaard 60% reductie daalde de
verbruiksschatting exact naar 40% van normaal, en het uurverbruiksprofiel
bleef ongewijzigd tijdens een volledige update-cyclus met vakantiemodus
aan.

**Belangrijk:** de reductiefactor is een **schatting**, geen exacte
meting — sommige apparaten (koelkast, eventuele verwarming/koeling)
blijven wel verbruiken tijdens vakantie. De standaard 60% is bewust
conservatief; pas 'm aan als je eigen situatie sterk afwijkt.

## v0.47.0 — apparaat-bewustzijn (vaatwasser & wasmachine, puur informatief)

**Aanleiding:** het eerder gedeelde overzicht van apparaat-entiteiten
(`ems_apparaat_entiteiten_overzicht.md`) — drie gekozen vervolgstappen:
een dashboard-kaart, verbruikspatroon-leren, en actieve meldingen.

**Belangrijk: niets hiervan stuurt een apparaat aan.** Alles is puur
informatief/adviserend.

### 1. Nieuwe optionele config-velden
`Vaatwasser vermogen-sensor`, `Vaatwasser "klaar om te starten"-sensor`,
zelfde twee voor de wasmachine, en een optionele `Notify-service` (leeg =
gewone HA-pop-up-melding).

### 2. Verbruikspatroon-leren per apparaat
Nieuwe sensoren **`sensor.dishwasher_typical_usage_hours`** en
**`sensor.washing_machine_typical_usage_hours`** — houden per uur van de
dag bij hoe vaak dit apparaat actief is, en tonen de uren waarin dat
"typisch" is (≥15% van de tijd). Compact opgeslagen (samengevat per uur,
niet de ruwe metingen) om de eerder gevonden 16KB-attribuutlimiet
(v0.40.2) niet opnieuw te raken. Wordt **gepauzeerd tijdens vakantiemodus**
(v0.46.0), net als het huishoud-verbruiksprofiel.

### 3. Eén melding per dag, op het juiste moment
Zodra een apparaat klaarstaat om te starten (via de "klaar"-sensor) én
we ons momenteel in het goedkoopste prijsblok van de dag bevinden, stuurt
de integratie **één keer per dag per apparaat** een melding — via een HA-
pop-up (standaard) of een eigen notify-service. Geen melding als het
apparaat al draait, en geen dubbele meldingen dezelfde dag.

**Getest (13 nieuwe permanente tests):** geen melding buiten het
goedkoopste blok, wél erbinnen, geen dubbele melding, geen melding bij
een al-draaiend apparaat, correcte per-uur-tracking, pauzeren tijdens
vakantiemodus, en een correcte "typische uren"-berekening op basis van
frequentie.

**Bonus: de structurele-integriteitstest zelf is verbeterd** om ook
sensoren met extra constructor-argumenten (zoals deze twee) te dekken —
dat gat zou anders deze nieuwe sensoren ongetest hebben gelaten.

Dashboard bijgewerkt met een nieuwe "Apparaten"-kaart en de
vakantiemodus-schakelaar.

## v0.48.0 — live-verbruikscorrectie gedempt (alsnog gebouwd)

**Aanleiding:** een gebruiker zag `select.zendure_manager_operation`
binnen 30-50 seconden twee keer wisselen (Slim ontladen ↔ Slimme
Matching), en apart daarvan een absurd hoog basisverbruik (17,4 kWh)
in de live-uitleg. Beide bleken hetzelfde onderliggende probleem: de
live-verbruikscorrectie (v0.29.0/v0.43.1) gebruikte één momentane
meting, die door een korte piek de **hele** resterende schatting (soms
15+ uur) kon opblazen — precies het scenario dat we eerder al
signaleerden (de 33,5→0,4 kWh-sprong) maar destijds bewust niet
aanpakten.

**Fix — nu wel gebouwd, met twee lagen bescherming:**
1. **Demping via een glijdend gemiddelde**: in plaats van één meting
   gebruiken we het gemiddelde van de laatste 4 metingen (~15-20
   minuten bij de huidige 5-minuten-cyclus). Eén korte piek tussen
   normale metingen wordt daardoor sterk afgevlakt.
2. **Bovengrens op de correctiefactor**: zelfs na demping wordt de
   factor nooit hoger dan **5x** — een grotere afwijking is
   vrijwel zeker een sensor-hapering, geen echte structurele verandering.

**Blijft volledig responsief voor een echte, aanhoudende verandering**
(bv. de airco die een tijd aan blijft staan) — dat wordt nog steeds
correct met de volle factor doorberekend, alleen een kortstondige piek
niet meer.

Getest (nu ook permanent, 4 nieuwe/bijgewerkte tests): één korte piek
(900W tussen normale metingen) werd gedempt van een rauwe 3x naar 1,5x;
een aanhoudende verhoging bleef volledig responsief op 3x; een extreme
uitschieter (9000W, vermoedelijk een glitch) werd via demping al
teruggebracht van 30x naar 8,25x, en vervolgens afgetopt op de
maximale 5x.

## v0.49.0 — stabiliteit goedkoopste-blok-selectie (nieuwe, andere oorzaak)

**Aanleiding:** ondanks de demping van v0.48.0 blijven wilde
schommelingen optreden in het energie-brug-logboek (bv. 24,37 kWh direct
gevolgd door 0,0 kWh, met **ongewijzigde** beschikbare energie). Dit kon
niet door een verbruikspiek komen — de sprong was te groot en
`available_kwh` bleef gelijk.

**Gevonden, andere oorzaak:** de goedkoopste-blok-detectie
(`_cheapest_block_range`) kon wisselen tussen twee **bijna-gelijke**
kandidaten ergens anders op de dag, zodra "nu" een kwartiergrens
overschreed en de "nog aankomende" kwartieren-lijst verschoof. Zo'n
wissel verandert het aantal uren tot het goedkoopste blok drastisch,
en dus ook de benodigde reserve — zonder dat er iets wezenlijks is
veranderd.

**Fix:** hysterese op de blok-selectie zelf. Zolang het vorige gekozen
kwartier nog "aankomend" is én het prijsverschil met de nieuwe
kandidaat klein is (binnen 5% van de dagelijkse prijsrange), blijft de
vorige keuze staan. Een écht goedkopere kandidaat (buiten die marge)
wint gewoon meteen, zoals het moet.

**Ook toegevoegd:** `cheap_block_start` wordt nu opgeslagen bij elke
logboek-vermelding, zodat een toekomstige schommeling **met zekerheid**
kan worden toegeschreven aan een gewisseld doelblok, in plaats van te
moeten gissen. Dashboard-tabel uitgebreid met deze kolom.

Getest (4 nieuwe permanente tests): de vorige keuze blijft stabiel
zolang die nog geldig is, wisselt onvermijdelijk zodra die kwartier
écht is verstreken, en een werkelijk veel goedkopere kandidaat wint nog
steeds direct (hysterese beschermt alleen tegen bijna-gelijke standen).

Dashboard bijgewerkt met de door de gebruiker gecorrigeerde
entiteitsnamen en de nieuwe logboek-kolom.

## v0.49.1 — icoon toegevoegd (accu + bliksem)

**Aanleiding:** de integratie toonde "icon not available" in HACS.

Sinds Home Assistant 2026.3 kunnen custom integraties hun eigen
merkicoon direct meeleveren via een `brand/`-map in de integratie zelf —
de oude `home-assistant/brands`-repository accepteert daar geen PR's meer
voor (aangekondigd via de Brands Proxy API). Toegevoegd:
`custom_components/energy_management_system/brand/icon.png` (256×256) en
`icon@2x.png` (512×512), voldoend aan de HA-richtlijnen (vierkant,
transparante achtergrond, getrimd).

**Bekende beperking (niet iets wat ik kan oplossen):** er is een actuele
HACS-bug (`hacs/integration#5171` / `#5223`) waarbij het "Update"-
overzicht in HACS zelf dit soort inline-merkicoontjes nog niet toont —
dat scherm haalt icoontjes nog van een externe CDN die geen weet heeft
van custom-integratie-icoontjes. Het icoon **zou wel gewoon moeten
verschijnen** in Instellingen → Apparaten & Diensten en op de
apparaatpagina zelf, aangezien Home Assistant die rechtstreeks via de
lokale brands-proxy serveert.

## v0.49.2 — dashboard: eigen zijbalk-item + meerdere tabbladen

**Twee dingen aangepakt:**

**1. Overzichtelijker: 5 tabbladen in plaats van 1 lange lijst.**
`dashboards/energy_management_system_dashboard.yaml` is omgezet naar een
dashboard met eigen `views:` (tabbladen): **Overzicht**, **Financieel**,
**Zelflerend**, **Apparaten**, **Geschiedenis**.

**2. Automatisch een eigen item in de zijbalk (eenmalige instelling).**
Een integratie kan niet veilig zelf `configuration.yaml` aanpassen — dat
zou risicovol zijn voor je HA-installatie. In plaats daarvan: voeg
**eenmalig** dit toe aan je `configuration.yaml` (via **Instellingen →
Add-ons → Bestandseditor**, of via Samba/SSH):

```yaml
lovelace:
  dashboards:
    energy-management-system:
      mode: yaml
      title: Energy Management System
      icon: mdi:home-lightning-bolt
      show_in_sidebar: true
      filename: energy_management_system_dashboard.yaml
```

Plaats `energy_management_system_dashboard.yaml` in je `config/`-map
(dezelfde map als `configuration.yaml`), herstart Home Assistant, en het
dashboard verschijnt daarna **permanent als eigen item in de zijbalk** —
elke toekomstige update van dit bestand (bij een nieuwe versie van de
integratie) verschijnt dan vanzelf, zonder dat je iets in de UI hoeft te
kopiëren/plakken.

## v0.49.3 — industriële tegel-look voor het Overzicht-tabblad (Mushroom Cards)

**Aanleiding:** de wens voor een strakkere, "industriële" uitstraling
(zoals de Zendure-app zelf) met waarden in tegels/plaatjes in plaats van
platte tekstlijsten.

**Vereist: Mushroom Cards (via HACS).** Het Overzicht-tabblad gebruikt nu:
- `custom:mushroom-title-card` — titel + actuele reden als ondertitel.
- Twee `gauge`-kaarten (ingebouwd in HA) voor Accu-SoC en geleerd
  rendement — ronde meters, net als de Zendure-app.
- Een raster van `custom:mushroom-template-card`-tegels (beschikbare
  energie, verbruik, prijs, modus, verwachte modus, aantal dure
  kwartieren) — elk met een eigen icoon en kleur.
- `custom:mushroom-select-card` voor de Zendure-modus — een nette
  segmented-button-achtige weergave in plaats van een dropdown.
- `custom:mushroom-entity-card`-tegels voor de drie schakelaars (Force
  manual / Learning only / Vakantiemodus).

De overige tabbladen (Financieel, Zelflerend, Apparaten, Geschiedenis)
gebruiken voorlopig nog de standaard `entities`-weergave — laat weten of
je wilt dat dezelfde tegel-stijl daar ook wordt doorgevoerd.

**Belangrijk:** dit tabblad werkt nu **alleen** met Mushroom Cards
geïnstalleerd (bevestigd dat je dit al hebt via HACS). Zonder Mushroom
zou dit tabblad kapotte kaarten tonen.

## v0.50.0 — systeemstatus-sensor (werkt de integratie goed?)

**Aanleiding:** de wens voor een entiteit die in één oogopslag laat zien
of de integratie goed functioneert, zonder dat je daarvoor de Home
Assistant-logs hoeft te doorzoeken.

**Nieuw: `sensor.system_status`.** Toont:
- **"OK"** — de laatste update is geslaagd.
- **"Fout"** — de laatste update crashte met een onverwachte fout (sinds
  v0.34.2 vangen we die al af zodat de integratie niet stopt, maar nu
  wordt dat ook zichtbaar gemaakt i.p.v. alleen in de logs).
- **"Mogelijk vastgelopen"** — er is al langer dan 3x het update-interval
  (nu 5 minuten, dus >15 minuten) geen enkele update meer geweest, geslaagd
  of niet — een signaal dat de update-cyclus zelf mogelijk is gestopt.

Attributen: `last_error` (de foutmelding zelf), `last_error_time`,
`last_successful_update` — voor als je toch wilt doorklikken naar meer
detail.

Getest (4 nieuwe permanente tests): OK na een geslaagde update, Fout na
een crash, herstel naar OK bij een volgende geslaagde update, en
"Mogelijk vastgelopen" als er te lang niks is gebeurd.

Toegevoegd als prominente tegel bovenaan het Overzicht-tabblad (groen
vinkje bij OK, rood uitroepteken anders), en meegenomen in
`diagnostics.py`.

## v0.51.0 — dashboard-sjabloon automatisch geplaatst bij eerste installatie

**Correctie op eerdere, te stellige uitspraak:** het registreren van het
dashboard in `configuration.yaml` (v0.49.2) zorgde er **niet** voor dat
het bestand zelf zich bijwerkt — dat vereiste nog steeds handmatig
kopiëren. Excuus voor de verwarring.

**Ook gevonden en gefixt: het dashboard-bestand stond buiten de map die
HACS daadwerkelijk naar je systeem installeert** (`custom_components/
energy_management_system/`) — het stond in een `dashboards/`-map op
repo-niveau, die HACS nooit meekopieert. Verplaatst naar
`custom_components/energy_management_system/dashboard_template.yaml`,
zodat het bestand ook echt op je systeem terechtkomt.

**Nieuw: automatisch geplaatst bij de allereerste installatie.** Bij het
opstarten van de integratie wordt gecontroleerd of
`config/energy_management_system_dashboard.yaml` al bestaat — zo niet,
dan wordt het meegeleverde sjabloon daar automatisch naartoe gekopieerd.
**Bestaat het bestand al** (bijvoorbeeld omdat je het al hebt, of eigen
aanpassingen hebt gedaan), dan wordt het **nooit overschreven** — je
aanpassingen gaan dus nooit verloren.

**Belangrijke beperking, eerlijk gezegd:** dit helpt alleen bij de
allereerste keer. Toekomstige dashboard-verbeteringen van mij moeten nog
steeds handmatig gekopieerd worden — een bestaand, mogelijk aangepast
bestand veilig automatisch "bijwerken" zonder je eigen wijzigingen kwijt
te raken, is niet iets wat dit automatisch kan (of zou moeten) doen.

Getest (2 nieuwe permanente tests): het sjabloon wordt gekopieerd als het
bestand ontbreekt, en een al bestaand (aangepast) bestand blijft
gegarandeerd ongewijzigd.

## v0.52.0 — dashboard wordt nu bij elke update automatisch overschreven

**Afspraak:** de gebruiker geeft expliciet toestemming om het
dashboard-bestand voortaan altijd te overschrijven bij een herstart, op
voorwaarde dat handmatige wijzigingen altijd eerst worden teruggekoppeld
(zodat ze in het sjabloon verwerkt kunnen worden vóórdat een nieuwe
versie wordt uitgebracht).

**Wijziging:** `_copy_dashboard_template_if_missing()` is vervangen door
`_copy_dashboard_template()` — kopieert nu **altijd** het meegeleverde
sjabloon naar `config/energy_management_system_dashboard.yaml`, ook als
het bestand al bestaat.

**Consequentie om te onthouden:** een handmatige aanpassing die niet is
teruggekoppeld, gaat bij de eerstvolgende herstart **verloren**. Dit is
een bewuste, afgesproken trade-off — geef wijzigingen dus altijd door
vóórdat je een nieuwe versie installeert.

Getest (2 bijgewerkte permanente tests): het sjabloon wordt zowel
geplaatst als het ontbreekt, als overschreven als er al iets anders
staat.

## v0.53.0 — dashboard: naam-fix, read-only modus/vermogenslimiet, robuustere tabel, alle tabbladen gemoderniseerd

**Naam-fix:** `sensor.energy_management_system_system_status` →
`sensor.woonkamer_energy_management_system_system_status`.

**Modus-tegel en vermogenslimiet nu duidelijk alleen-lezen.** De
"Werkelijke modus (Zendure)"-tegel toonde voorheen ook een aparte,
interactieve dropdown (`mushroom-select-card`) waarmee je de modus zelf
kon wijzigen — verwarrend, aangezien de integratie dit volledig zelf
regelt. Die losse dropdown is verwijderd; de tegel zelf heeft nu
`tap_action`/`hold_action: none` zodat die niet meer per ongeluk aan te
klikken is. Zelfde behandeling voor de zonnepaneel-vermogenslimiet: was
een interactieve schuifregelaar, nu een platte weergave-tegel.

**Transitielog-tabel robuuster tegen oude/ontbrekende velden.** Gebruikt
nu `.get(...)` met standaardwaarden voor elk veld, zodat een oudere,
onvolledige logboek-vermelding (van vóór een sensortoevoeging) de hele
tabel niet meer kan laten crashen.

**Overige vier tabbladen gemoderniseerd** naar dezelfde
Mushroom-tegel-stijl als het Overzicht-tabblad:
- **Financieel**: gauges/tegels voor totaalwaarden, een 3-koloms-raster
  voor vandaag/week/maand (ontladen én netladen), tegels voor
  tekort-/overschot-dagen (met kleurindicatie).
- **Zelflerend**: gauges voor rendement en PV-afwijking, tegels voor
  verbruiksprofiel/nachtvenster/PV-bias.
- **Apparaten**: tegels voor typische gebruiksuren per apparaat.
- **Geschiedenis**: titel-kaart toegevoegd, logboek-/schema-tabellen en
  geschiedenis-grafieken ongewijzigd qua functie, wel robuuster.

**Ter info, uit de gedeelde logmelding:** de meeste getoonde
sjabloonfouten (vaatwasser/wasmachine Home Connect-kaarten,
slaapkamertemperatuur-styling) horen bij je **andere**, losse
dashboard-kaarten — niet bij deze integratie. Gecontroleerd: geen van
die entiteiten komt voor in ons dashboard-bestand.

## v0.53.1 — dashboard: gauge-crash gefixt, tijdstempel netjes geformatteerd

**Gevonden fout:** "Entiteit is niet-numeriek" op het Zelflerend-tabblad.
Oorzaak: `sensor.pv_forecast_accuracy` en
`sensor.learned_battery_efficiency` retourneren `None` (state "unknown")
totdat er genoeg data is — een `gauge`-kaart kan fundamenteel geen
niet-numerieke state weergeven en crasht daarop. Bij deze gebruiker
toevallig niet zichtbaar voor het rendement (al genoeg data), maar een
sluimerende fout voor elke nieuwe installatie.

**Fix:** alle drie gauge-kaarten voor deze twee sensoren (Overzicht +
Zelflerend, in totaal 3 plekken) vervangen door `mushroom-template-card`-
tegels die "unknown"/"unavailable" netjes afvangen (grijs, geen %-teken)
in plaats van te crashen.

**Ook gefixt:** de tijdstempel onder de systeemstatus-tegel toonde de
ruwe ISO-string inclusief microseconden. Nu netjes geformatteerd via
`as_timestamp` + `timestamp_custom` (bv. "zo 12:59:10").

## v0.53.2 — geleerde geschiedenis nu als nette tabellen i.p.v. ruwe data-dump

**Aanleiding:** de "Geleerde geschiedenis"-kaart toonde ruwe
Python-dict/lijst-representaties (bv. `{'0': 264, '1': 219, ...}`) —
functioneel, maar niet overzichtelijk.

**Omgezet naar vier aparte tabellen met headers:**
- **Verbruiksprofiel per uur** — 24 rijen, "Uur" en "Verbruik (W)".
- **Nachtvenster-gemiddelde** — genummerd 1-7, meest recente nacht
  gemarkeerd.
- **Solcast-nauwkeurigheid per dag** — inclusief de geleerde
  bias als laatste, vetgedrukte rij.
- **PV-voorspelling bias per uur** — alleen uren met data (dus geen lege
  nachtelijke rijen), met een korte uitleg wat de ratio betekent.

## v0.53.3 — tabellen echt gefixt (YAML-vouwing + Jinja bleek subtieler dan gedacht)

**Wat er misging in v0.53.2:** het "verwijderen van lege regels" om de
tabellen compact te maken, brak ze juist volledig — YAML's `>`-vouwstijl
voegt opeenvolgende niet-lege regels samen met een **spatie**, niet een
newline. Zonder lege regels smolten header, scheidingslijn en elke rij
samen tot bijna één lange regel, wat Markdown niet meer als tabel
herkent.

**Correcte oplossing, nu daadwerkelijk end-to-end getest (YAML-parse
gevolgd door Jinja-rendering, exact zoals Home Assistant het doet):**
precies één lege regel op elk punt waar één newline nodig is,
gecombineerd met Jinja's `{%- %}`-whitespace-controle om de eigen
newlines van de `{% for %}`/`{% endfor %}`-tags weg te snijden.

**Bonus: hierbij ook twee tabellen op het Geschiedenis-tabblad gevonden
en gefixt** (transitielogboek en verwacht-schema) die **dezelfde**
onderliggende fout al hadden, nog van vóór dit gesprek — mijn nieuwe
test vond dit automatisch.

**Nieuw: permanente test (`tests/test_dashboard_tables.py`)** die elke
markdown-tabel in het dashboard door de volledige YAML+Jinja-pijplijn
haalt en controleert op (a) geen lege regels tussen tabelrijen, en (b)
header en scheidingslijn altijd op eigen, opeenvolgende regels. Dit
voorkomt dat deze specifieke, subtiele fout ooit nog terugkeert bij een
toekomstige dashboard-wijziging.

## v0.53.4 — gauge terug voor Geleerd rendement (op eigen verzoek)

**Herstart-vraag beantwoord (geen codewijziging):** onderzocht en
bevestigd — een volledige HA-herstart bij elke code-update is een
fundamentele eigenschap van hoe Python module-caching werkt in
combinatie met HACS, en geldt voor vrijwel elke custom integratie in
het hele ecosysteem. "Herladen" ververst alleen de configuratie, niet de
Python-code zelf. Dit is niet iets wat vanuit deze (of enige andere)
integratie op te lossen is.

**Gauge teruggezet** voor "Geleerd rendement" (Overzicht + Zelflerend),
op expliciet verzoek — bewust terug naar de ronde-meter-look, met het
kleine, geaccepteerde risico dat deze kaart tijdelijk kan crashen bij een
gloednieuwe installatie (vóórdat er 3 rendementsmetingen zijn
verzameld). Bij een bestaande installatie met al voldoende data (zoals
deze) speelt dat risico niet.

## v0.54.0 — vorige waarde, procentueel verschil en trendpijl (Zelflerend-tabblad)

**Aanleiding:** de wens om voor de zelflerende cijfers de vorige waarde,
het verschil en een pijl (↑/↓/→) te zien.

**Drie sensoren hadden al een expliciete geschiedenis-lijst — direct
uitgebreid, zonder Python-wijzigingen:**
- **Geleerd rendement** — nieuwe trend-tekstkaart naast de gauge
  (Overzicht + Zelflerend), gebruikt de bestaande `history`-lijst.
- **Solcast-nauwkeurigheid per dag** — nieuwe "Verschil"-kolom in de
  tabel (procentpunt-verschil met de vorige dag).
- **Nachtvenster-gemiddelde** — nieuwe "Verschil"-kolom (W-verschil met
  de vorige nacht).

**Twee sensoren waren doorlopend bijgewerkte voortschrijdende
gemiddelden zonder los "vorige waarde"-concept — hiervoor is een kleine
Python-uitbreiding gebouwd:**
- Nieuwe coordinator-methoden `previous_hourly_avg_kw(hour)` en
  `previous_pv_hourly_ratio(hour)` — berekenen het gemiddelde
  **exclusief** de meest recente meting, zodat er alsnog een zinvolle
  "vorige waarde" is om mee te vergelijken.
- Nieuwe sensor-attributen `previous_profile_watts`
  (verbruiksprofiel-sensor) en `previous_profile` (PV-bias-sensor).
- Beide tabellen (Verbruiksprofiel per uur, PV-bias per uur) hebben nu
  ook een "Verschil"-kolom.

**Getest:** 4 nieuwe permanente tests voor de nieuwe helper-methoden,
plus alle dashboard-tabellen opnieuw end-to-end (YAML+Jinja) gevalideerd
met de uitgebreide testdata.

**Bijwerking:** de tabellen voor verbruiksprofiel-per-uur en
PV-bias-per-uur tonen nu alleen uren **met** data (geen "—"-plaatshouder
meer voor lege uren) — logischer nu er ook een verschil-kolom bij komt.

## v0.55.0 — %-teken i.p.v. "pp", en een logischere dashboard-indeling

**%-teken:** alle "procentpunt"/"pp"-labels (trend-indicatoren,
Solcast-verschil-kolom) vervangen door een gewoon %-teken, zoals
gevraagd.

**Logischere indeling.** De vorige lay-out gebruikte een standaard
"masonry"-view — Home Assistant herschikt kaarten daarin automatisch
over kolommen op basis van hoogte, wat de bedoelde volgorde behoorlijk
kon door elkaar husselen (zoals zichtbaar in de gedeelde screenshot).

**Fix: het Overzicht-tabblad gebruikt nu `type: sections`** (HA's
nieuwere, expliciete layout-systeem) met 7 duidelijk gescheiden,
getitelde groepen, in deze vaste volgorde:
1. Status (titel + systeemstatus)
2. Accu & rendement (beide gauges + trend)
3. Live cijfers (beschikbare energie, verbruik, prijs)
4. Modus & besluit (werkelijke/verwachte modus, dure kwartieren,
   zonnepaneel-limiet)
5. Besturing (de drie schakelaars)
6. Wat gebeurt er nu, en waarom (uitleg)
7. Actuele beslissing (detail)

Deze volgorde ligt nu vast — geen automatische herschikking meer.

## v0.55.1 — Overzicht-tabblad verder verfijnd: minder lege ruimte, gauges gehalveerd

**Drie punten opgepakt:**

1. **"Wat gebeurt er nu, en waarom?"** staat nu direct in de eerste
   sectie, meteen onder de status — niet meer onderaan.
2. **Gauges nemen minder ruimte in** — Accu SoC en Geleerd rendement
   staan nu **naast elkaar** (elk de halve breedte) in plaats van
   gestapeld op volle breedte.
3. **Minder lege vakken** — elke kaart heeft nu een expliciete
   `grid_options`-breedte (in HA's 12-koloms sectie-raster), zodat
   secties met 3 of 4 kaarten precies de volledige breedte vullen in
   plaats van een leeg gat over te laten.

Structuur nu: Status + uitleg → Accu & rendement (compact) → Live
cijfers → Modus & besluit → Besturing → Actuele beslissing (detail).

## v0.55.2 — transitielogboek beperkt tot laatste 10 rijen

De "Overgangen energie-check"-tabel toonde tot nu toe de volledige
opgeslagen geschiedenis (tot 50 vermeldingen). Nu beperkt tot de
**laatste 10** (meest recent bovenaan), voor een overzichtelijker
tabblad. De onderliggende opslag (max. 50) blijft ongewijzigd — alleen
de weergave in het dashboard is beperkt.

## v0.55.3 — tegels breder, niet meer afgekapt

**Aanleiding:** de tegels in "Live cijfers" (3 naast elkaar,
`columns: 4`) en "Modus & besluit" (4 naast elkaar, `columns: 3`) waren
te smal, waardoor tekst werd afgekapt ("7.603...", "S...", "1...").

**Fix:** alle acht tegels in deze twee secties verbreed naar
`columns: 6` — nu twee per rij in plaats van drie of vier, met genoeg
ruimte voor de volledige tekst.

## v0.56.0 — maandelijkse samenvatting: echte langetermijntrend

**Aanleiding:** de vraag hoe het systeem zichzelf over de langere termijn
evalueert. Eerlijk antwoord destijds: de bestaande zelfcorrectie kijkt
alleen naar een rollend venster van 7 dagen — er was geen manier om
maand-op-maand te vergelijken.

**Nieuw: `sensor.monthly_summary`.** State = netto resultaat deze maand
tot nu toe (ontladen-waarde minus netlaadkosten). Attributen bevatten de
volledige vergelijking:
- `current_month_discharge_value_eur`, `current_month_charge_cost_eur`
- `current_month_shortfall_days`, `current_month_excess_days`
- `previous_month_*` (dezelfde velden, van de vorige volledige maand)
- `previous_month_net_eur`

**Werking:** nieuwe methode `_check_monthly_rollover()` detecteert een
kalendermaand-wisseling, legt dan de huidige maand-totalen vast als
"vorige maand" en reset de tellers voor de nieuwe maand. De bestaande
financiële tracking en dag-afsluiting (tekort/overschot) voeden nu ook
deze maandelijkse tellers, naast de bestaande cumulatieve/rollende
tellers.

**Dashboard:** nieuwe kaart op het Financieel-tabblad, met trendpijl
t.o.v. dezelfde periode vorige maand.

Getest (4 nieuwe permanente tests): eerste keer geen "vorige maand",
correcte snapshot-en-reset bij een maandwisseling, geen wisseling binnen
dezelfde maand, en correcte doorvoer vanuit de financiële tracking.

**Blijft bewust beperkt:** dit toont een directe maand-op-maand
vergelijking, geen seizoensanalyse of "bespaart dit systeem mij geld
t.o.v. geen integratie" — dat laatste vereist een contrafeitelijke
vergelijking die niet eerlijk te verifiëren is.

## v0.56.1 — "Verschil"-kolom reset niet meer na elke herstart

**Gevonden:** de "Verschil" (trend)-kolommen voor verbruiksprofiel-per-uur
en PV-bias-per-uur toonden na elke herstart "—" voor alle uren, ook al
was er al weken aan geleerde data.

**Oorzaak:** bij herstel na een herstart wordt alleen het **gemiddelde**
per uur teruggezet, als één enkele waarde — niet de onderliggende reeks
metingen. Aangezien "vorige waarde" minstens 2 metingen nodig heeft om
iets te kunnen berekenen, bleef dit na elke herstart leeg totdat er
weer nieuwe, echte metingen binnenkwamen.

**Fix:** de herstelde waarde wordt nu **tweemaal** opgeslagen (als twee
identieke metingen). Direct na een herstart toont "Verschil" daardoor
"→" (geen verandering) in plaats van "—", en zodra er ook maar **één**
nieuwe, echte meting binnenkomt, verschijnt meteen een zinvol verschil.

Getest (3 nieuwe permanente tests): direct na herstel is "vorige" gelijk
aan "huidig" (geen onbeschikbaar meer), en na één nieuwe meting toont
het verschil correct.

## v0.57.0 — mediaan i.p.v. gemiddelde: oven/Quooker-pieken volledig genegeerd

**Terechte vraag:** waarom schiet het basisverbruik omhoog na de oven of
Quooker, terwijl 2000W voor 2 minuten nauwelijks energie is?

**Gevonden, echt ontwerpprobleem:** onze demping (v0.48.0) gebruikte het
**gemiddelde** van de laatste 4 metingen (~20 minuten). Als een korte
apparaat-piek (oven/Quooker, 2000W gedurende 1-2 minuten terwijl het
verwarmingselement cyclisch aan/uit schakelt) toevallig precies binnen
één 5-minuten-meting viel, werd bijvoorbeeld `[400, 400, 400, 2000]` →
**gemiddelde 800W** — een verdubbeling die vervolgens over de hele
resterende overbruggingsperiode (soms 12+ uur) werd doorgerekend. Voor
een gebeurtenis van een paar minuten volstrekt onevenredig.

**Fix:** de **mediaan** van de laatste 4 metingen in plaats van het
gemiddelde. Bij `[400, 400, 400, 2000]` is de mediaan gewoon 400W — de
uitschieter wordt volledig genegeerd. Een écht aanhoudende verandering
(airco, minstens 2 van de 4 metingen verhoogd) wordt nog steeds volledig
herkend.

Getest (bijgewerkt + 1 nieuwe permanente test): een geïsoleerde piek
(zelfs een extreme van 9000W) geeft nu exact hetzelfde resultaat als
geen piek (1,0x, geen correctie) — voorheen nog altijd afgetopt op 5x.
Een aanhoudende verandering (2 van de 4 metingen verhoogd, zoals de
airco net na het aanslaan) blijft volledig herkend op 2,0x.

## v0.57.1 — kritieke inconsistentie gefixt: laden-uitstellen-beslissing gebruikte nog de oude, minder veilige reserve-berekening

**Wat opviel:** "geschat nodig: 0.00 kWh" in de uitleg, terwijl de
opsplitsing liet zien dat basisverbruik (5.356 kWh) en verwachte zon
(5.78 kWh) elkaar bijna precies opheften.

**Gevonden, belangrijke inconsistentie:** de diepste-tekort-reserve
(v0.43.0) — specifiek gebouwd om te voorkomen dat veel verwachte zon
een reëel nachtelijk tekort kan verbergen — was alleen gekoppeld aan de
**ontlaad-vermogen-begrenzing**, niet aan de **laden-uitstellen-
beslissing** zelf (`_should_postpone_charging`). Die gebruikte nog
steeds de oude, simpele netto-berekening (basisverbruik minus zon over
de hele periode, geklemd op 0) — exact het soort berekening waarvan we
al hadden vastgesteld dat die een nachtelijk tekort kan verbergen.

**Fix:** `_should_postpone_charging` gebruikt nu ook de
diepste-tekort-berekening als de daadwerkelijke beslissingsgrondslag.
Basisverbruik en verwachte zon blijven zichtbaar in de opsplitsing, maar
puur als informatieve context — niet meer als de berekening die de
beslissing aanstuurt. Het veld `reservering_dure_kwartieren_kwh` (altijd
0, sinds v0.41.0 toch al overbodig) is vervangen door
`diepste_tekort_kwh`, en de uitleg-tekst is hierop aangepast.

**Getest** (nieuwe permanente test): een scenario waarin de oude
netto-methode ~0 kWh zou tonen (basisverbruik < verwachte zon) geeft nu
via de diepste-tekort-berekening een reëel, positief tekort — en dat
getal komt nu ook daadwerkelijk terecht in de opsplitsing die de
beslissing aanstuurt, niet alleen in een aparte weergave.

**Dit is waarschijnlijk relevanter dan het lijkt:** dit betekent dat de
"laden uitstellen ten gunste van teruglevering"-beslissing voorheen te
optimistisch kon zijn op precies de dagen met veel verwachte zon —
exact het scenario waar de bescherming het hardst nodig is.

## v0.58.0 — secundaire prijslaag: spare headroom niet meer onbenut

**Aanleiding:** een dag met 7,60 kWh beschikbaar, waarvan maar 15
minuten daadwerkelijk werd verkocht (tegen €0,4177), terwijl de
omringende kwartieren (€0,33-0,38) — met duidelijk nog ruimte over in de
accu — onbenut bleven.

**Ook opgehelderd:** de "Boven dynamische prijsdrempel"-teller (8
kwartieren) leek niet te kloppen met het schema (1 kwartier) — bleek een
schijnbare inconsistentie: die teller telt de **hele kalenderdag**
(inclusief al gepasseerde uren), het schema toont alleen wat nog **komt**.
Verduidelijkt in het dashboard.

**De echte verbetering: een tweede, ruimere prijslaag.** Naast de
bestaande strikte drempel (top 20% van de dagprijs-range) is er nu een
**secundaire, ruimere drempel** (top 45%) die ook mag verkopen — maar
uitsluitend met **spare headroom**: wat overblijft nadat alle nog
resterende, écht dure (primaire) kwartieren van vandaag al zijn
gereserveerd. Deze laag kan dus **nooit** ten koste gaan van de
bescherming voor de echte piek of de nachtelijke reserve — hij vult
alleen aan wat toch al onbenut zou blijven.

**Nieuwe functies:**
- `_get_secondary_expensive_price_threshold()` — de ruimere drempel.
- `_get_spare_headroom_after_primary_tier_kwh()` — hoeveel headroom
  overblijft na de primaire kwartieren.
- `_is_worth_discharging_at_secondary_tier()` — prijs-prioriteit binnen
  de secundaire laag, zelfde principe als de bestaande primaire
  prijs-prioriteit (v0.40.0).

Ingehaakt in de hoofdbeslisboom: als een kwartier de strikte drempel
niet haalt, wordt nu ook gecontroleerd of het de secundaire drempel wél
haalt én er spare headroom is — zo niet, blijft het gedrag exact zoals
voorheen.

**Getest (4 nieuwe permanente tests):** secundaire laag wordt gebruikt
bij ruime headroom, niet gebruikt als de headroom al nodig is voor de
échte piek, nooit van toepassing onder de secundaire drempel zelf (ook
niet bij extreem veel headroom), en spare headroom is terecht 0 als de
primaire laag alles al opeist.

## v0.58.1 — planningstabel toont nu ook de secundaire prijslaag

**Gevonden bij analyse van een verse diagnostiek-export:** de secundaire
laag (v0.58.0) werkte correct in de **live beslissing** (bevestigd:
`last_reason: expensive_quarter` tijdens het huidige kwartier), maar de
**planningstabel** (Overzicht komende uren) bleef toekomstige
secundaire-laag-kwartieren tonen als "smart" — omdat
`_build_forecast_timeline` alleen ooit de primaire drempel checkte, nooit
de secundaire laag of de spare headroom die daarna overblijft.

**Fix:** dezelfde spare-headroom-simulatie die de live beslissing al
gebruikt, is nu ook in de planningsprojectie ingebouwd. Na het simuleren
van de primaire-laag-kwartieren per dag, wordt eventuele resterende
headroom nu ook besteed aan secundaire-laag-kwartieren, in dezelfde
prijs-prioriteit-volgorde.

**Getest** (1 nieuwe permanente test, exact het gerapporteerde scenario
nagebouwd): de planning toont nu correct extra "manual"-kwartieren rond
de piek (20:15-20:45, eerder onterecht "smart"), naast het bestaande
piek-kwartier zelf.

## v0.59.0 — ontlaadvermogen zakt niet meer onder het huishoudverbruik

**Gerapporteerd:** rond 22:00 schakelde de modus naar `manual` (een
geldig `expensive_quarter`-kwartier), maar het toegepaste ontlaadvermogen
kwam uit op slechts ~150W terwijl de woning ~340W verbruikte — het
verschil (~190W) werd geïmporteerd, tegen dezelfde piekprijs waarop net
was besloten te gaan verkopen.

**Root cause:** `_get_soc_scaled_discharge_power()` schaalt het
ontlaadvermogen naar de *headroom* (beschikbare energie min de
nachtreserve), niet naar het actuele huishoudverbruik. Terugrekenen
vanuit de gerapporteerde 150W (bij `manual_discharge_power` = 1600W, 5
min interval) gaf een headroom van slechts ~12,5 Wh — bevestigd met een
"Beschikbare Energie"-geschiedenisgrafiek die rond dat tijdstip ~5,7-5,8
kWh liet zien, bijna gelijk aan de berekende reserve. De schaling deed
dus precies wat hij moest doen (nachtreserve beschermen), maar dat is
tijdens een reeds-actief verkoop-kwartier de verkeerde afweging: minder
verkopen dan het huisverbruik betekent alsnog importeren, tegen dezelfde
piekprijs, in hetzelfde kwartier.

**Fix:** een ondergrens toegevoegd op basis van het live, gecorrigeerde
huishoudverbruik (`_read_corrected_consumption_power()`, bestond al voor
de mediaan-smoothing van v0.57.0). Het toegepaste ontlaadvermogen zakt
nu nooit meer onder het actuele huisverbruik, begrensd door wat fysiek
beschikbaar is in deze tick (`available_kwh` / interval) en door
`manual_discharge_power` als plafond. Geldt zowel wanneer de
headroom-schaling een te lage waarde geeft als wanneer de headroom
volledig op is (voorheen: geen geforceerde ontlading). De
prijs-prioriteit-logica (welk kwartier het bést is om in te verkopen,
v0.40.0) blijft ongewijzigd — dit raakt alleen hoeveel er wordt verkocht
zodra een kwartier al gekozen is.

**Getest** (5 nieuwe permanente tests): headroom te laag → opgehoogd tot
huisverbruik; headroom volledig op → toch dekking i.p.v. skip; vloer
nooit hoger dan fysiek beschikbare energie; ruime headroom → ongewijzigd
gedrag (regressietest); geen verbruikssensor geconfigureerd → ongewijzigd
gedrag (regressietest).

## v0.59.1 — vloer-toepassingen zichtbaar in de diagnostiek-export

**Aanleiding:** om een volgend geval van de v0.59.0-situatie te kunnen
beoordelen was tot nu toe een los uit HA getrokken geschiedenisgrafiek
nodig ("Beschikbare Energie") — omdat de diagnostiek-export een
momentopname is, miste die het moment zelf als er niet toevallig net op
dat tijdstip werd geëxporteerd.

**Toegevoegd aan `coordinator` (state) en diagnostiek:**
- `last_household_load_w` — laatst gemeten, gecorrigeerd huishoudverbruik
  bij de meest recente ontlaad-berekening.
- `last_discharge_floor_applied` — of de vloer op de laatste tick
  daadwerkelijk iets heeft opgehoogd.
- `discharge_floor_events` — bijgehouden log (laatste 50, zelfde patroon
  als `energy_bridge_transition_log`) met per gebeurtenis: tijdstip,
  huishoudverbruik, wat de headroom-schaling zou hebben gegeven, wat er
  uiteindelijk is toegepast, en de onderliggende `available_kwh`/
  `reserve_kwh`. Wordt alleen gelogd wanneer de vloer de headroom-schaling
  daadwerkelijk overstijgt — niet elke tick.

**Getest** (1 nieuwe permanente test): een vloer-toepassing wordt
gelogd, staat in `discharge_floor_events`, en de volledige
diagnostiek-export blijft JSON-serialiseerbaar.

## v0.60.0 — bredere diagnostiek-uitbreiding: meer beslispunten zichtbaar

**Aanleiding:** meerdere beslispunten in de hoofdboom werden tot nu toe
alleen via `_LOGGER.debug` gelogd — onzichtbaar zodra een diagnostiek-
export wordt gedeeld zonder dat er live wordt meegekeken in de HA-logs.
Dit maakte eerdere analyses (zoals v0.59.0) trager dan nodig: er moest
telkens los uit HA een geschiedenisgrafiek worden getrokken om te
reconstrueren wat er was gebeurd.

**Vijf nieuwe velden in `coordinator`-state en diagnostiek:**
- **`last_expensive_tier`** (`"primary"` | `"secondary"` | `null`) — of
  het huidige/laatste verkoop-besluit via de strikte primaire drempel
  (top 20%) of de ruimere secundaire laag (top 45%, v0.58.0) tot stand
  kwam. Voorheen alleen af te leiden uit prijs + drempel-berekeningen
  achteraf.
- **`last_price_priority_held_off`** — of de prijs-prioriteit-logica
  (v0.40.0) een kwartier bewust heeft overgeslagen omdat de beperkte
  headroom beter besteed is aan een duurder kwartier later die dag. Dit
  verklaart het "waarom staat de modus op smart terwijl is_expensive
  eigenlijk True was"-scenario.
- **`last_used_soc_taper_fallback`** — of de primitievere platte
  SoC-percentage-aftopping is gebruikt in plaats van de
  diepste-tekort-reserve-berekening (gebeurt als er geen
  `available_energy`-sensor is geconfigureerd, of de reserve die tick
  niet berekend kon worden). Nuttig om configuratie- of
  sensor-problemen te signaleren.
- **`last_reserve_margin_breakdown`** — de volledige opbouw van de
  veiligheidsmarge op de nachtreserve: basispercentage, lage-zon-bonus
  (+ aantal dagen), tekort-bonus (+ aantal recente tekortdagen),
  overschot-reductie (+ aantal recente overschotdagen), de vaste
  "onbeschermde nasleep"-marge, en het totaal — plus de kWh vóór en ná
  marge. Voorheen alleen zichtbaar als een `_LOGGER.debug`-regel wanneer
  de bonus niet 0 was.
- **`last_winter_guard_suppressed_today`** — of de winter-guard
  (v0.27.0) vandaag een verkoop heeft onderdrukt omdat er die dag al
  netgeladen is. Reset bij een nieuwe dag, net als `grid_charged_today`.

**Getest** (7 nieuwe permanente tests, verdeeld over
`test_decision_visibility.py` en een uitbreiding van
`test_winter_guard_and_emergency_charge.py`): primaire vs. secundaire
laag correct geregistreerd, prijs-prioriteit-hold-off geregistreerd,
SoC-taper-fallback-vlag correct gezet en weer gewist zodra de dynamische
tak weer bruikbaar is, marge-breakdown correct gevuld, en de
winter-guard-vlag zet en reset op de juiste momenten.

## v0.60.1 — "Verschil"-trend in de dashboardtabellen overleeft een herstart niet echt

**Gerapporteerd:** na een herstart toonden zowel "PV-voorspelling bias
per uur" als "Verbruiksprofiel per uur" voor elk uur `+0` / `+0.000` in
de Verschil-kolom.

**Root cause:** dit was deels bewust gedrag uit v0.56.1 — bij een
herstart wordt alleen het **gecollapste gemiddelde** per uur
gepersisteerd (in de `profile`-attribute), niet de onderliggende losse
dagwaarden. Om te voorkomen dat de Verschil-kolom "-" toont totdat er
weer twee samples zijn, werd dat ene herstelde gemiddelde **dubbel**
opgeslagen (previous == current), wat een genuine "+0,000" oplevert. Dat
is op zich geen foute data, maar het betekent wél dat de **echte**
dag-op-dag-trend van vóór de herstart verloren gaat, en dat elk uur
afzonderlijk pas weer een echte trend toont zodra dat specifieke
uur-van-de-dag opnieuw wordt doorlopen (tot ~24 uur later). Bij
meerdere herstarts op één dag (zoals vandaag, voor v0.59.0/v0.59.1/
v0.60.0) blijft de kolom daardoor voortdurend op nul staan.

**Fix:** naast de bestaande `profile`-attribute wordt nu ook de volledige
onderliggende lijst per uur gepersisteerd (`profile_history`, max
`LEARNING_HISTORY_DAYS` = 7 waarden per uur — verwaarloosbaar qua
grootte). Bij het herstellen wordt deze volledige historie gebruikt
wanneer aanwezig, zodat de échte trend van vóór de herstart intact
blijft. Blijft achterwaarts compatibel: state opgeslagen door een oudere
versie (zonder `profile_history`) valt terug op de oude
dubbele-waarde-aanpak.

**Getest** (4 nieuwe permanente tests): volledige historie wordt
hersteld en toont direct een échte previous/current-afwijking; oude
state zonder `profile_history` valt terecht terug op de
dubbele-waarde-aanpak; zelfde voor de PV-bias-sensor.

## v0.61.0 — de uitlegtekst zegt nu ook wáárom, niet alleen wát

**Aanleiding:** de tekstsensor liet zien dat het "smart" was, met als
uitleg "de prijs is niet bijzonder hoog" — te generiek om te kunnen
beoordelen of dat klopte. Moest geraden worden (bijv. "vermoedelijk
vanwege weinig zon vandaag") in plaats van afgelezen.

**Wat er nu bij staat, per situatie:**
- **`default_smart` (geen speciale reden):** toont nu de **werkelijke
  prijs vs. de dynamische drempel voor 'duur' vandaag** (bijv. "€0,339
  haalt de drempel van €0,378 niet"), en vermeldt expliciet als die
  drempel vandaag **strenger staat omdat er weinig zon wordt verwacht**
  (top 8% i.p.v. top 20% van de prijsrange) — dus je hoeft niet meer te
  gokken of dat de reden was. Vermeldt ook de secundaire drempel, en of
  de winter-guard vandaag al een verkoop heeft onderdrukt.
- **`expensive_quarter`:** vermeldt nu of het kwartier via de **primaire**
  of **secundaire** prijslaag kwalificeerde, en of het toegepaste
  vermogen is opgehoogd door de huishoudverbruik-vloer (v0.59.0).
- **`expensive_quarter_soc_protected`:** **bugfix in de tekst zelf** — dit
  label wordt namelijk gebruikt in twee heel verschillende gevallen (te
  lage SoC, **of** prijs-prioriteit die bewust wacht op een duurder
  kwartier later), maar de tekst zei tot nu toe altijd "de accu-SoC is
  te laag", ook wanneer de SoC prima was en het eigenlijk om
  prijs-prioriteit ging. Onderscheidt dit nu correct met de
  `last_price_priority_held_off`-vlag uit v0.60.0.

**Drie nieuwe coordinator-velden** (ook in diagnostiek):
`last_expensive_price_threshold`, `last_secondary_price_threshold`,
`last_low_solar_narrowed_threshold`. Daarnaast staat `last_explanation`
zelf nu ook in de diagnostiek-export (stond er tot nu toe niet in,
alleen op het dashboard).

**Getest** (8 nieuwe permanente tests in `test_explanation_text.py`):
prijs-vs-drempel-tekst, lage-zon-vermelding, winter-guard-vermelding,
nette fallback zonder prijsspreiding, correcte onderscheiding
SoC-bescherming vs. prijs-prioriteit in beide richtingen, vermelding van
de gebruikte prijslaag, en vermelding van de huishoudverbruik-vloer.

## v0.61.1 — icoon-samenvatting boven de uitlegtekst op het dashboard

**Verzoek:** de cruciale waarden achter de uitleg (tijd, force manual,
modus, prijs, drempel) los en met icoontjes bovenaan de uitlegkaart,
met de bestaande volledige tekst er direct onder — naar het voorbeeld
van een vergelijkbaar overzichtskaartje.

**`ExplanationSensor` (sensor.py):** exporteert nu naast de bestaande
`explanation`-attribute ook de losse waarden erachter als eigen
attributen: `last_successful_update`, `force_manual`, `expected_mode`,
`current_price_per_kwh`, `expensive_price_threshold`,
`secondary_price_threshold`, `effective_expensive_quarters_count`. Zo
hoeft het dashboard niet meerdere andere entiteiten te combineren of de
prozatekst te parsen.

**Dashboard:** de uitlegkaart (`dashboard_template.yaml` en de
gesynchroniseerde kopie in `dashboards/`) toont nu bovenaan een
icoon-per-regel samenvatting (🕐 Tijd, 🔒 Force manual, ⚙️ Actuele
modus, 💰 Actuele kwartierprijs, 📈 Drempel 'duur' vandaag, 🎯 Dure
kwartieren vandaag), gevolgd door een `---`-scheiding en daaronder de
volledige, ongewijzigde uitlegtekst zoals voorheen. De kaart is
overgezet van YAML's folded (`>`) naar literal (`|`) block-stijl voor
dit specifieke kaartje — voorkomt exact het soort fold-gerelateerde
opmaakverrassingen waar `test_dashboard_tables.py` al eerder voor is
gebouwd, door de regel-einden hier expliciet zelf te bepalen in plaats
van op YAML's folding-regels te vertrouwen.

**Getest** (2 nieuwe permanente tests voor de sensor-attributen, plus
uitgebreide fake-testdata in de bestaande
`test_dashboard_tables.py`-pijplijn zodat deze kaart nu ook echt
gerenderd wordt gecontroleerd op geldige YAML + Jinja).

## v0.61.2 — diepste-tekort-berekening als tabel i.p.v. dichte zin

**Aanleiding:** de zin "tegenover 1,415 kWh basisverbruik en 3,805 kWh
verwachte zon over de hele periode" oogde ongeloofwaardig totdat de
exacte periode (nu → goedkoopste blok) met de hand werd
gereconstrueerd uit een losse diagnostiek-export. Bij nacontrole klopten
beide getallen exact (basisverbruik matcht het geleerde profiel +
live-correctie; zon komt overeen met ~18,6% van de dagvoorspelling in
dat tijdvak) — het probleem zat dus puur in de leesbaarheid van de
tekst, niet in de berekening zelf.

**Fix:** `_build_needed_kwh_breakdown_table()` (coordinator.py) zet deze
breakdown nu om in een echte Markdown-tabel, met de periode expliciet
uitgeschreven (start, eind, duur — bijv. "nu (08:32) → 11:29 (2u57m)")
in plaats van de vage formulering "over de hele periode". Gebruikt in
zowel de `discharging_window`- als de `default_smart`-uitleg (beide
gebruiken dezelfde breakdown-data). Omdat de uitlegtekst al rechtstreeks
als Markdown wordt gerenderd in de dashboardkaart (sinds v0.61.1), komt
dit vanzelf als een nette tabel op het scherm - geen dashboard-aanpassing
nodig.

**Getest** (2 nieuwe permanente tests): tabel bevat header, scheidingsregel
en rijen zonder tussenliggende lege regels (zelfde regel als
`test_dashboard_tables.py` al afdwingt voor de statische dashboard-YAML),
en de fallback naar "onbekend" werkt correct wanneer er geen
goedkoopste-blok-tijdstip bekend is.

## v0.61.3 — dashboard compacter: minder lege ruimte

**Aanleiding:** de eerste kolom (Energy Management System) werd door de
grote uitlegkaart (icoon-samenvatting + tabel + tekst) veel hoger dan de
kolommen ernaast (Accu & rendement, Live cijfers, Modus & besluit) - de
volgende rij secties (Besturing, Actuele beslissing) start pas na de
hoogte van de hoogste kolom in de vorige rij, dus die extra hoogte werd
puur verloren witruimte.

**Wijzigingen:**
- De titel-kaart en de status-kaart delen nu één rij (8 + 4 kolommen)
  in plaats van elk een eigen volle rij - scheelt een regel hoogte.
- De icoon-samenvatting (v0.61.1) is omgezet van 6 losse, door lege
  regels gescheiden alinea's naar een compacte 2-koloms tabel (3 rijen)
  - ongeveer de helft van de eerdere hoogte voor hetzelfde aantal
    waarden.

**Onderweg gevonden en gefixt:** de lege kop-cellen (`|  |  |`) van die
nieuwe tabel bleken per ongeluk te matchen met de regex die
`test_dashboard_tables.py` gebruikt om scheidingsregels (`|---|---|`) te
herkennen — met een lege koprij ontstaat een tweede "match", waarna de
test via een omslachtige `lines[idx - 1]`-vergelijking (Python's
negatieve index-wraparound) de láátste regel van de kaart als
"voorafgaande regel" pakte in plaats van de echte koprij, en zo ten
onrechte faalde. Opgelost door de koprij een niet-blanco (maar visueel
onopvallend) `—`-teken te geven in plaats van lege cellen.

**Getest:** bestaande dashboard-testpijplijn (YAML + Jinja-rendering)
blijft groen; geen nieuwe tests nodig, het is dezelfde kaart met dezelfde
databronnen, alleen compacter opgemaakt.

## v0.61.4 — titel/status-samenvoeging uit v0.61.3 teruggedraaid

**Gerapporteerd:** de titelkaart en statuskaart naast elkaar op 8+4
kolommen zag er kapot uit - de ondertitel-tekst ("Reden laatste
beslissing: ...") wrapt naar een tweede regel die niet in de
`rows: 1`-hoogte past, en overlapt zichtbaar met de tabel eronder
("Energy Management Systeem" werd afgekapt tot "Energy Management" met
de tabel er half overheen).

**Fix:** titelkaart en statuskaart terug naar elk hun eigen volle rij
(12 kolommen), zoals vóór v0.61.3. De andere compacte wijziging uit
v0.61.3 (de icoon-samenvatting als 2-koloms tabel i.p.v. 6 losse
alinea's) blijft staan - die leverde de daadwerkelijke hoogtewinst op
zonder dit probleem.

**Les:** twee kaarten naast elkaar proppen op basis van geschatte
tekstbreedte is fragiel zodra de inhoud (hier: de "reason"-sensor se
naam) langer is dan getest - een kleinere, voorspelbare wijziging
(alleen de tabel) was hier de betere afweging geweest dan beide
tegelijk. Geen aparte tests aan toegevoegd, dit is puur een layout-
terugdraai naar een eerder bevestigd werkende staat.

## v0.62.0 — geleerd uurprofiel & PV-bias: mediaan i.p.v. gemiddelde

**Vraag:** hoe wordt omgegaan met een uitschieterdag - een regenbui die
de zon plots wegneemt, of de wasmachine die op één dag drie keer draait?

**Antwoord vóór deze versie:** twee gescheiden lagen. (1) Het live
moment zelf was al beschermd (mediaan van de laatste 4 metingen, ~20
min, afgetopt op 5x - sinds v0.57.0) tegen een korte piek die dezelfde
avond nog een projectie zou verpesten. Maar (2) de **langetermijn**-
leerdata (het 7-daagse uurprofiel en de PV-uur-bias) gebruikte gewoon
het **gemiddelde** over de laatste `LEARNING_HISTORY_DAYS` (7) dagen -
een uitschieterdag telde daar gewoon 1/7 mee, zonder filtering, tot hij
na een week vanzelf uit het venster viel.

**Afweging en besluit:** overgestapt op **mediaan** voor beide
leerreeksen. Een enkele uitschieterdag heeft nu vrijwel geen invloed
(pas als een meerderheid van de 7 dagen het nieuwe niveau bevestigt,
verschuift de mediaan mee). Het risico dat dit een échte, structurele
verandering te traag oppikt (thuiswerken, seizoensovergang) wordt al
opgevangen door het bestaande zelfcorrigerende marge-mechanisme
(`reserve_shortfall_history`) aan de veiligheidskant, en seizoenverloop
in zonopbrengst is sowieso te traag om een paar dagen vertraging te
voelen.

**Gewijzigde functies:** `learned_hourly_avg_kw`,
`previous_hourly_avg_kw`, `learned_pv_hourly_ratio`,
`previous_pv_hourly_ratio`, `raw_pv_hourly_avg` - stuk voor stuk van
`sum(values) / len(values)` naar `statistics.median(values)`.

**Bijwerking van een bestaande test:** de v0.56.1-restore-fallback
(dupliceert bij een herstart van vóór v0.60.1 de herstelde waarde
tweemaal, zodat er meteen een "vorige" waarde is) kreeg met een mediaan
een subtiele bijwerking - de dubbele oude waarde heeft nu 2 stemmen
tegen 1 nieuwe meting, dus is er na een herstart **één meting extra**
nodig voordat de trend zichtbaar verschuift (was: al na de eerste
nieuwe meting). Geldt alleen voor state van vóór v0.60.1 tijdens de
overgang; de huidige `profile_history`-restore (v0.60.1) heeft dit
probleem niet, want die herstelt de échte historie.

**Getest** (5 nieuwe permanente tests in
`test_outlier_resistant_learning.py`, 1 bestaande test bijgewerkt):
een enkele uitschieterdag beweegt de mediaan niet noemenswaardig (zowel
voor verbruik als PV-bias); een échte structurele verandering komt wél
door zodra een meerderheid van de 7 dagen het bevestigt; een verandering
die nog geen meerderheid heeft, beweegt de mediaan terecht nog niet; en
de "vorige"-trendwaarde gebruikt dezelfde mediaan-aggregatie als de
huidige waarde.

## v0.63.0 — grootverbruiker-bevestiging omzeilt mediaan-vertraging

**Aanleiding:** een herfstavond waarop de airco onregelmatig op
verwarmen gaat (bijv. maandag wel, dinsdag/woensdag niet, donderdag
weer wel) is precies het soort patroon waar de 7-daagse mediaan
(v0.62.0) terecht sceptisch over blijft — het wordt nooit een
meerderheid van de week, dus het geleerde profiel leert dit patroon
bewust niet aan. Voor de reserve die diezelfde avond nog moet kloppen is
dat te traag: de live-correctie (mediaan van de laatste 4 metingen, ~20
min) heeft eerst meerdere ticks nodig om een echte, aanhoudende
verbruiksverhoging te "geloven" — dezelfde voorzichtigheid die een
Quooker-tik van een paar minuten terecht negeert, vertraagt nu ook een
legitieme airco-avond.

**Oplossing:** als een bekende grootverbruiker via zijn **eigen
entiteit bevestigt** dat hij actief is, is die onzekerheid weg - dan
wordt de live meting direct vertrouwd, zonder op de mediaan te wachten.

**Nieuwe optionele configuratievelden** (Instellingen → dit apparaat →
Configureren): Quooker-vermogen-sensor en airco-climate-entiteit.
Vaatwasser en wasmachine hergebruiken de al bestaande
vermogen-sensoren uit de apparaat-bewustzijn-functie (v0.47.0) - geen
nieuwe configuratie nodig voor die twee.

**Per apparaat:**
- **Vaatwasser / wasmachine:** vermogen boven `APPLIANCE_RUNNING_POWER_THRESHOLD_W`
  (15W, dezelfde drempel als de bestaande gebruiksdetectie) → direct bevestigd.
- **Quooker:** zelfde drempel, maar moet minstens `QUOOKER_SUSTAINED_MINUTES`
  (2 minuten) **aanhoudend** actief zijn. Een enkele korte tik blijft
  bewust genegeerd - dat was namelijk precies de reden waarom de
  mediaan-smoothing (v0.57.0) ooit is toegevoegd.
- **Airco:** de climate-entiteit's `hvac_action` staat op `heating` of
  `cooling` (niet `idle`/`off`).

**Nog niet gedekt:** oven en kookplaat - daar heb je nog geen
vermogen-sensoren voor. Zodra die er zijn, is hetzelfde patroon
(drempel-gebaseerd, zoals vaatwasser/wasmachine) eenvoudig toe te
voegen.

**Wat het niet oplost:** zonder vermogen-sensor voor de airco blijft het
bij "bevestigd actief", niet "hoeveel Watt precies" - de correctie werkt
nog steeds via de totale P1-meting, alleen zonder de ingebouwde
mediaan-vertraging wanneer bevestiging er is.

**Getest** (12 nieuwe permanente tests in `test_heavy_load_awareness.py`):
elk apparaat afzonderlijk bevestigd/niet bevestigd, Quooker-tik genegeerd
vs. aanhoudend gebruik wél bevestigd (inclusief reset bij tussentijds
uitvallen), de correctieratio omzeilt de mediaan zodra er bevestiging is
maar blijft wel afgetopt bij een onwaarschijnlijke meting, en een
end-to-end-test die bevestigt dat dit ook echt in de normale update-tick
wordt bijgehouden (zichtbaar in de diagnostiek via `last_heavy_load_source`).

## v0.63.1 — oven en kookplaat toegevoegd (Home Connect operation_state)

**Aanleiding:** geen vermogen-sensoren voor oven/kookplaat, wel Home
Connect `operation_state`-sensoren
(`sensor.oven_operation_state`/`sensor.kookplaat_operation_state`).

**Aanpak:** anders dan de vermogen-drempel-apparaten hierboven, werkt dit
status-gebaseerd - dezelfde soort aanpak als de airco's `hvac_action`.
Home Connect's `operation_state` kent o.a. `Inactive`, `Ready`,
`DelayedStart`, `Run`, `Pause`, `Finished`, `Error`, `Aborting`; alleen
**`Run`** (hoofdletterongevoelig vergeleken) betekent dat het apparaat
daadwerkelijk vermogen trekt. `Ready`/`DelayedStart` is
ingepland-maar-inactief, `Pause` heeft het verwarmingselement
tussentijds uit, `Finished`/`Inactive` is klaar.

**Nieuwe optionele configuratievelden:** oven- en
kookplaat-status-sensor (beide domain `sensor`, geen vermogen-sensor
nodig).

**Getest** (5 nieuwe permanente tests): `Run` wordt bevestigd (ook
hoofdletterongevoelig), `Ready`/`Finished` terecht niet, en kookplaat
afzonderlijk.

## v0.63.2 — grootverbruiker-status zichtbaar op het dashboard

**Aanleiding:** v0.63.0/v0.63.1 voegden de logica en de
diagnostiek-zichtbaarheid toe, maar niets op het dashboard zelf liet
zien óf, en welke, grootverbruiker net bevestigd actief was.

**Toegevoegd:**
- `ExplanationSensor` (sensor.py) exporteert nu ook `heavy_load_source`
  als attribuut, naast de al bestaande cruciale-waarden-attributen
  (v0.61.1).
- Nieuwe kaart in de "Modus & besluit"-sectie: toont "Geen" of de naam
  van het bevestigde apparaat (Vaatwasser/Wasmachine/Quooker/Airco/
  Oven/Kookplaat), met een oplichtend bliksem-icoon zodra er
  daadwerkelijk iets bevestigd actief is.

**Getest:** bestaande dashboard-testpijplijn blijft groen; de nieuwe
sensor-attribute is meegenomen in de bestaande
`test_explanation_sensor_attributes.py`-tests (aanwezig + correct
`None` als fallback).

## v0.63.3 — scroll-pijltjes weg, secties herschikt tegen lege ruimte

**Gerapporteerd (met screenshot):** twee kleine kaartjes toonden
onbedoelde scroll-pijltjes (Rendement-trend in "Accu & rendement", en de
"hele kalenderdag"-toelichting in "Modus & besluit"), en er bleef nog
steeds een grote lege ruimte over rechts, onder de kortere secties.

**Scroll-pijltjes:** beide kaartjes stonden op `rows: 1`, maar hun tekst
past over 2 regels - Home Assistant maakt de kaart dan intern
scrollbaar in plaats van hem uit te rekken. Opgelost door `rows: 2` te
geven aan beide.

**Lege ruimte:** de "Besturing"- en "Actuele beslissing
(detail)"-secties (samen zo'n 5-6 rijen aan echte inhoud) stonden ver
onderaan de pagina, in een eigen rij die pas begint nadat de hoogste
sectie van rij 1 (de uitlegkaart) is afgelopen - met een hoop lege
ruimte rechts ervan. Verplaatst naar direct na de eerste sectie (Energy
Management System), zodat ze nu in dezelfde rij meelopen en de ruimte
naast de uitlegkaart met echte inhoud vullen in plaats van pas in een
nieuwe rij te verschijnen. Nieuwe volgorde: Energy Management System →
Besturing → Actuele beslissing (detail) → Accu & rendement → Live
cijfers → Modus & besluit.

**Getest:** bestaande dashboard-testpijplijn (YAML-geldigheid +
Jinja-rendering) blijft groen - puur een herschikking en
hoogte-aanpassing, geen nieuwe databronnen.

## v0.63.4 — sectie-herschikking uit v0.63.3 teruggedraaid

**Gerapporteerd (met screenshot):** de herschikking uit v0.63.3
(Besturing/Actuele beslissing direct na de eerste sectie) maakte het
juist slechter — afgeknapte tekst ("Reden laatste beslissing" toonde
"...lt_smart" in plaats van "default_smart") en een nieuwe, grotere
lege ruimte tussen "Besturing" en "Modus & besluit".

**Wat er mis ging:** de aanname dat secties simpelweg rij-voor-rij
wrappen bleek onjuist — Home Assistant's `sections`-layout plaatst elke
sectie kennelijk in de op dat moment kortste kolom (masonry-achtig),
niet strikt links-naar-rechts. Door de volgorde te wijzigen verschoof
de kolomtoewijzing op een manier die niet was te voorspellen zonder het
live te zien, met de afgeknapte tekst en een nieuwe lege ruimte tot
gevolg.

**Fix:** de sectie-volgorde teruggedraaid naar v0.63.2 (Energy
Management System → Accu & rendement → Live cijfers → Modus & besluit →
Besturing → Actuele beslissing). De **wel** ondubbelzinnig goede fix uit
v0.63.3 (scroll-pijltjes weg door `rows: 2` op de twee te-krappe
markdown-kaartjes) blijft staan.

**Les:** een layout-eigenschap aannemen zonder het live te kunnen zien
is te riskant zodra het om iets minder voorspelbaars gaat dan een
enkele kaart-hoogte - voor verdere lege-ruimte-verbeteringen is een
screenshot-feedback-cyclus per stap veiliger dan een grotere
herschikking ineens.

**Getest:** bestaande dashboard-testpijplijn blijft groen; puur een
terugdraai naar een eerder bevestigde structuur.

## v0.63.5 — utility_meter_ems.yaml: verkeerde source-entity's

**Gerapporteerd:** de "Vandaag/Deze week/Deze maand"-kaartjes op het
Financieel-tabblad bleven na correcte installatie van de Utility
Meter-helpers permanent op €0 staan, terwijl de totaalteller er wel
gewoon boven (€6,0583) stond.

**Root cause:** `dashboards/utility_meter_ems.yaml` gebruikte
`source: sensor.energy_management_system_discharge_value_expensive_quarters`
(zonder voorvoegsel), terwijl de daadwerkelijke entity-naam bij een
apparaat met een area-naam (hier: "woonkamer")
`sensor.woonkamer_energy_management_system_discharge_value_expensive_quarters`
is — exact dezelfde inconsistentie in entity-naamgeving die al eerder
in dit dashboard is tegengekomen (sommige sensoren krijgen wel, andere
geen device-naam-voorvoegsel, afhankelijk van of ze `has_entity_name`
gebruiken). Een niet-bestaande `source` levert bij Utility Meter geen
foutmelding op - de meter blijft simpelweg voor altijd op 0 staan, wat
het onopgemerkt liet tot nu.

**Fix:** beide `source`-verwijzingen (discharge value én charge cost)
voorzien van het "woonkamer_"-voorvoegsel, en een waarschuwing in de
bovenste commentaarregels toegevoegd dat een foute source-naam
stilzwijgend faalt (geen foutmelding, gewoon altijd 0) - zodat een
volgende keer, bij een naamswijziging, sneller wordt herkend wat er aan
de hand is.

**Vereist:** een nieuwe volledige HA-herstart (Utility Meter-config
wordt niet met "YAML herladen" bijgewerkt, zoals het bestand zelf ook
al aangaf). Na de herstart begint de teller op dat moment opnieuw vanaf
0 als startpunt - dus ook nu weer pas zichtbaar bij de eerstvolgende
ontlading/netlading.

**Niet in tests gedekt:** dit bestand wordt buiten Home Assistant om
gebruikt (los toe te voegen aan `configuration.yaml`) en valt buiten de
testsuite van deze integratie.

## v0.63.6 — ontbrekende "Accu-bescherming"-sensor toegevoegd aan dashboard

**Aanleiding:** een systematische controle van alle entity-referenties
in het dashboard tegen de daadwerkelijke entiteitenlijst (n.a.v. de
utility_meter-bug) bracht aan het licht dat
`sensor.energy_management_system_battery_protection` — bestaat,
werkt prima — nergens op het dashboard stond. Deze toont het
daadwerkelijk toegepaste ontlaadvermogen tijdens dure kwartieren
(inclusief SoC-aftopping en de huishoudverbruik-vloer uit v0.59.0), met
de SoC op dat moment als attribuut.

**Fix:** toegevoegd als extra rij in de "Actuele beslissing
(detail)"-lijst, naast de andere diagnostische regels.

**Verder gecontroleerd, geen extra fouten gevonden:** alle overige 29
EMS-entity-referenties in het dashboard kloppen exact met de
daadwerkelijke entiteitenlijst (inclusief het wisselende
`woonkamer_`-voorvoegsel per sensor).

## v0.63.7 — losse automatisering: melding bij accumodus/vermogen-wijziging

**Verzoek:** een mobiele melding zodra de integratie de Zendure-modus of
het handmatige vermogen wijzigt, naar het voorbeeld van een bestaande
eigen automatisering — maar dan met live data uit de integratie zelf,
in plaats van de reden opnieuw af te leiden via een eigen kopie van de
SoC/prijs-drempel-logica (die drempels zijn dynamisch en zelflerend
sinds v0.40.0+, dus een statische herhaling zou vroeg of laat uit de
pas gaan lopen).

**Nieuw bestand: `dashboards/notify_battery_mode_change.yaml`** — een
losse Home Assistant-automatisering, zelfde installatiepatroon als
`utility_meter_ems.yaml` (plakken in de automatisering-YAML-editor, geen
integratie-wijziging).

**Aanpak:**
- Trigger op `select.zendure_manager_operation` én
  `number.zendure_manager_manual_power` (dekt zowel een modus-wissel als
  een vermogens-aanpassing binnen dezelfde modus, bijv. de
  huishoudverbruik-vloer uit v0.59.0 die het ontlaadvermogen tussentijds
  ophoogt).
- Meldt alleen wijzigingen die de **integratie zelf** heeft doorgevoerd
  — een wijziging terwijl "Force manual" aanstaat (dus een handmatige
  wijziging van jouzelf) wordt bewust overgeslagen.
- Titel: een emoji + de modus, afgeleid van
  `sensor...last_decision_reason` (alle 8 mogelijke waarden gedekt, plus
  een fallback-icoon voor onbekende/toekomstige waarden).
- Bericht: het toegepaste vermogen, tijdstip, en de **volledige,
  al berekende uitlegtekst** uit `sensor...explanation` (dezelfde tekst
  als op het dashboard, inclusief tabel bij `discharging_window`/
  `default_smart` — blijft vanzelf kloppen bij toekomstige wijzigingen
  aan de beslislogica, geen tweede plek om bij te houden).

**Niet in tests gedekt** (zelfde reden als `utility_meter_ems.yaml`:
buiten Home Assistant om gebruikt), wel handmatig gevalideerd: YAML
laadt correct, en de emoji-Jinja-template is doorgerekend voor alle 8
bekende `last_decision_reason`-waarden plus de fallback.

## v0.63.8 — modus/vermogen-melding ingebouwd (v0.63.7 losse automatisering vervalt)

**Aanleiding:** de losse automatisering uit v0.63.7 werkte, maar de
verwachting was dat dit net als de vaatwasser/wasmachine-melding
**ingebouwd** zou zijn — geen eigen automatisering nodig, gewoon het al
ingevulde `appliance_notify_service`-veld hergebruiken. Terechte
verwachting, dus alsnog zo gebouwd.

**`dashboards/notify_battery_mode_change.yaml` is verwijderd** — zou nu
dubbele meldingen geven als hij ook nog als automatisering bestond.
**Als je die eerder had aangemaakt: verwijder 'm handmatig** (Instellingen
→ Automatiseringen), anders krijg je 'm dubbel.

**Nieuw in de coordinator:**
- `_dispatch_notification()` — gedeelde verzendlogica, geëxtraheerd uit
  de bestaande vaatwasser/wasmachine-melding (v0.47.0) zodat beide
  functies 'm hergebruiken. Zelfde fallback-gedrag als voorheen
  (persistent notification in de HA-UI als er geen notify-service is
  ingevuld).
- `_maybe_notify_mode_change()` — vergelijkt elke tick de combinatie
  (reden, toegepast ontlaad-/laadvermogen) met de vorige tick; bij een
  echt verschil wordt genotificeerd. Dekt zowel een modus-wissel als een
  vermogens-aanpassing binnen dezelfde modus (bijv. de
  huishoudverbruik-vloer uit v0.59.0 die het ontlaadvermogen tussentijds
  ophoogt). Slaat notificeren over bij: de allereerste tick na een
  herstart (niets om mee te vergelijken), `learning_only`-modus (er
  wordt toch niets echt verstuurd), en de `force_manual`/
  `no_forecast_data`-paden (die passeren `_finish_decision_tick` niet,
  want daar wordt sowieso niets naar het apparaat gestuurd).
- `_finish_decision_tick()` — nieuwe gedeelde afsluiter voor elk pad in
  de beslisboom dat daadwerkelijk iets naar het apparaat stuurt: bouwt
  de uitlegtekst én checkt de melding, in één aanroep in plaats van op 7
  plekken losse code te herhalen.

**Bericht bevat:** een reden-specifieke emoji in de titel (alle 8
mogelijke `last_reason`-waarden gedekt, plus een generieke fallback),
het toegepaste vermogen, het tijdstip, en de **volledige, live berekende
uitlegtekst** (`_build_explanation()`) — dus geen tweede, losse kopie
van de beslislogica die op termijn uit de pas kan gaan lopen, zoals bij
een losse automatisering wel het risico was.

**Getest** (7 nieuwe permanente tests in `test_mode_change_notification.py`):
geen melding op de allereerste tick; melding bij een echte
reden-wijziging, met de juiste titel/inhoud; geen dubbele melding bij
eenzelfde reden op de volgende tick; geen melding zonder ingevulde
notify-service; geen melding in `learning_only`; geen melding tijdens
`force_manual`; en de gedeelde `_dispatch_notification`-helper valt nog
steeds correct terug op een persistent notification.

## v0.63.9 — testknop voor de melding

**Aanleiding:** de nieuwe modus/vermogen-melding (v0.63.8) is alleen te
testen door op een échte volgende beslissingswijziging te wachten - de
oude trucje (via Ontwikkelaarshulpmiddelen een status forceren op
`select.zendure_manager_operation`) werkt niet meer, want de melding
wordt nu aangestuurd door de coordinator-cyclus zelf, niet door
state-wijzigingen van die entiteit.

**Nieuw: `button.py`** — een `button`-entiteit ("Test notificatie
versturen") die bij indrukken **dezelfde** `_dispatch_notification()`
-code aanroept als de echte melding, met dezelfde geconfigureerde
`appliance_notify_service`. Test dus niet alleen "werkt notify.*
uberhaupt", maar specifiek "werkt mijn eigen configuratie in deze
integratie" - de eigenlijke vraag.

**Nieuw platform:** `button` toegevoegd aan `PLATFORMS` in `__init__.py`.
Kaartje toegevoegd aan de "Besturing"-sectie op het dashboard.

**Let op:** de entity-ID (`button.woonkamer_energy_management_system_...`)
is de verwachte naam op basis van het bestaande naamgevingspatroon voor
nieuw toegevoegde entiteiten met `has_entity_name`, maar dat patroon is
in dit project al eens onverwacht gebleken (zie de eerdere
`utility_meter`-bug) - controleer na installeren zelf even via
Ontwikkelaarshulpmiddelen of de knop op het dashboard verschijnt zoals
verwacht, en pas de entity-ID in het dashboard-bestand aan indien nodig.

**Getest** (2 nieuwe permanente tests in
`test_test_notification_button.py`): knop verstuurt via de
geconfigureerde notify-service, en valt correct terug op een persistent
notification zonder geconfigureerde service. `homeassistant.components.button`
toegevoegd aan de test-mocks in `conftest.py`, naar hetzelfde patroon
als `switch`.

## v0.63.10 — twee gemiste plekken uit de mediaan-conversie (v0.62.0) alsnog gefixt

**Gevonden bij analyse van een verse diagnostiek-export:** twee
eigenschappen gebruikten nog het gewone gemiddelde over de laatste 7
dagen, en de export liet daar een live voorbeeld van zien:

- **`learned_night_consumption_kw`** (legacy fallback, alleen gebruikt
  als het uurprofiel geen data heeft voor het relevante uur): een
  historie van `[0.407, 0.274, 0.217, 0.166, 0.254, 0.276, 2.121]` gaf
  een gemiddelde van **0,531 kW** — bijna het dubbele van wat 6 van de 7
  bijgehouden nachten daadwerkelijk lieten zien, puur door die ene
  uitschieter-nacht van 2,121 kW.
- **`learned_battery_efficiency_percent`**: een historie van
  `[93.3, 93.6, 84.9, 84.7, 92.0, 92.9, 75.9]` liet een vergelijkbare
  scheeftrekking zien door de uitschieter van 75,9%. Deze waarde
  schaalt rechtstreeks de veiligheidskritische reserve-berekening
  (`_get_efficiency_discounted_pv_offset`,
  `_estimate_worst_case_deficit_kwh`), dus een uitschieter hier raakt
  niet alleen een displaywaarde maar ook hoeveel reserve er 's nachts
  wordt aangehouden.

**Fix:** beide overgezet naar `statistics.median()`, exact dezelfde
aanpak en onderbouwing als v0.62.0 — een enkele ongewone nacht/cyclus
mag een 7-daagse basiswaarde niet noemenswaardig verschuiven.

**Bijkomende observatie, geen actie ondernomen:** `reserve_excess_days`
(1 dag) en `reserve_shortfall_days` (4 dagen) in dezelfde export hadden
een opvallend verschillende historielengte, terwijl beide in exact
hetzelfde codeblok worden bijgewerkt (geverifieerd: geen logicafout in
de huidige code). Vermoedelijk een eenmalig historisch artefact; niet
schadelijk (leidt hooguit tot een licht conservatievere marge dan
strikt nodig), maar niet met zekerheid te verklaren vanuit deze export
alleen.

**Getest** (2 nieuwe permanente tests, reproduceren beide exacte
scenario's uit de diagnostiek-export): de uitschieter beweegt de
mediaan niet noemenswaardig, ter vergelijking met wat het (foute)
gemiddelde zou hebben gedaan.

## v0.63.11 — drie diagnostiek-uitbreidingen, plus een audit van de README-beperkingenlijst

**Drie diagnostiek-uitbreidingen (op verzoek):**

1. **`mode_change_log`** — bouwt voort op de bestaande
   modus-wijziging-detectie (v0.63.8): elke genuine wijziging (reden of
   toegepast vermogen) landt nu in een bounded logboek (laatste 50),
   **onafhankelijk van of er een notify-service is ingesteld**. Eén
   diagnostiek-export volstaat nu om de hele dag se modus-geschiedenis
   te reconstrueren, in plaats van een export op precies het juiste
   moment nodig te hebben.
2. **`reserve_shortfall_dates` / `reserve_excess_dates`** — parallelle
   datumlijst naast de bestaande boolean-historie
   (`reserve_shortfall_history`/`reserve_excess_history`), puur
   additief (raakt de bestaande marge-berekening en restore-logica
   niet). Had de asymmetrie-vraag van vorige keer meteen beantwoord in
   plaats van giswerk.
3. **`pv_forecast_raw`** — de ruwe Solcast-halfuur-voorspelling
   (start/eind/kWh, komende ~48 uur) rechtstreeks in de export, zodat
   de PV-voorspelling zelf te verifiëren is zonder los in
   Ontwikkelaarshulpmiddelen te hoeven kijken.

**README-audit — "Bekende beperkingen" was verouderd, niet blind
overgenomen:**

Vóór het toepassen van de vier genoemde punten eerst gecontroleerd of
ze nog klopten (het stuk noemde nog "15-minuten timer", terwijl dat
sinds v0.44.0 al 5 minuten is). Resultaat: **3 van de 4 waren
achterhaald of feitelijk onjuist**, en zijn gecorrigeerd in plaats van
geïmplementeerd:

- **SoC-check**: allang aanwezig (taps toelopende ontlaad-limiet,
  noodladen, diepste-tekort-reserve).
- **Hysterese**: het genoemde "elke 15 min omslaan" is normaal,
  prijs-gedreven gedrag, geen instabiliteit — maar wél een écht, smaller
  randgeval geïdentificeerd (secundaire-laag-drempel kan theoretisch
  flikkeren op live beschikbare energie binnen hetzelfde kwartier), nog
  niet bevestigd als daadwerkelijk probleem.
- **Zonneplan tomorrow-forecast-timing**: geen bug, correct verwacht
  gedrag — heretiketteerd als zodanig i.p.v. als "op te lossen
  beperking".
- **`iot_class: local_push`**: dit advies was **onjuist** en had ik niet
  moeten uitvoeren zonder controle — deze integratie is fundamenteel
  tijd-gedreven (tijd-tot-goedkoopste-blok verandert puur door het
  verstrijken van tijd, niet door een entity-state-wijziging),
  `local_polling` is hier de juiste classificatie. Laten staan.

**Getest** (3 nieuwe permanente tests in `test_diagnostics_extensions.py`):
mode-change-log bevat de juiste reden/vermogen na een echte
tick-op-tick-wijziging; datum-lijsten komen correct door in de export;
ruwe PV-forecast-entries worden correct omgezet van kW naar kWh per
interval.

## v0.63.12 — steelstofzuiger laadt automatisch tijdens het goedkoopste blok

**Aanleiding:** een bestaande, losse HA-automatisering zette de lader van
de steelstofzuiger op een vaste klok aan/uit (12:00-16:00), met als doel
"altijd op zonne-energie laden". Een vast blok is daar een zwakke
benadering van — op een bewolkte dag laadt hij dan gewoon van het net, en
op een lange zomerdag met veel zon buiten dat venster blijven bruikbare
uren onbenut. Na overleg gekozen voor een eenvoudiger, robuuster doel:
**altijd op de goedkoopste uren van de dag laden, het hele jaar door** —
en dat wél in de integratie zelf, met leerbare laadduur.

**Nieuw: `_async_update_steelstofzuiger_charging()`.** Hergebruikt de
al bestaande "is dit het goedkoopste blok van vandaag"-berekening
(dezelfde die ook de accu-logica gebruikt) om de schakelaar aan te
zetten zodra het blok begint. Zet zichzelf weer uit zodra het vermogen
**2 minuten aanhoudend** onder de bekende "apparaat actief"-drempel
(15W, `APPLIANCE_RUNNING_POWER_THRESHOLD_W`) zakt — hetzelfde principe
als de Quooker-detectie (v0.63.0), nu omgekeerd toegepast: niet
"aanhoudend actief bevestigen", maar "aanhoudend inactief bevestigen dat
de lading klaar is". Laadt maximaal 1x per dag; eenmaal klaar blijft de
schakelaar uit voor de rest van de dag, ook al valt die nog binnen het
goedkope blok.

**Geleerde laadduur** (mediaan over de laatste 7 sessies, dezelfde
uitschieter-resistente aanpak als v0.62.0) wordt bijgehouden voor
diagnostiek/weergave — puur informatief, de aan/uit-beslissing zelf
leunt op de live vermogensmeting, niet op de schatting.

**Nieuwe configuratievelden:** `steelstofzuiger_switch_entity` (de
schakelaar) en `steelstofzuiger_power_sensor_entity` (voor
klaar-detectie, optioneel maar zonder deze wordt "klaar" nooit
gedetecteerd en blijft de schakelaar aan tot het einde van het
goedkope blok).

**Bewuste ontwerpkeuze:** los van `force_manual` (dat gaat specifiek over
de accu-besturing, niet over dit apparaat), wél gebonden aan
`learning_only` (simuleert dan alleen, stuurt niets echt). De
`_async_set_switch()`-helper schrijft bewust niet naar
`last_simulated_action` — dat veld wordt in dezelfde tick ook door de
accu-beslisboom gebruikt en zou elkaar overschrijven;
`last_steelstofzuiger_action` is de eigen, aparte statusindicator.

**Nieuwe sensor:** `sensor.steelstofzuiger_status` (toegevoegd aan het
dashboard, "Actuele beslissing (detail)"-sectie) toont de huidige actie
(`wacht_op_goedkoop_blok` / `laden_gestart` / `aan_het_laden` /
`voltooid` / `voltooid_vandaag`) plus de laadduur-historie en geleerde
mediaan als attributen. Ook zichtbaar in de diagnostiek-export.

**Getest** (8 nieuwe permanente tests in `test_steelstofzuiger_charging.py`):
schakelaar gaat aan bij start van het goedkope blok, blijft uit erbuiten,
gaat uit zodra de lading aanhoudend voltooid is (met correcte
duur-registratie), blijft uit voor de rest van de dag na voltooiing,
reset de "voltooid"-vlag bij een nieuwe dag, doet niets zonder
geconfigureerde schakelaar, raakt de schakelaar nooit aan in
`learning_only`, en de geleerde duur gebruikt de mediaan.

## v0.63.13 — fietsladers toegevoegd, logica gegeneraliseerd

**Aanleiding:** een tweede, bijna identieke losse HA-automatisering
zette de e-bike-laders uit zodra het vermogen 2 minuten onder 20W bleef
("Fietsladers: Automatisch uit bij volle accu"), met een melding erbij
- maar geen prijs-gestuurde inschakeling ("in principe zetten we nu de
schakelaar handmatig aan"). In plaats van dit als tweede, bijna
identieke kopie van de steelstofzuiger-code (v0.63.12) te bouwen, eerst
gegeneraliseerd naar een herbruikbare, parametrische functie.

**Refactor:** `_async_update_steelstofzuiger_charging()` is vervangen
door de gedeelde `_async_update_scheduled_charge_appliance()`, die
per-apparaat state via expliciete attribuutnamen doorgeeft
(`getattr`/`setattr`, hetzelfde patroon dat `_notify_if_appliance_ready`
al gebruikte) - geen dictionary-herstructurering nodig, dus alle
bestaande steelstofzuiger-attributen/tests blijven ongewijzigd werken.
Ook `_finish_steelstofzuiger_session()` is gegeneraliseerd naar
`_finish_scheduled_charge_session()`.

**Fietsladers, nieuw:** eigen configuratievelden
(`fietsladers_switch_entity` / `fietsladers_power_sensor_entity`), eigen
**20W-drempel** (`FIETSLADERS_COMPLETE_THRESHOLD_W`) in plaats van de
gedeelde 15W (`APPLIANCE_RUNNING_POWER_THRESHOLD_W`) - de gerapporteerde
laders hebben kennelijk een hogere standby-trek dan de steelstofzuiger.
Stuurt bij voltooiing een melding ("🚲 Fietsen opgeladen"), exact de
tekst uit de oorspronkelijke automatisering. Dezelfde
voltooiing-melding is ook met terugwerkende kracht aan de
steelstofzuiger toegevoegd, voor consistentie.

**Dashboard ("Apparaten"-pagina):**
- Icoon aangepast van `mdi:dishwasher` naar `mdi:devices` - representeert
  nu meerdere soorten apparaten, niet alleen de vaatwasser.
- Ondertitel gecorrigeerd: was nog "Informatief — geen aansturing", wat
  sinds v0.63.12 niet meer klopt voor de steelstofzuiger/fietsladers
  (die worden wél echt aangestuurd).
- Twee nieuwe kaarten: actuele status + geleerde laadduur voor beide
  geplande laadapparaten.

**Nieuwe sensor:** `sensor.fietsladers_status` (mirror van
`sensor.steelstofzuiger_status`, v0.63.12).

**Getest** (3 nieuwe permanente tests, toegevoegd aan het hernoemde
`test_scheduled_charge_appliances.py`): de 20W-drempel wordt
daadwerkelijk gebruikt (niet de gedeelde 15W - getest met 18W, dat bij
de verkeerde drempel nooit als "klaar" zou zijn herkend); de
voltooiing-melding wordt verstuurd met de juiste titel; en beide
apparaten lopen via dezelfde gedeelde functie zonder dat hun state door
elkaar loopt.

## v0.63.14 — overrule-schakelaars voor steelstofzuiger en fietsladers

**Aanleiding:** de nieuwe geplande-laadapparaten-functie (v0.63.12/
v0.63.13) had geen manier om een apparaat tijdelijk over te nemen zonder
de hele configuratie te verwijderen.

**Nieuw:** twee `switch`-entiteiten, `switch.steelstofzuiger_overrule`
en `switch.fietsladers_overrule` (persistent over herstarts, zelfde
`RestoreEntity`-patroon als `Force manual`/`Learning only`/
`Vakantiemodus`). Staat er eentje aan, dan laat
`_async_update_scheduled_charge_appliance()` die ene schakelaar
volledig met rust — geen aan/uit-commando's, geen
klaar-met-laden-detectie, niets. De status verandert dan naar
`overruled` (zichtbaar in de bijbehorende sensor en de diagnostiek).
Bewust per apparaat, niet gedeeld: het overrulen van de steelstofzuiger
raakt de fietsladers niet en andersom, en beide staan los van
`Force manual` (dat blijft specifiek voor de accu).

**Getest** (4 nieuwe permanente tests): overrule laat de betreffende
schakelaar volledig ongemoeid tijdens het goedkoopste blok, voor beide
apparaten afzonderlijk, en een overrule op het ene apparaat heeft geen
effect op het andere.

## v0.63.15 — arbitrage-laden: actief bijkopen bij een winstgevend prijsverschil

**Aanleiding:** een terechte tegenwerping op de eerdere uitleg (v0.63.14
gaf een te makkelijk antwoord op "waarom laadt de accu nu niet bij tegen
21 ct, terwijl vanavond duurdere kwartieren aankomen?"). Na het
laad/ontlaad-rendement (destijds 88,2%) mee te rekenen bleek dit wél
degelijk winstgevend — de integratie liet hier bewust marge liggen,
omdat ze alleen "genoeg reserve aanhouden" en "verkopen wat er al is"
deed, niet "actief bijkopen omdat het loont".

**Nieuw: `_get_arbitrage_charge_power()`.** Vergelijkt elke tick de
huidige prijs met de hoogste nog resterende prijs van vandaag,
verdisconteerd met het geleerde (of geconfigureerde fallback-)
accu-rendement:

```
netto_eur_per_kwh = (rendement × beste_resterende_verkoopprijs_vandaag) − huidige_prijs
```

Alleen winstgevend genoeg (≥ `MIN_ARBITRAGE_MARGIN_EUR_PER_KWH` = 3
cent/kWh, buffer tegen voorspellingsonzekerheid) triggert een
geforceerde manual-laadactie, reden `arbitrage_charging`.

**Zon-prioriteit** (expliciet gevraagd: "tijdens goedkope uren vooral
zonne-energie blijft opslaan"): het gewenste laadvermogen wordt eerst
verminderd met het live zonoverschot (PV-productie minus werkelijk
huishoudverbruik); alleen het restgat wordt van het net gekocht. Dekt
het zonoverschot het gewenste vermogen al, dan gebeurt er niets — de
bestaande smart-modus (P1-volgend) vangt die zon toch al zelf op.

**Kritieke ontwerpkeuze:** deze branch staat vóór de
`should_postpone_charging`-check in de beslisboom, niet erna — het
gerapporteerde scenario had namelijk precies dit patroon: "genoeg
beschikbaar om te overbruggen" triggerde `smart_discharging`
(uitstellen), wat de arbitrage-kans nooit had bereikt als hij ná die
check stond. "Genoeg om te overbruggen" en "winstgevend om nu meer te
kopen" zijn onafhankelijke vragen. Zet daarnaast **nooit**
`_grid_charged_today` — dat zou de winter-guard activeren en precies de
verkoop onderdrukken waar deze aankoop voor bedoeld was.

**Nieuwe schakelaar:** `switch.arbitrage_laden` — **standaard uit**,
bewust opt-in omdat dit nieuw, echt-geld-gedrag is na een update.

**Nieuwe diagnostiek:** `last_arbitrage_margin_eur_per_kwh`,
`last_arbitrage_solar_surplus_w`, `last_arbitrage_grid_power_w`.

**Getest** (8 nieuwe permanente tests in `test_arbitrage_charging.py`):
geen actie als uitgeschakeld; laadt wanneer winstgevend (reproduceert
het gerapporteerde scenario, 21 ct nu vs. 39 ct later, 88,2% rendement);
geen actie bij een te kleine marge; zonoverschot dat het volledige
doelvermogen dekt voorkomt netaankoop; gedeeltelijk zonoverschot koopt
alleen het gat; zet nooit de winter-guard-vlag; overrulet
`should_postpone_charging` wanneer winstgevend; en gedraagt zich netjes
zonder resterende prijsdata.

## v0.63.16 — de échte oorzaak van "Verschil blijft leeg"

**Aanleiding:** ondanks de eerdere fixes (v0.60.1: volledige
dagreeks-restore i.p.v. alleen het gemiddelde; v0.62.0: mediaan i.p.v.
gemiddelde) bleef de "Verschil"-kolom in beide dashboardtabellen
(uurprofiel-verbruik en PV-voorspellingsbias) voor elk uur op `+0`
staan, ook dagen later.

**Root cause, dieper dan de restore-logica zelf:** het **lopende, nog
niet afgeronde uur** wordt nergens bewaard — alleen al-afgeronde uren
landen in `hourly_consumption_profile`/`pv_hourly_bias_history`. Een
nieuw uur wordt pas als meting bijgeschreven zodra dat uur **zonder
onderbreking volledig is doorlopen**
(`_finalize_hourly_bucket`/`_finalize_pv_hourly_bucket`). Bij elke
HA-herstart resette de in-memory tracker
(`_current_tracked_hour`/`_hour_energy_kwh`/`_hour_duration_hours`/
`_hour_last_sample`, en de PV-tegenhangers) zonder dat er iets werd
gerestored — dus bij frequente herstarts (zoals deze week, tientallen
keren kort na elkaar voor alle versie-updates) kreeg géén enkel uur ooit
de kans om volledig af te ronden. `hourly_consumption_profile` bleef
daardoor bevroren op zijn oude staat, en `previous_hourly_avg_kw` ==
`learned_hourly_avg_kw` exact, voor elk uur, keer op keer.

**Fix:** de opbouw van het lopende uur wordt nu ook gepersisteerd (nieuw
`in_progress`-attribuut op beide sensoren: uur, opgebouwde kWh, duur,
laatste-meting-tijdstip) en bij een herstart hersteld. De bestaande
uur-boundary-logica in `_update_hourly_consumption_profile`/
`_update_pv_hourly_bias_tracking` rondt dan vanzelf correct af zodra de
eerstvolgende uurgrens wordt gepasseerd — inclusief de tijd van vóór de
herstart.

**Veiligheidsgrens tegen een echte, lange storing:** een hersteld
tijdstip dat meer dan `MAX_HOUR_TRACKING_GAP_MINUTES` (20 min) in het
verleden ligt, wordt **niet** gebruikt — bij een uren durende storing
zou de hele tussenliggende tijd anders ten onrechte worden toegeschreven
aan één enkel vermogensniveau, wat dat uur juist zou verpesten. In dat
geval wordt gewoon opnieuw begonnen, zoals voorheen.

**Getest** (2 nieuwe permanente tests in `test_trend_restore.py`): een
herstart halverwege een uur, gevolgd door realistische 5-minuten-ticks
tot de volgende uurgrens, resulteert in een daadwerkelijk nieuwe meting
die de tijd van vóór én na de herstart samenvoegt; en een té oud
hersteld tijdstip (>20 min) wordt terecht verworpen in plaats van
gebruikt.

## v0.63.17 — "PV-voorspelling afwijking" bleef vastzitten op unknown

**Gerapporteerd (met screenshot):** naast de al bekende "PV-voorspelling
bias (huidig uur)" (verwacht gedrag zolang dat specifieke uur nog geen 3
dagen data heeft — zou met v0.63.16 vanzelf opbouwen) bleef ook
"PV-voorspelling afwijking" hardnekkig op `unknown` staan.

**Root cause, een andere zelfversterkende restore-bug:**
`last_deviation_percent` (de weergegeven waarde) werd bij een herstart
hersteld vanuit de **eigen vorige status-string van de sensor**
(`last_state.state`). Was die status op enig moment "unknown" — bijv.
heel normaal vóórdat ooit een eerste dagvergelijking had plaatsgevonden
— dan herstelt elke volgende herstart gewoon weer "unknown" → `None`,
**ook nadat** `deviation_history` (de historielijst) allang echte
metingen bevat uit latere, succesvolle dagvergelijkingen. De restore
keek namelijk nooit naar die historielijst zelf als terugval.

**Fix:** als de directe restore leeg uitvalt maar `deviation_history`
wél waarden bevat, wordt de laatst bekende historische afwijking
gebruikt in plaats van vast te blijven zitten op `unknown`.

**Getest** (3 nieuwe permanente tests in
`test_pv_forecast_accuracy_restore.py`): terugval naar de historie
werkt bij een "unknown" laatste status; een geldige laatste status
wordt gewoon gebruikt (geen onnodige overschrijving); en zonder enige
historie blijft de waarde terecht `None` (niets om op terug te vallen).

## v0.63.18 — "1600W of niets", geen doorlopende trickle-schaling meer

**Aanleiding:** het geschaalde ontlaadvermogen tijdens dure kwartieren
werd continu afgeknepen door een per-tick-headroomformule
(`headroom_kwh / 5-minuten-interval`), die er de facto van uitgaat dat
alle beschikbare headroom binnen die ene 5-minuten-tick besteed zou
moeten worden. Resultaat: een kwartier dat de prijs-prioriteitscheck
(`_is_worth_discharging_now`) al als "betaalbaar op vol vermogen"
bestempelde, kreeg tóch vaak maar een fractie daarvan toegepast (bijv.
150W van de ingestelde 1600W) — een bedrag dat volgens de gebruiker
"niets oplevert" in verhouding tot de moeite.

**Kernwijziging:** zodra `_is_worth_discharging_now` bevestigt dat dit
kwartier hoort bij de zoveel duurste kwartieren die de headroom op **vol**
`manual_discharge_power` kan bekostigen, wordt dat volle bedrag nu ook
daadwerkelijk toegepast — begrensd alleen door wat fysiek in de accu zit
op dat moment (en, als ondergrens, door de huishoudverbruik-vloer,
v0.59.0). De per-tick-headroomformule (`max_power_w`) wordt niet meer
gebruikt als extra afknijp-stap bovenop een reeds-goedgekeurd kwartier —
alleen nog als vangnet in het pad zonder prijscontext (`entries=None`,
uitsluitend een testscenario; de echte beslisboom geeft altijd
`entries` mee).

**Bewust ongewijzigd:** het "niet-betaalbaar"-pad (kwartier valt buiten
de headroom-affordable top) blijft exact zoals het was — geen ontlading,
geen huishoudverbruik-vloer-uitzondering daar, headroom blijft intact
voor een duurder kwartier later. En de huishoudverbruik-vloer zelf blijft
ongewijzigd begrensd op `manual_discharge_power` (was al zo, niet nieuw
in deze versie) — bij een huisverbruik hoger dan het ingestelde
maximum wordt dus nog steeds "slechts" dat maximum toegepast, niet meer.

**Getest** (5 nieuwe permanente tests in `test_full_power_or_nothing.py`,
2 bestaande tests in `test_price_priority_and_scheduling.py` en
`test_consumption_floor.py` bleven ongewijzigd/groen zonder aanpassing
nodig): vol vermogen bij een betaalbaar bevonden kwartier, ondanks een
kunstmatig kleine per-tick-headroom; begrensd door fysieke
beschikbaarheid; onveranderd "niets" bij een niet-betaalbaar kwartier;
en de huishoudverbruik-vloer blijft correct werken als ondergrens
(zowel onder als boven `base_power`).

## v0.63.19 — bij exact geen headroom: smart, geen geforceerd manual-commando

**Gerapporteerd (met diagnostiek-export):** een echt duur kwartier
(`expensive_tier: primary`) resulteerde in `last_reason: expensive_quarter`
met `manual`-modus op slechts 458,7W — exact gelijk aan het live
huisverbruik. Dat kwam van de huishoudverbruik-vloer (v0.59.0), die bij
headroom = 0 nog altijd een `manual`-commando stuurde puur om import te
voorkomen.

**Waarom dat overbodig bleek:** deze installatie's zendure-ha-configuratie
regelt `smart`-modus al P1-volgend richting een klein terugleverdoel
(eerder gedeeld: "HW P1 Vermogen -50W"). Dat voorkomt netimport al
vanzelf, en doet dat **continu bijgesteld**, terwijl een handmatig
commando pas bij de volgende 5-minuten-tick wordt herzien. Een
geforceerd `manual`-commando met exact het huisverbruik voegt dus niets
toe aan wat `smart` toch al doet — en blokkeert bovendien dat
`smart` zijn eigen, actievere regeling kan toepassen.

**Fix:** bij `max_power_w <= 0` (headroom exact uitgeput) stuurt
`_get_soc_scaled_discharge_power` niet langer een vloer-commando, maar
geeft `None` terug — de aanroepende beslisboom schakelt dan (zoals al
sinds eerder) expliciet naar `smart`
(`expensive_quarter_soc_protected`). De huishoudverbruik-vloer blijft
wél actief zodra er íets aan headroom is (hoe klein ook, tot aan de
"1600W of niets"-drempel uit v0.63.18) — alleen het exact-nul-geval
verandert.

**Getest** (1 bestaande test omgezet naar het nieuwe verwachte gedrag,
1 nieuwe end-to-end test in `test_full_power_or_nothing.py`): bevestigt
zowel dat de helper-functie `None` teruggeeft bij exact geen headroom,
als dat de volledige beslisboom daadwerkelijk het `select.select_option`
"smart"-commando verstuurt in dat scenario.

## v0.63.20 — twee inconsistenties in dezelfde export gevonden en gefixt

**Gerapporteerd (met screenshot):** twee dingen klopten niet met elkaar
in dezelfde weergave:

1. De uitlegtekst zei "de accu-SoC (88%) is te laag om dat te
   rechtvaardigen" — maar 88% is allesbehalve laag.
2. "Werkelijke modus (Zendure ...)" toonde `smart`, maar "Verwachte
   modus (logica)" toonde `manual` — tegenstrijdig.

**Bug 1 — verkeerde verklaring:** de `expensive_quarter_soc_protected`-
tekst had maar twee takken: prijs-prioriteit, of "SoC te laag". Die
tweede tak was geschreven voor de vlakke SoC-taper-fallback (geen
`available_energy_sensor_entity` geconfigureerd), maar wordt ook getoond
wanneer de **dynamische reserve-tak** simpelweg geen headroom meer over
heeft (sinds v0.63.19 valt dat terug op `smart` zonder geforceerd
commando) — een heel andere, legitieme reden die niets met de SoC zelf
te maken heeft. Nu een derde tak toegevoegd (herkend via de al
bestaande `last_used_soc_taper_fallback`-vlag, v0.60.0): bij de
dynamische tak wordt nu de werkelijke reden uitgelegd (de
nachtreserve-berekening laat geen ruimte over), met het beschikbare
aantal kWh erbij, in plaats van ten onrechte de SoC de schuld te geven.

**Bug 2 — verkeerde "Verwachte modus":** `last_expected_mode` werd
vroeg in de beslisboom precies één keer berekend, puur op basis van "is
dit kwartier duur" — vóórdat de headroom-/SoC-/prijs-prioriteitschecks
konden bepalen dat het uiteindelijke besluit toch `smart` werd. Die
correctie gebeurde daarna nergens meer, dus bleef de weergave op
`manual` staan hangen terwijl er allang `smart` was toegepast. Nu
gecorrigeerd in `_finish_decision_tick()` (draait aan het einde van elk
pad dat daadwerkelijk iets toepast): een nieuwe `REASON_TO_MODE`-mapping
zet `last_expected_mode` na afloop gelijk aan wat er op basis van de
uiteindelijke `last_reason` daadwerkelijk is besloten.

**Getest** (1 nieuwe permanente test in `test_explanation_text.py` voor
de tekst-fix, 2 nieuwe in `test_expected_mode_correction.py` voor de
modus-correctie): de dynamische-reserve-tak noemt nu de nachtreserve en
niet de SoC; en `last_expected_mode` komt na afloop overeen met de
daadwerkelijke beslissing, zowel voor een geslaagde ontlading als voor
de terugval naar smart.

## v0.63.21 — laatste stuk van "Verschil blijft leeg": een verankerd duplicaat opgeruimd

**Gerapporteerd, met de daadwerkelijke `profile_history`-attributen erbij
(geen giswerk deze keer):** ondanks v0.63.16 (lopend uur overleeft een
herstart) bleef "Verschil" op `+0` staan. De data zelf liet zien dát er
al een derde, echte meting was bijgekomen voor de meeste uren — het
probleem zat 'm dus niet in het verzamelen, maar in de mediaan-wiskunde
zelf.

**Root cause:** elk uur begon zijn leven met **twee identieke**
waarden (het duplicaat-restpatroon van de allereerste, oude
restore-methode van vóór v0.60.1, v0.56.1). Met die twee identieke
"stemmen" plus precies één nieuwe, echte meting — bijv. `[0.781, 0.781,
0.826]` — verandert de mediaan van alle 3 waarden helemaal niet ten
opzichte van de mediaan van de eerste 2: `0.781` in beide gevallen. Het
duplicaat-paar houdt de mediaan dus verankerd totdat er een
**meerderheid** van échte, nieuwe metingen tegenover staat — precies
het mechanisme dat mediaan-gebaseerd leren (v0.62.0) bewust
uitschieter-resistent maakt, maar hier ongewenst een oud restant
bevoordeelde boven verse data.

**Fix:** bij het herstellen van `profile_history` wordt een **leidend
duplicaat-paar** (`waarde[0] == waarde[1]`, exact de vingerafdruk van
het oude seed-patroon) nu eenmalig teruggebracht tot één waarde
(`[x, x, y]` → `[x, y]`). Daarmee telt de eerstvolgende écht nieuwe
meting weer meteen mee, zoals het oorspronkelijke ontwerp
(v0.56.1: "twee identieke waarden = geen wijziging, tot de eerstvolgende
meting een echt verschil laat zien") altijd al bedoeld had — vóórdat de
overstap naar mediaan (v0.62.0) dat stilzwijgend ondermijnde voor uren
met weinig samples.

**Getest** (3 nieuwe permanente tests in `test_trend_restore.py`, met
de exacte gerapporteerde waarden): het duplicaat-paar wordt opgeruimd en
laat de eerstvolgende meting meteen een echt verschil tonen; een
niet-duplicaat leidend paar (twee daadwerkelijk verschillende dagen)
blijft terecht ongemoeid; en hetzelfde voor de PV-bias-sensor.

## v0.63.22 — diepste-tekort-tabel nu bij elke reden zichtbaar, niet alleen discharging_window

**Gerapporteerd:** "Ik zie de 2e tabel alleen bij smart_discharging,
waarom niet bij andere operation modes?"

**Onderzoek, en een correctie op mijn eigen eerste inschatting:**
aanvankelijk vermoedde ik dat `last_needed_kwh_breakdown` alleen
ververst werd wanneer `_should_postpone_charging()` daadwerkelijk
"aan de beurt" kwam in de beslisboom. Bij het echt narekenen bleek dat
niet te kloppen — die functie wordt al vroeg in elke tick aangeroepen,
**vóórdat** de reden-specifieke takken (negative_price, expensive_quarter,
grid_charging_low_solar, enz.) een keuze maken. De data was dus allang
elke tick vers beschikbaar; het probleem zat puur in de tekstopbouw
(`_build_explanation()`), die de tabel maar in twee van de acht
mogelijke redenen daadwerkelijk liet zien.

**Fix:** de tabel-toevoeging is verplaatst van losse code per reden naar
één centrale plek, die voor **elke** reden (behalve `no_forecast_data`,
waar geen reserve-context relevant is) de tabel toont zodra
`last_needed_kwh_breakdown` gevuld is. Geen duplicatie meer, en
consistente zichtbaarheid ongeacht welke modus er op dat moment actief
is.

**Getest** (2 nieuwe permanente tests in `test_explanation_text.py`):
de tabel verschijnt nu ook bij een reden als `expensive_quarter` zodra
er data is, en blijft terecht weg wanneer de breakdown leeg is.

## v0.63.23 — "teruglevering krijgt voorrang" was onjuiste terminologie

**Gerapporteerd, na de eigen definities van de drie smart-varianten
(v0.63.22-conversatie):**

| Modus | Ontladen (0 op meter) | Laden |
|---|---|---|
| `smart_discharging` | Ja | Nee |
| `smart_charging` | Nee | Ja, alleen bij PV-overschot |
| `smart` | Ja | Ja, alleen bij PV-overschot |

De `discharging_window`-uitleg zei "laden wordt uitgesteld en krijgt
teruglevering nu voorrang (smart_discharging)" — maar "teruglevering
krijgt voorrang" suggereert **actief exporteren/verkopen**, terwijl
`smart_discharging` volgens de eigen definitie alleen betekent: de accu
dekt het huishoudverbruik zelf (0 op de meter), zonder actieve
verkoop. Een te stellige/verkeerde formulering, in beide varianten van
deze tekst (met en zonder energie-context).

**Fix:** "de accu dekt het huishoudverbruik zelf (0 op de meter), zonder
actief te verkopen (smart_discharging)" — in lijn met de daadwerkelijke
betekenis.

**Niet gewijzigd:** de historische vermelding van de oude tekst in dit
CHANGELOG-bestand zelf (v0.30.0-sectie) - dat is een citaat van hoe de
tekst destijds daadwerkelijk luidde, geen actuele documentatie.

## v0.63.24 — "wat bespaart de accu": kostprijs-gebaseerd besparingsmodel

**Aanleiding:** de bestaande financiële sensoren
(`discharge_value_expensive_quarters`/`charge_cost_grid_charging`) meten
alleen de directe waarde van expliciete koop-/verkoopacties — niet wat
de accu in bredere zin "bespaart", zoals ook de waarde van 0-op-de-meter
houden met zon- of goedkoop-net-geladen energie tijdens een duurder
moment, zonder dat er iets expliciet is "verkocht".

**Kernidee, mogelijk gemaakt door het salderen-contract (tot en met
2026-12-31):** onder salderen betaalt teruglevering hetzelfde dynamische
tarief als inkoop — dus zon die de accu in gaat (in plaats van terug te
leveren) heeft exact dezelfde opportuniteitskosten als het inkopen van
diezelfde energie op dat moment. Dat maakt één uniform model mogelijk:
elke kWh die de accu in gaat wordt gewaardeerd tegen de actuele
dynamische prijs (ongeacht bron), en elke kWh die eruit gaat — verkocht
óf gebruikt om een import te voorkomen — realiseert het verschil met die
kostprijs. Geen aparte boekhouding per bron nodig (en ook niet mogelijk:
de accu is één gedeelde pool, geen partijen per herkomst).

**Nieuw: `_update_battery_cost_basis_and_savings()`.** Draait elke tick,
onvoorwaardelijk en vroeg (net als de andere trackers), en leest de
verandering in `available_kwh` sinds de vorige tick:
- **Toename** (laden, ongeacht bron) → gewogen-gemiddelde kostprijs
  bijwerken tegen de actuele prijs.
- **Afname** (ontladen, verkocht of verbruik-dekkend) → verschil tussen
  actuele prijs en kostprijs realiseren als besparing/verdiensten.
- Kleine schommelingen (< `MIN_COST_BASIS_DELTA_KWH` = 0,01 kWh) worden
  genegeerd als sensorruis.
- Ontlading vóórdat er ooit een kostprijs is vastgesteld (bijv. vlak na
  installatie) wordt overgeslagen in plaats van geraden.

**Nieuwe sensor:** `sensor.battery_savings_cost_basis_model` — in
tegenstelling tot de bestaande sensoren mag deze wél "besparing" heten:
hij gebruikt uitsluitend prijzen die daadwerkelijk zijn waargenomen op
het moment van laden/ontladen, geen hypothetisch scenario. Kan net als
de werkelijkheid ook dalen (verlies bij verkoop onder kostprijs), dus
`state_class: total`, niet `total_increasing`. Toont de actuele
kostprijs per kWh als attribuut.

**Nieuwe Utility Meter-regels** toegevoegd aan `utility_meter_ems.yaml`
(dag/week/maand), plus een nieuwe koptekst-kaart en dag/week/maand-rij
op het Financieel-dashboard.

**Bewuste vereenvoudiging:** onderscheidt niet tussen "ontlading die
nuttig verbruik dekte" en "ontlading verloren aan interne
zelfontlading" — beide zien er in de `available_kwh`-data identiek uit.
Zelfontlading is doorgaans een klein deel van de totale doorstroom.

**Getest** (8 nieuwe permanente tests in `test_battery_savings.py`):
eerste tick zaait alleen; laden zet de kostprijs op de actuele prijs;
meerdere ladingen werken het gewogen gemiddelde correct bij; ontladen
realiseert het juiste verschil; ontladen zonder bekende kostprijs wordt
overgeslagen; kleine schommelingen worden genegeerd; een verlies-
realisatie (verkoop onder kostprijs) werkt en levert een negatief getal
op; en zonder geconfigureerde `available_energy_sensor_entity` gebeurt
er niets.

## v0.63.25 — Zonneplan Zonnebonus verrekend in het besparingsmodel

**Gevraagd:** of het v0.63.24-besparingsmodel al rekening hield met de
Zonneplan Zonnebonus en de bijbehorende criteria. Dat was niet het
geval — en na webonderzoek (niet aangenomen) bleek dit relevant.

**Gevonden, bevestigd via meerdere onafhankelijke bronnen:**
- Bovenop de kale marktprijs geldt een **vaste terugleverpremie van
  €0,02/kWh**, voor elke kWh die daadwerkelijk wordt teruggeleverd —
  ook vanuit een accu, ook buiten je saldeerbereik.
- Daarbovenop een **aparte 10%-bonus**, met voorwaarden (alleen
  overdag, niet bij bijna-negatieve prijzen, max. 7.500 kWh/jaar) —
  maar cruciaal: **"Geen bonus over teruglevering vanuit een
  thuisbatterij."** Die 10% geldt dus nooit voor onze accu.

**Wat dit onthulde:** de vaste €0,02/kWh-premie zat nergens in het
model — bij een daadwerkelijke verkoop werd de opbrengst dus met
€0,02/kWh onderschat. Bovendien maakte het model geen onderscheid
tussen ontlading die daadwerkelijk het net op gaat (waar de premie voor
geldt) en ontlading die alleen eigen verbruik dekt (geen teruglevering,
dus ook geen premie).

**Fix, na expliciete keuze van de gebruiker voor de precieze variant
boven een simpele benadering:** `_update_battery_cost_basis_and_savings()`
splitst een ontlading nu per tick in een export- en een
verbruik-dekkend deel, door het gemiddelde ontlaadtempo (uit de
`available_kwh`-daling gedeeld door de verstreken tijd) te vergelijken
met het live gecorrigeerde huisverbruik. Alleen het deel dat daarboven
uitkomt (`FEEDIN_PREMIUM_EUR_PER_KWH` = €0,02) telt als echte
teruglevering. De 10%-bonus wordt bewust **nooit** toegepast (geldt
sowieso niet voor accu-teruglevering).

**Bewust beperkt tot de ontladingskant** (zoals gevraagd) — de laadkant
(zou zon-geladen energie tegen de gederfde teruglever-waarde
gewaardeerd moeten worden in plaats van de marktprijs?) blijft
ongewijzigd, een mogelijke vervolgstap.

**Nieuw:** `total_feedin_premium_eur` (cumulatief, apart bijgehouden en
zichtbaar als attribuut op `sensor.battery_savings_cost_basis_model` en
in de diagnostiek) — laat zien hoeveel van de totale besparing specifiek
uit de terugleverpremie komt.

**Getest** (2 nieuwe permanente tests in `test_battery_savings.py`, met
een correct geconfigureerde `battery_power_sensor_entity` om het
werkelijke huisverbruik correct te reconstrueren uit de P1-meterstand):
de premie wordt correct toegepast op alleen het exportdeel van een
ontlading, en blijft terecht op nul wanneer een ontlading uitsluitend
eigen verbruik dekt.

## v0.63.26 — feed-in-premie ook consistent op discharge_value_expensive_quarters

**Opschoning + aanvulling op v0.63.25:** tijdens het narekenen bleek
`_update_financial_tracking()` (de bestaande
`discharge_value_expensive_quarters`-sensor) de nieuwe
export-vs-verbruik-dekkend-splitsing nog niet te gebruiken — die telde
nog steeds puur `vermogen × marktprijs`, zonder de €0,02/kWh
Zonneplan-terugleverpremie. Voor een sensor die zich presenteert als
"directe waarde van verkoop" is dat een reële onderschatting bij een
daadwerkelijke export. Nu consistent met het kostprijsmodel: dezelfde
per-tick-splitsing (ontlaadtempo vs. live gecorrigeerd huisverbruik)
bepaalt welk deel premie krijgt.

**Ook opgeruimd:** een tijdens het ontwikkelen ontstane dubbele,
overbodige implementatie (een eenvoudigere P1-teken-gebaseerde
premie-detectie naast de al aanwezige, preciezere tick-interne
rate-vergelijking) — verwijderd ten gunste van de bestaande, betere
aanpak.

**Getest** (1 nieuwe permanente test): reproduceert exact hetzelfde
scenario als de bestaande kostprijsmodel-tests (200W huisverbruik,
1000W ontlading → 800W echte export), en bevestigt dat
`discharge_value_expensive_quarters` nu ook €0,016 premie meerekent op
die 0,8 kWh export.

## v0.63.27 — "Dure kwartieren" begrensd op wat de accu fysiek aankan

**Gerapporteerd (met screenshot):** "Drempel duur" toonde 35 kwartieren
— 8,75 uur bij 1600W, tegenover een accu met slechts ~7,4 kWh
beschikbaar. Fysiek onmogelijk, en daarmee meer verwarrend dan nuttig.

**Root cause:** `_count_expensive_quarters_today()` telde simpelweg alle
kwartieren van de hele kalenderdag die de dynamische drempel (top 20%
van de prijsrange) haalden, zonder enige begrenzing op wat de accu ooit
zou kunnen verkopen. Bij een relatief vlakke prijsdag met één duidelijke
dip en een lang "schouder"-gebied van vergelijkbaar hoge prijzen kan dat
aantal ver boven de nominale 20% uitkomen.

**Fix:** twee nieuwe, optionele configuratievelden —
`battery_total_capacity_sensor_entity` (bijv.
`sensor.zendure_manager_total_kwh`) en `battery_min_soc_number_entity`
(bijv. `number.solarflow_2400_ac_min_soc`, de **hardware**-ondergrens
van het apparaat zelf, los van de eigen `min_soc_percent`-instelling van
deze integratie). Beide **live** uitgelezen, niet statisch
geconfigureerd, zodat het blijft kloppen als de capaciteit verandert
(bijv. door veroudering) of de min-SoC handmatig wordt aangepast.

Bruikbare capaciteit = `totale_capaciteit × (1 − hardware_min_soc / 100)`.
Maximaal aantal kwartieren = die capaciteit gedeeld door de energie per
kwartier bij `manual_discharge_power`. De uiteindelijke telling is
`min(ruwe_telling, capaciteit_maximum)` — een grove, fysieke bovengrens,
bewust geen precieze "hoeveel kan ik vandaag echt verkopen"-voorspelling
(dat vereist de dynamische nachtreserve, die per kwartier verschilt en
al door de bestaande prijs-prioriteitslogica wordt afgehandeld). Zonder
de twee nieuwe velden: exact hetzelfde gedrag als voorheen (geen
regressie voor bestaande installaties).

**Nieuwe diagnostiek:** `last_max_sellable_quarters_by_capacity`.

**Dashboard:** de info-kaart naast "Dure kwartieren" is bijgewerkt om
de nieuwe capaciteit-begrenzing uit te leggen.

**Getest** (5 nieuwe permanente tests in
`test_realistic_expensive_quarters.py`): reproduceert het gerapporteerde
scenario (36 ruwe kwartieren, 7,4 kWh → begrensd tot 18); een
hardware-min-SoC vermindert de bruikbare capaciteit correct; de kleinste
van de twee waarden wint altijd (geen kunstmatige verhoging op een dag
met weinig dure kwartieren); en zonder (één van) de twee entiteiten
blijft het exact de oude, ongebreidelde telling.

## v0.63.28 — Kirchhoff-energiebalans-validatie (fase 1 van de architectuur-uitbreiding)

**Aanleiding:** een uitgebreide architectuur-wishlist ontvangen
(Kirchhoff Validation, Occupancy Engine, Dynamic Reserve Engine,
Battery Profit/Wear Engine, MPC, Monte Carlo, NILM, Markov States,
Kalman Filtering, Weather Ensemble, Anomaly/CUSUM, Digital Twin,
Database-laag, nieuwe dashboards, testmatrix). Na beoordeling: 6-7 van
de veertien voorgestelde onderdelen bleken **al te bestaan** onder een
andere naam (Energy Bridge, Reserve/Battery/Forecast-Bias Learning,
Forecast Confidence, deels Kirchhoff zelf, NILM). De zwaardere
technieken (MPC over 96 kwartieren, Monte Carlo, Kalman filtering,
Digital Twin, een eigen database-laag) zijn bewust **niet** opgepakt —
te zwaar en te moeilijk te verifiëren voor een installatie met één
huishouden en één accu, en in directe spanning met de uitlegbaarheid
waar deze integratie de hele ontwikkeling al op inzet. In overleg
gekozen om te beginnen met het stuk dat het meest natuurlijk voortbouwt
op bestaande, geteste logica: energiebalans-validatie.

**Nieuw: `_update_energy_balance_validation()`.** Vergelijkt elke tick
het batterijvermogen-sensor met wat de verandering in beschikbare
energie sinds de vorige tick **impliceert** dat het vermogen geweest
moet zijn — een interne consistentiecontrole op sensoren die al
geconfigureerd zijn, geen nieuwe meting. Vangt: een vastgelopen/
niet-beschikbare sensor, een verkeerd gekozen entity, een
eenheden-mismatch, of een tekenfout die `invert_battery_power_sign` had
moeten corrigeren.

**`sensor.sensor_health_score`** (0-100%): percentage van de laatste 20
metingen binnen de foutmarge (300W). Een ontbrekende sensorwaarde telt
als "slecht". **`measurement_quality`**: vertaalt de score naar
goed/verminderd/slecht. Bewust géén `RestoreEntity` — dit is een live
signaal over recente ticks, geen cumulatieve teller; verouderde
historie herstellen zou juist misleidend zijn over de **huidige**
sensor-gezondheid.

**Veiligheidsgrens:** een herstart-grote onderbreking (>20 minuten)
wordt overgeslagen in plaats van als fout geteld — dezelfde
staleness-guard als bij de uurprofiel-tracking (v0.63.16).

**Getest** (7 nieuwe permanente tests in
`test_energy_balance_validation.py`): consistente metingen scoren
perfect; een grote mismatch wordt gevlagd; een ontbrekende sensorwaarde
telt als slecht; een herstart-grote onderbreking wordt niet als fout
geteld; de score middelt correct over een glijdend venster; en zonder
beide sensoren gebeurt er niets (geen regressie).

## v0.63.29 — CUSUM-sluipverbruik-detectie (fase 2 van de architectuur-uitbreiding)

**Aanleiding:** vervolg op de architectuur-wishlist (v0.63.28). Van de
resterende vijf onderdelen (Occupancy Engine, Battery Profit/Wear
Engine, Markov States, Weather Ensemble, Anomaly/CUSUM) beoordeeld en
in overleg gekozen om te beginnen met Anomaly/CUSUM — geen nieuwe
sensoren nodig, bouwt volledig voort op de al bestaande, geleerde
verbruiksdata. Battery Wear Engine voorlopig overgeslagen (vereist
vervangingskosten + verwachte levensduur, nog niet aangeleverd);
Occupancy Engine, Markov States en Weather Ensemble beoordeeld als
minder gunstige verhouding tussen moeite en meerwaarde gegeven wat er
al bestaat (zie v0.63.28-toelichting in de conversatie).

**Nieuw: `_update_anomaly_detection()` + `_finalize_baseline_load_day()`.**
Volgt dagelijks het laagste gecorrigeerd-verbruik-moment (meestal diep
in de nacht) en past een klassieke **CUSUM-controlekaart** toe om een
**aanhoudende** stijging te detecteren — bewust met een aparte, langere
geschiedenis (30 dagen) dan de adaptieve 7-dagen-mediaan die de rest van
de integratie gebruikt, want die zou een langzame sluipende stijging
juist binnen een week stilzwijgend als "normaal" opnemen.

Parameters: 20W dode zone (normale ruis accumuleert niet), 150W
cumulatieve alarmdrempel (een kleine afwijking kost ~een week om te
alarmeren, een grote sprong een paar dagen), referentie sluit de meest
recente 5 dagen uit (voorkomt dat een lopende afwijking zijn eigen
vergelijkingsbasis vervuilt). Gepauzeerd tijdens vakantiemodus.

**Nieuwe sensor:** `sensor.sluipverbruik_detectie` ("normaal"/
"gedetecteerd"), mét `RestoreEntity` (in tegenstelling tot de
Kirchhoff-gezondheidsscore van v0.63.28 — deze geschiedenis is juist
bedoeld om over weken op te bouwen, dat mag een herstart niet
resetten).

**Melding:** edge-triggered (alleen bij de overgang naar
"gedetecteerd", niet elke dag opnieuw zolang het aanhoudt) via
`appliance_notify_service`.

**Getest** (9 nieuwe permanente tests in
`test_sluipverbruik_detection.py`): geen detectie met onvoldoende
geschiedenis; een stabiele belasting triggert nooit; een aanhoudende
verschuiving wordt na een paar dagen gedetecteerd; een losse
uitschieter-nacht triggert niet; kleine afwijkingen binnen de dode zone
accumuleren niet; gepauzeerd tijdens vakantiemodus; de laagste meting
binnen één dag wordt correct bijgehouden; zonder verbruikssensor
gebeurt er niets; en de melding wordt precies één keer verstuurd, niet
elke dag opnieuw.

## v0.63.30 — Weather Ensemble (fase 3): bewolkingsgraad-tegencheck, geen kWh-ensemble

**Aanleiding:** vervolg op de architectuur-wishlist (v0.63.28/.29).
Vooraf de haalbaarheid eerlijk doorgenomen: KNMI en OpenWeatherMap
geven algemeen weer (bewolkingsgraad), geen kant-en-klare PV-opbrengst
zoals Solcast — een écht vergelijkbare kWh-schatting zou
paneelgegevens (oriëntatie, hellingshoek, wattpiek) vereisen die deze
integratie niet verzamelt. In overleg gekozen voor een eerlijker,
kleiner afgebakende versie: een bewolkingsgraad-tegencheck in plaats van
een vervangende opbrengstvoorspelling.

**Nieuw: `_update_weather_ensemble_check()`.** Leest live
`cloud_coverage`-attributen van de geconfigureerde `weather`-entiteiten
(KNMI/OpenWeatherMap — bestaande HA-integraties, geen nieuwe
API-koppeling nodig) en middelt ze. Vergelijkt daarnaast, als
`pv_power_sensor_entity` is geconfigureerd, het live PV-vermogen met
wat Solcast voor **dit exacte moment** voorspelt (hergebruikt de
bestaande `_get_pv_forecast_entries()`). Presteert de PV fors onder de
Solcast-voorspelling terwijl beide weerbronnen heldere lucht melden, dan
wijst dat eerder op een paneel-/omvormer-kwestie dan op het weer — en
wordt als zodanig gesignaleerd (en omgekeerd, als minder urgente
kalibratie-notitie).

**Nieuwe configuratievelden:** `knmi_weather_entity`,
`openweathermap_weather_entity` (beide optioneel, `weather`-domein).

**Nieuwe sensor:** `sensor.weather_ensemble_bewolkingsgraad` — gemiddelde
bewolkingsgraad + label (helder/half bewolkt/bewolkt) + het
onenigheid-signaal als attribuut. Geen `RestoreEntity` — een live
tegencheck, geen cumulatieve teller.

**Bewust puur informatief:** niet verweven in enige beslissing van de
integratie, zoals afgesproken.

**Getest** (9 nieuwe permanente tests in `test_weather_ensemble.py`):
middeling over beide bronnen; alle drie labels correct toegepast; werkt
met slechts één geconfigureerde bron; niets zonder bronnen; een
ontbrekend `cloud_coverage`-attribuut wordt overgeslagen (niet als 0
geteld); onderpresteren-bij-heldere-lucht wordt gesignaleerd;
onderpresteren-bij-bewolking wordt terecht **niet** gesignaleerd
(consistent, geen onenigheid); en geen tegencheck zonder PV-sensor.

## v0.63.31 — climate.slaapkamer toegevoegd aan de grootverbruiker-detectie

**Gevraagd:** een tweede climate-entiteit (`climate.slaapkamer`) naast
de bestaande airco laten meetellen voor grootverbruiker-bevestiging.

**Fix:** nieuw, onafhankelijk configuratieveld
`slaapkamer_climate_entity`, met exact dezelfde `hvac_action`-gebaseerde
detectie als de bestaande airco (heating/cooling =
`AIRCO_ACTIVE_HVAC_ACTIONS`). Los van elkaar: een idle airco maskeert
geen actieve slaapkamer-eenheid en andersom.

**Getest** (3 nieuwe permanente tests in `test_heavy_load_awareness.py`):
verwarmen wordt bevestigd, idle niet, en beide climate-entiteiten werken
onafhankelijk van elkaar.

## v0.63.32 — Markov States "Optie 1": vaatwasser/wasmachine RUSTEND/ACTIEF/KLAAR

**Aanleiding:** vervolg op de architectuur-wishlist (fase 4/5). Vooraf de
haalbaarheid van echte Markov-fasedetectie (vullen/wassen/spoelen/
centrifugeren apart herkennen) eerlijk doorgenomen: dat vereist
merk/model-specifieke vermogenspatronen waar geen trainingsdata voor
is. In overleg gekozen voor "Optie 1": geen fase-detectie, wel een
eenvoudige, robuuste RUSTEND/ACTIEF/KLAAR-toestandsmachine met geleerde
cyclusduur.

**Nieuw: `_update_appliance_state_machine()`**, gedeeld tussen vaatwasser
en wasmachine. RUSTEND→ACTIEF bij vermogen boven de bekende
apparaat-actief-drempel (15W). ACTIEF→KLAAR bij
`APPLIANCE_CYCLE_COMPLETE_SUSTAINED_MINUTES` (5 minuten, bewust ruimer
dan de 2 minuten van de steelstofzuiger/fietsladers) aanhoudend
daaronder — een cyclus kan tussentijdse stille fases hebben (vullen,
weken) die een kortere marge ten onrechte als "klaar" zou markeren.
KLAAR→ACTIEF start een nieuwe cyclus direct door.

Leert de cyclusduur (mediaan over de laatste 7 cycli) en toont een
grove voortgangsschatting zolang een cyclus loopt. Stuurt een melding
via `appliance_notify_service` zodra een cyclus klaar is.

**Nieuwe sensoren:** `sensor.vaatwasser_cyclus_status`,
`sensor.wasmachine_cyclus_status` — beide `RestoreEntity` (de geleerde
cyclusduur-geschiedenis moet een herstart overleven, zelfde patroon als
de scheduled-charge-apparaten).

**Dashboard:** twee nieuwe kaarten op de "Apparaten"-pagina, naast de
bestaande steelstofzuiger/fietsladers-statuskaarten.

**Getest** (8 nieuwe permanente tests in `test_appliance_cycle_state.py`):
start in rustend; correcte overgang naar actief; een korte pauze
onderbreekt de cyclus niet ten onrechte; aanhoudend laag vermogen rondt
de cyclus af en leert de duur; een nieuwe cyclus start direct door
vanuit klaar; vaatwasser en wasmachine lopen onafhankelijk van elkaar;
niets zonder geconfigureerde sensor; en de melding wordt correct
verstuurd bij voltooiing.

## v0.63.33 — MPC-adviesmotor (prijsarbitrage-plan), uitsluitend adviserend

**Aanleiding:** vervolg op de architectuur-wishlist. Vooraf expliciet
bevestigd dat MPC **niet** de accu mag aansturen — puur adviserend naast
de bestaande, beproefde beslisboom, om precies de reden die eerder is
toegelicht: de resultaten van MPC/Monte Carlo/Kalman/Digital Twin/
Database-laag zijn niet tegen echte data te verifiëren zoals de rest
van deze integratie dat wel is (elke eerdere feature is getoetst tegen
screenshots/diagnostiek-exports). Zonder die feedback-loop worden deze
vijf uitsluitend informatief gebouwd, nooit sturend.

**Nieuw: `_compute_mpc_plan()`.** Greedy interval-pairing-algoritme over
de beschikbare prijsvoorspellingshorizon (vandaag + morgen, tot 48 uur):
koppelt herhaaldelijk het goedkoopste nog-niet-toegewezen kwartier aan
het duurste nog-niet-toegewezen kwartier, wijst daar een laad-/
ontlaadhoeveelheid tussen toe (begrensd door fysiek tempo + resterende
accu-headroom), zolang het paar de minimale marge (3 cent/kWh, na
rendementsverlies) overhoudt. Stopt zodra het best overgebleven paar
niet meer rendabel is — correct, want vooraf op prijs gesorteerd. Een
bekende, goede heuristiek voor voorraad-arbitrage, bewust geen
lineaire-programmering-solver (geen scipy/pulp-afhankelijkheid, blijft
een lichte HACS-integratie, en elke stap blijft individueel
controleerbaar).

Hergebruikt de v0.63.27-capaciteitsvelden
(`battery_total_capacity_sensor_entity` +
`battery_min_soc_number_entity`) — de onderliggende
capaciteitsberekening is uitgefactored naar een gedeelde
`_max_usable_battery_capacity_kwh()`, gebruikt door zowel de "dure
kwartieren"-telling als MPC.

**Bewust pure prijsarbitrage**: geen huishoudverbruik/PV-modellering,
geen nachtreserve-aftrek (dat blijft het werk van de echte beslisboom).
De geprojecteerde winst is een theoretisch maximum, geen letterlijke
aanbeveling — expliciet vermeld in het `note`-attribuut.

**Nieuwe sensor:** `sensor.mpc_advies_prijsarbitrage_plan` — geprojecteerde
winst (€) als state, volledig geplande schema als attribuut. Geen
`RestoreEntity` (elke tick een vers plan, geen hersteld verouderd
plan).

**Getest** (6 nieuwe permanente tests in `test_mpc_advisory.py`, incl.
een expliciete test die bevestigt dat er nooit een `hass.services`-call
wordt gedaan): geen plan zonder capaciteitssensoren; correcte
laden/ontladen-koppeling bij een duidelijke prijsvorm; geen paren bij
een te kleine marge (vlakke prijsdag); correcte begrenzing door
resterende headroom; nooit een device-commando; en het `note`-attribuut
vermeldt altijd expliciet het adviserende karakter.

## v0.63.34 — Monte Carlo-adviesmotor (tekortkans), uitsluitend adviserend

**Aanleiding:** vervolg op de architectuur-wishlist, tweede van de vijf
zwaardere technieken (MPC/Monte Carlo/Kalman/Digital Twin/Database-laag)
die vooraf expliciet als uitsluitend adviserend zijn afgesproken — stuurt
nooit een commando, past de werkelijke reserve-marge niet aan.

**Nieuw: `_run_monte_carlo_simulation()`.** Vult het bestaande,
deterministieke diepste-tekort-cijfer (mediaan-gebaseerd) aan met een
kansverdeling: 1000 gesimuleerde trajecten over dezelfde uur-voor-uur
diepste-tekort-berekening als `_estimate_worst_case_deficit_kwh`, elk
getrokken uit de al bestaande, geleerde geschiedenis
(`hourly_consumption_profile` voor verbruik,
`pv_hourly_bias_history` voor de Solcast-voorspellingsfout) via
bootstrap-resampling — geen aangenomen verdeling (Gauss-curve met een
gegokte standaardafwijking), maar de daadwerkelijk waargenomen
steekproeven zelf.

**Bewust geen aparte weer-/bezettingsruis**: de PV-bias-geschiedenis
weerspiegelt al impliciet weersvariatie, en er is geen bezettingsmodel
in deze integratie om uit te putten.

**Prestaties**: horizon begrensd op 48 uur; in de praktijk ~15ms voor
een realistisch 14-uursscenario met 1000 simulaties — verwaarloosbaar
binnen een 5-minuten-tick.

**Nieuwe sensor:** `sensor.monte_carlo_risico_tekortkans` — percentage
simulaties waarin het gesimuleerde tekort de daadwerkelijk beschikbare
energie overschreed, met mediaan/p10/p90 als attributen. Geen
`RestoreEntity` (elke tick een verse batch).

**Getest** (10 nieuwe permanente tests in `test_monte_carlo_advisory.py`,
incl. een expliciete test die bevestigt dat er nooit een
`hass.services`-call wordt gedaan): geen simulatie zonder
(toekomstig) goedkoopste blok; draait altijd de volle 1000 simulaties;
identieke historische samples geven nul spreiding (mediaan=p10=p90);
echte variantie in de geschiedenis geeft een reële spreiding; de
tekortkans wordt correct berekend tegen de beschikbare energie; geen
tekortkans zonder geconfigureerde sensor; horizon correct begrensd op
48 uur; nette fallback zonder geschiedenis; en nooit een
device-commando.

## v0.63.35 — Kalman filtering (SoC/PV/verbruik), uitsluitend adviserend

**Aanleiding:** vervolg op de architectuur-wishlist, derde van de vijf
zwaardere technieken die vooraf expliciet als uitsluitend adviserend
zijn afgesproken.

**Nieuw: `_KalmanFilter1D`** — een minimaal, afhankelijkheidsvrij
scalair Kalman-filter (geen numpy, blijft een lichte HACS-integratie):
elke update weegt de vorige schatting tegen de nieuwe meting af op basis
van hun relatieve onzekerheid (de Kalman-gain), berekend uit proces-ruis
(Q, verwachte drift van de werkelijke waarde tussen ticks) en meet-ruis
(R, hoe onbetrouwbaar de ruwe sensorwaarde wordt geacht). Een principieel
andere techniek dan de mediaan-gebaseerde gladstrijking die de rest van
de integratie al gebruikt.

**`_update_kalman_filters()`** past dit toe op drie live signalen:
beschikbare energie/SoC, live PV-vermogen, live huishoudverbruik
(hergebruikt `_read_corrected_consumption_power`). Proces-/meetruis-
parameters zijn onderbouwde standaardwaarden per signaal, niet
empirisch bepaald voor deze specifieke installatie — dat is expliciet
zo benoemd in zowel de code-documentatie als de sensor-attributen.

**Nooit meegenomen in enige beslissing** — de gefilterde schattingen
staan volledig los van `_get_dynamic_discharge_reserve_kwh`,
`_read_corrected_consumption_power`, of enige andere berekening die de
echte beslisboom gebruikt.

**Nieuwe sensor:** `sensor.kalman_filtering_soc_pv_verbruik` — toont
"actief"/"geen data", met de gefilterde én ruwe waarde voor alle drie
signalen als attributen. Geen `RestoreEntity` (elk filter herstelt
zichzelf binnen enkele ticks vanaf de eerstvolgende live meting).

**Getest** (9 nieuwe permanente tests in `test_kalman_filtering.py`,
incl. een expliciete test die bevestigt dat er nooit een
`hass.services`-call wordt gedaan): eerste meting zaait de schatting
exact; convergentie naar de werkelijke waarde ondanks ruis; een plotse
uitschieter wordt gedempt, niet direct overgenomen; hogere meetruis
reageert trager dan lagere; onzekerheid krimpt naarmate er meer
metingen binnenkomen; correcte koppeling aan SoC/PV/verbruik in de
coordinator; nette omgang met ontbrekende sensoren; nooit een
device-commando; en het filter behoudt zijn state over meerdere ticks
(geen reset per tick).

## v0.63.36 — Digital Twin (gesimuleerde SoC/winst), uitsluitend adviserend

**Aanleiding:** vervolg op de architectuur-wishlist, vierde van de vijf
zwaardere technieken die vooraf expliciet als uitsluitend adviserend
zijn afgesproken.

**Nieuw: `_run_digital_twin_simulation()`.** Simuleert vooruit wat de
**bestaande, regelgebaseerde logica** aan SoC/financieel resultaat zou
opleveren — als natuurlijk vergelijkingspunt naast het MPC-adviesplan
(theoretisch optimum, v0.63.33). Het verschil tussen de twee laat zien
hoeveel arbitrage-ruimte de huidige logica al daadwerkelijk benut.

**Kernontwerpkeuze**: hergebruikt bewust `self.last_timeline` — al elke
tick berekend voor de bestaande "Overzicht komende uren"-tabel op het
dashboard (v0.40.0/v0.60.0), compleet met reserve-bewuste,
prijs-prioriteit-bewuste kwartier-classificatie inclusief de secundaire
laag — in plaats van een eigen, mogelijk afwijkende classificatielogica
te verzinnen. Dit is een échte tweeling van de bestaande projectie, geen
tweede, potentieel inconsistente benadering ernaast.

Loopt die tijdlijn door en simuleert per kwartier: `manual`
(dure kwartieren) ontlaadt tegen `manual_discharge_power`, begrensd
door de resterende gesimuleerde SoC; `smart` binnen het
geïdentificeerde goedkoopste blok laadt tegen `manual_charge_power`,
begrensd door de resterende capaciteit-headroom; overige modi
(`smart_discharging`, of `smart` buiten het goedkoopste blok) geven
geen expliciete SoC-wijziging — dezelfde scope-beperking als de
MPC-adviesmotor (geen huishoudverbruik-/PV-net-load-modellering),
expliciet zo benoemd in het `note`-attribuut.

**Nieuwe sensor:** `sensor.digital_twin_gesimuleerde_soc_winst` —
geprojecteerde winst (€) als state, volledig gesimuleerd traject
(per kwartier: modus, SoC) als attribuut. Geen `RestoreEntity` (elke
tick een verse simulatie vanaf de live tijdlijn).

**Getest** (6 nieuwe permanente tests in `test_digital_twin_advisory.py`):
geen simulatie zonder tijdlijn; geen simulatie zonder
beschikbare-energie-sensor; een volledige tick produceert een traject
zonder ooit het apparaat aan te raken; ontlading correct begrensd door
resterende SoC; laden gebeurt alleen binnen het geïdentificeerde
goedkoopste blok; en `smart_discharging` laat de SoC terecht ongewijzigd.

## v0.63.37 — geen valse "voltooid" meer als er nog niets is aangesloten

**Gerapporteerd:** "wat als het goedkoopste kwartier nu start maar de
fietsen pas 2 uur later aan de lader worden gezet, maar het nog wel een
goedkoop uur is? Kan er een soort controle-cyclus op basis van
stroomverbruik worden ingebouwd?"

**Root cause, bevestigd na natrekken van de gedeelde
`_async_update_scheduled_charge_appliance()` (steelstofzuiger +
fietsladers, v0.63.12/.13):** de schakelaar gaat aan zodra het goedkope
blok begint. Als er op dat moment niets is aangesloten, blijft het
vermogen laag — en dat zag er **identiek** uit als "was aan het laden,
nu klaar" (aanhoudend laag vermogen). Met een drempel van 2 minuten en
een tick-interval van 5 minuten was **één enkele tick** al genoeg om
ten onrechte te concluderen dat de lading voltooid was, de schakelaar
weer uit te zetten en de dag als "voltooid" te markeren — nog vóórdat
er ooit iets was aangesloten. Als de fietsen dan 2 uur later alsnog aan
de lader gingen (nog steeds binnen hetzelfde goedkope blok), gebeurde
er niets meer.

**Fix:** een nieuwe, per-sessie vlag (`ever_active_this_session`,
gereset bij elke nieuwe keer dat de schakelaar aangaat) houdt bij of het
vermogen tijdens de huidige sessie **ooit** daadwerkelijk boven de
drempel is gekomen. Aanhoudend laag vermogen telt nu alleen als "echt
klaar" als dat waar is — anders blijft de schakelaar gewoon aan,
wachtend tot er daadwerkelijk iets wordt aangesloten, zolang het
goedkope blok duurt. Nieuwe status `wacht_op_apparaat` maakt dit
onderscheid zichtbaar op het dashboard/in de diagnostiek (was voorheen
niet te onderscheiden van `aan_het_laden`).

**Getest**: 3 bestaande tests bijgewerkt naar het correcte 3-fasen-
patroon (eerst een echte actieve meting, dán pas de
laag-vermogen-detectie) — deze testten voorheen onbedoeld precies het
foute gedrag. Plus 1 nieuwe, gerichte regressietest die het exact
gerapporteerde scenario natrekt: schakelaar gaat aan, blijft 10 minuten
op stand-by-vermogen staan zonder ooit uit te gaan, en pas zodra er 2
uur later daadwerkelijk stroom wordt getrokken schakelt de status naar
`aan_het_laden`.

## v0.63.38 — polling in plaats van continu aan (brandveiligheid)

**Gerapporteerd, direct na v0.63.37:** "het gevaar bij die fietsen is
dat de omvormers wel altijd aan de stroom hangen, dat is toch
brandgevaarlijk?" — terechte vervolgvraag. De v0.63.37-fix loste de
valse "voltooid"-melding op, maar had als bijwerking dat de schakelaar
nu continu aan bleef staan zolang er niets was aangesloten — mogelijk
urenlang, wat een lader/omvormer onnodig lang onder spanning laat staan
zonder toezicht.

**Fix: polling in plaats van "aan en wachten".** Sluit exact aan bij de
oorspronkelijke suggestie ("een soort 15 minuten controle cyclus... op
basis van stroomverbruik"): de schakelaar gaat kort aan (één
update-tick, ~5 minuten) om te testen of er iets is aangesloten. Wordt
niets gevonden, dan gaat hij weer uit voor een afkoelperiode van
`SCHEDULED_CHARGE_POLL_OFF_MINUTES` (15 minuten) voordat de volgende
testpoging volgt — een duty-cycle van ~25% in plaats van continu onder
spanning. Zodra er tijdens zo'n testvenster daadwerkelijk stroom wordt
getrokken, schakelt het systeem meteen over naar normaal, doorlopend
laden.

**Nieuwe status:** `test_aan` (lopende testpoging), naast het bestaande
`wacht_op_apparaat` (afkoelperiode tussen pogingen).

**Nauwkeuriger geleerde laadduur als bijeffect:** de duur-meting start
nu pas zodra er daadwerkelijk stroom wordt getrokken, niet vanaf de
allereerste testpoging — dus telt niet meer de tijd mee die is
besteed aan wachten/pollen.

**Getest**: 6 bestaande tests bijgewerkt naar de nieuwe statusnamen en
tick-volgorde (inclusief een herberekende geleerde laadduur: 8 minuten
i.p.v. 13, nu de meting pas start bij bevestigde activiteit). Plus 1
nieuwe, gerichte test die de polling-cyclus zelf natrekt: bevestigt een
~5-minuten-testvenster gevolgd door een 15-minuten-afkoelperiode, met
in totaal twee losse aan/uit-cycli in plaats van één continue
aan-periode.

## v0.63.39 — NILM-achtige apparaat-auto-detectie met bevestigingssysteem

**Aanleiding:** laatste van de architectuur-wishlist-punten. Vooraf de
haalbaarheid eerlijk doorgenomen: "echte" NILM (blinde disaggregatie
van één geaggregeerd vermogenssignaal, zonder trainingsdata) is bewust
niet gebouwd — zelfde reden als bij MPC/Monte Carlo/Kalman/Digital
Twin. In overleg gekozen voor een haalbare, eerlijke versie: bestaande
vermogen-sensoren automatisch ontdekken die nog niet elders
geconfigureerd zijn, met een expliciet bevestigingssysteem voordat er
iets wordt gevolgd, en drift-detectie na bevestiging.

**Database-laag (het laatste punt van de vijf zwaardere technieken)
bewust overgeslagen** na overleg — HA's eigen `recorder` (+ eventueel
Grafana/InfluxDB) dekt de "lange-termijn-analyse"-behoefte al beter dan
een zelfgebouwde database in een HACS-integratie zou kunnen, zonder de
risico's (schema-migraties, corruptie) daarvan.

**Nieuw: `_update_nilm_discovery()`.** Scant elke tick alle
`sensor.*`-entiteiten met een vermogens-eenheid (W/kW), sluit alle al
elders geconfigureerde entiteiten uit (accu, PV, verbruik, de benoemde
apparaten), en houdt nieuwe vondsten bij als onbevestigde kandidaten.

**Bevestigingssysteem via Home Assistant-services** (op verzoek —
"een systeem bedenken waarbij ik kan bevestigen dat iets correct is
gedetecteerd"): twee nieuwe services,
`energy_management_system.confirm_nilm_device` en `reject_nilm_device`
(beide met `entity_id` als verplichte parameter), aanroepbaar via
Ontwikkelaarshulpmiddelen → Acties. Een `services.yaml` erbij voor
nette veldbeschrijvingen in de HA-UI. Geregistreerd één keer per
HA-instantie (niet per config-entry, voorkomt een
"service-al-geregistreerd"-fout bij een opties-reload).

**Drift-detectie na bevestiging** (`_update_nilm_confirmed_devices()` +
`_finalize_nilm_device_day()`): zelfde CUSUM-principe als de
sluipverbruik-detectie (v0.63.29), maar per apparaat en
**percentage-gebaseerd** (10% dode zone, 100%-cumulatieve alarmdrempel)
in plaats van een vaste Watt-drempel — vermogensniveaus verschillen te
veel tussen apparaten voor één vaste drempel. Volgt het dagelijkse
gemiddelde vermogen per bevestigd apparaat; een aanhoudende stijging
wordt gesignaleerd als mogelijk beginnend defect, met een melding via
`appliance_notify_service`.

**Nieuwe sensoren:** `sensor.nilm_onbevestigde_kandidaten` (geen
`RestoreEntity` — elke tick vers herontdekt) en
`sensor.nilm_bevestigde_apparaten` (wél `RestoreEntity` — de geleerde
geschiedenis moet wekenlang opbouwen).

**Puur informatief**, zoals afgesproken — nergens meegewogen in
accubeslissingen.

**Getest** (14 nieuwe permanente tests: 10 in `test_nilm_discovery.py`,
4 in `test_nilm_services.py`): ontdekking van een vermogen-sensor;
niet-vermogen-sensoren worden genegeerd; al-geconfigureerde entiteiten
uitgesloten; bevestigen verplaatst correct naar de bevestigde lijst;
onbekende entiteit bij bevestigen geeft `False`; negeren voorkomt
permanent herontdekking; negeren verwijdert ook een al-bevestigd
apparaat; dagelijks gemiddelde wordt correct bijgehouden; een
aanhoudende stijging wordt gesignaleerd; nooit een device-commando;
beide services registreren correct; dubbele registratie geeft geen
fout; en beide services roepen daadwerkelijk de juiste
coordinator-methode aan.

## v0.63.40 — advies-gereedheid: wanneer is een adviesmodule betrouwbaar genoeg?

**Aanleiding:** na afronding van de acht adviserende modules (Kirchhoff
t/m NILM) gevraagd of er een advies kan worden afgegeven wanneer elke
module betrouwbaar genoeg is om er daadwerkelijk iets mee te doen.

**Kernbeslissing — bewuste eerlijkheidsscheiding, geen valse claim van
bewezen betrouwbaarheid:**

- **Vijf modules met een echte data-volwassenheid-signaal** (Kirchhoff,
  sluipverbruik, Monte Carlo, Kalman, NILM) krijgen een genuine
  gereedheidsstatus: `klaar` / `bijna_klaar` / `onvoldoende_data` /
  `kwaliteit_te_laag` / `niet_geconfigureerd` — gebaseerd op al bestaande
  interne signalen (steekproefaantallen t.o.v. hun ontwerpdrempel, of
  bij Kalman: hoever de eigen onzekerheid is gekrompen t.o.v. het
  startpunt).
- **Drie modules zonder mechanisme dat een voorspelling ooit tegen de
  werkelijkheid legt** (Weather Ensemble, MPC, Digital Twin) krijgen
  bewust **nooit** `klaar` — in plaats daarvan `structureel_beschikbaar`,
  met expliciete vermelding dat de nauwkeurigheid niet wordt gevolgd.
  Dit voorkomt een schijnbaar gereedheidsoordeel dat de integratie niet
  heeft verdiend.

**Nieuw: `_update_advisory_readiness()`.** Berekent elke tick, voor elk
van de acht modules, de status + een leesbare reden, puur op basis van
al bestaande state (geen nieuwe tracking-infrastructuur nodig — dit is
een laag bovenop wat er al werd bijgehouden).

**Nieuwe sensor:** `sensor.advies_gereedheid_8_modules` — toont het
aantal modules met status `klaar`, met de volledige uitsplitsing per
module als attribuut. Geen `RestoreEntity` (elke tick vers berekend).

**Getest** (16 nieuwe permanente tests in `test_advisory_readiness.py`):
alle drie de niveaus voor Kirchhoff (onvoldoende data, klaar,
kwaliteit te laag) en sluipverbruik (onvoldoende/bijna/klaar); expliciete
bevestiging dat Weather Ensemble/MPC/Digital Twin nooit `klaar` krijgen,
zelfs met volop data; Monte Carlo- en Kalman-convergentie; NILM-
maturiteit over meerdere apparaten heen; alle acht modules altijd
aanwezig in de uitvoer; en nooit een device-commando.

## v0.63.41 — NILM bevestigen/negeren direct vanuit het dashboard

**Gevraagd:** een overzicht in het dashboard van gedetecteerde
NILM-kandidaten, met de optie om ze direct te accepteren of te weigeren
— zonder via Ontwikkelaarshulpmiddelen → Acties te hoeven.

**Beperking eerlijk vooraf benoemd:** een kale Lovelace-dashboard (geen
extra HACS-frontend-kaart aangenomen) kan geen dynamische, onbekende-
lengte-lijst automatisch in knoppen omzetten. Opgelost met een **vaste
set van 8 sleuven** in plaats van dynamisch aangemaakte/verwijderde
entiteiten (wat de complexiteit en het risico van entity-lifecycle-
beheer had toegevoegd).

**Nieuw: `get_nilm_candidate_at_slot()`** op de coordinator — bepaalt
welke kandidaat een gegeven sleuf-index (0-7) momenteel bevat,
alfabetisch gesorteerd op `entity_id` voor een stabiele, deterministische
volgorde (geen onverwacht wisselende sleuven tussen ticks).

**16 nieuwe knop-entiteiten** (`NilmConfirmCandidateButton` /
`NilmRejectCandidateButton`, 8 sleuven × 2): elke knop toont via zijn
eigen attributen (`kandidaat_naam`, `kandidaat_vermogen_w`) welke
kandidaat er momenteel in zit, en werkt bij indrukken op *whichever*
kandidaat op dat moment in die sleuf zit — geen vaste koppeling aan één
specifieke entity_id.

**Dashboard**: een nieuwe kaartensectie op het "Overzicht"-paneel met
een tabel (Jinja-template die alle 8 sleuven doorloopt) plus de 16
knoppen eronder.

**Getest** (7 nieuwe permanente tests in `test_nilm_dashboard_buttons.py`):
een sleuf toont de alfabetisch eerste kandidaat; een lege sleuf toont
niets; bevestigen/negeren via de knop werkt op de juiste, op dat moment
gesloten kandidaat; drukken op een lege sleuf doet niets (geen crash);
sleuven verschuiven correct nadat een kandidaat is bevestigd; en de
setup registreert alle 16 sleufknoppen plus de bestaande testmelding-
knop.

## v0.63.42 — NILM-onderdelen verplaatst naar het "Apparaten"-tabblad

**Gevraagd:** alles wat apparaat-/NILM-gerelateerd is bij elkaar op het
"Apparaten"-tabblad in plaats van verspreid over "Overzicht" en
"Apparaten".

**Wijziging (puur dashboard-YAML, geen code):** de NILM-sensorrijen
(onbevestigde kandidaten, bevestigde apparaten) en de hele sleuf-tabel
+ 16 bevestigen/negeren-knoppen zijn verplaatst van het
"Overzicht"-paneel naar het "Apparaten"-paneel, direct na de bestaande
vaatwasser/wasmachine/steelstofzuiger/fietsladers-kaarten en de
"Laatste meldingen"-sectie — zodat alles rond fysieke apparaten nu op
één plek staat.

**Geen wijziging aan sensoren, knoppen, of services** — puur een
herindeling van waar bestaande kaarten in het dashboard staan.

## v0.63.43 — NILM-knoppen tonen kandidaat direct, dashboard leesbaar op mobiel

**Gerapporteerd, met screenshots:** de dashboard-tabel + generieke
knoplabels ("1 — bevestigen") werden op een smal/mobiel scherm zwaar
afgekapt en onbruikbaar — kandidaatnamen waren niet te lezen, en welke
knop bij welke kandidaat hoorde was niet duidelijk.

**Root cause:** het ontwerp vereiste kruisverwijzing tussen een aparte
tabel (sleufnummer → kandidaat) en een losse knoppenlijst met alleen
generieke sleufnummers — bij afkapping op een smal scherm viel die
koppeling volledig weg.

**Fix:** de knoppen tonen nu **zelf** direct welke kandidaat erin zit —
`name` is niet langer een statisch `_attr_name`, maar een dynamische
property die de kandidaatnaam + huidig vermogen combineert (bijv. "✅
Koelkast 82W"), met "(leeg)" voor een onbezette sleuf. Geen aparte
tabel meer nodig; de dashboard-YAML verwijdert de per-rij `name:`-
overrides zodat de echte, dynamische entiteitsnaam zichtbaar wordt, en
geeft de knoppenkaart de volle breedte (`grid_options: columns: 12`) in
plaats van een smalle kolom.

**Zijopmerking over de gerapporteerde "AB3000"/"accu_*"-kandidaten**:
dit is verwacht gedrag van de bewust brede detectie (alle
vermogens-sensoren) — vermoedelijk granulaire deelmetingen van de
Zendure-accu zelf (per-pack laad-/ontlaad-/PV-vermogen), geen losse
apparaten. Negeren via de knop is de bedoelde oplossing; nu ook
expliciet zo benoemd in de README.

**Getest** (2 nieuwe permanente tests in `test_nilm_dashboard_buttons.py`):
de knopnaam bevat de kandidaatnaam + vermogen; een lege sleuf toont
"(leeg)".

## v0.63.44 — nieuw dashboard-tabblad "Advies" voor de acht adviesmodules

**Gerapporteerd, met screenshot:** `sensor.advies_gereedheid_8_modules`
toont "0" zonder context — en gevraagd om beter te kunnen zien welke
module geschikt is voor "actieve bijsturing", het liefst op een apart
tabblad met uitgebreidere gegevens.

**Belangrijke nuance eerst expliciet herbevestigd**: gereedheid zegt
iets over hoe betrouwbaar het cijfer zelf is — niet over of het veilig
is om ergens op te sturen. Alle acht modules blijven, ongeacht hun
status, uitsluitend adviserend. Dit staat nu ook zo op het nieuwe
tabblad zelf, niet alleen in de README.

**Nieuw tabblad "Advies"** (puur dashboard-YAML, geen codewijziging):

- Introkaart met de expliciete "geen van deze stuurt iets aan"-herinnering.
- Legenda-kaart die de twee categorieën uitlegt (echte data-volwassenheid
  vs. structureel beschikbaar zonder nauwkeurigheids-tracking).
- Volledige tabel (Jinja-template, itereert over de acht modules) met
  naam, status (met icoon) en reden per module — leesbaar in één
  overzicht in plaats van acht losse regels tussen alle andere kaarten.
- Drill-down-kaart met directe links naar elke module's eigen sensor.

**Testsuite bijgewerkt**: `test_dashboard_yaml_is_valid` verwachtte
exact 5 tabbladen, nu 6.

## v0.63.45 — NILM-kandidatenattribuut begrensd (HA 16KB recorder-limiet)

**Gerapporteerd, met HA-logmelding:** `homeassistant.components.recorder.
db_schema` waarschuwde dat de attributen van
`sensor.nilm_onbevestigde_kandidaten` de maximale 16384 bytes per
attribuut overschreden — HA slaat het attribuut dan stilzwijgend
helemaal niet meer op (geen fout, maar wel verlies van
geschiedenis/debug-informatie voor dat attribuut).

**Root cause:** de bewust brede detectie ("alle sensoren met een
vermogens-eenheid") kan, met name via de Zendure-integratie's eigen
granulaire per-pack-vermogenssensoren (zoals eerder gezien: "AB3000",
"accu_*"), tientallen tot honderden kandidaten opleveren. Het volledige
`nilm_unconfirmed_candidates`-dict (entity_id, naam, vermogen, eerst-
gezien per kandidaat) als rauw attribuut opslaan groeit dan voorbij de
16KB-grens.

**Fix:** `NilmUnconfirmedCandidatesSensor` toont nu een **begrensd
voorbeeld** (standaard de eerste 20, alfabetisch gesorteerd — dezelfde
volgorde als de dashboard-sleuven) in plaats van het volledige dict, met
een apart `totaal_aantal`-attribuut dat wél het echte aantal toont, en
een verwijzing naar de diagnostiek-export (niet aan de 16KB-limiet
gebonden) voor de volledige lijst. De onderliggende
detectie/bevestigen/negeren-functionaliteit zelf is door deze cap niet
beperkt — alleen wat dit ene sensor-attribuut laat zien.

`NilmConfirmedDevicesSensor` bewust **niet** aangepast: die lijst is
door de gebruiker zelf samengesteld (via bevestigen), in de praktijk
veel kleiner, en het volledige attribuut is nodig voor de
`RestoreEntity`-herstelfunctie na een herstart.

**Getest** (5 nieuwe permanente tests in `test_nilm_attribute_size_cap.py`):
de state toont altijd het echte totaal, ook ver boven de limiet; het
voorbeeld wordt begrensd tot de limiet zodra die wordt overschreden
(met verwijzing naar diagnostiek); onder de limiet wordt alles getoond
(geen onnodige verwijzing); het voorbeeld is consistent met de
dashboard-sleufvolgorde; en een regressie-test die met 500 kandidaten
bevestigt dat de geserialiseerde attribuutgrootte ruim onder de
16KB-grens blijft.

## v0.63.46 — zelflerende voltooiingsdrempel (was een gegokte vaste waarde)

**Gerapporteerd:** het standaard-verbruik van de fietsladers ligt in de
praktijk rond 2W, ruim onder de vaste, gegokte drempel van 20W
(`FIETSLADERS_COMPLETE_THRESHOLD_W`) — met de vraag of het systeem dit
zelf kan leren in plaats van op een gegokte constante te vertrouwen.

**Fix: `_get_learned_completion_threshold_w()` + `_record_idle_power_
sample()`.** Elke meting die tijdens een testpoging (polling, v0.63.38)
wordt gedaan terwijl er nog geen bevestigde activiteit is, is een
echte stand-by-meting — deze worden bijgehouden in een begrensde
geschiedenis (`IDLE_POWER_HISTORY_LENGTH` = 20 metingen) per apparaat.
Zodra er minstens `LEARNED_THRESHOLD_MIN_SAMPLES` (5) zijn verzameld,
wordt de voltooiingsdrempel automatisch afgeleid als de mediaan van die
stand-by-metingen plus een veiligheidsmarge
(`LEARNED_THRESHOLD_MARGIN_W` = 5W, een onderbouwde maar niet
empirisch-per-installatie-geverifieerde keuze — expliciet zo benoemd
in de code-documentatie). Bij 2W stand-by dus een geleerde drempel van
~7W in plaats van de gegokte 20W. Valt terug op de vaste,
geconfigureerde drempel zolang er nog onvoldoende metingen zijn — geen
regressie voor een verse installatie.

**Toegepast op zowel de "is dit genuine actief"-check als de
"aanhoudend laag vermogen = klaar"-check** — beide gebruikten al
dezelfde drempel, en gebruiken nu dezelfde geleerde waarde.

**Zichtbaar gemaakt**: nieuwe attributen `idle_power_history_w` en
`learned_completion_threshold_w` op zowel de steelstofzuiger- als de
fietsladers-statussensor, en in de diagnostiek-export.

**Getest** (5 nieuwe permanente tests in
`test_learned_completion_threshold.py`): valt terug op de vaste drempel
zonder genoeg metingen; leert een veel lagere drempel uit waargenomen
stand-by-metingen (2W → geleerde drempel 7W); de geschiedenis blijft
begrensd tot 20 metingen; metingen tijdens de testpoging worden
daadwerkelijk vastgelegd; en echte laadstroom (honderden watts) wordt
nog steeds correct herkend tegen de nieuwe, veel lagere geleerde
drempel.

## v0.63.47 — echte oorzaak van de afkapping gevonden: apparaatnaam-voorvoegsel

**Gerapporteerd, opnieuw met screenshots:** ondanks v0.63.43's dynamische
knopnamen bleef alles afgekapt tot "E...".

**Werkelijke root cause, nu gevonden:** `_attr_has_entity_name = True`
(zoals elke andere entiteit in deze integratie) laat Home Assistant de
apparaatnaam ("Energy Management System") vóór elke weergavenaam
plakken. In een smalle naamkolom kapte dat af tot alleen "E..." — de
knop droeg intern al de juiste naam ("✅ Koelkast 82W"), maar die werd
nooit zichtbaar doordat het lange voorvoegsel als eerste werd afgekapt.

**Fix:** `has_entity_name` staat nu bewust **uit** voor deze 16
sleufknoppen (enige uitzondering in de hele integratie) — ze worden
gelezen als losstaande actie-labels, niet als apparaat-subfuncties, dus
het voorvoegsel voegt niets toe behalve lengte.

**Kaartvorm ook aangepast**: de knoppenlijst gebruikte `type: entities`
(een layout met een intrinsiek smalle naamkolom, ongeacht het
voorvoegsel-probleem) — vervangen door 16 losse
`custom:mushroom-entity-card`s in een raster (2 per rij, groen voor
bevestigen/rood voor negeren), consistent met de rest van dit
dashboard en met veel meer ruimte voor de volledige naam.

**Getest**: nieuwe permanente test bevestigt expliciet dat
`has_entity_name` uit staat op beide knoptypes, zodat een toekomstige
wijziging dit niet per ongeluk terugzet.

## v0.63.48 — knoppen ververst nu daadwerkelijk live (was structureel bevroren)

**Gerapporteerd:** "alle sleuven zijn ook leeg, als ik er overheen
hover" — ondanks een correct werkende detectie (de sensor toonde
eerder al 120 kandidaten).

**Werkelijke root cause:** `ButtonEntity` pollt, in tegenstelling tot
`SensorEntity`, niet standaard. Onze knoppen berekenen hun naam/
attributen weliswaar correct als Python-property bij elke aanroep, maar
zonder polling of een expliciete "schrijf je status nu"-melding wordt
die berekening nooit opnieuw naar Home Assistant's state-machine
weggeschreven — de weergave bleef letterlijk bevroren op het allereerste
moment dat de knop werd geregistreerd (nog vóórdat er ooit een
detectie had gelopen), en zou dat voor altijd blijven doen.

**Fix:** een luisteraar-mechanisme (`register_listener`/
`unregister_listener`/`_notify_listeners`) toegevoegd aan de
hoofdcoordinator — exact hetzelfde bewezen patroon dat de aparte
PV-nauwkeurigheids-tracker al gebruikte. Elke sleufknop registreert
zichzelf (`async_write_ha_state`) bij het toevoegen aan Home Assistant,
en de coordinator roept alle geregistreerde luisteraars aan na **elke**
update-poging — in een `finally`-blok, dus gegarandeerd ook bij een
vroege `return` in een van de vele beslistakken van de hoofdlus, en
zelfs bij een onverwachte fout.

**Bijkomend gevonden en gefixt tijdens het bouwen hiervan:** een eerdere
`str_replace`-bewerking had per ongeluk een stuk van `__init__`
(ongeveer 70 regels state-initialisatie, inclusief `self._lock`) laten
opslokken door de nieuwe `_notify_listeners()`-methode door een
samenvallende inspringing — dit veroorzaakte in eerste instantie 96
falende tests (`AttributeError: object has no attribute '_lock'`) en
een sterk vertraagde testrun. Teruggevonden en hersteld voordat dit
werd uitgeleverd.

**Testomgeving uitgebreid**: de nep-`ButtonEntity` in de testharnas
miste `async_write_ha_state`/`async_added_to_hass`/
`async_will_remove_from_hass` — toegevoegd zodat dit gedrag
daadwerkelijk getest kan worden.

**Getest** (4 nieuwe permanente tests): een knop registreert zichzelf
bij toevoeging; een knop meldt zich correct af bij verwijdering; de
coordinator meldt luisteraars ook bij een vroege `return`; en ook na
een onverwachte uitzondering.

## v0.63.49 — dashboard-kaarten omgezet naar sjabloonkaarten (naam bleef "Energy Man...")

**Gerapporteerd, opnieuw met screenshots, na v0.63.47/.48:** "nog niet
duidelijk" — de knoppen toonden nog steeds "Energy Man..." ondanks dat
`has_entity_name` uit stond en het verversen (bevestigd) correct werkte.

**Vermoedelijke root cause**: Home Assistant's entity-registry cachet
de weergavenaam (`original_name`) doorgaans bij de eerste registratie
van een entiteit. Omdat de `unique_id` van deze knoppen ongewijzigd
bleef tussen versies, herkende Home Assistant ze als "dezelfde"
entiteiten en pakte de codewijziging (has_entity_name uit) niet
automatisch op via een gewone herstart — een bekend knelpunt bij het
wijzigen van entity-naamgedrag op een al-bestaande entiteit, dat
normaliter een handmatige stap (verwijderen/opnieuw toevoegen, of de
naam-override in de entiteit-instellingen wissen) vereist.

**Fix, die dit knelpunt volledig omzeilt**: in plaats van te
vertrouwen op hóe Home Assistant de entiteitsnaam zelf berekent en
cachet, tonen de 16 dashboardkaarten nu de tekst via een eigen
sjabloon — omgezet van `custom:mushroom-entity-card` naar
`custom:mushroom-template-card` (hetzelfde patroon dat al overal elders
in dit dashboard wordt gebruikt). De kaarttekst wordt nu rechtstreeks
via Jinja (`state_attr(..., 'kandidaat_naam')` /
`state_attr(..., 'kandidaat_vermogen_w')`) uit de attributen gelezen —
die worden al sinds v0.63.48 correct ververst, en zijn nooit onderhevig
geweest aan entity-naam-caching (attributen zijn losse data, geen
"naam"). Tikken op een kaart roept de knop nog steeds aan, nu via een
expliciete `tap_action: call-service, service: button.press`.

**Geen Python-wijzigingen** — puur dashboard-YAML. Handmatig
gerenderd en gevalideerd (16 kaarten, geen duplicaten, correcte
tekstopbouw) voordat dit werd uitgeleverd.

## v0.63.50 — sleufgenoot ververst nu ook direct na bevestigen/negeren

**Gerapporteerd, met screenshot:** "werkbaar alleen als ik iets weiger
past de accepteer-kaart zich niet aan" — na het negeren van een
kandidaat bleef de bijbehorende bevestig-knop voor diezelfde sleuf de
oude, inmiddels verwijderde kandidaat tonen.

**Root cause:** een druk op een knop laat Home Assistant automatisch
alléén díe ene knop-entiteit zijn eigen status wegschrijven (ingebouwd
gedrag na `async_press()`). Het luisteraar-mechanisme uit v0.63.48
werkte weliswaar correct, maar werd alleen aangeroepen aan het einde
van de reguliere 5-minuten-update-cyclus — niet direct na een
handmatige bevestiging/weigering. De sleuf zelf schoof al meteen door
naar de volgende kandidaat (de onderliggende data was direct correct),
maar de niet-ingedrukte buurknop wist dat pas bij de eerstvolgende
tick.

**Fix:** `confirm_nilm_device()` en `reject_nilm_device()` roepen nu
zelf direct `_notify_listeners()` aan zodra de wijziging is
doorgevoerd — niet pas wachten op de volgende tick. Alle 16
geregistreerde sleufknoppen verversen daardoor onmiddellijk samen,
ongeacht welke van de twee (bevestigen/negeren) je daadwerkelijk hebt
ingedrukt.

**Getest** (3 nieuwe permanente tests): bevestigen meldt geregistreerde
luisteraars direct; negeren meldt alle geregistreerde luisteraars
direct; en een end-to-end-test die exact het gerapporteerde scenario
natrekt — twee knop-instanties voor dezelfde sleuf tonen na het indrukken
van slechts één ervan allebei correct de doorgeschoven kandidaat.

## v0.63.51 — overzichtstabel bevestigde NILM-apparaten (naam, vermogen, trend)

**Gevraagd:** een tabel met bevestigde NILM-apparaten, hun huidige
verbruik, en een trend in verbruik — drie kolommen.

**Nieuw: `get_nilm_devices_table()` + `_describe_nilm_trend()`.** Geen
nieuwe trackinglaag — het huidige vermogen wordt live uitgelezen per
apparaat, en de trend is een lichtere, granulaire aftakking van de
al bestaande CUSUM-drift-detectie (v0.63.39): vergelijkt simpelweg de
meest recente dagelijkse gemiddelde met de langere-termijn-referentie.
Een verschuiving van >5% is al zichtbaar (`↗ licht stijgend` /
`↘ dalend` / `→ stabiel`), ruim vóórdat die de 10%-aanhoudende-
alarmdrempel van de bestaande detectie zou bereiken. Bij een
daadwerkelijk gesignaleerde, aanhoudende afwijking toont de trend-kolom
expliciet "mogelijk defect" met het geschatte percentage. Alfabetisch
gesorteerd voor een voorspelbare volgorde.

**Beschikbaar als `tabel`-attribuut** op de al bestaande
`sensor.nilm_bevestigde_apparaten` (geen nieuwe entiteit nodig) en in
de diagnostiek-export.

**Dashboard**: nieuwe markdown-tabelkaart op het "Apparaten"-paneel,
direct boven de bevestigen/negeren-knoppen — toont "Nog geen apparaten
bevestigd" als de lijst leeg is, anders een nette driekoloms-tabel.

**Getest** (8 nieuwe permanente tests in `test_nilm_devices_table.py`):
elke rij heeft precies de drie gevraagde kolommen; alfabetisch
gesorteerd; onbekende trend zonder genoeg geschiedenis; stabiel binnen
de marge; stijgend/dalend boven de drempel, correct onderscheiden van
een aanhoudende, gesignaleerde afwijking; en een lege tabel zonder
bevestigde apparaten.

## v0.63.52 — apparaten-lijst leesbaar op smal scherm, lege sleuven verborgen

**Gerapporteerd, met screenshots:** "al beter, echter tabel niet in 1
oogopzicht duidelijk inzichtelijk, en knoppen mogen verdwijnen wanneer
een sleuf leeg is".

**Fix 1 — apparatenoverzicht als lopende lijst in plaats van een
markdown-tabel.** Een `|kolom|kolom|kolom|`-markdown-tabel werd op een
smal scherm per kolom apart onder elkaar gestapeld (eerst alle namen,
dan een lange losse lijst met alleen vermogens, dan een lange losse
lijst met alleen trends) — onmogelijk in één oogopzicht te lezen. Elke
rij toont nu gewoon "**Naam** — vermogen — trend" op één regel via een
markdown-lijst (`- `-items, die altijd los blijven staan, in
tegenstelling tot losse tekstregels die markdown zonder lege regel
ertussen samenvoegt tot één alinea). Buigt natuurlijk mee op elke
schermbreedte, geen kolomopmaak nodig.

**Fix 2 — lege sleuf-knoppen verdwijnen nu uit beeld.** Elke van de 16
sleufknop-kaarten heeft nu een `visibility`-conditie
(`condition: template`) die rechtstreeks leest of
`state_attr(entity, 'kandidaat_entity_id')` niet `None` is. Een lege
sleuf neemt geen ruimte meer in op het dashboard; zodra er een nieuwe
kandidaat instroomt en de sleuf bezet raakt, verschijnt de kaart
vanzelf weer (dezelfde live-verversende attributen die al sinds
v0.63.48/.50 correct bijgewerkt worden).

**Geen Python-wijzigingen** — puur dashboard-YAML. Handmatig
gerenderd en gevalideerd (16 kaarten met visibility, correcte
lijstopbouw met/zonder data) voordat dit werd uitgeleverd.

## v0.63.53 — echte oorzaak van de tabel-onleesbaarheid gevonden: vaste kaarthoogte

**Gerapporteerd, met screenshot van een wél-goed-werkende tabel:**
"tabel er ongeveer zo uit laten zien" — verwijzend naar de vergelijkbare
3-koloms-tabel op het "Advies"-tabblad, die prima leesbaar rendert.

**Echte root cause, nu gevonden door de twee kaarten te vergelijken:**
niet de tabelopmaak zelf — v0.63.52's omzetting naar een lopende lijst
loste dus het verkeerde probleem op. De NILM-tabelkaart zat, in
tegenstelling tot de Advies-tabelkaart (een kale kaartenlijst zonder
vaste afmeting), in een grid-layout met een **vaste hoogte**
(`grid_options: rows: 5`). Bij genoeg bevestigde apparaten paste de
tabel daar niet meer in, met inklappen/overlappen tot gevolg.

**Fix:** teruggezet naar een echte markdown-tabel (zoals gevraagd),
met `grid_options: rows: auto` in plaats van een vaste waarde — de
kaart groeit nu automatisch mee met het aantal bevestigde apparaten,
net als de Advies-tabel dat vanzelf al deed.

**Gecontroleerd of dit probleem nog ergens anders in het dashboard
sluimert**: enige andere dynamische (Jinja-`for`-lus) markdown-tabel is
de Advies-tabel zelf, die al geen vaste hoogte heeft — geen verdere
risicoplekken gevonden.

**Geen Python-wijzigingen** — puur dashboard-YAML. Handmatig
gerenderd en gevalideerd voordat dit werd uitgeleverd.

## v0.63.54 — vaatwasser/wasmachine-"goedkoop moment"-melding apart uit te zetten

**Gevraagd:** geen melding meer voor "Goedkoop moment voor de
vaatwasser/wasmachine" (v0.47.0's apparaat-gereed-suggestie).

**Bewust geen simpele "notify-service leegmaken"-oplossing**:
`appliance_notify_service` wordt gedeeld door veel andere, ongerelateerde
meldingstypes (modus-wijziging, steelstofzuiger/fietsladers-klaar,
sluipverbruik-detectie, NILM-afwijkingen) — die leegmaken had al die
andere, waarschijnlijk wél gewenste meldingen ook stilgelegd.

**Fix: een nieuwe, dedicated switch.** `appliance_ready_notifications_
enabled` (standaard `True`, ongewijzigd gedrag) op de coordinator,
met een nieuwe `switch.vaatwasser_wasmachine_meldingen`-entiteit
(`RestoreEntity`, zelfde patroon als de bestaande overrule-switches).
`_check_and_notify_appliance_ready()` controleert deze vlag als eerste
en stopt direct als hij uit staat — vóór er ooit een
`_dispatch_notification`-aanroep plaatsvindt.

**Testomgeving uitgebreid**: de nep-`SwitchEntity` in de testharnas
miste `async_write_ha_state` — toegevoegd (zelfde gat als eerder bij
`ButtonEntity` gevonden en gefixt).

**Getest** (6 nieuwe permanente tests in
`test_appliance_ready_notification_toggle.py`): standaard aan; melding
wordt verstuurd als de switch aan staat; geen melding als de switch uit
staat; het uitzetten van deze switch heeft geen effect op andere
meldingstypes via dezelfde notify-service; de switch-entiteit
weerspiegelt en wijzigt de coordinator-vlag correct in beide richtingen;
en de uit-stand overleeft een herstart.

## v0.63.55 t/m v0.63.58 — Klimaat-tabblad: geleerde woonkamertemperatuur-projectie

**Gevraagd, in meerdere stappen**: eerst een airco-verwachting op basis
van woonkamertemperatuur (v0.63.55), toen uitgebreid met rolluikstand +
een 24-uurs uurlijkse temperatuurprojectie op basis van de KNMI/
OpenWeatherMap-buitentemperatuur-voorspelling (v0.63.56), daarna
tweeledige betrouwbaarheid — "indicatief" vs "betrouwbaar" (v0.63.57),
en tot slot correctie op de actueel gemeten waarde (v0.63.58).

### v0.63.55 — Airco-verwachting op basis van woonkamertemperatuur

Nieuw: `_update_living_room_airco_prediction()` — echte anticipatie, niet
alleen "staat de airco nu aan". Gebruikt hetzelfde "wacht af en
bevestig later"-patroon als de PV-nauwkeurigheids-tracker: elke
temperatuurmeting (1°C-bakken) wordt gequeued en 60 minuten later
bevestigd als de airco in die periode is aangeslagen. Kort, glijdend
venster per bucket (niet seizoensgebonden) — spring/herfst kan
dag-afhankelijk zijn. Luchtvochtigheid bijgehouden als context.
Nieuwe sensor: `sensor.airco_verwachting_woonkamertemperatuur`.

### v0.63.56 — Rolluikstand + 24-uurs temperatuurprojectie

Nieuwe configvelden `living_room_shutter_entity_1`/`_2`, gecombineerd
tot "beide_dicht"/"gedeeltelijk"/"beide_open". Nieuw geleerd:
verandersnelheid (°C/uur) van de woonkamertemperatuur per combinatie
van buitentemperatuur-bucket (2°C) × rolluikstand × airco-status
("uit"/"verwarmen"/"koelen", via `hvac_action`) — bewust **zonder
bewolking** als aparte dimensie (bevestigd met de gebruiker: een
volledig model zou honderden cellen opleveren die maandenlang
onvoldoende data zouden tonen).

Eerste gebruik van `weather.get_forecasts` met een échte respons in
deze integratie (`_async_fetch_hourly_outdoor_forecast`) — nieuw
terrein, foutbestendig geïmplementeerd. Tijdens het bouwen ontdekt en
gefixt: een tik-voor-tik-snelheidsberekening (elke 5 min) was veel te
ruisgevoelig voor zo'n langzaam fysiek proces — herontworpen naar een
"anker"-aanpak die over ongeveer een uur meet.

### v0.63.57 — Twee betrouwbaarheidsniveaus

`get_climate_rate()` geeft nu "onvoldoende_data"/"indicatief" (≥5
samples)/"betrouwbaar" (≥15 samples). De projectie berekent voortaan
twee parallelle reeksen per uur (`kort_termijn_temp_c` en
`betrouwbaar_temp_c`), niet twee losse modellen — beide bevriezen op
het voorgaande uur zolang hun eigen drempel niet is gehaald.

### v0.63.58 — Correctie op de actueel gemeten waarde

Gesplitst in twee delen met eigen ritme:
`_async_maybe_refresh_outdoor_forecast()` haalt de weersvoorspelling
nog steeds maar eens per 30 minuten op (een échte, dure
service-aanroep), maar `_recompute_climate_trajectory()` — goedkoop,
geen netwerk-aanroep — draait elke tick en verankert de projectie
steeds opnieuw aan de actueel gemeten temperatuur. Zonder deze
scheiding zou de projectie tot 30 minuten kunnen wegdrijven van wat er
intussen echt gemeten wordt.

**Nieuwe sensor**: `sensor.klimaat_projectie_woonkamertemperatuur`
(`RestoreEntity` — het geleerde snelheidsmodel moet weken opbouwen).
**Nieuw dashboard-tabblad "Klimaat"**: live context-kaarten (temperatuur,
luchtvochtigheid, buitentemperatuur, rolluikstand, airco-status,
airco-verwachting), een betrouwbaarheid-legenda, en **twee tabellen**
(kort-termijn/indicatief en betrouwbaar), elk met tijd, voorspelde
buitentemperatuur, voorspelde woonkamertemperatuur, en
betrouwbaarheidsniveau per uur.

**Puur informatief**, zoals bij alle andere adviesmodules — stuurt
nooit een commando, weegt niet mee in accubeslissingen.

**Getest**: 26 nieuwe permanente tests in `test_climate_tab.py`
(rolluikstand-combinaties, airco-statuslabels, live buitentemperatuur
met fallback, snelheid-leren inclusief staleness-guard en begrensd
venster, weersvoorspelling-ophalen inclusief foutafhandeling,
projectie met beide betrouwbaarheidsniveaus, throttling, en de
correctie-op-actuele-waarde binnen het ophaal-throttle-venster) + 10
tests in `test_living_room_airco_prediction.py`.

## v0.63.59 — arbitrage-laden negeerde vermijdbaar zonoverschot tijdens smart_discharging

**Gerapporteerd, met diagnostiek-export en dashboard-screenshot:** "de
accu wordt nu toch weer ingesteld op smart_discharging terwijl ik juist
wil om verder te laden omdat vanavond vele dure uren zijn" — ondanks
zowel `arbitrage_charging_enabled` als `learning_only` correct
ingesteld (bevestigd via de aangeleverde diagnostiek: marge
€0,1709/kWh, ruim boven de drempel).

**Root cause, gevonden via de diagnostiek-cijfers**: er stond op dat
moment 2858W aan zonoverschot. Arbitrage-laden's "zon-prioriteit"-logica
zag dat overschot ruim genoeg om het gewenste laadvermogen te dekken,
en deed daarom bewust niets — met de aanname "de bestaande
`smart`-modus vangt dit toch al zelf op". Die aanname bleek in dit
geval niet te kloppen: de terugvalmodus was hier niet `smart` maar
`smart_discharging` (laden uitstellen, want er was al genoeg om te
overbruggen tot het goedkope blok) — en bevestigd met de gebruiker:
`smart_discharging` dekt alléén het huishoudverbruik en laadt **niet**
bij vanuit een zonoverschot. Dat overschot bleef daardoor volledig
onbenut in plaats van gratis in de accu te belanden.

**Fix**: `_get_arbitrage_charge_power()` krijgt nu `should_postpone_
charging` als parameter. Zou de accu zonder ingrijpen in
`smart_discharging` terechtkomen (in plaats van `smart`), dan wordt nu
bewust het **volle** gewenste laadvermogen ingesteld in plaats van
alleen het net-gat boven het zonoverschot — de fysieke PV/net-verdeling
gebeurt vanzelf bij de meter (zon dekt wat ze kan, net vult de rest
aan), dus dit koopt niet meer van het net dan nodig, het voorkomt
alleen dat het zonoverschot verloren gaat.

**Getest** (2 nieuwe permanente tests in `test_arbitrage_charging.py`,
rechtstreeks op `_get_arbitrage_charge_power` om deze beslissing los te
testen van de (ongerelateerde) reserve-berekening die
`should_postpone_charging` zelf bepaalt): vol zonoverschot met
`should_postpone_charging=True` → nu het volle doelvermogen; hetzelfde
scenario met `should_postpone_charging=False` → nog steeds `None`
(oorspronkelijk, correct gedrag voor de `smart`-terugval blijft intact).

## v0.63.60 — zonoverschot vastleggen via smart-modus, niet manual

**Teruggekoppeld direct na v0.63.59:** "Nee met arbitrage aan moet hij
naar smart niet naar manual" — de vorige fix loste het probleem
(zonoverschot bleef onbenut tijdens smart_discharging) inhoudelijk al
op, maar deed dat door een geforceerde **manual**-laadopdracht op het
volle doelvermogen. Dat was zwaarder dan nodig: er is in dit scenario
namelijk helemaal geen actieve netaankoop nodig, het zonoverschot dekt
het doelvermogen al volledig uit zichzelf.

**Fix**: `_get_arbitrage_charge_power()` geeft nu in dit specifieke
geval `None` terug (geen netaankoop nodig) en zet een nieuwe vlag,
`_arbitrage_wants_smart_over_postpone`. De hoofdbeslisboom herkent die
vlag en schakelt dan gewoon over naar de gewone **`smart`**-modus
(nieuwe reden: `arbitrage_solar_capture`) in plaats van
`smart_discharging` — die vangt het zonoverschot vanzelf op via
P1-volgend laden, exact zoals ze dat altijd al doet wanneer er geen
sprake is van laden uitstellen. Geen handmatig commando, geen
expliciete netaankoop.

**Tijdens het testen ontdekt**: de bestaande testfixture
(`_price_fn_cheap_now_expensive_later`, cheap vóór 14u) bleek "nu" zélf
al als het goedkoopste moment van de dag te zien, waardoor
`should_postpone_charging` er nooit betrouwbaar op `True` mee te
forceren was via de gebruikelijke techniek (een vlak, laag
verbruiksprofiel) — dat verklaarde ook waarom een eerdere test
toevallig slaagde: arbitrage vuurde daar sowieso al af, ongeacht wat
`should_postpone_charging` deed. De nieuwe test isoleert dit daarom
netjes door `_should_postpone_charging` zelf te monkeypatchen naar
`True`, in plaats van op een toevallig scenario te vertrouwen.

**Getest** (2 nieuwe/bijgewerkte permanente tests in
`test_arbitrage_charging.py`): de "zon dekt het doelvermogen al"-cases
geven nu `None` + de juiste vlag terug (in beide varianten: met en
zonder `should_postpone_charging`); en een end-to-end-test die
bevestigt dat de volledige beslisboom bij die vlag daadwerkelijk
`select.select_option` met `option: smart` aanroept, met reden
`arbitrage_solar_capture` — niet `manual`.

## v0.63.61 — arbitrage-laden staat nu standaard aan

**Gevraagd:** "Arbitrage moet naar herstart standaard aan staan".

**Fix**: de coordinator's standaardwaarde voor `arbitrage_charging_
enabled` gaat van `False` naar `True`. Dit raakt alleen een verse
installatie of het allereerste moment vóórdat er ooit een status is
hersteld — `ArbitrageChargingSwitch.async_added_to_hass()` overschrijft
deze standaardwaarde nog steeds met de eerder opgeslagen status zodra
die bestaat, dus zet je de schakelaar zelf uit, dan blijft die na een
herstart gewoon uit, exact zoals elke andere schakelaar in deze
integratie zich gedraagt.

**Getest** (1 nieuwe permanente test): een verse coordinator (geen
eerdere herstelde status) heeft `arbitrage_charging_enabled == True`.
Volledige testsuite gecontroleerd op impliciete aannames over de oude
standaardwaarde — geen gevonden, alle bestaande tests zetten de vlag
al expliciet naar de gewenste waarde voor dat scenario.

## v0.63.62 — apparatenoverzicht definitief teruggezet naar een lopende lijst

**Gerapporteerd, met screenshot:** "sorry dat ik het zeg maar de
weergave is nog steeds waardeloos" — ook ná v0.63.53's hoogte-fix
(`grid_options: rows: auto`) bleef de tabel op een smal scherm
onleesbaar: alleen de "Apparaat"-kolom was zichtbaar, met lange, over
meerdere regels afgebroken apparaatnamen.

**Root cause, ditmaal definitief**: niet de hoogte (die was al
gefixt), maar de **breedte**. De NILM-apparaatnamen (bijv. "Airco
Woonkamer Compressor geschat energieverbruik") zijn veel langer dan de
korte, vaste modulenamen op de wél-goed-werkende Advies-tabel — een
3-koloms-tabel met zulke lange labels in de eerste kolom loopt op een
smal scherm alsnog vast, hoogte-fix of niet.

**Fix**: definitief terug naar een lopende lijst (zoals kortstondig al
geprobeerd in v0.63.52, toen nog om de verkeerde reden teruggedraaid).
Elke rij toont "**Naam** — vermogen — trend" als los markdown-
lijstitem — dat buigt bij een lange naam gewoon natuurlijk mee
(woordafbreking) in plaats van in een vaste kolombreedte te knijpen,
ongeacht hoe lang de apparaatnaam is.

**Geen Python-wijzigingen** — puur dashboard-YAML. Handmatig
gerenderd met de exacte lange namen uit het gerapporteerde screenshot
voordat dit werd uitgeleverd.

## v0.63.63 — apparatentabel als eigen kaart, losgetrokken uit de gedeelde grid-wrapper

**Gerapporteerd, met vergelijkingsscreenshot** van de wél-goed-werkende
Advies-tab: "volgens mij moet de tabblad opbouw gelijk zijn aan deze".

**Root cause, bevestigd door de twee tabbladen te vergelijken:** op de
Advies-tab staat "Alle acht modules" als een **eigen, losstaande kaart**
direct in de tabblad-lijst (geen gedeelde wrapper) en krijgt daardoor
zijn volle, onafhankelijke breedte in Home Assistant's Sections-layout.
Op de Apparaten-tab zat de apparatentabel echter genest in dezelfde
`type: grid`-kaart als de NILM-sensorenlijst, de instructietekst, de
"Bevestigen/negeren"-kop en alle 16 sleufknoppen. Die hele wrapper werd
door de Sections-layout als **één enkel item** behandeld en kreeg
daardoor zelf een smalle breedte — de "columns: 12" die de kinderen
daarbinnen opgaven regelt alleen hun onderlinge verdeling binnen die
al-smalle kaart, niet de breedte van de kaart zelf op de pagina.

**Fix**: de apparatentabel is losgetrokken tot een eigen, top-level
kaart in de tabblad-lijst — exact hetzelfde patroon als de Advies-tab's
"Alle acht modules". De resterende NILM-onderdelen (sensorenlijst,
sleufknoppen) blijven in hun eigen, kleinere grid-wrappers staan, nu
gescheiden van de tabel.

**Geen Python-wijzigingen** — puur dashboard-YAML herstructurering.
Gevalideerd (YAML correct, template rendert, kaart aantoonbaar als
top-level item aanwezig) voordat dit werd uitgeleverd.

## v0.63.64 — persistentie-gat gevonden: zelflerende voltooiingsdrempel overleefde geen herstart

**Gevraagd:** een controle of alle vandaag toegevoegde, zelflerende
data daadwerkelijk een herstart overleeft.

**Gat gevonden bij het nalopen**: `SteelstofzuigerStatusSensor` en
`FietsladersStatusSensor` erfden alleen over van de niet-herstellende
diagnostiek-basisklasse (`_CoordinatorDiagnosticSensor`), geen
`RestoreEntity`. Dat betekende dat zowel `idle_power_history_w` (de
stand-by-metingen achter de zelflerende voltooiingsdrempel, v0.63.46 —
vandaag toegevoegd) als `duration_history_minutes` (de geleerde
laadduur, al langer bestaand) bij elke Home Assistant-herstart
stilzwijgend terugvielen naar een lege lijst. Het leerproces begon dus
telkens weer bij nul.

**Alles daarbuiten gecontroleerd en in orde bevonden**: de
airco-verwachting-sensor, de klimaat-projectie-sensor, de
"Vaatwasser/wasmachine-meldingen"-schakelaar en de
"Arbitrage-laden"-schakelaar zijn allemaal correct `RestoreEntity` en
herstellen hun geleerde data/status bij het opstarten. De
NILM-apparatentabel heeft geen eigen opslag nodig — die leunt op de
al bestaande, wél opgeslagen bevestigde-apparatenlijst.

**Fix**: beide status-sensoren zijn nu ook `RestoreEntity` en
herstellen zowel `idle_power_history_w` als `duration_history_minutes`
bij het opstarten.

**Getest** (5 nieuwe permanente tests in
`test_appliance_learning_persistence.py`): beide histories worden voor
beide apparaten correct hersteld uit een eerdere status; en een verse
installatie (geen eerdere status) crasht niet en laat de net
geïnitialiseerde lege geschiedenis met rust.

## v0.63.65 — arbitrage-laden is nu standaardgedrag, geen aparte schakelaar meer

**Aanleiding:** een gerapporteerde snelle wisseling tussen `manual` en
`smart_discharging` (elke 15-30 sec i.p.v. de bedoelde 5 minuten) in
een diagnostiek-export leidde tot een bredere discussie over hoe
arbitrage-laden zou moeten werken. Uiteindelijk: "ik denk dat arbitrage
er helemaal uit kan" — in plaats van een apart, opt-in mechanisme met
een eigen schakelaar, moet het gewoon **standaardgedrag** zijn: tijdens
een goedkoop moment blijft de accu doorladen richting vol (net als
zonoverschot), tenzij er geen winstgevend duur moment later vandaag is.

**Bevestigd bij het narekken van de beslisboom**: de arbitrage-check
stond al vóór zowel de "laden uitstellen"- als de gewone
"smart"-aftakking. Het enige dat nodig was: de aan/uit-schakelaar
verwijderen zodat de winst-marge-check (die al bestond en beschermt
tegen onnodig inkopen) altijd meedraait, zonder handmatige activering.

**Verwijderd**: `switch.arbitrage_laden` (`ArbitrageChargingSwitch`),
de `arbitrage_charging_enabled`-vlag en bijbehorende setter op de
coordinator, het diagnostiek-veld, en de dashboardkaart. De
onderliggende winst-marge-logica (`_get_arbitrage_charge_power`,
inclusief de zon-prioriteit en de v0.63.60-fix voor het
smart-vs-manual-onderscheid) blijft ongewijzigd — die draait nu gewoon
altijd.

**Getest**: bestaande arbitrage-tests aangepast (verwijderde,
overbodige `arbitrage_charging_enabled = True`-regels opgeschoond) +
2 vervangende tests: bevestigt dat er geen winstgevende arbitrage
optreedt zonder een profijtelijke marge (zonder dat daar een schakelaar
voor nodig is), en bevestigt dat de `ArbitrageChargingSwitch`-klasse
niet meer bestaat.

## v0.63.66 — bevestigde NILM-apparaten opgeslagen via eigen Store (16KB-limiet)

**Gerapporteerd (recorder-log):** "State attributes for
sensor...nilm_bevestigde_apparaten exceed maximum size of 16384 bytes.
This can cause database performance issues; Attributes will not be
stored" — bij 59 bevestigde apparaten (elk met een eigen geleerde
CUSUM-geschiedenis) plus de recent toegevoegde `tabel`-attribuut, groeit
dit ruim voorbij de 16KB die Home Assistant's recorder per
entiteit-attribuut toestaat.

**Bewust géén simpele afkapping** (zoals bij de kandidatenlijst,
v0.63.45): die lijst is user-curated en bedoeld om maandenlang op te
bouwen — een preview-afkapping op het HA-attribuut zou daadwerkelijk
data laten verdwijnen bij een herstart, omdat de `RestoreEntity` tot nu
toe DIT attribuut als bron van waarheid gebruikte.

**Fix, structureel**: een eigen `Store` (`homeassistant.helpers.
storage.Store`, een los JSON-bestand onder `.storage/` — hetzelfde
mechanisme dat Home Assistant's eigen `restore_state` gebruikt) is nu
de bron van waarheid voor bevestigde apparaten + genegeerde entiteiten.
Volledig los van de recorder's staat-geschiedenis-database en zijn
grootte-limiet — geen enkel plafond meer. Wordt geladen tijdens
`coordinator.async_setup()` (vóór de eerste tick), en opgeslagen na elke
bevestiging/negering en na elke dagelijkse CUSUM-afronding.

**Sensor-attribuut nu puur cosmetisch begrensd**: `apparaten`/`tabel`
tonen een voorbeeld van de eerste 20 (net als de kandidatenlijst), met
het werkelijke totaal en een verwijzing naar de diagnostiek-export voor
de volledige lijst — maar dit is nu alleen nog om de recorder-melding
te voorkomen, niet meer de bron voor wat bij een herstart wordt
teruggehaald.

**Automatische, eenmalige migratie** voor bestaande installaties: is de
nieuwe Store nog leeg (nooit eerder geschreven), dan valt de sensor
terug op zijn eigen oude, herstelde HA-status en slaat die meteen op in
de nieuwe Store — die terugval-route is daarna nooit meer nodig.

**Testomgeving uitgebreid**: een minimale, functionele nep-`Store` toegevoegd
aan de testharnas (backing-dict leeft op de `FakeHass`-instantie, dus
vanzelf per test gereset).

**Getest** (11 nieuwe permanente tests in
`test_nilm_confirmed_devices_persistence.py`): attribuut-begrenzing
(`apparaten`/`tabel`) bij veel apparaten, met correct totaal en
diagnostiek-verwijzing; klein blijft onafgekapt; bevestigen/negeren/
dagelijkse-CUSUM-afronding slaan daadwerkelijk op in de Store; laden
uit de Store vult de coordinator-status correct; laden bij een lege
Store laat bestaande status met rust; en de eenmalige migratie werkt
correct in beide richtingen (valt terug wanneer de Store leeg is, wint
niet wanneer de Store al data heeft).

## v0.63.67 — arbitrage_solar_capture: twee vergeten aansluitingen gefixt

**Gerapporteerd, met screenshots:** "Verwachting zegt nog steeds smart
discharge" — ondanks dat "Werkelijke modus" al correct `smart` toonde
sinds v0.63.60, bleef "Verwachte modus (logica)" op `smart_discharging`
staan. Ook toonde de uitlegtekst "Onbekende reden:
arbitrage_solar_capture" in plaats van een echte uitleg.

**Root cause, beide keren dezelfde soort fout**: bij het introduceren
van de reden `arbitrage_solar_capture` in v0.63.60 is vergeten om die
ook toe te voegen aan twee plekken die per-reden expliciet zijn
opgesomd:

1. **`REASON_TO_MODE`** — `_finish_decision_tick()` gebruikt
   `REASON_TO_MODE.get(self.last_reason, self.last_expected_mode)` om
   de weergegeven "verwachte modus" te corrigeren naar wat er
   daadwerkelijk is besloten. Zonder een item voor deze reden viel dit
   terug op de **vorige tick's** waarde (vaak nog `smart_discharging`
   van een eerdere beslissing) in plaats van correct naar `smart` te
   resolven — nu toegevoegd.
2. **De uitlegtekst-generator** (`_build_explanation`) — had geen
   `elif reason == "arbitrage_solar_capture"`-tak, dus viel terug op de
   generieke "Onbekende reden: ..."-melding. Nu een volwaardige uitleg
   toegevoegd (vermeldt de winstmarge en het zonoverschot, net als de
   bestaande `arbitrage_charging`-uitleg).

**Getest** (2 nieuwe permanente tests): `_finish_decision_tick()` met
deze reden en een bewust verouderde "verwachte modus" resolvt correct
naar `smart`; en `_build_explanation()` met deze reden bevat geen
"onbekende reden" meer en vermeldt het zonoverschot en de smart-modus.

## v0.63.68 — nieuwe service: NILM-apparaat verwijderen en opnieuw laten beoordelen

**Gevraagd:** "Hoe kan ik de NILM apparaat verwijderen en opnieuw
beoordelen?" — de bestaande `reject_nilm_device` verwijdert een
apparaat weliswaar uit de bevestigde lijst, maar zet het meteen op de
permanente negeer-lijst (nooit meer voorgesteld), wat niet is wat je
wilt als je het apparaat juist opnieuw met een verse basislijn wilt
laten beoordelen.

**Nieuw: `unconfirm_nilm_device()` + de service
`energy_management_system.unconfirm_nilm_device`.** Verwijdert een
bevestigd apparaat inclusief zijn volledige geleerde geschiedenis
(basislijn, drift-status, dagelijkse gemiddelden) — maar voegt het,
in tegenstelling tot negeren, **niet** toe aan de permanente
negeer-lijst. Bij de eerstvolgende NILM-scan verschijnt het apparaat
daardoor gewoon weer als nieuwe, onbevestigde kandidaat, klaar om met
een schone lei opnieuw bevestigd te worden. Bruikbaar wanneer het
fysieke apparaat is vervangen of gerepareerd en de oude basislijn niet
meer relevant is.

Persisteert naar de dedicated Store (v0.63.66) en meldt geregistreerde
luisteraars direct, net als confirm/reject.

**Getest** (5 nieuwe permanente tests): de coordinator-methode
verwijdert correct zonder te blokkeren; geeft `False` terug als het
apparaat niet bevestigd was; het apparaat verschijnt daadwerkelijk
weer als kandidaat bij de eerstvolgende scan (de kern van deze
functie); slaat op naar de Store; en de service zelf roept de
coordinator correct aan.

## v0.63.70 — verwacht schema kende de solar-capture-override nog niet

**Gerapporteerd, met screenshots:** "Zie nu alleen in het verwachtte
schema nog smart_discharging staan op dit tijdstip" — de live
beslissing toonde al correct `smart` (dankzij de
`arbitrage_solar_capture`-override uit v0.63.60), maar het "Overzicht
komende uren"-schema bleef voor exact datzelfde moment
`smart_discharging` tonen.

**Root cause**: `_build_forecast_timeline()` (de functie achter dat
schema) heeft al langer een eigen mechanisme om de "nu"-rij te
overschrijven met de live beslissing, zodat die altijd matcht met wat
er daadwerkelijk gebeurt — maar dat mechanisme kende alleen
`live_is_expensive`/`live_should_postpone_charging`. De nieuwere
`arbitrage_solar_capture`-override (v0.63.60) was daar nooit aan
toegevoegd, dus bleef de "nu"-rij de kale, prijs-alleen-projectie tonen
in plaats van de echte, zon-bewuste beslissing.

**Fix**: een nieuwe parameter `live_should_capture_solar` toegevoegd
aan `_build_forecast_timeline()`. De onderliggende zon-overschot-check
wordt nu vroeg in de tick geëvalueerd (uitsluitend voor deze
projectie — de echte beslissing verderop in dezelfde tick berekent
gewoon opnieuw en overschrijft veilig dezelfde staat), en gebruikt om
de "nu"-rij correct op `smart` te zetten wanneer die override actief
is, in plaats van `smart_discharging`.

**Getest** (3 nieuwe permanente tests in
`test_schedule_solar_capture_override.py`): de override zet de huidige
rij op `smart`; zonder de override blijft het bestaande gedrag
(`smart_discharging`) intact; en een volledige tick (met een echt
prijsverschil zodat de marge-check slaagt, en `_should_postpone_
charging` gemonkeypatcht naar `True` om het scenario betrouwbaar te
forceren) bevestigt dat `last_timeline`'s huidige rij daadwerkelijk
`smart` toont wanneer `last_reason == "arbitrage_solar_capture"`.

## v0.63.71 — zon-overschot-beslissing gebruikt nu de Solcast-verwachting, niet de live meting

**Gerapporteerd, met screenshots en een eigen, correct vermoeden:**
"Modus toch weer naar manual, heb nu een vermoeden, hij kijkt naar het
live PV opbrengst en niet naar de verwachtte zon" — de modus wisselde
binnen 7 minuten van `smart` (zonoverschot 2668W, dekte het
doelvermogen volledig) naar `manual` (zonoverschot gedaald naar 1707W,
dus een net van 293W bijgekocht) — een klassiek gevolg van het
reageren op een ogenblikkelijke meting in plaats van een gedempte of
voorspelde waarde.

**Bevestigd**: `_get_arbitrage_charge_power()` las `pv_power_w` via
`self._read_sensor_float(pv_entity)` — de live, ogenblikkelijke
PV-sensorwaarde, zonder enige demping.

**Bewust géén simpele mediaan-demping** (het eerste voorstel) — de
gebruiker gaf expliciet aan de Solcast-voorspelling te bedoelen, niet
een gladgestreken live meting. Nieuw: `_get_expected_pv_power_w(now)`
— zoekt het half-uur-interval in de al bestaande Solcast
`detailedForecast`-parsing (`_get_pv_forecast_entries`) dat "nu" bevat,
en corrigeert de ruwe Solcast-schatting met de **al bestaande**, per
uur geleerde bias-ratio (`learned_pv_hourly_ratio`) — geen nieuwe
koppeling nodig, hergebruik van bestaande infrastructuur. Valt terug op
de live meting als er geen `solar_forecast_sensor_entity` is
geconfigureerd (ongewijzigd gedrag in dat geval).

`_get_arbitrage_charge_power()` gebruikt deze verwachte waarde nu als
primaire bron voor het zonoverschot in de arbitrage/solar-capture-
beslissing, met terugval naar de live meting. De uitlegtekst
("Live zonoverschot") is bijgewerkt naar "Verwacht zonoverschot" om dit
correct te weerspiegelen.

**Getest** (5 nieuwe permanente tests in
`test_arbitrage_forecast_not_live_pv.py`): de nieuwe helper leest het
juiste half-uur-interval; past de geleerde bias correct toe; geeft
`None` terug zonder geconfigureerde voorspellingssensor; de kern-
regressietest (een gedempte live PV-meting mag de beslissing niet meer
omslaan zolang de Solcast-voorspelling een comfortabel overschot
toont); en de terugval-naar-live-meting blijft exact werken zoals
voorheen wanneer er geen voorspellingssensor is geconfigureerd.

## v0.63.72 — fundamenteel gat gevonden: manual-modus combineert geen zon

**Gerapporteerd:** "Tevens is de som in vermogens welke hier aangegeven
wordt 2000W [...] Dit klopt opzich alleen regelt de zendure zelf dat
het PV overschot wordt opgeslagen in de smart mode" — de uitlegtekst
toonde "actief bijgekocht op 293W" naast "zonoverschot (1707W) wordt
eerst benut", samen precies het doelvermogen (2000W). De gebruiker
vermoedde terecht dat hier een aanname in zat die niet klopte.

**Bevestigd via twee gerichte vragen:**
1. Manual-modus commanderen op 293W laadt de accu ook daadwerkelijk
   met **maar 293W totaal** — het zonoverschot (1707W) wordt dan
   gewoon apart teruggeleverd, niet vastgelegd. Manual-modus op deze
   Zendure is dus **niet zon-bewust**.
2. Manual-modus commanderen op het **volle** doelvermogen (2000W)
   resulteert wél in 1707W zon + 293W net = 2000W totaal — de accu
   combineert zon en net dan vanzelf tot het gecommandeerde totaal.

**Impact van de oude aanpak**: sinds v0.63.15 (het allereerste
arbitrage-laden) werd steeds alleen het net-gat gecommandeerd, in de
veronderstelling dat de accu daar vanzelf het zonoverschot bovenop zou
leggen. In werkelijkheid werd daarmee het grootste deel van het
zonoverschot **verspild** (apart teruggeleverd) terwijl de accu maar
een fractie van het beoogde vermogen daadwerkelijk laadde — feitelijk
**slechter dan niets doen**, want gewone smart-modus zou dat
zonoverschot wél hebben vastgelegd.

**Fix**: `_get_arbitrage_charge_power()` commandeert nu altijd het
**volle** doelvermogen zodra er enige winstgevende netaankoop
gerechtvaardigd is — nooit meer alleen het gat. `last_arbitrage_grid_
power_w` blijft bestaan als informatieve schatting van het werkelijke
net-aandeel, los van het gecommandeerde totaal. Bevestigd (en door de
gebruiker expliciet benoemd): dit pad wordt hierdoor alleen bereikt
wanneer het verwachte zonoverschot ontoereikend is om het doel te
dekken — vooral najaar/winter, of vroeg/laat op de dag; dekt de zon
het doel al volledig, dan gaat het via `arbitrage_solar_capture` naar
`smart` zonder enige netaankoop, zoals al het geval was.

**Financiële tracking gecontroleerd, geen aanpassing nodig**: de
kostenbasis-tracking (`_update_battery_cost_basis_and_savings`) leest
de **werkelijke** verandering in beschikbare accu-energie (niet het
gecommandeerde vermogen), en de directe-kosten-tracking
(`_update_financial_tracking`) rekent `arbitrage_charging` sowieso al
niet mee. Beide dus ongewijzigd correct.

**Uitlegtekst bijgewerkt**: toont nu expliciet dat het volle vermogen
wordt gecommandeerd en dat de Zendure zon+net automatisch combineert,
met het geschatte net-aandeel als aparte, informatieve waarde.

**Getest**: bestaande tests bijgewerkt naar het gecorrigeerde gedrag
(2 tests) + 1 nieuwe permanente test die exact het gerapporteerde
veldscenario natrekt (1707W zon, 293W net-gat, 2000W doel) en
bevestigt dat het volle doelvermogen wordt gecommandeerd, niet het gat.

## v0.63.73 — actief bijkopen mag alleen nog als de reserve écht ontoereikend is

**Gerapporteerd:** "Hij sprint toch weer naar manual" — gevolgd door
een expliciete, duidelijke regel: "Als er voldoende capaciteit is voor
overbruggen van de nacht, en er 's avonds dure kwartier prijzen zijn
mag de accu NIET manual gaan bijladen, alleen op smart om de zonne
energie welke wordt teruggeleverd op te slaan. Is er te weinig om de
nacht te overbruggen dan mag hij manual bijladen."

**Dit draait de oorspronkelijke v0.63.15-aanname volledig om**: tot nu
toe werd er altijd actief bijgekocht zodra de winst-marge het toeliet,
**ongeacht** of de bestaande reserve al genoeg was ("genoeg om te
overbruggen" en "winstgevend om nu meer te kopen" waren bewust
onafhankelijke vragen). Vanaf nu geldt: is de reserve al voldoende om
de nacht te overbruggen, dan is een actieve netaankoop puur voor winst
niet meer toegestaan, hoe gunstig de marge ook is.

**Fix**: `_get_arbitrage_charge_power()` controleert `should_postpone_
charging` nu als allereerste, bepalende voorwaarde:
- **Voldoende reserve** (`should_postpone_charging = True`): nooit een
  echte netaankoop meer. Alleen het al aanwezige zonoverschot wordt via
  smart-modus vastgelegd (het bestaande v0.63.60-mechanisme,
  `arbitrage_solar_capture`) — nooit meer `arbitrage_charging`/manual.
- **Ontoereikende reserve** (`should_postpone_charging = False`): de
  winst-marge-logica (inclusief de v0.63.71-Solcast-verwachting en de
  v0.63.72-volledig-doelvermogen-fix) werkt exact zoals voorheen.

**Dode code opgeruimd**: een onbereikbare `if should_postpone_charging`
-check verderop in de functie (nu altijd al door de nieuwe, vroege
check afgehandeld) is verwijderd.

**Getest** (3 bijgewerkte/nieuwe permanente tests in
`test_arbitrage_charging.py`, met de al gevestigde `_should_postpone_
charging`-monkeypatch-techniek om dit betrouwbaar te forceren, in
plaats van op een toevallig scenario te vertrouwen): geen arbitrage-
netaankoop meer bij voldoende reserve, ongeacht de marge; arbitrage
vuurt nog gewoon bij een echt ontoereikende reserve; en het aanwezige
zonoverschot wordt bij voldoende reserve nog steeds via smart-modus
vastgelegd in plaats van verspild.

## v0.63.74 — sleufknoppen kregen onvoorspelbare entity_id's

**Gerapporteerd, met screenshot:** "Tabel NILM is nu goed genoeg,
alleen kan niet beoordelen afwijzen etc van nieuwe apparaten" — onder
"Bevestigen / negeren" verscheen helemaal niets, ondanks 80 openstaande
kandidaten.

**Eerste vermoeden (breedteprobleem) getoetst en verworpen**: de
zichtbaarheids-voorwaarde (v0.63.52) verbergt lege sleuven, maar hier
verdween alles, niet gedeeltelijk — dat wees op iets fundamentelers.

**Werkelijke root cause, gevonden bij het narekenen van hoe Home
Assistant entity_id's genereert**: sinds `has_entity_name` uit staat
voor deze knoppen (v0.63.47, om naam-afkapping te voorkomen) én er
nooit een expliciete `object_id` was ingesteld, leidt Home Assistant de
entity_id af van de entiteit's eigen `name`-property **op het moment
van de allereerste registratie**. Die naam is echter bewust dynamisch
(v0.63.43 — toont steeds welke kandidaat er op dat moment in de sleuf
zit). Bij een verse registratie werd daardoor een onvoorspelbare
entity_id vastgelegd, afhankelijk van toeval (welke kandidaat er op dat
exacte moment in zat) — niet de stabiele `nilm_kandidaat_N_bevestigen`/
`_negeren`-id die het meegeleverde dashboard hardcodeert. Elke
dashboardverwijzing naar deze 16 knoppen wees daardoor stilzwijgend
naar een niet-bestaande entiteit — vandaar dat er letterlijk niets
verscheen.

**Fix**: een expliciete `_attr_suggested_object_id` toegevoegd, apart
gehouden van de (Engelse) `unique_suffix` die de `unique_id` al gebruikt
— gebaseerd puur op het vaste sleufnummer, nooit op de dynamische
kandidaatnaam. Resultaat: `nilm_kandidaat_1_bevestigen` t/m
`nilm_kandidaat_8_negeren`, exact matchend met wat het dashboard
verwacht.

**Belangrijke beperking, expliciet benoemd**: dit fixt alleen **nieuw
geregistreerde** entiteiten — een al-bestaande, verkeerd benoemde
entiteit behoudt zijn oude entity_id voor altijd (gekoppeld aan
`unique_id`, niet aan de naam). Bestaande installaties met dit probleem
moeten de 16 sleufknoppen eenmalig handmatig verwijderen (Instellingen
→ Apparaten & Diensten → Energy Management System → apparaat) en HA
herstarten, zodat ze opnieuw worden aangemaakt met de correcte,
stabiele entity_id.

**Gecontroleerd of dit probleem nog ergens anders sluimert**: alle
overige entiteiten in de integratie hebben `has_entity_name = True`
(of expliciet ingesteld) — alleen deze 16 sleufknoppen liepen risico.

**Getest** (3 nieuwe permanente tests): de object_id blijft stabiel
ongeacht welke kandidaat er in de sleuf zit; bevestig- en
negeer-knoppen krijgen de juiste, verschillende Nederlandse suffix; en
alle 16 object_id's zijn uniek en matchen exact wat het dashboard
hardcodeert.

## v0.63.75 — verwacht schema kende ook de arbitrage_charging-uitkomst nog niet

**Gerapporteerd, met screenshots:** "we hadden toch juist afgesproken
om dit anders te doen" — de gebruiker citeerde de uitlegtekst voor
`arbitrage_charging` (manual, 418W bijgekocht van het net) en
overrulede het systeem naar Learning-only omdat dit ongewenst leek.

**Onderzocht en gebleken: de beslissing zelf was correct.** De
"Overzicht komende uren"-tabel toonde `smart` voor exact hetzelfde
tijdslot als waarvoor "Verwachte modus (logica)" `manual` liet zien —
een directe tegenstrijdigheid, geen bevestiging dat de v0.63.73-regel
verkeerd was toegepast. Nagetrokken: de reserve was op dat moment
daadwerkelijk ontoereikend om de nacht te overbruggen
(`should_postpone_charging = False`), dus mocht er volgens de eigen,
net vastgestelde regel ("is er te weinig om de nacht te overbruggen dan
mag hij manual bijladen") gewoon actief bijgeladen worden.

**Root cause, dezelfde soort fout als v0.63.70**: de "nu"-override in
`_build_forecast_timeline()` kende alleen `live_is_expensive` en
`live_should_postpone_charging`/`live_should_capture_solar`. Een échte,
winstgevende netaankoop (`arbitrage_charging`) is geen van beide — de
override-logica had hier geen signaal voor en viel stilzwijgend terug
op `smart`, terwijl de daadwerkelijke beslissing `manual` was.

**Fix**: de al bestaande, vroege arbitrage-evaluatie (sinds v0.63.70,
puur voor de schema-projectie) levert nu ook een expliciet
`live_is_arbitrage_charging`-signaal, doorgegeven aan
`_build_forecast_timeline()`, dat de huidige rij correct op `manual`
zet wanneer dat de daadwerkelijke beslissing is.

**Getest** (2 nieuwe permanente tests in
`test_schedule_solar_capture_override.py`): het signaal zet de huidige
rij op `manual`; en een volledige tick (met `_should_postpone_charging`
gemonkeypatcht naar `False` om een echt ontoereikende reserve
betrouwbaar te forceren) bevestigt dat `last_timeline`'s huidige rij
daadwerkelijk `manual` toont wanneer `last_reason ==
"arbitrage_charging"`.

## v0.63.76 — capaciteitstabel nu altijd zichtbaar in de uitlegtekst

**Gevraagd**: "In de tekst card wil ik daarom ook altijd de tabel zien,
wat de verwachtingen zijn qua capaciteit" — naar aanleiding van het
vorige rapport, waarbij bleek dat de "diepste-tekort"-tabel
(Periode/Basisverbruik/Verwachte zon/Diepste tekort/Veiligheidsmarge)
niet verscheen bij de `arbitrage_charging`-reden.

**Root cause, empirisch nagerekend** (niet zomaar aangenomen): de tabel
werd tot dan toe alleen berekend **binnen** `_should_postpone_
charging`'s eigen, smalle scope (`nu < cheap_block_start`). Zodra dat
moment voorbij was, of er simpelweg geen naderend goedkoop blok
identificeerbaar was, nam die functie een vroege `return` zónder de
tabel aan te raken — waardoor 'm gewoon de oude, vaak lege waarde bleef
tonen, zelfs wanneer `arbitrage_charging` (of in principe elke andere
reden) de daadwerkelijke, actuele beslissing was.

**Fix**: een nieuwe, volledig onvoorwaardelijke functie
(`_update_needed_kwh_breakdown_for_display`) die elke tick draait,
losgekoppeld van `_should_postpone_charging`'s eigen scope en
beslissingslogica (die zelf ongewijzigd blijft). Gebruikt
`cheap_block_start` als eindpunt zodra die zinvol in de toekomst ligt;
valt anders terug op een generieke vooruitblik van 24 uur, zodat er
altijd iets zinvols te tonen is. Het nieuwe
`last_needed_kwh_breakdown_end_time`-veld houdt de tabel se
"Periode"-tekst consistent met welk eindpunt daadwerkelijk is gebruikt.

**Getest** (5 nieuwe permanente tests in
`test_needed_kwh_breakdown_always_shown.py`, plus 1 bestaande test
bijgewerkt naar het nieuwe veld): de tabel verschijnt nu daadwerkelijk
bij `arbitrage_charging`; valt terug op de 24-uurs-vooruitblik zonder
naderend goedkoop blok; gebruikt `cheap_block_start` wanneer die wél
zinvol in de toekomst ligt; valt terug wanneer `cheap_block_start` al
gepasseerd is; en de "Periode"-tekst blijft consistent met het
daadwerkelijk gebruikte eindpunt.

## v0.63.77 — arbitrage-laden definitief en volledig verwijderd

**Aanleiding:** meerdere gerapporteerde velscenario's ("Manueel laden
mag nooit als er later tegen dure uren wordt ontladen, dit gebeurt nu
met de nieuwste versie" en "Winst gevende marge achter wege laten,
gewoon smart opladen") — de v0.63.73-uitzondering ("bij ontoereikende
reserve mag manual") bleef in de praktijk regelmatig grotendeels van
het net bijladen, wat niet meer gewenst was.

**Definitieve, expliciet bevestigde beslissing**: het hele
"actief bijkopen van het net omdat er later een winstgevend duurder
kwartier komt"-mechanisme (arbitrage-laden, sinds v0.63.15) is volledig
verwijderd — óók voor het geval waarin de reserve écht ontoereikend is.
Reden, door de gebruiker zelf benoemd: voor deze accu-capaciteit wordt
gekochte energie in de praktijk toch nooit met winst doorverkocht — het
dient sowieso als overbrugging voor de nacht, wat de hele
winst-framing overbodig maakte. Bevestigd: `should_force_charge`
(weinig zon tijdens het goedkope blok) en `_is_emergency_low_battery`
(kritiek lage SoC) blijven als enige, aparte vangnetten over.

**Fix**: `_get_arbitrage_charge_power()` (marge-berekening,
netaankoop-logica) volledig verwijderd, vervangen door de veel
eenvoudigere `_should_capture_solar_instead_of_postponing()` — die doet
nog maar één ding: voorkomen dat al aanwezig zonoverschot verloren gaat
tijdens "laden uitstellen" (`smart_discharging` dekt alleen
huishoudverbruik, laadt niet bij vanuit zon). Geen netaankoop meer,
onder geen enkele omstandigheid.

**Opgeruimd**: `MIN_ARBITRAGE_MARGIN_EUR_PER_KWH`,
`MIN_ARBITRAGE_GRID_POWER_W`, `last_arbitrage_margin_eur_per_kwh`,
`last_arbitrage_grid_power_w`, `_arbitrage_wants_smart_over_postpone`,
`_get_best_remaining_sell_price_today_eur` (nu ongebruikt), de
`arbitrage_charging`-reden uit `REASON_TO_MODE` en de emoji-mapping, de
bijbehorende uitlegtekst-tak, het `live_is_arbitrage_charging`-signaal
in de schema-projectie, en de diagnostiek-velden.

**Testsuite herzien**: `test_arbitrage_charging.py` volledig herschreven
(8 tests, gericht op het overblijvende zon-vastleggen-gedrag);
`test_arbitrage_forecast_not_live_pv.py` bijgewerkt (Solcast-voorkeur
geldt nu voor het zon-vastleggen-signaal, niet meer voor een
netaankoop); `test_schedule_solar_capture_override.py` en
`test_needed_kwh_breakdown_always_shown.py` bijgewerkt naar het nieuwe
gedrag (arbitrage_charging kan niet meer voorkomen).

## v0.63.78 — kookpiek blies de "diepste tekort"-berekening op

**Gerapporteerd:** "Het basis verbruik schiet tussen ca. 16:00 en 17:00
omhoog door koken etc." — de "Basisverbruik"/"Diepste tekort
onderweg"-cijfers konden flink oplopen als de berekening samenviel met
een actieve kookpiek.

**Root cause**: `_get_smoothed_consumption_correction_ratio()` slaat de
mediaan-demping bewust over zodra een **bevestigde** zware verbruiker
actief is (`last_heavy_load_source`), en vertrouwt dan de laatste,
ongefilterde meting direct — terecht voor airco (kan uren aanhouden),
maar deze uitzondering gold voor **alle** apparaten uit die lijst,
inclusief de inherent kortdurende: oven, kookplaat, vaatwasser,
wasmachine, Quooker. Een kooksessie (ruim onder het uur) werd zo
gebruikt om de **hele resterende periode** (vaak 15+ uur) mee op te
schalen — voor een gebeurtenis die allang voorbij is tegen de tijd dat
de nacht daadwerkelijk aanbreekt.

**Fix**: nieuwe constante `SUSTAINED_HEAVY_LOAD_SOURCES` (`airco`,
`slaapkamer`) — alleen deze twee mogen de mediaan-demping nog
overslaan. De kortdurende apparaten vallen nu terug op dezelfde
mediaan-gedempte route als een onbevestigde meting.

**Getest** (2 nieuwe permanente tests in `test_heavy_load_awareness.py`,
1 bestaande test aangepast): oven/kookplaat/vaatwasser/wasmachine/
Quooker slaan de demping niet meer over; airco/slaapkamer blijven dat
wel doen.

## v0.63.79 — de v0.63.74-fix werkte niet: `_attr_suggested_object_id` bestaat niet

**Gerapporteerd**: na de handmatige verwijder-en-herstart-migratiestap
uit v0.63.74 bleef "Bevestigen / negeren" alsnog volledig leeg —
"Niet geholpen".

**Root cause, nagetrokken tegen de officiële Home Assistant
developer-documentatie en broncode** (niet zomaar opnieuw aangenomen):
`_attr_suggested_object_id`, de fix uit v0.63.74, blijkt **geen
bestaand Home Assistant-attribuut** te zijn. Een fout van mijn kant —
ik had de API verkeerd onthouden. De officiële "Registry properties"-
tabel op https://developers.home-assistant.io/docs/core/entity noemt
alleen `device_info`, `entity_category`,
`entity_registry_enabled_default`, `entity_registry_visible_default`
en `unique_id`. Het enige vergelijkbare mechanisme in de broncode
(`internal_integration_suggested_object_id`) is expliciet
gedocumenteerd als "only handled internally, never to be used by
integrations". Home Assistant negeerde het gezette attribuut dus
simpelweg volledig, en bleef de entity_id afleiden van de dynamische
naam — exact het oorspronkelijke probleem, ongewijzigd.

**Echte fix**: `self.entity_id` wordt nu rechtstreeks als
instantie-attribuut gezet in `_NilmSlotButton.__init__`, vóórdat de
entiteit ooit aan hass wordt toegevoegd. Dit is een genuine,
gerespecteerde override — `entity_id` is een gewoon, instelbaar
attribuut op `Entity`; Home Assistant genereert er alleen automatisch
één als de integratie zelf nog niets heeft ingesteld. De volledige
entity_id (inclusief de `woonkamer_energy_management_system_`-prefix
die het dashboard al voor elke andere entiteit hardcodeert) wordt nu
expliciet uitgeschreven.

**De migratiestap uit v0.63.74 blijft nodig**: bestaande, verkeerd
benoemde knop-entiteiten moeten nog steeds eenmalig handmatig worden
verwijderd (Instellingen → Apparaten & Diensten → Energy Management
System → apparaat → de 16 knop-entiteiten), gevolgd door een
HA-herstart — pas dan registreren ze zich opnieuw met de nu wél
correcte, expliciet gezette entity_id.

**Getest**: de 3 bestaande tests uit v0.63.74 herschreven om
`entity_id` te controleren in plaats van het niet-bestaande
`_attr_suggested_object_id` — alle drie slagen nu tegen de echte fix.

## v0.63.80 — handmatige verwijdering niet meer nodig (unique_id opgehoogd)

**Gerapporteerd, met screenshot**: "Je kunt enkel 0 van de 16
entiteiten verwijderen. De andere vereisen dat de integratie stopt met
ze aan te leveren" — Home Assistant blokkeert het handmatig verwijderen
van entiteiten die nog actief door een geladen integratie worden
geleverd, waardoor de v0.63.74/.79-migratie-instructie (verwijderen +
herstarten) simpelweg onuitvoerbaar was via de UI.

**Bovendien**: zelfs een kale herstart zonder verwijderen zou niet
geholpen hebben. Home Assistant's entity-registry zoekt bij registratie
eerst een bestaand item op via de `unique_id` — vindt het er één, dan
wordt de **opgeslagen, oude** entity_id hergebruikt; een in de code
nieuw gezette `self.entity_id` (v0.63.79) wordt dan nooit toegepast.

**Fix**: de `unique_id` van de 16 sleufknoppen zelf is opgehoogd (een
`_v2`-suffix toegevoegd). Home Assistant heeft daardoor geen enkele
match meer in de registry en registreert deze knoppen dus daadwerkelijk
vers — met correcte toepassing van de expliciet gezette entity_id uit
v0.63.79. **Geen handmatige verwijdering meer nodig** — alleen een
gewone HA-herstart volstaat. De oude v1-entiteiten stoppen simpelweg
met bestaan; er was nooit state gekoppeld aan hun unique_id (het
NILM-kandidaten-/bevestigde-apparaten-state leeft in de coordinator,
gekeyed op de gemonitorde sensor-entity_id, niet op deze knoppen).

**Getest**: nieuwe permanente test die bevestigt dat beide
knoptypes (bevestigen/negeren) een `_v2`-gesuffixte, onderling
verschillende `unique_id` krijgen.
