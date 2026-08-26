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

## v0.63.81 — de v0.63.80-fix loste het maar half op: eenmalig toegewezen deduplicatie is blijvend

**Gerapporteerd, met Ontwikkelaarshulpmiddelen → Statussen-screenshot**:
na het verwijderen van de 16 oude (unavailable) v1-entiteiten en een
herstart, registreerde de nieuwe knop zich alsnog onder
`..._nilm_kandidaat_1_bevestigen_2` — nog steeds niet de naam die het
dashboard verwacht.

**Root cause, nagetrokken via Ontwikkelaarshulpmiddelen**: de "_v2"
-generatie (v0.63.80) had zichzelf al eerder — tijdens een eerdere
herstart, toen de oude v1-entiteiten nog niet verwijderd waren en dus
de kale naam nog bezet hielden — een `_2`-gededuplificeerde entity_id
laten toewijzen. Zodra Home Assistant die deduplicatie eenmaal heeft
vastgelegd voor een gegeven `unique_id`, is dat **permanent** — de naam
wordt nooit later automatisch "geüpgraded" terug naar de kale versie,
ook niet als het onderliggende conflict inmiddels is opgelost. En omdat
deze "_2"-entiteit zelf nu weer actief is, loopt handmatig verwijderen
tegen precies dezelfde "0 van de 16 verwijderbaar"-muur op als de
v1-entiteiten daarvoor.

**Fix**: de `unique_id` nogmaals opgehoogd, naar een `_v3`-suffix.

**Belangrijk — dit vereist ditmaal een tweetrapsvolgorde, niet zomaar
installeren + herstarten:**
1. Installeer v0.63.81 en herstart HA. De huidige `_2`-entiteiten (unique_id
   `_v2`) worden dan niet meer door de integratie aangeboden en worden
   zelf `unavailable` — maar ze **houden de kale naam nog steeds bezet**
   in de registry op het moment van déze herstart, dus de nieuwe
   `_v3`-registratie krijgt bij déze eerste herstart mogelijk zelf weer
   een gededupliceerde naam.
2. Verwijder daarna de nu-`unavailable` geworden `_2`-entiteiten (nu wél
   verwijderbaar, want niet meer actief) via Instellingen → Apparaten &
   Diensten → Entiteiten, en herstart **nogmaals**. Pas dan is er echt
   niets meer om mee te botsen, en zou de `_v3`-generatie de kale,
   correcte naam moeten krijgen.

**Getest**: bestaande test bijgewerkt naar de `_v3`-suffix.

## v0.63.82 — zichtbaarheids-conditie verwijderd: entiteiten kloppen, dashboard toch leeg

**Bevestigd via Ontwikkelaarshulpmiddelen → Statussen**: na de volledige
v0.63.74-t/m-.81-migratie hebben alle 16 sleufknoppen eindelijk de
correcte, kale entity_id (exact matchend met wat het dashboard
verwacht) én correct gevulde `kandidaat_entity_id`/`kandidaat_naam`/
`kandidaat_vermogen_w`-attributen. De entity-registratie-kant van dit
probleem is dus volledig opgelost.

**Toch bleef "Bevestigen / negeren" leeg** — wat de zichtbaarheids-
conditie (`visibility: condition: template`, v0.63.52) als enige
overgebleven verdachte aanwijst. In plaats van verder te blijven zoeken
naar waarom die specifieke conditie niet betrouwbaar werkt in deze
dashboard-configuratie (genest in een grid binnen de Sections-layout),
is gekozen voor de pragmatische, gegarandeerd werkende route die al
eerder als alternatief was voorgesteld.

**Fix**: alle 16 `visibility`-blokken verwijderd uit zowel
`dashboards/energy_management_system_dashboard.yaml` als het
meegeleverde `dashboard_template.yaml`. Alle 16 knoppen zijn nu altijd
zichtbaar, met "Sleuf N (leeg)" als er geen kandidaat in zit — ten
koste van soms een paar lege kaarten te zien, maar met gegarandeerde
functionaliteit.

**Geen codewijziging nodig** — dit is uitsluitend een dashboard-YAML-
aanpassing; de coordinator/button-logica blijft ongewijzigd.

## v0.63.83 — van 8 zichtbare sleuven terug naar 1 (breedteprobleem)

**Gerapporteerd, met screenshot**: de knoppen verschenen eindelijk
(v0.63.82 loste dat op), maar de kandidaatnaam werd afgekapt ("Houten
la..." in plaats van de volledige naam) — met 8 sleuven × 2 knoppen
naast elkaar (2 per rij) was er simpelweg te weinig breedte per kaart.

**Gevraagd**: "1 optie tonen is voldoende, als de 1e beoordeeld is
verschijnt de 2e automatisch" — beoordelen gebeurt toch al één voor
één, dus 8 gelijktijdig zichtbare sleuven voegden weinig toe.

**Fix**: `NILM_DASHBOARD_SLOT_COUNT` verlaagd van 8 naar 1 in
`const.py`. Het dashboard toont nu nog maar één bevestig/negeer-
kaartpaar, met de volle breedte (12 kolommen in plaats van 6) — ruim
voldoende voor de langste kandidaatnaam. 30 van de 32 knopkaarten
(sleuf 2 t/m 8) zijn uit het dashboard verwijderd; de introtekst is
aangepast om het nieuwe, sequentiële gedrag te beschrijven.

**Geen wijziging nodig aan het onderliggende doorschuifmechanisme**:
`get_nilm_candidate_at_slot`/confirm/reject werken al generiek voor elk
aantal sleuven — bevestigen of negeren van de huidige kandidaat laat de
eerstvolgende gewoon automatisch instromen, nu met één zichtbare sleuf
in plaats van acht.

**Getest**: bestaande test (voorheen hardcoded op "16"/"range(1, 9)")
aangepast om dynamisch met `NILM_DASHBOARD_SLOT_COUNT` mee te schalen,
zodat een toekomstige aanpassing van dit aantal niet opnieuw
testonderhoud vereist.

## v0.63.84 — écht fundamentele oorzaak: Grid-kaart, geen Sections-sectie

**Gerapporteerd, met screenshot**: zelfs met 12 kolommen op de knoppen
(v0.63.83) bleef de kandidaatnaam afgekapt, met veel lege verticale
ruimte in de kaart. Gevraagd: "Kun je niet beter een 'sections
dashboard' maken?"

**Nagetrokken tegen de officiële Home Assistant-documentatie** (niet
zomaar aangenomen, na de eerdere `_attr_suggested_object_id`-misser):
dit dashboard gebruikt voor élk tabblad behalve "Overzicht" géén
`type: sections`, maar het klassieke **Masonry**-weergavetype (`cards:`
rechtstreeks onder de view-definitie, in plaats van `sections:`). De
`- type: grid`-kaarten in die tabbladen zijn daardoor geen
Sections-"secties", maar de gewone **Grid-kaart**
(https://www.home-assistant.io/dashboards/grid/) — met een volledig
ander eigenschappenmodel:
- Sections-secties gebruiken per-kaart `grid_options` binnen een
  intern 12-koloms-raster.
- De Grid-kaart heeft in plaats daarvan haar éígen `columns`
  (standaard **3**) en `square` (standaard **true** — kaarten
  vierkant gedwongen) op de Grid-kaart zélf, niet op de kinderen.

Zonder deze twee expliciet te zetten, viel de knoppenkaart (en de
NILM-tellingen/kandidaten-kaart erboven) terug op 3 kolommen + vierkante
cellen — ongeacht welke `grid_options` ik op de onderliggende kaarten
zette (die eigenschap heeft in deze context simpelweg geen enkel
effect). Dit verklaart zowel de afgekapte namen als de vierkante,
halflege kaarten in vrijwel elke NILM-screenshot deze hele sessie —
inclusief de aanhoudende "NI... 80" / "NI... 20"-afkapping bovenaan het
"Apparaten"-tabblad.

**Fix**: `columns: 1` en `square: false` rechtstreeks op de twee
betrokken Grid-kaarten gezet (niet op de kinderen — dat blijft zoals
het was). Andere Grid-kaarten in de overige tabbladen bleken dit al
eerder correct te hebben ingesteld; alleen deze twee ontbraken nog.

**Geen codewijziging nodig** — uitsluitend een dashboard-YAML-fix.

## v0.63.85 — nieuw Water-tabblad (verbruik, trend, gebruiksmomenten)

**Gevraagd**: "Meldingen/tracking zoals bij vaatwasser/wasmachine" —
na verduidelijking herzien naar "geen meldingen alleen een watertabblad
met relevante info". Puur informatief, stuurt niets aan en heeft geen
invloed op de accu-beslissing.

**Nieuw**:
1. **Dagelijks verbruik + geschiedenis** — volgt de "vandaag"-sensor
   rechtstreeks; archiveert automatisch bij zijn eigen middernacht-reset
   (gedetecteerd via een dalende uitlezing, geen eigen reset-logica
   nodig).
2. **Losse gebruiksmomenten** — RUSTEND/ACTIEF-toestandsmachine op het
   live debiet (`_update_water_tracking`), zelfde principe als de
   vaatwasser/wasmachine-detectie maar met eigen constanten:
   `WATER_USAGE_ACTIVE_THRESHOLD_L_PER_MIN` (1 L/min, bewust laag voor
   volledig inzicht inclusief de nachtelijke waterontharder-
   regeneratie) en `WATER_SESSION_COMPLETE_SUSTAINED_MINUTES` (2 min,
   korter dan de vaatwasser/wasmachine-marge). Geschat volume per
   moment via de optionele totaal-verbruiksensor.

**Nieuwe configuratie-opties**: `water_active_usage_sensor_entity`,
`water_daily_total_sensor_entity`, `water_total_usage_sensor_entity`
— alle drie optioneel.

**Nieuwe sensor**: `WaterUsageSensor`
(`sensor.woonkamer_energy_management_system_waterverbruik`) — live
debiet als state; vandaag-totaal, gemiddelde, trend-procent,
dag-geschiedenis en recente gebruiksmomenten als attributen.
RestoreEntity.

**Nieuw dashboardtabblad "Water"** — met de inmiddels bekende, correcte
Grid-kaart-instellingen (`columns`/`square` expliciet gezet) om
hetzelfde breedteprobleem als eerder te vermijden.

**Testinfrastructuur-fix, terzijde**: tijdens het bouwen bleek een
markdown-lijst-kaart plotseling alles op één regel te renderen ondanks
een exact kloppend template — root cause: `dashboard_template.yaml`
(waar de test tegen valideert) was niet opnieuw gesynchroniseerd na een
losse bewerking aan `dashboards/energy_management_system_dashboard.yaml`.
Geen echte Jinja/YAML-bug; wél een waardevolle herinnering om na élke
dashboard-bewerking te synchroniseren en te valideren — wat voortaan
consequent gebeurt. Testdata voor de NILM-apparatentabel en het nieuwe
Water-tabblad toegevoegd aan `test_dashboard_tables.py` zodat toekomstige
lijst-/tabel-kaarten ook echt met gevulde data worden doorgetest, niet
alleen het lege pad.

**Getest** (9 nieuwe permanente tests in `test_water_tracking.py`):
dagelijks totaal wordt gevolgd; archivering bij reset; geschiedenis
begrensd tot het leervenster; sessie wordt correct gedetecteerd en
gelogd (inclusief volume-schatting); een korte onderbreking beëindigt
de sessie niet; te lage flow start nooit een sessie; niets gebeurt
zonder geconfigureerde sensoren; en de sensor toont/herstelt zijn data
correct.

## v0.63.86 — waterontharder-regeneratie herkennen (wanneer + hoelang geleden)

**Gevraagd**: "Voor de waterontharder zou ik willen zien wanneer hij
zijn werk heeft gedaan en hoelang dat geleden is."

**Aanpak**: er is geen betrouwbare manier om dit puur op debiet of duur
te onderscheiden van ander watergebruik (verschilt per merk/model, geen
trainingsdata). In plaats daarvan: elk afgerond gebruiksmoment dat
start binnen een nachtelijk venster (standaard middernacht–6 uur,
nieuwe constanten `WATER_SOFTENER_NIGHT_WINDOW_START_HOUR`/`_END_HOUR`)
wordt aangemerkt als de waterontharder — niemand doucht of vult
structureel een bad midden in de nacht, dus tijdstip alleen is al een
betrouwbare indicator.

**Coordinator**: `_update_water_tracking()` markeert elk gelogd
gebruiksmoment met `waarschijnlijk_waterontharder` en houdt
`water_softener_last_regeneration` bij (het tijdstip van de laatst
herkende regeneratie).

**Sensor**: nieuw attribuut `waterontharder_laatste_regeneratie`
(ISO-tijdstip) op `WaterUsageSensor`, met RestoreEntity-herstel.

**Diagnostiek** uitgebreid met hetzelfde veld.

**Dashboard**: nieuwe "Waterontharder"-kaart op het Water-tabblad —
toont wanneer de laatste regeneratie was én hoelang geleden (via HA's
eigen `relative_time()`-functie), plus een 🧂-markering bij het
betreffende moment in de gebruiksmomenten-tabel.

**Testinfrastructuur uitgebreid**: fake `as_datetime`/`relative_time`-
implementaties toegevoegd aan de dashboard-render-test, met echte
testdata (niet alleen het lege pad) voor de nieuwe kaart en de
uitgebreide tabel.

**Getest** (4 nieuwe permanente tests in `test_water_tracking.py`):
een nachtelijk gebruiksmoment wordt correct als waterontharder
gemarkeerd; een overdag-gebruiksmoment (bijv. douche) niet; de sensor
toont het tijdstip correct; en herstelt het na een herstart.

## v0.63.87 — extra-dip laden op weinig-zon-dagen + spreidingsgebaseerde drempel

Uitgebreid besproken en ontworpen door de gebruiker, naar aanleiding
van een extreme-koude-dag-analyse (11 januari 2026: laagste
etmaalgemiddelde van het jaar, -4,1 °C, bijna -10 °C 's nachts).

### Extra-dip laden op weinig-zon-dagen

**Aanleiding**: sinds v0.63.77 laadt het systeem tijdens een
weinig-zon-dag alleen nog gedwongen bij binnen het ene, hoofd-goedkope
blok van de dag (`should_force_charge`). Een aparte, losse prijsdip
elders die dag werd volledig genegeerd, ook al zou bijladen daar
aantoonbaar voordeliger zijn dan wachten — een onbedoeld neveneffect
van de volledige arbitrage-verwijdering.

**Fix**: nieuwe beslistak direct na `should_force_charge`. Vuurt alleen
wanneer `_is_low_solar_expected() = True` én we ons buiten het
hoofdblok bevinden, met een rendement-gecorrigeerde marge-check
(`geleerde_efficiëntie × beste-resterende-prijs-vandaag − huidige-prijs
≥ 0,03 €/kWh`, nieuwe constante
`LOW_SOLAR_EXTRA_DIP_MIN_MARGIN_EUR_PER_KWH`). Hergebruikt de al
continu bijgehouden `learned_battery_efficiency_percent` (terugval op
`battery_round_trip_efficiency_percent`). Laadt met hetzelfde vaste
`manual_charge_power`, en zet ook de winter-guard-vlag
(`_grid_charged_today`) — deze energie is om dezelfde reden gekocht,
dus mag ook niet diezelfde dag worden terugverkocht. Bewust géén
rendement-check op het bestaande hoofdblok zelf (expliciet zo
besloten). Nieuwe reden `grid_charging_low_solar_extra_dip`, met eigen
uitlegtekst, `REASON_TO_MODE`-entry, emoji, en financiële tracking.

**Kritieke ontwerpfout gevonden tijdens het testen, direct
gecorrigeerd**: de eerste versie gebruikte
`is_low_solar and not in_cheap_block and not self._grid_charged_today`
als poort. Op elke weinig-zon-dag zet het hoofdblok (vroeg op de dag)
die vlag echter vrijwel altijd al — waardoor deze poort het hele
mechanisme in de praktijk onbereikbaar maakte. De vlag is bedoeld om
later VERKOPEN te onderdrukken (winter-guard), niet om verdere
LEGITIEME lading te blokkeren. Gecorrigeerd naar uitsluitend
`is_low_solar and not in_cheap_block` (plus de marge-check).

**Getest** (6 permanente tests,
`test_low_solar_extra_dip_charging.py`): vuurt bij voldoende marge;
zet de winter-guard-vlag zodat later verkopen wordt onderdrukt; vuurt
niet bij onvoldoende marge; vuurt nooit op een dag met voldoende zon;
blijft vuren ook als het hoofdblok die dag al eerder heeft geladen
(de gecorrigeerde poort); gebruikt de geleerde efficiëntie boven de
geconfigureerde terugval. Belangrijke test-subtiliteit gedocumenteerd:
`_cheapest_block_range()` kijkt alleen naar toekomstige prijzen, dus
elke testreeks bevat bewust een latere, nóg goedkopere stretch zodat
het testmoment zelf niet abusievelijk als hoofdblok wordt herkend.

### Spreidingsgebaseerde "weinig zon"-drempel

**Aanleiding**: `LOW_SOLAR_RELATIVE_FRACTION` (bepaalt of de geleerde
"typische dag" als "weinig zon" geldt) was een vaste 40%, ongeacht hoe
betrouwbaar de voorspelling recent is gebleken.

**Fix**: nieuwe `deviation_stdev_percent`-property op
`SolarForecastAccuracyTracker`, die de standaarddeviatie berekent van
de al bestaande `deviation_history` (voorheen alleen gebruikt voor het
gemiddelde/de systematische bias via `learned_bias_percent` - geen
nieuwe meting nodig). Nieuwe `_get_low_solar_relative_fraction()` op de
coordinator kiest tussen drie vaste niveaus:
```
stdev < 10%   → fractie 0,6 (consistente voorspelling, ruimer vertrouwen)
stdev 10–25%  → fractie 0,4 (huidige, voorzichtige standaard)
stdev > 25%   → fractie 0,3 (onbetrouwbaar, extra conservatief)
```
Vereist minimaal 5 samples (nieuwe constante
`MIN_SOLAR_HISTORY_FOR_SPREAD_BASED_FRACTION`) voor een betrouwbare
standaarddeviatie; valt anders terug op de vaste 40%. Bewust drie
uitlegbare niveaus in plaats van een continue formule, consistent met
de rest van deze integratie.

**Doorgesproken alternatieven, bewust niet gebouwd**: een uitgebreide
lijst statistische methoden (procesprestaties/Cp-Cpk, hypothesetoetsen,
SPC-kaarten, DOE, Gage R&R, FMEA/Weibull) is beoordeeld en afgewezen -
zie README voor de volledige, beargumenteerde doorloop. Wél als
kansrijk genoemd voor een vervolgstap: een temperatuur-verbruik-
regressie voor extreme-koude-dagen (nog niet gebouwd).

**Getest** (8 permanente tests,
`test_low_solar_spread_based_fraction.py`): stdev is `None` zonder
genoeg samples; correcte berekening met genoeg samples; negeert
implausibele uitschieters (net als `learned_bias_percent`); fractie
valt terug op 0,4 zonder genoeg geschiedenis; verbreedt naar 0,6 bij
lage spreiding; versmalt naar 0,3 bij hoge spreiding; blijft 0,4 bij
gematigde spreiding; end-to-end via `_is_forecast_value_low`.

## v0.63.88 — model-/parameternauwkeurigheid-trends + temperatuur-verbruik-regressie

Uitgebreid besproken en ontworpen door de gebruiker, als vervolg op de
extreme-koude-dag-discussie (11 januari 2026).

### Gedeelde trend-infrastructuur

**Gevraagd**: "wel wil ik allerlei waardes welke je nu hebt toegevoegd
ook inzicht zien op het dashboard met trends... en of het
model/parameter nauwkeuriger wordt", met als expliciete eis:
"Statistisch de beste keuze nemen" voor de berekening.

**Fix**: nieuwe `_compute_trend_summary()` — een kleinste-kwadraten-
regressielijn door een korte tijdreeks, in plaats van een naïeve
nieuwste-vs-oudste-vergelijking. Gebruikt alle beschikbare punten;
rapporteert het %-verschil dat de gefitte lijn impliceert van begin tot
eind van het venster.

**Statistische nuance ontdekt tijdens het testen, gedocumenteerd**:
een eerste test nam aan dat regressie ongevoelig zou zijn voor een
uitschieter aan het uiteinde van de reeks - dat bleek feitelijk
onjuist (een bekende "leverage"-eigenschap: uitschieters aan de randen
hebben juist veel invloed op een regressielijn). Test gecorrigeerd naar
een eerlijke claim: robuustheid bij een uitschieter in het midden van
de reeks (lage leverage daar), niet aan een uiteinde.

Toegepast op drie nieuwe metrics, elk met een eigen, dagelijks
bijgehouden geschiedenis:
1. **Zonvoorspelling-spreiding** (`deviation_stdev_history`, nieuw op
   `SolarForecastAccuracyTracker`, meegerestored via de bestaande
   `PvForecastAccuracySensor`).
2. **Extra-dip-laadmarge** (`extra_dip_margin_history`, één sample per
   dag - niet elke tick, anders zou de geschiedenis met bijna-
   identieke waarden overspoeld raken).
3. **Temperatuur-regressie-nauwkeurigheid** (zie hieronder).

**Nieuwe sensor**:
`ModelTrendInsightSensor`
(`sensor.woonkamer_energy_management_system_model_en_parameternauwkeurigheid`),
bundelt alle drie trends. RestoreEntity. Nieuwe dashboardkaart op het
Advies-tabblad.

**Getest**: 5 tests voor `_compute_trend_summary` zelf, 3 voor de
nieuwe sensor (blootstelling + herstel na restart + het bestaande
PvForecastAccuracySensor-restorepad uitgebreid).

### Temperatuur-verbruik-regressie voor extreme-koude-dagen

**Bewust puur adviserend voor nu** ("eerst observeren", expliciet zo
afgesproken) - beïnvloedt de bestaande reserve-/dieptekort-berekening
nog op geen enkele manier.

**Data verzamelen**: tijdens hetzelfde nachtvenster waar het verbruik
al wordt gevolgd (`_update_night_consumption_tracking`), wordt nu ook
de buitentemperatuur meegesampled (hergebruikt de bestaande
`_get_live_outdoor_temp_c()` - geen nieuwe sensor-configuratie nodig).
Bij afsluiten van het venster wordt het (gemiddelde temperatuur,
totaal verbruik)-paar toegevoegd aan `temp_consumption_history`
(rollend venster, `LEARNING_HISTORY_DAYS`).

**Regressie**: nieuwe, gedeelde `_ols_fit()`-helper (gewone kleinste-
kwadraten) door de (temperatuur, verbruik)-paren, vanaf minimaal 4
samples (nieuwe constante `TEMP_CONSUMPTION_MIN_SAMPLES`).

**Eerlijke, niet-lekkende validatie**: bij het afsluiten van elk
nachtvenster wordt éérst - met de geschiedenis zoals die vóór die nacht
al bekend was - voorspeld wat die nacht had moeten kosten, en pas
dáárna wordt het nieuwe paar zelf toegevoegd aan de geschiedenis. Zo
meet `temp_consumption_prediction_error_history` een eerlijke
validatie (voorspellen met wat toen al bekend was), niet een achteraf-
passende schijnnauwkeurigheid.

`last_temp_consumption_note` toont in gewone taal wat er is voorspeld
vs. wat er werkelijk gebeurde, elke nacht.

**Getest** (9 permanente tests, `test_temp_consumption_regression.py`):
`_ols_fit` correct op een bekende lijn, None bij te weinig punten/geen
x-variatie; voorspelling correct kouder-is-meer-verbruik; venster-
afsluiting sampelt temperatuur en voegt toe aan de geschiedenis; geen
temperatuurmeting → geen toevoeging; validatie gebruikt uitsluitend
eerder-bekende geschiedenis (niet-lekkend); geschiedenis begrensd tot
het leervenster.

## v0.63.89 — NILM structurele naampatroon-uitsluiting (fase 1/solaredge/zendure)

**Gerapporteerd**: "de afgewezen NILM apparaten komen bij elke
herstart terug."

**Onderzocht met een volledige diagnostiek-export** (niet de afgekapte
dashboard-preview, die alleen de eerste ~20 van mogelijk veel meer
afgewezen entiteiten toont) - bleek **geen bug**: de daadwerkelijk
afgewezen entiteit (`sensor.aquarium_jill_vermogen_fase_1`) stond
correct en blijvend in de volledige `nilm_rejected_entities`-lijst.
Wat terugkwam was "Aquarium Jill Vermogen" zelf - een destijds
**bevestigd** (niet afgewezen) apparaat, dat terecht altijd in de
"Bevestigde apparaten"-lijst blijft staan.

**Vervolgvraag, wél geïmplementeerd**: "alles waar fase 1 bij staat
mag sowieso uitgesloten worden net als solaredge en zendure
entiteiten" - een structurele uitsluiting in plaats van losse
afwijzingen per sub-fase-sensor of accu-/omvormer-signaal.

**Nieuwe uitsluitingslaag**: `_is_nilm_pattern_excluded()`, substring-
match (kleine letters) tegen zowel entity_id als friendly_name:
`fase 1`, `fase_1`, `solaredge`, `zendure` (nieuwe constante
`NILM_PATTERN_EXCLUDED_KEYWORDS`) - naast de bestaande, exacte-match
uitsluiting van specifiek geconfigureerde entiteiten.

**Ruimt ook met terugwerkende kracht op**: nieuwe
`_prune_nilm_pattern_excluded_entries()`, draait elke tick vóór de
discovery-scan zelf. Verwijdert alles wat al in de kandidaten-,
bevestigde- of afgewezen-lijst stond en nu aan het patroon voldoet -
niet alleen nieuw ontdekte entiteiten vanaf nu. Eerder afgewezen
entiteiten die nu patroon-uitgesloten zijn, worden ook uit de aparte
`nilm_rejected_entities`-lijst verwijderd (overbodig geworden na de
structurele uitsluiting).

**Getest** (8 permanente tests, `test_nilm_pattern_exclusion.py`):
fase_1 uitgesloten via entity_id én via friendly_name apart;
solaredge/zendure uitgesloten; niet-gerelateerde sensoren (bijv.
"Koelkast") blijven normaal werken; bestaande kandidaten/bevestigde/
afgewezen entiteiten die aan het patroon voldoen worden met
terugwerkende kracht opgeruimd bij de eerstvolgende tick.

## v0.63.90 — NILM-trendlabel: misleidend percentage naast "stijgend"

**Gevraagd, tijdens een grondige diagnostiek-analyse**: "wil je het
gehele statistiek bestand nakijken, dan hoeft ik HA niet zo vaak te
herstarten."

**Gevonden**: 5 "Eetkamer lamp"-sensoren toonden `⚠️ aanhoudend
stijgend (-0%) - mogelijk defect` in de NILM-apparatentabel — een
negatief/nul percentage naast het woord "stijgend".

**Root cause**: de CUSUM-detector is bewust eenzijdig (accumuleert
alleen bij afwijkingen boven de referentie, geklemd op minimaal 0) -
"stijgend" is dus conceptueel altijd correct zodra het alarm afgaat.
Maar `estimated_drift_percent` is puur de afwijking van de LAATSTE dag,
die toevallig rond nul kan liggen ook al was de OPGEBOUWDE geschiedenis
(over meerdere eerdere dagen) wél voldoende om het alarm te triggeren.

**Fix**: `_describe_nilm_trend()` toont het percentage nu alleen als
het ook echt een stijging weergeeft (`drift > 0`); bij een niet-
positieve waarde toont het label "⚠️ aanhoudend stijgend - mogelijk
defect" zonder het verwarrende getal.

**Tijdens dezelfde analyse ook onderzocht, bevestigd géén bug**: twee
schijnbaar tegenstrijdige "veiligheidsmarge"-percentages
(energiebrug-check's vaste 15% vs. de dynamische ontlaadreserve's
10-32%) - bleken twee bewust gescheiden mechanismen met een eigen
scope te zijn (zie `_get_dynamic_discharge_reserve_kwh`'s docstring).
Op uitdrukkelijk verzoek ongewijzigd gelaten - geen wijziging.

**Getest**: nieuwe permanente test
(`test_anomaly_with_non_positive_latest_drift_omits_the_misleading_percentage`)
in `test_nilm_devices_table.py` - bevestigt dat "mogelijk defect" en
"aanhoudend stijgend" nog steeds getoond worden, maar zonder een
misleidend percentage wanneer de laatste-dag-afwijking niet positief
is.

## v0.63.91 — vier verbeteringen na de diagnostiek-review

Gevraagd: "zijn er nog zaken om de integratie te verbeteren, dus
bijvoorbeeld de diagnostiek gedetailleerder maken" — bevestigd: "allemaal,
integratie moet alleen maar beter kunnen worden".

### 1. Snelle gezondheidscheck-samenvatting

Nieuwe `get_diagnostic_summary()`, toegevoegd bovenaan elke
diagnostiek-export (`diagnostic_summary`). Verzamelt een korte lijst
"aandachtspunten" uit bestaande signalen: sensor-gezondheid (indien
niet "goed"), mogelijk-defecte NILM-apparaten (`anomaly_detected`),
NILM-duplicaten, recente tekort-dagen, sluipverbruik-detectie, laatste
fout. `{"status": "nominaal"}` als niets opvalt. Voorkomt een
handmatige doorloop van 150+ velden bij een toekomstige review.

### 2. NILM-duplicaatdetectie

**Aanleiding**: tijdens de v0.63.90-diagnostiek-review bleken 5
"Eetkamer lamp"-sensoren een identieke vermogensgeschiedenis te delen -
vermoedelijk hetzelfde fysieke circuit onder meerdere HA-entiteiten.

**Fix**: nieuwe `get_nilm_duplicate_pairs()` - vergelijkt elk paar
bevestigde apparaten op hun `daily_avg_history` over de gedeelde dagen.
Binnen een tolerantie van 2% (`NILM_DUPLICATE_TOLERANCE_FRACTION`) en
met minimaal 3 gedeelde dagen (`NILM_DUPLICATE_MIN_SHARED_DAYS`) geldt
een paar als waarschijnlijk duplicaat. Puur informatief. Blootgesteld
via de bestaande NILM-sensor (`waarschijnlijke_duplicaten`) en
diagnostiek.

**Getest** (7 tests, `test_nilm_duplicate_detection.py`): identieke
geschiedenis gemarkeerd; kleine meetruis binnen tolerantie ook
gemarkeerd; wezenlijk verschillende geschiedenis niet; te weinig
gedeelde dagen niet; 3 onderling identieke apparaten leveren 3 paren
op; vergelijking gebruikt alleen de meest recente gedeelde dagen bij
ongelijke geschiedenislengte.

### 3. Advies-gereedheid uitgebreid naar 10 modules

De bestaande "Advies-gereedheid"-sensor beoordeelde 8 modules; de
nieuwe extra-dip-marge (v0.63.87) en temperatuur-regressie (v0.63.88)
hadden nog geen status. Zelfde patroon als de bestaande modules met een
genuine maturiteitssignaal. Sensor hernoemd naar "Advies-gereedheid (10
modules)" (unique_id ongewijzigd, dus geen entity_id-migratie nodig).

**Getest** (4 nieuwe tests + 1 bijgewerkt in `test_advisory_readiness.py`).

### 4. Shortfall/excess-tracking samengevoegd tot één atomische structuur

**Aanleiding**: tijdens dezelfde diagnostiek-review leken
`reserve_shortfall_history` (5 items) en `reserve_shortfall_dates` (1
datum) uit sync - bleek geen actieve bug (de code voegt ze altijd
samen toe), maar wel een structuur die gevoelig is voor toekomstige,
per-ongeluk-uit-sync-lopende uitbreidingen.

**Fix**: de vier losse lijsten (`reserve_shortfall_history`/`_dates`,
`reserve_excess_history`/`_dates`) vervangen door één
`reserve_daily_records`-lijst (dicts met datum + shortfall + excess
samen, altijd atomisch toegevoegd in `_update_shortfall_detection`).
De vier oude namen bestaan nog als afgeleide, read-only properties
(behouden exact dezelfde semantiek: `_dates` bevat één datum per dag,
niet alleen True-dagen) voor volledige achterwaartse compatibiliteit.

**Restore-subtiliteit, opgelost**: `ReserveShortfallSensor` en
`ReserveExcessSensor` herstellen elk hun eigen helft van de data, in
een volgorde die HA niet garandeert. Nieuwe
`_merge_reserve_daily_records()` in `sensor.py` merget beide
restore-acties correct samen op datum, ongeacht restorevolgorde, zonder
dat de een de al herstelde data van de ander overschrijft.

**Getest** (6 nieuwe tests, `test_reserve_daily_records_refactor.py`):
afgeleide properties kloppen; atomische toevoeging; leervenster-
afkapping; merge-functie default't het andere veld correct bij eerste
restore; merge overschrijft niet bij tweede restore; merge werkt
identiek ongeacht restorevolgorde. Bestaande diagnostiek-test
bijgewerkt naar de nieuwe structuur.

**Volledige testsuite**: 487 tests, allemaal groen.

## v0.63.92 — woonkamertemperatuur: absurd veel decimalen op het dashboard

**Gerapporteerd, met screenshot**: de live woonkamertemperatuur toonde
`24.1230773925781 °C` op het Klimaat-tabblad — in twee losse tegels
tegelijk ("Woonkamertemperatuur (live)" en de primaire waarde van
"Airco-verwachting").

**Root cause**: `living_room_current_temp_c` (toegewezen in
`_update_living_room_airco_prediction`) werd nergens afgerond - de
onderliggende temperatuursensor rapporteert zelf met hoge precisie
(bijv. een Zigbee-sensor). De buitentemperatuur toonde wél netjes
afgerond, simpelweg omdat die via de weerentiteit binnenkomt (die zelf
al op 1 decimaal rapporteert) - geen aparte afronding nodig geweest
daar. Beide dashboardtegels lazen bij nader inzien dezelfde
onderliggende, ongeronde coordinator-waarde - één root cause, niet
twee losse bugs.

**Fix**: `round(temp_c, 1)` bij toewijzing, consistent met elke andere
temperatuurweergave in deze integratie.

**Getest**: nieuwe test in `test_climate_tab.py` - bevestigt dat een
sensorwaarde met 13 decimalen correct wordt afgerond naar 1 decimaal.

## v0.63.93 — buitentemperatuur-voorspelling klopte niet + tijdzone-bug blootgelegd

**Gerapporteerd**: "de temperature verwachting van KNMI klopt niet in
de tabellen, het is nu 15.3 graden en in de tabellen wordt 23
weergegeven."

**Uitgezocht met een live `weather.get_forecasts`-aanroep** op de
daadwerkelijke KNMI-entiteit (`weather.knmi_thuis`, opgezocht via
Ontwikkelaarshulpmiddelen) - bleek **geen verwerkingsfout in deze
integratie**: de ruwe KNMI-brondata toonde zelf al 23°C voor het
eerstvolgende uur, tegenover een live meting van 15,3°C - een sprong
die weerkundig niet plausibel is. Root cause bevestigd te liggen bij de
brondata van deze specifieke KNMI-integratie, niet in de verwerking
hier.

**Oplossing, op initiatief van de gebruiker**: overgestapt naar een
nauwkeurigere weerentiteit (`weather.forecast_thuis`), waarvan de
eerste voorspelling (15,9°C) wél goed aansloot bij de live meting.

**Tijdens het vergelijken van beide bronnen een échte, latente bug
blootgelegd**: `weather.forecast_thuis` rapporteert tijdstippen in UTC
(`+00:00`), terwijl `weather.knmi_thuis` toevallig al in lokale tijd
(`+02:00`) rapporteerde. `_async_fetch_hourly_outdoor_forecast` zette
de ontvangen tijdstempel nergens expliciet om naar lokale tijd
(`hour_dt.isoformat()` rechtstreeks op de geparste waarde) - dit werkte
dus tot nu toe alleen "toevallig" goed doordat KNMI zelf al lokale tijd
gebruikte. Met de nieuwe, UTC-gebaseerde bron zou de "Uur"-kolom op het
Klimaat-tabblad 2 uur hebben achtergelopen op de werkelijke lokale
tijd.

**Fix**: `dt_util.as_local()` toegepast direct na het parsen van elke
voorspellings-entry, ongeacht welke tijdzone de brondata zelf
gebruikt - niet langer afhankelijk van toeval bij een specifieke
weerintegratie.

**Getest**: nieuwe test in `test_climate_tab.py`
(`test_fetch_forecast_converts_datetimes_to_local_time`) - bevestigt
via een spy op `dt_util.as_local` dat de tijdzone-conversie
daadwerkelijk wordt aangeroepen voor elke geparste voorspellings-entry.

## v0.63.94 — twee klimaat-tabellen toonden dezelfde betrouwbaarheid

**Gerapporteerd, met screenshot**: "de 2 tabellen lijken hetzelfde weer
te geven." De "Woonkamer (°C)"-kolom verschilde al correct tussen
"Korte termijn (indicatief)" en "Betrouwbaar (≥15 metingen per cel)",
maar de "Betrouwbaarheid"-kolom niet.

**Root cause**: beide dashboardtabellen lazen hetzelfde, enkele
`betrouwbaarheid`-veld per traject-rij - het niveau voor de soepele
"kort termijn"-drempel (≥5 metingen). Een cel met bijv. 8 metingen
toonde daardoor `🟡 indicatief` in **beide** tabellen, ook in de tabel
die specifiek ≥15 metingen belooft, terwijl die daar
`⚪ onvoldoende_data` had moeten tonen.

**Fix**: nieuw, apart veld `betrouwbaarheid_streng` toegevoegd aan
elke traject-rij in `_recompute_climate_trajectory` - alleen
`betrouwbaar` als de ≥15-drempel écht gehaald is, anders altijd
`onvoldoende_data` (nooit `indicatief`). De "Betrouwbaar"-tabel in
`dashboard_template.yaml` gebruikt nu dit nieuwe veld; de "Korte
termijn"-tabel blijft het bestaande `betrouwbaarheid`-veld gebruiken.

**Testinfrastructuur, terzijde**: de dashboard-render-test had nog
geen testdata voor de klimaat-projectietabellen - beide tabellen
werden dus alleen in hun lege-staat getest. Testdata toegevoegd,
waardoor nu ook zichtbaar bevestigd wordt dat beide tabellen bij
dezelfde onderliggende rij daadwerkelijk een andere betrouwbaarheids-
status tonen.

**Getest**: nieuwe test
(`test_indicatief_cell_shows_onvoldoende_data_in_the_strict_field`) in
`test_climate_tab.py` - bevestigt dat een cel met 8 metingen (genoeg
voor "indicatief", niet voor "betrouwbaar") `betrouwbaarheid_streng`
op `onvoldoende_data` zet, terwijl het bestaande `betrouwbaarheid`-veld
ongewijzigd `indicatief` blijft tonen.

## v0.63.95 — achtertuinsensor + geleerde bias-correctie voor de klimaat-projectie

**Gevraagd**: "zijn er zaken waardoor ik de voorspelling kan
verbeteren, door bijvoorbeeld correlaties? Ik heb ook een
temperatuursensor in mijn achtertuin hangen" - beide voorgestelde
richtingen gecombineerd gebouwd.

### 1. Achtertuinsensor als voorkeursbron

`_get_live_outdoor_temp_c()` gebruikt nu, indien geconfigureerd
(nieuwe optie `backyard_temperature_sensor_entity`), eerst de eigen
fysieke achtertuinsensor - nauwkeuriger voor de eigen locatie dan een
regionale weerentiteit-schatting. Valt terug op KNMI/OpenWeatherMap
zonder configuratie - volledig optioneel.

### 2. Geleerde bias-correctie op de hele 24-uurs-voorspelling

Nieuwe state `climate_forecast_bias_history` en property
`climate_forecast_learned_bias_c`. Elke keer dat de voorspelling
ververst wordt (max. 1x/30 min), wordt de eerstvolgende voorspelde
waarde vergeleken met de actuele achtertuinsensor-meting - dat
verschil (°C, additief, bewust geen procentuele correctie zoals bij de
zonvoorspelling - temperatuur kent geen zinvolle nulpuntschaal daarvoor)
wordt bijgehouden in een rollend venster (nieuwe constante
`CLIMATE_FORECAST_BIAS_HISTORY_LENGTH`, 100 samples) en toegepast op
**elk uur** van de projectie in `_recompute_climate_trajectory`, niet
alleen het startpunt. Vereist minimaal 5 samples (nieuwe constante
`CLIMATE_FORECAST_BIAS_MIN_SAMPLES`) voordat de correctie actief
wordt.

**Zichtbaarheid**: nieuwe dashboardtegel op het Klimaat-tabblad toont
de huidige geleerde bias + aantal samples. Nieuwe attributen
(`voorspelling_bias_c`, `voorspelling_bias_geschiedenis`) op de
bestaande klimaat-projectie-sensor, met RestoreEntity-herstel.
Toegevoegd aan diagnostiek.

**Getest** (14 nieuwe tests in `test_climate_tab.py`): achtertuinsensor
krijgt voorrang boven de weerentiteiten; correcte terugval zonder
achtertuinsensor-meting; geen bias-sample zonder geconfigureerde
sensor; geleerde bias is `None` bij te weinig samples (< 5); gemiddelde-
berekening klopt; geschiedenis wordt afgekapt tot 100; en de correctie
werkt daadwerkelijk door op de héle trajectory - inclusief welke
geleerde rate-cel per uur wordt opgezocht, niet alleen de weergegeven
temperatuur.

**Volledige testsuite**: 498 tests, allemaal groen.

## v0.63.96 — uitschieter-filter voor de achtertuinsensor

**Gerapporteerd, met grafiek**: de nieuwe achtertuinsensor (v0.63.95)
kan 's ochtends kort in direct zonlicht hangen, wat een plotselinge,
kortstondige sprong in de gemeten temperatuur veroorzaakt - de
sensorbehuizing warmt zelf op, los van de werkelijke luchttemperatuur.
Zonder filtering zou dit zowel het live-anker als de bias-leer-
geschiedenis kunnen vervuilen.

**Fix**: nieuwe, gedeelde `_get_filtered_backyard_temp_c(now)`. Een
sprong die de plausibele afkoel/opwarm-snelheid van buitenlucht
(nieuwe constante `BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR`,
4°C/uur) ver overschrijdt, wordt niet meteen vertrouwd - de vorige,
geaccepteerde waarde blijft gelden totdat de nieuwe waarde minstens
`BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES` (45 min) aanhoudt (binnen een
tolerantiemarge, `BACKYARD_TEMP_SPIKE_TOLERANCE_C`, tegen kleine
meetruis tijdens het wachten). Een kortstondige zonneflits zakt
vanzelf terug voor dit venster verstrijkt en wordt genegeerd; een
echte, aanhoudende verandering (bijv. een koufront) wordt na dit
venster alsnog geaccepteerd.

Zowel `_get_live_outdoor_temp_c` (live-anker) als de bias-sample-
berekening in `_async_maybe_refresh_outdoor_forecast` (v0.63.95) lopen
nu door dit gedeelde filter, zodat beide mechanismen consistent
beschermd zijn.

**Bewust géén RestoreEntity** voor de filter-state - de tijdschalen
zijn kort (minuten tot ~45 min), dus een reset bij herstart is
verwaarloosbaar.

**Zichtbaarheid**: nieuwe waarschuwingskaart op het Klimaat-tabblad,
alleen zichtbaar wanneer een uitschieter daadwerkelijk wordt genegeerd.
Nieuw attribuut `achtertuinsensor_uitschieter_genegeerd` op de
klimaat-projectie-sensor. Toegevoegd aan diagnostiek.

**Getest** (5 nieuwe tests in `test_climate_tab.py`): eerste meting
direct geaccepteerd; plausibele geleidelijke verandering direct
geaccepteerd; kortstondige zonneflits genegeerd (vorige waarde blijft
gelden) totdat die zelf terugzakt; aanhoudende verandering alsnog
geaccepteerd na het bevestigingsvenster; geen filter-activiteit zonder
geconfigureerde achtertuinsensor.

**Volledige testsuite**: 503 tests, allemaal groen.

## v0.63.97 — nieuw "Live"-tabblad: lopend verhaal over wat de integratie doet

**Gevraagd**: "een tabblad wat live vertelt wat de gehele integratie
doet, dit om mijzelf ook bewuster te maken wat er gebeurt op alle
vlakken en mogelijk weer extra input aan jou kan geven." Op verzoek
server-side gegenereerd (niet losse dashboard-teksten aan elkaar
geplakt) voor een écht vloeiend verhaal - kost meer bouwtijd, expliciet
zo gekozen.

**Nieuwe `get_live_narrative(now)`** combineert bestaande state uit
meerdere onderdelen tot één lopend verhaal, elk met een eigen, apart
testbare deelfunctie:
- `_narrate_battery_decision` - hergebruikt de al bestaande, rijke
  `last_explanation` als kernalinea.
- `_narrate_appliances` - lopende vaatwasser/wasmachine-cyclus + duur.
- `_narrate_water` - actief waterverbruik, of het dagtotaal.
- `_narrate_nilm` - openstaande kandidaten + mogelijk defecte
  apparaten.
- `_narrate_climate` - klimaat-projectie-status of verwachte
  temperatuur.
- `_narrate_attention` - aandachtspunten uit de bestaande
  gezondheidscheck-samenvatting (v0.63.91).

Puur informatief/samenvattend - berekent zelf niets nieuws, stuurt
niets aan.

**Nieuwe sensor** `LiveNarrativeSensor` - state afgekapt op 255 tekens
(HA's limiet), volledige tekst in het `verhaal`-attribuut. Niet een
RestoreEntity. Toegevoegd aan diagnostiek.

**Nieuw dashboardtabblad "Live"** (negende tabblad).

**Getest** (16 nieuwe tests: 14 voor de verhaal-generator,
2 voor de sensor): elk onderdeel apart getest, inclusief correcte
grammatica bij 1 vs. meerdere NILM-kandidaten, stilte wanneer een
onderdeel niets te melden heeft, en de 255-tekens-afkapping.

**Volledige testsuite**: 519 tests, allemaal groen.

## v0.63.98 — water-sessiedetectie: live event-driven i.p.v. tick-gebaseerd

**Gerapporteerd, met screenshot + ruwe sensorgeschiedenis (CSV)**: "in
de tabel ontbreekt mijn inziens data" - het dagtotaal (60,87L) klopte,
maar "Recente gebruiksmomenten" toonde slechts 1 sessie terwijl de
ruwe geschiedenis 64 losse verbruiksstoten liet zien.

**Root cause, bevestigd via analyse van de aangeleverde CSV**: de
sessiedetectie las het live debiet uitsluitend op de gewone
5-minuten-tick. Verbruiksstoten duren vaak maar 15-90 seconden (handen
wassen, toilet doorspoelen) - een steekproef elke 5 minuten heeft
simpelweg te weinig kans om zo'n kort venster te raken. Het dagtotaal
bleef correct omdat dat van een aparte, cumulatieve tellersensor komt.

**Bredere relevantie, op verzoek onderzocht**: apparaat-tracking
(vaatwasser/wasmachine, uren lang) en NILM (dagelijkse gemiddelden)
zijn veel minder gevoelig - die lopen lang genoeg dat een 5-minuten-
tick ze sowieso vangt. Alleen water is uniek kwetsbaar.

**Ontwerpafweging, "Wat gebeurt er als we naar live tikken gaan?"**:
géén pure event-driven oplossing. Analyse van de ruwe geschiedenis
liet gaten tot bijna 7 uur zien tussen sensor-updates zolang het
debiet stil op 0 staat - een pure event-driven afronding zou een
sessie soms uren kunnen laten vastzitten, wachtend op een event dat
niet komt.

**Fix**: sessielogica uit `_update_water_tracking` geëxtraheerd naar
een nieuwe, gedeelde `_process_water_flow_sample(flow, now)`, nu
aangeroepen vanuit twee plekken:
1. Nieuwe **live listener** `_handle_water_flow_change`
   (`async_track_state_change_event` op de watersensor,
   geregistreerd in `async_setup`, opgeruimd in `async_unload`) -
   reageert direct op élke wijziging.
2. De bestaande **5-minuten-tick** blijft draaien als vangnet voor de
   *afronding* van een sessie.

**Getest** (6 nieuwe tests, `test_water_live_tracking.py`): een stoot
van 20 seconden (het exacte scenario uit het rapport) correct
gedetecteerd via de listener; de tick rondt een sessie alsnog af
zonder verdere events; ongeldige/lege state-waarden veilig genegeerd;
listener alleen geregistreerd met geconfigureerde watersensor.

**Volledige testsuite**: 525 tests, allemaal groen.

## v0.63.99 — drie verbeteringen naar aanleiding van het Live-tabblad

Het nieuwe Live-tabblad (v0.63.97) leverde meteen concrete input op:
51 onbevestigde NILM-kandidaten, 18 waarschijnlijke duplicaatparen, en
6 aanhoudend "mogelijk defect"-apparaten. Op verzoek ("de integratie
moet eigenlijk met de minuut beter worden") alle drie opgepakt.

### 1 & 2. Zichtbaarheid voor onbevestigde kandidaten en duplicaten

Beide datasets bestonden al, maar stonden nergens op het dashboard -
alleen bereikbaar via diagnostiek. Twee nieuwe markdown-tabellen op
het Apparaten-tabblad: "Onbevestigde NILM-kandidaten" (voorbeeld van
max 20, naam + vermogen) en "Waarschijnlijke NILM-duplicaten" (elk
paar met gedeelde-dagen-telling + verwijzing naar de juiste service).

### 3. CUSUM-uitschieter-plafond

**Root cause**: een geïsoleerde uitschieterdag (bijv. eenmalig 45W
tegen een referentie van 6,2W) leverde zonder plafond een
ongeplafonneerde bijdrage van >6 aan de CUSUM-accumulator in één klap
- ver boven de alarmdrempel (1,0) - en liet het alarm daardoor
langdurig afgaan, ook al was het structurele gemiddelde over de hele
periode maar +2,4%.

**Fix**: nieuwe constante `NILM_CUSUM_MAX_DAILY_CONTRIBUTION` (0,5) in
`_finalize_nilm_device_day` - begrenst de maximale bijdrage van één
dag aan de accumulator. Alleen de positieve kant is begrensd; een
ongewoon lage meting (die de accumulator omlaag trekt) blijft
ongeplafonneerd.

**Let op voor bestaande installaties**: corrigeert de berekening voor
toekomstige dagen, herberekent de al opgeslagen accumulator-waarde
niet met terugwerkende kracht - gebruik `unconfirm_nilm_device` voor
een meteen schone lei bij een al aanhoudend gealarmeerd apparaat.

**Getest** (3 nieuwe tests, `test_nilm_cusum_outlier_cap.py`): een
enkele geïsoleerde uitschieter triggert het alarm niet meer; een
structurele, aanhoudende afwijking triggert het nog steeds terecht;
een negatieve afwijking blijft ongeplafonneerd.

**Volledige testsuite**: 528 tests, allemaal groen.

## v0.63.100 — NILM-alarm lost zichzelf voortaan live op

**Vervolgvraag na v0.63.99**: "kan dit soort zaken eerder in
diagnostiek worden opgevangen, het mooiste zou natuurlijk iets in de
integratie zijn wel dit live zelf in Home Assistant oplost?"

**Aanleiding**: het v0.63.99-plafond voorkomt toekomstige uitschieter-
gestuurde alarmen, maar een al opgebouwde, verouderde accumulator
bouwt via de normale, kleine dagelijkse afbouw extreem traag af -
doorgerekend voor het gerapporteerde CV-ketel-scenario: bijna 90
dagen.

**Fix 1 - auto-reset**: nieuwe constante `NILM_CUSUM_RESET_STREAK_DAYS`
(5) in `_finalize_nilm_device_day`. Zodra een apparaat dit aantal
opeenvolgende dagen een genuine terugkeer naar normaal laat zien (de
RUWE dagwaarde op of onder de referentie, gemeten vóór het v0.63.99-
plafond wordt toegepast), wordt de accumulator direct volledig
gereset. Een dag die de streak onderbreekt reset de teller naar 0 -
vereist dus daadwerkelijk aaneengesloten dagen, niet "de meeste".

**Fix 2 - diagnostiek-context**: `get_diagnostic_summary()` toont nu,
voor elk actief alarm met een lopende streak, expliciet "X dag(en) op
rij weer normaal - herstelt vanzelf over nog Y dag(en)" - in plaats
van alleen een kale "mogelijk defect"-melding.

**Getest** (5 nieuwe tests: 3 in `test_nilm_cusum_outlier_cap.py`,
2 in `test_diagnostic_summary.py`): reset na aanhoudende terugkeer
naar normaal; streak-teller reset correct bij onderbreking; geen
onbedoelde reset zonder actief alarm; herstelvoortgang getoond bij
lopende streak; geen melding zonder streak.

**Volledige testsuite**: 533 tests, allemaal groen.

## v0.63.101 — vijf klassieke EMS-kengetallen toegevoegd

**Gevraagd**: "heb je nog zaken voor een typisch EMS welke we kunnen
toevoegen?" - bevestigd: "ik zou ze allemaal wel willen integreren".
Nieuw dashboardtabblad "EMS-KPI's" bundelt alle vijf.

### 1. Piekvermogen-tracking (capaciteitstarief)

Nieuwe `_update_peak_power_tracking` + `PeakPowerSensor`. Houdt het
hoogste gemeten netto-netimport-vermogen bij op drie niveaus (vandaag/
maand/all-time), op basis van de RUWE P1-meter-aflezing (niet de
gecorrigeerde huishoudverbruik-schatting - een capaciteitstarief
rekent af op wat het net zelf ziet). RestoreEntity.

### 2. Tegenfeitelijke besparingsvergelijking

Nieuwe `_update_counterfactual_savings` + `CounterfactualSavingsSensor`.
Reconstrueert per tick wat de netmeter zonder accu-sturing zou hebben
getoond (P1 + accu-vermogen, zelfde PV), rekent beide scenario's tegen
dezelfde dynamische prijs af. RestoreEntity.

### 3. Zelfconsumptie-/zelfvoorzieningsratio

Nieuwe `_update_self_sufficiency_tracking` + `SelfSufficiencySensor`.
Zelfconsumptie = deel van eigen PV-productie zelf verbruikt (niet
geëxporteerd). Zelfvoorziening = deel van totaal verbruik gedekt door
eigen bronnen (niet geïmporteerd).

### 4. Accu-gezondheid over de lange termijn

Nieuwe `_update_battery_cycle_tracking` + `BatteryHealthSensor` +
constante `BATTERY_CYCLES_TO_80_PERCENT_CAPACITY` (4000). Cyclus-
telling (cumulatieve ontladen energie / capaciteit) + een lineair
gemodelleerde, NADRUKKELIJK als schatting gelabelde capaciteits-
degradatie - geen gemeten waarde. RestoreEntity (levenslange teller).

### 5. CO2-intensiteit van het net

Nieuwe optionele config `co2_intensity_sensor_entity`,
`_update_co2_tracking` + `CO2IntensitySensor`. Uitstoot van
geïmporteerde energie (huidige intensiteit × geïmporteerde kWh).

**Getest** (35 nieuwe tests: 7 piekvermogen, 7 tegenfeitelijke
besparing, 7 zelfvoorziening, 9 accu-gezondheid, 5 CO2): elke feature
apart, inclusief dag/maand-rollover, randgevallen (geen sensor,
export i.p.v. import, grote hiaten na herstart), en het degradatie-
model dat correct clampt op 80% i.p.v. door te extrapoleren.

**Volledige testsuite**: 568 tests, allemaal groen.

## v0.63.102 — Airco-verwachting-tegel toonde temperatuur i.p.v. kans

**Gerapporteerd, met screenshot**: de "Airco-verwachting"-tegel op het
Klimaat-tabblad toonde als hoofdwaarde een temperatuur (identiek aan
de "Woonkamertemperatuur (live)"-tegel ernaast), terwijl de kans-op-
airco-binnen-1-uur alleen in de kleinere subtekst stond.

**Verklaring**: `LivingRoomAircoPredictionSensor.native_value` is
bewust de temperatuur-bucket die wordt bijgehouden (voor HA-
statistieken/grafieken), met de voorspelling als apart attribuut - een
geldige technische keuze, maar verwarrend als dashboardweergave.

**Fix**: alleen de dashboardkaart in `dashboard_template.yaml`
aangepast (de sensor zelf ongewijzigd) - primary toont nu de kans-
procent, secondary toont de temperatuur waarbij die kans hoort.

## v0.63.103 — NILM: eigen sensoren + SolarFlow/Solcast bleven als kandidaat terugkomen

**Gerapporteerd**: "elke keer terug krijg onbevestigde kandidaten na
herstart", met een concrete lijst van 19 entiteiten - daaruit bleken
twee structurele bugs.

**Bug 1 - eigen-integratie-sensoren als NILM-kandidaat**: "Energy
Management System Hourly consumption profile" en "Energy Management
System Piekvermogen" (v0.63.101) rapporteren zelf ook in Watt en
werden voorgesteld als "apparaat" - geen check tegen de eigen
entiteiten van deze integratie.

**Fix**: nieuwe `_is_own_integration_entity()` in coordinator.py - elke
entity_id van deze integratie volgt het patroon
`sensor.<apparaat>_energy_management_system_<naam>`, dus `DOMAIN` als
substring is een betrouwbare, generieke uitsluiting. Toegepast in
zowel `_update_nilm_discovery` als `_prune_nilm_pattern_excluded_entries`
(terugwerkende opruiming van al-ontdekte eigen sensoren).

**Bug 2 - ontbrekende naampatronen**: de batterij verschijnt onder de
merknaam "SolarFlow" (niet "zendure") in entity-namen ("SolarFlow 2400
AC PV1 Solar Power" etc.) - alleen "zendure" stond in
`NILM_PATTERN_EXCLUDED_KEYWORDS`. Solcast-voorspellingssensoren en
gespiegelde accu-signalen ("... (omgekeerd)") hadden hetzelfde
probleem.

**Fix**: `NILM_PATTERN_EXCLUDED_KEYWORDS` uitgebreid met "solarflow",
"solcast", "(omgekeerd)".

**Getest** (6 nieuwe tests in `test_nilm_pattern_exclusion.py`):
SolarFlow/Solcast/gespiegelde-accu-entiteiten worden nooit meer
kandidaat; eigen-integratie-sensoren worden nooit kandidaat; een
legitiem apparaat blijft gewoon gevonden worden naast deze
uitsluitingen; bestaande, al-bevestigde eigen-integratie-entiteiten
worden met terugwerkende kracht opgeruimd.

**Volledige testsuite**: 574 tests, allemaal groen.

## v0.63.104 — zonoverschot-schatting gebruikte trage i.p.v. live correctie

**Gerapporteerd, met screenshot**: "dit komt niet overeen met de
werkelijkheid 55W, het overschot is veel groter op dit moment."

**Root cause, gevonden door twee PV-schattingsfuncties in dezelfde
codebase te vergelijken**: `_estimate_pv_kwh_for_period` (gebruikt in
de tekortberekening) gebruikt AL Solcast's eigen live "resterend
vandaag"-sensor om de voorspelling real-time bij te stellen op basis
van daadwerkelijk waargenomen omstandigheden
(`_get_pv_remaining_correction_ratio`). Maar `_get_expected_pv_power_w`
- specifiek gebruikt voor de "moet ik nu zonoverschot vangen"-
beslissing waar dit rapport over gaat - gebruikte uitsluitend de
trage, langetermijn-geleerde uur-bias-ratio, zonder deze live
correctie. Op een dag zonniger dan het langetermijngemiddelde voor dat
uur, gaf dit stelselmatig een te lage verwachting.

**Fix**: `_get_expected_pv_power_w` probeert nu eerst de live
"resterend vandaag"-correctieratio, valt pas terug op de trage
geleerde uur-ratio als die niet beschikbaar is - dezelfde
prioriteitsvolgorde die elders al gold. Zonder geconfigureerde
`solar_remaining_today_sensor_entity` blijft het oude gedrag
ongewijzigd (geen regressie).

**Getest** (2 nieuwe tests in `test_arbitrage_forecast_not_live_pv.py`):
live correctie krijgt voorrang boven de geleerde ratio wanneer beide
beschikbaar zijn; zonder geconfigureerde live-sensor blijft het
bestaande gedrag ongewijzigd.

**Volledige testsuite**: 576 tests, allemaal groen.

## v0.63.105 — overzicht van ontbrekende optionele functies

**Gevraagd**: "er zijn natuurlijk meerdere entiteiten welke ik
manueel moet invullen, kun je een melding ergens op een geschikt
dashboard plaatsen wanneer er 1 ontbreekt?"

**Nieuwe `get_missing_optional_features()`** in coordinator.py - een
curated lijst van negen optionele sensoren die een zichtbare functie
ontgrendelen: achtertuinsensor, Solcast-live-correctie, CO2-
intensiteit, accu-capaciteit, woonkamertemperatuur, water,
meldingsservice, vaatwasser-vermogen, wasmachine-vermogen - plus een
aparte KNMI-of-OpenWeatherMap-check (één van beide is voldoende).
Bewust geen volledige lijst van elke config-key - kernvereisten
(prijs/accu/PV/verbruik/SoC) blijven buiten beschouwing.

**Nieuwe sensor** `MissingOptionalFeaturesSensor` - state is het
aantal ontbrekende functies, volledige lijst (naam + wat het
ontgrendelt) als attribuut. Niet een RestoreEntity.

**Nieuwe waarschuwingskaart op het Live-tabblad**, direct onder het
lopende verhaal - verschijnt alleen als er daadwerkelijk iets
ontbreekt. Toegevoegd aan diagnostiek.

**Getest** (6 nieuwe tests in `test_missing_optional_features.py`):
alles ontbreekt zonder configuratie; een geconfigureerde sensor
verdwijnt uit de lijst; de KNMI/OpenWeatherMap-OR-check werkt in beide
richtingen; elke melding heeft een naam en uitleg; een volledig
geconfigureerde installatie geeft een lege lijst.

**Volledige testsuite**: 582 tests, allemaal groen.

## v0.63.106 — NILM: fase 2/3 en een tweede zon-voorspellingsintegratie glipten erdoor

**Gerapporteerd, met screenshot**: "Solar Production entiteiten en P1
meter vermogen mogen sowieso uitgesloten worden."

**Gevonden**: twee gaten in de bestaande patroonuitsluiting
(v0.63.89/.103):
1. Alleen "fase 1" stond in `NILM_PATTERN_EXCLUDED_KEYWORDS`, niet
   "fase 2"/"fase 3" - "P1 meter Vermogen fase 3" glipte erdoorheen.
2. Een andere zon-voorspellingsintegratie ("Solar production
   forecast", andere naamgeving dan "solcast") werd nog niet herkend.

**Fix**: `NILM_PATTERN_EXCLUDED_KEYWORDS` uitgebreid met "fase 2",
"fase_2", "fase 3", "fase_3", "solar production", "p1 meter".

**Getest** (3 nieuwe tests in `test_nilm_pattern_exclusion.py`):
P1-meter-fase-3 en de nieuwe zon-voorspellingsintegratie worden nooit
meer kandidaat; fase 2 wordt ook correct uitgesloten.

**Volledige testsuite**: 585 tests, allemaal groen.

## v0.63.107 — NILM-knop: bevestigde/afgewezen keuzes konden op het verkeerde apparaat landen

**Gevraagd**, na de v0.63.103/.106-fixes: "heb je ook gekeken waarom
keuzes welke ik reeds gemaakt heb niet werden opgeslagen en na een
herstart dus weer terug kwamen?" - scherper dan de eerdere patroon-
gaten (die alleen verklaren waarom *nieuw ontdekte* entiteiten bleven
verschijnen).

**Root cause, gevonden in `button.py`, niet in de opslag zelf** (die
was al eerder deze sessie met echte diagnostiekdata bevestigd correct
te werken): `NilmConfirmCandidateButton`/`NilmRejectCandidateButton`'s
`async_press()` riep `get_nilm_candidate_at_slot(self._slot)` OPNIEUW
aan op het moment van drukken, in plaats van het entity_id te
gebruiken dat op het scherm werd getoond. Als de sleuf-inhoud
tussentijds verschoof (bijv. een nieuw ontdekte, alfabetisch eerdere
kandidaat) tussen het TONEN van de knop en het DRUKKEN erop,
bevestigde/wees de gebruiker in werkelijkheid een ANDER apparaat af
dan bedoeld - het apparaat dat ze écht wilden afwijzen bleef gewoon
staan en kwam na een herstart terug.

**Fix**: nieuw `_last_displayed_entity_id`-veld op `_NilmSlotButton`,
vastgelegd via `_resolve_and_cache_slot_entity_id()` zodra het
entity_id voor weergave wordt opgevraagd (`_slot_label`/
`extra_state_attributes`). `async_press()` gebruikt nu exact deze
vastgelegde waarde in plaats van een verse opvraag - met een veilige
terugval voor het randgeval dat er nog nooit iets is vastgelegd.

**Getest** (3 nieuwe tests in `test_nilm_dashboard_buttons.py`):
reproduceert het exacte race-condition-scenario voor zowel bevestigen
als afwijzen, plus de terugval-test.

**Volledige testsuite**: 588 tests, allemaal groen.

## v0.63.108 — drie proactieve checks toegevoegd aan de diagnostiek-samenvatting

**Gevraagd**: "ik denk dat je vele zaken welke ik vandaag en gister
heb aangedragen moet zien te detecteren in de diagnose, kun je dit
herzien?" - drie nieuwe checks in `get_diagnostic_summary()`.

**1. Klimaat-projectie zonder enkele geleerde cel, ondanks tijd**:
als `living_room_temperature_sensor_entity` geconfigureerd is, er
al ≥2 dagen zijn verstreken sinds `first_seen_date`, en géén enkele
cel in `climate_rate_history` data heeft - verklaart expliciet waarom
"Korte termijn"/"Betrouwbaar" er identiek uitzien.

**2. Ongewoon groot aantal onbevestigde NILM-kandidaten**: nieuwe
constante `NILM_CANDIDATE_COUNT_ATTENTION_THRESHOLD` (15) - signaal om
de patroon-uitsluiting te herzien i.p.v. individueel te beoordelen.

**3. Waterverbruik: dagtotaal veel hoger dan geregistreerde sessies**:
als het dagtotaal (≥20L) een stuk hoger is dan wat vandaags
gebruiksmomenten verklaren (<30%) - resterend signaal voor gemiste
stoten, ook na v0.63.98.

**Testinfrastructuur, terzijde**: 18 bestaande testbestanden bleken
`dt_util.now` globaal te monkeypatchen zonder herstel na afloop. De
nieuwe tests zijn zelf expliciet gepatcht en ruimen zichzelf netjes op
met een lokale, autouse fixture in `test_diagnostic_summary.py`.

**Getest** (8 nieuwe tests): elke check apart voor triggeren/niet-
triggeren, inclusief het randgeval "te vroeg om data te verwachten".

**Volledige testsuite**: 596 tests, allemaal groen.

## v0.63.109 — systeemstatus-tegel toonde "OK" ondanks inhoudelijke aandachtspunten

**Gevraagd, met screenshot**: "misschien iets van een self-diagnose
toevoegen zodat ik ook in de button relevante en dus systeem status ok
niet klopt eigenlijk kan zien."

**Root cause**: `system_status` was puur een technische health-check
(crash/vastlopen) - toonde "OK" ook als `get_diagnostic_summary()` wél
degelijk aandachtspunten had.

**Fix**: derde status "Aandacht gewenst" toegevoegd aan
`system_status` in coordinator.py - alleen wanneer de integratie
technisch prima draait maar er inhoudelijke aandachtspunten zijn.
Blijft apart van "Fout"/"Mogelijk vastgelopen" (ernstiger).

**Subtiliteit, opgelost tijdens het testen**: een oude, herstelde fout
die enkel nog als historisch "laatste fout"-veld blijft staan mag niet
op zichzelf "Aandacht gewenst" triggeren (al preciezer afgedekt door
de bestaande "Fout"-check) - die ene aandachtspunt wordt nu specifiek
genegeerd bij het bepalen van "Aandacht gewenst".

**Zichtbaarheid**: volledige aandachtspunten-lijst als attribuut op
`SystemStatusSensor`. Dashboardkaart (de kaart uit de screenshot)
uitgebreid naar drie kleuren (groen/oranje/rood) i.p.v. twee, plus het
aantal aandachtspunten in de subtekst.

**Getest** (3 nieuwe tests in `test_system_status.py`): "Aandacht
gewenst" verschijnt correct; een oude herstelde fout triggert dit niet
op zichzelf; een actieve fout blijft "Fout" tonen, niet gedegradeerd.

**Volledige testsuite**: 599 tests, allemaal groen.

## v0.63.110 — piekvermogen verduidelijkt: netimport, niet totaal huishoudverbruik

**Gerapporteerd, met twee screenshots**: "Piekvermogen verbruik klopt
niet, het standaard energie dashboard van Home Assistant zelf geeft
aan dat het huidige verbruik al 247W is" (tegenover een geregistreerde
piek van 107W).

**Uitgezocht, bleek geen bug**: HA's eigen "Stroomverbruik" berekent
het TOTALE huishoudverbruik (P1 + accu + PV samen). Piekvermogen volgt
bewust alleen de NETIMPORT via de P1-meter (relevant voor
capaciteitstarief). Legitiem lager zodra de accu/zon een deel van het
verbruik dekt.

**Fix**: puur verduidelijking, geen gedragswijziging. `PeakPowerSensor`
hernoemd naar "Piekvermogen (netimport)", nieuw `note`-attribuut,
dashboardkaart (titel + tegel-labels) aangepast om het onderscheid
expliciet te maken.

**Volledige testsuite**: 599 tests, allemaal groen (geen nieuw gedrag
om te testen - puur tekst/labels).

## v0.63.111 — werkelijk huishoudverbruik toegevoegd + "Huidig verbruik" verduidelijkt

**Gevraagd, vervolg op v0.63.110**: "Kun je ergens wel toevoegen wat
mijn actuele huisverbruik is... Huidig verbruik heeft hier misschien
ook een verkeerde naamgeving?" - de "Huidig verbruik"-tegel op het
Overzicht-tabblad toonde de kale P1-meter-aflezing (-24,0W in het
gerapporteerde screenshot), negatief bij export.

**Nieuwe sensor** `HouseholdConsumptionSensor` in sensor.py -
hergebruikt `_read_corrected_consumption_power()` (P1 + accu + PV,
zelfde formule als HA's eigen Energiedashboard). Altijd ≥ 0.

**Dashboard**: bestaande P1-tegel hernoemd naar "Netstroom, P1 (kan
negatief zijn bij export)", nieuwe tegel ernaast voor het werkelijke
huishoudverbruik.

**Getest** (2 nieuwe tests in `test_household_consumption_sensor.py`):
berekening klopt bij export met PV-dekking; `None` zonder leesbare
P1-sensor.

**Volledige testsuite**: 601 tests, allemaal groen.

## v0.63.112 — systeemstatus-tegel toonde aantal aandachtspunten zonder de inhoud

**Gerapporteerd, met screenshot**: "De update van de integratie is
leuk, maar waar is aandacht voor vereist?" - v0.63.109 toonde het
aantal ("5 aandachtspunt(en)"), maar niet de inhoud.

**Fix**: nieuwe markdown-kaart direct onder de systeemstatus-tegel op
het Overzicht-tabblad in `dashboard_template.yaml`, toont de volledige
lijst zodra die niet leeg is. Hergebruikt het bestaande
`aandachtspunten`-attribuut, geen nieuwe berekening.

**Volledige testsuite**: 601 tests, allemaal groen (puur dashboard-
wijziging, geen nieuw Python-gedrag).

## v0.63.113 — Overzicht-tabblad herzien: balans + compactheid

**Gerapporteerd, met screenshot**: "het past niet meer op 1 pagina en
vele lege ruimte." Gevraagd: kolommen beter in balans + compacter -
"allebei".

**Root cause**: HA's "sections"-layout (masonry-gedrag) plaatst nieuwe
kaartblokken in de kortste kolom op dat moment. De eerste kolom
(uitgebreide beslistabel + -tekst) was veel langer dan de rest,
resulterend in scheve verdeling en lege ruimte onderin de kortere
kolommen.

**Compacter**: titelkaart verwijderd (overlapte met tabnaam +
uitlegtekst), "Modus & besluit"-uitlegblok van vaste `rows: 3` (moest
scrollen) naar `rows: auto`, "Accu & rendement" + "Live cijfers"
samengevoegd tot één sectie.

**Beter gebalanceerd**: de lange "Actuele beslissing (detail)"-kaart
(15 regels) gesplitst in "Kernbeslissing (detail)" (9 regels) en
"Advies-modules (detail, adviserend)" (6 regels) - kleinere blokken
verdelen natuurlijker over de masonry-kolommen.

**Resultaat**: van 4/3/4/6/7/2 naar 3/8/7/8/2/2 kaarten per sectie -
veel gelijkmatiger, zonder functionaliteit te verliezen.

**Volledige testsuite**: 601 tests, allemaal groen (puur dashboard-
herstructurering, geen Python-wijzigingen).

## v0.63.114 — gauge-kaarten vervangen door compacte tegels

**Gevraagd**: "De gauge kaarten zijn ook veel te groot dit mogen wat
mij betreft de zelfde kaarten worden als de live cijfers."

**Fix**: alle drie de `type: gauge`-kaarten (Accu SoC + Geleerd
rendement op Overzicht; Geleerd accu-rendement op Zelflerend, waar het
al inconsistent naast een mushroom-template-card stond) vervangen door
`mushroom-template-card`, consistent met de "Live cijfers"-tegels.
Kleurindicatie behouden via `icon_color`, dezelfde drempels als de
oude `severity`-instelling.

**Volledige testsuite**: 601 tests, allemaal groen (puur dashboard-
wijziging).

## v0.63.115 — NILM-keuzes overleefden geen herstart (Store werd afgekapt op 20)

**Gerapporteerd** (ná v0.63.107): "Keuzes voor NILM apparaten worden nog
steeds niet opgeslagen, de onbevestigde lijst blijft terug komen na een
herstart." Dashboard toonde 23 kandidaten en exact 20 bevestigde
apparaten — dat getal 20 is precies
`NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT`.

**Root cause** (een andere dan v0.63.107): `async_setup_entry` riep
`async_forward_entry_setups()` aan vóór `coordinator.async_setup()`, en
dus vóór de NILM-Store-load. Daardoor draaide
`NilmConfirmedDevicesSensor.async_added_to_hass` altijd met lege lijsten,
concludeerde daaruit ten onrechte dat de Store leeg was, en viel bij élke
herstart terug op het eenmalig bedoelde migratiepad vanuit de eigen
herstelde entiteit-state. Die attributen zijn met opzet afgekapt op 20
items (recorder-limiet, v0.63.45/.66). Vervolgens schreef die methode het
afgekapte resultaat onvoorwaardelijk terug naar de Store en overschreef
zo de volledige inhoud. Pas daarna las de coordinator de verminkte Store
terug. Effect was progressief: de lijsten konden nooit boven 20 uitkomen.

**Bewijs**: productievolgorde nagebootst tegen v0.63.114-code met 60
bevestigde apparaten in de Store → `assert 20 == 60` na één herstart.

**Waarom niet eerder gevangen**: de bestaande test
`test_sensor_does_not_migrate_when_store_already_has_data` zette de
Store-inhoud handmatig in het geheugen — precies de toestand die in
productie nooit werd bereikt. De test controleerde het bedoelde gedrag,
niet de werkelijke bedrading.

**Fix** (drie lagen, elk afzonderlijk voldoende):
- `__init__.py`: Store laden vóór platform-setup, via de nieuwe publieke
  `coordinator.async_load_persisted_nilm_state()`. De load in
  `async_setup()` blijft als vangnet en is idempotent gemaakt.
- `coordinator.py`: expliciete vlaggen `_nilm_store_loaded` /
  `_nilm_store_had_data` + publieke property `nilm_store_had_data`, zodat
  het migratiepad niet meer hoeft te gissen op "geheugen is leeg".
- `sensor.py`: migratiepad wordt volledig overgeslagen zodra de Store
  data had; afgewezen entiteiten worden samengevoegd (union) in plaats
  van vervangen; en er wordt alleen naar de Store geschreven als er
  daadwerkelijk iets is hersteld.

**Getest**: nieuw `tests/test_nilm_restart_persistence_truncation.py`,
11 tests (alle elf falen op v0.63.114), inclusief vijf opeenvolgende
herstarts, behoud van geleerde CUSUM-geschiedenis, end-to-end
discovery-scan na herstart, en een structurele bronvolgorde-check op
`__init__.py` zodat de volgorde niet ongemerkt kan terugdraaien.

**Volledige testsuite**: 612 tests, allemaal groen.

**Let op**: reeds verloren data is niet te reconstrueren — de 23 huidige
kandidaten moeten één keer opnieuw beoordeeld worden. Daarna blijft het
staan.

## v0.63.116 — Duplicaten-melding telt niet meer mee voor de systeemstatus

**Gevraagd**: "de melding duplicaten zie ik niet als een melding welke
systeem status niet naar ok kan brengen."

**Aanleiding**: waarschijnlijke NILM-duplicaatparen zijn een observatie
over de HA-installatie (twee entiteiten die hetzelfde fysieke signaal
meten), niet iets dat mis is met deze integratie. Het is bovendien een
permanente toestand die bewust zo gelaten kan worden — zolang die melding
meetelde, bleef de systeemstatus voor altijd op "Aandacht gewenst" en
verloor die status zijn signaalwaarde.

**Wijziging**: `get_diagnostic_summary()` retourneert nu twee
categorieën: `aandachtspunten` (mogen de status naar "Aandacht gewenst"
brengen) en `informatief` (blijven zichtbaar, laten de status op "OK").
De duplicaten-melding verhuist naar `informatief`. Onderdrukken was
nadrukkelijk niet de bedoeling — alleen herclassificeren.

- `sensor.py`: nieuw attribuut `informatief` op de systeemstatus-sensor.
- `dashboard_template.yaml` / `dashboards/...yaml`: eigen blok "ℹ️ Ter
  info (geen invloed op de status)" op het Overzicht-tabblad.
- `_narrate_attention()`: informatieve regels krijgen "Ter info:" i.p.v.
  "Let op:", en verdwijnen niet langer uit het Live-verhaal zodra er
  verder niets aan de hand is (de functie stopte voorheen bij status
  "nominaal").

**Getest**: nieuw `tests/test_diagnostic_informational_category.py`,
9 tests (status blijft OK bij alleen duplicaten, melding blijft bestaan,
end-to-end op de statussensor, écht aandachtspunt brengt status nog wél
omlaag, actieve fout wint nog steeds, en de vier varianten van het
Live-verhaal). Bestaande `test_flags_nilm_duplicates` meebewogen naar het
nieuwe, bedoelde gedrag.

**Volledige testsuite**: 621 tests, allemaal groen.

## v0.63.117 — Einde saldering ingebouwd + laadkant financieel rechtgetrokken

**Gevraagd**: of het besparen van inkoop (ontladen) én het beperken van
terugleveropbrengst (laden) overal correct verwerkt zit — gevolgd door
"alles oppakken en integreren dat vanaf 01-01-2027 saldering niet meer
geldt".

**Twee problemen**:
1. De laadkant boekte élke geladen kWh tegen de kale inkoopprijs, ook
   PV-overschot dat anders was teruggeleverd. De terugleverpremie
   (€0,02/kWh) werd bij export wél bijgeteld maar bij het opofferen van
   export nooit afgetrokken — een structurele, eenzijdige overschatting
   van de besparing. Stond sinds v0.63.25 als bekende beperking in de
   docstring, nooit afgemaakt.
2. Het hele model rustte op de aanname "teruglevering = inkoopprijs".
   Exact juist onder saldering, volledig onjuist daarna.

**Nieuw model**: kostprijs volgt de BRON (netinkoop = inkoopprijs,
PV-overschot = gederfde teruglevering), opbrengst volgt de BESTEMMING
(eigen verbruik = vermeden inkoopprijs, export = teruglevertarief).
Twee spiegelbeeldige helpers: `_split_charge_pv_vs_grid` en
`_split_discharge_export_vs_load`. Zonder PV-/verbruikssensor wordt
alles als netinkoop geteld (conservatief).

**Saldering-overgang**: `_get_feedin_value_per_kwh` geeft onder
saldering de inkoopprijs plus premie (alles valt samen zoals voorheen,
historische cijfers blijven vergelijkbaar), daarna het kale marktarief
zonder energiebelasting plus premie minus terugleverkosten. Ontbreekt
dat attribuut na saldering, dan wordt NIET teruggevallen op de
inkoopprijs maar een aandachtspunt gemeld.

**Impact bij €0,30 inkoop / €0,09 kaal markttarief**: PV → accu → eigen
verbruik is onder saldering −€0,02/kWh waard en daarna +€0,19/kWh.

**Nieuwe config**: `salderen_end_date` (standaard 2026-12-31,
configureerbaar wegens mogelijk politiek uitstel; ongeldige datum valt
terug op "salderen actief"), `feedin_price_attribute` (standaard
`price_tax_excluded`), `feedin_cost_eur_per_kwh` (standaard 0).

**Ook aangepast**: de tegenfeitelijke KPI rekende import en export tegen
hetzelfde tarief af, wat de vergelijking na saldering scheeftrok in het
voordeel van "geen accu" (dat scenario exporteert per definitie meer) —
nu aparte tarieven per richting via `_grid_flow_cost_eur`. Regime,
terugleverwaarde, PV/net-splitsing en gederfde teruglevering zijn
zichtbaar op het Financieel-tabblad en in de diagnostiek.

**Getest**: `tests/test_salderen_end_financial_model.py`, 23 tests,
waaronder de bevestiging dat exportgedrag onder saldering exact de oude
formule oplevert.

**Volledige testsuite**: 644 tests, allemaal groen.

**Bewust niet aangepast**: de beslislogica. Die beslist nog puur op
prijsdrempels. Na saldering wordt zonoverschot opslaan op zichzelf al
waardevol, ook zonder prijsverschil tussen kwartieren — dat raakt
mechanismen die eerder expliciet ongewijzigd moesten blijven en is dus
een aparte beslissing.

## v0.63.118 — Duplicaatparen kunnen nu ook beoordeeld worden

**Gevraagd**: "NILM apparaten kan ik bevestigen danwel negeren, dit kan
nog niet met de waarschijnlijke duplicaten - kun je hiervoor een zelfde
optie maken zodat ik ook dit kan afwijzen, en dit dan ook daadwerkelijk
niet meer terug komt als mogelijk duplicaat?"

**Probleem**: de duplicaat-detectie (v0.63.91) meldde paren maar bood
geen enkele actie. Het dashboard verwees naar `reject_nilm_device`, maar
dat sluit een heel apparaat uit - niet hetzelfde als "deze twee zijn
geen duplicaat van elkaar". Een bewust geaccepteerd paar bleef dus
eeuwig terugkomen.

**Twee acties**:
- `confirm_nilm_duplicate_pair` / ✅-knop: het is echt hetzelfde signaal
  - het TWEEDE apparaat wordt permanent uitgesloten via het bestaande
  `reject_nilm_device`. De knop noemt dat apparaat in zijn eigen label.
- `dismiss_nilm_duplicate_pair` / ❌-knop: geen duplicaat - het paar
  verdwijnt permanent uit de suggesties, beide apparaten blijven
  bevestigd en getrackt.

**Persistentie**: opgeslagen als richting-onafhankelijke sleutel
(`"<a>|<b>"`, alfabetisch) in `nilm_dismissed_duplicate_pairs`, door
dezelfde Store als de bevestigde/afgewezen apparaten (dus inclusief de
laadvolgorde-borging van v0.63.115). Richting-onafhankelijk omdat een
omgedraaide volgorde het paar anders alsnog zou laten terugkomen. Een
oordeel wordt bewust niet opgeruimd als een apparaat tijdelijk uit de
bevestigde lijst verdwijnt.

**Zichtbaarheid**: nieuw blok "Duplicaatpaar beoordelen" op het
Apparaten-tabblad (één sleuf, zelfde principe als de kandidaat-knoppen),
`afgewezen_duplicaatparen` als sensorattribuut en in de
diagnostiek-export, plus beide services in `services.yaml`.

**Herbruikte lessen**: knoppen volgen exact het patroon van de
kandidaat-knoppen - `has_entity_name` uit met expliciete `entity_id`
(v0.63.47/.79), coordinator-listener omdat een ButtonEntity niet pollt
(v0.63.48), en het GETOONDE paar wordt vastgelegd bij weergave zodat een
druk niet op een verschoven sleuf landt (v0.63.107).

**Getest**: nieuw `tests/test_nilm_duplicate_pair_judgement.py`, 21
tests, waaronder niet-terugkomen na één en na vijf herstarts.

**Volledige testsuite**: 665 tests, allemaal groen.

## v0.63.119 — Waterverbruik: drie oorzaken waarom momenten het dagtotaal niet verklaarden

**Gerapporteerd (derde keer)**: "dagtotaal (85 L) is een stuk hoger dan
wat de geregistreerde gebruiksmomenten van vandaag verklaren (5 L)".

De eerdere aanname (er worden stoten gemist) bleek niet de kern: de
momenten werden grotendeels wél gedetecteerd, maar hun volume kwam op
nul uit. Drie afzonderlijke, elk aantoonbare oorzaken:

1. **Meterstand-resolutie**. Liters kwamen uitsluitend uit het verschil
   van de cumulatieve meterstand. Bij m3 met twee decimalen is de
   kleinste stap 10 L, dus elke korte stoot kwam uit op 0,0 L. Nu wordt
   het DEBIET geïntegreerd (L/min x verstreken minuten), ongevoelig voor
   de stapgrootte van de meter. Een te groot gat (herstart) wordt niet
   meegerekend. De meterstand blijft als kruiscontrole in
   `liter_uit_meterstand`.
2. **Weergavevenster als rekenbasis**. De check telde op uit
   `water_session_history`, die maar 20 momenten bewaart - meer momenten
   op een dag gaf structureel een te laag "verklaard" totaal, los van de
   detectie. Nu een losstaande dagteller (`water_sessions_today_l` /
   `_count`), met de oude optelling als terugval na een herstart.
3. **Tijdzone**. `last_changed` komt in UTC binnen terwijl de tick lokale
   tijd doorgeeft. Gevolg: een moment tussen middernacht en 02:00 lokaal
   kreeg de datum van gisteren (telde niet mee voor vandaag), en het
   waterontharder-venster (0-6 uur) schoof twee uur mee (ochtenddouche
   onterecht als regeneratie, nachtelijke spoeling juist niet). Zelfde
   soort fout als de achtertuinsensor-tijdzonebug uit v0.63.93. Nu
   `dt_util.as_local()`.

**Getest**: nieuw `tests/test_water_session_volume_accounting.py`, 10
tests waarvan er 9 aantoonbaar falen op v0.63.118. Twee bestaande tests
legden de oude meterstand-methode vast en zijn meebewogen naar de nieuwe
bedoeling (controleren nu beide waarden).

**Volledige testsuite**: 675 tests, allemaal groen.

## v0.63.120 — Klimaat-projectie meldde een verkeerde reden

**Gerapporteerd** met screenshot van het ingevulde configuratiescherm:
"Maar ze staan wel ingevuld?" Het Klimaat-tabblad meldde "Geen
living_room_temperature_sensor_entity geconfigureerd of niet
uitleesbaar", terwijl die sensor wél was gekoppeld en een actuele waarde
gaf.

**Root cause**: `_recompute_climate_trajectory` liet de reden bij een
ontbrekende buitenvoorspelling over aan wat de FETCH ooit in
`climate_forecast_note` had achtergelaten ("already set by the fetch
step above"). Maar die fetch is gethrottled op eens per 30 minuten en
draait op tussenliggende ticks helemaal niet. Gevolg: was de
temperatuursensor eenmalig kort onbereikbaar (normaal vlak na een
herstart), dan bleef die sensor-melding daarna permanent staan - ook toen
de sensor allang weer werkte en de werkelijke oorzaak de ontbrekende
buitentemperatuur-voorspelling was. Een onjuiste diagnose die de
zoekrichting verlegt.

**Tweede probleem**: "niet geconfigureerd" en "niet uitleesbaar" zaten in
één zin, terwijl dat twee totaal verschillende situaties zijn (de een
vraagt actie, de ander lost zichzelf op).

**Fix**: de reden voor een ontbrekende buitenvoorspelling wordt apart
bewaard (`_climate_forecast_fetch_note`) en elke tick opnieuw getoond;
bij een geslaagde fetch gewist. Drie losse, accurate meldingen: niet
geconfigureerd (verwijst naar Configureren), geconfigureerd maar nu niet
uitleesbaar (noemt de entity_id, meldt dat het vanzelf herstelt), en nog
geen buitenvoorspelling.

**Getest**: nieuw `tests/test_climate_projection_note_accuracy.py`, 8
tests waarvan er 6 aantoonbaar falen op v0.63.119, inclusief de exact
gerapporteerde tick-volgorde.

**Volledige testsuite**: 683 tests, allemaal groen.

## v0.63.121 — Vier verbeteringen uit een diagnostiek-review

**Gevraagd**: "Graag analyseren en waar mogelijk verbeteringen
doorvoeren", bij een verse diagnostiek-export van v0.63.120.

Uit die export bleek eerst dat de klimaat-projectie inmiddels werkt
(24-uurs traject, geleerde bias 0,3 °C), alle vijf leercheks op OK
staan, er geen ontbrekende optionele sensoren meer zijn en er geen
fouten zijn. Vier verbeterpunten:

1. **Luchtvochtigheid niet afgerond**
   (`living_room_current_humidity_percent: 45.9213256835938`) - dezelfde
   klacht die in v0.63.92 voor de temperatuur werd opgelost, maar de
   luchtvochtigheid ernaast bleef ongemoeid. Nu ook op 1 decimaal.
2. **Oude UTC-tijdstempels trokken de watertelling scheef.** De
   sessiegeschiedenis bevatte zowel "+02:00" als "+00:00" (litteken van
   de tijdzonebug uit v0.63.119; die entries blijven bewaard). De
   "verklaart maar X L"-check las de eerste tien tekens als datum, wat
   voor een UTC-tijdstempel tussen middernacht en 02:00 lokaal de datum
   van gisteren oplevert. Nu wordt de tijdstempel geparsed en naar
   lokale tijd omgerekend.
3. **De waterwaarschuwing gokte.** "Mogelijk worden stoten gemist" wees
   twee keer de verkeerde kant op. De melding noemt nu het AANTAL
   herkende momenten en trekt de bijbehorende conclusie: weinig momenten
   wijst naar de detectie, veel momenten met weinig liters naar de
   volumebepaling.
4. **Sensor-gezondheid oordeelde op één of twee metingen** ("slecht
   (0.0%, 1 metingen)", "verminderd (50.0%, 2 metingen)") en trok
   daarmee de systeemstatus omlaag, terwijl het venster na elke herstart
   onvermijdelijk door die fase loopt. Nieuwe
   `MEASUREMENT_QUALITY_MIN_SAMPLES` (10): onder die drempel geen
   oordeel. Een echte storing overleeft tien metingen moeiteloos.

**Getest**: nieuw `tests/test_diagnostics_review_improvements.py`, 11
tests waarvan er 7 aantoonbaar falen op de vorige versie. Vier bestaande
tests in `test_energy_balance_validation.py` rekenden met 1-4 metingen en
zijn opgehoogd tot boven de drempel; de water-assertie in
`test_diagnostic_summary.py` is meebewogen naar de nieuwe formulering.

**Volledige testsuite**: 694 tests, allemaal groen.

**Niet op te lossen met deze export**: het waterverschil zelf (85 L vs
5 L). Alle vier opgeslagen momenten dateren van vóór v0.63.119 (geen
`liter_uit_meterstand`) en `water_sessions_today_count` stond op 0 - de
nieuwe volumebepaling had nog geen kans gehad.

## v0.63.122 — Accu-koeling geïntegreerd

**Gevraagd**: "Integreren zodat ik dit niet meer als losse
automatisering hoef te doen, het heeft mijn inziens toch met de accu te
maken." De koelventilator stond sinds het begin bewust buiten deze
integratie; die afspraak is op verzoek herzien.

**Overgenomen**: de automatisering "Accu: Temperatuurbeheer Thuisaccu
(Buiten) - PRO v9", met EXACT dezelfde zes drempels als constanten in
`const.py`. Aanzetten bij één van vier redenen (delta >5°C; accu >35°C;
>500W én delta >2°C; >1500W én accu >30°C), uitzetten alleen als alle
drie tegelijk gelden (delta <2°C, vermogen <300W, accu <33°C). De marge
ertussen is bewuste hysterese.

**Twee bewuste afwijkingen**:
- **Geen `float(0)`-terugval.** De automatisering las sensoren met
  `states(...)|float(0)`; een weggevallen buitensensor werd dan 0°C,
  waardoor de delta gelijk werd aan de hele accutemperatuur en de
  ventilator aansloeg op een meting die er niet was (en andersom: een
  weggevallen accusensor betekende nooit meer koelen). Bij ontbrekende
  of onleesbare data wordt de schakelaar nu met rust gelaten - ook als
  de ventilatorschakelaar zelf onleesbaar is.
- **Geen 20-seconden-vertraging** op de vermogenstrigger; de evaluatie
  draait bij elke wijziging en de hysterese vangt korte pieken al af.

**Reactiesnelheid**: eigen state-listener op accutemperatuur,
buitentemperatuur en accuvermogen (zelfde patroon als de live
waterdetectie uit v0.63.98), naast de gewone tick - alleen de
5-minuten-tick zou merkbaar trager zijn dan de vervangen automatisering.

**Ingebed**: `force_manual` en `learning only` blokkeren het schakelen
(de beslissing wordt wél doorgerekend en getoond); meldingen lopen via
de bestaande `_dispatch_notification`; er wordt niet geschakeld als de
ventilator al goed staat.

**Zichtbaarheid**: nieuwe sensor "Accu-koeling" met stand + welke van de
vier redenen geldt + de laatste tien schakelmomenten, een tegel op het
Overzicht-tabblad, en `battery_cooling_state`/`battery_cooling_history`
in de diagnostiek.

**Configuratie**: drie nieuwe optionele velden (accutemperatuur-sensor,
ventilatorschakelaar, eigen buitentemperatuursensor). De laatste mag leeg
blijven - dan wordt de al gebruikte live-buitentemperatuur hergebruikt.

**Getest**: nieuw `tests/test_battery_cooling_control.py`, 21 tests.

**Volledige testsuite**: 715 tests, allemaal groen.

**Na installatie**: velden invullen en de eigen automatisering
UITZETTEN, anders sturen beide dezelfde schakelaar aan.

## v0.63.123 — Accu-modulegezondheid + tabbladnamen zichtbaar

**Gevraagd**: of er in de per-module metingen (hoogste/laagste
celspanning, celtemperatuur, SoC, stroom, vermogen) nog relevante info
zat om de accugezondheid te monitoren - plus: tabbladnamen tonen in
plaats van alleen icoontjes.

**Tabbladen**: Home Assistant toont uitsluitend het icoon zodra een view
er een heeft; de titel verdwijnt dan volledig. De tien view-iconen zijn
verwijderd, alle tabbladen tonen nu hun naam. Een test borgt dat elke
view een titel heeft en géén icoon.

**Accu-modulegezondheid**: anders dan
`battery_estimated_capacity_percent` (een lineaire schatting uit
cyclustelling) rust dit volledig op werkelijke metingen.

Kern is een DIFFERENTIELE vergelijking: elke module tegen het gemiddelde
van de ANDERE modules op hetzelfde moment. Alle modules draaien onder
identieke omstandigheden, dus alles wat ze delen valt weg en wat
overblijft is eigen aan die module. Dat lost meteen op dat het
celspanningsverschil bij LFP sterk SoC-afhankelijk is (vlak in het
midden, steil aan de uiteinden) en een absolute waarde dus niet over de
tijd met zichzelf te vergelijken is. Bewust tegen de ANDERE modules en
niet inclusief zichzelf: anders wordt de eigen afwijking met factor
(n-1)/n onderschat.

Bewaakt: dagelijkse MEDIAAN van drie afwijkingen (celspanningsverschil,
celtemperatuur, SoC) door een CUSUM-drifttest - zelfde mechanisme als de
NILM-bewaking, inclusief het zelfherstel uit v0.63.100. Daarnaast directe
absolute controles (celdelta >0,10 / >0,20 V, celtemperatuur >40 °C,
temperatuurspreiding >5 °C, SoC-spreiding >10 %); die drempels zijn
heuristiek, geen fabrieksspecificatie. Absolute celdelta wordt per
SoC-bucket van 10% bewaard, puur ter referentie.

**Configuratie**: vijf optionele LIJSTvelden; de volgorde bepaalt het
modulenummer. Schaalt naar elk aantal modules, lijsten mogen ongelijk
lang zijn, en één weggevallen sensor laat de module niet verdwijnen.

**Zichtbaarheid**: nieuw tabblad "Accumodules" met vier tabellen (live,
afwijking, spreiding, bevindingen), sensor "Accu-modulegezondheid"
(waarde = aantal modules dat aandacht verdient), en alles in de
diagnostiek-export.

**Getest**: nieuw `tests/test_battery_module_health.py`, 27 tests,
waaronder dat de screenshot-situatie zelf geen enkele melding oplevert.

**Volledige testsuite**: 742 tests, allemaal groen.

## v0.63.124 — Accu-koeling verplaatst naar de live-cijfers

**Gevraagd**: de accu-koeling als tegel binnen "Accu, rendement & live
cijfers" in plaats van een eigen sectie.

Als eigen sectie zette de masonry-layout de koeling linksboven, waar hij
een volle kolombreedte innam voor één regel informatie en de kerncijfers
naar rechts duwde. Nu een halve-breedte tegel (6 kolommen, gelijk aan de
tegels ernaast) achter "Huidige prijs": accutemperatuur als hoofdwaarde,
koelstatus eronder. Reden en schakelgeschiedenis blijven bereikbaar via
de tegel.

**Getest**: extra test in `test_battery_cooling_control.py` die borgt dat
"Accu-koeling" geen eigen sectiekop meer is en dat er precies één
koeltegel van 6 kolommen in de live-cijfers-sectie staat.

**Volledige testsuite**: 743 tests, allemaal groen.

## v0.63.125 — Grafische overzichtskaart met entiteiten in een afbeelding

**Gevraagd**: één grote kaart met alle gegevens per subcategorie
verwerkt in een afbeelding, eerst voor tabblad 1.

**Gebouwd als `picture-elements`** (kernkaart van Home Assistant, geen
HACS-afhankelijkheid): een meegeleverde SVG-achtergrond met daarop
absoluut gepositioneerde `state-label`- en `state-icon`-elementen.

**Indeling** — zes zones als energieschema: Zon (opwek, bewolking,
resterend vandaag), Huis (verbruik, zwaarste bron), Net (P1, prijs,
drempel), Thuisaccu (lading, beschikbare energie, rendement, koeling),
Besluit (modus, dure kwartieren, force manual, vakantiemodus) en
Bewaking (sensor-gezondheid, sluipverbruik, accumodules, laatste
update). Force manual en vakantiemodus zijn direct schakelbaar; de rest
klikt door naar de details.

**Achtergrond wordt automatisch klaargezet**: Home Assistant serveert
alleen `<config>/www/` (als `/local/`), dus de integratie kopieert de SVG
daarheen bij elke start - zelfde patroon als het dashboard zelf. Bestond
`www/` nog niet, dan is één extra herstart nodig voordat de map ook
daadwerkelijk geserveerd wordt.

**Bewaakte valkuil**: de posities zijn percentages van de afbeelding, dus
tekening en kaart kunnen stil uit elkaar lopen. De SVG documenteert elk
ankerpunt in commentaar en een test controleert dat bij elk anker ook
echt een element in de buurt staat.

**Getest**: nieuw `tests/test_overview_picture_card.py`, 13 tests,
waaronder dat de bestaande kaarten blijven bestaan - de grafische kaart
komt erbij, niet in plaats van.

**Volledige testsuite**: 756 tests, allemaal groen.

## v0.63.126 — Grafische kaart naar een eigen tabblad "Visueel"

**Gevraagd**: "Ik wil een extra tabblad voor hetgeen je net gemaakt
hebt."

De picture-elements-kaart stond boven aan Overzicht en duwde de
werkkaarten naar beneden. Nu een eigen tabblad "Visueel", direct na
Overzicht.

Uitgevoerd als panel-view (`panel: true`): de ene kaart vult de volle
breedte en hoogte, wat de tekening op een groot scherm pas tot zijn
recht laat komen - in een gewone view blijft hij in een kolom hangen.
Een panel-view mag exact één kaart bevatten; een test borgt dat.
`grid_options` is verwijderd (hoort bij een sections-view, doet hier
niets).

Overzicht is verder onaangeroerd. Een test controleert zowel dat de
picture-elements-kaart er niet meer staat als dat de drie kernsecties er
nog zijn.

**Volledige testsuite**: 758 tests, allemaal groen.

## v0.63.127 — Accuvermogen zichtbaar + leesbare tijdnotatie

**Gerapporteerd** bij de grafische kaart: "Vermogen naar/van accu is niet
inzichtelijk en de datum notatie is niet duidelijk."

Beide bij de BRON opgelost: een `state-label` op een
picture-elements-kaart toont de ruwe attribuutwaarde en kan niet
formatteren, dus een dashboardoplossing bestaat niet.

- **`accu_vermogen_weergave`**: geeft de RICHTING mee ("laden 597 W",
  "ontladen 800 W", "rust"). Leest `_read_corrected_battery_power`,
  dezelfde bron inclusief teken-omkering als de beslislogica, zodat kaart
  en besluit nooit iets anders beweren. Onder
  `MIN_BATTERY_POWER_IDLE_W` (25 W) heet het "rust".
- **`last_successful_update_short`** (statussensor én uitlegsensor):
  `2026-08-06T12:48:28.434441+02:00` wordt `do 6 aug 12:48`. De ruwe
  ISO-waarde blijft beschikbaar.
- **Dubbele pijlpunt** tussen huis en accu; de enkele pijl suggereerde
  permanent ontladen.

**SVG-valkuil onderweg**: markers schalen standaard mee met de
lijndikte, dus bij `stroke-width: 6` werd een pijlpunt van 10 eenheden er
één van 60 - bij de dubbele pijl raakten de punten elkaar (zandloper).
Opgelost met `markerUnits="userSpaceOnUse"`.

**Getest**: nieuw `tests/test_display_formatting.py` (12 tests, inclusief
een rondgang van 370 dagen tegen IndexErrors op maanden/weekdagen) plus
drie tests in `test_overview_picture_card.py`.

**Volledige testsuite**: 772 tests, allemaal groen.

## v0.63.128 — Ook de netpijl wijst beide kanten op

**Gerapporteerd**: "Dit geldt ook voor 'NET' (de pijl suggereert één
richting)." Terecht - in de screenshot stond de netstroom op -826 W, dus
er werd teruggeleverd terwijl de pijl naar het huis wees. Het net is net
zo goed tweerichtingsverkeer als de accu.

- Dubbele pijlpunt tussen Huis en Net (`pijlNetTerug`).
- De ZON-pijl blijft bewust enkelzijdig - de zon produceert alleen. Een
  test legt dat onderscheid vast, zodat "consistentie" later geen reden
  wordt om daar alsnog een dubbele pijl van te maken.
- Netpijlpunten iets kleiner (14 i.p.v. 18 eenheden): de opening tussen
  Huis en Net is 40 px tegen 60 px bij de accu, dus op ware grootte
  zouden de twee punten elkaar daar weer raken.
- Extra test: élke marker in de tekening moet
  `markerUnits="userSpaceOnUse"` hebben - zonder dat schalen pijlpunten
  mee met de lijndikte (de valkuil uit v0.63.127).

**Volledige testsuite**: 775 tests, allemaal groen.

## v0.63.129 — Waterdekking telt niet meer mee voor de systeemstatus

**Gevraagd**: "En dit mag geen aandachtspunt zijn, ik ben me er van
bewust" - over de melding dat het waterdagtotaal hoger is dan wat de
herkende gebruiksmomenten verklaren.

Zelfde redenering als bij de NILM-duplicaten (v0.63.116): het is een
observatie over de DEKKING van de waterdetectie, niet iets dat mis is met
de integratie. Het kan dagen aanhouden zonder dat er iets te doen valt,
waardoor de systeemstatus permanent op "Aandacht gewenst" bleef staan en
zijn signaalwaarde verloor.

Verhuisd naar `informatief`: onverkort zichtbaar inclusief de
richtinggevende duiding uit v0.63.121, maar de status blijft "OK".
Onderdrukken was niet de bedoeling - wordt de dekking ooit veel
slechter, dan wil je dat nog steeds zien.

**Getest**: twee extra tests in
`test_diagnostic_informational_category.py`; vier bestaande tests die de
oude categorie vastlegden zijn meebewogen.

**Volledige testsuite**: 777 tests, allemaal groen.

## v0.63.130 — Grootste verbruiker altijd zichtbaar op de visual

**Gerapporteerd**: "In de visual is nu de zwaarste bron nog niet
zichtbaar, mijn inziens is er altijd een zwaarste bron ook al zou die
maar 10 W zijn."

**Oorzaak**: het vak toonde `heavy_load_source`, een BESLISLOGICA-signaal
dat alleen iets teruggeeft als een specifiek zwaar apparaat aantoonbaar
draait. Het bestaat om de mediaan-voorzichtigheid van de
verbruikscorrectie over te slaan en hoort meestal leeg te zijn - het
label beloofde iets anders dan het attribuut betekende.

**Nieuw**: `get_largest_known_consumer()` / attribuut
`grootste_verbruiker` - van alle bevestigde NILM-apparaten degene met het
hoogste verbruik nu, inclusief waarde ("Televisie (120 W)"). Negatieve
waarden worden overgeslagen (productie-entiteiten zijn geen verbruikers),
0 W ook. Valt terug op het zwaar-apparaat-signaal, en anders "geen
gemeten apparaat actief" - nooit meer een leeg vak.

**Bewuste beperking**: alleen apparaten die zelf hun vermogen meten. Het
label op de tekening is daarom "GROOTSTE VERBRUIKER" geworden in plaats
van "ZWAARSTE BRON".

**Getest**: nieuw `tests/test_largest_known_consumer.py`, 12 tests.

**Volledige testsuite**: 789 tests, allemaal groen.

## v0.63.131 — Achtergrondtekening bleef in de cache hangen

**Gerapporteerd**: "Afbeelding (richtingen van de stromen) nog niet
geupdate?" - op de screenshot stonden de nieuwe waarden ("laden 390 W")
naast de oude, enkelzijdige pijlen.

**Root cause**: een picture-elements-kaart heeft twee soorten inhoud die
niet op dezelfde manier verversen. De entiteitswaarden komen live over de
websocket; de achtergrond is een statisch bestand onder een VASTE naam
via `/local/`. Browsers en de HA-app cachen dat. De integratie schreef de
nieuwe SVG wel netjes naar `www/`, maar de client vroeg hem niet opnieuw
op. Geen fout, geen melding - alleen nieuwe cijfers op een oude tekening.
Structureel probleem: zou zich bij elke volgende wijziging herhalen.

**Fix**: versiesleutel in de URL
(`...overview.svg?v=0.63.131`), plus een test die die sleutel hard
koppelt aan `manifest.json` - een versieverhoging zonder bijgewerkte
sleutel laat de testsuite falen. Geverifieerd door de versie tijdelijk op
0.63.999 te zetten.

**Eenmalig**: de al gecachte afbeelding verdwijnt niet vanzelf; één harde
vernieuwing (Ctrl+Shift+R of app-cache wissen) is nog nodig.

**Volledige testsuite**: 790 tests, allemaal groen.

## v0.63.132 — Diagnostiek-review: dagteller en een verkeerde waterconclusie

**Gevraagd**: "Algehele controle aub" bij een verse export van v0.63.130.

Uit die export: status nominaal, geen aandachtspunten, geen fouten, alle
vijf leercheks op OK, accu-modulebewaking draait en meet (celdelta's
0,03/0,01/0,00 V, temperaturen 30/29/28 °C, netjes in balans), koeling
werkt, de bron/bestemming-splitsing boekt inmiddels echt. Twee
verbeterpunten:

1. **Dagteller overleefde de herstart niet.** Zes watermomenten van
   vandaag in de geschiedenis terwijl `water_sessions_today_count` op 0
   stond: die velden zijn gewoon geheugen en worden bij elke herstart
   nul, terwijl `water_session_history` wél wordt hersteld. De check viel
   daardoor terug op de optelling over de weergavelijst van 20 - precies
   wat die teller in v0.63.119 moest vervangen. Opgelost door de teller
   bij het herstellen van de geschiedenis te herbouwen; geen extra
   opslag nodig.
2. **De waterconclusie was omgekeerd.** De melding zei "detectie werkt,
   volume te laag", terwijl dezelfde export liet zien dat geïntegreerd
   12,2 L en meterstand 12,0 L opleverden. De heuristiek uit v0.63.121
   trok haar conclusie uit een telling-drempel (meer/minder dan vijf
   momenten) die niets met de werkelijke oorzaak te maken had. Nu wordt
   het geïntegreerde debiet vergeleken met de meterstand over de
   momenten waar beide een waarde gaven: komen ze overeen (binnen
   `WATER_VOLUME_AGREEMENT_TOLERANCE`, 25%), dan worden er momenten
   gemist; wijken ze af, dan is de volumebepaling de zwakke schakel; is
   er geen vergelijkingsmateriaal, dan zegt de melding dat eerlijk.

Tegen de echte exportdata gedraaid geeft de nieuwe logica: "de 6 herkende
moment(en) kloppen qua volume - er worden gebruiksmomenten gemist."

**Getest**: vier nieuwe tests in
`test_water_session_volume_accounting.py` en drie in
`test_diagnostics_review_improvements.py`; twee bestaande tests
meebewogen.

**Volledige testsuite**: 795 tests, allemaal groen.

## v1.0.0 — Versienummering en automatische releases

**Gerapporteerd**: "Nu zie ik met de update telkens een code als
48eb9da. Ik zou daar vanaf nu graag V.1.00 of iets dergelijks zien welke
daarna automatisch ophoogt."

**Oorzaak**: `48eb9da` is een Git-commit-hash. HACS toont die als
TERUGVAL zodra een repository geen GitHub-releases heeft - het is geen
verkeerde instelling, er viel simpelweg geen versienummer te tonen. Deze
repository had wel drie workflows (HACS-validatie, hassfest, tests) maar
geen enkele die een release aanmaakte.

**Nieuw**: `.github/workflows/release.yml`. Bij elke push naar `main`:
1. leest het versienummer uit `manifest.json`;
2. stopt als die tag al bestaat (dus geen dubbele releases per push);
3. draait de volledige testsuite - een release zonder groene tests zou
   de hele borging van dit project omzeilen;
4. haalt de bijbehorende sectie uit `CHANGELOG.md` als release-notitie;
5. maakt tag `v<versie>` + GitHub-release aan.

`manifest.json` blijft dus de enige bron van waarheid; er komt geen
tweede nummering naast. Elke versieverhoging wordt vanzelf een release
die HACS als versienummer toont.

**Nummering**: van `0.63.132` naar `1.0.0`. De opbouw blijft
`major.minor.patch`, want HACS sorteert releases op versienummer en een
afwijkend formaat maakt "welke is nieuwer" onbetrouwbaar. Een test
bewaakt dat formaat.

**Getest**: twee tests in `test_overview_picture_card.py` (de
release-workflow bestaat, leest manifest.json en draait pytest; het
versienummer heeft het juiste formaat). De cache-sleutel van de
achtergrondtekening is meegegaan naar `?v=1.0.0`, bewaakt door de
bestaande test.

**Volledige testsuite**: 797 tests, allemaal groen.

**Eenmalig in GitHub**: deze workflow draait pas ná het pushen van deze
versie. Verschijnt er geen release, controleer dan onder Settings →
Actions → General of workflows schrijfrechten hebben ("Read and write
permissions").

## v1.0.1 — Digital Twin meet nu zijn eigen nauwkeurigheid

**Gerapporteerd**: "Digital Twin — structureel_beschikbaar — Simuleert
over 34.8 uur, nauwkeurigheid t.o.v. het daadwerkelijke resultaat wordt
niet bijgehouden." Eerlijk, maar onnodig: de twin voorspelt een SoC en
die is later gewoon na te meten.

**Nieuw**: elk uur wordt de voorspelde accu-inhoud zes uur vooruit
vastgelegd; op dat moment wordt de werkelijke meting ernaast gelegd.
Zelfde techniek als de zonvoorspelling-tracker.

Ontwerpkeuzes:
- niet elke tick vastleggen (honderden overlappende voorspellingen zouden
  vooral meten hoe vaak er gemeten is);
- voorspellingen die door een herstart >45 min te laat aan de beurt komen
  worden weggegooid in plaats van afgerekend;
- geen oordeel onder acht vergelijkingen;
- de fout wordt afgezet tegen de BRUIKBARE accucapaciteit, niet tegen een
  vast aantal kWh - 0,5 kWh betekent iets anders bij 10 kWh dan bij 2.

Oordeel: "klaar" <10%, "bijna_klaar" <20%, daarboven
"kwaliteit_te_laag". De adviesmodule toont dat nu in plaats van
"structureel_beschikbaar", met de simulatieduur ernaast.

**Persistentie**: nieuwe RestoreEntity-sensor "Digital Twin
nauwkeurigheid" herstelt zowel afgeronde vergelijkingen als openstaande
voorspellingen - zonder dat zou het oordeel bij frequent herstarten nooit
verschijnen (dezelfde fout als in v0.63.115).

**Bewust niet voor MPC**: dat plan is een theoretisch optimum dat met
opzet niet wordt uitgevoerd, dus er valt niets tegen af te rekenen. Een
test legt die tekst vast.

**Getest**: nieuw `tests/test_digital_twin_accuracy.py`, 17 tests.

**Volledige testsuite**: 814 tests, allemaal groen.

## v1.0.2 — Weather Ensemble meet nu of hij het bij het rechte eind heeft

**Aanleiding**: van de acht adviesmodules stonden er nog twee op
"structureel beschikbaar - nauwkeurigheid wordt niet bijgehouden".

**De vraag was verkeerd gesteld**: de ensemble doet geen voorspelling,
hij meldt de ACTUELE bewolkingsgraad. "Hoe nauwkeurig is de voorspelling"
past daar niet op. Wat er wél toe doet: klopt die melding met wat de
eigen panelen doen? Dat werd al per moment berekend voor de
onenigheids-signalering, maar nooit over tijd bijgehouden.

**Nieuw**: elke geldige waarneming (overdag, zinvolle
Solcast-verwachting) telt als "eens" of "oneens". Oneens = precies de
twee gevallen die de bestaande signalering meldt (heldere lucht bij forse
onderprestatie, zware bewolking bij overprestatie). Gebeurt op dezelfde
plek en met dezelfde drempels als die signalering - twee losse
berekeningen zouden uit de pas kunnen lopen. Een test legt dat hergebruik
vast.

Oordeel: "klaar" >=80%, "bijna_klaar" >=60%, daaronder
"kwaliteit_te_laag". Ruim genomen omdat bewolking en PV-opbrengst
samenhangen maar niet hetzelfde zijn.

**Persistentie**: `WeatherEnsembleSensor` is een RestoreEntity geworden -
er zijn twintig waarnemingen BIJ DAGLICHT nodig, dus zonder herstel zou
elke herstart de telling terugzetten.

**MPC blijft ongemoeid**: een theoretisch optimum dat met opzet niet
wordt uitgevoerd, dus er is geen werkelijkheid om tegen af te zetten.

**Getest**: nieuw `tests/test_weather_ensemble_agreement.py`, 13 tests.

**Volledige testsuite**: 827 tests, allemaal groen.

## v1.0.3 — Legenda liep achter op de code

**Gerapporteerd** met een screenshot van het Advies-tabblad. De
statustabel klopte (die leest live waarden), maar de legenda eronder is
vaste dashboardtekst en beweerde nog dat `structureel_beschikbaar` gold
voor "de drie modules zonder mechanisme dat een voorspelling ooit tegen
de werkelijkheid legt (Weather Ensemble, MPC, Digital Twin)". Sinds
v1.0.1/v1.0.2 meten die twee zichzelf wél. Zelfde soort fout als de
verouderde docstrings in v0.63.117 en de vastgeroeste klimaatmelding in
v0.63.120.

**Nu**: de categorie wordt uitgelegd als "er is wél een uitkomst, maar
niets om die tegen af te zetten", met MPC (per ontwerp) en Digital Twin
(alleen als de accucapaciteit onbekend is - dan is de afwijking wel
gemeten maar valt niet te zeggen of die veel of weinig is). Die
uitzondering is bewust genoemd: "geldt nog voor één module" zou korter
klinken maar opnieuw onjuist zijn.

**Getest**: vier tests in `test_advisory_readiness.py` - de oude
bewering mag er niet meer staan, MPC blijft er mét reden in, de
twin-uitzondering wordt genoemd, en Weather Ensemble kan daadwerkelijk
"klaar" bereiken. De legendatekst wordt eerst tot één regel
samengevouwen, omdat de YAML-bron zinnen over regels afbreekt.

**Volledige testsuite**: 831 tests, allemaal groen.

## v1.0.4 — Geen verliezen meer na een herstart

**Gevraagd**: "kijk naar de gehele integratie welke waardes eventueel
verloren gaan na een herstart, ik wil algeheel geen verliezen".

**Inventarisatie**: alle 286 coordinator-attributen doorgelopen. Het
overgrote deel wordt elke tick herberekend (projecties, live metingen,
`last_*`) - dat verliezen is onschadelijk, en terugzetten zou juist
schadelijk zijn (verouderde momentopname als actueel tonen). Maar een
deel is echt OPGEBOUWD en verdween bij elke herstart:
`battery_module_health` (maandenlange leergeschiedenis + CUSUM),
`mode_change_log` (het hele Geschiedenis-tabblad), de cumulatieve
`actual_cost_*`/`counterfactual_cost_*`, de vier splitsingstellers uit
v0.63.117, vaatwasser-/wasmachine-leergeschiedenis,
`energy_balance_error_history` en de dag-KPI's.

**Oplossing**: één gedeelde Store met een EXPLICIETE veldenlijst. Twee
eerdere lessen komen samen: entiteit-attributen hebben een
recorder-limiet van 16 KB (v0.63.66), en de laadvolgorde moet vóór
platform-setup liggen (v0.63.115). Opslag gaat vertraagd (30 s) om
schrijfacties te bundelen; bij afsluiten wordt hard weggeschreven.

**Datum-sleutels**: de zes dag-/maandsleutels gaan mee en worden bij het
laden terug omgezet naar echte `date`-objecten. Als tekst zou de
vergelijking met `now.date()` altijd ongelijk zijn en zouden de
dagtellers bij de eerstvolgende tick alsnog op nul springen.

**Borging tegen nieuwe gaten**: een test herhaalt de inventarisatie bij
elke run - elk publiek veld dat op naam opgebouwde toestand is moet in de
Store-lijst staan of een RestoreEntity hebben. Eén expliciete
uitzondering (`was_bootstrapped_from_history`), met een tweede test die
controleert dat die uitzondering nog bestaat.

**Getest**: nieuw `tests/test_state_persistence.py`, 17 tests. De
test-fake van `Store` heeft `async_delay_save` gekregen.

**Volledige testsuite**: 848 tests, allemaal groen.

## v1.0.5 — Twee onzichtbare modules, en een onjuiste claim

**Gevraagd**: "welke modules werken daadwerkelijk mee of blijven
adviserend?"

1. **Twee modules waren onzichtbaar**: `extra_dip_marge` en
   `temperatuur_regressie` (v0.63.91) stonden niet in de hardcoded
   namenlijst van het Advies-tabblad. Op drie plekken stond bovendien
   "acht" waar het er tien zijn.
2. **De claim "alle tien zijn uitsluitend adviserend" was onjuist.** De
   extra-dip-laadmarge roept `_async_apply_manual(charge_power)` aan en
   zet een eigen beslissingsreden - het is een volwaardig laadmechanisme.
   De tekst zegt nu "negen van de tien", met een alinea over de
   uitzondering en een ⚡-markering in de tabel. Ook vermeld: de
   gereedheidsstatus van die module zegt alleen iets over de opgebouwde
   marge-geschiedenis; het mechanisme werkt vanaf dag één.
3. **De negen andere zijn geverifieerd**, niet aangenomen: elk
   uitkomstveld is getraceerd. MPC, Monte Carlo, Digital Twin, Kalman en
   Weather Ensemble worden nergens buiten hun eigen berekening/weergave
   gelezen; de temperatuur-regressie gebruikt haar voorspelling alleen om
   haar eigen fout te meten; Kirchhoff en sluipverbruik komen alleen in
   de diagnostiek; NILM raakt geen accubeslissing.

**Getest**: zes tests in `test_advisory_readiness.py`, waaronder de
borging dat een elfde module zonder dashboardlabel de suite laat falen.

**Volledige testsuite**: 856 tests, allemaal groen.

## v1.0.6 — Uitschieter-filter sloeg aan op gewone meetruis

**Gerapporteerd**: "Uitschieter genegeerd: 24.3°C wijkt te snel af van
24.7°C ... Net was het andersom."

**Root cause**: het filter toetste alleen op TEMPO (afwijking gedeeld
door verstreken tijd, grens 4 °C/uur). Op korte intervallen is die deler
minuscuul: bij een tick van vijf minuten mocht de temperatuur maar
0,33 °C veranderen, over één minuut zelfs maar 0,07 °C. Elke normale
sensorruis haalde die drempel, waardoor het filter heen en weer sloeg
tussen twee volstrekt normale waarden en ondertussen een verouderde
waarde vasthield.

**Niet 60 minuten**: bij afwijzing wordt het tijdstip van de laatst
geaccepteerde meting niet bijgewerkt, dus de noemer groeit en het tempo
zakt vanzelf onder de grens - meestal binnen één of twee ticks. Het
bevestigingsvenster van 45 minuten werd zelden gehaald. Maar in die
tussentijd stond er wel een oude waarde, bij elke kleine schommeling
opnieuw.

**Fix**: een uitschieter moet nu aan TWEE voorwaarden voldoen - een
onwaarschijnlijk tempo én een afwijking van minstens
`BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C` (1,5 °C). Ruim boven de ruis van
een buitensensor, ruim onder een zonneflits. Daarnaast wordt de melding
gewist zodra er weer een normale waarde binnenkomt.

**Getest**: nieuw `tests/test_backyard_spike_filter_noise_floor.py`,
9 tests waarvan er 6 aantoonbaar falen op v1.0.5.

**Volledige testsuite**: 865 tests, allemaal groen.

## v1.0.7 — Kalman: meten of filteren hier eigenlijk iets oplevert

**Gevraagd**: doen we actief iets met de Kalman-filters, en wat zou het
betekenen als wel? Antwoord op het eerste: nee, geverifieerd - geen van
de drie gefilterde waarden wordt in een beslispad gelezen.

**Probleem met de bestaande status**: "alle 3 filters geconvergeerd" zei
alleen dat de interne onzekerheid was uitgezakt, niet dat de gefilterde
waarde BETER is dan de ruwe. Er was geen cijfer dat "heeft filteren hier
zin?" kon beantwoorden.

**Nieuw**: per signaal wordt bij elke meting het paar (verschil,
signaalgrootte) vastgelegd; het oordeel volgt uit de verhouding
(<1% verwaarloosbaar, <5% klein, daarboven noemenswaardig).

Twee ontwerpkeuzes: de verhouding wordt over de SOMMEN genomen (per
meting delen zou één moment met bijna nul opwek het gemiddelde laten
domineren), en beide getallen worden bewaard (50 W op 10 kW PV is
verwaarloosbaar, dezelfde 50 W op 200 W huisverbruik is fors). Vijftig
metingen per signaal nodig; gaat mee in de toestandspersistentie van
v1.0.4.

**Blijft volledig adviserend**: een test controleert dat de meting
nergens een commando raakt.

**Getest**: nieuw `tests/test_kalman_divergence.py`, 12 tests.

**Volledige testsuite**: 877 tests, allemaal groen.

## v1.1.0 — Beslislogica na het einde van saldering

**Gevraagd**: wijziging 1 en 2 uit de eerdere afweging, met de
uitdrukkelijke voorwaarde dat het pas vanaf 01-01-2027 geldt.

**Volledig achter `_is_salderen_active(now)`** - dezelfde poort als het
financiële model uit v0.63.117. Tot en met 31-12-2026 verandert er
letterlijk niets; alle 877 bestaande tests (die met data in 2026 draaien,
dus met saldering actief) slagen ongewijzigd.

**Wijziging 1**: is er tijdens een duur kwartier noemenswaardig
zonoverschot (>=150 W), dan gaat de accu naar `smart` om dat op te vangen
in plaats van te verkopen. Opgeslagen zon vermijdt later inkoop tegen de
volle prijs; verkopen levert alleen het lage teruglevertarief - ook in
het duurste kwartier.

**Wijziging 2**: geforceerd ontladen wordt afgetopt op het huisverbruik
plus 150 W marge. Alles daarboven gaat tegen het lage tarief het net op,
terwijl diezelfde kWh later de volle inkoopprijs had kunnen vermijden.

Een test bracht een fout in de eerste opzet aan het licht: de ondergrens
voor "zinvol ontladen" stond op het begrensde totaal, waardoor de marge
in zijn eentje die grens al haalde en er bij nul eigen verbruik alsnog
150 W puur geëxporteerd zou worden. De grens geldt nu op het EIGEN
VERBRUIK.

**Nieuwe beslissingsredenen** met eigen uitleg:
`post_salderen_solar_capture` en `expensive_quarter_no_own_load`. Die
tweede is bewust onderscheiden van `expensive_quarter_soc_protected` -
zelfde uitkomst, heel andere situatie.

**Bewust niet aangepast**: de reserveberekening (energiebrug-check en
dynamische ontlaadreserve), conform de eerdere afspraak.

**Uitproberen**: zet de salderingsdatum tijdelijk in het verleden.

**Getest**: nieuw `tests/test_post_salderen_decision_logic.py`, 17 tests.

**Volledige testsuite**: 894 tests, allemaal groen.

## v1.1.1 — Het label noemde de verkeerde temperatuurbron

**Gerapporteerd**: "We hebben mijn buitentemperatuur sensor toegevoegd
maar die zie ik niet terug?"

De sensor werd wél gebruikt: `_get_live_outdoor_temp_c` verkiest de
achtertuinsensor sinds v0.63.95 boven de weerentiteit, en de
configuratie-export bevestigde dat hij netjes was ingevuld. Alleen het
dashboardlabel stond nog hardgecodeerd als "Buitentemperatuur (live,
KNMI/OpenWeatherMap)" uit de tijd daarvóór - het beweerde dus iets anders
dan de code deed. Zelfde soort fout als de verouderde legenda in v1.0.5.

**Fix**: niet een nieuw hardgecodeerd label (dat loopt over een jaar
opnieuw achter), maar `climate_live_outdoor_source` - de entiteit die de
waarde daadwerkelijk leverde. De tegel toont die naam en wisselt mee als
de bron wisselt.

**Ook toegevoegd**: uitleg op het Klimaat-tabblad dat live-meting en
uurvoorspelling bewust uit verschillende bronnen komen. De
achtertuinsensor kan geen voorspelling leveren; het verschil tussen beide
wordt als geleerde bias-correctie over de hele voorspelling toegepast.

**Getest**: nieuw `tests/test_outdoor_temperature_source.py`, 8 tests,
waaronder dat de bron bij elke uitlezing opnieuw wordt bepaald.

**Volledige testsuite**: 902 tests, allemaal groen.

## v1.1.2 — "Korte termijn" bevroor maandenlang

**Gevraagd**: "Maar korte termijn zou toch op relatief korte termijn een
indicatie geven?"

**Rekensom**: het klimaatmodel leert per cel (buitentemperatuur x
rolluikstand x airco-status) = 252 mogelijke cellen. In de echte export
na vijf dagen: 6 cellen met enige data, 1 met de vereiste 5 metingen. De
projectie loopt 24 uur vooruit langs telkens een ander
buitentemperatuur-vakje, dus vrijwel elk uur bevroor - niet omdat er
niets geleerd was, maar omdat het geleerde net niet bij dat uur paste.

**Fix**: de indicatieve reeks valt nu terug, van dichtbij naar ver:
exacte cel -> naburige buitentemperatuur (zelfde rolluik/airco) ->
zelfde buitentemperatuur (elke stand) -> alle metingen. Stap 2 gaat
bewust vóór stap 3: de rolluikstand bepaalt hoeveel zon er binnenvalt en
weegt zwaarder dan twee graden verschil buiten.

De STRENGE reeks blijft exact zoals hij was - een test borgt dat
"betrouwbaar" nooit op een samenvatting rust. De drempel van vijf
metingen geldt ook voor de samenvatting, en zonder enige data bevriest de
reeks alsnog.

**Getoetst aan de echte celdata**: van één bruikbaar uur naar een
volledige kolom met indicaties.

**Eerlijkheid**: nieuwe kolom "Gebaseerd op" toont per uur of de
schatting op deze combinatie rust of op een grovere samenvatting.

**Getest**: nieuw `tests/test_climate_rate_fallback.py`, 10 tests.

**Volledige testsuite**: 912 tests, allemaal groen.

## v1.1.3 — Sensor-gezondheid stond op 21% door een trage sensor

**Gevraagd**: "Kun je uitzoeken waarom de sensor gezondheid zo laag is?
Of komt dit door een recente herstart?" Geen herstart - de grafiek besloeg
een hele dag.

**Aanwijzing**: de foutwaarden herhaalden zich verdacht exact (2019,1 /
2020,3 / 2020,9 / 2025,6 W, en 1111,1 / 1112,9 W). Ruis ziet er niet zo
uit.

**Root cause**: de beschikbare-energiesensor werkt veel trager bij dan de
tick van vijf minuten. Stond hij stil, dan kwam het AFGELEIDE
accuvermogen op 0 uit terwijl de accu werkelijk ~2000 W leverde - en dan
is de "fout" precies gelijk aan dat accuvermogen. Geen sensorstoring maar
een verschil in meetfrequentie, dat wel als slechte meting werd geteld.
Het spiegelbeeld volgde daarna: de opgespaarde sprong in één tick, goed
voor de 15330 W die ook in de reeks stond.

**Twee correcties**:
- Er wordt alleen nog geregistreerd als de sensor daadwerkelijk beweegt
  (`ENERGY_BALANCE_MIN_DELTA_KWH`), en dan over het werkelijke interval
  sinds die vorige beweging. Stilstand is geen slechte meting maar géén
  meting.
- Het gemeten vermogen wordt over datzelfde venster gemiddeld; het
  afgeleide tempo is immers ook een gemiddelde. Een momentopname
  ernaastleggen was op zichzelf al een bron van schijnfouten.

Onderweg bleek een dubbel startblok in de functie te staan waardoor de
eerste vermogensmeting na elke herstart wegviel - ook opgeruimd.

**Getoetst**: de gerapporteerde situatie nagebootst (sensor beweegt eens
per kwartier, accu op 2000 W): oude logica 12 metingen waarvan 8 fout,
nieuwe logica 4 metingen met fout 0.

**Getest**: nieuw `tests/test_energy_balance_stale_sensor.py`, 7 tests.
Twee bestaande tests die de oude aanname vastlegden zijn meebewogen.

**Volledige testsuite**: 919 tests, allemaal groen.

## v1.1.4 — Audit op dezelfde foutklasse, en betere diagnostiek

**Gevraagd**: "Had je dit eerder kunnen afvangen als de diagnostiek beter
was, en zitten er elders meer van dit soort zaken?"

**Diagnostiek**: ja. De export toonde de uitkomst (gezondheid 21%, een
reeks foutwaarden) maar nergens hoe vaak elke bronsensor bijwerkte -
precies het getal dat "sensoren spreken elkaar tegen" onderscheidt van
"sensoren meten op een ander tempo". Nieuw: een meetfrequentie-rapport
per bronsensor (percentage metingen waarbij de waarde verandert), in de
diagnostiek-export en als INFORMATIEVE regel op het dashboard - traag is
geen storing.

**Audit**: alle plekken die een tempo afleiden uit het verschil van een
niveaumeting zijn nagelopen. Kirchhoff (v1.1.3) en het
achtertuin-uitschieterfilter (v1.0.6) waren al opgelost; het
klimaat-tempo bleek al veilig (meet over een anker van ~1 uur, met de
reden gedocumenteerd). Eén nieuwe treffer:

**De kostprijs-/besparingsboekhouding** berekende het ontlaadtempo over
de tick in plaats van over de werkelijke beweging van de sensor. Bij vier
stille ticks gevolgd door een sprong kwam het tempo tot vijf keer te hoog
uit - en dat tempo bepaalt hoeveel van een ontlading als EXPORT wordt
geboekt. Bij 500 W huisverbruik en 500 W werkelijke ontlading: oud 0,167
kWh "export", nieuw 0,000. Er ging niets het net op, en toch werd er
terugleverpremie geboekt. Na saldering zou dat nog zwaarder wegen.

De vier plekken die vermogen x tijd = energie rekenen zijn een andere
zaak (een stilstaande meting is daar een redelijke benadering, en ze zijn
al begrensd tegen grote hiaten) en blijven ongewijzigd.

**Getest**: nieuw `tests/test_cost_basis_stale_sensor.py` (4 tests) en
`tests/test_sensor_cadence.py` (6 tests).

**Volledige testsuite**: 929 tests, allemaal groen.

## v1.1.5 — Integratie-brede review: twee stille problemen

**Gevraagd**: de hele integratie nakijken op zaken die beter kunnen.
Nagelopen: ongebruikte constanten, dode methodes, brede
except-clausules, achtergebleven TODO's, en gelijktijdigheid. Twee echte
vondsten, allebei stil (geen fout, geen melding, wel ander gedrag dan
bedoeld):

1. **De koelventilator kon dubbel schakelen.** De koeling draait binnen
   de tick (dus binnen het bestaande slot) én sinds v0.63.122 vanuit een
   eigen live listener daarbuiten. Die konden elkaar kruisen op de
   `await` van de service-aanroep: beide lezen "uit", beide schakelen
   aan - dubbele melding, dubbele regel in de geschiedenis. Nu een eigen
   slot; bewust niet het bestaande, want dat wordt de hele tick
   vastgehouden en zou de live-reactie tenietdoen. Bewezen door het slot
   tijdelijk te verwijderen: `assert 2 == 1`.
2. **De configuratie werd nergens gecontroleerd.** `errors` werd
   aangemaakt maar nooit gevuld. De salderingsdatum is vrije tekst en
   stuurt sinds v1.1.0 de beslislogica; een typefout viel stilzwijgend
   terug op "salderen actief" zonder enig signaal. Datum en
   terugleverkosten worden nu gevalideerd in beide flows, met vertaalde
   foutmeldingen, en het formulier komt terug met de ingevulde waarden.

**Wat goed bleek**: geen dode methodes (232 gecontroleerd), geen
ongebruikte constanten, geen TODO's, en alle acht brede
except-clausules hebben een expliciete onderbouwing. De hoofdupdate was
al met een slot beschermd.

**Bewust ongewijzigd**: `coordinator.py` (11.559 regels). Opsplitsen zou
vooral verplaatsen zonder te vereenvoudigen, met risico op precies de
"verplaatste methode"-regressie waar `test_structural_integrity.py` voor
is gebouwd. Eigen project met eigen plan.

**Getest**: nieuw `tests/test_review_findings.py`, 9 tests.

**Volledige testsuite**: 938 tests, allemaal groen.

## v1.1.6 — Sensor-gezondheid: het was de resolutie, niet de sensoren

**Gevraagd**: "Waarom nog steeds een slechte score?" - 20%, ondanks de
fix van v1.1.3.

**Aanwijzing**: de resterende fouten lagen rond 880-1175 W. Weer een
patroon, geen ruis.

**Root cause**: de beschikbare-energiesensor stapt in hele
SoC-procenten (~0,077 kWh bij 7,7 kWh). Over vijf minuten is één zo'n
stap ~920 W afgeleid vermogen, terwijl de drempel op 300 W ligt. Elke
enkele stap over één tick was dus automatisch een "slechte meting" - de
check mat de RESOLUTIE van de sensor gedeeld door een kort interval, niet
de sensoren zelf. v1.1.3 loste het stilstandsprobleem op maar liet een
beweging van 0,005 kWh al meetellen, ver onder één stap.

**Fix**: pas oordelen na `ENERGY_BALANCE_MIN_INTERVAL_MINUTES` (30). Die
stap komt dan uit op ~155 W. Zelfde principe als het klimaat-tempo, dat
al over een anker van ~1 uur meet met exact deze redenering. Eigen
bovengrens van 2 uur, omdat de bestaande 20-minutengrens (bedoeld voor
energie-integratie) lager is dan het nieuwe minimum.

**Oude metingen**: de methode is sinds v1.1.2 twee keer wezenlijk
veranderd en de reeks wordt sinds v1.0.4 bewaard, dus er stonden nog
metingen van de oude methode in (waaronder 15330 W) die de score omlaag
drukten. `ENERGY_BALANCE_METHOD_VERSION` wist de reeks eenmalig bij een
methodewijziging. De score staat na installatie dus even op leeg.

**Getest**: vier tests erbij in `test_energy_balance_stale_sensor.py`.
Zes bestaande tests rekenden met intervallen van 5-6 minuten - precies
het scenario dat nu bewust wordt overgeslagen - en zijn meebewogen.

**Volledige testsuite**: 942 tests, allemaal groen.

## v1.1.7 — Drift accepteren als nieuw normaal

**Gevraagd**: "1 apparaat/apparaten mogelijk defect: Koelkast schuur
Vermogen. Hoe kan dit als acceptabel worden gezien?" Antwoord: dat kon
niet, en dat was een gat.

**Probleem**: de drift-detectie herstelt zichzelf alleen als het verbruik
vijf dagen op rij TERUGKEERT naar het oude niveau. Blijft het hoger -
omdat het apparaat werkelijk meer gebruikt, of omdat een koelkast het in
de zomer zwaarder heeft - dan blijft de melding weken staan. De enige
uitwegen waren `unconfirm_nilm_device` (wist de hele leergeschiedenis) en
`reject_nilm_device` (haalt het apparaat eruit); beide buiten proportie.

**Nieuw**: `accept_nilm_device_drift`. Het apparaat blijft bevestigd en
gevolgd; de referentie wordt opnieuw verankerd op het recente niveau en
het alarm verdwijnt. De oudste dagen verdwijnen uit de geschiedenis zodat
de mediaan meteen het nieuwe normaal weerspiegelt. Bewust NIET alles
wissen: dan zou er tien dagen geen referentie zijn en kon een échte
verslechtering ongemerkt blijven. Een test legt vast dat een verdere
stijging daarna weer een alarm geeft.

**Ook aangepast**: het aandachtspunt noemt nu zelf de vraag ("klopt het
hogere verbruik?") en de actie - dat was het eigenlijke probleem, er
stond wel wat er aan de hand was maar niet wat de uitweg is.

**Getest**: nieuw `tests/test_accept_nilm_drift.py`, 9 tests.

**Volledige testsuite**: 951 tests, allemaal groen.

## v1.1.8 — Weerbronnen apart zichtbaar + wismechanisme werkte niet

**Gerapporteerd**: "Weather ensemble 25,4% terwijl het zo goed als
volledig bewolkt is."

**Het gemiddelde verborg het meningsverschil.** Twee bronnen die 0% en
51% melden geven precies hetzelfde gemiddelde als twee keer 25%, terwijl
het eerste geval betekent dat er iets mis is met een bron. De
afzonderlijke waarden waren nergens zichtbaar, ook niet in de
diagnostiek. Nu per bron vastgelegd, plus de spreiding; bij meer dan 40
procentpunt verschil een informatieve melding met beide waarden.
Informatief en geen aandachtspunt - het is geen storing van deze
integratie.

**Een fix die nooit werkte.** In dezelfde export stond
`energy_balance_method_version` op 3, terwijl het wismechanisme uit
v1.1.6 juist bedoeld was voor een opslag die dat veld nog niet kende. Het
veld begon in de code al op de huidige waarde, dus de vergelijking was
altijd onwaar - precies in het geval waarvoor het gemaakt was. Begint nu
op None ("onbekend"), zodat een oude opslag wél wordt herkend.

**Goed nieuws uit dezelfde export**: sensor-gezondheid staat op 100%
(alle twintig metingen tussen 46 en 247 W, ruim onder de drempel van
300) - de fix van v1.1.6 werkt. En het meetfrequentie-rapport bevestigt
de diagnose: `zendure_manager_available_kwh` beweegt bij 29,9% van de
metingen, `solaredge_i1_ac_power` bij 13,4%, terwijl accuvermogen en P1
de tick wél volgen (99,5% en 91,8%).

**Getest**: nieuw `tests/test_weather_ensemble_spread.py` (9 tests) plus
twee tests in `test_state_persistence.py`.

**Volledige testsuite**: 962 tests, allemaal groen.

## v1.1.9 — De meetfrequentie mat vooral hoeveel uur het nacht was

**Aangekaart**: "sensor.solaredge_i1_ac_power beweegt maar bij 13,8% van
de metingen" - met terechte twijfel of dat klopt. Het klopte niet, en het
is de meting uit v1.1.4 zelf.

**Vertekening**: de teller telde élke tick mee, ook momenten waarop de
sensor terecht stilstaat. Het PV-vermogen is 's nachts per definitie nul.
Over ~16 uur meten: 26 wijzigingen op 194 metingen = 13,4%, terwijl
diezelfde 26 wijzigingen op ~98 dagmetingen 27% is - één wijziging per
~19 minuten. De conclusie klopte (trager dan de tick, passend bij de
SolarEdge-cloud die per kwartier pollt), het getal suggereerde meer dan
twee keer zo traag. Hetzelfde gold voor de beschikbare energie bij een
stilstaande accu.

**Correctie**: alleen meten op momenten waarop de sensor kán bewegen -
de PV-sensor bij opwek, de energiesensor als de accu laadt of ontlaadt.
Netvermogen en accuvermogen onvoorwaardelijk, want die fluctueren altijd.
Een test legt vast dat een sensor die tijdens ACTIEVE momenten nauwelijks
beweegt nog steeds als traag geldt.

**Waarom dit ertoe doet**: dit cijfer verklaarde de 21%-gezondheidsstoring
en onderbouwt de keuze om afgeleide tempo's over de werkelijke beweging te
rekenen. Een systematisch te pessimistische maat stuurt een volgende
diagnose de verkeerde kant op.

**Getest**: vier tests erbij in `test_sensor_cadence.py`; bestaande tests
meebewogen naar een actieve accu.

**Volledige testsuite**: 966 tests, allemaal groen.

## v1.2.0 — Meldingen-tabblad met een schakelaar per melding

**Gevraagd**: een tabblad waar meldingen los aan/uit te zetten zijn, en
zoveel mogelijk relevante meldingen toevoegen.

**Was**: zeven meldingen aan één configuratieveld - alles aan of alles
uit.

**Nu**: twintig soorten, elk met een eigen schakelaar, plus een
hoofdschakelaar. Nieuw onder meer: accu haalt de nacht niet, accu vol
terwijl de zon schijnt, negatieve prijzen vandaag, integratie loopt vast,
accumodule loopt uit de pas, dag- en maandoverzicht.

Twee ontwerpkeuzes: alleen de zes bestaande soorten staan standaard AAN
(al het nieuwe begint uit - twintig meldingen die zichzelf aanzetten
zorgen ervoor dat er binnen een week niets meer van gelezen wordt), en
elke soort heeft een eigen dempingsvenster (5 min tot 24 uur). Onderdrukte
meldingen worden geteld en getoond.

**Borging**: de controle zit in de gedeelde verzendfunctie, niet op elke
aanroepplek. Twee tests: elke aanroep moet een soort meegeven, en elke
gebruikte soort moet in het register bestaan. Een onbekende soort wordt
bewust doorgelaten - beter een melding te veel dan een stille regressie.

**Persistentie**: standen én verzendmomenten gaan mee in de opslag van
v1.0.4; zonder dat laatste zou het dempingsvenster na elke herstart
opnieuw beginnen.

**Getest**: nieuw `tests/test_notifications.py`, 20 tests.

**Volledige testsuite**: 986 tests, allemaal groen.

## v1.3.0 — Eén betrouwbaarheidsschaal voor alle gegenereerde data

**Gevraagd**: "hoe betrouwbaar is de gegenereerde data" - voor alles wat
de integratie berekent, plus: kan de sun-integratie helpen?

**Probleem**: vijf woordenlijsten naast elkaar voor dezelfde vraag
(adviesmodules, sensor-gezondheid, klimaatprojectie, Kalman-divergentie,
meetfrequentie), en 40 van de 56 sensoren zonder enige aanduiding -
waaronder het geleerde accu-rendement, dat wél meerekent in de
extra-dip-laadbeslissing.

**Eén schaal**, zes niveaus: niet_geconfigureerd, onvoldoende_data,
indicatief, betrouwbaar, onbetrouwbaar, niet_toetsbaar. Alleen de
middelste drie vormen een ladder; de twee buitenstaanders staan er
bewust buiten omdat ze niet met wachten beter worden. Bewust een
VERTALING en geen hernoeming, zodat bestaande automatiseringen en tests
blijven werken.

**Onderscheid dat ertoe doet**: de meeste regels meten DATA-RIJPHEID.
Waar een echte nauwkeurigheidsmeting bestaat (Digital Twin,
weerensemble, sensor-gezondheid) telt díe. Staat expliciet op het
tabblad.

**Nieuw tabblad "Betrouwbaarheid"** met alles op één plek, plus een
sensor waarvan de toestand het aantal betrouwbare regels is. Het
bewolkingslabel toont nu zijn eigen betrouwbaarheid.

**Zonnestand repareert een blinde vlek uit v1.1.9**: daar bepaalde de
PV-sensor zélf of hij mocht bewegen, waardoor een vastgelopen koppeling
midden op de dag onzichtbaar bleef. Nu bepaalt de zonnestand dat -
fase-sensor, dan hoogte, dan `sun.sun` als vangnet. Twee nieuwe
configuratievelden.

**Getest**: nieuw `tests/test_reliability_scale.py` (17 tests) en
`tests/test_sun_daylight_gate.py` (10 tests).

**Volledige testsuite**: 1013 tests, allemaal groen.

## v1.3.1 — Uitschieter-filter weet nu of de zon wel schijnt

Het filter op de achtertuinsensor bestaat expliciet voor "kortstondig
direct zonlicht op de sensor", maar wist niet of de zon überhaupt scheen.
Een sprong om drie uur 's nachts kreeg dezelfde behandeling, inclusief de
melding dat het mogelijk zonlicht was - aantoonbaar onjuist, en 45
minuten wachten voor iets dat vrijwel zeker echt weer was.

**Twee aanpassingen**:
- Staat de zon onder de horizon, dan gaat het wachtvenster van 45 naar 10
  minuten en zegt de melding eerlijk waarom. Niet nul, want een
  langsrijdende auto kan ook een sprong geven.
- De blootstellingsrichting wordt GELEERD: zodra een uitschieter niet
  aanhoudt was het een echte flits, en dan wordt onthouden uit welke
  richting de zon toen kwam. Na vijf waarnemingen geldt buiten die
  richting het korte venster. Bewust geleerd en niet gevraagd - de
  meeste mensen weten niet uit welke windrichting hun sensorbehuizing
  zon vangt.

**Detail dat makkelijk misgaat**: de afstand tussen windrichtingen is
cirkelvormig (350° en 10° liggen 20 graden uit elkaar, niet 340). Zonder
die correctie zou een sensor op het noorden nooit herkend worden.

**Getest**: nieuw `tests/test_backyard_spike_sun_aware.py`, 12 tests.

**Volledige testsuite**: 1025 tests, allemaal groen.

## v1.4.0 — PV-installatieprofiel afgeleid uit de zonnestand

**Gevraagd**: een berekening van de azimut en andere informatie over hoe
de PV-installatie ligt.

**Oriëntatie**: het vermogen piekt wanneer de zon recht voor de panelen
staat, dus de zon-azimut op dat moment schat de paneelrichting; mediaan
over meerdere dagen. Alleen dagen die minstens 70% van de
Solcast-verwachting haalden tellen mee - op een dag met wisselende
bewolking ligt de piek waar het toevallig opklaarde. Uit de spreiding
van de dagelijkse piekrichtingen volgt of er meerdere dakvlakken zijn
(>40 graden = waarschijnlijk oost/west).

**Beschaduwing**: per vakje van 10 graden azimut de verhouding
werkelijk/verwacht. Onder 60% structureel = obstakel. Vakjes met minder
dan twintig metingen krijgen geen oordeel, en momenten met een
verwachting onder 200 W tellen niet mee (anders zou vroeg in de ochtend
alles als beschaduwd gelden).

**Bewust NIET**: de hellingshoek. Die vraagt maanden aan
seizoensvariatie of oncontroleerbare aannames; een getal dat er vijftien
graden naast zit is erger dan geen getal. Een test legt vast dat het
profiel geen hellingshoek bevat.

**Zichtbaar** op het Zelflerend-tabblad, als eigen sensor, en in het
betrouwbaarheidsoverzicht. Vijf heldere dagen voor een eerste schatting,
twintig voor "betrouwbaar"; het profiel gaat mee in de opslag.

**Getest**: nieuw `tests/test_pv_installation_profile.py`, 14 tests.

**Volledige testsuite**: 1039 tests, allemaal groen.

## v1.4.1 — Opgegeven PV-oriëntatie als ijkpunt

**Aanleiding**: luchtfoto en camerabeeld van de opstelling. Die
corrigeerden mijn eerste schatting: ik leidde de oriëntatie af uit de
DAKNOK (~235° WZW), maar de panelen liggen op een plat dak op een schans,
los van de nok - eerder 190-210°, zuid tot zuid-zuidwest.

**Twee nieuwe velden**: werkelijke oriëntatie en hellingshoek. De
integratie vergelijkt haar eigen afleiding daarmee en meldt afwijkingen.
Verschuift de afgeleide piekrichting later terwijl de panelen niet zijn
verplaatst, dan wijst dat op iets fysieks (uitgegroeide boom, vervuiling,
uitgevallen streng) - met een eigen melding, uit te zetten op het
Meldingen-tabblad.

**Hellingshoek wordt nog steeds niet geschat**, maar bepaalt wél de
tolerantie als je hem invult. Bij een flauwe helling is de
opbrengstcurve breder en ligt het piekmoment minder scherp vast; onder 20
graden wordt de tolerantie opgerekt van 25 naar 40 graden. Anders zou een
vlakke opstelling voortdurend "afwijkend" melden terwijl er niets aan de
hand is.

**Geen oordeel bij een zwakke schatting**: zolang de afleiding op
"onvoldoende data" staat komt er geen afwijkingsoordeel.

**Getest**: zes tests erbij in `test_pv_installation_profile.py`. De
bestaande "geen hellingshoek"-test accepteert nu
`opgegeven_hellingshoek` - dat is een ingevulde waarde, geen schatting.

**Volledige testsuite**: 1045 tests, allemaal groen.

## v1.4.2 — Configuratieformulier was niet meer te verzenden

**Gerapporteerd** met screenshot: twee velden toonden "expected float" en
het formulier liet zich niet opslaan. Dat waren de PV-oriëntatie en
hellingshoek uit v1.4.1.

**Oorzaak**: beide zijn optioneel en mogen leeg blijven, maar een leeg
optioneel veld krijgt `None` als standaard - en een `NumberSelector`
wijst dat af. Alle bestaande getalvelden in deze flow hebben een concrete
standaard en liepen daar nooit tegenaan. Erger: zolang de validatie
klaagt is het HELE formulier geblokkeerd, dus ook alle andere
instellingen op dat scherm.

**Fix**: tekstvelden met controle in `_validate_input` (bestaat sinds
v1.1.5). Leeg = geen ijkpunt; een ingevulde waarde wordt op bereik
gecontroleerd en meteen naar een getal omgezet. Een komma als
decimaalteken wordt geaccepteerd.

**Borging**: een test scant het formulier op optionele
NumberSelector-velden zonder terugvalwaarde.

**Getest**: vijf tests erbij in `test_review_findings.py`.

**Volledige testsuite**: 1050 tests, allemaal groen.

## v1.5.0 — De integratie bewaakt haar eigen zonvoorspelling

**Gevraagd**: "Neem je dit zelf mee in een diagnostiek, zodat je dit zelf
detecteert wanneer dit niet correct is" - handmatig parameters bewaken is
wat de integratie zelf hoort te doen.

**Zelfcontrole**: de geleerde bias haalt de systematische afwijking eruit
(-11,6% bij deze installatie); wat overblijft hoort dagruis te zijn. In
de laatste export -10,3% tegen -11,6%, dus de correctie werkt. Blijven de
recente dagen structureel aan één kant hangen, dan is er iets veranderd:
vervuiling, uitgevallen streng, uitgegroeide boom. Alleen de laatste vijf
dagen tellen (anders middelt een lange goede geschiedenis een
verslechtering weg), en afwijking naar boven telt ook mee.

**Weinig-zon-marge**: 15,4 kWh verwacht tegen 21,8 typisch = 71%, vlak op
de grens - dat was nergens te zien. Staat nu in de diagnostiek inclusief
of het een grensgeval is, met DEZELFDE fractie als de beslissing zelf
gebruikt (een tweede berekening zou uit de pas kunnen lopen).

**Negen meldingen bleken nooit verstuurd** te worden ondanks hun
schakelaar. Zes zijn aangesloten: zonopbrengst wijkt af, weinig-zon-dag,
uitzonderlijk duur kwartier, goedkoop blok begint bijna, lage accustand
voor de piek, sensor niet uitleesbaar. Een test dwingt de lijst af; dag-
en maandoverzicht en "module is klaar" staan er bewust nog als
uitzondering in.

**Getest**: nieuw `tests/test_solar_forecast_health.py`, 11 tests.

**Volledige testsuite**: 1061 tests, allemaal groen.

## v1.5.1 — De laatste drie meldingen aangesloten

Van de eenentwintig soorten uit v1.2.0 stonden er nog drie op de
uitzonderingenlijst. Die zijn nu aangesloten en de uitzondering is uit de
test verwijderd: alle eenentwintig worden daadwerkelijk verstuurd.

- **Dagoverzicht** (na 22:00): opwek, verbruik, netimport en wat de accu
  scheelde ten opzichte van dezelfde dag zonder accu.
- **Maandoverzicht** (op de eerste van de maand): dezelfde vergelijking
  over de hele maand.
- **Adviesmodule is klaar**: alleen de OVERGANG naar klaar wordt gemeld,
  door de huidige stand met de vorige te vergelijken. Zonder dat zou elke
  tick opnieuw melden. Bij een verse installatie is alles in één klap
  "nieuw klaar" - dan volgt geen melding maar een stille registratie van
  de uitgangssituatie. De lijst wordt bewaard, anders meldt elke herstart
  dezelfde overgang opnieuw.

**Getest**: zes tests erbij in `test_notifications.py`.

**Volledige testsuite**: 1067 tests, allemaal groen.

## v1.5.2 — Betrouwbaarheid per weerbron

**Gerapporteerd**: de twee weerbronnen liepen 70 procentpunt uiteen
(forecast_thuis 12%, openweathermap 83%), waarbij OpenWeatherMap het bij
het juiste eind leek te hebben. De melding uit v1.1.8 deed zijn werk,
maar zegt alleen DAT ze uiteenlopen, niet WELKE deugt.

**Nu**: de bestaande toets (klopt de gemelde bewolking met wat de panelen
doen) wordt ook per bron afzonderlijk gedaan, met exact dezelfde
drempels. Een test dwingt af dat het één definitie blijft.

**Bewust meten en niet wegen**, expliciet gevraagd omdat één dag niets
zegt: twintig waarnemingen bij daglicht per bron voor een oordeel, en pas
vergelijken als BEIDE die drempel halen (anders zou een bron met drie
waarnemingen "de beste" kunnen heten). Het gemiddelde blijft ongewogen -
een bron die deze week beter is kan volgende week slechter zijn.

Blijkt één bron structureel >20 procentpunt beter, dan volgt een
informatieve regel met het advies de andere uit de configuratie te halen.
Keuze van de gebruiker, niet van de integratie.

**Getest**: nieuw `tests/test_weather_source_reliability.py`, 11 tests.

**Volledige testsuite**: 1078 tests, allemaal groen.

## v1.6.0 — Werkelijke afrekening van Zonneplan op het Financieel-tabblad

**Gevraagd**: het financiële tabblad uitbreiden met Zonneplan-waarden,
met de eis dat de entiteiten AUTOMATISCH gevonden worden zonder
handmatige configuratie.

**Geen configuratieveld erbij**: de al ingevulde prijssensor verraadt het
voorvoegsel (`sensor.zonneplan_`), de rest wordt daaruit afgeleid. Twee
valkuilen: de integratie levert entity_id's in twee talen door elkaar
(`electricity_delivery_costs_today` naast
`elektriciteitsleveringskosten_deze_maand`), dus er worden per waarde
meerdere kandidaten geprobeerd; en veel van deze sensoren staan standaard
uit in HA, dus een ontbrekende sensor levert uitleg op in plaats van een
foutmelding. Getoetst tegen 58 echte entiteitnamen: alle zes doelen
gevonden. Een test borgt dat er geen configuratieveld is bijgekomen.

**Wat het oplevert**: de eigen kostenberekening naast wat Zonneplan
werkelijk afrekent - voor geld wat de Kirchhoff-check voor energie is.
Loopt het uiteen, dan klopt er iets niet in de prijsafhandeling
(prijsattribuut, netbeheerkosten, terugleveraanname). Zonneplan splitst
afname en teruglevering; die worden eerst verrekend tot het netto bedrag.

**Ruime, schaalgevoelige drempel**: 50 cent of 15%, wat het grootst is.
De kostensensor werkt maar eens per uur bij. Bij 100 euro is 50 cent
verwaarloosbaar, bij 2 euro niet - een vaste drempel zou het aan één kant
fout doen.

**Nieuwe melding** `cost_mismatch`, standaard uit, met schakelaar op het
Meldingen-tabblad.

**Getest**: nieuw `tests/test_zonneplan_cost_comparison.py`, 14 tests.

**Volledige testsuite**: 1092 tests, allemaal groen.

## v1.6.1 — Aangescherpt wat de Zonneplan-vergelijking bewijst

**Opgemerkt**: "Let wel op dat zonneplan financieel niets over de accu
kan zeggen, hun kunnen niet zien wat accu verbruik, naar woning en pv
naar woning etc is." Klopt - en het legde een zwakte bloot in de
presentatie, niet in de vergelijking zelf.

**De vergelijking is geldig om precies die reden**:
`actual_cost_today_eur` wordt berekend uit `p1_power_w`, dezelfde meter
die Zonneplan afrekent. Twee metingen van hetzelfde punt. Zou onze
berekening uit accu- of PV-vermogen komen, dan zou ze niets betekenen -
daar staat nu een test op.

**Maar de tekst suggereerde te veel**: op het Financieel-tabblad staat de
tegenfeitelijke besparing vlak boven deze vergelijking, en zonder uitleg
lijkt het alsof Zonneplan dát bevestigt. Dat kan niet - "wat had je
betaald zonder accu" bestaat in hun wereld niet, en ook de
accu-boekhouding (kostprijs per kWh, splitsing zon/net) blijft
ongetoetst. Staat nu expliciet in de code, de melding, op het tabblad en
als apart diagnostiekveld.

**Getest**: vier tests erbij in `test_zonneplan_cost_comparison.py`.

**Volledige testsuite**: 1096 tests, allemaal groen.

## v1.6.2 — Herstelmeldingen

**Gerapporteerd**: "Er is nu een melding verstuurd dat een sensor niet
uitleesbaar is, maar er komt geen melding wanneer de sensor weer
uitleesbaar is."

Zonder herstelmelding blijf je in het ongewisse: is het opgelost, of is
de melding gewoon gedempt? Bij een venster van twee uur is dat niet uit
elkaar te houden - en dat is precies waardoor mensen meldingen gaan
negeren.

**Zeven soorten** krijgen een herstelmelding: sensor weer uitleesbaar,
integratie draait weer, kosten kloppen weer, zonopbrengst op niveau,
PV-oriëntatie komt overeen, accumodules lopen gelijk, accu haalt de nacht
weer. Meldingen die een GEBEURTENIS beschrijven horen er bewust niet bij
(apparaat klaar, goedkoop blok, dagoverzicht) - daar valt niets aan te
herstellen. Een test legt dat onderscheid vast.

**Drie keuzes**: dezelfde schakelaar (wie de melding uitzet wil ook het
herstel niet), het dempingsvenster wordt omzeild (anders verdwijnt een
snel opgelost probleem stilzwijgend), en na een herstel wordt de demping
van de probleemmelding gewist zodat een terugkerend probleem meteen weer
meldt.

**Niet mis**: de screenshot toonde 21 van 22 meldingen aan, terwijl er
zes standaard aan horen te staan. Nagemeten op een verse installatie:
precies die zes. De rest stond aan door eigen keuze.

**Getest**: nieuw `tests/test_recovery_notifications.py`, 11 tests.

**Volledige testsuite**: 1107 tests, allemaal groen.

## v1.6.3 — Meldingsgeschiedenis werd onbruikbaar zonder het bericht

**Gerapporteerd**: "Nu was er een sensor niet uitleesbaar maar kan in de
gecreeerde tabel niet zien om welke het ging" - plus de vraag hoelang het
venster blijft bestaan.

De titel zegt DAT er een sensor wegviel, het bericht zegt WELKE. Alleen
de titel werd bewaard, waardoor de geschiedenis onbruikbaar was voor
precies het geval waarvoor je hem opzoekt.

**Drie aanpassingen**:
- Het bericht wordt meebewaard en getoond (dus de entity_id is zichtbaar).
- Van 50 naar 200 bewaarde meldingen; de tabel toont er 30 in plaats van
  15. Met tweeëntwintig soorten en herstelmeldingen was vijftig krap.
- Boven de tabel staat nu dat meldingen NIET na een bepaalde tijd
  verdwijnen, alleen als er 200 nieuwere bijkomen - die vraag stond
  nergens beantwoord.

Meldingen van vóór deze versie hebben geen bewaard bericht en tonen dat
eerlijk.

**Getest**: vier tests erbij in `test_recovery_notifications.py`.

**Volledige testsuite**: 1111 tests, allemaal groen.

## v1.6.4 — Dashboard wees de verkeerde kant op

**Gerapporteerd**: het Financieel-tabblad toonde "Geen
Zonneplan-kostensensoren gevonden", terwijl die sensoren er wél waren en
waarden gaven (delivery_costs_today €0,033, production_costs_today
€0,163, plus maand- en jaarvarianten).

**Echte oorzaak**: het dashboard las
`..._tegenfeitelijke_besparing`, maar die sensor heet "Besparing t.o.v.
zonder accu-sturing" en heeft dus een andere entity_id. `state_attr` op
een niet-bestaande entiteit geeft stilzwijgend None, waarop het sjabloon
zijn terugvaltekst toonde - een melding over Zonneplan terwijl het
probleem bij de eigen entiteitnaam lag. De naam was bij het bouwen
geraden in plaats van opgezocht.

**Nu bewaakt**: een test controleert dat elke
`sensor.woonkamer_energy_management_system_X` in het dashboard
correspondeert met een bestaande sensornaam, via dezelfde slugificatie
die Home Assistant gebruikt.

Die test vond meteen twee andere verwijzingen die WÉL correct blijken:
HA kent de entity_id toe bij de eerste aanmaak en laat die ongemoeid bij
een hernoeming ("Advies-gereedheid (10 modules)" heette ooit "(8
modules)", "Piekvermogen (netimport)" ooit alleen "Piekvermogen"). Die
staan op een expliciete uitzonderingenlijst mét reden.

**Getest**: nieuw `tests/test_dashboard_entity_references.py`, 3 tests.

**Volledige testsuite**: 1114 tests, allemaal groen.

## v1.6.5 — Gezondheidsscore verborg de echte oorzaak

**Gevraagd**: algehele controle van een verse export (v1.6.4).

**Goed nieuws**: de Zonneplan-vergelijking werkt - alle zes
kostensensoren automatisch gevonden, en -0,19 € eigen berekening tegen
-0,16 € bij Zonneplan. Drie cent verschil, sterke bevestiging dat de
prijsafhandeling klopt. De weerbronmeting staat op 12 van de 20
waarnemingen per bron.

**De vondst**: het aandachtspunt meldde "Sensor-gezondheid: verminderd
(65,0%, 20 metingen)" - wat leest als onnauwkeurige metingen. Maar van de
20 waren er 13 echte vergelijkingen, ALLEMAAL binnen de marge (47-141 W,
drempel 300); de daling kwam volledig door 7 momenten waarop de sensor
wegviel. Twee verschillende problemen met verschillende oplossingen,
samengeknepen tot één cijfer.

**Nu uitgesplitst** in nauwkeurigheid en beschikbaarheid, met de grootste
veroorzaker in de melding: "Niet door onnauwkeurige metingen - alle 13
vergelijkingen vielen binnen de marge - maar doordat een sensor 7 van de
20 keer geen waarde gaf." De gecombineerde score blijft bestaan; alleen
de duiding is nu correct.

**Getest**: nieuw `tests/test_sensor_health_breakdown.py`, 9 tests,
waaronder de echte reeks uit de export.

**Volledige testsuite**: 1123 tests, allemaal groen.

## v1.6.6 — Herstelmelding noemt de sensor, en wacht na een herstart

**Gerapporteerd**: "'Sensor is weer uitleesbaar' geeft niet aan welke
sensor" en "Het uitvallen komt door een herstart (start relatief traag
op), misschien deze melding iets vertragen?"

**Herstelmelding noemt nu de sensor**: de probleemmelding gaf de
entity_id wél, het herstel zei alleen "alle geconfigureerde sensoren
geven weer een waarde". Welke sensoren wegvielen wordt nu bijgehouden en
in de herstelmelding genoemd; daarna wordt die lijst gewist, anders zou
een volgende melding de sensoren van de vorige storing opsommen.

**Aanlooptijd van drie minuten** (`STARTUP_GRACE_SECONDS`) voor
beschikbaarheidsmeldingen. Sensoren zijn na een herstart even weg omdat
hun integratie nog opstart - dat is normaal. Een melding over iets dat
vanzelf goed komt, leert je die meldingen te negeren. Alleen
`sensor_unavailable` en `integration_error` wachten; een prijspiek of
apparaat-klaar heeft niets met opstarten te maken. Na de aanlooptijd komt
de melding gewoon - een echte storing mag niet verborgen blijven.

**Getest**: vijf tests erbij in `test_recovery_notifications.py`.

**Volledige testsuite**: 1128 tests, allemaal groen.

## v1.6.7 — Watertabellen groeiden ongelimiteerd

**Gevraagd**: gebruiksmomenten alleen vandaag tonen, daggeschiedenis
alleen de laatste 7 dagen.

- **Gebruiksmomenten**: alleen die van vandaag, met alleen de tijd (de
  dag is nu bekend). Erboven het aantal. Is er vandaag niets gemeten, dan
  staat dat er expliciet mét hoeveel eerdere momenten bewaard zijn - een
  lege tabel zonder uitleg zou lijken alsof de detectie stuk is.
- **Daggeschiedenis**: zeven dagen, en nu als tabel MET datum. "441 L"
  zegt weinig als je niet weet wanneer dat was.

**Drie pogingen voor het filteren**: `selectattr(..., 'search', ...)` en
de `match`-variant zijn Home Assistant-uitbreidingen die kale Jinja niet
kent, en liepen stuk in de bestaande opmaaktest (die de sjablonen echt
rendert). Uiteindelijk een gewone lus met namespace.

Onderweg bleek de testhulp `now()` niet te kennen, waardoor elk sjabloon
met die functie stilzwijgend niet werd gecontroleerd - nu gestubd. En de
opmaaktest las de kopie in `custom_components` die nog niet bijgewerkt
was; precies waarom die kopie er is.

**Getest**: nieuw `tests/test_water_tab_filtering.py`, 8 tests.

**Volledige testsuite**: 1137 tests, allemaal groen.

## v1.7.0 — Gas meegenomen in het financiële overzicht

**Gevraagd**: "Zonneplan levert ook gas aan mij, dit graag meenemen in
het financiele gedeelte." Zonder die post waren de energiekosten maar
half zichtbaar.

Met de echte cijfers uit de export: stroom netto -0,16 € (afname 0,04,
teruglevering 0,19), gas 0,13 €, totale energiekosten vandaag -0,03 €.
Een heel ander beeld dan alleen de stroomhelft.

De gasentiteit wordt automatisch gevonden, net als de rest.

**Twee dingen die eerlijk blijven**:
- Gas wordt alleen GETOOND, niet getoetst - deze integratie berekent er
  niets aan, dus er valt niets naast te leggen. Een test legt vast dat
  gas het oordeel over de stroomberekening niet beïnvloedt, ook niet bij
  een groot bedrag.
- Voor gas bestaat alleen een DAGtotaal, geen maand- of jaarvariant zoals
  bij stroom. Beperking van de Zonneplan-integratie zelf; staat op het
  tabblad in plaats van stilzwijgend te ontbreken.

Zonder gas bij dezelfde leverancier verdwijnen de regels - "None €" is
erger dan geen regel.

**Getest**: zes tests erbij in `test_zonneplan_cost_comparison.py`.

**Volledige testsuite**: 1143 tests, allemaal groen.

## v1.8.0 — Week-, maand- en jaarcijfers plus trends

**Gevraagd**: week/maand/jaar voor gas, en voor zowel gas als stroom een
dagelijkse en wekelijkse trend in procenten.

**Gas zelf opgebouwd**: Zonneplan levert alleen een dagtotaal. Die worden
nu bij elke dagwissel vastgelegd; daaruit volgen week, maand en jaar. De
teller springt om middernacht naar nul, dus de waarde wordt vlak VÓÓR de
wissel vastgelegd - na de wissel is de vorige dag niet meer op te vragen.

**Trends alleen op VOLTOOIDE dagen.** "Vandaag tot nu toe" vergelijken
met een volledige gisteren geeft de hele dag een negatieve trend die om
middernacht vanzelf verdwijnt (om 10:00 sta je op een derde van je
dagverbruik = "-65%"). Altijd negatief, altijd betekenisloos, en je zou
er conclusies aan verbinden. Dus: gisteren tegen eergisteren, en de
laatste zeven dagen tegen de zeven daarvoor. Vandaag staat er wel bij,
zonder trend.

**Geen percentage onder 20 cent** - van 2 naar 4 cent is "+100%" en dat
is ruis.

**Op het tabblad**: stroom en gas naast elkaar voor 7/30/365 dagen, plus
de twee trends met 📈 duurder en 📉 goedkoper. Zonder gas blijft die
kolom leeg in plaats van nul (nul suggereert dat er niets verbruikt is).

**Getest**: nieuw `tests/test_energy_cost_trends.py`, 14 tests.

**Volledige testsuite**: 1157 tests, allemaal groen.

## v1.8.1 — Controle: draait alles nog na alle wijzigingen?

**Gevraagd**: controleren of alles op alle tabbladen nog actief wordt
bijgestuurd, na veertien versies op één dag.

**Nagelopen**: 14 tabbladen, 132 kaarten, 104 `state_attr`-aanroepen
vergeleken met wat de sensoren teruggeven; elke sensor geïnstantieerd; een
volledige tick gedraaid. Alle twaalf nieuwe mechanismen worden
aangeroepen en de waarden bewegen.

**Twee vals alarm**: negen sensoren "faalden" omdat ze simpelweg geen
attributen hebben, en `PvForecastAccuracySensor` krijgt een tracker mee
in plaats van de coordinator (fout in het controlescript, niet in de
code).

**Eén echte vondst**: het PV-installatieprofiel vult zich niet zonder
zonvoorspelling - correct gedrag, want zonder verwachting valt niet te
bepalen of een dag helder genoeg was, maar de melding zei dat niet. Er
stond alleen "0/5 heldere dagen", en wie geen Solcast heeft zou eeuwig
wachten. Staat er nu expliciet bij.

**Getest**: één test erbij; vijf bestaande tests stubben nu de
zonvoorspelling mee.

**Volledige testsuite**: 1158 tests, allemaal groen.

## v1.8.2 — Aandachtspunt noemt nu wélke sensor wegviel

**Gerapporteerd**: "doordat een sensor 9 van de 20 keer geen waarde gaf.
Maar kan niet ingrijpen, dit omdat ik niet weet om welke sensor het
gaat." Dezelfde omissie als bij de herstelmelding in v1.6.6.

Bij een ontbrekende meting werd alleen een `None` in de foutreeks gezet;
de naam ging verloren. Nu wordt per sensor geteld hoe vaak die geen
waarde gaf, en de melding noemt ze - grootste veroorzaker vooraan.

**Twee kleinere dingen**: de telling gaat mee in de opslag (de foutreeks
blijft immers ook bewaard, dus zonder namen zou de melding na een
herstart weer generiek worden), en bij een lege geschiedenis ontbrak de
sleutel `uitval_per_sensor` waar hij verder altijd bestaat.

**Getest**: vijf tests erbij in `test_sensor_health_breakdown.py`.

**Volledige testsuite**: 1163 tests, allemaal groen.

## v1.9.0 — Diagnostiek werd een dagrapport

**Gevraagd**: is de diagnostiek voldoende gevuld om er dagelijks mee te
kunnen verbeteren, of kan het uitgebreider?

**Wat ontbrak**: de export toonde de HUIDIGE stand. Wat er om 03:00
gebeurde was onzichtbaar tenzij het toevallig in een bewaarde reeks
stond. Bij de analyses van vandaag miste ik daardoor: op welke
tijdstippen de sensoruitvallen zaten, hoe de SoC over de dag verliep, en
of een beslissing uitpakte zoals verwacht.

**Twee nieuwe lagen**:
- **Beslislogboek** per tick, 600 regels (~2 dagen): tijdstip, modus,
  reden, SoC, kWh, prijs, PV, huisverbruik, accuvermogen,
  overbruggingsbehoefte. Compacte sleutels - een leesbare export is meer
  waard dan een volledige die niemand doorkomt.
- **Dagsamenvatting**, 30 dagen: ticks, SoC min/max, welke beslissingen
  hoe vaak (grootste eerst), fouten, sensoruitval per sensor, kosten,
  opwek, verbruik, netimport.

De eerste toont wat er binnen een dag gebeurde, de tweede of iets
structureel is.

**Omvang**: logboek ~110 kB, dagrapporten ~9 kB; de export gaat van ~280
naar ~400 kB. Het beslislogboek gaat bewust NIET mee in de opslag (een
momentopname van twee dagen heeft na een herstart weinig waarde en zou de
opslag met honderden regels per herstart belasten); de dagrapporten wél.

**Onderweg**: twee verzonnen veldnamen kostten 51 falende tests, en de
borgingstest uit v1.0.4 ving direct dat `daily_report_history` niet
persistent was.

**Getest**: nieuw `tests/test_daily_diagnostics.py`, 14 tests.

**Volledige testsuite**: 1177 tests, allemaal groen.

## v1.9.1 — PV-dagopwek was structureel te laag

**Gemeld**: "Dagrapport geeft aan opwek 12.9 kWh terwijl mijn PV
installatie zegt 13.5 kWh" - 4,4%, te veel voor ruis.

**Oorzaak**: de dagopwek werd geïntegreerd (vermogen x tijd, elke tick),
wat aanneemt dat het vermogen die vijf minuten constant was. Uit het
meetfrequentie-rapport van v1.1.9 bleek al dat de SolarEdge-sensor maar
eens per 15-20 minuten bijwerkt; een verouderde waarde wordt dus over
drie ticks bevroren en pieken daartussen vallen weg. De omvormer meet
continu en telt ze wél mee. Een methodefout, en eenzijdig: hij mist
alleen naar boven.

**Oplossing**: nieuw optioneel veld `CONF_PV_ENERGY_SENSOR` voor een
cumulatieve kWh-meter (bij deze installatie
`sensor.solaredge_i1_ac_energy`, 22.633 kWh). Het dagverschil daarvan is
exact ongeacht onze leesfrequentie. Integreren blijft de terugval, en het
betrouwbaarheidsoverzicht meldt welke bron actief is - met bij
integreren de uitleg dat het onderschat en hoe je dat oplost.

**Twee valkuilen afgevangen**: een teller kan bij een herstart van de
omvormer terugvallen (opnieuw ijken, en behouden wat er al stond), en de
meterstand loopt door over middernacht (nieuw ijkpunt bij de dagreset).

**Getest**: nieuw `tests/test_pv_production_from_meter.py`, 7 tests.

**Volledige testsuite**: 1184 tests, allemaal groen.

## v1.9.2 — Vier gemelde punten

1. **Zelfconsumptie op -244,6%.** `pv_export_today_kwh` telt alles wat de
   P1-meter het net op ziet gaan; bij een thuisaccu die 's ochtends
   verkoopt komt dat deels uit de ACCU. De formule nam aan dat alle
   export zon was, en zodra die de dagopwek overstijgt wordt de uitkomst
   negatief. De export wordt nu begrensd op de dagopwek - de enige
   verdedigbare aanname zonder aparte meting per bron.
2. **"Avondpiek" om 07:15.** Het dagdeel was hardgecodeerd omdat het
   duurste blok daar meestal ligt. Volgt nu uit het werkelijke tijdstip.
3. **Waterontharder: 3,1 L om 00:28 was geen regeneratie.** Het
   tijdvenster alleen is geen bewijs - 's nachts wordt er ook
   doorgespoeld. Nieuwe ondergrens `WATER_SOFTENER_MIN_LITERS` (10 L),
   de waarde die de gebruiker uit ervaring noemde.
4. **Weerbronnen: de meting spreekt de indruk tegen.** Over 180
   waarnemingen: forecast_thuis 82,8%, openweathermap 79,4% - drie
   procentpunt in het voordeel van de bron die er volgens losse momenten
   "altijd naast zat". Die momenten waren allemaal tijdens bewolking en
   dus niet representatief. Er werd alleen gemeld BIJ een groot verschil,
   waardoor stilte dubbelzinnig was; nu wordt ook gemeld dát ze
   vergelijkbaar presteren, mét percentages.

**Getest**: nieuw `tests/test_reported_issues_1_9_2.py`, 10 tests.

**Volledige testsuite**: 1194 tests, allemaal groen.

## v1.9.3 — Meldingsruis rond drempels

**Gevraagd**: de melding rond middernacht nakijken.

**Middernachtmelding**: om 00:02 "kostenberekening wijkt 1,53 € af", om
00:04 "klopt weer". Geen rekenfout - onze dagteller springt om 00:00 naar
nul, die van Zonneplan een paar minuten later. De vergelijking slaat het
eerste half uur na middernacht nu over, met die reden erbij.

**Zelfde patroon bij de nachtreserve**: "Accu haalt de nacht niet" ging
diezelfde nacht zeven keer af, met tekorten van 0,01 tot 0,21 kWh, telkens
gevolgd door "haalt de nacht weer". Vijf van de zes binnen 1% van de
drempel - geruis, geen waarschuwing. De schatting van de
overbruggingsbehoefte is zelf onnauwkeuriger dan dat, en de accu laadt
sowieso bij. Nu pas melden bij minstens 0,5 kWh of 10% van de behoefte,
zodat de drempel meeschaalt.

**Getest**: nieuw `tests/test_notification_noise.py`, 6 tests.

**Volledige testsuite**: 1200 tests, allemaal groen.

## v1.9.4 — Volledige diagnostiek-controle

**Gevraagd**: het hele diagnostiekbestand nakijken vóór installatie.

**Twee echte vondsten**:
- **Accu-rendement stond op 8290%** terwijl `learning_health` in dezelfde
  export 82,9 meldde. In v1.3.0 stond hier een x100 op basis van een
  testwaarde van 0,85, maar de eigenschap geeft wel degelijk een
  percentage. De test die dat vastlegde gebruikte dezelfde verkeerde
  aanname en bevestigde de fout dus in plaats van hem te vangen. Er staat
  nu ook een test op dat het rendement nooit boven 100% komt.
- **Gaskosten met zeven decimalen** (0,0466657 €) in het
  kostenoverzicht; afgerond op centen, met behoud van `None` als er geen
  gas is.

**Eén vals alarm**: de accumodules leken leeg, maar dat was mijn
leescommando (`celdelta_v` in plaats van `cel_delta_v`). Alle drie
leveren gewoon.

**Wat goed staat**: vijf leercheks op OK, geen fouten, 38 NILM-apparaten,
Zonneplan-vergelijking op 2 cent, beslislogboek en dagrapport draaien.

**Kalman-vraag beantwoord** na 500 metingen: SoC 0,82% (verwaarloosbaar),
PV 9,4%, huisverbruik 25,4%. Voor de accu-inhoud - het enige signaal dat
de beslislogica raakt - valt er niets te winnen.

**Getest**: nieuw `tests/test_review_1_9_4.py`, 4 tests.

**Volledige testsuite**: 1204 tests, allemaal groen.

## v1.9.5 — De integratie controleert zichzelf op onmogelijke waarden

**Gevraagd**: of de diagnostiek zo was nagekeken dat er niets meer uit te
herleiden viel. Eerlijke antwoord: nee - ~200 velden, waarvan er
handmatig veertig echt waren bekeken.

Het rendement van 8290% viel pas op toen de HELE betrouwbaarheidslijst
werd uitgeprint; de zelfconsumptie van -244,6% kwam alleen boven water
doordat de gebruiker hem meldde. Zo'n fout hoort niet af te hangen van of
iemand toevallig goed kijkt.

**Nu**: elke tick worden alle numerieke velden getoetst aan wat fysiek
mogelijk is (rendement 0-100%, aandeel 0-100, SoC niet boven 100).
Overschrijding is een rekenfout en wordt als aandachtspunt gemeld.
Getoetst tegen beide fouten van vandaag: allebei zouden ze automatisch
gevonden zijn.

De SPECIFIEKSTE regel wint (`_ratio_percent` voor `_percent`), anders
zou een aandeel de ruime percentagegrenzen krijgen. Grenzen bewust ruim:
het doel is fouten vangen, niet commentaar op een uitzonderlijke dag -
een negatieve inkoop/teruglever-spreiding geeft geen alarm.

**Wat dit niet is**: het vangt onmogelijke waarden, geen verkeerde. Een
rendement van 45% is plausibel maar kan nog steeds fout zijn.

**Getest**: nieuw `tests/test_plausibility_scan.py`, 10 tests.

**Volledige testsuite**: 1214 tests, allemaal groen.

## v1.9.6 — Laatste controle vóór installatie

**Gevraagd**: alles nog één keer volledig beoordelen op onvolkomenheden.

**Goed**: alle .py/.yaml/.json parsen, 1214 tests groen, versie en
cachesleutel lopen gelijk, elk nieuw onderdeel wordt aangeroepen, geen
debug-restanten.

**Eén vondst**: acht configuratievelden hadden geen Nederlands label en
toonden dus de kale sleutel in het formulier (achtertuinsensor, drie
watersensoren, salderingsdatum, terugleverkosten, prijsattribuut,
CO2-intensiteit). Aangevuld in alle drie de taalbestanden.

**Zeven controles draaien nu automatisch** in plaats van als handwerk:
Nederlands label per configuratieveld, complete Engelse vertaling,
versie/cachesleutel/CHANGELOG gelijk, dashboardkopie in sync,
SVG-kopie in sync, elke dienst geregistreerd, geen print/breakpoint.

**Getest**: nieuw `tests/test_release_readiness.py`, 7 tests.

**Volledige testsuite**: 1221 tests, allemaal groen.

## v1.10.0 — GACS-tabblad: de vier eisen als spiegel

**Gevraagd**: een GACS-tabblad om van te leren voor het bedrijfsleven.

**Eerst het belangrijkste**: de GACS-verplichting geldt NIET voor
woningen. Zij geldt voor utiliteitsgebouwen zonder woonfunctie met een
verwarmings- of koelinstallatie boven 290 kW (vanaf 2030: 70 kW). Dat
staat bovenaan het tabblad en in de sensor, met een test dat het er
blijft staan.

**Wat het wel is**: een spiegel langs de vier functionele eisen uit het
Besluit Bouwwerken Leefomgeving. Drie daarvan waren al ingevuld
(monitoring, efficiëntie toetsen, interoperabiliteit); de derde -
de beheerder informeren over VERBETERMOGELIJKHEDEN - was het zwakst.

**Zeven soorten advies**, afgeleid uit de eigen metingen, met het cijfer
erbij: accu-rendement onder 85%, lage zelfconsumptie, beschaduwing per
windrichting, trage sensoren, driftende apparaten, een structureel
slechtere weerbron, en geïntegreerde in plaats van gemeten PV-opwek.
Bewust terughoudend - twintig adviezen leest niemand.

**Eerlijk over de eigen score**: zonder adviezen geldt de derde eis niet
als volledig ingevuld; dan staat er dat het óf goed staat óf dat er te
weinig is gemeten.

**Getest**: nieuw `tests/test_gacs_assessment.py`, 12 tests.

**Volledige testsuite**: 1233 tests, allemaal groen.

## v1.10.1 — Van vijftien naar tien tabbladen

**Gevraagd**: tabbladen logisch samenvoegen; vijftien was te veel.

**Samengevoegd**: Betrouwbaarheid + Advies + GACS -> **Kwaliteit**;
Financieel + EMS-KPI's -> **Financieel**; Live + Geschiedenis ->
**Verloop**; Klimaat + Water -> **Klimaat & water**. Alle 141 kaarten
behouden, plus vier kopjes zodat binnen een samengevoegd tabblad
zichtbaar blijft waar een onderwerp begint.

**Bewust niet samengevoegd**: Meldingen (27 kaarten waarvan 22
schakelaars - een instellingenpagina) en Accumodules (thuisaccu, tegenover
Apparaten voor NILM-huishoudapparaten).

**Bijna misgegaan**: de eerste aanpak las de YAML in en schreef hem
opnieuw weg, wat alle aanhalingstekens in de Jinja-sjablonen verdubbelde
(`z.get('...')` werd `z.get(''...'')`). Een bestaande test ving dat.
Hersteld uit de laatst opgeleverde zip en tekstueel opnieuw gedaan.

**Nu bewaakt**: vier tests - geen leeg tabblad, elk samengevoegd tabblad
bevat de inhoud van al zijn bronnen, Overzicht behoudt `sections`, Visueel
blijft panel. Drie bestaande tests zochten op oude tabbladnamen; op
Kwaliteit staan nu twee kaarten met de titel "Legenda", dus die worden op
inhoud onderscheiden.

**Volledige testsuite**: 1237 tests, allemaal groen.

## v1.10.2 — Overbodige koppen uit de tabbladen

**Gevraagd**: irrelevante informatie uit de tabbladen halen, behalve uit
Overzicht.

**Eerst gemeten**: van alle entiteitverwijzingen kwamen er drie op
meerdere niet-Overzicht-tabbladen voor, en die bleken geen duplicatie
(NILM staat op Kwaliteit als adviesmodule en op Apparaten als
apparaatlijst - twee invalshoeken). Geen kaarten die naar niet-bestaande
sensoren wijzen.

**Wat wel overbodig was**: tien koppen. Vier herhaalden de kaart eronder
("Betrouwbaarheid" boven "Hoe hard is dit cijfer?", "GACS" boven
"GACS-zelfbeoordeling", "Advies" boven "Advies-gereedheid", "Water" boven
"Waterverbruik"), en vijf tabbladen begonnen met een kop gelijk aan de
tabbladnaam zelf. Geen enkele kaart met inhoud verwijderd.

**De tests vonden er meer dan ik**: zelf vijf gevonden, de twee daarna
geschreven borgingstests vonden er nog vijf bij.

**Getest**: twee tests erbij in `test_dashboard_tables.py` - geen kop
herhaalt de kop eronder, geen kop is gelijk aan de tabbladnaam.

**Volledige testsuite**: 1239 tests, allemaal groen.

## v1.11.0 — Opstart telt niet meer mee, melding pas bij echte uitval

**Gemeld**: de beschikbare-energiesensor van de Zendure heeft langer
nodig om op te starten; die uitval mag niet meetellen in de
kwaliteitsanalyse, en de melding pas als de sensor ECHT weg is.

**De export bevestigde het**: score 70% ("verminderd") terwijl alle
veertien werkelijke vergelijkingen binnen de marge vielen (4-110 W). De
zes ontbrekende metingen stonden aaneengesloten aan het eind van de reeks
- de opstartperiode.

**Tijdens de opstart wordt er niets geregistreerd** (10 minuten): niet
als goede meting en niet als slechte. Geen meting is eerlijker dan een
slechte meting, en als "goed" tellen zou een echte storing vlak na een
herstart verbergen. Ruimer dan de 3 minuten voor meldingen, omdat de
score over twintig metingen terugkijkt.

**De melding komt pas na 15 minuten aanhoudende uitval**, gemeten vanaf
het EERSTE gemis. Komt de sensor tussendoor terug, dan begint de teller
opnieuw. Een enkele gemiste uitlezing komt voor bij elke cloudgebonden
integratie.

**Onderweg**: acht bestaande tests gingen uit van directe melding en
simuleren nu aanhoudende uitval. De nieuwe tests faalden eerst omdat
`_dispatch_notification` intern de echte klok gebruikt terwijl de test
een eigen tijdstip hanteerde - opgelost door de klok te bevriezen.

**Getest**: nieuw `tests/test_startup_and_real_outage.py`, 9 tests.

**Volledige testsuite**: 1248 tests, allemaal groen.

## v1.11.1 — Stilstaande geleerde waarden opsporen

**Gevraagd**: welke gegenereerde waarden werken mogelijk niet goed doordat
ze lang stilstaan, of zijn juist al zo betrouwbaar dat ze niet meer
wijzigen?

**Wat de export liet zien**: één reeks stond volledig stil,
`steelstofzuiger_idle_power_history_w` op acht keer 0,0 W. Plausibel (een
lader die niets doet verbruikt niets) maar niet te onderscheiden van een
meting die is gestopt - beide zien er identiek uit. De andere reeksen
bewegen gezond.

**Nu**: reeksen die niet meer veranderen worden opgespoord, met het
aantal metingen erbij. Onderscheid tussen reeksen waar een constante
waarde NORMAAL is (ruststroom, laadduur - geen melding) en grootheden die
horen te fluctueren (accu-rendement, nachtverbruik - informatieve regel).
De uitzonderingenlijst is expliciet en klein; een test bewaakt dat.
Booleans tellen niet mee.

**Geen bug**: de regeneratie van 00:28 in de export is een registratie
van vóór v1.9.2; de detectie gebruikt wél de nieuwe volumedrempel.

**Getest**: nieuw `tests/test_stalled_series.py`, 9 tests.

**Volledige testsuite**: 1257 tests, allemaal groen.

## v1.12.0 — Dashboards opgeruimd: conclusie in plaats van tabel

**Gemeld**: de dashboards zijn te druk; tabellen graag als één zin over
betrouwbaarheid, en liever een melding bij een probleem dan al die info.

**Van 145 naar 90 kaarten.** Elk onderwerp toont nu één zin met de
conclusie ("Alle 3 modules lopen gelijk", "2 van de 38 apparaten
verbruikt meer dan normaal: IPTV, Koelkast schuur"). Bij een probleem
staat WAT er mis is, niet alleen dat er iets is.

**Er gaat niets verloren**: de onderbouwing blijft in de
sensorattributen (tik op een kaart) en de diagnostiek-export. De
tabellen staan alleen niet meer standaard open.

**Bewust behouden**: Financieel houdt zijn tabellen - daar ZIJN de
bedragen de inhoud, en die in een zin persen zou informatie kosten in
plaats van ruis besparen (de lange Zonneplan-toelichting is wel van ~25
naar 4 regels terug). Meldingen blijft een bedieningspaneel, Overzicht de
landingspagina. Grafieken bleven staan: verloop vang je niet in een zin.

**Twintig tests geraakt**: waar de onderliggende garantie nog geldt, zijn
ze omgezet naar de DATA in plaats van de weergave (elke adviesmodule in
het betrouwbaarheidsoverzicht, duplicaatknoppen bestaan, watersessies in
de export). Tests over verdwenen sjablonen zijn verwijderd, niet
uitgeschakeld.

**Getest**: nieuw `tests/test_compact_dashboard.py`, 9 tests.

**Volledige testsuite**: 1253 tests, allemaal groen.

## v1.12.1 — Overzicht past nu op één scherm

**Gemeld**: niet hoeven scrollen op het overzichtsdashboard; het infoveld
over de kwartiertelling mag weg omdat die uitleg bekend is.

**Van 31 naar 24 kaarten, van ~2700 naar 751 tekens tekst.** Verwijderd:
de uitleg over de kwartiertelling, een lang statusblok dat herhaalde wat
de tegels ernaast al tonen, en de twee detailsecties ("Kernbeslissing",
"Advies-modules") met uitklaplijsten van onderliggende sensoren.

**Aandachtspunten in één regel**: "⚠️ 3 aandachtspunt(en) — hiervan krijg
je een melding. Tik op de statuskaart voor de details." Dat sluit aan bij
het eerdere uitgangspunt: liever een melding dan een muur informatie.

**Twee keer misgegaan onderweg**: de eerste knip liep één regel te ver
door waardoor twee secties samenvloeiden (hersteld uit de laatst
opgeleverde zip, opnieuw gedaan met inspringing als grens), en de
vervanging van de aandachtspunten-kaart voegde een tweede kaart toe in
plaats van de eerste te overschrijven - de nieuwe test ving dat.

**Getest**: drie tests erbij in `test_compact_dashboard.py`.

**Volledige testsuite**: 1256 tests, allemaal groen.

## v1.12.2 — Van tien naar zeven tabbladen

**Gemeld**: sommige tabbladen zijn na het opruimen zo leeg dat ze beter
samengevoegd kunnen worden, met een titel die aangeeft wat ze tonen.

**Nieuw tabblad "Systeem"** uit Accumodules (1 kaart), Apparaten (1),
Zelflerend (1) en Klimaat & water (2). Elk onderwerp krijgt een kop met
ondertitel die zegt wat je ziet - zonder tabbladnaam is dat anders niet
meer af te leiden.

**Stand**: Overzicht 24, Meldingen 26, Financieel 13, Systeem 9, Verloop
8, Kwaliteit 5, Visueel 1. Van vijftien tabbladen en 145 kaarten naar
zeven en 86.

**Nu bewaakt**: geen tabblad houdt minder dan drie kaarten over (Visueel
uitgezonderd - één schermvullende plattegrond), elk onderwerp op Systeem
heeft een kop, en elke kop heeft een ondertitel. Die eerste voorkomt dat
een volgende opruimronde opnieuw lege tabbladen achterlaat.

**Getest**: drie tests erbij in `test_compact_dashboard.py`.

**Volledige testsuite**: 1256 tests, allemaal groen.

## v1.12.3 — Statuskaart terug, en drift-meldingen over tienden van watts

**Gemeld**: "Welke status kaart?" - de aandachtspunten-kaart verwees naar
een statuskaart die in v1.12.1 was weggehaald, en een markdown-kaart is
niet aanklikbaar. De kaart is nu zelf de ingang (template-card met
tap_action); een test controleert dat.

**Vijf apparaten "mogelijk defect", waarvan vier onzin**: televisie 0,79 W
(-24% = 0,19 W), diepvries 0,85 W (-15% = 0,13 W), IPTV 2,49 W (+15% =
0,37 W), oplader 2,84 W (+47% = 1,33 W). Alleen de koelkast schuur (8,3
-> 67,7 W) was echt iets.

Een procentuele drempel is bij zulke vermogens betekenisloos - meetruis
van een tiende watt is al 15%. Twee ondergrenzen nu: referentie >= 5 W EN
verschil >= 5 W. Beide nodig: een apparaat van 200 W dat 2 watt meer
trekt is evenmin een defect. Getoetst tegen de echte cijfers: van vijf
meldingen naar één; een koelkast van 80 naar 110 W blijft melden.

**Onderweg**: drie CUSUM-tests draaiden op 6,2 W en vielen onder de
nieuwe drempel; opgeschaald naar 62 W. Daarbij schaalden per ongeluk ook
de CUSUM-waarden mee (geen watts) - twee tests vingen dat.

**Getest**: nieuw `tests/test_nilm_drift_thresholds.py`, 7 tests.

**Volledige testsuite**: 1266 tests, allemaal groen.

## v1.12.4 — Overal hetzelfde: conclusie op de kaart, detail door te tikken

**Gemeld**: het principe van summiere informatie met doorklikken voor
detail overal toepassen.

**Elke tegel is te openen**: 21 kaarten toonden een conclusie zonder
tap_action - dat laat je met de vraag zitten zonder manier om hem te
beantwoorden. Een test bewaakt dat nu.

**Financieel was het laatste bastion**: drie tabellen van samen ruim 4000
tekens, nu twee tegels ("-0,03 € vandaag — stroom -0,16 €, gas 0,13 €.
Eigen berekening klopt met Zonneplan."). Het maandoverzicht verviel; die
cijfers stonden al in de tweede tegel. Alle bedragen blijven in de
attributen.

**Nog twee toelichtingen weg**: de uitleg bovenaan Kwaliteit was zelf de
langste tekst op dat tabblad geworden, en de rendementsregel op Overzicht
stond pal naast de rendementstegel.

**Stand**: 85 kaarten, ~2000 tekens tekst waarvan de helft op Meldingen
(een bedieningspaneel). Was 145 kaarten.

**Vier tests moesten mee**: die bewaakten de Zonneplan-tabel. De
beperking ("dit toetst niet de accu-boekhouding") staat nu in het OORDEEL
zelf - dat is wat je ziet bij doorklikken.

**Getest**: drie tests erbij in `test_compact_dashboard.py`.

**Volledige testsuite**: 1265 tests, allemaal groen.

## v1.12.5 — Uitgezette meldingen blijven nalees baar

**Gevraagd**: een uitgezette melding moet niet meer naar de telefoon,
maar wel zichtbaar blijven in de geschiedenis.

**Was**: een geblokkeerde melding sloeg de geschiedenis over, dus
uitzetten was hetzelfde als weggooien.

**Nu**: de schakelaar bepaalt alleen of de telefoon rinkelt. Vastleggen
gebeurt altijd, met 🔕 in de tabel en de reden erbij ("deze melding staat
uit" / "hoofdschakelaar staat uit"). Zonder markering zou het lijken
alsof de schakelaar niets doet.

**Demping werkt bewust anders**: dat venster bestaat om HERHALING te
voorkomen, en die alsnog vastleggen zou de geschiedenis volschrijven met
dubbele regels. Hetzelfde voor de aanlooptijd na een herstart. Het
onderscheid: een keuze van de gebruiker wordt vastgelegd, een
timingregel niet.

**Onderweg**: twee bestaande tests eisten een lege geschiedenis bij een
uitgeschakelde melding - precies de aanname die nu omkeert.

**Getest**: nieuw `tests/test_notification_history_when_disabled.py`, 9
tests.

**Volledige testsuite**: 1277 tests, allemaal groen.

## v1.12.6 — Labels pasten niet in de tegels

**Gemeld**: de rendementskaart is leesbaar, de rest niet. Die stond op
volle breedte (12 kolommen), de rest op de halve (6) - waar ongeveer 22
tekens in passen.

**Afgekapt**: "Grootverbruiker bevestigd actief (omzeilt
mediaan-vertraging)" (61), "Boven prijsdrempel (hele dag,
capaciteit-begrensd)" (50), "Netstroom, P1 (kan negatief zijn bij
export)" (44). Je zag "Netstroom, P1 (kan n…" - dat maakt de tegel
onbruikbaar zonder erop te klikken.

**Negen labels ingekort**; de uitleg tussen haakjes staat toch in de
attributen en elke tegel is sinds v1.12.4 aanklikbaar. De
besturingssectie van 4 naar 6 kolommen, met kortere namen
("Steelstofzuiger", "Fietsladers", "Apparaatmeldingen").

**Nu bewaakt**: een test rekent per kaart uit hoeveel tekens er passen
bij zijn kolombreedte (15/22/48) en faalt op elk label dat eroverheen
gaat. Plus een test dat het inkorten de betekenis niet wegnam.

**Getest**: nieuw `tests/test_dashboard_label_length.py`, 4 tests.

**Volledige testsuite**: 1281 tests, allemaal groen.

## v1.12.7 — "Tik voor details" leverde niets op

**Gemeld**: bij een tik verschijnen geen details - met screenshot van de
standaard more-info van Home Assistant.

**Oorzaak**: HA toont in more-info geen ATTRIBUTEN, alleen toestand,
geschiedenis en logboek. Sinds v1.12.4 was elke tegel aanklikbaar en in
v1.12.0 verdwenen de tabellen met het argument dat de onderbouwing "in de
attributen blijft" - technisch waar, maar niet te zien. De belofte was
loos.

**Nu een SUBVIEW "Details"**: staat niet in de tabbalk (die is in v1.12.2
juist teruggebracht van tien naar zeven) maar is bereikbaar via navigate.
Daarop alles wat is weggehaald: volledige aandachtspunten inclusief
informatieve regels, betrouwbaarheidstabel per grootheid,
verbetermogelijkheden, accumodules, herkende apparaten met drift, en de
watersessies van vandaag. Negen samenvattingstegels wijzen erheen.

**Meetwaardetegels houden more-info**: daar is de grafiek juist het
nuttige detail. Onderscheid: samenvatting -> detailpagina, meetwaarde ->
eigen geschiedenis.

**Zes tests moesten mee**: twee namen aan dat views[0] Overzicht is, drie
pasten de compactheidsregels op de detailpagina toe, en één eiste
more-info op de statuskaart.

**Getest**: nieuw `tests/test_detail_subview.py`, 6 tests.

**Volledige testsuite**: 1287 tests, allemaal groen.

## v1.12.8 — Het doorklik-principe voor élke kaart

**Gevraagd**: het principe toepassen op alle kaarten die het moeten
hanteren.

**Negen tegels deden niets**: binnen de grid-kaarten op Financieel zaten
tegels met losse bedragen zonder tap_action. Die tonen één getal, dus
more-info is daar het juiste detail (de grafiek van dat bedrag) - niet de
detailpagina.

**Twee keer hetzelfde**: de verbetermogelijkheden stonden zowel op
Kwaliteit als op de detailpagina; nu alleen daar. Ook de uitleg bovenaan
Kwaliteit is weg (was in v1.12.4 al bedoeld te verdwijnen). Kwaliteit
houdt drie tegels.

**Drie soorten volgen het principe bewust niet**: schakelaars (tikken
schakelt), grafieken (die zijn het detail) en markdown (ondersteunt geen
tap_action in HA). Die uitzonderingen staan als expliciete lijst in een
test; een vierde soort laat hem falen.

**De regel**: samenvatting -> detailpagina, meetwaarde -> eigen
geschiedenis, schakelaar -> schakelt, grafiek -> is het detail.

**Onderweg**: de eerste poging verwijderde de verbetermogelijkheden van
de DETAILPAGINA in plaats van van Kwaliteit - de test die de
detailpagina bewaakt ving dat.

**Getest**: drie tests erbij in `test_detail_subview.py`.

**Volledige testsuite**: 1287 tests, allemaal groen.

## v1.13.0 — Alleen Overzicht in de tabbalk

**Gevraagd**: de tabbladen standaard niet zichtbaar; alleen zien na
klikken op "meer info". Een popup zou ook kunnen.

**Alles is een subview**: Visueel, Meldingen, Kwaliteit, Systeem,
Financieel en Verloop staan niet meer in de tabbalk. Je opent het
dashboard en ziet één scherm.

**Sectie "Meer bekijken"** onderaan Overzicht met zes tegels, elk met een
regel die zegt waar je terechtkomt. Zonder die tegels zouden de pagina's
alleen via de URL te vinden zijn. Een test bewaakt dat elke verborgen
pagina een ingang heeft, en een tweede dat geen tegel naar een
niet-bestaande pagina wijst.

**Over de popup**: dat kan met browser_mod, maar dat is een extra
installatie via HACS. Subviews zijn ingebouwd en werken overal, met
hetzelfde gedrag: je ziet het pas als je erom vraagt.

**Onderweg**: de testhelper filterde op `subview` om de detailpagina uit
te sluiten; nu alles subview is viel daarmee bijna alles buiten de
controle (filtert nu op naam). En de labeltest uit v1.12.6 ving vier te
lange ondertitels op de nieuwe tegels.

**Getest**: nieuw `tests/test_navigation.py`, 5 tests.

**Volledige testsuite**: 1290 tests, allemaal groen.

## v1.13.1 — Koppen raakten los van hun kaarten

**Gemeld**: de "Zelflerend"-titel stond onderaan de linkerkolom terwijl
de bijbehorende kaart bovenaan de rechterkolom hing, onder een andere
kop.

**Oorzaak**: het Systeem-tabblad gebruikte de standaard
masonry-indeling, die kaarten over kolommen verdeelt op basis van hoogte
zonder te weten dat een kop bij de kaart eronder hoort. Bij vier koppen
gaat dat gegarandeerd mis. Omgezet naar `type: sections`.

**Verloop had hetzelfde probleem** (drie koppen, acht kaarten); ook
omgezet. Onderweg bleek "Live" een kop zonder eigen kaart - samengevoegd,
want een kop zonder inhoud toont een titel waar niets onder staat.

**Nu bewaakt**: een tabblad met meer dan één kop moet `type: sections`
gebruiken, en geen sectie mag alleen uit een kop bestaan. Die eerste
vangt het probleem bij de bron in plaats van op een screenshot.

**Getest**: twee tests erbij in `test_compact_dashboard.py`; één
bestaande test las `view["cards"]` en moest leren dat secties ook kaarten
bevatten.

**Volledige testsuite**: 1295 tests, allemaal groen.

## v1.13.2 — Labels op Financieel pasten niet

**Gemeld**: op het Financieel-tabblad zijn de teksten niet goed
zichtbaar, net als eerder op de landingspagina.

**Waarom de test dit miste**: de labeltest uit v1.12.6 keek alleen naar
kaarten met een EXPLICIETE kolombreedte, en kaarten binnen een grid
hebben die niet - op Financieel zit bijna alles in grids. Bovendien ging
de test bij een ontbrekende breedte uit van de VOLLE breedte (48 tekens),
terwijl grid-kaarten juist smal zijn. De aanname stond precies verkeerd
om.

**Afgekapt**: "Besparing t.o.v. zonder accu-sturing (vandaag)" (46),
"Onverwachte netimport-dagen (laatste 7)" (39), "Piekvermogen deze maand
(netimport)" (35). Twaalf labels ingekort, plus twee sjabloonlabels die
hun tekst dynamisch opbouwen en daarom nooit werden getoetst.

**Nu bewaakt**: de helper kijkt ook in grids (44 labels in plaats van een
handvol) en gaat bij een ontbrekende breedte uit van smal. Langste label
nu 22 tekens. Twee tests erbij: één dat er daadwerkelijk in grids wordt
gekeken, en één op de sjabloonlabels.

**Volledige testsuite**: 1299 tests, allemaal groen.

## v1.14.0 — Zelfevaluatie: de integratie beoordeelt haar eigen instellingen

**Gevraagd**: een mechanisme waarmee de integratie zichzelf verbetert en
tips geeft.

**Afbakening**: zichzelf herschrijven kan niet, en automatisch bijstellen
wil je niet - de reserveberekening is eerder expliciet afgeschermd. Wat
wel kan is ACHTERAF TOETSEN of een keuze goed uitpakte, met de eigen
meetgeschiedenis als bewijs.

**Vier dingen worden nagerekend**:
- Staat de nachtreserve te ruim (30 dagen overschot, nul tekorten = die
  energie had verkocht kunnen worden) of te krap (>20% tekort-dagen)?
- Wordt de accu benut, of blijft de laagste stand boven 40%?
- Verzamelen modules na 30 dagen nog steeds zonder resultaat?
- Is er variatie in de beslissingen, of staat een drempel zo dat er
  zelden iets verandert?

**Elk voorstel noemt zijn bewijs** ("In 30 dagen was er 30x energie over
en geen enkele keer tekort") plus waar je op moet letten - een zachte
periode vertekent. Een test legt vast dat elke bevinding bewijs én
voorstel heeft, en dat er NIETS automatisch wordt gewijzigd.

De bevindingen komen in dezelfde lijst als de configuratie-adviezen; voor
de gebruiker is dat onderscheid niet interessant.

**Getest**: nieuw `tests/test_self_evaluation.py`, 12 tests.

**Volledige testsuite**: 1311 tests, allemaal groen.

## v1.14.1 — Alleen de detailpagina was nog zichtbaar

**Gemeld**: "Zie nu alleen maar een details tabblad meer?"

**Oorzaak**: Home Assistant opent altijd de EERSTE view. In v1.12.7 kwam
"Details" vóór Overzicht te staan - toen ongemerkt, want er was nog een
tabbalk. Sinds v1.13.0 is Overzicht de enige zichtbare view, en een
subview toont geen tabbalk: je opende het dashboard, kwam op Details
terecht en kon nergens heen.

Details staat nu achteraan; Overzicht opent weer als eerste.

**Nu bewaakt**: twee tests - de eerste view mag geen subview zijn, en het
is Overzicht. Een subview vooraan maakt het hele dashboard onbereikbaar,
en dat merk je pas bij het openen.

**Onderweg**: drie tests zochten de detailpagina op als "de eerste
subview"; sinds alles subview is was dat Visueel geworden. Die zoeken nu
op naam.

**Volledige testsuite**: 1313 tests, allemaal groen.

## v1.14.2 — Apparatentabel toonde overal "None"

**Gemeld**: "Moet deze data nog opbouwen?" met screenshot van 38
apparaten met "None W" in elke kolom.

**Nee**: het sjabloon vroeg sleutels op die niet bestaan (`gemiddeld_w`,
`referentie_w`, `drift_procent`); de tabel levert `naam`,
`huidig_vermogen_w` en `trend`. Die had ik bij het bouwen van de
detailpagina verzonnen in plaats van opgezocht.

Een sjabloon dat een niet-bestaande sleutel opvraagt geeft stilzwijgend
`None` - de tabel ziet er compleet uit en het lijkt alsof de meting nog
moet opstarten.

**De echte kolommen zeggen ook meer**: huidig vermogen plus een
trendbeschrijving, met het totaal aantal apparaten erbij (de tabel toont
er maar een deel).

**Nu bewaakt**: vijf tests die per detailtabel de opgevraagde sleutels
vergelijken met wat de bron levert. De andere drie tabellen bleken
correct - bij de accumodules doordat de tabel `**module` uitklapt.

**Volledige testsuite**: 1318 tests, allemaal groen.

## v1.14.3 — Stilstaande reeksen werden niet gevonden

**Gevraagd**: kijken of er meer zaken niet correct lopen, bij een verse
export.

**Goed nieuws**: de drift-drempel uit v1.12.3 werkt (van vijf apparaten
"mogelijk defect" naar één), en de aanlooptijd uit v1.11.0 haalde de
sensor-gezondheid uit de aandachtspunten.

**Twee vondsten**:
- De stilstaande-reeks-detectie vond niets terwijl
  `_steelstofzuiger_idle_power_history` op tien identieke waarden stond.
  Oorzaak: alles met een underscore werd overgeslagen, maar de echte
  velden heten zo - in de export wordt de underscore weggehaald en "_w"
  toegevoegd. En toen hij eenmaal werd gevonden gold hij als VERDACHT,
  want de uitzonderingslijst stond op `idle_power_history_w` met dat
  export-achtervoegsel. Twee keer dezelfde fout op twee plekken.
- `pv_production_source` stond niet in de export, waardoor niet na te
  gaan is of de kWh-meter uit v1.9.1 wordt gebruikt. Toegevoegd.

**Eén vals alarm**: de PV-velden leken te ontbreken maar staan in de
KPI-sectie. Zelfconsumptie 76,8% - sinds v1.9.2 weer plausibel.

**Getest**: drie tests erbij in `test_stalled_series.py`.

**Volledige testsuite**: 1321 tests, allemaal groen.

## v1.14.4 — Detailpagina paste niet op het scherm

**Gemeld**: de betrouwbaarheidstabel brak af op "Ni…" en de toelichting
viel weg.

**Oorzaak**: de detailpagina stond in masonry, die kaarten over drie
kolommen verdeelt. Een tabel met vier kolommen kreeg een derde van het
scherm. Nu `type: sections` met `max_columns: 1`, zodat elke tabel de
volle breedte heeft.

**Betrouwbaarheidstabel is een lijst geworden**: vier kolommen passen
sowieso niet op een telefoon. Nu een gegroepeerde opsomming met de groep
als kop, daaronder niveau, naam, waarde en toelichting - schaalt mee met
elke breedte.

**Apparatentabel**: stond nog op "None" omdat v1.14.1 draaide; de
correctie zit in v1.14.2.

**Onderweg misgegaan**: de eerste poging voegde `grid_options` toe achter
elke kaart, wat bij de laatste binnen de sjabloontekst belandde (YAML
kapot). Hersteld uit de laatste zip. Daarna moesten drie testhelpers
leren dat de kaarten in secties zitten - zeven tests vielen daarop om.

**Getest**: drie tests erbij in `test_detail_table_keys.py`.

**Volledige testsuite**: 1324 tests, allemaal groen.

## v1.14.5 — Meer informatie terug op het beginscherm

**Gemeld**: meer informatie op het dashboard gewenst, met doorklikken
naar de verborgen tabbladen; er viel te weinig te beoordelen.

**Wat er misging**: in v1.12.0 werden tabellen vervangen door één zin per
onderwerp - goed idee, maar die zinnen belandden op vier verschillende
verborgen tabbladen, die in v1.13.0 ook nog uit de tabbalk gingen. Je
moest dus klikken om te weten ÓF er iets aan de hand was. En de
aandachtspunten waren een telling geworden: "4 aandachtspunten" zegt niet
wat er is.

**Nu op Overzicht**: nieuwe sectie "Status per onderwerp" met zeven
tegels (accumodules, apparaten, zelflerend, financieel, klimaat, water,
meetkwaliteit), elk met de conclusie in één regel, kleurcode en een tik
naar de detailpagina. Aandachtspunten weer uitgeschreven inclusief de
informatieve regels.

Van 24 naar 40 kaarten, maar anders opgebouwd: korte regels met
doorklik, geen tabellen.

**De grens blijft**: tekstlimiet per tabblad van 800 naar 1400 tekens -
ruimer, niet weg. Zonder grens wordt het opnieuw een muur tekst.

**Getest**: drie tests aangepast of toegevoegd in
`test_compact_dashboard.py`.

**Volledige testsuite**: 1326 tests, allemaal groen.

## v1.14.6 — Uurvoorspelling woonkamertemperatuur terug

**Gemeld**: de uurvoorspelling van de woonkamertemperatuur werd gemist;
daarna: "Snelle voorspelling en lange termijn zoals origineel".

Die was met het opruimen van het Klimaat-tabblad gesneuveld. Een verloop
per uur laat zich niet in één zin vangen - juist het verloop is de
informatie.

**Beide reeksen terug**: `kort_termijn_temp_c` (valt terug op naburige
situaties zodra de exacte cel te dun bezet is - de terugval uit v1.1.2)
en `betrouwbaar_temp_c` (pas bij genoeg metingen in precies die
situatie). Plus buitentemperatuur, de kolom Basis en het aantal metingen,
met een regel uitleg eronder.

**Blinde vlek in de eigen test**: de kolomtest uit v1.14.4 keek of een
regel BEGINT met "|", maar tabelrijen beginnen met een Jinja-tag
("{% for u in t %}| ..."). Daardoor werd vrijwel geen rij gecontroleerd -
de accumodule-tabel met zes kolommen glipte er al die tijd door. Nu telt
hij de pipes ongeacht het begin; grens van drie naar zes, omdat de
detailpagina sinds v1.14.4 op één kolom staat en de kolomvergelijking bij
deze tabellen juist het nut is.

**Getest**: twee tests erbij in `test_detail_table_keys.py`.

**Volledige testsuite**: 1328 tests, allemaal groen.

## v1.14.7 — NILM-beoordeling was onbereikbaar geworden

**Gevraagd**: waar NILM-apparaten en mogelijke duplicaten te beoordelen
zijn. Antwoord: nergens - bij het opruimen van het Apparaten-tabblad in
v1.12.0 zijn de knoppen verdwenen.

**Erger dan een weggevallen tabel**: zonder die knoppen kan een kandidaat
niet worden bevestigd of afgewezen en blijft een gemeld duplicaat staan.
De detectie draait wel (de export meldt twee duplicaatparen) maar je kunt
er niets mee.

**Terug op de detailpagina**: kaart "Te beoordelen" met de huidige
kandidaat (naam en vermogen) en de gevonden duplicaatparen, plus de vier
knoppen. Een knop "bevestigen" zonder te tonen wát je bevestigt is niet
te gebruiken.

**Bijna de verkeerde entity_id's gebruikt**: de weergavenamen zijn
dynamisch (ze tonen de kandidaat), dus daar zijn ze niet uit af te
leiden. `button.py` legt ze expliciet vast om de "_2"-deduplicatie uit
v0.63.81 te voorkomen: `nilm_kandidaat_1_*` en `nilm_duplicaat_1_*`. Een
test bewaakt dat het dashboard geen zelfbedachte varianten gebruikt.

**Getest**: drie tests erbij in `test_detail_table_keys.py`.

**Volledige testsuite**: 1331 tests, allemaal groen.

## v1.14.8 — Alle 24 verdwenen sensoren terug

**Gevraagd**: alles terugzetten wat er qua dashboards is verwijderd,
zodat de informatie weer volledig is.

**Eerst gemeten**: een blanco herstel zou ook de zeven tabbladen, de
doorklik en de kortere labels terugdraaien. Dus uitgezocht wat er echt
ontbrak: van de 55 sensoren stonden er 24 nergens - beslissing en
planning (7), adviesmodules (7), apparaatstatussen (5), zon en klimaat
(3), overig (2). Veel meer dan de drie die opvielen.

**Terug op de verborgen tabbladen** waar ze thuishoren; Overzicht blijft
de samenvatting met doorklik. Van 85 naar 138 kaarten.

**Grenzen meebewogen**: maximum per tabblad van 10 naar 20 kaarten -
ruimer, niet weg.

**Twee tests deden hun werk**: de regel uit v1.13.1 (meerdere koppen ->
`sections`) sloeg aan op Financieel, dat door de nieuwe kop "Overig" twee
koppen in masonry kreeg. En de eis dat elke kop een ondertitel heeft,
dwong uit te leggen wat er in elke nieuwe sectie staat.

**Nu bewaakt**: een test controleert dat ELKE sensor ergens op het
dashboard staat, zodat een volgende opruimronde niet stilletjes
informatie laat verdwijnen.

**Volledige testsuite**: 1332 tests, allemaal groen.

## v1.14.9 — Volledige analyse vóór installatie

**Gevraagd**: een volledige analyse voor het installeren.

**In orde**: alle bestanden parsen, 1334 tests groen, en het dashboard is
sluitend - 0 van 55 sensoren zonder plek, geen dode sensorverwijzingen,
geen dode navigatiepaden, geen onbereikbare subviews, eerste view is geen
subview, NILM-knoppen bereikbaar, 7/7 schakelaars en 22/22
meldingsschakelaars op het dashboard.

**Eén echte fout**: de sensor-gezondheidsmelding zei "Niet door
onnauwkeurige metingen - alle 14 vergelijkingen vielen binnen de marge"
terwijl de nauwkeurigheid op 78,6% stond (drie metingen boven de drempel:
368, 798, 593 W). De tekst uit v1.6.5 nam aan dat bij uitval als
hoofdoorzaak álle metingen goed waren - het kan allebei tegelijk. Nu:
"Vooral doordat een sensor 6 van de 20 keer geen waarde gaf (11 van de 14
vergelijkingen vielen binnen de marge)".

**Eén terechte nieuwe waarschuwing**: accumodule 1 met celdelta 0,190 V.
De vergelijking is differentieel (module t.o.v. het gemiddelde van de
andere op hetzelfde moment), dus SoC- en temperatuurinvloeden vallen weg.
Module 1 wijkt +0,17 V af waar de andere op 0,03 en 0,01 V zitten - het
opvolgen waard.

**Getest**: twee tests erbij; één oudere test toetst nu de strekking in
plaats van de exacte formulering.

**Volledige testsuite**: 1334 tests, allemaal groen.

## v1.15.0 — Gezondheidsoordeel verdween na een herstart

**Gevraagd**: volledige analyse van een verse export (v1.14.9).

**De vondst**: `sensor_health_score` en `measurement_quality` stonden op
None terwijl de foutreeks van twintig metingen wél was hersteld. De reeks
wordt bewaard, het daaruit afgeleide oordeel niet - en dat werd alleen
berekend bij een NIEUWE meting. Na een herstart was er dus wel data maar
geen oordeel, en verdween het aandachtspunt terwijl het probleem
doorliep: de melding weg, het probleem niet.

Het oordeel wordt nu herberekend uit de reeks zodra de opgeslagen
toestand is geladen. Herberekenen in plaats van bewaren, zodat het nooit
uit de pas kan lopen met de gegevens waarop het rust.

**Verder in orde**: de correctie uit v1.14.9 werkt (geen
zelftegensprekende meldingen), vijf leercheks op OK, accu-rendement
86,9%, Zonneplan-vergelijking op 10 cent, zelfconsumptie 74,4%,
zelfvoorziening 95,2%. De stilstaande-reeks-detectie vindt nu wél de
ruststroom van de steelstofzuiger.

**Twee observaties, geen fouten**: vandaag kostte de accu 47 cent (met
-0,61 €, zonder -1,08 €) terwijl de maand 52 cent voordeel laat zien - op
een dag met 15,5 kWh opwek kan opslaan ongunstiger zijn dan terugleveren.
En de PV-energiemeter is nog niet ingesteld, dus de dagopwek wordt nog
geïntegreerd.

**Getest**: vier tests erbij in `test_sensor_health_breakdown.py`.

**Volledige testsuite**: 1338 tests, allemaal groen.

## v1.15.1 — "expected str" bij het bewerken van de configuratie

**Gemeld**: bij het openen van de configuratie toonden de PV-oriëntatie
en hellingshoek "expected str"; het formulier liet zich niet verzenden.

**Het spiegelbeeld van v1.4.2**: toen gaf een leeg NumberSelector
"expected float", dus werden het tekstvelden. Maar `_validate_input`
slaat een ingevulde waarde op als GETAL (200.0) zodat de coordinator
ermee kan rekenen, en bij heropenen geeft HA die waarde terug als
standaard van het veld. Een tekstveld weigert dan met "expected str".
Beide keren blokkeerde dat het HELE formulier.

**Oplossing**: opslaan als getal blijft juist, alleen de weergave wordt
tekst (hele getallen zonder decimaal - "200" leest prettiger dan
"200.0").

**Waarom het twee keer kon**: er was geen test die de volledige
heen-en-terugweg afliep (invullen -> opslaan -> heropenen -> opnieuw
opslaan). Elke stap apart was getest, de overgang ertussen niet. Die
test is er nu, plus een scan die vastlegt dat een TextSelector zijn
standaard nooit rechtstreeks uit de opslag haalt.

**Getest**: nieuw `tests/test_config_flow_roundtrip.py`, 7 tests.

**Volledige testsuite**: 1345 tests, allemaal groen.

## v1.15.2 — "Score None%" — ontbrekend oordeel als slecht oordeel

**Gemeld**: "⚠️ onbetrouwbaar kirchhoff — Score None% - sensoren zelf
lijken inconsistent." Twee dingen die niet samengaan.

**Oorzaak**: `(self.sensor_health_score or 0)` viel bij None terug op
nul, waardoor een ONTBREKEND oordeel dezelfde tak in ging als een SLECHT
oordeel - nul is immers lager dan elke drempel. Geen score betekent dat
er nog niet genoeg te vergelijken viel, niet dat de metingen elkaar
tegenspreken. Zo'n melding stuurt je op zoek naar een sensorprobleem dat
er niet is.

De reden noemt nu de werkelijke oorzaak: de accusensor gaf te vaak geen
waarde.

**Waarom het nu pas opviel**: in v1.15.0 wordt het oordeel herberekend na
een herstart. Daarvóór was de score ook None, maar viel de beoordeling
nog in "onvoldoende data" omdat de reeks zelf leeg was. Nu die wél wordt
hersteld, komt hij verder - en belandde in de verkeerde tak.

**Getest**: nieuw `tests/test_readiness_none_score.py`, 6 tests,
waaronder een borging dat geen enkele reden ooit "None%" bevat.

**Volledige testsuite**: 1351 tests, allemaal groen.

## v1.15.3 — Drie kaarten wezen naar hernoemde sensoren

**Gemeld**: twee kaarten onder "Overig" toonden "Entiteit niet
gevonden".

**Oorzaak**: Home Assistant kent de entity_id toe bij de EERSTE aanmaak
en laat die ongemoeid bij een hernoeming. Dat was in v1.6.4 al
vastgesteld en vastgelegd (`Piekvermogen (netimport)` ->
`..._piekvermogen`, `Advies-gereedheid (10 modules)` ->
`..._advies_gereedheid_8_modules`). Bij het terugzetten van de 24
sensoren in v1.14.8 leidde ik ze opnieuw af uit de huidige naam, zonder
die lijst te raadplegen.

De test uit v1.14.8 sloeg niet aan omdat die óók op de weergavenaam
zoekt - dezelfde verkeerde aanname aan beide kanten, dus de fout
bevestigde zichzelf.

**Drie gevallen**: piekvermogen, nachtverbruik en (gevonden door de
nieuwe test) advies-gereedheid.

**Kaarten falen nu netjes**: de twee onder "Overig" zijn template-cards
geworden - die tonen "onbekend" in plaats van alleen "Entiteit niet
gevonden", zodat je nog ziet waar de kaart over gaat.

**Getest**: twee tests erbij in `test_dashboard_entity_references.py`,
plus de uitzondering toegevoegd aan de test uit v1.14.8.

**Volledige testsuite**: 1353 tests, allemaal groen.

## v1.15.4 — "balance_power_samples staat op -0.0" was vals alarm

**Gemeld**: "0,0???" bij de melding dat `balance_power_samples` al 27
metingen op -0.0 staat.

**Geen echte waarschuwing**: `_balance_power_samples` is een WERKBUFFER
die accuvermogens verzamelt tussen twee balanscontroles en zichzelf
daarna leegt. 27x -0,0 W betekent dat de accu stilstond - 's nachts bij
een volle accu normaal. De -0.0 komt van een vermogensmeter die met een
teken de richting aangeeft.

**Ontstaan door v1.14.3**: daar werden underscore-velden meegenomen om
`_steelstofzuiger_idle_power_history` te vinden, en daarmee kwamen ook de
werkbuffers binnen.

**Onderscheid zit in de naam**: een reeks die LEERT heet `_history` of
`_records`, een buffer heet `_samples` of `_buffer`. Een test bewaakt dat
de uitzonderingsfragmenten geen "history" of "records" bevatten, zodat
ze niet per ongeluk echte reeksen uitsluiten.

**Getest**: drie tests erbij in `test_stalled_series.py`.

**Volledige testsuite**: 1356 tests, allemaal groen.

## v1.15.5 — "unknown kW" bij het nachtverbruik

**Gemeld**: piekvermogen toonde 2128 W, nachtverbruik "unknown kW".

**Twee fouten in één kaart**:
- De sensor rapporteert WATT (hij rekent de intern geleerde kW al om). Ik
  nam de eenheid over uit `learned_night_consumption_kw` en zette er "kW"
  achter - het getal zou duizend keer verkeerd lezen zodra het
  verschijnt.
- Een kale "unknown" leest als een storing, terwijl het bij een geleerde
  waarde meestal "nog niet genoeg verzameld" betekent. Nu "nog niet
  geleerd" respectievelijk "nog niet gemeten".

**Alleen bij geleerde waarden**: bij live meetwaarden (accustand,
netstroom) is een lege toestand juist wél een signaal. Die houden hun
kale weergave.

Mijn eerste poging paste de terugval op alle zestien kaarten toe; dat
brak de YAML én zou echte storingen hebben verdoezeld. Hersteld uit de
laatste zip en beperkt tot de twee geleerde waarden.

**Getest**: twee tests erbij in `test_dashboard_entity_references.py`.

**Volledige testsuite**: 1358 tests, allemaal groen.

## v1.15.6 — Acht sensoren bestaan zonder apparaatvoorvoegsel

**Gemeld**: zeven kaarten onder "Beslissing en planning" toonden
"Entiteit niet gevonden".

**Oorzaak**: deze sensoren bestaan al langer dan de apparaatnaam
"Woonkamer". HA legt de entity_id vast bij de EERSTE aanmaak, dus ze
heten `sensor.energy_management_system_*` zonder voorvoegsel. Ik had ze
afgeleid uit de weergavenaam mét voorvoegsel - het patroon van alle
nieuwere sensoren.

**Gevonden via het dashboard van v0.63.114**, waar ze nog staan: elf
sensoren zonder voorvoegsel, waarvan zeven op de nieuwe kaarten. Plus een
achtste: `learned_night_consumption` - dat was de "unknown" uit v1.15.5,
dus geen ontbrekende geleerde waarde maar hetzelfde voorvoegselprobleem.

**Waarom de test dit miste**: die uit v1.14.8 zoekt op de NAAM, niet op
de volledige entity_id. Derde keer vandaag dat een test dezelfde aanname
maakte als de code die hij moest controleren.

**Nu bewaakt**: expliciete lijst van de elf sensoren zonder voorvoegsel,
met een test die faalt zodra er eentje mét voorvoegsel wordt aangeroepen.

**Getest**: twee tests erbij in `test_dashboard_entity_references.py`.

**Volledige testsuite**: 1360 tests, allemaal groen.

## v1.15.7 — "-34,6%" was 7 procentpunt

**Gemeld**: tegel toont 86,9% geleerd rendement, de regel eronder
"vorige meting was 94,0% (-34,6%)".

**Twee dingen door elkaar**: de kaart vergeleek twee LOSSE laadcycli
(94,0 -> 59,4) terwijl de tegel de MEDIAAN toont (86,9%). Daardoor leek
die -34,6 op de 86,9% te slaan. En "%" achter een verschil leest als een
procentuele daling, terwijl het PROCENTPUNTEN zijn.

**Waarom ze mogen verschillen**: de mediaan bestaat omdat één laadcyclus
sterk kan afwijken (v0.63.10) - anders zou een enkele meting de
veiligheidsmarge van de reserveberekening verschuiven. Maar dat verschil
tonen zonder uit te leggen waarom maakt het onbruikbaar.

De regel zegt nu: "Laatste laadcyclus 59,4%, daarvoor 94,0% (-34,6
procentpunt). De tegel hierboven toont de mediaan over 8 cycli - één
afwijkende cyclus telt daar bewust nauwelijks in mee."

**In de code stond het al goed** (weerbronnen, bias-drift); alleen het
dashboard liep achter.

**Getest**: nieuw `tests/test_percentage_points.py`, 4 tests.

**Volledige testsuite**: 1364 tests, allemaal groen.

## v1.15.8 — Temperatuurverschil: twee verklaringen, één conclusie

**Uit een export**: "Accumodules verschillen 5,0 °C in celtemperatuur -
bij gelijke belasting wijst dat op een module met hogere inwendige
weerstand."

**Te stellig**: er zijn twee even goede verklaringen - hogere inwendige
weerstand, of plaatsing (bovenaan de stapel, tegen een muur). Die tweede
kan de integratie niet zien, maar werd ook niet genoemd.

**Het vermogen maakt het onderscheid**: bij deze installatie is de
warmste module ook de zwakste (32 °C bij 542 W tegen 27 °C bij 602 W) -
dat past bij hogere inwendige weerstand. Levert de warmste evenveel of
meer, dan meldt de integratie nu dat het eerder aan de plaatsing ligt.
Zonder vermogenssensoren vervalt de duiding en blijft alleen het
temperatuurverschil staan.

**Celdelta-waarschuwing is weg**: module 1 stond op 0,19 V bij 100% SoC,
nu op 0,02 V bij 77%. Die spreiding was dus grotendeels
ladingsafhankelijk; mijn eerdere uitspraak dat de differentiële
vergelijking dat wegneemt klopte maar ten dele.

**Getest**: nieuw `tests/test_module_temperature_warning.py`, 4 tests.

**Volledige testsuite**: 1368 tests, allemaal groen.

## v1.15.9 — Drie kaarten toonden een rauwe sensortoestand

**Gemeld**: "Gesimuleerde actie: Onbekend", "Energie-check: Onbekend" en
"Accubescherming: 1600.0".

**Eén oorzaak**: de sensortoestand werd ongewijzigd getoond. "Onbekend"
leest als storing terwijl de simulatie gewoon niet draait; de
energie-check levert Engelse waarden (`enough_to_postpone`); en "1600.0"
is een getal zonder eenheid.

**Nu**: "simulatie draait niet", "genoeg om uit te stellen" / "bijladen
nodig" / "nog niet beoordeeld", en "1600 W ontlaadgrens" / "geen grens
actief". De sensoren zelf blijven ongewijzigd - daar wordt elders op
gerekend; alleen de weergave vertaalt.

"Goedkoopste blok: over 12 uur" klopte wel: dat is een tijdstempel dat HA
relatief toont.

**Onderweg**: de eerste poging zocht de kaarten op regelnummer en knipte
te veel weg (achttien falende tests). Hersteld uit de laatste zip en
opnieuw gedaan met de kaarttekst als anker.

**Getest**: nieuw `tests/test_raw_states_on_dashboard.py`, 5 tests,
waaronder een borging dat geen kaart een Engelse toestand toont.

**Volledige testsuite**: 1373 tests, allemaal groen.

## v1.16.0 — "Komend schema" toonde een getal

**Gemeld**: het komende schema was "raar".

**Oorzaak**: de tegel toonde de TOESTAND van de sensor, en dat is het
aantal geplande kwartieren - "96" zegt niets. De bruikbare informatie zat
in het attribuut `transitions`: de blokken met begintijd, eindtijd, modus
en prijsbereik.

**Nu**: op Overzicht "3 blok(ken) gepland — Nu smart tot 17:15, daarna
smart_discharging". Op de detailpagina de volledige tabel (van, tot,
modus, hoogste prijs); het verloop over de dag laat zich niet in een
tegel vangen, dus de tik leidt daarheen.

**Blinde vlek in een eigen test**: de kolomtest uit v1.14.6 telde
Jinja-filterpipes mee als tabelkolommen (`{{ x | timestamp_custom(...) }}`),
waardoor een tabel van vier kolommen op zeven uitkwam. Nu worden de
Jinja-expressies eerst verwijderd. Tweede keer dat deze test op zijn
eigen telling struikelde.

**Getest**: drie tests erbij in `test_raw_states_on_dashboard.py`.

**Volledige testsuite**: 1376 tests, allemaal groen.

## v1.16.1 — "PV-voorspelling bias: Onbekend" was geen storing

**Gevraagd**: "Bias ook kapot?"

**Nee**: die sensor toont de bias voor HET HUIDIGE UUR, en buiten de
daglichturen is die er niet. De export laat zien dat er vijftien uren
zijn geleerd, van 6:00 (0,53) tot 20:00 (0,29). De kaart meldt nu
"buiten daglichturen" met "15 uren geleerd" erbij.

**Nog een verzonnen attribuutnaam**: ik vroeg `profiel` op, het heet
`profile_confident`. Een sjabloon dat een niet-bestaand attribuut
opvraagt geeft stilzwijgend niets terug - de kaart ziet er correct uit
terwijl de telling ontbreekt. Derde keer vandaag dat een verzonnen naam
een kaart stil liet falen.

**Nu bewaakt**: een test controleert dat elk opgevraagd attribuut ergens
in de code wordt aangeboden. Die sloeg meteen aan op zeven attributen die
wél bestaan - in switch.py, button.py en coordinator.py. Alleen in
sensor.py kijken was te smal.

**Getest**: drie tests erbij in `test_raw_states_on_dashboard.py`.

**Volledige testsuite**: 1379 tests, allemaal groen.

## v1.16.2 — Systematische controle: vier kaarten met interne codes

**Gevraagd**: kijken of er nog meer gerepareerd moet worden.

**Alle zeventien kaarten nagelopen** die een rauwe sensortoestand tonen.
Vier gevallen: "Laatste reden: expensive_quarter", "Steelstofzuiger:
wacht_op_goedkoop_blok", "Fietsladers: idem", en "Kandidaten: 0" (een
getal zonder context).

Interne codes zijn prima als waarde in de logica, maar zeggen niets op
een Nederlands dashboard - dezelfde fout als bij de energie-check in
v1.15.9. Nu "duur kwartier", "wacht op goedkoop blok" en "geen nieuwe
kandidaten".

**De codes zelf blijven ongewijzigd**: vertalen gebeurt in de WEERGAVE.
De logica vergelijkt op `expensive_quarter`; dat aanpassen zou elke
vergelijking breken. Een test bewaakt dat.

**Wel in orde**: de andere dertien kaarten - MPC-advies, Monte Carlo en
Digital Twin hebben een eenheid, en het PV-installatieprofiel geeft zelf
al "nog niet bepaald" terug.

**Nu bewaakt**: elke beslisreden uit coordinator.py moet een vertaling
hebben (dertien nu); een nieuwe zonder label laat de test falen. Plus een
test dat de vertalingen leesbaar zijn (geen underscores).

**Getest**: nieuw `tests/test_internal_codes_translated.py`, 6 tests.

**Volledige testsuite**: 1385 tests, allemaal groen.

## v1.16.3 — De export zag het dashboard niet

**Gevraagd**: "Had je alles afgevangen met een betere diagnose file?"
Eerlijk antwoord: nee, grotendeels niet.

**Waarom**: van de veertien problemen op één dag zaten er tien in het
DASHBOARD en vier in de coordinator. De export bevatte alleen
sensorwaarden, niet hoe die worden getoond - elke fout zat in de laag
ertussen en was alleen op een screenshot te zien.

**Nu in de export**: `dashboard_health` controleert of elke entiteit waar
het dashboard naar verwijst bestaat (vangt voorvoegsel-fouten en
hernoemde sensoren) en of ze niet op unknown/unavailable staat (vangt de
"Onbekend"-kaarten). 66 entiteiten gecontroleerd; negen van de tien
dashboardfouten van vandaag zouden hierin zichtbaar zijn geweest.

Twee aparte lijsten, bewust: "Onbekend" kan normaal zijn (PV-bias buiten
daglichturen), "Entiteit niet gevonden" nooit.

**Wat een export niet kan zien**: uitlijning, kolombreedte, of een tekst
prettig leest. Daar blijven screenshots voor nodig - dat is een grens van
de export, geen tekortkoming.

**Getest**: nieuw `tests/test_dashboard_health_export.py`, 7 tests.

**Volledige testsuite**: 1392 tests, allemaal groen.

## v1.16.4 — Warmte kan de oorzaak zijn in plaats van het gevolg

**Gemeld**: het vermoeden dat accumodule 1 direct onder de omvormer zit.

**Dat keert het beeld om**: in v1.15.8 concludeerde ik "warmste levert
het minste, dus hogere inwendige weerstand". Maar een warmere accucel
heeft juist LAGERE inwendige weerstand - minder vermogen bij hogere
temperatuur past eerder bij een BMS dat terugregelt om de cel te
beschermen. Dan is de warmte de oorzaak van het lagere vermogen, niet het
gevolg van een zwakke module.

**Het rustverschil maakt het onderscheid**: externe warmte werkt dag en
nacht, eigen verlies alleen onder belasting. Bij deze installatie: 2 °C
in rust tegen 5 °C onder belasting - het verschil groeit dus met de
belasting, wat tegen de omvormer als enige verklaring pleit (al past die
2 °C basisverschil er wel bij).

**De melding**: bij een rustverschil van minstens 60% van het belaste
verschil wijst ze naar buiten ("staat er iets warms boven of naast, zoals
de omvormer?"), anders naar de module. Zonder rustmeting doet ze er geen
uitspraak over.

**Getest**: drie tests erbij in `test_module_temperature_warning.py`.

**Volledige testsuite**: 1395 tests, allemaal groen.

## v1.16.5 — "0.0 kWh opgewekt" na een herstart

**Gemeld**: het dagoverzicht van 22:00 meldde 0,0 kWh opgewekt terwijl de
omvormer 15,5 kWh had geproduceerd.

**De ontbrekende schakel**: de dagsleutel en `pv_production_today_kwh`
werden wél bewaard, het IJKPUNT van de kWh-meter niet. Na een herstart
klopt de dagsleutel dus (geen dagwissel, geen reset), maar
`_pv_energy_meter_day_start` is leeg - waarna de meterroute opnieuw ijkt
op de huidige stand. De opwek wordt dan bijna nul, en dat overschrijft de
bewaarde waarde. Bij meerdere herstarts op een dag blijft alleen de opwek
sinds de laatste over.

**Getoetst**: twee metingen na een herstart geven 16,4 kWh met bewaard
ijkpunt tegen 0,9 kWh zonder.

**Twee keer de verkeerde diagnose**: eerst dacht ik dat de dagsleutel
niet bewaard werd - die stond al in PERSISTED_DATE_FIELDS, ik had alleen
PERSISTED_PLAIN_FIELDS bekeken terwijl er vijf lijsten zijn. Die
"reparatie" zette het veld in de verkeerde lijst en de dagsleutel om naar
tekst, waardoor elf tests omvielen. Volledig teruggedraaid tot het
bestand identiek was aan v1.16.3.

**Getest**: nieuw `tests/test_pv_meter_persistence.py`, 6 tests.

**Volledige testsuite**: 1401 tests, allemaal groen.

## v1.16.6 — Samenhangcontrole na een dag met 25 versies

**Gevraagd**: controleren of alles na de vele wijzigingen nog samenwerkt.

**Ketens doorgetrokken** in plaats van alleen losse tests: een volledige
dag van 64 ticks (0 fouten), alle 14 diagnostiekmethodes, alle 23
export-aanroepen, 197 uitgelezen attributen, 0 sensoren zonder plek op
het dashboard, 0 onbekende attributen, 0 dode navigatiepaden, 6 van 6
diensten geregistreerd.

**De aansturing is niet geraakt**: de reserveberekening
(`_get_dynamic_discharge_reserve_kwh`) en de planningsprojectie
(`_build_forecast_timeline`) zijn byte voor byte identiek aan v0.63.114.
Alles van vandaag zat in weergave, meldingen en diagnostiek.

**Eén vals alarm**: mijn controle meldde zes niet-geregistreerde
diensten; dat bleek het zoekpatroon (de naam staat op de regel ná
`async_register`). Alle zes zijn correct geregistreerd.

**Getest**: nieuw `tests/test_end_to_end_coherence.py`, 6 tests die
voortaan bij elke wijziging meedraaien.

**Volledige testsuite**: 1407 tests, allemaal groen.

## v1.16.7 — Waterontharder was onzichtbaar geworden

**Gevraagd**: waar te zien of de waterontharder heeft geregenereerd.
Antwoord: nergens - bij het opruimen van v1.12.0 is die informatie
volledig van het dashboard verdwenen (nul verwijzingen naar
`waterontharder_laatste_regeneratie` of de regeneratievlag).

De detectie draaide wel, inclusief de volumedrempel uit v1.9.2, maar het
resultaat was niet te zien - en dat is precies waarvoor die detectie is
gebouwd.

**Nu op de detailpagina**: de laatste regeneratie met hoe lang geleden,
hoeveel recente gebruiksmomenten er een waren, en waaraan ze worden
herkend (nachtelijke sessie van minstens 10 liter). Die laatste regel is
nodig om te beoordelen of een gemiste regeneratie aan de ontharder ligt
of aan de drempel.

**Onderweg**: de eerste versie rekende het aantal dagen uit met
`as_timestamp`, wat twee bestaande tabeltests brak (de testrenderer geeft
daar een datetime door waar een getal wordt verwacht). Vervangen door
`relative_time`.

**Getest**: drie tests erbij in `test_water_tab_filtering.py`.

**Volledige testsuite**: 1410 tests, allemaal groen.

## v1.16.8 — Diepe analyse: twee vondsten en één correctie

**Gevraagd**: diepe analyse van de export voor installatie. Alle 206
coordinator-velden nagelopen, KPI's onderling getoetst, geschiedenissen
op patronen bekeken.

**Vondst 1 - zelfconsumptie 0,0%**: bij 0,215 kWh opwek en 0,56 kWh
export. Rekenkundig juist (de begrenzing uit v1.9.2 kapt de export op de
dagopwek) maar het leest als "geen enkele zon zelf gebruikt". De accu
verkocht 's nachts meer dan de zon die ochtend opwekte. Onder een halve
kWh geen uitspraak meer.

**Vondst 2 - twee tekort-nachten op rij**: tekorten op 7 én 8 augustus.
De zelfevaluatie uit v1.14.0 wacht op veertien dagen; voor een
VERHOUDING is dat verdedigbaar, maar twee op rij is een patroon - dan is
er twee nachten achtereen tegen de ochtendprijs bijgekocht. Die melding
wacht nu niet meer op de dagendrempel.

**Correctie op gisteren**: ik noemde de celspreiding van module 1
"grotendeels ladingsafhankelijk". Te geruststellend: 0,190 V bij 100%,
0,020 V bij 77%, en nu weer 0,190 V bij 12% SoC - met gelijke
temperaturen (23/23/23). Hoog aan beide uiteinden past bij een cel met
afwijkende capaciteit.

**Twee valse alarmen**: `reserve_shortfall_dates` en `_excess_dates`
bevatten dezelfde datums, maar de docstring zegt dat het ALLE dagen zijn
(de vlaggen staan in de `_history`-lijsten). En
`gross_consumption_today_kwh` las ik uit de verkeerde sectie.

**Getest**: nieuw `tests/test_deep_analysis_findings.py`, 8 tests.

**Volledige testsuite**: 1418 tests, allemaal groen.

## v1.16.9 — Zon via de accu telt nu als zelfconsumptie

**Gemeld**: zon die via de accu in huis wordt gebruikt is nog steeds
zelfconsumptie, alleen niet rechtstreeks.

**Terecht**: de begrenzing uit v1.9.2 kapte de export op de dagopwek,
maar nam nog steeds aan dat export ZON is zolang er die dag genoeg
scheen. Op de ochtend van 9 augustus gaf dat 0% bij 0,215 kWh opwek en
0,56 kWh export - terwijl die export uit de accu kwam.

**Nieuwe volgorde**: wat de accu heeft ONTLADEN kan geen zon-export van
vandaag zijn (die energie is eerder geladen), dus dat wordt eerst van de
export afgetrokken. Zon die rechtstreeks het net op gaat verlaagt de
verhouding nog steeds - het is geen truc die alles op 100% zet.

**De werkstand in plaats van een teken**: gemeld dat er geen tekenfout in
mocht sluipen, met de suggestie
`sensor.zendure_manager_operation_state`. Bij deze installatie staat
`invert_battery_power_sign` op True en was niet uit de export vast te
stellen of dat klopt. De werkstandsensor ("Laden"/"Ontladen"/"Inactief")
is nu de eerste keus, met het vermogensteken als terugval.

**Nieuw configuratieveld**: "Werkstand-sensor van de accu".

**Getest**: nieuw `tests/test_battery_state_and_self_consumption.py`, 12
tests.

**Volledige testsuite**: 1430 tests, allemaal groen.

## v1.17.0 — Eén detailpagina per onderwerp

**Gemeld**: de detailpagina bevat zoveel dat het niet overzichtelijk is;
verzoek om aparte pagina's per facet.

**Terecht**: de verzamelpagina telde zestien kaarten en bijna 6000
tekens - niet overzichtelijker dan de tabbladen die er in v1.12.0 voor
waren opgeruimd. Het probleem was verplaatst, niet opgelost.

**Zeven pagina's**: Accu, Apparaten, Klimaat, Water, Planning, Zon en
Meetkwaliteit. Elke pagina houdt hooguit zes kaarten en 2500 tekens; een
test bewaakt dat de indeling niet stilaan weer te grof wordt.

**Zeventien tegels omgeleid** naar hun eigen onderwerp. Een tegel die op
de verkeerde pagina uitkomt is erger dan geen doorklik - dan zoek je op
de verkeerde plek. Een test controleert de koppeling per onderwerp.

**Niets kwijtgeraakt**: alle zestien kaarten verdeeld; tests bewaken dat
de tien inhoudelijke kaarten er nog zijn en dat elke pagina een ingang
heeft.

**Onderweg**: negentien tests zochten naar één pagina "Details". Die
helpers kijken nu naar het pad-voorvoegsel `detail-`. Twee aannames
moesten mee: een detailpagina mág klein zijn (dat is het doel) en het pad
heet niet meer `/details`.

**Getest**: nieuw `tests/test_detail_pages_per_topic.py`, 8 tests.

**Volledige testsuite**: 1438 tests, allemaal groen.

## v1.17.1 — Twaalf pagina's, elk één onderwerp

**Gemeld**: liever meer subviews met specifiekere informatie - PV = PV,
accu = accu, water = water.

**De opsplitsing van v1.17.0 was te grof**: de tabbladen Systeem,
Financieel, Verloop en Kwaliteit telden 11 tot 16 kaarten met onderwerpen
door elkaar. Op Systeem stonden accu, apparaten, klimaat én water samen.

**Nu twaalf pagina's**: PV/zon, Accu, Water, Klimaat, Apparaten,
Vaatwasser & wasmachine, Planning, Kosten, Besparing, Adviesmodules,
Meetkwaliteit en Verloop. Alle 59 kaarten verdeeld op INHOUD, niet op
herkomst.

**Zichtbaar blijven**: Overzicht, Visueel en Meldingen. De rest is
subview, bereikbaar via de statustegels en "Meer bekijken". Twee
pagina's raakten tijdens het herbouwen hun ingang kwijt en zijn
hersteld.

**Bekende valkuil opnieuw geraakt**: het dashboard is via `yaml.dump`
herschreven, wat aanhalingstekens in Jinja verdubbelt - precies waarom in
v1.10.1 een YAML-ronde werd vermeden. Na parsing is de Jinja identiek,
maar tests die op de ruwe tekst zochten faalden; die lezen nu via de
geparste kaarten.

**Niets kwijtgeraakt**: 55 sensoren geplaatst, geen dode navigatiepaden,
geen onbereikbare pagina's, 143 kaarten.

**Getest**: drie tests erbij in `test_detail_pages_per_topic.py`.

**Volledige testsuite**: 1441 tests, allemaal groen.

## v1.17.2 — Compactere landingspagina en PV-voorspelkwaliteit

**Gemeld**: veel lege vlakken op de landingspagina, en de wens om meer
analyseparameters te zien - bijvoorbeeld hoe goed de PV-voorspelling is.

**Het wit**: vier van de vijf secties hadden een oneven aantal tegels op
halve breedte (gat rechtsonder), en de statustegels stonden op
multiline_secondary met een hele zin. Besturing, Status per onderwerp en
Meer bekijken staan nu op vier kolommen (drie per rij), met ingekorte
labels.

**PV-voorspelkwaliteit**: er werd alleen de BIAS getoond (-11,6%). Nu ook
de gemiddelde absolute fout (15,2%), mediaan (10,4%), spreiding (14,3%),
beste en slechtste dag (4,5% / 37,2%) en het aantal dagen binnen 10% en
20%. Bias en fout zijn verschillende dingen: wie alleen de bias ziet
denkt dat corrigeren het oplost, maar dan blijft de spreiding over. Met
een duiding erbij, want "15,2%" is een getal zonder schaal.

**Twee eigen tests moesten mee**: de regel "geen tabellen buiten
Overzicht" stamt uit v1.12.0 toen alles op één niveau stond;
detailpagina's zijn juist bedoeld voor tabellen. En de labeltest sloeg
terecht aan op de smallere tegels (15 in plaats van 22 tekens).

**Getest**: nieuw `tests/test_pv_forecast_quality.py`, 13 tests.

**Volledige testsuite**: 1454 tests, allemaal groen.

## v1.17.3 — Tegels op volle sectiebreedte

**Gemeld**: veel labels onleesbaar afgekapt, met de opmerking dat er drie
secties in de breedte staan.

**Dubbel opgedeeld**: Home Assistant zet secties naast elkaar (drie op
een breed scherm), dus elke sectie is ongeveer een derde van het scherm.
Daarbinnen stonden de tegels op 4 van de 12 kolommen - effectief een
NEGENDE van het scherm. Daar past "Accumodules" niet in.

De drie kolommen die je ziet zijn de secties zelf; binnen een sectie nog
eens opdelen is dubbelop - precies wat er in v1.17.2 gebeurde bij het
weghalen van wit.

**Nu volle sectiebreedte** voor elke tegel, met verlengde labels ("Accu
en apparaten" in plaats van "Accu") en statuszinnen die weer mogen
doorlopen. De labeltest gaat van 48 naar 34 tekens voor volle breedte,
omdat een sectie een derde van het scherm is.

**Getest**: twee tests erbij in `test_dashboard_label_length.py`; één
bestaande test legde de halve breedte van de koeltegel vast en is
bijgesteld.

**Volledige testsuite**: 1456 tests, allemaal groen.

## v1.17.4 — Dertien kaarten zonder icoon

**Gemeld**: de Airco-verwachting toonde een lege blauwe cirkel.

**Oorzaak**: de sensor heeft wél een icoon (`_attr_icon`), maar een
mushroom-kaart neemt dat niet over als het veld `icon` op de kaart
ontbreekt. Dertien kaarten hadden dat - ontstaan bij het herverdelen van
v1.17.1, waar entity-cards zijn verplaatst die nooit een eigen icoon
hadden (op de oude tabbladen stonden ze in een lijst, waar het niet
opviel).

**Nu allemaal voorzien** van een passend icoon per onderwerp; de sensoren
zelf blijven ongewijzigd.

**Nu bewaakt**: élke entity- of template-kaart heeft een icoon, en elk
icoon begint met `mdi:` - een naam zonder dat voorvoegsel rendert niet en
dat zie je pas op het scherm.

**Volledige testsuite**: 1458 tests, allemaal groen.

## v1.17.5 — PV-tegel op Overzicht

**Gemeld**: er ontbreekt een PV-tegel om op te klikken voor alle
PV-informatie.

**Terecht**: er was wél een PV-pagina sinds v1.17.1, maar
`get_topic_summaries()` maakte geen samenvatting voor zon - en zonder
samenvatting geen tegel. De pagina was alleen via "Meer bekijken" te
vinden.

**De tegel toont** de opwek van vandaag plus de betrouwbaarheid van de
voorspelling ("15,5 kWh opgewekt vandaag. De voorspelling zit er over 7
dagen gemiddeld 15% naast."). De kleur volgt die kwaliteit: groen onder
10% gemiddelde fout, oranje tot 20%, rood daarboven.

**Vooraan geplaatst**: de zon is de bron van alles wat daarna gebeurt.
Zonder voltooide dagen toont hij nog steeds de opwek, met de reden erbij.

**Getest**: vier tests erbij in `test_pv_forecast_quality.py`.

**Volledige testsuite**: 1462 tests, allemaal groen.

## v1.17.6 — Airco-verwachting gaf een temperatuur

**Gemeld**: de kaart toonde 22,0 °C terwijl er een kans in procenten werd
verwacht, met de opmerking dat er van eigen airco-gebruik geleerd kan
worden.

**Dat mechanisme bestond al** sinds v0.63.55: elke temperatuurmeting gaat
in een bin van 1 °C en krijgt een uur de tijd; gaat de airco in dat uur
aan, dan telt die waarneming als "ja". Per bin de laatste 20
waarnemingen, zodat het meebeweegt met het seizoen.

**Maar de sensor gaf de HUIDIGE woonkamertemperatuur terug** - hetzelfde
getal dat de temperatuursensor al toont. De kans zat in een attribuut dat
nergens in beeld kwam.

**Nu**: sensor heet "Airco-verwachting (kans binnen 1 uur)" en geeft een
percentage. Op de Klimaat-pagina staat de hele tabel met alle geleerde
bins plus uitleg over het mechanisme - zonder die uitleg is niet te
beoordelen waarom een bin op 0% staat.

**Bekend patroon opnieuw**: het hernoemen brak twee tests omdat HA de
entity_id vasthoudt bij de eerste aanmaak
(`airco_verwachting_woonkamertemperatuur`). Dezelfde regel als bij
`piekvermogen` in v1.6.4; de uitzonderingenlijst is aangevuld.

**Getest**: nieuw `tests/test_airco_expectation.py`, 7 tests.

**Volledige testsuite**: 1469 tests, allemaal groen.

## v1.17.7 — Tijdstempel en een vlakke kolom in de klimaattabel

**Gemeld**: de tijdsaanduiding in de klimaattabel was incorrect - elke
rij toonde de rauwe ISO-tijdstempel (`2026-08-09T11:00:00+02:00`),
waardoor die kolom breder was dan de rest van de tabel samen. Nu alleen
het uur.

Alle andere tabellen gecontroleerd op hetzelfde patroon: geen tweede
geval, met een test die dat blijft bewaken.

**Opgemerkt bij het kijken**: de kolom "Betrouwbaar" stond op alle uren
op 22,0 °C terwijl het buiten van 26,7 naar 31,1 liep. Dat is bewust
gedrag (bij te weinig metingen wordt de huidige temperatuur aangehouden -
liever geen verandering voorspellen dan een verkeerde, v1.1.2) maar het
was uit de tabel niet af te lezen. Er staat nu een regel onder die dat
uitlegt, en de kolom Metingen laat zien waarom een uur op de terugval
valt.

**Getest**: nieuw `tests/test_climate_table_time.py`, 7 tests.

**Volledige testsuite**: 1476 tests, allemaal groen.

## v1.17.8 — Ja, de PV-voorspelling wordt echt gecorrigeerd

**Gevraagd**: wordt de PV-verwachting daadwerkelijk gecorrigeerd?

**Ja, op drie niveaus**, maar dat was nergens te zien: (1) vandaag worden
de resterende uren geschaald op wat er tot nu toe werkelijk is opgewekt,
(2) toekomstige uren krijgen de per uur geleerde verhouding, (3) alleen
als die er voor dat uur niet is geldt het daggemiddelde.

**Die volgorde doet ertoe**: bij deze installatie loopt de uurcorrectie
van x0,53 om 6:00 via x1,03 om 10:00 tot x0,29 om 20:00. Vijftien uren
hebben een eigen correctie; één daggemiddelde van -11,6% zou dat verschil
wegpoetsen.

**Waar het gebeurt**: in `_get_expected_pv_kwh`, de functie die de
voorspelling levert aan de RESERVEBEREKENING - dus invoer voor de
beslissing, geen weergave. Drie tests op de code zelf falen zodra iemand
de toepassing eruit haalt en alleen de meting laat staan.

**Nu zichtbaar** op de PV-pagina: de hele keten, het aantal uren met een
eigen correctie, en de sterkste en zwakste.

**Getest**: nieuw `tests/test_pv_correction_applied.py`, 10 tests.

**Volledige testsuite**: 1486 tests, allemaal groen.

## v1.18.0 — Waterontharder-drempel en waterverbruik toewijzen

**Gemeld**: de waterontharder had niet geregenereerd terwijl dat wel werd
gemeld; plus het voorstel om waterverbruik aan een bron toe te wijzen.

**Drempel stond te laag**: tien liter haalt een wc-spoeling plus een
kraan al. Een echte regeneratie spoelt 50 tot 200 liter over 20 tot 60
minuten. Nu 40 liter EN 15 minuten, allebei nodig - een snelle sessie van
veertig liter is eerder een bad of een lekkage.

**Waterverbruik toewijzen**: vaatwasser draait -> vaatwasser; wasmachine
-> wasmachine; CV-ketel actief en langer dan 3 minuten -> douche, korter
-> handen wassen; Quooker -> keuken; niets aan en ~6 L in ~40 sec ->
toilet; anders onbekend (gokken is erger). Volgorde van specifiek naar
algemeen.

**CV-ketel uit de bevestigde NILM-apparaten** in plaats van een eigen
configuratieveld - gevraagd: "CV ketel kan toch op basis van het vermogen
dat je al weet?"

**Bevestigen en leren**: de actie `confirm_water_source` legt vast waar
de laatste sessie heen ging. Per bron worden volume en duur bewaard; na
drie bevestigingen gebruikt de integratie jouw eigen patroon met de
werkelijke spreiding in plaats van de vuistregel. Twee bevestigingen zijn
niet genoeg om iets over spreiding te zeggen.

**Getest**: nieuw `tests/test_water_source_attribution.py`, 16 tests.

**Volledige testsuite**: 1502 tests, allemaal groen.

## v1.18.1 — Airco-verwachting werkt ook in de winter

**Gevraagd**: werkt het airco-voorspellingsmechanisme ook bij koude
temperaturen?

**Ja**: de bins zijn temperatuurbins van 1 °C en dus richtingsneutraal,
en AIRCO_ACTIVE_HVAC_ACTIONS bevat zowel "heating" als "cooling". Bij 18
°C leert hij wanneer je gaat stoken, bij 26 °C wanneer je gaat koelen.

**Maar de RICHTING werd niet bewaard**, en dat is geen detail: "60% kans
dat de airco aangaat" betekent iets heel anders bij 18 dan bij 26 graden
- tegengestelde acties met een tegengesteld gevolg voor het verbruik. Nu
wordt per bin bijgehouden wat er gebeurde, met een kolom Richting in de
tabel. De richting wordt meebewaard over herstarts.

**Bins van vóór deze versie** hebben nog geen richting en tonen een
streepje; dat loopt niet stuk en vult zich vanzelf.

**Getest**: vijf tests erbij in `test_airco_expectation.py`.

**Volledige testsuite**: 1507 tests, allemaal groen.

## v1.18.2 — Alles herleidbaar, plus aanwezigheidsdetectie

**Gevraagd**: alles van vandaag herleidbaar in de diagnostiek, en
aanwezigheidsdetectie via de bewegingssensoren.

**Zeven onderdelen ontbraken in de export**: statuszinnen, geleerde
waterbronnen, waterbron-overzicht, airco-richting, accu-ontlading vandaag
en het rustverschil tussen de accumodules. Dat is het gat dat vandaag
telkens pijn deed - tien van de veertien problemen zaten in een laag die
de export niet toonde. Er staat nu een test met één lijst van alles van
deze dag.

**Aanwezigheid uit bewegingssensoren**: instelbare lijst, geen
automatische herkenning - van de twintig bewegingsachtige entiteiten
hangen er meerdere buiten (deurbel, tuin, schuur) en die slaan aan op
voorbijgangers. Nieuw configuratieveld "Bewegingssensoren binnenshuis",
meerdere te kiezen.

Beweging betekent thuis; langer dan 45 minuten stil betekent weg - ruim
genomen, want stilzitten of slapen is geen afwezigheid.

**En het leert**: per halfuur van de week hoe vaak er iemand thuis was.
Begrensd op zes weken zodat oude gewoontes niet blijven meewegen; onder
drie waarnemingen geen uitspraak. Afwezigheid wordt net zo goed geleerd
als aanwezigheid.

**Getest**: nieuw `test_presence_detection.py` (15 tests) en
`test_diagnostics_completeness.py` (4 tests).

**Volledige testsuite**: 1526 tests, allemaal groen.

## v1.19.0 — Uitbreidingsadvies op basis van meetdata

**Gevraagd**: advies over het uitbreiden van de accu - een tweede
omvormer met modules erbij, waarmee het vermogen ~50% omhoog kan.

**De kernvraag**: knelt het VERMOGEN of de CAPACITEIT? Dat bepaalt of een
tweede omvormer of een extra module het juiste antwoord is, en het is uit
de eigen meetgegevens te beantwoorden.

Bij deze installatie: hoogste geleerde uurverbruik 644 W tegen 1600 W
ontlaadvermogen (40% benutting) - het vermogen knelt dus niet. Maar 7,7
kWh dagverbruik tegen 7,3 kWh bruikbare capaciteit, en twee tekort-
nachten van de vijf - de capaciteit wel.

**Advies**: een extra module aan de bestaande omvormer; een tweede
omvormer voegt vermogen toe dat ongebruikt blijft.

**Geen koopadvies**: prijzen, garantie en de levensduur van de bestaande
modules kent de integratie niet. Het voorbehoud staat er expliciet bij -
negen dagen in augustus is geen jaar.

**Getest**: nieuw `tests/test_expansion_advice.py`, 10 tests.

**Volledige testsuite**: 1536 tests, allemaal groen.

## v1.19.1 — Eén fout maakte alle acht tegels blanco

**Gemeld**: alle acht tegels onder "Status per onderwerp" toonden
tegelijk "Nog geen gegevens" - wat niet kan, want ze lezen verschillende
onderwerpen.

**Twee keer dezelfde vorm**:
- Het attributenblok van de GACS-sensor was één dict-expressie. Gooit één
  aanroep een fout, dan mislukt het HELE blok en heeft HA geen enkel
  attribuut meer.
- `get_topic_summaries` roept sinds v1.17.5 intern
  `get_pv_forecast_quality` aan voor de zon-samenvatting. Faalt die, dan
  valt de hele lijst van acht weg - ook water en klimaat, die er niets
  mee te maken hebben.

**Eigen schuld**: er zijn vandaag vijf aanroepen aan dat blok toegevoegd
zonder dat risico af te dekken.

**Nu apart afgeschermd**: elk deel wordt los opgehaald; wat werkt komt
door, wat faalt levert een leesbare foutmelding op in plaats van stilte.
Stil terugvallen is erger dan een foutmelding - dan zoek je in de
verkeerde hoek.

**Onderweg**: `import logging` belandde eerst midden in een importblok en
daarna vóór `from __future__ import annotations`; twee keer hersteld.

**Getest**: nieuw `tests/test_attribute_isolation.py`, 7 tests.

**Volledige testsuite**: 1543 tests, allemaal groen.

## v1.19.2 — De export zag ontbrekende attributen niet

**Gemeld**: ook op de PV-pagina bleven twee kaarten leeg.

**Verhelderend beeld**: op datzelfde scherm werkte de bias-tegel (0.933,
15 uren geleerd) - die leest een andere sensor. De twee lege kaarten
lezen allebei de GACS-sensor, dezelfde als de acht blanco statustegels.
Eén gemeenschappelijke oorzaak, aangepakt in v1.19.1.

**Maar de export had dit moeten aanwijzen**: de dashboardcontrole uit
v1.16.3 keek of elke ENTITEIT bestaat. Dat was hier niet het probleem -
de sensor bestond, zijn ATTRIBUTEN ontbraken. Een sjabloon dat een
ontbrekend attribuut opvraagt krijgt None en toont zijn vangnettekst; op
het scherm niet te onderscheiden van "nog niets geleerd".

De controle kijkt nu ook naar attributen en meldt ze bij naam.

**Onderweg**: de eerste versie vond niets omdat het sjabloon met
`yaml.dump` is weggeschreven en aanhalingstekens verdubbeld op schijf
staan - derde keer dat die keuze uit v1.17.1 iets breekt. De zoekactie
normaliseert nu eerst.

**Getest**: vijf tests erbij in `test_dashboard_health_export.py`.

**Volledige testsuite**: 1548 tests, allemaal groen.

## v1.19.3 — De export kon zelf omvallen

**Gemeld**: de diagnostiek levert een tekstbestand op in plaats van JSON.

**Terechte conclusie**: de exportfunctie was één grote dict-expressie met
dertig aanroepen. Gooit er één een fout, dan mislukt het hele bestand en
krijg je een foutpagina.

Dat is het verkeerde moment om te falen - de export is het gereedschap
dat je nodig hebt WANNEER er iets stuk is. Vandaag zijn er zeven
aanroepen aan toegevoegd; elke toevoeging vergrootte de kans dat het
geheel omvalt. Zelfde patroon als het attributenblok in v1.19.1, en
dezelfde oplossing.

**Nu**: elk onderdeel apart; een fout levert {"fout": "..."} op en de
rest komt door. De fout gaat ook naar het logboek - een stil weggevallen
onderdeel is erger dan een zichtbare fout.

**Niet vastgesteld**: welke aanroep het in de praktijk liet vastlopen. In
een test met de echte toestand slagen alle dertig, dus het zit in iets
dat alleen in een draaiende Home Assistant optreedt. Met deze versie komt
de fout in het bestand te staan.

**Onderweg**: `import logging` belandde weer op de verkeerde plek -
derde keer vandaag.

**Getest**: drie tests erbij in `test_diagnostics_completeness.py`.

**Volledige testsuite**: 1551 tests, allemaal groen.

## v1.19.4 — De export gaf een 500, en meldde dat niet

**Gemeld**: een 500 Internal Server Error bij het downloaden, plus de
opmerking dat er geen melding kwam dat het systeem niet correct
functioneert.

**De afscherming zat op de verkeerde plek**: v1.19.3 ving fouten in de
AANROEPEN, maar HA serialiseert het resultaat pas daarna. Een waarde die
JSON niet aankan laat het alsnog mislukken. Welk veld dat was is niet te
achterhalen gebleken; nu gaat de hele export door een laatste stap die
alles wat JSON niet kent omzet naar tekst. Liever een leesbare
tekenreeks dan geen bestand.

**Afschermen zonder melden is stil falen**: onderdelen zijn vandaag
afgeschermd zodat één fout niet alles meesleept, maar daarmee liep een
storing stil door - precies de fout die het afschermen moest voorkomen,
één laag hoger. Een gefaald onderdeel wordt nu vastgelegd en verschijnt
als aandachtspunt, met de uitleg dat de kaart zijn vangnettekst toont.
Ook in de export onder `internal_failures`.

**Getest**: nieuw `tests/test_export_never_500s.py`, 11 tests.

**Volledige testsuite**: 1562 tests, allemaal groen.

## v1.19.5 — De export wees de fout zelf aan

De verse export levert JSON op en `internal_failures` bevat:
"uitbreidingsadvies": "TypeError: unsupported operand type(s) for +:
'int' and 'list'".

**De fout**: `hourly_consumption_profile` is `dict[int, list[float]]` -
per uur de LOSSE metingen, niet het gemiddelde. Het uitbreidingsadvies
gebruikte hem alsof er getallen in stonden. `learned_hourly_avg_kw()`
doet die omrekening al en wordt ook door de export gebruikt.

**Waarom het niet eerder opviel**: de tests zetten het profiel met
kant-en-klare getallen en toetsten iets dat in productie niet bestaat. Die
opstelling gebruikt nu dezelfde structuur als de werkelijkheid.

Met de echte cijfers verandert de uitkomst nauwelijks: piek 497 W tegen
1600 W (31% benutting), 7,5 kWh dagverbruik tegen 7,3 kWh bruikbaar. De
conclusie blijft: een module, geen omvormer.

**De attributencontrole uit v1.19.2 werkte ook**: `kandidaat_naam` en
`kandidaat_vermogen_w` bestaan op de KNOP, niet op de sensor. De kaart
"Te beoordelen" las de verkeerde entiteit en toonde stilletjes niets.

**De zeven lege entiteiten zijn in orde**: simulatie draait niet,
energie-check nog niet beoordeeld, gezondheidsscore te weinig metingen,
adviesmodules verzamelen nog.

**Getest**: twee tests erbij in `test_expansion_advice.py`.

**Volledige testsuite**: 1564 tests, allemaal groen.

## v1.19.6 — Nachtvenster waterontharder instelbaar

**Gemeld**: de ontharder draait meestal tussen 02:00 en 05:00; de sessie
van 114 liter overdag was iets anders.

**Correctie op de eigen analyse**: die sessie (114 L in 17,2 min om
10:26) voldoet aan beide drempels, en ik stond op het punt het
nachtvenster te laten vallen omdat er volumegestuurde ontharders
bestaan. Dat zou verkeerd zijn geweest - het was een bad of de tuin (6,6
L/min is een kraan op vol debiet), en zonder venster was dat als
regeneratie geteld.

Het venster is dus het onderscheidende kenmerk, niet het volume.

**Nu instelbaar**: het stond vast op 00:00-06:00 terwijl deze ontharder
tussen 02:00 en 05:00 draait; een bad om 23:30 of 05:30 viel binnen dat
venster. Met 2 en 5 ingevuld valt zo'n sessie er niet meer in. Standaard
blijft 00:00-06:00.

**Waarom instelbaar en niet slimmer**: de bewoner weet wanneer zijn
ontharder draait, de integratie niet - sneller en betrouwbaarder dan het
uit maandenlange data afleiden.

**Getest**: vier tests erbij in `test_water_source_attribution.py`.

**Volledige testsuite**: 1568 tests, allemaal groen.

## v1.20.0 — Slapen is geen afwezigheid

**Gemeld**: als de overloopsensor 's avonds de laatste beweging is, is er
wel iemand thuis maar wordt er geslapen.

**Scherp gezien**: zonder dat kenmerk ziet stilte er hetzelfde uit,
terwijl "niemand thuis" en "iedereen slaapt" tegengestelde situaties zijn
- bij afwezigheid mag alles uit, bij slapen moet de nachtreserve juist
kloppen en loopt het basisverbruik door.

**De volgorde is het bewijs**: bewoog de slaapsensor als LAATSTE en
daarna niets meer, dan is iemand naar boven. Bewoog er daarna nog iets
beneden, dan is die persoon weer op. Buiten 20:00-05:00 telt de sensor
niet, want overdag loop je er ook langs.

**Instelbaar**: een overloop, trap of slaapkamer verschilt per huis.
Nieuw veld "Slaapsensor" bij Configureren.

**En het leert de bedtijd**: bij elke overgang wordt het tijdstip
bewaard; na een paar nachten toont de kaart de typische bedtijd. Een
bestaande borgingstest ving dat dit eerst niet werd bewaard.

**Onderweg**: de nieuwe kaart had vijf `if` en vier `endif`; dat kwam er
doorheen tot de tabeltests erop aansloegen, met een foutmelding die niet
naar de oorzaak wees. Er staat nu een test op die elk sjabloon door Jinja
zelf laat parsen - directer dan haakjes tellen, en met de naam van de
kaart erbij.

**Getest**: zeven tests erbij in `test_presence_detection.py`, plus de
Jinja-controle in `test_dashboard_tables.py`.

**Volledige testsuite**: 1576 tests, allemaal groen.

## v1.20.1 — Aanwezigheid: sneller, met bron, tv en vakantiemelding

**Gemeld**: 25 minuten van huis, terwijl de kaart "thuis" bleef tonen.
Dat klopte met de oude drempel van 45 minuten, die er stond om stilzitten
op de bank niet als afwezigheid te tellen.

**De televisie lost dat op**: tv aan telt nu als aanwezig, waarmee de
reden voor die ruime drempel vervalt. Van 45 naar 10 minuten zodra er een
tv-entiteit is ingesteld; zonder tv blijft hij op 45.

**Tabel met laatst gedetecteerde sensor**: per sensor het laatste moment
en hoe lang geleden, nieuwste bovenaan. Onderweg bleek de detectie te
stoppen bij de eerste sensor die bewoog; voor deze tabel moeten ze
allemaal worden vastgelegd.

**Melding bij beweging tijdens vakantie**: met sensornaam en tijdstip,
demping vijf minuten. Staat als enige nieuwe melding standaard aan - geen
uitzondering op de regel maar een gevolg ervan, want hij vuurt alleen als
de vakantiestand aan staat.

**Onderweg**: een testhulpje kende `binary_sensor.gang` niet, waardoor
tests die hem aanzetten stilzwijgend niets deden. En de naamopzoeking
ging stuk op een toestand zonder `name`.

**Getest**: dertien tests erbij in `test_presence_detection.py`.

**Volledige testsuite**: 1589 tests, allemaal groen.

## v1.20.2 — Live beweging en gewogen bewolking

**Beweging werd structureel gemist**: de tick draaide elke vijf minuten
en keek of een sensor op DAT MOMENT "on" stond. Een bewegingsmelder staat
30-60 seconden aan, kans ongeveer één op vijf. De export bewees het: 3
van de 15 sensoren ooit waargenomen, de laatste 550 minuten geleden,
terwijl er die nacht geslapen en opgestaan was. Voor de vakantiemelding
fataal - die kwam meestal helemaal niet.

Beweging loopt nu via state-change events, net als water en accukoeling.
De afgeleide (thuis/weg/slaapt) blijft op de tick; die blijft ook een
vangnet zodat een herstart midden in een beweging die niet kwijtraakt.

**Bewolking**: 62% getoond terwijl het bijna onbewolkt was - het
gemiddelde van 78,1% en 46,0%. Wegen naar betrouwbaarheid gaf maar 60,0%,
want 81,5% en 90,5% liggen te dicht bij elkaar. Bij 32 procentpunt
verschil is middelen verkeerd: de uitkomst past bij geen van beide. Vanaf
25 procentpunt wint nu de aantoonbaar betere bron. Bij kleine verschillen
blijft het middelen.

**Nieuwe pagina Weerbronnen**: wat elke bron meldt naast hoe goed die
klopt met de panelen. Zowel PV als Klimaat liep over de tekengrens.

**Getest**: nieuw `tests/test_live_motion_and_weather_weighting.py`, 12
tests.

**Volledige testsuite**: 1601 tests, allemaal groen.

## v1.20.3 — De dagelijkse PV-vergelijking lukte nooit

**Gevonden bij het doorlichten van zeven exports**: `last_compared_date`
stond in allemaal op None en `deviation_history` bleef op zeven waarden
staan - allemaal uit de bootstrap, niet uit een live vergelijking.

**De oorzaak is de volgorde**: 20:00 legt "de voorspelling voor morgen"
vast, 23:59 vergelijkt als die datum vandaag is. Maar de vastlegging
schreef direct in `pending`, dus op 10 augustus om 20:00 werd dat 11
augustus - en om 23:59 klopte de datum niet meer. De vastlegging van
20:00 gooide elke avond weg wat om 23:59 vergeleken had moeten worden.

**Gevolg**: bias en spreiding stonden stil op de bootstrap-waarden. De
uurcorrecties liepen wél door via hun eigen per-uur pad; dat verklaart
waarom het zo lang onopgemerkt bleef.

**De correctie**: de vastlegging gaat naar een apart veld en schuift pas
door NA de vergelijking. Getoetst over twee volle dagen. De velden worden
meebewaard (een herstart tussen 20:00 en 23:59 zou de voorspelling
kwijtraken) en staan in de export.

**Rest van de diagnostiek**: numeriek schoon, alle leercontroles OK,
accurendement 90,8% (was 86,9%), zelfconsumptie terecht None bij 0,08 kWh
opwek. Drie tekort-nachten op rij worden terecht gemeld.

**Getest**: nieuw `tests/test_daily_forecast_comparison.py`, 6 tests.

**Volledige testsuite**: 1607 tests, allemaal groen.

## v1.20.4 — Volledige doorlichting van de diagnostiek

Alle tien secties van de export langsgelopen in plaats van twee.

**In orde**: 218 velden numeriek binnen bereik, 18 None-velden allemaal
verklaarbaar, vijf van vijf leercontroles OK, sensorgezondheid 100%,
energiebalans 67 W afwijking, geen plausibiliteitswaarschuwingen, 171
beslissingsregels met één lege (na herstart). De waterontharder
regenereerde om 03:17 (113,9 L in 26,9 min) - precies in het ingestelde
venster. Waterbron-toewijzing werkt: zes van twintig sessies gekoppeld.

**Vondst**: het hoogste geleerde UUR is 497 W, maar het gemeten
piekvermogen 2199 W - boven het ontlaadvermogen van 1600 W. Het
uitbreidingsadvies keek alleen naar uurgemiddelden, die zo'n piek
verbergen. Nu weegt het advies het gemeten piekvermogen mee, met een
aparte uitkomst voor korte pieken.

**Twee valse alarmen**: de energiebalansfout las ik als procenten terwijl
het watt is (67 W is normaal). En `expected_operation_mode` bestaat niet;
de echte velden zijn `last_expected_mode` (smart) en `last_reason`.

**Voor de gebruiker**: tien van de 37 bevestigde apparaten hebben geen
referentiewaarde (rolluiken, melkopschuimer) waardoor daar geen drift kan
worden vastgesteld. En twee paren dragen identieke namen zonder dat de
duplicaatdetectie ze meldde.

**Getest**: drie tests erbij in `test_expansion_advice.py`.

**Volledige testsuite**: 1610 tests, allemaal groen.

## v1.20.5 — De status liep achter op de sensoren

**Gemeld**: status "onbekend" terwijl de tabel een beweging van 0,2
minuten geleden toonde.

**Fout uit v1.20.2**: de live gebeurtenis vulde wél de tabel en
`last_motion_at`, maar herberekende de STATUS niet - die werd alleen op
de vijf-minutentick gezet en stond na een herstart op "onbekend" naast
een meting van twaalf seconden oud.

**Precies de verkeerde kant op**: afwezigheid mag vertraagd zijn (een
afgeleide die pas na minuten kantelt), aanwezigheid niet. Beweging zet de
status nu onmiddellijk op "thuis"; alleen de overgang naar "weg" wacht op
de tick.

**De tabel overleeft nu een herstart**: `presence_last_seen` werd niet
bewaard, waardoor de tabel na elke herstart leeg was - terwijl juist die
tabel moet verklaren waarom de status is wat hij is. `last_motion_at`
herstelt zich nu uit die tabel; zonder enige waarneming blijft "onbekend"
het eerlijke antwoord.

**Getest**: vier tests erbij in
`test_live_motion_and_weather_weighting.py`.

**Volledige testsuite**: 1614 tests, allemaal groen.

## v1.20.6 — Echte prijzen, en een gratis optie eerst

**Opgegeven**: omvormer 374 euro, accumodule 729 euro, incl. btw. Eerder
werd met 959 euro voor de omvormer gerekend - dat bleek de bundelprijs
mét module.

**Gratis optie eerst**: het ontlaadvermogen staat op 1600 W terwijl de
SolarFlow 2400 AC 2400 W kan. Dat is een instelling, geen hardwaregrens;
verhogen dekt de gemeten piek van 2199 W zonder kosten. Geld uitgeven
aanraden waar een instelling volstaat is slecht advies, dus dat staat
bovenaan.

**Terugverdientijd op basis van eigen meetdata**: opbrengst hele accu 212
euro/jaar, extra module ~35 euro/jaar (bewust minder dan het gemiddelde -
de eerste kWh vangt de grootste prijsverschillen). Module 20,6 jaar,
omvormer 10,6 jaar. De omvormer verdient zich twee keer zo snel terug -
de conclusie die de bundelprijs verborg.

Prijzen zijn instelbaar.

**Getest**: zes tests erbij in `test_expansion_advice.py`.

**Volledige testsuite**: 1620 tests, allemaal groen.

## v1.20.7 — De fabrikantspecificatie corrigeert het advies

**"Gratis" was het niet**: de verhoging van 1600 naar 2400 W vraagt
volgens Zendure een eigen groep zonder andere belasting, plus een
upgrade via de app. Het blijft de goedkoopste stap, maar "gratis" was
onjuist. De kaart heet nu "Eerst dit", met de voorwaarde erbij.

**Eén omvormer draagt zes modules** (17,28 kWh). Een vierde module heeft
dus geen tweede omvormer nodig. Het eerdere advies bij "beide knellen"
("een tweede omvormer mét eigen modules") was duurder dan nodig -
capaciteit los je op met modules alleen, en meerdere omvormers moeten óók
op aparte circuits.

**Wat wel klopte**: Zendure claimt tot 93% AC round-trip; de gemeten
90,8% zit daar dicht tegenaan. Garantie tien jaar, zoals al vermeld.

**Getest**: twee tests erbij, twee bestaande bijgesteld omdat ze het
oude advies vastlegden.

**Volledige testsuite**: 1622 tests, allemaal groen.

## v1.21.0 — Koeling: meetuitval en buitentemperatuur

**Gemeld**: de buitentemperatuur meewegen bij koelkast/diepvries, die in
een warme schuur staan.

**Groter probleem eronder**: de dagreeks van de diepvries wisselde tussen
0,8 W (13 dagen) en 90 W (12 dagen). Een dagGEMIDDELDE van 0,8 W betekent
dat de compressor die dag niet draaide - dat zijn dagen waarop de meter
niets doorgaf. De referentie (mediaan over alle dagen) belandde daardoor
op 19,68 W, precies tussen beide groepen, en meldde "+57,4% drift,
mogelijk defect" terwijl 40,8 W normaal is.

Uitvaldagen tellen nu niet mee; de referentie gaat naar 76,3 W.

**Temperatuurmarge**: per graad boven de referentietemperatuur mag het
verbruik 3% hoger liggen (vuistregel koeltechniek). Alleen naar boven -
koeler weer mag geen defect verbergen - en alleen voor apparaten die
koelen. Zonder vijf dagen temperatuurgeschiedenis gebeurt er niets.

**Getest**: nieuw `tests/test_cooling_drift_temperature.py`, 13 tests.

**Volledige testsuite**: 1635 tests, allemaal groen.

## v1.21.1 — Fabrieksgrenzen uit de handleiding

De handleiding bevestigt de correctie van v1.20.7 letterlijk: standaard
800 W, hoger vraagt een gecertificeerde elektricien en daarna een
verhoging via de app.

**Nieuw**: ook het LAADvermogen heeft ruimte - 2400 W/2600 W max volgens
de specificatie, tegen 2000 W ingesteld. Dat raakt de tekort-nachten:
bij dynamische prijzen tellen goedkope kwartierblokken, en sneller laden
vangt meer kilowattuur binnen hetzelfde blok. Dezelfde voorwaarde geldt.

**Grenzen vastgelegd in code**: net 2400 W, accu 2400/2600 W,
accuspanning 37,5-54,75 V, bedrijfstemperatuur -20 tot 60 °C, maximaal 6
modules. De teksten verwijzen ernaar in plaats van het getal te herhalen.

**Getest**: vier tests erbij in `test_expansion_advice.py`.

**Volledige testsuite**: 1639 tests, allemaal groen.

## v1.21.2 — Bewust begrensd vermogen wordt gerespecteerd

**Gemeld**: het laad- en ontlaadvermogen zijn handmatig begrensd op 2000
respectievelijk 1600 W.

Dat maakt het advies van v1.21.1 ongefundeerd: het zag alleen dat die
onder de fabrieksgrens van 2400 liggen en raadde aan ze te verhogen. De
redenen voor een lagere grens - de groep in de meterkast, cellen sparen,
geluid, marge - staan nergens in de meetgegevens.

**Nieuwe instelling** "Laad-/ontlaadvermogen bewust begrensd". Staat die
aan, dan verdwijnen beide suggesties en verandert het oordeel mee: het
vermogen knelt dan wel, maar dat is een keuze en geen gebrek. Het
capaciteitsadvies blijft overeind.

**Waarom een instelling en niet slimmer**: uit de data valt niet af te
leiden of een lagere grens een keuze is of een vergetelheid.

**Getest**: vijf tests erbij in `test_expansion_advice.py`.

**Volledige testsuite**: 1644 tests, allemaal groen.

## v1.21.3 — Een dag afronden op vijf metingen

De correctie van v1.21.0 werkt: de referentie van de diepvries staat nu
op 76,34 W in plaats van 19,68. Maar hij sloeg de andere kant op aan.

**Vijf metingen, en toch een oordeel**: 81,49 gedeeld door 5 is 16,3 W,
tegen een referentie van 76,34 - drift -98,8%, "mogelijk defect". Bij een
tick van vijf minuten is dat 25 minuten; de integratie was net herstart
en de compressor draaide in dat kwartier net niet.

De uitvalfilter uit v1.21.0 werkt op de GESCHIEDENIS; de dag die nog liep
werd zonder ondergrens meegewogen. Een dag wordt nu pas afgerond bij
minstens honderd metingen - ruim acht uur.

**Drie tests moesten mee**: ze rondden een dag af op één of twee
metingen. Er is nu een hulpfunctie die een volle dag simuleert.

**Getest**: drie tests erbij in `test_cooling_drift_temperature.py`.

**Volledige testsuite**: 1647 tests, allemaal groen.

## v1.21.4 — Zelfconsumptie: verkeerde grafiek en een stilstaande teller

**Gemeld**: klikken op de tegel "9,1% Zelfconsumptie" opende de grafiek
van de Zelfvoorziening (97,4%).

**Oorzaak**: zelfconsumptie stond als ATTRIBUUT op de
zelfvoorzieningssensor, dus de tegel verwees naar diezelfde entiteit - en
HA toont dan de geschiedenis van de hoofdwaarde. Er is nu een aparte
sensor "Zelfconsumptieratio"; het attribuut blijft bestaan.

**En het getal klopte ook niet**: `battery_discharge_today_kwh` stond op
0,0 terwijl de accu 's nachts wel had ontladen (zelfvoorziening 97,4%,
nachtverbruik 403 W). Teruglevering uit de accu telde daardoor als
zon-export: 12,7% in plaats van ~95%.

**Twee oorzaken in de werkstandherkenning**:
- Deelwoorden: "ontladen" bevat "laden", dus de uitkomst hing af van de
  toetsvolgorde. Nu exact vergelijken.
- Te korte lijst: een onbekende waarde gold als "niet ontladen" en zette
  de teller stil. Nu terugvallen op het vermogensteken, met een
  logboekregel. "Inactief" en "standby" blijven bekende waarden die
  "doet niets" betekenen.

**Getest**: vijf tests erbij in
`test_battery_state_and_self_consumption.py`.

**Volledige testsuite**: 1652 tests, allemaal groen.

## v1.21.5 — "Nachtverbruik" was het ontlaadvenster

**Gemeld**: een nachtverbruik van 400 W lijkt te hoog, alsof het een
uurwaarde is.

**Het getal klopt, de naam niet**: het is een vermogen (0,403 kW ->
403 W), maar gemeten over het ONTLAADVENSTER - vanaf het moment dat de
accu gaat leveren tot het goedkope laadblok. Dat is avond én nacht
samen. Het geleerde uurprofiel laat 's nachts 199-271 W zien en 's avonds
294-379 W; 403 W past bij een venster dat zwaarder op de avond leunt.

De sensor heet nu "Gemiddeld vermogen in het ontlaadvenster", de tegel
"Ontlaadvenster", met een toelichting die de avond noemt.

**Waarom dit ertoe doet**: het is de terugvalwaarde voor de
reserveberekening. Wie hem als "nachtverbruik" leest en te hoog vindt,
gaat zoeken naar een sluipverbruiker die er niet is.

**Onderweg**: het hernoemen brak twee tests - één omdat de entity_id niet
meeverandert (zoals bij `piekvermogen` in v1.6.4), en één omdat het
toelichtingsblok de eenheid buiten een zoekvenster van 600 tekens duwde,
precies zoals eerder bij de waterontharder. Die zoekactie is nu op de
volgende klasse verankerd.

**Getest**: drie tests erbij in `test_dashboard_entity_references.py`.

**Volledige testsuite**: 1655 tests, allemaal groen.

## v1.22.0 — Zonopvang uitstellen naar een goedkoper uur

**Gevraagd**: of de accu niet beter later kon laden, zodat de dure
ochtendzon wordt teruggeleverd in plaats van opgeslagen.

**Eerst zat de analyse ernaast**: de eerste simulatie telde alleen
importkosten en vergat de teruglever-opbrengst - precies waar de
arbitrage zit. Met opbrengst erbij, op de werkelijke dag van 10 augustus:
altijd smart 1,657 EUR, omslag 11:00 1,884 EUR, omslag 13:00 2,152 EUR.

**Het mechanisme**: de accu neemt een vast aantal kWh op; WELKE dat zijn
bepaalt welke je exporteert. Vroeg laden slurpt de dure ochtendzon op
(26,8 ct) en laat de goedkope middagzon over voor het net (13,6 ct).

**De deadline is het vangnet**: er wordt gerekend tot 16:00, niet tot
zonsondergang, plus 25% extra overschot. Daardoor is de late middagzon
marge in plaats van onderdeel van het plan. Bij omslag 15:00 levert het
nog 0,40 EUR op maar eindigt de accu op 6,13 in plaats van 7,30 kWh - het
optimum ligt vlak vóór die klif.

**Vier remmen**: te weinig zon, minder dan 5 ct prijsverschil, accu onder
25%, of na 16:00. Elke weigering noemt zijn reden.

**Getest**: nieuw `tests/test_solar_capture_deferral.py`, 12 tests.

**Volledige testsuite**: 1667 tests, allemaal groen.

## v1.22.1 — Kwartierprijzen ontbraken in de export

**Gevraagd**: zijn de kwartierprijzen van Zonneplan niet al bekend?

Ja, en de integratie gebruikt ze - maar de export toonde alleen
`upcoming_transitions`: samengevoegde blokken per modus met een min- en
maxprijs. Voor 11 augustus waren dat drie regels, waarvan één negen uur
samenvatte als "0,1267 - 0,3505".

Daarmee valt niet na te gaan WANNEER de prijs hoog is - precies waar het
uitstelplan uit v1.22.0 op stuurt. Voor de uurtabel moest daardoor het
prijsverloop van de vorige dag als benadering dienen.

**Nu**: `price_forecast_quarters` met elk blok (start, eind, prijs),
afgeschermd zoals de rest - zonder prijssensor gooit de onderliggende
functie een KeyError, en dat mag het hele bestand niet meeslepen.

**Getest**: drie tests erbij in `test_diagnostics_completeness.py`.

**Volledige testsuite**: 1670 tests, allemaal groen.

## v1.22.2 — Kwartierplanning op het dashboard

**Gemeld**: de voorbeeldtabel miste de manual-verkoop tegen dure
prijzen, en er is behoefte aan een kwartierplanning met SoC op het
dashboard.

**De tabel was onvolledig**: die simuleerde alleen `smart` en
`smart_discharging`. De manual-verkoop ontbrak, terwijl dat juist de
stand is die geld oplevert. De regel zelf zit al langer in de code:
verkopen mag alleen als de accu die dag NIET van het net is geladen.

**Nieuwe pagina "Kwartierplanning"**: per kwartier tijd, prijs, verwachte
zon, verwacht verbruik, modus en SoC in procenten. Alle vier de modi,
inclusief het uitstelplan uit v1.22.0. Getoetst: 22 verkoopkwartieren bij
een zonnegeladen accu, nul bij een netgeladen accu.

**Eén eigen test was fout**: die toetste dat een lege accu niet verkoopt,
maar die vult zich tussendoor met zon en mag dán wél verkopen. De code
had gelijk; er staat nu ook een test op het omgekeerde geval.

**Getest**: nieuw `tests/test_quarter_plan.py`, 13 tests.

**Volledige testsuite**: 1683 tests, allemaal groen.

## v1.23.0 — De woning gaat voor verkopen

**Gevraagd**: actief toetsen of verkopen mogelijk is, en in de winter
alleen laden, bijladen en de eigen woning voeden.

**Wat een winterdag liet zien** (5 kWh zon, 7,4 kWh verbruik): de accu
verkocht 's ochtends tot nul en stond daarna drie uur leeg terwijl het
huis 25-33 ct per kWh uit het net betaalde.

**De reserve deed wél zijn werk** - die bewaarde 1,20 kWh voor de vier
uur tot het goedkope blok. Het probleem was de snelheid: verkopen gaat op
1600 W terwijl het huis 300 W trekt. Binnen een uur stond de accu op de
bodem. De toets was passief ("blijft er genoeg over?") in plaats van
actief.

**Twee remmen**: onder 5 kWh verwachte dagopbrengst wordt er niet
verkocht, ook niet met een volle accu. Anders moet er na de verkoop
genoeg overblijven om het huis te voeden tot het goedkope blok, met
anderhalf keer marge; zon die daarvóór nog komt telt mee.

**Niet blokkeren bij ontbrekende gegevens**: zonder Solcast-sensor of
zonder accusensor blijft het beproefde gedrag met de bestaande reserve
gelden.

**Getest**: nieuw `tests/test_sell_only_when_possible.py`, 10 tests.

**Volledige testsuite**: 1693 tests, allemaal groen.

## v1.23.1 — Kwartierplanning volledig te bewaken

**Gevraagd**: verwachte PV, verwachte winst en meer in het overzicht van
de kwartierplanning, om het mechanisme te kunnen bewaken zolang er weinig
data is.

**Samenvatting boven de tabel**: verwachte zon, verbruik, teruglevering,
import, verwachte opbrengst, opbrengst uit verkoop met aantal
verkoopkwartieren, laagste/hoogste/eind-SoC, kwartieren in het goedkope
blok en de verdeling over de modi.

De laagste SoC is daarbij het belangrijkste signaal: zakt de accu volgens
het plan te diep, dan is het te gretig.

**Drie kolommen erbij in de tabel**: Net (negatief bij teruglevering),
opbrengst per kwartier en een lopend totaal. Een test bewaakt dat het
cumulatief de som van de losse kwartieren is.

**Onderweg**: een eigen test pakte de verkeerde kaart omdat er nu drie
markdown-kaarten op die pagina staan; die zoekt nu op de tabellus.

**Getest**: zeven tests erbij in `test_quarter_plan.py`.

**Volledige testsuite**: 1701 tests, allemaal groen.

## v1.23.2 — Vooruitkijken en wijzigingen markeren

**Gevraagd**: maximaal 36 regels vooruit, voorbije kwartieren weg, en
gewijzigde kwartieren rood.

**Rood bij een wijziging**: de integratie onthoudt wat er als eerste voor
elk kwartier werd voorspeld. Verandert de modus later, dan kleurt die
regel rood met "was ..." erbij. De samenvatting telt de wijzigingen -
veel wijzigingen betekent dat de planning onrustig is.

Getoetst: eerste plan nul wijzigingen; na de accu op 0,3 kWh te zetten
sprongen zes kwartieren van manual naar smart, allemaal gemarkeerd.

**Negen uur vooruit** (36 regels), voorbije kwartieren verdwijnen.

**Eigen pagina voor de samenvatting**: met alle kolommen liep de
kwartierpagina over de leesbaarheidsgrens. De tabel ging van negen naar
zes kolommen - een bestaande test sloeg terecht aan dat negen niet op een
smal scherm past.

**Onderweg**: de eerste poging overschreef de kolommen van v1.23.1 in
plaats van ze aan te vullen; de rij is daarna opnieuw opgebouwd.

**Getest**: zeven tests erbij in `test_quarter_plan.py`.

**Volledige testsuite**: 1708 tests, allemaal groen.

## v1.23.3 — De minimum-SoC stond verkeerd

**Gemeld**: de laagste SoC kan nooit 0% zijn; de accu heeft één harde
begrenzing van 10%.

**0,43 kWh die niet bestond**: de configuratie stond op 15% terwijl de
accu op 10% staat - bruikbaar 7,31 in plaats van 7,74 kWh. Dat verschil
zat in elke berekening: de reserve hield te veel achter, het
uitbreidingsadvies zag een kleinere accu, de SoC-percentages klopten
niet, en tekort-nachten werden eerder gemeld dan nodig.

**De omvormer wist het zelf**: `number.solarflow_2400_ac_min_soc` stond
al geconfigureerd maar werd op één plek gebruikt, terwijl het handmatige
getal vijf berekeningen bepaalde. Nu gaat de gemeten waarde voor, met het
ingestelde getal als terugval. Een onwaarschijnlijke meting wordt
genegeerd.

**0% is nu een waarschuwing**: de planning liet de accu tot nul zakken
zonder dat te melden, terwijl dat betekent dat het huis volledig aan het
net hangt. Zulke kwartieren krijgen een "!" en worden geteld onder
"Kwartieren met tekort".

**Getest**: nieuw `tests/test_effective_min_soc.py`, 8 tests.

**Volledige testsuite**: 1716 tests, allemaal groen.

## v1.23.4 — Meldingen bij planningswijzigingen

**Gevraagd**: de diagnostiek bijwerken voor alle recente wijzigingen, en
berichten op de telefoon bij belangrijke planningswijzigingen - los uit
te schakelen.

**Twee gaten in de export gedicht**: de werkelijke minimum-SoC en de
eerste voorspelling per kwartier. Zonder die twee is niet na te gaan
waarom een SoC-percentage is wat het is, of waarom een kwartier als
gewijzigd geldt.

**Drie meldingen**: "Accu haalt de nacht mogelijk niet" (standaard aan,
demping 60 min), "Zon opvangen uitgesteld" (uit, 30 min) en "Verkopen
geblokkeerd voor de woning" (uit, 120 min). Elk met een eigen schakelaar
op de Meldingen-pagina.

Alleen de eerste staat standaard aan, om dezelfde reden als de
vakantiemelding: die vuurt alleen als er werkelijk iets misgaat.

**Alleen bij een overgang**, niet elke tick - getoetst: eerste keer één
melding, tweede keer nul. De melding noemt de cijfers zelf, want zonder
cijfers dwingt hij tot doorklikken.

**Afgeschermd**: het versturen zit in een try - een melding mag de
aansturing nooit laten vallen.

**Getest**: nieuw `tests/test_plan_notifications.py`, 9 tests.

**Volledige testsuite**: 1725 tests, allemaal groen.

## v1.24.0 — Meldingen in het Achterhoeks

**Gevraagd**: met één schakelaar alles in het Achterhoeks, ook de
meldingen op de telefoon.

**Alleen de meldingen**: de hele integratie vertalen zou ~1.664 losse
teksten in de code raken plus ruim 3.000 dashboardlabels. Alleen de
meldingen is een fractie daarvan en levert het leukste deel op - de
telefoon spreekt Achterhoeks, het dashboard blijft leesbaar.

26 titels en 60 woordvervangingen in één tabel in const.py.

**Twee fouten die het proberen opleverde**: "goedkope blok" werd
"goodkope blok" omdat "goed" -> "good" over het al vervangen woord heen
liep (nu in één doorgang met markeringen), en "niets" werd "nwat" omdat
"iets" -> "wat" erin toesloeg (volgorde: langere woorden eerst).

**De schakelaar** staat bovenaan de Meldingen-pagina, standaard uit, en
overleeft een herstart. De vertaling zit in de gedeelde verzendfunctie,
dus telefoon én meldingenoverzicht spreken dezelfde taal.

**Eerlijk erbij**: een benadering, geen gecontroleerde streektaal.

**Getest**: nieuw `tests/test_achterhoeks.py`, 12 tests. De test op
"elke meldingsoort heeft een titel" ving er meteen één die vergeten was.

**Volledige testsuite**: 1737 tests, allemaal groen.

## v1.24.1 — "Nog geen planning" bij een volle accu

**Gemeld**: de Planning-samenvatting toonde "Nog geen planning" en "Ja.
Accustand onbekend" terwijl de accu 7,69 kWh had.

**Het verkeerde veld**: de nieuwe functies lazen `last_available_kwh`,
dat alleen wordt gezet als de HELE energie-check slaagt en op een tak
zonder verbruiksschatting expliciet op None wordt gezet. Een bijproduct
dus, geen betrouwbare accustand. Er is nu één functie die de sensor
rechtstreeks leest, met dat bijproduct als terugval; kwartierplanning,
verkooptoets en uitstelplan gebruiken die.

**Twee teksten die niets zeiden**: "Ja. Accustand onbekend" las
tegenstrijdig, en "Nog geen planning" liet zoeken naar iets wat kapot
leek. Beide zeggen nu wat er aan de hand is.

**Dezelfde valkuil als in v1.22.1**: `_get_forecast_entries` gooit een
KeyError zonder prijssensor. Dat brak bij de export al eens en nu bij de
planning; beide zijn afgeschermd.

**Getest**: vier tests erbij in `test_quarter_plan.py`.

**Volledige testsuite**: 1741 tests, allemaal groen.

## v1.24.2 — Vijftien miljoen euro en een zonarme zomerdag

Twee fouten uit één screenshot.

**"Verwachte opbrengst 15124941.79 EUR"**: `_get_forecast_entries` geeft
de rauwe waarde terug (3181681), niet euro's. Elders wordt die door
PRICE_SCALE_FACTOR (10.000.000) gedeeld; in de nieuwe planning gebeurde
dat niet. De deling ontbrak op drie plekken - kwartierplanning, uurprijs
voor het uitstelplan, en de grens van het goedkope blok. Dat laatste
verklaart ook "0 kwartieren in goedkoop blok". Na de correctie: 2,81 EUR.

**"Zonarme dag (0.1 kWh verwacht)" om 20:23**:
`_estimate_pv_kwh_for_period` kijkt alleen vooruit, dus 's avonds bleef
er 0,1 kWh over terwijl er die dag ruim 20 kWh was opgewekt. Nu telt de
hele dag: al opgewekt plus nog te komen, met de ochtendvoorspelling als
terugval zonder dagmeter. De winterregel blijft intact.

**Wat dit zegt**: beide fouten kwamen door de tests omdat de
testopstellingen prijzen in euro's meegaven terwijl de sensor rauwe
eenheden levert - dezelfde valkuil als in v1.19.5. De tests gebruiken nu
PRICE_SCALE_FACTOR.

**Getest**: vijf tests erbij.

**Volledige testsuite**: 1746 tests, allemaal groen.

## v1.24.3 — SoC 0% bij een ondergrens van 10%

**Gemeld**: "SoC laagste / hoogste 0% / 86%" terwijl de accu een harde
ondergrens van 10% heeft.

Klopt: er werd het percentage van de BRUIKBARE capaciteit getoond, niet
de echte accustand. "0%" betekende 10% - de accu is dan leeg voor
gebruik, maar niet leeg. Dat leest als iets onmogelijks en komt niet
overeen met wat de Zendure-app toont.

**Nu allebei**: de tabel en samenvatting tonen de echte accustand, die
nooit onder de ondergrens zakt, plus "Waarvan bruikbaar, laagste" - 0%
daar is het signaal dat de accu niets meer levert.

Getoetst met een avond zonder zon: 20:00 82%/80%, 23:00 26%/18%, 02:00
10%/0%.

**Getest**: vier tests erbij in `test_quarter_plan.py`.

**Volledige testsuite**: 1750 tests, allemaal groen.

## v1.25.0 — Zoveel kwartieren als er prijzen zijn

**Gemeld**: "De kwartierplanning toont niet de maximale aantal
kwartieren vooruit (waarin zonneplan prijzen beschikbaar zijn)."

Klopt. De vraag in v1.23.2 was "zoveel prijzen er zijn, dus
waarschijnlijk max. 36 regels" - ik las de schatting als de eis en zette
er een harde grens van 36 op. Die schatting was te laag: Zonneplan
publiceert de prijzen van morgen in de loop van de middag. In de export
van 10 augustus 20:54 stonden **109 toekomstige kwartieren** (27 uur)
klaar terwijl de tabel er 36 toonde.

**Nu**: de tabel loopt zover als er prijzen zijn. De grens van 192
(twee etmalen) is alleen nog een fysiek plafond, geen keuze.

**Dagaanduiding erbij**: boven een etmaal komt elk tijdstip twee keer
voor. Vandaag krijgt geen merk - dat leest rustiger - morgen en
overmorgen wel.

**Wat er ook uit kwam**: de GACS-sensor draagt de tekst voor een stuk of
tien dashboardpagina's en zat met 36 planregels al op **ruim 21 kB**,
waarvan 12 kB planning. Home Assistant slaat de attributen van een
toestand **boven 16 kB niet meer op** - die stonden er dus al niet in,
zonder dat iemand dat merkte. Met 109 regels was het richting 37 kB
gegaan.

Twee dingen daaraan gedaan:

- Het dashboard krijgt een **compacte planning**: de tien velden die de
  tabel toont in plaats van alle vijftien. Dat scheelt bijna de helft.
  De samenvatting en de diagnostiek-export blijven de volle regels
  gebruiken.
- De grote attributen staan nu in `_unrecorded_attributes`, zodat de
  recorder ze overslaat. Er verdwijnt niets: de kaarten lezen de huidige
  toestand, niet de geschiedenis.

**Getest**: zeven tests erbij, in `test_quarter_plan.py` en
`test_attribute_isolation.py`.

**Volledige testsuite**: 1757 tests, allemaal groen.

## v1.26.0 — Tijdlijn van aanwezigheid

**Gevraagd**: "Tevens in dit overzicht een 'time table' Thuis, weg
slapen of iets dergelijks zodat ik achteraf kan controleren of het
klopt."

Het weekprofiel zegt wat er *gemiddeld* gebeurt (33% van de tijd iemand
thuis). Om te controleren of de afleiding klopt, heb je het verloop zelf
nodig.

**Twee tabellen op een eigen pagina** *Aanwezigheid-tijdlijn*:

- **Uren per dag** — thuis, weg en slapend per dag. Blokken over
  middernacht worden gesplitst, anders schrijft een nacht slapen zeven
  uur op de verkeerde dag.
- **Tijdlijn** — dag, van, tot, staat, duur en **waarom**. Die laatste
  kolom is waar de controle mee begint: "weg om 14:20" zegt niets, "weg,
  45 min na de laatste beweging (Aanwezigheid woonkamer)" wel.

**Alleen overgangen worden vastgelegd**, niet elke tick — anders staan
er 288 regels per dag die allemaal hetzelfde zeggen. Blokjes korter dan
vijf minuten tussen twee gelijke staten worden samengevoegd: één
beweging midden in de nacht zou anders "slaapt — thuis — slaapt"
opleveren.

De tijdlijn wordt **bewaard over een herstart** heen. Een tabel die elke
keer leeg begint valt niet achteraf te controleren, en dat was de vraag.

**Eigen pagina, net als in v1.23.2**: met beide tabellen erbij liep de
aanwezigheidspagina op 3628 tekens, ruim over de grens van 2500. De
bestaande test sloeg daar terecht op aan.

Het dashboard toont 30 overgangen; de volledige tijdlijn (120) staat in
de diagnostiek-export.

**Getest**: tien tests erbij in `test_presence_detection.py`.

**Volledige testsuite**: 1767 tests, allemaal groen.

## v1.27.0 — De zonschatting stond verkeerd geijkt

**Gemeld** met een screenshot van de kwartierplanning: "Hier gaat wat
mis de accu kan niet in 1 uur vol zijn. Vermogen zonnepanelen is W en
niet kWh dus hier gaat iets niet goed."

De eenheid klopte; de **ijking** niet — en de conclusie was terecht.

### De oorzaak

De live correctie deelt de Solcast-teller *"rest van vandaag"* door onze
eigen optelling voor de rest van vandaag. Die deling geldt alleen vanaf
**nu**: de teller telt af vanaf het huidige moment.

Hij werd geijkt op het **begin van de periode die geschat werd**. Voor
een kwartier van later vanmiddag krimpt de noemer terwijl de teller
blijft staan. Uit de gemelde tabel na te rekenen:

| Kwartier | Getoond | Ruwe voorspelling | Factor |
|---|---|---|---|
| 13:00 | 1,227 | 0,743 | 1,65× |
| 15:00 | 1,795 | 0,645 | 2,78× |
| 16:30 | 2,641 | 0,517 | 5,11× |
| 17:30 | 3,512 | 0,396 | **8,87×** |

Alle vier de keren komt de impliciete teller uit op **23,0 kWh** — de
dagvoorspelling. Gevolg: 3,5 kWh in een kwartier, oftewel 14 kW uit een
installatie die op 2,9 kW piekt.

**Deze fout raakte élke schatting vooruit**, dus ook de reserve, de
energiebrug en de verkooptoets: die lazen structureel te veel zon.

### Tweede fout in dezelfde tabel

De simulatie kende de **vermogensgrenzen** niet. Laden staat bewust
handmatig op 2000 W, dus er kan hooguit 0,5 kWh per kwartier in — de
tabel liet 1,7 kWh per kwartier zien en een accu die in een uur van 10%
naar 100% ging. Zon die er niet in kan, wordt nu als teruglevering
geboekt. Ontladen is begrensd op 1600 W.

### En de verkooptoets, die hier al open stond

Rem 2 rekende met de **nettosom** tot het goedkope blok — verbruik min
zon over de hele periode. Daarmee werd de zon van *morgenochtend*
afgetrokken van het verbruik van *vannacht*: 1,77 kWh nodig, terwijl het
diepste moment onderweg 5,23 kWh vroeg. Nu dezelfde wandeling als de
energiebrug, met marge **1,15×** in plaats van 1,5× (die factor
compenseerde een basis die structureel te laag was).

De planning past die reserve nu ook toe, per uur berekend. Een planning
die iets anders belooft dan de aansturing doet, is erger dan geen
planning.

**Getest**: vijftien tests erbij. Op de oude code vallen vijf van de zes
ijkingstests en vier van de vermogenstests om.

**Volledige testsuite**: 1782 tests, allemaal groen.

## v1.28.0 — Uitstellen op prijs en zon, en de diagnostiek weer als JSON

**Gevraagd**: "Ik wil alleen dat op basis van prijs en verwachte PV
opbrengst de modus later naar smart gaat, en dus (met de data van
vandaag als voorbeeld) de accu pas rond 11 uur naar smart gaat."

### De accustand was een verborgen rem

Er stond een ondergrens van 25% op het uitstelplan. Die werd gemeten als
percentage van de **bruikbare** capaciteit, terwijl de accustand die je
ziet de **echte** is — dezelfde verwarring als in v1.24.3. 25% echt is
16,7% bruikbaar, dus de rem sloeg pas los boven 32,5% echt.

Op 11 augustus 07:45 stond de accu op 25% en gaf het plan: *"Accu op 17%
— vullen gaat nu voor optimaliseren."* Terwijl er 23 kWh zon aankwam en
het prijsverschil 18 ct was.

De rem is **weg**, niet omgerekend. Een lege accu betekent alleen dat er
méér ruimte te vullen is, en dat zit al in de marge: het overschot moet
1,25× de ruimte zijn, dus hoe leger de accu hoe strenger die eis vanzelf
wordt.

Nagerekend op de gegevens van vandaag:

| Tijd | Prijs | SoC | Besluit |
|---|---|---|---|
| 08:00 | 33,3 ct | 25% | uitstellen |
| 09:00 | 30,5 ct | 21% | uitstellen |
| 10:00 | 24,9 ct | 18% | uitstellen |
| **11:00** | 16,4 ct | 13% | **smart** (verschil nog 3,4 ct) |

### Een latente fout die hierdoor bovenkwam

`_estimate_consumption_kwh_for_period` kan `None` geven. Zolang de
accustand-rem er nog voor stond, sprong de functie er bij een lege accu
al uit; zonder die rem liep de hele beslistick stuk op *"unsupported
operand -: float and NoneType"*. Valkuil 4 uit de overdracht, opnieuw.

### De diagnostiek was weer een txt

**Gemeld**: "Tevens is de diagnostiek weer een txt i.p.v. json."

Twee fouten in één regel. `datetime.now()` geeft een tijd **zonder
tijdzone**, terwijl alles binnen de integratie er wel een heeft. Draait
er net een vaatwasser of wasmachine, dan rekent het verhaal `nu −
starttijd` uit en gooit Python *"can't subtract offset-naive and
offset-aware datetimes"*. En die aanroep stond als enige **niet** in
`_veilig`, dus die fout sloopte de hele export: Home Assistant geeft dan
een foutpagina terug en de browser bewaart die als .txt.

Dat het maar sóms gebeurde past bij de oorzaak: alleen als er net een
apparaat draaide. De vaatwasser draait hier meestal tussen 13 en 15 uur.

Precies zoals v1.19.3, alleen bleven deze twee regels toen staan. Nu
zitten álle aanroepen erin, ook `learning_health`,
`persisted_state_snapshot`, `pv_forecast_raw` en `system_scan`.

**Volledige testsuite**: 1785 tests, allemaal groen.

## v1.29.0 — Een falend onderdeel meldt zichzelf

**Gemeld**: "Dat er een txt wordt gemaakt is een error, ik had daar
graag een melding van verwacht zoals eerder afgesproken."

Terecht, en dit is de tweede keer. In **v1.19.4** was de vraag *"ik had
nu ook ergens een melding verwacht dat het systeem niet correct
functioneert"*, en toen heb ik er een **aandachtspunt** van gemaakt: een
regel op een dashboardpagina waar je naartoe moet klikken. Dat is geen
melding. Het argument van toen — afschermen zonder melden laat een
storing stil doorlopen — geldt net zo goed voor die halve oplossing.

**Nieuw**: melding *"Onderdeel van de integratie faalt"*, standaard
**aan**, demping 60 minuten, eigen schakelaar op de Meldingen-pagina en
een Achterhoekse titel. Het bericht noemt wélk onderdeel en wélke fout —
"er is iets stuk" zonder te zeggen wát kost meer tijd dan het bespaart.

Drie dingen die daarvoor nodig waren:

- **De diagnostiek-export registreert nu zijn fouten.** `_veilig` ving
  ze al op, maar zette alleen een `{"fout": ...}` in het bestand. Wie de
  export niet regel voor regel leest, merkte er niets van.
- **Fouten worden ook weer opgeruimd** zodra een onderdeel het weer doet.
  Zonder dat blijft een fout van weken geleden voor altijd staan en gaat
  de herstelmelding nooit af.
- **Herstelmelding**: *"✅ Alle onderdelen rekenen weer."*

### En de valkuil die daaronder lag

`_get_forecast_entries` gooide een `KeyError` zodra de prijssensor niet
was ingesteld — dezelfde fout die als terugkerende valkuil in de
overdracht staat. Die sloopte de hele meldingenronde. Nu structureel weg:
geen sensor is gewoon geen prijzen.

**Volledige testsuite**: 1792 tests, allemaal groen.

## v1.30.0 — De nacht is geen afwezigheid, en niets gaat meer verloren

**Gemeld**: "Ik ging om 23:15 slapen, was snachts wel een tijdje wakker"
— en de tijdlijn gaf van 23:15 tot de ochtend **weg**, met "laatst: Gang
Beweging" als reden. Plus: "Let op alle gecreeerde data dient na een
herstart niet verloren te gaan."

Die twee horen bij elkaar.

### Wat er niet bewaard werd

`last_bedtime_motion_at` en `last_motion_at` stonden **niet** in de
opslag. De slaapherkenning vraagt of de slaapsensor de *laatste*
beweging was; na een herstart was dat veld leeg en kon die vraag niet
meer beantwoord worden. Wie al in bed ligt, loopt niet opnieuw langs die
sensor — dus bleef het de hele nacht "weg".

Ook toegevoegd: `presence_state` zelf, en
`quarter_plan_first_seen` (waarmee de rode "was …"-markering wordt
bepaald; die begon na elke herstart opnieuw).

### De nacht als eigen regel

`_slaapt_waarschijnlijk` kijkt alleen naar de volgorde van de sensoren.
Loop je via de gang naar bed, dan is de gang de laatste en valt de hele
nacht als afwezigheid uit de bus.

Nieuw: tussen **22:00 en 07:00** geldt stilte als slapen — *mits* er net
nog iemand thuis was. Een huis loopt 's nachts niet vanzelf leeg; kwam de
staat van "weg", dan blijft het "weg". Het is bovendien de veilige
aanname: bij slapen blijft de nachtreserve staan.

### Vijf "weg"-regels achter elkaar

Een tijdlijn van blokken hoort **nooit** twee gelijke staten naast
elkaar te hebben. Dat kwam er vooral door de ontbrekende opslag: elke
herstart begon op "onbekend" en schreef een nieuwe regel zonder dat er
iets veranderd was. Die oorzaak is weg, en de tabel kan er nu sowieso
tegen: gelijke staten worden samengevoegd, en een ontbrekende meting
onderbreekt het lopende blok niet meer.

**Volledige testsuite**: 1798 tests, allemaal groen.

## v1.31.0 — Plantoetsing, en de opnamegrens in het uitstelplan

### De 25% buffer werkte niet zoals bedoeld

**Gemeld**: "ik het echter 25% buffer = 1 uur gevraagd, mijn inziens zou
het systeem dan om 11 uur naar smart gaan."

Klopt, en de oorzaak is dat het uitstelplan alleen naar **energie** keek.
Vanaf 12:00 komt er tot 16:00 nog 9,66 kWh overschot — meer dan de 8,06
die met marge nodig is — maar de accu neemt hooguit 2000 W op, dus in
vier uur past er 8,0 kWh in. Precies te weinig, en dat zag het plan niet.

Met de opnamegrens erbij valt 12:00 af en wordt het **11:00**: vijf uur ×
2 kW = 10 kWh. Dezelfde grens die v1.27.0 al in de kwartierplanning
zette; die hoorde hier ook te staan.

Nagerekend op de gegevens van 11 augustus:

| Tijd | SoC | Besluit |
|---|---|---|
| 08:00 | 25% | uitstellen |
| 10:00 | 18% | uitstellen |
| **11:00** | 13% | **smart** |

### Plantoetsing (stap 1 van het leren)

**Gevraagd**: "Kun je de diagnostiek zo maken, dat je leert van het accu
gedrag en morgen verder optimaliseert indien noodzakelijk?"

Hiervan is dit **stap één: meten**. Zonder meting is bijsturen blind, en
valt niet te controleren of een aanpassing hielp. De aanleiding staat in
dezelfde week: de zonschatting stond verkeerd geijkt zonder dat iets
aansloeg.

Elke ochtend om 08:00 wordt het plan vastgelegd: verwachte opbrengst,
zon, import, laagste SoC, tekortkwartieren. Na middernacht komt daar de
werkelijkheid naast, met een oordeel per dag:

> *"Afwijking: zon −35% (minder dan gedacht), accu zakte naar 5% terwijl
> 20% was voorspeld."*

Dertig dagen worden bewaard, met een mediaan per grootheid en een
duiding zodra er vijf dagen zijn. Eigen pagina *Plantoetsing*; de
volledige geschiedenis staat in de diagnostiek-export.

**Er wordt bewust niets bijgestuurd.** Dat is stap twee en een aparte
beslissing. Een test bewaakt dat.

**Volledige testsuite**: 1812 tests, allemaal groen.

## v1.31.1 — Twee vondsten uit de export van 11 augustus 08:36

### De accustand was "onbekend" terwijl de accu 22% aangaf

`last_soc_percent` stond op **None** terwijl alle drie de modules netjes
rapporteerden. Dat veld wordt alléén gezet in de berekening van het
ontlaadvermogen, en die tak wordt niet bereikt zodra de tick eerder
eindigt — bij `solar_capture_deferred` gebeurt dat **elke ochtend die
met uitstellen begint**.

Dezelfde vorm als `beschikbare_energie_kwh` in v1.24.1: een bijproduct
van een berekening is geen accustand. Nieuw: `accustand_procent()`, dat
de sensor rechtstreeks leest met het oude veld en de beschikbare energie
als terugval.

Dit raakte de plantoetsing van v1.31.0 meteen: die hield de laagste
stand van de dag bij via het lege veld, dus juist op de dagen dat de
accu het diepst zakt was er niets gemeten. Ook de dagsamenvatting en
twee meldingen lazen hem.

### De tijdlijn liep uit de pas met de werkelijkheid

De tabel stond op "weg sinds 08:21" terwijl de staat "thuis" was en er
2,6 minuten eerder nog beweging was. Zolang alleen een **wissel** werd
vastgelegd, was elke gemiste wissel blijvend — er kwam nooit meer een
gelegenheid om hem goed te zetten.

De staat wordt nu elke tick aangeboden; gelijke staten worden toch al
samengevoegd (v1.30.0), dus dit levert geen extra regels op en de tabel
herstelt zichzelf.

**Volledige testsuite**: 1816 tests, allemaal groen.

## v1.32.0 — Rendement per halve slag

**Gemeten reeks in de export van 11 augustus**: 95,5 – 76,9 – 74,2 –
82,9 – 83,2 – 97,6 – **56,4**%. Mediaan 82,9, terwijl er zelf 90,8% was
gemeten. Veertig procentpunt spreiding betekent niet dat de accu
wisselt, maar dat er iets anders gemeten werd dan rendement.

### Waarom het zwabberde

De formule was `(ontladen + verschil in voorraad) / geladen`. Die klopt
alleen als het venster op een **hele slag** eindigt. Maar het venster
sloot zodra er 1 kWh geladen was — dus midden in een lading, midden in
een ontlading, waar het toevallig uitkwam. Halverwege het laden meet je
zo de laadkant, halverwege het ontladen iets daartussenin.

### Wat er nu gebeurt

**Gevraagd**: "volgens mij is het simpel te berekenen middels laad en
ontlaad vermogen en beschikbaar vermogen." Klopt — mits je de twee
kanten apart houdt:

    laadrendement    = toename voorraad / wat erin ging
    ontlaadrendement = wat eruit kwam / afname voorraad
    heen en terug    = laadrendement × ontlaadrendement

Een stuk loopt zolang de accu dezelfde kant op gaat en wordt afgesloten
zodra hij omdraait. Vier grendels: minstens **1,5 kWh** per stuk (de
voorraadsensor meldt in stappen van 1% = 0,086 kWh, daaronder meet je
afronding), geen gat groter dan 20 minuten, stilstand onder 50 W telt
niet mee, en per kant moet de uitkomst tussen 70 en 100% liggen.

De grens ligt bij de **vorige** meting, niet bij de huidige: op de tick
waarop de accu omdraait is de voorraad al een stap de nieuwe kant op
gegaan terwijl dat vermogen nog nergens is geteld. In de testopstelling
zakte 80% daardoor naar 68,6% en werd de meting als onmogelijk
weggegooid.

De oude methode blijft als terugval tot er per kant drie metingen zijn,
zodat een verse installatie niet zonder waarde komt te zitten.

**Kanttekening**: dit meet wat `sensor.zendure_batterij_vermogen` ziet.
Meet die aan de accuzijde, dan blijft het omvormerverlies buiten beeld
en valt de uitkomst hoger uit dan wat er aan de meterkast te merken is.
Dat is nu zichtbaar doordat beide kanten apart op het dashboard staan.

**Volledige testsuite**: 1823 tests, allemaal groen.

## v1.33.0 — Achterhoeks nagelopen tegen een woordenboek

**Gevraagd**: "Helpt dit nog wat voor de achterhoekse vertaling?" — met
een verwijzing naar het dialectwoordenboek van mijnwoordenboek.nl (1326
woorden, door bezoekers aangedragen).

Ja. En er zat meteen een fout in.

### "mangs" betekent niet "mogelijk"

Het betekent **soms**, alvast of binnenkort. De melding *"Den accu haalt
de nacht mangs neet"* zei dus niet "misschien niet" maar "soms niet" —
en juist die melding staat standaard aan. Nu **meugelijk**; "mangs"
staat er nog wel, maar dan voor "soms".

### Verder nagelopen

- **gaan** → *goan* (stond op "goat", dat is de wij-vorm)
- **moeten** → *motten* (stond op "mot", dat is enkelvoud)
- **bijna** → *bi'jnoa* (stond op "hoast", dat is Twents/Fries)
- **even** → *efkes*
- **daarna** → *daornao*
- **teruggeleverd** → *truggelevert* (terug is *trugge*, met dubbele g)
- **hangt** → *hunk*

### Woorden erbij die in de meldingen voorkomen

vandaag → *vandage*, tijd → *tied*, water → *waoter*, klaar → *kloar*,
nodig → *neudig*, genoeg → *genög*, koud → *kold*, warm → *heit*, werk →
*wark*, meteen → *dreks*, verder → *wieter*, vaak → *duk*, en de kleine
woorden voor, maar, naar, over, daar, terwijl.

Het blijft een benadering, geen gecontroleerde streektaal — het
woordenboek is zelf ook door bezoekers gevuld en geeft per woord vaak
meerdere vormen. Alles staat nog steeds in één tabel in `const.py`.

**Volledige testsuite**: 1826 tests, allemaal groen.

## v1.34.0 — Eén tegel per onderwerp

**Gemeld**: "Er zijn nu 2 plannings tegels aanwezig op de
landingspagina, kan dit samen gevoegd worden?"

Het waren er zelfs **vier**: Planning, Kwartierplanning,
Planning-samenvatting en Plantoetsing. Elke keer dat een pagina werd
gesplitst omdat de tekengrens van 2500 werd gehaald, kwam er ook een
tegel bij. Dat is een indeling die volgt uit een technische grens, niet
uit onderwerpen.

**Nu**: één tegel *Planning*, met de drie doorverwijzingen als links
onderaan de pagina zelf. Hetzelfde voor *Aanwezigheid* en de tijdlijn.

### Drie tegels die de verkeerde pagina openden

Onder "Meer bekijken" stonden *Systeem*, *Financieel*, *Verloop* en
*Kwaliteit* — en alle vier wezen ze naar `detail-verloop`. Drie ervan
beloofden dus iets anders dan ze gaven. Ook stonden *PV / zon* en
*Apparaten* er dubbel in, één keer per sectie.

Zeventien tegels teruggebracht naar acht, elk naar een eigen pagina.

Twee tests erbij die dit vasthouden: geen twee tegels naar dezelfde
pagina, en niet meer dan één planningsingang. En de bestaande toets op
bereikbaarheid telt nu ook links in een markdown-kaart mee — anders zou
"elke pagina heeft een ingang" alleen met tegels te halen zijn.

**Volledige testsuite**: 1828 tests, allemaal groen.

## v1.34.1 — Prijsbereik in het komende schema

**Gemeld** met screenshot: "Hier zou toch een prijs range moeten staan?
Elk kwartier wijzigd de prijs namelijk."

Klopt. Kwartieren met dezelfde modus staan als één blok — een blok van
10:45 tot 18:45 beslaat 32 kwartieren met evenzoveel prijzen, en er
stond alleen de hoogste. Dat las als "de prijs is 0,321 €/kWh" terwijl
hij tussen 13,1 en 32,1 ct schommelde.

De laagste werd al berekend (`min_price_per_kwh`) maar nergens getoond.
Nu het bereik, in centen omdat dat leest zoals de rest van het
dashboard:

| Van | Tot | Modus | Prijs (ct/kWh) |
|---|---|---|---|
| 10:45 | 18:45 | smart | 13,1 – 32,1 |
| 19:30 | 23:00 | manual | 32,4 – 38,1 |

Een blok van één kwartier heeft geen bereik en toont één getal.

**Volledige testsuite**: 1829 tests, allemaal groen.

## v1.35.0 — Gespeld volgens de WALD-spelling

**Gevraagd**: "Helpt deze informatie nog voor de achterhoekse vertaling
om deze te verbeteren?" — met de uitgangspunten van de WALD-spelling
(Staring Instituut) en de Achterhoekse taalwiezer.

Ja, en dit is nuttiger dan het woordenboek van v1.33.0: dat gaf losse
woorden, dit geeft **regels**. Vier ervan raakten de tabel.

### 1. "ao", nooit "oa"

De WALD-spelling kent `ao` als zelfstandig teken; `oa` bestaat niet.
Er stond *goan, moar, noar, oaver, doar, kloar* — dat wordt **gaon,
maor, naor, aover, daor, klaor**.

### 2. De e zonder klemtoon is altijd een e

Dus **-lijk wordt -lek** en **-ig wordt -eg**: *meugelek*, *nachtelek*,
*neudeg*, *weineg*. Juist dat onderscheid maakt het Achterhoeks
zichtbaar naast het Liemers, dat -ig houdt.

### 3. i-j met een streepje

De tweeklank krijgt een streepje; de apostrof is voor samengetrokken
woorden (*he'j*, *da'k*, *lao'w*). Er stond *bi'j*.

### 4. Scheidbare werkwoorden

In het voltooid deelwoord komt een streepje tussen de delen —
*an-egeven*, *weg-enommen*. Dus **op-ewekt**, **uut-esteld**,
**bi-j-elaojen**, **trugge-elevert**, **umhoog-egaon**.

### Zo leest het nu

> "De accu haalt de nacht waarschijnlek neet: d'r is 2 kWh neudeg maor
> 1 kWh beschikbaor."

Ook zeven titels bijgewerkt. En "zon" gaat nu zonder spatie in de tabel,
zodat *zon,* en *zon.* ook meegaan — veilig omdat *zonder* en *zonne*
eerder in de tabel staan.

**Vier tests erbij** die de regels vasthouden in plaats van losse
woorden: geen "oa", geen -lijk of -ig, geen i'j, en streepjes bij de
scheidbare deelwoorden. Dat is het verschil met v1.33.0 — een regel is
te toetsen, een woordenlijst niet.

**Volledige testsuite**: 1833 tests, allemaal groen.

## v1.36.0 — Lampen tellen mee voor aanwezigheid

**Gevraagd**: "Voor aanwezigheids detectie, kan ook nog gekeken naar
lampen of heb ik dat niet goed?"

Je had het goed: dat gebeurde niet. Wrang detail — de systeemscan
verzamelde de lampen al wél, met als reden *"useful context for a
smarter, usage-aware EMS"*. Ze stonden dus in de export en werden
nergens gebruikt.

Een brandende lamp is hetzelfde soort signaal als de tv: het zegt niets
over **beweging**, maar wel dat er iemand is. Daarmee vervalt de stilte
als bewijs van afwezigheid, net zoals de tv de drempel van 45 naar 10
minuten kon brengen.

**Nieuw configuratieveld** "Lampen binnenshuis", meerdere te kiezen.
Bewust een eigen lijst en niet "alle lampen":

- **Alleen binnen.** Een buitenlamp of tuinverlichting op een tijdklok
  brandt elke winteravond en zou het huis permanent bewoond verklaren.
- **Niet tijdens de vakantiestand.** De automatisering *Vakantie
  Rolluiken + Verlichting* zet lampen juist aan om aanwezigheid na te
  bootsen. Die als bewijs van aanwezigheid nemen is een
  cirkelredenering — en het zou de inbraakmelding smoren, precies
  wanneer die nodig is.

In de tijdlijn staat **welke** lamp: "licht aan (Woonkamer)". Zonder die
naam valt niet na te gaan of het klopt; een vergeten zolderlamp
verklaart anders een verkeerde staat.

**Vijf tests erbij**, waaronder één die controleert dat dezelfde stilte
zonder lamp wél "weg" oplevert — anders toetst de rest niets.

**Volledige testsuite**: 1838 tests, allemaal groen.

## v1.37.0 — Toets op het prijsattribuut

**Gevraagd**: "Neem je alles gerelateerd aan de kwartier prijzen van
zonneplan mee incl tax/btw?"

**Ja.** Alle prijzen komen uit één plek, `_get_forecast_entries`, en die
leest `price_tax_included` — de prijs inclusief energiebelasting en BTW.
Dat geldt voor de dure-kwartier-drempels, de reserve, de kostprijs per
kWh in de accu, de kwartierplanning, de besparing en de meldingen.

Het kale `price_tax_excluded` wordt op **precies één** plek gebruikt:
het teruglevertarief ná het einde van de saldering. Zolang salderen
geldt is een teruggeleverde kWh de volle inkoopprijs waard (inclusief
belasting en BTW) plus de Zonnebonus van 2 ct.

### Maar dat was een antwoord uit de code, geen meting

Zonneplan levert zelf een sensor met de gemiddelde afnameprijs van
vandaag. Die stond al in de export als *gevonden entiteit* — en werd
nergens gebruikt.

Nieuw: ligt dat gemiddelde buiten het bereik van onze eigen
kwartierprijzen van vandaag, dan lezen we structureel iets anders dan
waarvoor jij betaalt. Op jouw gegevens van vandaag:

> De gemiddelde afnameprijs van Zonneplan (27,4 ct) ligt binnen de eigen
> kwartierprijzen van vandaag (13,1 tot 33,7 ct). Belasting en BTW zitten
> er dus in.

Bewust alleen die grove toets. Vergelijken met ons *gemiddelde* zou
niets zeggen: Zonneplan weegt naar werkelijk verbruik en er wordt vooral
's nachts ingekocht, dus dat hoort lager te liggen. Buiten het bereik
vallen kán niet — tenzij er een verkeerd veld wordt gelezen, en dat is
precies de vraag.

Staat het attribuut zelf al op het kale tarief, dan wordt dat direct
gemeld: elke drempel, reserve en opbrengst valt dan te laag uit.

Zichtbaar op de Kosten-pagina; de volledige toets staat in de
diagnostiek-export. **Zes tests erbij**, waaronder één die bewaakt dat
het kale tarief nergens anders opduikt dan bij de teruglevering.

**Volledige testsuite**: 1844 tests, allemaal groen.

## v1.37.1 — Vooruitblik op het teruglevertarief

**Gevraagd**: "Wanneer salderen wordt afgeschaft (na 31-12-2026) geldt
de export prijs zonder tax/btw als ik het goed heb."

Klopt, en Zonneplan schrijft het zelf zo op: bij een dynamisch contract
is de terugleververgoeding de **kale prijs, dus zonder energiebelasting
en BTW**. Precies wat deze integratie doet — `price_tax_excluded` plus
de Zonnebonus van 2 ct, met de omslag op de instelbare
`salderen_end_date`.

### Het risico zit in het veld, niet in de regel

Die berekening leunt op een tweede veld in dezelfde prijssensor dat
**vandaag nergens voor wordt gebruikt**. Ontbreekt het, of levert het
onzin, dan merk je daar niets van zolang salderen geldt — en valt de
terugleverwaarde stil op 1 januari. Dat is de slechtst denkbare dag om
dat te ontdekken.

De prijstoets kijkt daarom nu al vooruit en meldt één van drie dingen:

- het kale tarief is aanwezig en lager dan de belaste prijs (goed);
- het veld zit niet in deze prijssensor;
- het veld geeft een waarde die niet lager is dan de belaste prijs, en
  dat kan niet kloppen voor een tarief zonder belasting.

Ook het aantal resterende saldeerdagen staat erbij.

**Vier tests erbij.**

**Volledige testsuite**: 1848 tests, allemaal groen.

## v1.37.2 — De plantoetsing vergeleek appels met peren

Gevonden in de export van 11 augustus 11:21, in wat een dag eerder was
gebouwd.

De momentopname van het plan was om **10:26** genomen. De verwachting
die daarin staat gaat over de **rest van de dag** — de planning begint
immers bij "nu". Maar de werkelijkheid werd vergeleken met de
**dagtellers**, en die tellen vanaf middernacht.

Vandaag scheelt dat de hele ochtendzon: 21,1 kWh verwacht tegen ruim
23 kWh gemeten. Dat was vanavond gerapporteerd als een afwijking van
10% terwijl de voorspelling gewoon klopte — precies het soort vals
alarm waardoor een rapport niet meer gelezen wordt.

**Nu** legt de momentopname ook de stand van de dagtellers vast (zon,
import, opbrengst), zodat het verschil met het verschil wordt
vergeleken. Een opslagbestand van vóór deze versie mist die velden en
valt terug op nul, zonder om te vallen.

Ook: de gemeten accustand staat nu in de diagnostiek naast
`last_soc_percent`. Dat laatste veld is een bijproduct van de
ontlaadberekening en stond in deze export op `null` — midden in het
goedkope blok eindigt de tick eerder, en dan wordt het niet gezet.

**Volledige testsuite**: 1851 tests, allemaal groen.

## v1.38.0 — Proefstand: vijf kandidaten die niets sturen

**Gevraagd**: "Misschien eerst integreren totdat ze daadwerkelijk gaan
meebewegen? Dus een extra onzichtbaar tabblad waar waardes zichtbaar
zijn hoe betrouwbaar etc."

Precies de goede volgorde, en dezelfde die bij de plantoetsing werkte:
eerst meten, dan pas sturen. Vijf tegelijk in de beslislogica hangen zou
betekenen dat je bij een afwijking niet meer weet welke het deed.

Nieuwe subview **Proefstand**, bereikbaar vanaf de Meetkwaliteit-pagina.
Elke kandidaat meldt wat hij zou zeggen, hoe hard dat is, en wat hij zou
raken:

| Kandidaat | Nu |
|---|---|
| Slijtagekosten per kWh | **4,7 ct/kWh** — 3 × €729 over 7,74 kWh × 6000 cycli |
| Opbrengst na de saldering | ruwe doorrekening van het plan van vandaag |
| Verbruiksprofiel per dagtype | verzamelt vanaf nu, weken nodig |
| Accugezondheid over de tijd | dagmeting, minstens 30 dagen |
| Prijsvorm voorbij de bekende prijzen | verzamelt vanaf nu |

### Wat er onderweg rechtgezet moest worden

Mijn eigen voorstel voor de slijtagekosten klopte niet. Ik schreef dat
verkopen bij een marge van 2,8 ct verlies is omdat een cyclus 4 ct kost
— maar **ontladen naar het huis of naar het net is dezelfde slijtage**.
Dat getal kiest daar dus niets tussen.

Waar het wél telt: of energie überhaupt door de accu moet. Zon direct
terugleveren kost niets; opslaan en later gebruiken kost een halve slag
heen en een halve terug. En verkopen wat het huis vannacht nodig heeft
om het daarna terug te kopen is een **extra** slag die er anders niet
was geweest. Dat staat nu zo in de code en in de toelichting.

### Bewaakt

Een test leest de proefstandcode en controleert dat er geen modus, geen
vermogen en geen drempel in voorkomt. Alle drie de nieuwe reeksen worden
bewaard over een herstart — kandidaten die zich moeten bewijzen kunnen
dat niet als ze elke keer opnieuw beginnen.

**Dertien tests erbij.**

**Volledige testsuite**: 1864 tests, allemaal groen.

## v1.39.0 — Wat een kandidaat zou hebben opgeleverd

**Gevraagd**: "Dan dus ook aangeven wat het opgeleverd zou hebben als ze
wel zouden sturen."

Terecht: zonder bedrag is "betrouwbaar" geen argument om iets aan te
zetten. Elke kandidaat op de proefstand boekt nu dagelijks wat hij zou
hebben gedaan, met een totaal per dag en per jaar.

### Maar niet alles is in euro's te vangen

Een verzonnen bedrag is erger dan geen bedrag, dus wie het niet kan zegt
dat — met de reden erbij:

| Kandidaat | Bedrag |
|---|---|
| Slijtagekosten | **ja** — doorzet × 4,7 ct, per dag geboekt |
| Verbruiksprofiel per dagtype | **ja** — het verschil in kWh × de prijs |
| Opbrengst na de saldering | nee: dat bedrag is wat de nieuwe regels *kosten*, niet wat sturen oplevert |
| Accugezondheid | nee: het voorkomt een verkeerde aanname, het levert niets op |
| Prijsvorm | nee: pas te becijferen als de voorspelde vorm naast de echte prijzen van de dag erna ligt |

De slijtage is bewust **negatief** geboekt. Sturen zou dat bedrag niet
verdienen maar vermijden: de gerapporteerde opbrengst houdt nu geen
rekening met wat de accu zichzelf kost, en dit is precies het deel dat
er ten onrechte bij staat. Bij een doorzet van ruim 6 kWh per dag gaat
het om zo'n **€ 0,29 per dag, oftewel € 107 per jaar**.

Het dagtypebedrag is nadrukkelijk een **bovengrens**: niet elke
misrekening in de reserve kost ook echt geld — alleen die waarbij de
accu daardoor te vroeg leeg was of onnodig vol bleef.

De boekingen worden 120 dagen bewaard en overleven een herstart.

**Vijf tests erbij**, waaronder één die eist dat élke kandidaat een
uitspraak doet over het bedrag — ook als die uitspraak "dat kan ik niet"
is.

**Volledige testsuite**: 1869 tests, allemaal groen.

## v1.39.1 — De proefstand stond op de verkeerde pagina

**Gevraagd**: "Waar vind ik de info nu?"

Goede vraag, en het antwoord klopte niet. De ingang naar de proefstand
was onder *Planning* beland terwijl hij bij *Meetkwaliteit* hoort — daar
staat alles wat over betrouwbaarheid gaat, en dat is precies wat een
kandidaat op de proefstand moet bewijzen.

De link staat nu onderaan de Meetkwaliteit-pagina.

**Volledige testsuite**: 1869 tests, allemaal groen.

## v1.40.0 — Ook melden dat het weer goed is

**Gemeld**: "Ik krijg wel de melding dat er niet genoeg is, maar niet
dat er wel weer genoeg zou zijn, op de landingspage misschien, hierbij
een tekst en uitleg met eventueel een kleine tabel?"

Twee dingen, en het eerste is een gat: de waarschuwing *"Accu haalt de
nacht mogelijk niet"* had geen tegenhanger. Je blijft dus achter met een
melding die misschien allang niet meer geldt — en dan ga je zelf kijken,
of je zet de melding uit. Precies wat je niet wilt bij de enige melding
die standaard aan staat.

**Nu**: *"✅ Accu haalt de nacht weer"*, met de laagste stand erbij.
Alleen bij de omslag, en alleen als er ook echt eerst een waarschuwing
is geweest — anders krijg je elke ochtend een opgewekt bericht dat er
niets aan de hand is.

Dezelfde afspraken als de bestaande herstelmeldingen: de schakelaar van
de probleemmelding geldt (wie die uitzet wil ook het herstel niet), maar
het dempingsvenster wordt bewust omzeild. Een probleem dat tien minuten
na de waarschuwing is opgelost zou anders stilzwijgend verdwijnen.

### Op de landingspagina

Nieuwe sectie **Haalt de accu het?** met een regel uitleg en een tabel:

| Laagste | Eind | Opbrengst | Vooruit |
|---|---|---|---|
| 28% | 28% | € 3,59 | 51 kw |

Daarvoor moest de tekengrens van de landingspagina van 1400 naar 1650 —
bewust, en met de reden erbij, zodat de volgende toevoeging weer een
afweging wordt in plaats van vanzelfsprekend.

### En een taalfoutje

In je screenshot stond *"de huus aan 't net hunk"*. Huis is onzijdig:
"de woning" wordt nu **'t huus**.

**Volledige testsuite**: 1872 tests, allemaal groen.

## v1.41.0 — Nog niet bepaald: en waaróm dan

**Gemeld** met een screenshot van de tegel *"PV-installatieprofiel — nog
niet bepaald"*: "Als er zaken niet bepaald zijn of nog niet genoeg data,
wil ik dat graag zien."

Terecht. "Nog niet bepaald" zegt niet of er iets stuk is, of er iets
moet gebeuren, of dat het gewoon een kwestie van wachten is — en dat
verschil is precies wat je wilt weten.

Wrang: achter die tegel stond de reden al klaar. In de diagnostiek van
16:31 staat bij dat profiel *"0/5 heldere dagen verzameld"*. Die zin
haalde alleen het dashboard niet.

**Nieuw**: één overzicht van alles wat nog niet af is, gescheiden in
twee stapels:

- **Wachten op waarnemingen** — er is niets mis, er zijn nog te weinig
  metingen. Nu 16 onderdelen, van *"6/10 dagen minimum"* tot *"0/5
  heldere dagen verzameld"*.
- **Vraagt een handeling** — er ontbreekt een sensor of instelling, en
  wachten helpt niet. Nu 0.

Wat *niet toetsbaar* is blijft er bewust buiten: daar valt principieel
niets tegen af te zetten, en in de wachtrij zetten zou suggereren dat
het vanzelf goedkomt.

Zichtbaar als tabel op de Meetkwaliteit-pagina, met een tegel op de
landingspagina die het aantal toont en rood kleurt zodra er iets in de
doen-stapel staat.

Niets nieuws gemeten — dit komt uit het bestaande
betrouwbaarheidsoverzicht, de proefstand en de leergezondheid. Ze stonden
alleen nergens bij elkaar.

**Vijf tests erbij.**

**Volledige testsuite**: 1877 tests, allemaal groen.

## v1.42.0 — De tekortmelding was zinloos geworden

**Gevraagd**: "Heb je het diagnostiek file ook nagekeken?"

Nee, niet goed genoeg — ik had er alleen het gereedheidsoverzicht uit
getrokken. Bij het echte nakijken kwam dit boven.

In de export van 16:31: **36 tekortkwartieren**, laagste stand 10%, en
de melding *"Accu haalt de nacht mogelijk niet"* ging om 14:30, 15:31
**en** 16:31 af.

Dat getal was zinloos geworden, en door mijn eigen toedoen. Het telde
over de HELE planning, en die reikt sinds **v1.25.0** zover als er
prijzen zijn — hier 126 kwartieren, ruim 31 uur. Over die periode vraagt
het huis 38 kWh terwijl er 7,78 kWh in de accu past. Dat de accu ergens
onderweg leeg is, is dan geen storing maar rekenkunde.

De maat is gemaakt voor een horizon van negen uur en is nooit meegegaan
toen die horizon verviervoudigde.

**Nu** telt hij tot het eerstvolgende goedkope blok — precies wat de
reserve belooft. Wat daarna gebeurt is een andere vraag: dan wordt er
geladen, en leeg zijn is het begin van een nieuwe slag. Op de gegevens
van 16:31 wordt dat **0 in plaats van 36**. Het oude getal blijft
zichtbaar als `tekort_kwartieren_hele_planning`.

### En een tweede fout onderweg

Ik wilde de grens eerst leggen bij het veld `in_goedkoop_blok` dat elke
planregel al draagt. Dat blijkt iets anders te betekenen dan de naam
zegt: het is *"prijs onder de drempel"*, en die vlag springt heen en
weer — in de export staat 16:30 op waar, 16:45 op niet-waar, terwijl het
blok pas de volgende ochtend begint. Elke planregel draagt nu een eigen
`voor_bijladen`, gezet op het moment dat het echte blok bekend is.

**Volledige testsuite**: 1880 tests, allemaal groen.

## v1.43.0 — Nee, en nu wel

**Gevraagd**: "Wordt nu echt alle data opgeslagen, zodat een herstart
nergens meer invloed op heeft?"

Nagerekend in plaats van gegokt, en het antwoord was **nee**. Elf velden
bouwden toestand op en werden nergens bewaard.

### Wat er verloren ging

| Veld | Gevolg van een herstart |
|---|---|
| `nilm_dismissed_duplicate_pairs` | weggeklikte dubbelparen kwamen terug |
| `nilm_unconfirmed_candidates` | "wordt al tien dagen gezien" begon opnieuw bij vandaag |
| `water_source_profiles` | de geleerde koppeling kraan ↔ verbruik |
| `current_month_*` (5 tellers) | het maandoverzicht sprong halverwege de maand op nul |
| `battery_discharge_today_kwh` | de dagteller |
| `_daily_report_counters` | de dagrapportage |
| `_last_plan_alert` | **de tekortmelding ging opnieuw af** |

Die laatste verklaart wat je vanmiddag zag: *"Accu haalt de nacht
mogelijk niet"* om 14:30, 15:31 én 16:31. Elke herstart begon met een
schone lei, dus gold elke waarschuwing weer als nieuw.

Bij `nilm_unconfirmed_candidates` draai ik een eerdere keuze terug. Die
lijst wordt inderdaad elke tick opnieuw gevuld — maar één veld niet:
`first_seen`, de dag waarop een apparaat voor het eerst opviel.

### Bewust níet bewaard

Halve metingen. Een rendementsstuk of meetvenster dat door een herstart
een gat heeft is geen meting meer; opnieuw beginnen is beter dan een
verminkt getal bewaren. Datzelfde voor korte schuivende vensters van
enkele minuten en voor alles wat elke tick opnieuw wordt berekend — dat
terugzetten zou een oud getal tonen alsof het actueel is.

### En de vraag zelf beantwoordbaar gemaakt

Ik kon dit alleen beantwoorden door alles met de hand na te lopen, en
dat houdt niemand vol. Een nieuwe test doet het voortaan: elk veld dat
in `__init__` als lege verzameling of nulteller begint moet in precies
één van drie bakken vallen — bewaard in de opslag, teruggezet door een
sensor, of expliciet als vluchtig benoemd **met reden**. Wie er een
nieuwe bijzet en niets kiest, krijgt een rode test in plaats van stil
dataverlies.

Plus een test die eist dat wat jij hebt weggeklikt of bevestigd nooit
vluchtig is.

**Volledige testsuite**: 1883 tests, allemaal groen.

## v1.43.1 — "124 kw" leest als kilowatt

**Gemeld**: "die 124 kw ziet er raar uit niet?"

Klopt. Het waren kwartieren, en op een pagina waar overal vermogens en
kilowatturen staan is "kw" precies het verkeerde woord. Er staat nu **31
uur** — dat zegt bovendien meer: je wilt weten hoe ver het plan reikt,
niet uit hoeveel blokjes het bestaat.

**Volledige testsuite**: 1883 tests, allemaal groen.

## v1.44.0 — Welke uren dan?

**Gevraagd**: "Ok maar waar zie ik dan welke uren hij verwacht aan het
net te hangen?"

Nergens — tenzij je de 120 regels van de kwartiertabel afzocht op het
uitroepteken. Een aantal zonder tijdstip is een alarm zonder adres.

**Nu** staan de tijden erbij, met aaneengesloten kwartieren samengevoegd
tot één periode:

> **Nee: 8 kwartier(en) aan het net** — 03:15-05:15.

Acht losse tijdstippen leest niemand; één periode wel. Ze staan op de
landingspagina (de eerste twee, om de tegel leesbaar te houden) en
volledig op de pagina *Planning-samenvatting*. De melding op je telefoon
blijft ongewijzigd — daar staat het aantal, en de tijden vind je in het
dashboard.

Ook hier alleen tot het goedkope blok, net als de telling zelf: daarna
wordt er geladen en is leeg zijn geen tekort meer.

De regel *"Ondergrens 10%"* is van de landingstegel verdwenen; die stond
al bij de kwartiertabel en kostte precies de ruimte die de tijden nu
innemen. En de twee tekengrenzen voor de landingspagina - 1600 en 1400 -
zijn gelijkgetrokken op 1650; twee grenzen die net iets van elkaar
verschillen leveren alleen verwarring op.

**Volledige testsuite**: 1886 tests, allemaal groen.

## v1.45.0 — Het dagtypeprofiel hoefde niet vanaf nul

**Gevraagd**: "Nog geen data verzameld? *Verbruiksprofiel per dagtype: 0
van de 24 uren.*"

Klopt, en dat was onnodig traag. Het algemene uurprofiel wordt bij de
installatie in één keer uit de recorder gevuld; het profiel per dagtype
begon leeg en had daardoor weken nodig — een weekend levert twee dagen
per week.

Terwijl **diezelfde geschiedenis de dag al draagt**: elke emmer in die
bootstrap is een `(datum, uur)`-paar, dus of het een werkdag was staat
er gewoon in. Dat werd alleen weggegooid.

Bij de eerstvolgende herstart wordt het profiel per dagtype in één keer
gevuld uit de zeven dagen recordergeschiedenis die er al waren. In jouw
geval: vier werkdagen en twee weekenddagen (8 en 9 augustus). Er zijn er
drie per uur nodig, dus **de derde weekenddag komt zaterdag** — geen
weken meer, maar vier dagen.

Een bestaand profiel wordt niet overschreven; de bootstrap loopt alleen
als er nog niets staat.

### En de tekst zei niet waar het aan lag

*"0 van de 24 uren"* laat in het midden of er niets binnenkomt of dat
één van de twee dagtypen achterloopt. Nu:

> Werkdagen: 4 waarneming(en) per uur, weekend: 2. Er zijn er 3 nodig
> voor beide, en weekend loopt achter.

**Volledige testsuite**: 1889 tests, allemaal groen.

## v1.46.0 — Het lag niet aan de bewolking

**Gemeld**: "Vandaag was een mega zonnige dag: *PV-installatieprofiel
(oriëntatie) 0/5 heldere dagen verzameld.*"

Terecht wantrouwen. In de diagnostiek staat `sun_azimuth_degrees` op
**null** terwijl de zonshoogte gewoon 39,5° geeft.

De azimut werd **uitsluitend** uit `sun.sun` gelezen, terwijl de
zonshoogte al jaren een eigen instelbare sensor kent met `sun.sun` als
vangnet. Jouw zonstand komt van een eigen integratie
(`sensor.zon_van_eibergen_...`), en zonder dat ene attribuut viel
`_update_pv_geometry_learning` **elke tick meteen stil** — bij de eerste
regel, nog voor er iets over bewolking berekend werd.

Dat is ook te zien: `pv_peak_azimuth_history` is leeg, en
`pv_azimuth_performance` — dat elke tick gevuld hoort te worden — óók.
Twee lege verzamelingen die samen precies één oorzaak aanwijzen.

**Nu**: een eigen azimut-sensor bij de instellingen, met `sun.sun` als
vangnet. Zelfde opzet als de zonshoogte.

### En de tekst loog

*"0/5 heldere dagen verzameld"* suggereert dat het aan het weer lag en
dat wachten helpt. Als de zonstand niet uit te lezen valt, staat er nu
dat dát het probleem is — inclusief wat je eraan kunt doen. Precies
waarvoor de "nog niet bepaald"-lijst uit v1.41.0 bedoeld was; deze zat
er alleen nog met de verkeerde reden in.

**Vier tests erbij.**

**Volledige testsuite**: 1893 tests, allemaal groen.

## v1.46.0 — Herstelmeldingen spraken Nederlands

**Gemeld**: "Niet in het achterhoeks? *✅ Accu haalt de nacht weer — Er
is weer genoeg opgeslagen om tot het goedkope blok te overbruggen.*"

Twee losse fouten in één regel.

### 1. De geschiedenis kreeg de onvertaalde tekst

De vertaling zelf klopte: alles wat de deur uitgaat gaat er doorheen.
Maar de herstelmeldingen schreven daarna **zelf** een regel in de
geschiedenis, met hun eigen lokale variabelen — en die waren nog
Nederlands. Op de telefoon stond dus Achterhoeks en in het
meldingenoverzicht Nederlands, precies wat v1.24.0 wilde voorkomen.

Die regel wordt nu geschreven door de functie die ook verstuurt, met de
tekst die daadwerkelijk de deur uitging. Beide herstelpaden — het
bestaande en dat van v1.40.0 — deden dit fout; het tweede omdat ik het
eerste had gekopieerd.

### 2. De titel stond niet in de tabel

Bij een herstelmelding is de soort bewust leeg (het dempingsvenster
geldt er niet voor), en daarmee viel ook het opzoeken van de titel weg.
Woordvervanging alleen maakt van *"Accu haalt de nacht weer"* niets
Achterhoeks: geen van die woorden staat in de tabel.

Alle negen herstelsoorten hebben nu een eigen titel — *"Den accu haalt
de nacht weer"*, *"De sensor dut 't weer"*, *"'t Systeem löp weer"* — en
een test eist dat elke herstelsoort er een heeft, zodat er niet
stilzwijgend eentje terugvalt op Nederlands.

**Volledige testsuite**: 1897 tests, allemaal groen.

## v1.47.0 — Ingangen die er zijn maar niets leveren

**Gevraagd**: "Meer van dit soort zaken in de integratie?"

Dat is de goede vraag: de azimut was geen incident maar een **soort**
fout. Een onderdeel leest een attribuut, krijgt `None`, keert netjes
terug — en er is niemand die het merkt. Een *ontbrekende* sensor werd al
gemeld; een sensor die er wél is maar het gevraagde attribuut niet
heeft, glipte ertussendoor.

**Nieuw**: een controle die niet naar de configuratie kijkt maar naar de
**waarde**. Levert de bron op dit moment iets bruikbaars op? Zo nee, dan
staat erbij wat er stilvalt en wat je eraan kunt doen. Acht ingangen:

| Ingang | Wat stilvalt zonder |
|---|---|
| Stand van de zon (azimut) | het installatieprofiel en de beschaduwing |
| Hoogte van de zon | de daglichtbepaling |
| Zonvoorspelling (`detailedForecast`) | elke schatting van de zon vooruit |
| Prijsvoorspelling (`forecast`) | de hele planning en elke prijsdrempel |
| Bewolking (`cloud_coverage`) | het weer-ensemble |
| Buitentemperatuur | de klimaatvoorspelling en de accukoeling |
| Airco / slaapkamer (`hvac_action`) | de aircoherkenning |

Alleen wat je hebt ingesteld. Wie geen airco heeft hoort daar niets
over.

De gebreken landen in de **doen**-stapel van het "nog niet
bepaald"-overzicht, niet in de wachtstapel — wachten helpt hier niet.
Daarmee kleurt de tegel op de landingspagina rood zodra er zoiets
opduikt, in plaats van dat een onderdeel maandenlang stil niets doet.

### Wat de rondgang verder opleverde

Alle andere lege verzamelingen in je export bleken te verklaren en geen
fout: `water_source_profiles` wacht op jouw bevestiging (zo bedoeld),
`nilm_unconfirmed_candidates` is leeg omdat alle 37 apparaten al
beoordeeld zijn, en de rest staat al op de wachtlijst met een reden.

**Zes tests erbij.**

**Volledige testsuite**: 1903 tests, allemaal groen.

## v1.48.0 — De codebase langs dezelfde meetlat

**Gevraagd**: "kun je aan de hand van deze verbeteringen de hele code
eens nakijken op ontbrekende danwel incorrecte zaken?"

Gezocht op de fouttypen die deze week boven kwamen: tijdzoneloze klokken,
maten die met de horizon meegroeiden, ijkpunten op het verkeerde moment,
en stille doodlopende wegen. Drie echte vondsten.

### 1. De klok van het proces in plaats van die van Home Assistant

`datetime.now().hour` volgt de tijdzone van het **proces**, niet die van
Home Assistant. Draait HA in een container op UTC — wat gebruikelijk is —
dan scheelt dat 's zomers twee uur.

Twee sensoren lazen zo het **verbruiksprofiel** en de **PV-bias van het
verkeerde uur** af, en een NILM-bevestiging kreeg mogelijk de verkeerde
datum. Dit viel nergens om: het gaf een plausibel getal, alleen van het
verkeerde uur. Dezelfde soort fout als de tijdzoneloze tijd in de
diagnostiek (v1.28.0), maar dan zonder foutmelding.

### 2. De plantoetsing vergeleek nog steeds appels met peren

In v1.37.2 legde ik de dagtellers vast bij de momentopname. Maar de
**verwachting** zelf liep nog altijd over de hele planning — sinds
v1.25.0 tot 31 uur. Er werd dus een halve dag van morgen tegen de
werkelijkheid van vandaag gelegd: 21 kWh rest-vandaag plus 23 kWh morgen
tegenover 23 kWh gemeten. Elke dag tientallen procenten "afwijking" op
een voorspelling die klopte.

De samenvatting kan nu worden afgebakend, en de momentopname loopt tot
middernacht.

### 3. "Laagste 10%" ging over morgenochtend

Dezelfde horizonfout, derde plek: de laagste stand op de landingstegel
liep over de hele planning. Nu tot het eerstvolgende bijladen — precies
wat de reserve belooft, en wat je er als lezer in legt.

### Onderliggende oorzaak weggenomen

Een planregel droeg alleen `"14:30"`. Elke afbakening moest daardoor met
omwegen worden gemaakt, en dat ging twee keer mis — één keer met een
veld dat iets anders bleek te betekenen (`in_goedkoop_blok`). Elke regel
draagt nu zijn **echte tijdstip**.

### Bewaakt

Een test die geen `datetime.now()`, `datetime.utcnow()` of
`date.today()` meer toestaat in de integratie.

**Volledige testsuite**: 1908 tests, allemaal groen.

## v1.49.0 — Drie dingen uit de export van 18:53

**Gevraagd**: "Klopt nu alles?" Nee. Maar de ingangscontrole van v1.47.0
meldt niets meer, dus de azimut wordt nu wél uitgelezen.

### Eerst een correctie op mezelf

Ik schreef gisteren: *"`sun_azimuth_degrees` is None in je export."* Dat
veld **staat helemaal niet in de export**. Ik las een ontbrekende sleutel
als een lege waarde en presenteerde dat als bewijs. Het bewijs was de
lege `pv_azimuth_performance`, en de conclusie bleek te kloppen — maar
de onderbouwing die ik gaf, klopte niet.

### 1. Een volgordefout die de eerdere fix ongedaan maakte

`_recompute_measurement_quality()` werd aangeroepen **vóór**
`_apply_persisted_state()`. Hij rekende dus op een lege reeks en zette
score én label juist op `None` — precies de kwaal die v1.15.0 wilde
verhelpen, alleen nu met een extra regel code.

Te zien in de export: twintig herstelde metingen,
`sensor_health_score` op null, en de regel in het
betrouwbaarheidsoverzicht op *"niet geconfigureerd"* — waardoor hij in
de **doen**-stapel belandde terwijl er niets te configureren viel.

De bestaande test keek alleen of de aanroep ergens in de buurt stond.
Nu wordt de volgorde getoetst.

### 2. Een rapport dat zichzelf tegensprak

`uitval: 0` naast `uitval_per_sensor: {available_kwh: 8}` in hetzelfde
blok. De eerste telt over de laatste twintig metingen, de tweede over de
hele looptijd. De sleutel heet nu `uitval_per_sensor_totaal`, en de zin
*"sensor 0x niet uitleesbaar"* — die niemand wil lezen — verschijnt
alleen nog als er ook echt iets is weggevallen.

### 3. "0/5 heldere dagen" was een zelfvervullende voorspelling

De dagstand van de PV-geometrie (`_pv_geometry_day_peak_w` en
verwanten) werd **niet bewaard**. Bij een herstart staat de piek op 0 en
wordt de dag stilzwijgend weggegooid; bij een herstart ná de middagpiek
is de rest van de dag bovendien te donker om als "helder" door te komen.

Elke versie die je vandaag installeerde, wiste dus de dag waarop
gemeten werd. Nu blijft de dagstand staan.

**Volledige testsuite**: 1910 tests, allemaal groen.

## v1.50.0 — Een diepvries is aan/uit

**Gevraagd**: "Het is toch simpelweg, aan/uit? Wordt er rekening
gehouden met de buitentemp?"

Allebei raak, en samen verklaren ze de hele meldingenreeks.

### Het daggemiddelde is een product van twee dingen

    daggemiddelde = vermogen tijdens draaien × aandeel van de dag draaiend

Die twee door elkaar meten maakt het onmogelijk te zeggen wát er aan de
hand is. Loopt het draaivermogen op, dan is er mechanisch iets; loopt de
inschakelduur op, dan is er méér warmte — een warme schuur, een deur die
openstond, een slechte afdichting.

En het verklaart de reeks van de diepvries: **12 van de 30 dagen op
0,8 W, 13 dagen op 76-81 W**. Dat is geen slijtage maar een sensor die
hele dagen niets doorgaf. Een diepvries doet dat niet.

**Nu** worden inschakelduur en draaivermogen apart gemeten. Draait de
compressor minder dan 5% van de dag, dan is de dag meetuitval en telt
hij niet mee — in plaats van als "−98,8% drift, mogelijk defect".

### De temperatuurcorrectie stond op 0,0%

Die bestaat sinds v1.21.0, maar in jouw export staat één enkele
temperatuur in de reeks. Die reeks groeit namelijk alleen bij een
**afgesloten dag**, en meer dan de helft van de dagen viel af — dus
bleef de correctie eeuwig uit. Nu de uitvaldagen bij de bron worden
herkend, groeit hij weer. En er staat voortaan bij waaróm hij 0,0% is,
zodat dat niet leest als "de temperatuur doet er niet toe".

### Het opgebouwde alarm is eenmalig herrekend

Wat er al stond bleef staan, en dat alarm rust op die uitvaldagen. De
opgeschoonde reeks wordt nu één keer opnieuw afgespeeld — bewust geen
blinde reset, zodat een apparaat dat écht meer verbruikt zijn alarm
houdt.

Op jouw gegevens: van *"⚠️ aanhoudend stijgend — mogelijk defect"* naar
**"→ stabiel"**, met 18 echte dagen en een referentie van 76,8 W.

### En de drift keek naar de verkeerde dag

De referentie filterde uitvaldagen al weg, maar het driftpercentage
vergeleek met `history[-1]` — en die kon zelf een uitvaldag zijn. Vandaar
"−98,8%" terwijl de dag ervoor gewoon 80,57 W was.

**Zeven tests erbij**, waaronder één die bewaakt dat apparaten van vóór
deze versie blijven werken: zonder vangnet zou elke dag als meetuitval
gelden en zou de hele detectie na de opwaardering stilvallen.

**Volledige testsuite**: 1917 tests, allemaal groen.

## v1.51.0 — Een stille sensor is geen instelprobleem

**Gemeld** met screenshot: onder *"Vraagt een handeling (2)"* stonden
`mpc` en `digital_twin`, allebei met "Beschikbare-energie-sensor niet
uitleesbaar".

Terwijl die sensor gewoon is ingesteld en het meestal doet. Hij
antwoordde die ronde even niet — en dan levert MPC geen plan, dus stond
de status op **niet geconfigureerd**. Dat is de enige status die in de
doen-stapel belandt, dus vroeg het overzicht om een handeling die er
niet is.

Nu wordt er onderscheid gemaakt:

| Situatie | Waar |
|---|---|
| Entiteit niet ingesteld | **doen** — er valt iets in te stellen |
| Entiteit zwijgt al minuten | **doen** — controleer de sensor |
| Entiteit antwoordde deze ronde niet | **wachten** — trekt zichzelf recht |

De middelste gebruikt de bestaande bevestigingsdrempel uit v1.11.0: een
enkele gemiste uitlezing hoort niemand wakker te maken, een sensor die
minutenlang zwijgt wel.

Dat de doen-stapel rood kleurt is precies de bedoeling — dan moet er ook
echt iets te doen zijn. Anders leert het overzicht je hem te negeren, en
dan mist het de keer dat er wél wat aan de hand is.

**Volledige testsuite**: 1920 tests, allemaal groen.

## v1.52.0 — De besparing van vandaag stond op min

**Gevraagd**: "Kan alles nu correct gelezen worden, kloppen de waarden
etc?"

De hele export nagelopen: 239 velden, alle kerncijfers binnen een
plausibel bereik, geen interne fouten, en de doen-stapel is leeg. Eén
getal klopte niet.

### -€0,37 besparing, terwijl de accu vol staat

Vandaag: werkelijk **-2,03**, zonder accu-sturing **-2,40**. Besparing
dus **-0,37** — alsof de aansturing slechter is dan niets doen. Op een
dag met 22,7 kWh zon en een accu op 98%.

De vergelijking rekent per tick af tegen de netstroom. **Laden is op dat
moment een kost**: die kWh had ook teruggeleverd kunnen worden. De
opbrengst volgt pas bij het ontladen, vanavond. Een dag afsluiten met
een volle accu tegen een dag die leeg eindigt is dus geen eerlijke
vergelijking — dezelfde soort fout als meten over een horizon die niet
aansluit.

**Nu** staat er een correctie naast: het verschil in accu-inhoud tussen
het begin van de dag en nu, gewaardeerd tegen wat een kWh op dit moment
opbrengt. Met jouw cijfers wordt -0,37 daarmee ruim **+2,00**.

Bewust **naast** het rauwe cijfer en niet eroverheen: het rauwe cijfer
is wat er werkelijk is afgerekend, de correctie is een schatting van wat
er nog komt. De maandcijfers blijven zoals ze zijn — over een hele maand
middelt dit vanzelf uit.

### Wat verder klopte

De begrensde maten uit v1.42 en v1.48 doen hun werk: 13
tekortkwartieren tot het bijladen tegen 17 over de hele planning, met
"morgen 05:15-08:30" erbij. Slijtage €0,71 naast €5,19 netto verwacht.
De diepvries staat op 18 echte dagen zonder alarm. Ingangscontrole
schoon.

**Zes tests erbij.**

**Volledige testsuite**: 1926 tests, allemaal groen.

## v1.53.0 — Drie kolommen in plaats van zeven stroken

**Gemeld** met screenshot: "veel lege vlakken op landingspagina, op
mobiel niet te zien op laptop wel. Kun je zaken bundelen zodat het
mogelijk zelfs zonder scrollen in 1 opzicht te zien is?" en daarna: "3
secties en die met alles vullen incl headers?"

Zeven secties onder elkaar, elke kaart over de volle breedte van zijn
sectie: op een laptop gaf dat een smalle strook tekst met een half
scherm wit ernaast, en drie schermen scrollen.

**Nu drie kolommen die naast elkaar doorlopen**, elk met eigen koppen:

| Kolom | Inhoud |
|---|---|
| 1 | Statusbalk, accu- en live cijfers, modus & besluit |
| 2 | Haalt de accu het?, en de besturing |
| 3 | Status per onderwerp, nog niet bepaald, meer bekijken |

*Haalt de accu het?* is bewust naar kolom 2 verhuisd: het is het
antwoord op wat de besturing doet, en die kolom bleef anders halfleeg.
De statusbalk staat boven de eerste kop, want die gaat over alles.

**Niet voor mobiel geoptimaliseerd**, op verzoek — Home Assistant vouwt
de kolommen daar vanzelf onder elkaar, dus daar verandert de volgorde
maar niet de leesbaarheid.

Vier tests erbij: precies drie secties, elke kolom heeft koppen, de
kolommen blijven in balans (de langste hoogstens 2,5× de kortste), en
er raakt geen kaart zoek bij het herschikken.

**Volledige testsuite**: 1930 tests, allemaal groen.

## v1.54.0 — Eén uitschieter mag de meetlat niet optillen

**Gemeld** op de dag van de zonsverduistering: "De integratie geeft nu
maar 2 dure kwartieren door de piek, maar waarschijnlijk kan er toch
meer ontladen worden."

Klopt. De drempel is de bovenste 20% van de **prijsrange**, en die range
wordt opgerekt door één extreme piek:

    68,9 − 0,20 × (68,9 − 12,1) = 57,5 ct

Alleen 19:45 (68,9) en 20:00 (61,8) haalden dat. Kwartieren van 43 tot
51 ct — **anderhalf keer de mediaan van 30,7** — telden niet mee, puur
omdat de eclipspiek de meetlat omhoog trok.

**Nu wordt ook een mediaanmaat berekend en wint de ruimste van de
twee.** De range doet het werk op een gewone dag, de mediaan beperkt de
schade als één piek de range oprekt:

| Dag | Range | Mediaan | Resultaat |
|---|---|---|---|
| 11 aug (vlak) | 33 ct → 17 kw | 42 ct → 0 kw | **17** |
| 12 aug (eclips) | 58 ct → 2 kw | 43 ct → 6 kw | **6** |

Met twee grendels: er moet spreiding zijn (minstens 15 ct), én de piek
moet écht een uitschieter zijn (minstens tweemaal de mediaan). Op 11
augustus is de piek 1,25× de mediaan — dan verandert er niets. De maat
kan alleen versoepelen, nooit verstrengen.

## v1.55.0 — Modus `smart_charging`, en de vraag of de accu wel de goedkoopste bron is

**Gemeld**: "er is ook een operation mode smart-charge, deze laadt
alleen zonne energie maar geeft niet terug aan de woning" — en daarna
zelf gecorrigeerd naar de exacte waarde: `smart_charging`.

Die modus kende de integratie niet. Er stonden er drie in de code, en
`smart_charging` is de tegenhanger van `smart_discharging` die ontbrak.
Daardoor moest de aansturing altijd kiezen tussen "voed het huis"
(smart) en "doe niets met de zon" (manual op 0 W).

**Dat blokkeerde de vraag ervoor**: "het kan dus zijn dat de prijs
's nachts zo laag is dat stroom van het net goedkoper is."

Een kWh uit de accu is niet gratis:

    waarde = kostprijs / rendement + slijtage
           = 21,75 / 0,829 + 4,7 = 31,0 ct

Staat de nachtprijs op 12 ct, dan is die kWh van het net halen
goedkoper — én houd je de accu vol voor de ochtendpiek. De accu gaat dan
naar `smart_charging`: zon opnemen, niets afgeven.

Drie grendels: alleen als de modus écht in de select-entiteit staat,
alleen als kostprijs, rendement én slijtage gemeten zijn, en met 2 ct
marge zodat een half cent verschil niet elke tick heen en weer
schakelt.

**En een controle vooraf op elke modus.** Valkuil 2 uit de overdracht: een
term die de accu niet kent wordt stil genegeerd, en dan staat de accu
ergens anders dan de integratie denkt. Nu wordt de optielijst gelezen
vóór gebruik, met terugval op `smart` en een zichtbare melding.

## v1.56.0 — Knop "Nu laden"

**Gevraagd**: "als ik weet dat ik veel ga gebruiken is een button die
overschakelt naar smart (en automatische reset na 2 uur bijvoorbeeld)
een idee?"

Zet **alleen** het uitstelplan opzij. De reserve, de energiebrug en de
verkooptoets blijven werken — dat is het verschil met `force_manual`,
dat de hele aansturing overneemt. Een test bewaakt die grens.

Loopt tot het **einde van het uitstelvenster**, met twee uur als
ondergrens: twee uur alleen zou op een dag met uitstel tot 13:00
betekenen dat het uitstel om 10:00 hervat en je alsnog met een halfvolle
accu zit.

De **eindtijd** wordt bewaard, geen teller — anders zet een herstart de
klok terug op de volle looptijd.

De tegel telt af en noemt wat het kost: *"Nu laden — nog 3u12m ·
uitstel opzij gezet, kost ca. € 0,72"*. Niet om je tegen te houden,
maar zodat je weet wat je koopt.

**Volledige testsuite**: 1949 tests, allemaal groen.

## v1.57.0 — "None%", en eerlijk over wat de knop nog overruled

**Gemeld** met screenshot: "None%?" in de rendementstabel. De kaart
toonde de rauwe waarde terwijl die nog niet gemeten is. Er staat nu
*"nog niet gemeten (0 van 3 stukken)"*.

De rendementstabel is naar een **eigen pagina** verhuisd (bereikbaar via
de accupagina); met die extra tekst liep de accupagina over de grens van
2500 tekens.

**Gevraagd**: "Schakelt de nu laden knop automatisch uit wanneer het
goedkope daadwerkelijk door de integratie bepaalde nu starten met laden
moment start?"

Ja — de eindtijd ís dat omslagmoment. Behalve bij de ondergrens van twee
uur: ligt het omslagmoment dichterbij, dan loopt de knop daaroverheen.
Dat doet geen kwaad (de accu zou dan toch al laden), maar de tegel
beweerde wél dat er nog iets werd overruled. Nu staat er in dat geval:
*"Het uitstel was hier toch al afgelopen — de knop loopt alleen nog
uit"*, en de kostenschatting valt terug op nul.

Het omslagmoment wordt daarvoor apart bewaard: zodra de knop loopt geeft
het uitstelplan geen omslaguur meer terug, dus het moest worden
vastgelegd in plaats van opnieuw afgeleid.

## v1.58.0 — Hoe lang draait een noodloop al?

De les van deze week was steeds dezelfde: iets ving een probleem netjes
op — en **zweeg**. De azimut viel terug op `sun.sun`, kreeg niets, en
het installatieprofiel stond tien dagen op "0/5 heldere dagen". Er zijn
28 terugvalpaden en geen enkele mat hoe lang hij al actief was.

Vijf terugvallen worden nu gevolgd: de accustand die wordt afgeleid in
plaats van gemeten, de azimut en zonshoogte die op `sun.sun` terugvallen,
het rendement dat nog op de oude methode draait, en een modus die niet
bestaat.

Een dag terugval is ruis — een sensor die even zweeg. **Boven een dag**
verschijnt hij bij *"vraagt een handeling"* en kleurt de tegel op de
landingspagina rood.

Het beginmoment wordt bewaard; bij elke herstart opnieuw beginnen zou
"al drie dagen" onmogelijk maken, en dat is precies het getal waar het
om gaat.

De betrouwbaarheidstabel is naar een eigen pagina verhuisd — met de
noodlopen erbij liep Meetkwaliteit over de tekengrens.

## v1.59.0 — Wat veroudering versnelt

Van een **degradatiemodel is bewust afgezien**. Capaciteitsverlies is
enkele procenten per jáár, en de capaciteitssensor is zelf een schatting
die met de temperatuur meebeweegt. Uit elf dagen valt daar niets uit af
te leiden, en de modellen uit de literatuur vragen celparameters die
Zendure niet publiceert. Een curve die er wetenschappelijk uitziet met
onverifieerbare aannames is erger dan geen curve.

**Wat wél kan is de oorzaken meten in plaats van het gevolg.** Per dag
geteld:

- uren boven **90%** accustand — de accu stond gisteren uren op 98%
- uren boven **30 °C** celtemperatuur — gemeten 31 °C, 10,9 boven buiten
- uren op of onder 15%
- de warmste cel van die dag

Een gat in de metingen telt niet mee: dan weten we niet wat er
tussendoor gebeurde.

Zichtbaar op de nieuwe rendementspagina. Er wordt niets op gestuurd —
dit is meten, net als de proefstand. Twee bestaande mechanismen drukken
die drijvers trouwens al zonder dat dat de bedoeling was: het
uitstelplan houdt de accu 's ochtends laag, en de accukoeling drukt de
temperatuur.

**Volledige testsuite**: 1967 tests, allemaal groen.

## v1.60.0 — "Waarom doe je dit nu?"

**Gevraagd**: "Kun je in de integratie nog een eigen AI maken, die zaken
als *'Waarom laad je nu? → Omdat tussen 16:00 en 19:00 de prijs 31 cent
hoger ligt, er slechts 4,2 kWh zon wordt verwacht...'* kan toelichten, en
dan niet alleen het bovenstaande voorbeeld maar voor alles?"

**Geen taalmodel.** Het besluit is deterministisch — er is een exacte
regel die zei wat er moest gebeuren — dus een gegenereerde verklaring kan
er náást zitten zonder dat iemand het merkt. Elke regel komt uit een
waarde die de beslissing daadwerkelijk nam, en kan dus niets anders
zeggen dan wat er gebeurde. Een test bewaakt dat er geen API-aanroep in
sluipt.

Het live verhaal bevatte alle getallen al, maar als één lap tekst met
tabellen en klimaatprojectie ertussen — geen antwoord op "waarom nu".

Vijftien beslisredenen, elk met een eigen vraag boven het antwoord.
*"Waarom laad je nu?"* leest anders dan *"Waarom verkoop je nu?"*, en dat
verschil is het halve antwoord:

> **Waarom verkoop je nu?**
> → de prijs is nu 68,9 ct, de drempel voor 'duur' ligt op 43,0 ct
> → de accu staat op 77% (5,2 kWh bruikbaar)
> → er is 2,3 kWh nodig om de nacht te overbruggen, en dat blijft
> gereserveerd

Hoogstens drie regels: meer leest niemand, en de vierde reden is per
definitie de minst belangrijke.

Staat op de landingspagina, boven Besturing. Om er ruimte voor te maken
is de tabel bij *"Haalt de accu het?"* ingeruild voor één regel — de
getallen staan op de planningspagina. De tekengrens ging van 1650 naar
1900, met dezelfde reden erbij als de vorige keren.

**Volledige testsuite**: 1974 tests, allemaal groen.

## v1.61.0 — Gepland witgoed telt mee in de reserve

**Gevraagd**: "Nu weet ik zelf dat er morgen 2 wasmachines en een
vaatwasser zullen draaien, hoe gaat de integratie daar mee om?"

Niet — en dat is een gat van **4 à 5 kWh**, meer dan de helft van de
bruikbare accu. Het geleerde uurprofiel staat op 0,20 tot 0,51 kW per
uur. De kwartierplanning, de tekortkwartieren, de reserve en de
verkooptoets rekenden dus allemaal te laag.

Concreet risico: de verkooptoets besluit 's avonds dat er ruimte is,
gebaseerd op een nacht zonder wasmachines. Draaien die er 's ochtends
wél, dan hangt het huis eerder aan het net.

**Home Connect weet het wel.** Twee nieuwe configuratievelden:

| Veld | Entiteit bij jou |
|---|---|
| Uitgestelde start vaatwasser | `number.vaatwasser_begin_relatief` |
| Eindtijd wasmachine | `sensor.wasmachine_programma_eindtijd` |

**Uitlezen, niet bedienen** — die grens blijft staan, en een test
bewaakt hem: geen `async_call`, geen `set_value`, geen `press`.

Bij de wasmachine is alleen de **eindtijd** bekend, niet de starttijd.
Het verbruik zit vooral aan het begin (het verwarmen), maar zonder
programmaduur is het eerlijker om het bij het einde te leggen dan een
duur te verzinnen. Dat staat er zo bij.

**Wat een cyclus kost wordt gemeten**, niet geschat. Zolang er nog niets
gemeten is geldt 1,0 kWh voor de vaatwasser en 0,8 voor de wasmachine;
zodra een hele cyclus is gezien, is dat de waarde — als mediaan, want
een halve lading of een eco-programma hoort het beeld niet te bepalen.

Dat verbruik wordt uit het gemeten **vermogen** afgeleid en niet uit de
energieteller: die is cumulatief en de stand bij het begin van de cyclus
is niet bewaard.

**Volledige testsuite**: 1984 tests, allemaal groen.

## v1.62.0 — `grid_cheaper_than_battery` teruggedraaid

**Gemeld** op 12 augustus 11:56, met de modus in bedrijf: "Wat opvalt is
dat er nu voor smart charging is gekozen, er is voldoende zonne energie,
ook als de accu tijdelijk ontlaadt voor bijvoorbeeld het hogere vermogen
van de wasmachine."

De rekensom klopte — 33,1 ct uit de accu tegen 14,3 ct van het net — maar
de conclusie niet. **Drie fouten in één beslissing:**

**1. Bij zonoverschot is de keuze niet accu-tegen-net maar
zon-tegen-net.** En zon is gratis. Het huis kocht 14,3 ct van het net
terwijl diezelfde zon het huis had kunnen voeden. Er stond 1,23 kWh
import op de teller bij 5,28 kWh zon.

**2. De verkeerde kostprijs.** De vergelijking gebruikte de kostprijs van
energie die er ál in zat (23,5 ct). Wat er op dat moment ín ging was
zon, en dat kost niets — de marginale kWh was gratis.

**3. De ergste, en die geldt ook 's nachts: `smart_charging` zet de
piekbuffer uit.** Bij een wasmachine die 2000 W trekt terwijl de zon
1500 W levert, moet het verschil volledig van het net komen, terwijl de
accu op 35% stond. Het gemeten piekvermogen is 2199 W tegen 1600 W
ontlaadvermogen; die buffer is aantoonbaar nodig.

Die derde is niet met deze modus op te lossen. Wat nodig is — "voed het
basisverbruik niet uit de accu, maar pieken wél" — kent de Zendure niet:
`smart_charging` is alles of niets. Dat vraagt om `manual` met een
vermogen dat het basisverbruik dekt, en dat is een ánder mechanisme.

**De vergelijking blijft meerekenen** en staat in de diagnostiek onder
`battery_vs_grid`. Ze stuurt alleen niets meer aan. Juist in de winter,
als de accu uit het net laadt, wordt de vraag interessant — dan is het
prettig dat er dan al cijfers liggen.

De modus `smart_charging` blijft bestaan als bekende optie, met de
controle vooraf uit v1.55.0.

**Volledige testsuite**: 1987 tests, allemaal groen.

## v1.63.0 — "Vandaag" moet ook echt vandaag zijn

**Gemeld** met een Solcast-screenshot ernaast: "De verwachtte kw
zonneenergie kan niet kloppen."

De waarom-kaart zei *"er wordt vandaag nog 28,5 kWh zon verwacht"*,
Solcast meldde **6,63**.

28,5 = 6,6 van vandaag plus ruim 22 van morgen. De planning loopt zover
als er prijzen zijn — de kaart ernaast meldde het zelf: *"€ 6,59 over 32
uur"* — en de samenvatting telt alles bij elkaar op. Daar plakte deze
regel het woord "vandaag" op.

**Derde keer** dat deze horizon een maat betekenisloos maakte, na de
tekortkwartieren (v1.42.0) en de plantoetsing (v1.48.0). Telkens
dezelfde vorm: een maat die klopte bij negen uur vooruit, en die niet is
meegegaan toen die horizon in v1.25.0 verviervoudigde.

De grens wordt nu expliciet meegegeven in plaats van erop te vertrouwen
dat de planning bij middernacht ophoudt. Een test controleert dat er
daadwerkelijk om een grens wordt gevraagd, niet alleen dat het getal
toevallig klopt.

**En dezelfde belofte stond er nog een keer.** De pagina
*Planning-samenvatting* had als kop *"Verwachting voor de rest van de
dag"* terwijl daar dezelfde onbegrensde cijfers staan. Die kop is nu
*"Verwachting over de hele planning"*, met een regel erbij die zegt hoe
ver er gekeken wordt.

**Volledige testsuite**: 1988 tests, allemaal groen.

## v1.64.0 — Celspanningsverschil hangt van de accustand af

**Gemeld**: "Accumodule 1: celspanningsverschil 0.190 V - hoger dan
gebruikelijk. Dit lijkt een standaard iets te zijn, gebeurt altijd nabij
laden rond 100% SOC."

Klopt — en het stond al in de code, drie regels boven de drempel die het
negeerde:

> *"LFP heeft een vlakke spanningscurve in het midden en steile
> uiteinden, waardoor het celspanningsverschil sterk SoC-afhankelijk is.
> (…) De absolute delta wordt daarom per SoC-bucket bijgehouden."*

Die vakken werden bijgehouden **en nergens gebruikt**: de waarschuwing
vergeleek gewoon met een vaste drempel van 0,10 V. De eigen metingen
bevestigen je waarneming: dezelfde module 1 staat in het vak van 70% op
**0,00 tot 0,03 V**.

**Nu:**

| Accustand | Beoordeling |
|---|---|
| 20–90% (vlak) | de absolute drempels, zoals voorheen |
| Buiten dat bereik | vergeleken met wat voor **deze module** bij **deze stand** gebruikelijk is |

Bij minder dan twintig metingen in zo'n vak wordt er niets gemeld —
liever een gemiste melding dan er elke avond een die niets betekent, want
dan leert het overzicht je hem te negeren.

De melding verdwijnt dus niet, maar wordt eerlijk: staat module 1 bij een
volle accu op 0,19 terwijl 0,05 gebruikelijk is, dan hoor je dat nog
steeds. En de **differentiële** vergelijking (module tegen de andere
modules op hetzelfde moment) blijft onveranderd — die heeft geen last van
de accustand, want alle modules zitten op vrijwel dezelfde stand.

**Volledige testsuite**: 1994 tests, allemaal groen.

## v1.65.0 — Opgewekt én voorspeld

**Gevraagd**: "xx kw opgewekt vandaag (voorspeld was xx kw). Kun je het
'voorspeld was xx kw' stuk toevoegen? Ik wil de voorspelling van de
integratie."

De tegel zei alleen wat er uit kwam en hoeveel de voorspelling er
gemiddeld naast zit — maar niet waar die 9% vandaag op sloeg. Nu:

> **PV / zon** — 16,4 kWh opgewekt vandaag (voorspeld 23,0). De
> voorspelling zit er over 7 dagen gemiddeld 9% naast.

Nadrukkelijk de **eigen** verwachting, niet de kale Solcast-waarde: die
wordt gecorrigeerd met de geleerde bias per uur en de live teller. Juist
dat verschil maakt "zit er x% naast" een zinnig getal.

**Twee bronnen, in deze volgorde.** De momentopname van 08:00 als die er
is — dat is een echte *"was"*, want dat getal stond vast voordat de dag
zich ontvouwde. Anders wat er nu nog verwacht wordt plus wat er al ligt;
dat schuift mee met de dag en is dus geen eerlijke voorspelling meer,
maar het is het beste dat er is en de herkomst staat erbij.

Op de PV-pagina staat het uitgebreider, met de afwijking van vandaag en
waar het getal vandaan komt.

**Volledige testsuite**: 2001 tests, allemaal groen.

## v1.66.0 — Een volle accu vangt niets meer op

**Gemeld**: "Zonoverschot gaat de accu in? Kan niet want die is vol :)"

Klopt. Die regel stond er onvoorwaardelijk, ook bij een accu op 100%.
Dan gaat het overschot het net op — en dat is een heel ander verhaal dan
"de accu vangt het op".

Nu:

> **Waarom laad je nu?**
> → de accu is vol; het zonoverschot gaat het net op

En is er wél ruimte, dan staat erbij hoeveel: *"er is zonoverschot en
dat gaat de accu in (nog 3,4 kWh ruimte)"*. Geen ruimte kunnen bepalen
is iets anders dan geen ruimte hebben — dan blijft de regel vaag in
plaats van onwaar.

**Volledige testsuite**: 2005 tests, allemaal groen.

## v1.67.0 — De weerbronnenmelding van de landingspagina af

**Gemeld**: "Deze zie ik altijd op de landingspagina, nu niet meer nodig
toch?"

Klopt. In **v1.9.2** kwam die "vergelijkbaar"-variant erbij met een goede
reden: stilte was dubbelzinnig — geen verschil, of nog niet genoeg
gemeten? Een sterke indruk op basis van losse momenten ("die ene zit er
altijd naast") verdient een cijfer om tegen te houden.

Maar die boodschap heb je **één keer** nodig, op het moment dat je die
vraag stelt. Permanent op de landingspagina wordt hij behang — en dan
leest niemand meer de regel eronder die er wél toe doet.

**Alleen het actiebare geval blijft:** verschillen de bronnen 20
procentpunt of meer, dan staat er nog steeds een advies om er één uit de
configuratie te halen. De geruststelling is verhuisd naar de
**weerpagina**, waar je komt als je de vraag hebt — met het verschil in
procentpunten erbij.

**Volledige testsuite**: 2005 tests, allemaal groen.

## v1.68.0 — Koken om half vijf zegt niets over 03:00

**Gemeld**: "Nee: 34 kwartier(en) aan het net — morgen 01:00-09:30.
Laagste 10%, eind 10%, € -2.0 over 31 uur." En terecht: "maar hij moet
van 01:00 tot 09:30 toch juist de woning voorzien van stroom?"

Ja — en die 34 kwartieren betekenden dat hij dat volgens het plan **niet
kon**.

### Wat er misging

De export van 16:30 laat het zien: het plan rekende met **1,26 tot 1,38
kW** terwijl het geleerde profiel **0,20 tot 0,41 kW** zegt. Verbruik
over de hele planning: 41,2 kWh.

De oorzaak is de live verbruikscorrectie. Om 16:30 werd er gekookt, dus
die correctie zat op zijn maximum van **5,0×** — en die factor werd
toegepast op de **hele planning van 31 uur**, inclusief 03:00 vannacht en
morgenmiddag.

Die correctie is goed bedoeld en nodig: draait de airco nu, dan zegt het
gemiddelde van vorige week te weinig. Maar dat je om half vijf kookt,
zegt niets over drie uur 's nachts.

### Nu

Vol gewicht in het eerste uur, daarna uitdovend tot niets na vier uur:

| Horizon | Was | Wordt |
|---|---|---|
| 1 uur | 5,00× | **5,00×** |
| 4 uur | 5,00× | 3,50× |
| 8 uur | 5,00× | 2,25× |
| 31 uur | 5,00× | **1,32×** |

Naar boven afwijken blijft de veilige kant — dan houdt de accu meer
achter de hand — maar niet vijf keer het hele etmaal.

Dit raakt zowel de kwartierplanning als de wandeling naar het diepste
tekort, die tot het goedkope blok loopt (vannacht zeventien uur).

**Vierde keer dat deze horizon een maat kapotmaakte**, na de
tekortkwartieren (v1.42.0), de plantoetsing (v1.48.0) en de
zonverwachting (v1.63.0). Steeds dezelfde vorm: iets dat klopt voor het
nabije moment, toegepast op een venster dat sinds v1.25.0 vier keer zo
lang is.

**Volledige testsuite**: 2010 tests, allemaal groen.

## v1.69.0 — De rest van de codebase nagelopen op dezelfde fout

**Gevraagd**: "Gaat het misschien op nog meer plekken kapot?"

Vier keer was het al misgegaan met dezelfde vorm — iets dat klopt voor
één dag of één moment, toegepast op een horizon die sinds v1.25.0 vier
keer zo lang is. Dus systematisch nagelopen op alle plekken waar een
periode of een reeks als geheel wordt gebruikt.

**Eén echte vondst.** De drempel voor "goedkoop blok" in de
kwartierplanning werd berekend over **alle** beschikbare prijzen, dus
over twee dagen tegelijk. Heeft morgen een extreme piek en vandaag niet,
dan rekt die piek de range op en gelden er vandaag ineens veel meer
kwartieren als goedkoop.

Op de reeks van 12 augustus: gedeeld 27,1 ct tegen 26,3 voor vandaag en
27,8 voor morgen — klein verschil. Maar met de prijzen van 11 augustus
(piek 38 ct) zou de gedeelde drempel 27,1 ct zijn geweest tegen **19,8**
voor die dag zelf: een derde hoger. Nu per dag.

**Wat schoon bleek**, en dat is het vermelden waard:

- de dure-prijsdrempel en de telling van dure kwartieren filteren allebei
  al expliciet op `now.date()`
- de zoncorrectie is sinds v1.27.0 op het huidige moment geijkt en geldt
  alleen voor nog komende uren van vandaag
- de slijtage- en opbrengstcijfers gaan over de hele planning én worden
  zo genoemd — daar staat geen "vandaag" bij
- de netto-opbrengst en de slijtagekosten hanteren dezelfde periode, dus
  ze zijn onderling consistent

**Volledige testsuite**: 2012 tests, allemaal groen.

## v1.70.0 — Terugrekenen vanaf de eindtijd

**Gemeld**: "wasmachine heeft inderdaad alleen een eindtijd."

Dat legde een zwakte in v1.61.0 bloot. Die eindtijd als moment nemen
plaatst het verbruik **uren te laat**: bij een programma dat om 07:00
klaar is en anderhalf uur duurt, wordt het water rond 05:30 verwarmd.
Voor een reserve die de nacht moet overbruggen valt dat verbruik dan net
buiten het venster — precies de verkeerde kant op.

De cyclusduur wordt al geleerd. Is die er en plausibel, dan wordt
daarmee teruggerekend naar het startmoment.

**Maar niet blind.** De geleerde reeks bevat ook korte fragmenten — bij
deze installatie 8 en 10 minuten tussen echte cycli van 60 tot 80. Onder
de dertig minuten is de duur niet te vertrouwen en blijft de eindtijd
staan, mét kanttekening. Een duur verzinnen is erger dan een moment dat
een uur naast zit.

Ligt het berekende begin al in het verleden, dan draait de machine nu
al — en dan zit het verbruik in de live meting. Dan wordt hij niet
opnieuw gepland, anders telt hij dubbel.

Op de kaart staat nu ook de eindtijd: *"wasmachine | 21:40 (klaar 23:00)
| 0,8 | schatting"*.

**Volledige testsuite**: 2015 tests, allemaal groen.

## v1.71.0 — De zonstand wordt nagerekend

**Gevraagd**: "Kunnen we op een of andere manier verifieren dat de
azimuth correct wordt uitgelezen?"

Ja — de zonstand volgt uit tijd en plaats, en Home Assistant kent de
coördinaten. Dat geeft een onafhankelijke toets die niets van de sensor
aanneemt.

**Meteen toegepast op de melding van 12 augustus 17:30:** gemeten
**248,05°**, berekend **252,9°** voor Lochem. Verschil 4,9 graden — en
dat is precies wat een aflezing van een paar minuten eerder oplevert,
want de zon draait 15 graden per uur. De sensor klopt dus.

De controle draait nu permanent en meldt één van vier dingen:

| | |
|---|---|
| verschil ≤ 5° | betrouwbaar |
| verschil > 5° | onbetrouwbaar, met beide getallen erbij |
| buiten 0–360 | "dit is geen azimut" — vangt graden/radialen door elkaar |
| geen coördinaten | niet toetsbaar |

De draaiing over middernacht wordt goed afgehandeld: 359 en 1 graad
schelen twee graden, geen 358 — anders zou elke nacht een alarm geven.

Een afwijking landt in de **doen**-stapel, want wachten helpt daar niet.
Op de Meetkwaliteit-pagina staat de vergelijking met beide getallen.

De berekening is de standaard NOAA-benadering, nauwkeurig tot ongeveer
een tiende graad, en zonder extra afhankelijkheid.

**Volledige testsuite**: 2023 tests, allemaal groen.

## v1.72.0 — De knop "Nu laden" werkte niet

**Gemeld**: "De nu laden button geeft een fout: *'EnergyManagementSystem
Coordinator' object has no attribute 'async_request_refresh'*."

Die methode hoort bij `DataUpdateCoordinator`; deze coordinator is er
geen. De bestaande schakelaars roepen `async_update()` aan — dat had
deze ook moeten doen.

**Het ergste is dat alle 2023 tests groen bleven.** De tests toetsten de
coordinator-functies (`activeer_nu_laden`, aftelling, herstart), maar
nooit de schakelaar zelf. Het pad van "knop indrukken" tot "uitstel
opzij" was nergens gedekt.

Twee tests erbij die dat afdekken:

- de schakelaar wordt nu echt ingedrukt en losgelaten, met controle dat
  de knop daarna aan respectievelijk uit staat;
- een brede toets die van **elk** entiteitsbestand nagaat dat alle
  aangeroepen coordinator-methodes ook echt bestaan. Zonder die toets
  komt zoiets pas boven water als je de knop indrukt — en dan staat er
  een rode melding in de gebruikersinterface in plaats van een rode
  test.

De knop past de nieuwe stand nu ook meteen toe in plaats van pas bij de
volgende tick.

**Volledige testsuite**: 2026 tests, allemaal groen.

## v1.73.0 — Niet koelen wat niet warm is

**Gemeld**: "De koeling van de accu is nu wel heel veel aan, is dit
daadwerkelijk zoveel nodig? (…) Ik kan me voorstellen dat hij pas bij ca.
25 graden actief gaat koelen?"

Beide vermoedens kloppen, en er zat nog een tweede fout naast.

### Geen ondergrens

Drie van de vier aanzetregels kijken naar het **verschil met buiten** of
naar het **vermogen**, en maar één naar de absolute temperatuur. Op een
frisse ochtend van 16,5 °C is de accu bijna altijd twee graden warmer —
dat is normale afvoerwarmte, geen probleem.

In de export van 13 augustus draaide de ventilator bij **23 °C**, met
als reden *"1203W door de accu en al 3,0 °C boven buiten"*.

Lithium-ijzerfosfaat komt pas boven ongeveer 35 °C in het gebied waar
veroudering merkbaar versnelt. Onder **25 °C** wordt er nu niet meer
gekoeld, wat de andere regels ook zeggen.

### En hij ging uit op het slechtste moment

De uitschakelregel keek naar het verschil met buiten. Op 12 augustus
15:27: *"accu 32,0 °C, nog maar 1,9 °C boven buiten"* — ventilator uit,
bij het warmste punt van die dag, omdat het buiten óók warm was.
Precies andersom.

Boven **30 °C** blijft de ventilator nu draaien, ongeacht het verschil
met buiten. Dezelfde grens als waarboven de verouderingsdrijvers de uren
tellen (v1.59.0), zodat "warm" overal hetzelfde betekent.

### Effect

Nagerekend op de eigen geschiedenis: van de tien aanzetmomenten vervalt
er één (11 augustus 10:38, 23 °C bij 1958 W) — maar dat is de bovengrens
van het effect, want de geschiedenis legt alleen *wisselingen* vast, niet
hoe lang hij daarna doorliep. Het uitschakelen bij 32 °C is de zwaarste
van de twee.

**Zeven tests erbij**, gebaseerd op de werkelijk gelogde gevallen. Ook
hier bleven alle 2026 bestaande tests groen: die dekten de vier
aanzetregels apart, maar nooit een koude accu.

**Volledige testsuite**: 2033 tests, allemaal groen.

## v1.74.0 — De plantoetsing rekende met gewiste tellers

**Gevraagd**: "graag volledige controle, dus alles wat te controleren
valt."

Twee fouten gevonden, allebei in de plantoetsing en allebei van mij.

### Zon: −20,82 kWh

De toetsing meldde *"zon −1190% (minder dan gedacht)"* met een
werkelijke opbrengst van **−20,82 kWh**. Dat getal is precies de
negatieve stand van de momentopname.

De oorzaak is een volgordefout: `pv_production_today_kwh` en de
kostentellers worden bij de dagwissel op nul gezet door een routine die
**eerder** in de tick draait. De toetsing rekende dus 0 (nieuwe dag) min
20,82 (stand bij de opname). Alle drie de dagtellers hadden dat — zon,
import en opbrengst.

De eindstand van de laatste tick van die dag wordt nu vastgehouden en
gebruikt.

### De momentopname werd bij elke herstart weggegooid

De opnames stonden op **18:00** en **20:19** in plaats van 08:00,
telkens vlak na een herstart. `_plan_review_day_key` werd niet bewaard,
dus stond hij na een herstart op `None` — en dan wiste de dagwisselregel
de opname van vanochtend.

Een opname om 18:00 vergelijkt de **rest** van de dag (1,91 kWh zon) met
de werkelijkheid; dat zegt nauwelijks iets. Nu draagt de opname zelf de
datum en blijft hij staan. Stond er nog een opname van gisteren omdat de
integratie 's nachts uit was, dan wordt die alsnog afgesloten in plaats
van stilzwijgend verdwijnen.

Als datumveld bewaard, niet als tekst — anders is de vergelijking met de
huidige dag altijd ongelijk, en dat is een valkuil die al in de code
staat beschreven.

**Volledige testsuite**: 2037 tests, allemaal groen.

## v1.75.0 — Wat de saldering kost, gemeten in plaats van geschat

**Gevraagd**: "Kun je dat nu bekijken? Saldering is als bekend nu nog
actief, en stopt na 31-12-2026."

De proefstand meldde *"€ 0,61 in plaats van € 3,90"* — een daling van
84%. Dat klopt niet.

### De denkfout

Ik nam aan dat het kale tarief een vast **deel** van de belaste prijs is
(23%). Maar energiebelasting plus BTW is een vast **bedrag** per kWh:

| Belaste prijs | Kaal | Aandeel |
|---|---|---|
| 30 ct | 19 ct | 63% |
| 13 ct | 1,9 ct | 15% |

Eén breuk kan dat niet vangen. En 23% was er bovendien ver naast: bij
deze aansluiting is het gemeten verschil **11,1 ct/kWh**.

### Nu gemeten

Beide prijsvelden zitten in dezelfde sensor, dus het verschil valt te
meten in plaats van te schatten — als mediaan, zodat een kwartier met
een ontbrekend veld de uitkomst niet verpest.

Met de echte gegevens van 13 augustus:

> **€ 2,46 in plaats van € 3,90.** 13,0 kWh gaat het net op — nu 32,4 ct
> per kWh waard, straks 19,3 ct.

Dus **een derde eraf**, niet vijf zesde. Nog steeds fors, maar een heel
ander verhaal.

### Wat dit betekent voor 2027

Elke kWh die je 's avonds uit de accu gebruikt in plaats van 's middags
terug te leveren, wordt straks 13 ct meer waard. Dat maakt de vraag *"of
energie überhaupt door de accu moet"* — proefstandkandidaat 1 — een stuk
scherper: de slijtage van 4,7 ct blijft gelijk, de winst per opgeslagen
kWh stijgt.

En het maakt de rekensom omgekeerd óók scherper: op een dag als vandaag
is 21 kWh zon tegen 5,8 kWh verbruik, dus het meeste gaat hoe dan ook
het net op. Daar valt met de accu weinig aan te doen — dat is een
kwestie van meer opslag of meer verbruik verplaatsen.

**Volledige testsuite**: 2042 tests, allemaal groen.

## v1.76.0 — Volledige controle: vier vondsten

**Gevraagd**: "Kun je nog een keer de diagnostiek nakijken (…) ik wil er
zeker van zijn dat nu alles maar dan ook echt alles klopt."

Alles nagelopen: 247 velden, alle 22 null-waarden en 12 lege
verzamelingen verklaard, elke planregel op fysieke plausibiliteit
getoetst, en de kerncijfers tegen elkaar nagerekend. Vier fouten.

### 1. Zelfconsumptie 100% bij 1,04 kWh teruglevering

De berekening trok de hele **dagontlading** van de export af. Omdat de
accu die dag 2,47 kWh had geleverd, bleef er niets over als zon-export.

Die aanname is achteraf niet toetsbaar: met alleen dagtotalen is "alle
export kwam uit de accu" net zo consistent met de energiebalans als
"alle export was zon". Beide passen precies.

Op het moment zélf is het wél te zien: er kan niet meer accu-energie het
net op gaan dan de accu op dat moment levert. Dezelfde vergelijking, maar
per tick — over een hele dag dekt de ontlading van vannacht de zon-export
van vanmiddag af, terwijl die twee niets met elkaar te maken hebben.

Op de gecontroleerde cijfers: **54,4%** in plaats van 100%.

### 2. Twee tellingen van hetzelfde, met verschillende uitkomsten

De cyclusteller deelt de doorzet door de **nominale** capaciteit (8,6
kWh) en kwam op 5,5 cycli; de slijtageberekening gebruikte de
**bruikbare** 7,74 en kwam op 6,1.

De nominale is hier de juiste — de 6000 cycli van de fabrikant zijn
daarop gespecificeerd. Slijtage gaat van 4,7 naar **4,2 ct/kWh**.

### 3. Mijn koeldrempel van v1.73.0 miste hysterese

Twintig schakelingen in een uur, sommige binnen drie seconden. De
temperatuursensor meldt hele graden en wipte tussen 24 en 25 — precies
op de nieuwe grens.

Nu 26 aan / 24 uit, zoals de rest van dat bestand het al deed. Het
bestand zegt het zelf: *"bewust hysterese tussen aan- en uitschakelen
(…) zonder die marge zou de ventilator rond een enkele drempel blijven
pendelen."*

### 4. Een uitgezette melding vulde de geschiedenis

41 van de 200 regels waren accukoeling, waarvan 31 op één ochtend — bij
een soort die **uitstaat**, dus er ging niets naar de telefoon.

`is_notification_allowed` toetst eerst de schakelaar en komt bij een
uitgezette soort nooit aan het dempingsvenster toe. De reden is dan
"deze melding staat uit" en niet "gedempt", dus werd elke herhaling
alsnog vastgelegd — en duwde echte meldingen uit het venster van 200.

### En de export zelf was incompleet

Drie dingen bleken niet na te kijken omdat ze niet in de diagnostiek
stonden. Een ontbrekend veld ziet er hetzelfde uit als een veld dat op
nul staat — dat verschil kostte bij de azimut al een verkeerde
conclusie. Nu staan ze erin, met een test die dat vasthoudt.

### Wat goed bleek

- de energiebalans van de planning sluit tot op 0,24 kWh, precies het
  laadverlies bij 90%
- geen enkele planregel fysiek onmogelijk: geen SoC buiten bereik, geen
  sprong groter dan het laadvermogen toelaat
- zelfvoorziening 84,8% klopt exact met de narekening
- zonstandcontrole 0,4° verschil
- geen interne fouten, geen plausibiliteitswaarschuwingen, doen-stapel
  leeg

**Volledige testsuite**: 2058 tests, allemaal groen.

## v1.77.0 — Een README als visitekaartje

**Gevraagd**: "Ik wil een readme die er professioneel uitziet. Mogelijk
willen anderen in de toekomst de integratie ook gaan gebruiken."

De README was **12.389 regels**: bij elke versie was het verhaal
erbovenop geplakt, waardoor de installatie-instructie ergens op regel 37
begon en daarna 256 hoofdstukken volgden. Waardevol materiaal, maar niet
als eerste indruk — iemand die overweegt de integratie te gebruiken haakt
af voordat hij bij de configuratie is.

**Nu 434 regels**, opgebouwd zoals iemand hem leest: wat doet het, wat
heb je nodig, hoe installeer je het, hoe stel je het in, en pas daarna de
werking.

Toegevoegd:

- badges voor versie, Home Assistant-eis, testaantal en licentie
- een inhoudsopgave
- een korte Engelse samenvatting bovenaan, met de reden waarom de rest
  Nederlands is: de integratie is specifiek op de Nederlandse markt
  gericht (kwartierprijzen, salderingsregeling, meldingen in het
  Nederlands en Achterhoeks)
- een tabel met alle kenmerken, gegroepeerd naar aansturing, zelflerend
  en bewaking
- uitklapbare probleemoplossing
- een **MIT-licentie** — die ontbrak volledig, en zonder licentie mag
  niemand het gebruiken

De 11.873 regels ontwikkelgeschiedenis staan nu in
[`docs/ONTWIKKELING.md`](docs/ONTWIKKELING.md). Niet weggegooid: die
verhalen leggen vast wáárom een regel er is, en dat is vaak nuttiger dan
wat er staat.

**Eerlijk over de grenzen**, want dat hoort iemand vóór de installatie te
weten: er staat expliciet op welke opstelling dit getest is, dat andere
combinaties niet getest zijn, en dat `Learning only` bestaat om eerst mee
te kijken zonder dat er iets geschakeld wordt.

**Zeven tests erbij** die de vorm bewaken: de README mag niet opnieuw een
dagboek worden, de geschiedenis moet ergens bewaard blijven, de
beginnerssecties moeten er zijn, er moet een licentie zijn, en de
versiebadge moet met het manifest overeenkomen — een badge die achterloopt
is erger dan geen badge.

**Volledige testsuite**: 2065 tests, allemaal groen.

## v1.78.0 — De aanwezigheidsdrempel van 10 naar 20 minuten

**Gemeld**: "De aanwezigheid sensor wijzigt te snel naar weg, misschien
de tijd voor analyse verlengen?"

### Eerst een verkeerde verklaring van mijn kant

Ik dacht dat iemand naar de douche kon lopen zonder langs een sensor te
komen. Weerlegd: *"als je de doucheruimte in loopt loop je langs de
bewegingssensor op de overloop"*. Het gaat dus niet om ontbrekende
dekking maar puur om de lengte van de stilte.

### Wat de eigen tijdlijn zegt

Vier dagen, 24 weg-blokken. **Acht daarvan duurden precies vijf tot zeven
minuten** — dat is geflikker, geen vertrek. Daarboven zit een gat, en pas
bij een kwartier beginnen de echte blokken.

| Drempel | Blokken die vervallen |
|---|---|
| 10 min | 1 van de 24 |
| 15 min | 8 |
| **20 min** | **10** |
| 25 min | 13 |
| 45 min | 18 |

De aanname achter de tien minuten was *"wie stil zit, kijkt tv"*. Die
gaat 's avonds op de bank op, maar niet 's ochtends: de blokken van
07:00-07:49 en 07:00-07:34 vielen precies in het uur na het opstaan.

**Twintig minuten** haalt het geflikker weg en laat de blokken van
twintig minuten en langer staan — die kunnen een echt vertrek zijn.

### En instelbaar

Hoe lang stilte normaal is hangt af van hoeveel sensoren er hangen en hoe
het huis loopt; dat valt niet met één getal voor iedereen te vangen. Het
nieuwe veld staat bij Configureren, met de standaard als terugvalwaarde —
een leeg `NumberSelector` blokkeert anders het hele formulier, zoals een
bestaande test al bewaakte.

**Volledige testsuite**: 2068 tests, allemaal groen.

## v1.79.0 — Wachten is geen handeling

Gevonden in de export van 13 augustus 12:07: het rendement stond bij
**"vraagt een handeling"** omdat het al 24 uur op de oude methode
draaide.

Maar daar valt niets aan te doen. Het rendement per halve slag heeft
drie meetstukken per kant nodig van minstens 1,5 kWh; die komen vanzelf
zodra de accu een paar keer volledig laadt en ontlaadt.

De terugval-melding uit v1.58.0 zette **elke** langlopende noodloop in de
doen-stapel. Dat onderscheid ontbrak:

| Soort terugval | Waar |
|---|---|
| Sensor zwijgt, attribuut ontbreekt | **doen** — dat lost zichzelf niet op |
| Leerroutine verzamelt nog metingen | **wachten** — dat komt vanzelf |

De doen-stapel kleurt de tegel op de landingspagina rood. Als daar
dingen in staan waar je niets mee kunt, leer je hem negeren — precies
wat er met de tekortmelding en de weerbronnenmelding al gebeurde.

**Volledige testsuite**: 2071 tests, allemaal groen.

## v1.80.0 — De koeling stuurde op de omvormer, niet op de cellen

**Gemeld**: "Ventilatoren zuigen af van de omvormer" en "dat is de juiste
temperatuur van de omvormer".

Dat legt een fout bloot die dieper zat dan de drempels van v1.73.0 en
v1.76.0.

### Alle absolute drempels waren op de verkeerde grootheid geijkt

De redenering in de code stond letterlijk op **celtemperatuur**:
*"lithium-ijzerfosfaat komt boven ongeveer 35 °C in het gebied waar
veroudering versnelt"*. Maar de sensor die de koeling aanstuurt is
`solarflow_2400_ac_hyper_tmp` — de **omvormer**. Vermogenselektronica
draait routinematig boven de 60 °C zonder enig probleem.

In de eigen geschiedenis: tien aanzetmomenten, allemaal tussen **25 en
29 °C omvormertemperatuur**. Voor een omvormer volstrekt normaal. Met de
nieuwe ondergrens van 35 vervallen ze alle tien — terwijl de 38 °C van
13 augustus (2062 W laden, 32 °C buiten) gewoon gekoeld wordt.

| Drempel | Was | Wordt |
|---|---|---|
| Ondergrens (niets te winnen) | 26 °C | **35 °C** |
| Uit onder | 24 °C | 32 °C |
| Onvoorwaardelijk koelen | 35 °C | **50 °C** |
| Doorkoelen ongeacht buiten | 30 °C | 42 °C |

**Deze getallen zijn schattingen**, en dat staat er zo bij. Zendure
publiceert niet bij welke temperatuur de hyper terugregelt, er is geen
sensor die dat meldt, en de eigen reeks (24 tot 38 °C) is te kort om er
een grens uit af te leiden. Wat wél vaststaat is de fysica: een
ventilator kan niet onder de buitentemperatuur koelen — daar zijn de
verschilregels op gebaseerd, en die blijven ongewijzigd.

Er stond bovendien een **tweede, oudere set constanten** onderaan die de
nieuwe overschreef. Dat is de reden waarom `KEEP_RUNNING_ABOVE` op 30
bleef staan terwijl er 42 hoorde te gelden.

### En de verouderingsdrijvers misten hun context

**Gemeld**: "de buitentemperatuur is ook ruim 32 graden."

*"6,0 uur boven 30 °C"* klinkt zorgelijk, maar op een dag waarop het
buiten 32 was is dat onvermijdelijk. Veroudering hangt van de absolute
celtemperatuur af, dus die telling blijft leidend — maar zonder de
buitenwaarde ernaast is niet te zien of het aan de accu lag of aan het
weer, en alleen het eerste valt te beïnvloeden.

Er komen twee getallen bij: **hoogste buitentemperatuur** van die dag, en
**uren dat de cellen warmer waren dan buiten**, met de grootste
oversprong. Op 13 augustus waren de cellen 28 tot 32 °C bij 32 °C buiten
— dus koeler dan de omgeving, en dat is geen accuprobleem.

Alle temperaturen in de koeltests zijn twaalf graden opgehoogd, want die
stonden ook op de celschaal.

**Volledige testsuite**: 2075 tests, allemaal groen.

## v1.81.0 — Een model dat de vensterlengte niet kende

**Gemeld** met een screenshot van de modelnauwkeurigheid:

> Voorspeld 0.33 kWh bij 30.3°C, werkelijk 1.92 kWh (afwijking +476.4%)
> Voorspeld 0.84 kWh bij 18.5°C, werkelijk 1.60 kWh (afwijking +90.7%)

Dat zijn geen meetfouten maar een ontwerpfout van mijn kant.

### Wat er mis was

Het model voorspelde het **totaal** over het ontlaadvenster, terwijl de
lengte van dat venster niet in het model zat. Dat venster loopt van het
begin van het ontladen tot het goedkope blok en duurt de ene nacht drie
uur en de andere veertien — een factor vijf verschil dat de temperatuur
onmogelijk kan verklaren.

De twee metingen hierboven zijn zelfs van **dezelfde nacht**: om 00:00
een venster van bijna niets, om 06:04 een langer stuk. Beide werden
getoetst aan een model dat op volle nachten was gebouwd.

### Nu op gemiddeld vermogen

Vermogen is lengte-onafhankelijk — `night_consumption_history` doet dat
al zo, en de temperatuurregressie had dat vanaf het begin moeten volgen.
Twee nachten met hetzelfde verbruikspatroon geven nu dezelfde meting,
hoe lang het venster ook was.

Daarnaast worden vensters korter dan twee uur helemaal niet meer
vastgelegd: zo'n stuk zegt niets over het nachtverbruik.

De melding noemt nu watt in plaats van kWh, want anders is de afwijking
niet na te rekenen. Reeksen van vóór deze versie dragen kWh over
wisselende vensters; die worden genegeerd in plaats van meegerekend — ze
door elkaar halen zou een model opleveren dat twee grootheden mengt.

**Volledige testsuite**: 2079 tests, allemaal groen.

## v1.82.0 — Dertien komma twee wát?

**Gemeld** met een screenshot van de betrouwbaarheidstabel:

> ✅ betrouwbaar **PV-dagopwek** — 13.21

Een getal zonder eenheid is niet te controleren, en dat is precies waar
die pagina voor bedoeld is.

Het gold niet alleen voor die regel: **de hele tabel** toonde kale
getallen. Rendement, nachtverbruik, sensorgezondheid en het
kostenverschil met de leverancier stonden er net zo bij — en bij
"rendement 82.9" of "nachtverbruik 0.34" is het maar de vraag of je
procenten, kilowatt of kilowattuur leest.

Elke regel draagt nu zijn eenheid: **kWh**, **kW**, **%** of **EUR**.

Twee tests erbij: elke waarde moet een eenheid hebben, en die eenheid
moet uit een bekende verzameling komen — dat vangt een typefout of een
eenheid die niet bij de grootheid past. Plus één die controleert dat de
eenheid ook echt op het scherm komt; hem alleen opslaan lost niets op.

**Volledige testsuite**: 2083 tests, allemaal groen.

## v1.83.0 — "Heb je dit nu overal opgelost?"

Nee, toen niet. v1.82.0 raakte alleen de betrouwbaarheidstabel — de
tabel waar het screenshot vandaan kwam.

Het hele dashboard nagelopen op velden die een hoeveelheid dragen. **Eén
overgebleven geval**: op de witgoedpagina stond het geplande verbruik als
kaal getal, met de eenheid alleen in de kolomkop. Dat werkt zolang je de
kop meeleest, maar bij één regel in een tabel van vier kolommen is dat
te mager. De kop heet nu *Verbruik* en het getal draagt zelf **kWh**.

Ook de sensoren zelf gecontroleerd: elke sensor met een `state_class` of
`device_class` heeft een eenheid. Daar was niets mis.

**Twee tests erbij** die dit blijvend bewaken — één die het complete
dashboard doorzoekt op numerieke velden zonder eenheid, en één die
hetzelfde doet voor de sensoren. Zonder die toetsen was dit een
eenmalige opruiming geweest die bij de volgende toevoeging weer
scheefloopt.

**Volledige testsuite**: 2085 tests, allemaal groen.

## v1.84.0 — Nog twee regels zonder eenheid

**Gevraagd**: "En zijn er nog meer van dit soort schoonheidsfoutjes?"

Systematisch gezocht in plaats van gegokt. Zes categorieën nagelopen:
getallen zonder eenheid, ongeronde waarden, taalmenging, `None` in
gebruikersteksten, typografie, en waarden die niet bij hun eenheid
passen.

**Twee vondsten**, allebei in dezelfde tabel als vorige keer:

- **Meetfrequentie per sensor** — stond als kaal `97.3`
- **Weerbron-betrouwbaarheid** — stond als kaal `84.5`

Allebei procenten. Ze vielen buiten de eerste ronde omdat ze pas in de
tabel verschijnen zódra er genoeg metingen zijn — en de test bouwde een
lege coordinator, waarin die regels er simpelweg niet stonden. De test is
uitgebreid met meetgegevens, zodat hij het hele overzicht toetst en niet
de helft.

### Wat schoon bleek

- **Ongeronde getallen**: geen enkele in de dashboardattributen. Vier
  decimalen in `battery_vs_grid`, maar dat is diagnostiek en daar is
  precisie juist nuttig.
- **Taalmenging**: alleen "reserve", en dat is ook Nederlands.
- **`None` in teksten**: drie f-strings met optionele velden, alle drie
  achter een controle op aanwezigheid.
- **Typografie**: alle treffers zaten in commentaar en
  Engelstalige foutmeldingen, niet in wat jij te zien krijgt.
- **Sensoren**: elke sensor met een `state_class` heeft een eenheid.

### Eén ding bewust níet aangepakt

De markdown-tabellen tonen `13.21` met een **punt**, terwijl Home
Assistant zelf `13,21` toont. Dat is een echte inconsistentie binnen
dezelfde gebruikersinterface, maar het repareren vraagt een filter op
elke waarde in vijfentwintig kaarten — veel wijzigingen met kans op
nieuwe fouten, voor een verschil dat niemand verkeerd zal lezen. Als je
het toch wilt, is het een aparte, geïsoleerde ronde waard.

**Volledige testsuite**: 2085 tests, allemaal groen.

## v1.85.0 — Ruis die als trend werd getoond

**Gevraagd**: "Laatste laadcyclus 56.4%, daarvoor 97.6% (-41.2
procentpunt). (…) Die 56.4% is toch vaag, 10 → 100% is toch altijd 90%?"

Twee dingen, en het tweede is een fout in de weergave.

### Rendement is niet de accustand

Van 10 naar 100% is 90 **procentpunt accustand**. Rendement is iets
anders: energie eruit gedeeld door energie erin. Je stopt er 10 kWh in
en haalt er 9 uit — dat is 90% rendement, en de stand ging in beide
gevallen van 10 naar 100.

### Maar die 56,4% is inderdaad geen rendement

Hij komt uit de **oude** methode, die een venster afsloot zodra er 1 kWh
geladen was — ongeacht of de slag klaar was. Die grens valt willekeurig
middenin een cyclus. Vandaar de reeks:

    95,5 — 76,9 — 74,2 — 82,9 — 83,2 — 97,6 — 56,4

Van 56 tot 98 procent. Dat kán een lithium-ijzerfosfaataccu niet doen.
Het zijn geen rendementen maar afkapfouten.

De kaart toonde die losse waarden mét een verschil van **−41,2
procentpunt** tussen twee afkapfouten: ruis, gepresenteerd als signaal.

**Nu** leest de kaart de halve-slag-reeksen, die wél per stuk betekenis
hebben. Zolang die er nog niet zijn staat er wat er aan de hand is — dat
de oude reeks per cyclus niet te lezen is en alleen de mediaan iets
zegt.

**En op de vraag of het een doorlopende meting is:** ja. Een stuk loopt
tot de accu van richting draait, niet per dag. Draait hij op één dag
drie keer om, dan zijn dat drie metingen; gaat hij twee dagen dezelfde
kant op, dan is dat er één. Dat staat nu op de kaart.

De kaart is verhuisd van de landingspagina naar de rendementspagina — de
tegel met de mediaan blijft op het overzicht, de uitleg hoort bij de
details. En "Wat veroudering versnelt" heeft een eigen subview gekregen,
want de rendementspagina liep daarmee over de leesbaarheidsgrens.

**Volledige testsuite**: 2088 tests, allemaal groen.

## v1.86.0 — Twee reserves die elkaar tegenwerkten

**Gevraagd** na de melding *"Den accu haalt de nacht neet"*: "Maar dan
worden toch simpelweg de manual ontlaadkwartieren tegen een hoge prijs
gereduceerd om de nacht te halen?"

Precies. En dat gebeurde niet, want er waren **twee verschillende
reserves** in omloop.

| | Marge | Achterhouden |
|---|---|---|
| Ontlaadreserve | **40%** | 5,16 kWh |
| Verkooptoets | vaste 15% | 4,24 kWh |

Die 40% is niet willekeurig: 10% basis, plus **15% wegens drie
tekortdagen**, plus 15% voor de onbeschermde nacht na een duur kwartier.
Precies de bonus die na een tekort wordt opgebouwd om herhaling te
voorkomen.

Maar de verkooptoets kende die bonus niet en liet los bij 4,24 kWh — en
verkocht dus **exact de buffer weg die de tekortbonus had opgebouwd**.

Dat is een lus: tekortdag → bonus verhoogt de reserve → verkooptoets
negeert de bonus → volgende tekortdag. Dat verklaart waarom "3
onverwachte tekortdagen" al dagen bleef staan terwijl de zelfcorrectie
had moeten werken.

**Nu delen beide kanten dezelfde marge.** Met de cijfers van 13 augustus
17:05 gaat het vrij te verkopen deel van 3,54 naar **2,62 kWh** — zo'n
drie kwartieren minder verkopen vanavond, precies wat je voorstelde.

De oude vaste factor blijft de ondergrens: daalt de zelfcorrigerende
marge na dagen met overschot onder de 15%, dan wint 15%. Deze wijziging
mag de verkooptoets ruimer maken dan hij ooit was.

**Volledige testsuite**: 2092 tests, allemaal groen.

## v1.87.0 — "Waar zie ik die 40?"

Nergens. Die stond alleen in de diagnostiek-export onder
`last_reserve_margin_breakdown`.

En dat is precies waarom de lus uit v1.86.0 dagen kon doorlopen: de marge
liep op van 25 naar 40% wegens tekortdagen, terwijl de verkooptoets dat
getal negeerde. **Een zelfcorrigerend mechanisme dat zichzelf niet laat
zien, is niet te controleren** — noch door jou, noch door mij.

Nieuwe subview **Reservemarge**, bereikbaar vanaf de planningspagina:

| Onderdeel | % | Soort |
|---|---|---|
| Basis | 10 | vast |
| Tekortdagen (3 recent) | 15 | dynamisch |
| Onbeschermde nacht na een duur kwartier | 15 | vast |

Met daarbij hoeveel er vast is en hoeveel beweegt. Dat is het antwoord op
de vraag erachter — of 40% niet veel is. **Vijfentwintig procentpunt is
structureel**; alleen de tekortbonus beweegt, met 5 procentpunt per
tekortdag omhoog en 3 per overschotdag omlaag.

Regels op nul worden weggelaten: die zeggen niets en maken de tabel
alleen langer.

**Volledige testsuite**: 2096 tests, allemaal groen.

## v1.88.0 — De derde plek

**Gemeld** direct na de installatie van v1.87.0: "Krijg de melding na
installatie direct weer."

Terecht, en het is mijn fout. In v1.86.0 heb ik alleen de
**verkooptoets** gelijkgetrokken. Maar de kwartierplanning simuleert zijn
**eigen** reserve — en die stond nog op de vaste 1,15.

De simulatie plande dus meer verkoop dan de aansturing daadwerkelijk zou
toestaan, en de tekortmelding leest precies die simulatie. Vandaar dat de
melding meteen terugkwam, zij het met 11 in plaats van 13 kwartieren.

**Dezelfde marge stond op drie plekken los gedefinieerd:**

| Plek | Was | Nu |
|---|---|---|
| Ontlaadreserve | dynamisch, 40% | dynamisch |
| Verkooptoets | vast 15% | dezelfde dynamische |
| Kwartierplanning | vast 15% | dezelfde dynamische |

Alle drie lopen nu via `_reserve_margin_factor()`, met de vaste factor
alleen als **ondergrens**.

Een test bewaakt dat: zodra de vaste factor ergens rechtstreeks wordt
toegepast in plaats van als ondergrens onder de dynamische marge, valt
hij om. Zonder die toets was dit een derde ronde geworden na een vierde
plek.

Met de cijfers van vanavond: de simulatie houdt 5,16 kWh achter in plaats
van 4,24, waardoor er 2,62 kWh vrij te verkopen blijft in plaats van
3,47 — ongeveer drie kwartieren minder.

**Volledige testsuite**: 2098 tests, allemaal groen.

## v1.89.0 — Het lag niet aan de reserve

Na drie reparaties aan de reserve bleef de tekortmelding terugkomen — nu
met 8 kwartieren. De reserve deed inmiddels wél zijn werk: 5,05 kWh
achterhouden in plaats van 4,24, en één verkoopkwartier minder.

Maar de oorzaak zat ergens anders.

### Plan en reserve rekenden met verschillend verbruik

| | Verbruik vannacht |
|---|---|
| Geleerd profiel | 0,213 kW |
| Reserve-wandeling | 0,322 kW |
| **Kwartierplanning** | **0,428 kW** |

Twee mechanismen die hetzelfde horen te berekenen, met een verschil van
een derde. De planning zag daardoor een tekort dat de reserve niet zag.

### De uitdemping mat het verkeerde

In v1.68.0 heb ik de live verbruikscorrectie laten uitdoven over de
horizon — vol gewicht in het eerste uur, na vier uur niets. Maar die
uitdemping keek naar **de lengte van het gevraagde venster**, niet naar
de afstand tot nu.

De kwartierplanning vraagt om een schatting **per kwartier**. Een venster
van vijftien minuten is korter dan het volle-gewichtvenster, dus kreeg
elk kwartier de volle correctie van 5,0× — ook een kwartier van
morgenochtend zeven uur.

De reserve-wandeling vraagt om één venster van zeventien uur en kreeg
daardoor wél de uitgedoofde waarde. Vandaar het verschil.

**Nu telt de afstand van nu tot dat moment.** Een kwartier over veertien
uur krijgt geen correctie meer, of het nu apart of als onderdeel van een
groter venster wordt opgevraagd. Een test controleert dat de som van de
losse kwartieren gelijk is aan de schatting over het hele venster — dat
is precies wat er misging.

**Volledige testsuite**: 2101 tests, allemaal groen.

## v1.90.0 — Zelfconsumptie per periode, en het contractjaar

**Gevraagd**: "Misschien zelfconsumptie per dag/week/maand/jaar?" en
"Tevens lijkt het me handig dat de start van mijn contract bij Zonneplan
ingevoerd kan worden zodat ik precies het gebeuren voor mijn contractjaar
kan zien."

Daaraan ging een scherpere vraag vooraf: *"de zonne-energie van gisteren,
opgeslagen in de batterij, is vannacht gebruikt — dat is toch ook
zelfconsumptie?"*

**Ja, en de formule doet dat al goed:** wat niet is geëxporteerd, is zelf
gebruikt. Zon die via de accu in huis belandt telt dus mee.

Waar het misging is de **daggrens**. Op 14 augustus 08:23 stond er 0,109
kWh opwek tegen 0,448 kWh export — allemaal gisteren opgeslagen zon die
vannacht is verkocht. Die wordt afgerekend op de kalenderdag van vandaag,
terwijl hij bij de opwek van gisteren hoort. Vandaar ook de `unknown`:
onder een halve kWh opwek wordt er bewust geen aandeel berekend, want
daar rolt geen betekenisvol percentage uit.

**Nieuw: een dagreeks van 400 dagen** met opwek, zon-export, accu-export,
verbruik en import. Daarop rusten:

| Periode | |
|---|---|
| Week | laatste 7 dagen |
| Maand | vanaf de eerste van de maand |
| Jaar | vanaf 1 januari |
| **Contractjaar** | vanaf de ingevoerde startdatum |

Over een week valt de daggrens weg, en dat cijfer zegt dus meer dan dat
van vandaag. Zelfvoorziening staat er per periode bij.

Het contractjaar is nieuw configureerbaar (`JJJJ-MM-DD`) en schuift
automatisch mee: begint het contract later in het jaar dan vandaag, dan
loopt het lopende jaar vanaf vorig jaar.

Elke periode gebruikt de **gemeten** zon-export uit v1.76.0. Dagen van
daarvóór hebben die splitsing niet en vallen terug op de totale export
begrensd op de opwek, zoals v1.9.2 al deed.

Zichtbaar op de nieuwe subview **Zelfconsumptie**, bereikbaar vanaf de
accupagina. **Negen tests erbij.**

**Volledige testsuite**: 2110 tests, allemaal groen.

## v1.91.0 — Alles per dag, week, maand, jaar en contractjaar

**Gevraagd**: "Misschien dag/week/maand/jaar voor alle relevante sensoren
invoeren en zichtbaar maken? Kosten, verbruik, opwek, accu, noem het maar
op."

De dagreeks uit v1.90.0 draagt nu ook **accu-ontlading, kosten en CO₂**.
Daarmee ligt alles in één reeks en volgt de rest vanzelf:

| | Vandaag | Week | Maand | Jaar | Contractjaar |
|---|---|---|---|---|---|
| Opwek (kWh) | | | | | |
| Verbruik (kWh) | | | | | |
| Van het net (kWh) | | | | | |
| Naar het net (kWh) | | | | | |
| Uit de accu (kWh) | | | | | |
| Kosten (EUR) | | | | | |
| CO₂ (kg) | | | | | |
| Besparing (EUR) | | | | | |

**Eén reeks, één optelling, één tabel.** Losse tellers per onderwerp en
per periode zouden tientallen sensoren opleveren die elk hun eigen
dagwissel en herstart moeten overleven — en dat is precies waar deze week
een paar keer iets misging.

Besparing wordt apart berekend, want dat is een **verschil** tussen twee
reeksen en geen optelling. Vandaag komt uit de lopende tellers en telt
mee vanaf middernacht; de langere perioden rusten op afgesloten dagen.

Dagen van vóór deze versie missen de nieuwe velden; die tellen als nul
in plaats van de hele optelling te laten omvallen.

Zichtbaar op de nieuwe subview **Perioden**, bereikbaar vanaf de
accupagina naast Zelfconsumptie.

**Acht tests erbij.**

**Volledige testsuite**: 2118 tests, allemaal groen.

## v1.92.0 — Historische cijfers en gemiddelden

**Gevraagd**: "Historische cijfers kun je toch meenemen? Kan ik nu ook
startdatum contract invullen? Worden de kosten en het verbruik etc ook
dag/week/maand/jaar meegenomen en gemiddelden etc."

Drie keer ja, en op de eerste had ik me te snel neergelegd.

### Geschiedenis wordt nu ingelezen

Home Assistant houdt van elke energiesensor
**langetermijnstatistieken** bij — per uur, jaren terug. In deze
integratie staat daar al een voorbeeld van:
`async_bootstrap_night_consumption_from_history` uit een eerdere versie.
Ik had beter moeten kijken voordat ik zei dat het niet kon.

Bij het opstarten wordt de dagreeks tot **400 dagen** terug aangevuld uit
die statistieken. Alleen dagen vóór de oudste bekende dag: wat live is
gemeten wint altijd, want die kent de splitsing tussen zon- en
accu-export.

**Alleen uit meters.** Er zijn twee nieuwe configuratievelden voor de
kWh-meters van afname en teruglevering. Een vermogenssensor zou per uur
geïntegreerd moeten worden en dat wordt een schatting — deze cijfers
moeten naast een jaarafrekening kunnen liggen.

Ingelezen dagen missen de export-splitsing (die wordt pas sinds v1.76.0
gemeten) en dragen daarom `herkomst: statistieken`. Voor die dagen valt
de zelfconsumptie terug op de oude aanname, en dat is navolgbaar in
plaats van stilzwijgend.

### Gemiddelden per dag

Elke periode toont nu ook het **gemiddelde per dag** voor alle
grootheden. Zonder dat is een maand niet met een week te vergelijken —
dan kijk je naar het aantal dagen in plaats van naar het verbruik.

### En de contractdatum

Die kon al sinds v1.90.0: **Configureren → Startdatum energiecontract**,
als `JJJJ-MM-DD`. Het contractjaar verschijnt dan als extra kolom.

**Volledige testsuite**: 2123 tests, allemaal groen.

## v1.93.0 — Een factor duizend, en twee onvindbare pagina's

**Gemeld**: "Ik zie de nieuwe pagina niet?" en daarna "De data is onreëel
— Opwek 131548 kWh over een week."

Drie fouten in het werk van v1.91.0 en v1.92.0, alle drie van mij.

### De eenheid stond niet vast

131548 kWh over een week is een factor duizend te hoog: de bronsensor
levert **wattuur** en de code nam kilowattuur aan. Statistieken dragen
hun eigen eenheid; die wordt nu uit de metadata gelezen in plaats van
geraden, met een omrekentabel voor Wh, kWh en MWh.

Een sensor met een eenheid die daar niet in staat wordt overgeslagen met
een waarschuwing in het logboek — dat is beter dan een getal dat er
plausibel uitziet maar duizend keer verkeerd is.

Daarbij een plafond: een dag met meer dan 500 kWh is geen meting maar een
meterwissel of een teller die opnieuw begon.

### Verbruik werd verzonnen

Opwek en verbruik stonden in de tabel op **exact hetzelfde getal**, en
dat was meteen de verklikker. Verbruik werd berekend als *opwek + import
− export*; stonden de netmeters niet ingesteld, dan waren import en
export nul en kwam verbruik dus gelijk aan de opwek uit.

Nu wordt verbruik alleen ingevuld als **beide** netmeters er zijn.
Ontbreekt er één, dan blijft het veld leeg — ontbrekend is iets anders
dan nul.

### En de pagina's waren onvindbaar

De twee nieuwe pagina's misten `subview: true` en de links stonden
weggestopt onderaan het accu-uitbreidingsadvies. Er staan nu **tegels op
de Kostenpagina**, waar deze onderwerpen thuishoren. Twee bestaande tests
vingen dit alsnog: één die eist dat alleen het overzicht in de tabbalk
staat, en één die eist dat elke verborgen pagina via een tegel
bereikbaar is.

**Volledige testsuite**: 2128 tests, allemaal groen.

## v1.94.0 — De foute reeks stond er nog

**Gemeld** na de reparatie van v1.93.0: dezelfde 131548 kWh per week.

Terecht, en ik had het moeten voorzien. v1.93.0 repareerde het **inlezen**
— maar de reeks was al bewaard, en de routine vult alleen dagen *vóór* de
oudste bekende dag aan. Die 399 foute dagen bleven dus gewoon staan.

**Ingelezen dagen dragen nu een merkteken.** Alles zonder dat merkteken
komt uit de versie die de eenheid niet omrekende en verbruik gelijkstelde
aan de opwek; dat wordt weggegooid en opnieuw opgehaald. Verandert er
later weer iets aan het inlezen, dan volstaat het ophogen van dat getal.

**Live gemeten dagen blijven altijd staan.** Die kennen de splitsing
tussen zon- en accu-export en zijn niet opnieuw op te halen.

Daarnaast een **vangnet dat losstaat van het merkteken**: elke dag boven
500 kWh wordt geweerd, wie hem er ook in zette. Een woonhuis met
zonnepanelen haalt dat niet, dus zo'n waarde komt van een verkeerde
eenheid, een meterwissel of een teller die opnieuw begon.

Op de Perioden-pagina staat wat er is opgeruimd, naast wat er is
ingelezen.

**Wat vandaag wél klopte**: 20,98 kWh opwek, 6,19 kWh verbruik, 0,13 van
het net en 9,6 terug. Het live gedeelte was dus in orde; alleen de
ingelezen geschiedenis niet.

**Volledige testsuite**: 2132 tests, allemaal groen.

## v1.95.0 — De opruiming draaide op een lege lijst

**Gemeld** na v1.94.0: dezelfde 131548 kWh per week.

De opruiming van foute ingelezen dagen stond **vóór**
`async_load_persisted_nilm_state()` — dus ruimde hij een lege lijst op,
waarna de bewaarde reeks er meteen overheen kwam.

**Exact dezelfde volgordefout als v1.49.0.** Toen stond
`_recompute_measurement_quality()` vóór het terugzetten van de toestand
en bleef de meetkwaliteit daardoor altijd leeg. Ik heb toen wél de fout
gerepareerd maar géén test gemaakt die de *volgorde* bewaakt — en dus
kon dezelfde vorm terugkomen.

Nu drie tests die dat wel doen:

- alles wat de bewaarde reeksen leest of opruimt, moet ná het terugzetten
  komen;
- de tick mag pas starten als de toestand terug is;
- en een vangnet dat omvalt zodra er een nieuwe `async_bootstrap_...`
  bijkomt die niet expliciet in de volgorde is geplaatst.

Die eerste test is op de proef gesteld door de volgorde in een kopie
daadwerkelijk om te draaien: dan valt hij om. Een test die groen blijft
bij de fout die hij hoort te vangen, is erger dan geen test — en dat was
bij de eerste poging precies wat er gebeurde.

**Volledige testsuite**: 2135 tests, allemaal groen.

## v1.96.0 — Eindcontrole: twee vondsten

**Gevraagd**: "Zijn er verder nog zaken uit de diagnostiek naar voren
gekomen? Wil niet elke keer een nieuwe versie installeren."

De hele export nagelopen. Twee vondsten.

### De buitensensor leest structureel te warm

De verouderingsdrijvers legden **41,7 °C** buiten vast, en in de
koelgeschiedenis staan 35,4 en 35,9. Voor Lochem onwaarschijnlijk hoog.

De bron is `hue_outdoor_motion_sensor_1_temperatuur` — een
bewegingsmelder die in de zon hangt. Die leest bij direct zonlicht
makkelijk vijf tot tien graden te hoog. Geen uitschieter maar een
**aanhoudende afwijking**, dus het bestaande piekfilter ziet er niets
van.

**Dit raakt de aansturing.** De koeling vergelijkt de accu met buiten; een
te hoge buitenwaarde maakt dat verschil kunstmatig klein en laat de
ventilator te vroeg stoppen.

De sensor wordt nu vergeleken met de weerbronnen (luchttemperatuur in de
schaduw). Boven vier graden verschil verschijnt er een melding bij
*"vraagt een handeling"*. **Er wordt niets bijgesteld** — welke lucht de
ventilator werkelijk aanzuigt hangt van de opstelling af, en meten gaat
hier voor sturen.

### Restanten in de plantoetsing

Die droeg nog regels met **−20,82 en −22,73 kWh** aan werkelijke
zonopbrengst, geschreven vóór de volgordefix van v1.74.0. Negatieve zon
bestaat niet; die regels worden bij het opstarten verwijderd — ná het
terugzetten van de toestand, zoals v1.95.0 leerde.

### Wat schoon bleek

- geen interne fouten, geen plausibiliteitswaarschuwingen, doen-stapel
  leeg
- zelfvoorziening 97,9%, cycli en accustand kloppen exact met de
  narekening
- zonstand 0,4° verschil
- **nul tekortkwartieren**, laagste stand 34%
- rendement per halve slag heeft nu twee metingen per kant: laden 89,0 en
  85,2, ontladen 94,2 en 94,1 — bij drie slaat de methode om
- NILM 37 apparaten zonder alarm, 20 watersessies, aanwezigheid werkt
- de modulemelding is omgeslagen: module 1 is nog steeds de warmste maar
  levert niet minder, dus de melding wijst nu naar de plaatsing in plaats
  van naar de module

**Volledige testsuite**: 2144 tests, allemaal groen.

## v1.97.0 — Accu, kosten en CO₂ ook uit de geschiedenis

**Gevraagd** bij een screenshot waarop accu, kosten, CO₂ en besparing op
nul stonden voor de langere perioden: "deze kunnen toch ook met data uit
geschiedenis worden bepaald?"

Drie van de vier wel, één niet.

| Rij | Uit geschiedenis? |
|---|---|
| Uit de accu | **ja**, met een kWh-meter — bij deze installatie `sensor.zendure_export` |
| Kosten | **ja**, met een kostensensor — bijvoorbeeld `sensor.zonneplan_electricity_delivery_costs_today` |
| CO₂ | **ja**, afgeleid uit de al ingelezen netafname |
| Besparing | **nee** |

Besparing is het verschil met een tegenfeitelijke wereld zonder
aansturing, en die is nooit ergens vastgelegd. Terugrekenen zou
historische kwartierprijzen vragen die de prijssensor niet bewaart — en
een geschat verschil naast echte cijfers zetten is erger dan een leeg
vakje.

Twee nieuwe configuratievelden: **meter accu-ontlading** en
**kostensensor stroom**.

### En die nullen waren geen meting

Een periode zonder enkele dag met een waarde kwam als **0,0** in de tabel
— niet te onderscheiden van een periode die werkelijk op nul uitkomt.
Daar staat nu *"niet te bepalen"*.

De CO₂-intensiteit wordt afgeleid uit de dagen die live zijn gemeten: de
mediaan van gram per kWh netafname. Dat is een benadering voor ingelezen
dagen, want de intensiteit per uur is niet bewaard en schommelt met de
windproductie.

Het inlezen krijgt versie 3, dus de bestaande ingelezen dagen worden
opnieuw opgehaald — nu inclusief de nieuwe kolommen.

**Volledige testsuite**: 2148 tests, allemaal groen.

## v1.98.0 — Voor de derde keer dezelfde volgordefout

De energiecijfers kloppen nu — 108,36 kWh opwek deze week, 62,02
verbruik — en de opruiming deed zijn werk: 399 dagen verwijderd, 399
opnieuw ingelezen.

Maar accu, kosten en CO₂ stonden in **elke** periode op dezelfde waarde.
Week, maand, jaar en contractjaar allemaal 0,0 en 0,05. Dat kan niet.

### De tellers waren al gewist

De kostentellers worden op regel 13608 van de tick op nul gezet, de
accuteller op 13813 — en de dag wordt pas op 13867 afgesloten. Alles
stond dan al op nul, dus kreeg elke afgesloten dag nullen mee.

**Dit is de derde keer.** Eerder bij de plantoetsing (v1.74.0, negatieve
zonopbrengst) en bij de opruiming van de energiereeks (v1.95.0, die op
een lege lijst draaide). Steeds dezelfde vorm: iets leest een waarde
nadat een andere routine hem heeft gewist.

De oplossing is die van v1.74.0: de stand van de laatste tick van die dag
vasthouden, en die gebruiken bij het afsluiten. Dat gebeurt aan het
**einde** van de tick, als alle tellers zijn bijgewerkt, en het overleeft
een herstart.

**Een bredere test erbij** die omvalt zodra een afsluitroutine
rechtstreeks een dagteller leest in plaats van de bewaarde stand. Zonder
zo'n toets komt deze vorm een vierde keer terug.

### En de reeks stond niet in de export

Waardoor niet na te gaan was waarom die getallen gelijk waren. Een
optelling zonder de onderliggende regels is niet te controleren —
hetzelfde gat als eerder bij de meldingen. De laatste dertig dagen staan
er nu in.

**Volledige testsuite**: 2153 tests, allemaal groen.

## v1.99.0 — De ventilator pendelde dertien keer per nacht

**Gevraagd**: "Heb je de diagnostiek volledig nagekeken?" Nee — ik was op
één ding gestuit en had de rest laten liggen. Alsnog gedaan.

### De koeling pendelt

In de nacht van 15 augustus schakelde de ventilator **dertien keer**,
telkens tussen 31 en 35 °C, om de twintig minuten. In de
meldingsgeschiedenis staan daardoor 63 koelmeldingen op 200 regels.

Dit is géén sensorruis — de hysterese van v1.76.0 vangt dat al. Het is
echt thermisch pendelen: de ventilator koelt de omvormer in enkele
minuten van 35 naar 31, waarna hij weer opwarmt. Het systeem is sneller
dan de band tussen 32 en 35 breed is.

Een bredere band zou de omvormer onnodig warm houden. Daarom een
**minimale loop- en rusttijd van 30 minuten** — de gebruikelijke
oplossing bij ventilatoren en compressoren, en ze lost het op zonder aan
de temperatuurgrenzen te sleutelen.

De uitzondering daarop is bewust smal. Mijn eerste poging was "onder de
ondergrens mag hij altijd uit", en dat ondermijnde precies het
waargenomen geval: de uitschakeling gebeurde bíj 31 graden. Bij 31 met 23
buiten valt er nog acht graden te koelen; de ondergrens zegt alleen dat
de omvormer koel genoeg *is*. Alleen als het verschil met buiten te klein
is om nog iets te halen, wordt er niet gewacht.

### Wat verder uit de controle kwam

- **Alle kruiscontroles kloppen**: zelfvoorziening 99,9%, accustand,
  cycli 7,2
- **Zonstand** 0,7° verschil; **buitensensor** nu 0,9 °C boven de
  weerbron — vannacht dus geen zonnestraling op de sensor, wat het
  vermoeden van gisteren ondersteunt
- **Plantoetsing is schoon**: de negatieve regels zijn verdwenen, 14
  augustus staat op 20,9 kWh zon tegen 21,36 voorspeld
- **Nul tekortkwartieren**, en de tekortdagen zakken van 3 naar 2
- **Rendement**: drie ontlaadmetingen (94,2 / 94,1 / 93,0), nog twee
  laadmetingen — bij drie slaat de methode om
- Geen interne fouten, doen-stapel leeg, NILM zonder alarm

**Volledige testsuite**: 2157 tests, allemaal groen.

## v2.0.0 — Zelfcontrole: de integratie kijkt zichzelf na

**Gevraagd**: "Kun je dit soort zaken ook live in de integratie
analyseren, dus zonder jou een diagnostiek te sturen? (…) Eigenlijk dus
een soort van AI in de integratie, zodat ik live kan zien dat een
berekening ofzo niet klopt."

Ja — en er komt geen taalmodel aan te pas. Dat is geen beperking maar de
juiste keuze.

### Wat het nakijken werkelijk was

Vrijwel alles wat er deze week uit een diagnostiek kwam, kwam uit
**kruiscontroles**: twee getallen die hetzelfde horen te zeggen en dat
niet deden.

| Waarneming | Wat het aanwees |
|---|---|
| Opwek exact gelijk aan verbruik | een verzonnen verbruik |
| 131548 kWh per week | een niet-omgerekende eenheid |
| Elke periode dezelfde waarde | tellers die al gewist waren |
| Zon −20,82 kWh | een volgordefout |

Stuk voor stuk mechanisch te vinden. Een taalmodel zou daar niets aan
toevoegen en wél een reden kunnen verzinnen die niet klopt — dezelfde
afweging als bij de waarom-uitleg van v1.60.0.

### Acht controles, elke ronde

Zelfvoorziening tegen de tellers, beschikbare energie tegen de
accustand, de exportsplitsing tegen het totaal, opwek gelijk aan
verbruik, onmogelijke dagen in de reeks, week/maand/jaar met dezelfde
waarde, een vastgelopen tick, en een ventilator die te vaak schakelt.

Elke controle komt overeen met een fout die werkelijk is voorgekomen.

Bij een bevinding volgt een **melding** — alleen bij een verandering,
want dezelfde bevinding elke ronde herhalen is de snelste manier om te
zorgen dat er niet meer naar gekeken wordt. Die melding staat standaard
aan, net als "onderdeel van de integratie faalt": als twee getallen
elkaar tegenspreken is dat per definitie geen ruis.

Nieuwe subview **Zelfcontrole**, bereikbaar vanaf Meetkwaliteit.

### Wat het niet kan

Een fout van een soort die er niet in staat. Elke controle hierboven is
achteraf toegevoegd nadat de fout zich had voorgedaan — dat blijft zo.
Daar is nog steeds iemand voor nodig die kijkt, en dat staat ook in de
toelichting op het scherm.

**Volledige testsuite**: 2166 tests, allemaal groen.

## v2.1.0 — Logboek met drie prioriteiten

**Gevraagd**: "Misschien een soort logboek? Waarbij ik live besluiten, en
allerlei zaken kan zien? Dit in 3 prio's definieren, en bij een kritische
melding een melding naar mijn iPhone?"

De bouwstenen lagen er al, maar verspreid over vier reeksen:
modusveranderingen, meldingen, koelschakelingen en de energiebrug. Het
logboek voegt ze samen op moment, zodat er één tijdlijn is.

**Bewust geen vijfde reeks** die alles nog eens apart bijhoudt. Dan
kunnen de twee uit elkaar gaan lopen — en dat is precies waar het deze
week een paar keer misging: een reparatie van het schrijven die niet
raakte wat er al bewaard was.

### Drie prioriteiten

| | Betekenis |
|---|---|
| ❌ **Kritiek** | er gaat geld of comfort verloren, of de integratie doet iets anders dan bedoeld |
| ⚠️ **Aandacht** | het vraagt een beslissing, maar niet nu |
| ℹ️ **Info** | het hoort erbij en is achteraf nuttig |

Kritiek zijn: een voorspeld tekort, een lage stand vlak voor de piek, een
interne fout, een sensor die uitvalt, en een bevinding van de
zelfcontrole. **Vijf van de ruim dertig soorten** — een test bewaakt dat
het er hoogstens acht blijven, want als er tien kritiek zijn is er geen
enkele meer kritiek.

Elke meldingssoort moet een prioriteit hebben; een test valt om zodra er
een bijkomt zonder. Anders zou zo'n soort stilzwijgend als info eindigen,
ook als hij kritiek is.

### Kritieke meldingen op de telefoon

Die krijgen `interruption-level: time-sensitive` mee — het iOS-veld dat
de stille modus doorbreekt. Android krijgt via dezelfde sleutel hoge
prioriteit; een app die het niet kent, negeert het.

Een melding die om drie uur 's nachts met de rest in de wachtrij belandt,
is immers geen kritieke melding.

Nieuwe subview **Logboek**, bereikbaar vanaf Meetkwaliteit, met de
aantallen per prioriteit bovenaan.

**Volledige testsuite**: 2176 tests, allemaal groen.

## v2.0.1 — Zelfcontrole ook op de landingspagina

**Gevraagd**: "Dit uiteraard op een apart tabblad, maar op de
landingspagina een klein overzicht."

Een tegel bij *Status per onderwerp*, die het oordeel toont en hoogstens
de **eerste** bevinding — de rest staat op de eigen pagina, één tik
verderop.

De kleur zegt het meteen: groen als alle acht kruiscontroles kloppen,
rood bij een fout, amber bij iets dat aandacht vraagt, grijs als er nog
niets is nagerekend. Zonder kleur zou je hem moeten lezen om te weten of
er iets is, en dan werkt hij niet.

De landingspagina blijft daarmee op 1272 van de 1900 toegestane tekens.

**Volledige testsuite**: 2179 tests, allemaal groen.

## v2.2.0 — Integratiegezondheid, maar zonder verzonnen score

**Voorgesteld**: health check endpoint, diagnostische sensoren, watchdog,
automatisch reconnecten, datavalidatie — en een gezondheidsscore van
0-100% op basis van API-beschikbaarheid, updatefrequentie, aantal fouten
en dataconsistentie.

Twee daarvan zijn gebouwd, drie bestonden al, en één berust op een
misverstand.

### De score: goede onderdelen, verkeerde optelling

De vier onderdelen zijn goed gekozen en alle vier meetbaar. Het
**samenvoegen** tot één percentage is dat niet: dat vraagt wegingen die
nergens vandaan komen. Is 90% beschikbaarheid met perfecte consistentie
beter of slechter dan 100% beschikbaarheid met een rekenfout? Elk
antwoord daarop is verzonnen.

Dezelfde afweging als bij de eerder afgevallen netkwaliteitsscore. Wat
er nu staat: **vier oordelen naast elkaar**, en de status van het geheel
is die van het slechtste onderdeel — een ketting is zo sterk als de
zwakste schakel, en dat is geen aanname maar een definitie. Er staat ook
bij wélk onderdeel de status bepaalde.

Een test bewaakt dat er geen samengesteld percentage terugsluipt.

### Watchdog die ook ingrijpt

De zelfcontrole van v2.0.0 **meldt** al dat de ronde stilstaat, maar
melden is niet herstellen — en als de tijdklok zelf niet meer afgaat,
komt die melding er ook niet.

De watchdog loopt op een **eigen klok** en dwingt een ronde af na drie
gemiste ticks. Op dezelfde klok meeliften zou betekenen dat hij zwijgt
als juist die klok het begeeft.

### Wat er al was

- **Diagnostische sensoren**: 34 entiteiten dragen al
  `EntityCategory.DIAGNOSTIC`
- **Health check endpoint**: dat is de diagnostiek-export van Home
  Assistant zelf; een eigen HTTP-endpoint voegt daar niets aan toe en
  vraagt onderhoud
- **Datavalidatie**: plausibiliteitsregels (v1.9.5), ingangscontrole
  (v1.47.0), zelfcontrole (v2.0.0) en de plafonds op de dagreeks

### En het misverstand

**Automatisch reconnecten** kan niet, want er is geen verbinding. Deze
integratie praat niet met Zendure, SolarEdge of de P1-meter; ze leest
entiteiten uit Home Assistant. Vallen die weg, dan is dat een probleem
van díe integratie, en herstelt Home Assistant het zelf. Wat hier wél
kan is signaleren dat een bron stil is — en dat doet het eerste onderdeel
van de gezondheidspagina.

Nieuwe subview **Integratiegezondheid**, bereikbaar vanaf Meetkwaliteit.

**Volledige testsuite**: 2186 tests, allemaal groen.

## v2.3.0 — Vragen stellen over de eigen gegevens

**Gevraagd**: "zodat ik ook vragen kan stellen als: Wat is het verwachte
verbruik vandaag, wat zijn de kosten vandaag? Hoe laat was iedereen
thuis, weg etc."

Nieuwe dienst `energy_management_system.vraag`. Het antwoord komt terug
als dienstuitvoer, dus je kunt hem aanroepen vanuit een automatisering,
een script, of direct in de ontwikkelaarshulpmiddelen.

> **Wat zijn de kosten vandaag?**
> Vandaag staat er € 3,10 aan opbrengst. Zonder aansturing was dat
> € 0,40 geweest.

Acht vraagsoorten: verwacht verbruik, kosten, opwek tegenover
voorspelling, of de accu de nacht haalt, wat de accu nu doet en waarom,
aanwezigheid, besparing, en de accustand.

**Geen taalmodel in de integratie** — dezelfde afweging als bij de
waarom-uitleg (v1.60.0) en de zelfcontrole (v2.0.0). Een gegenereerd
antwoord kan een getal noemen dat nergens staat, en dat is bij
energiecijfers erger dan geen antwoord. In plaats daarvan een vaste
tabel: trefwoorden wijzen naar een functie die het antwoord uit gemeten
waarden opbouwt.

Elk antwoord draagt de **waarden** waarop het rust, zodat het na te
rekenen is. Een vraag die er niet in staat krijgt eerlijk *"die vraag ken
ik niet"* plus de lijst met wat wel kan — geen verzonnen antwoord. En een
vraag die de integratie kent maar niet kan beantwoorden, zegt dat in
plaats van de hele ronde te breken.

**Voor vrije vragen** is de juiste route de gespreksassistent van Home
Assistant zelf. Die kan een taalmodel gebruiken en leest de entiteiten
van deze integratie; het verschil is dat het model dan buiten de
aansturing staat. Deze dienst is bedoeld voor de vragen die vaak
terugkomen en waar een exact antwoord op hoort.

**Volledige testsuite**: 2194 tests, allemaal groen.

## v2.0.2 — Start de integratie nog op?

**Gevraagd**: "Tevens wil ik zien dat de integratie nog opstart (na een
herstart van HA)."

Terecht na drie dagen met tientallen wijzigingen. De testsuite draaide
`async_setup()` al, maar vier dingen worden pas bij een échte start
aangeraakt en werden nergens getoetst.

**En bij het bouwen van die toets bleek er meteen een gat**: de
configuratiestroom kon in de testomgeving **helemaal niet worden
opgebouwd**. Er ontbraken vier selectors en de dummy was niet
aanroepbaar, dus was er nooit een test die het probeerde. Een fout in de
configuratiestroom — een verkeerde selector, een standaardwaarde die niet
bij het type past — zou pas bij een echte herstart zijn opgevallen, en
dan laadt de integratie wel maar kun je hem niet instellen.

Elf toetsen die nu bij elke oplevering meelopen:

- elke module importeert (een ontbrekende constante laat niets laden)
- het **configuratieformulier** wordt gebouwd, leeg én met bestaande
  waarden
- de vertalingen zijn geldige JSON, en elk configuratieveld heeft een
  Nederlandse omschrijving
- manifest, `services.yaml` en het dashboardbestand zijn geldig
- de **diagnostiek** raakt alleen attributen die bestaan — anders faalt
  het downloaden precies op het moment dat je hem nodig hebt
- een **volledige opstartronde** met een realistische configuratie, met
  daarna een echte beslisronde
- en daarna zijn alle acht overzichten opvraagbaar: een integratie die
  laadt maar niets toont is net zo stuk

**Volledige testsuite**: 2205 tests, allemaal groen.

## v2.0.3 — De zelfcontrole werkt, en had op twee punten ongelijk

De eerste bevindingen kwamen binnen een ronde binnen. Allebei terecht
gesignaleerd, allebei verkeerd geëtiketteerd.

### "Week, maand en jaar staan alle drie op 0.05"

De waarneming klopt, maar de oorzaak is geen rekenfout: er is simpelweg
**één dag met een CO₂-waarde**. Ingelezen dagen hebben die niet, want de
intensiteit per uur is nooit bewaard.

De controle telt nu hoeveel dagen er werkelijk bijdragen. Is dat er één,
dan is het **aandacht** met erbij dat het zich vanzelf vult — of eerder,
met een meter bij Configureren. Dragen er meerdere dagen bij en staat
elke periode tóch op hetzelfde getal, dan is het wél een fout.

Een fout melden waar niets aan te doen is, is de snelste manier om de
controle te laten negeren. Dezelfde afweging als bij de terugval-duur
(v1.79.0).

### "18 schakelingen vandaag"

Ook waar, maar dat telde vanaf middernacht — inclusief de uren vóór de
minimale looptijd uit v1.99.0, die die middag pas was geïnstalleerd. Een
controle die terugkijkt naar een periode waarin de reparatie nog niet
draaide, meldt een probleem dat al opgelost is.

Nu over een **venster van zes uur**, met een grens van zes schakelingen.
Bij een minimale loop- en rusttijd van een half uur zijn er hoogstens
twaalf mogelijk in zes uur; zes is dus ruim boven normaal en onder het
maximum. Lang genoeg om pendelen te zien — het ging om de twintig
minuten — en kort genoeg om te merken dat het over is.

**Volledige testsuite**: 2208 tests, allemaal groen.

## v2.0.4 — Dubbele sleutel in het dashboard

**Gemeld** uit het logboek van Home Assistant:

> YAML file energy_management_system_dashboard.yaml contains duplicate
> key "grid_options". Check lines 279 and 282

De zelfcontrole-tegel uit v2.0.1 kreeg `grid_options` mee terwijl de
kaart die al had. Home Assistant negeert er dan één stilzwijgend — hier
zonder zichtbaar gevolg, maar het had net zo goed de breedte kunnen
verzetten.

**Geen enkele test ving dit**, en dat is het eigenlijke probleem:
`yaml.safe_load` slikt dubbele sleutels zonder te klagen, de laatste
wint. Alle bestaande dashboardtests gebruiken die functie en zagen dus
niets.

Twee toetsen erbij:

- een strenge lader die dubbele sleutels weigert, precies zoals Home
  Assistant zelf doet — over beide kopieën van het bestand;
- en een die de concrete vorm vangt: één kaart die twee keer verteld
  krijgt hoe breed hij is.

Allebei op de proef gesteld door de fout terug te zetten in een kopie:
dan vallen ze om.

**Volledige testsuite**: 2210 tests, allemaal groen.

## v2.0.5 — Vier vondsten uit het logboek

**Gevraagd**: "Logboek controle?" — en toen vijf meldingen gedeeld. Het
logboek zit niet in de diagnostiek-export, dus dit was voor mij tot nu
toe onzichtbaar.

### De gezondheidssensor was stuk

> `missing 1 required positional argument: 'entity_id'` — 27 keer in
> dertien minuten

`is_sensor_genuinely_unavailable` wil ook het tijdstip; het werd met één
argument aangeroepen. Die sensor was dus sinds zijn invoering kapot.

**Waarom dat niet opviel**: het attributenblok vangt elke sleutel apart
af sinds v1.16.x, dus de rest van de tegels bleef gewoon werken. Er stond
alleen dit ene attribuut niet — precies de vorm die je pas ziet als je de
export regel voor regel leest.

En de test die het had moeten vangen, bootste de functie na **met één
argument**. De nabootsing week af van de echte handtekening, dus de fout
was in de tests onzichtbaar.

### Taken vanaf de verkeerde draad

> `calls hass.async_create_task from a thread other than the event loop,
> which may cause Home Assistant to crash or data to corrupt`

En de gevolgmelding uit hetzelfde logboek: *"coroutine 'async_update' was
never awaited"*. De coroutine werd wél aangemaakt maar nooit uitgevoerd —
dus die tick ging verloren.

Beide terugroepen gebruiken nu `add_job`, dat wél draadveilig is en zelf
de juiste weg kiest.

### Vier tests erbij

- de gezondheidsberekening wordt echt uitgevoerd;
- **elke** attribuutfunctie van de sensor wordt aangeroepen — zonder dat
  blijft een fout verborgen achter de foutafvanging;
- geen van beide terugroepen mag nog `async_create_task` gebruiken;
- en een toets die alle **nabootsingen in de testbestanden** vergelijkt
  met de echte handtekening. Dat is de diepere oorzaak, en die kan overal
  toeslaan.

De vijfde melding (dubbele YAML-sleutel) was al opgelost in v2.0.4.

**Volledige testsuite**: 2214 tests, allemaal groen.

## v2.0.6 — Een bestand lezen in de event loop

**Gemeld** uit het logboek:

> Detected blocking call to read_text (…) inside the event loop by
> custom integration 'energy_management_system'

Een bestand lezen duurt milliseconden, maar in de event loop staat in
die tijd **alles** stil — elke andere integratie, elke automatisering.
Home Assistant verbiedt dat daarom, en terecht.

Het viel op bij het **downloaden van de diagnostiek**, want die roept
`get_dashboard_health` aan en die las het dashboardsjabloon van schijf.
Uitgerekend de functie die ik gebruik om problemen op te sporen,
veroorzaakte er dus zelf een.

Het sjabloon verandert alleen bij een update, dus het hoeft maar één keer
gelezen te worden: **bij het opstarten, in een executor**. Daarna komt
het uit het geheugen.

**Twee tests erbij.** Eén die het hele pakket doorzoekt op
bestandstoegang buiten een executor — met de omgeving als criterium, want
binnen een hulpfunctie die aan `async_add_executor_job` wordt meegegeven
is het juist correct. En één die vastlegt dat het sjabloon bij het
opstarten wordt ingelezen.

De eerste is op de proef gesteld door de fout terug te zetten in een
kopie: dan valt hij om.

**Vierde soort fout die alleen Home Assistant zelf ziet**, na de
ontbrekende selectors, de dubbele YAML-sleutel en de taak vanaf de
verkeerde draad. De testomgeving is milder dan de werkelijkheid; deze
toetsen halen daar telkens een stuk van weg.

**Volledige testsuite**: 2216 tests, allemaal groen.

## v2.0.7 — Twee verminkte woorden in de meldingen

**Gevraagd**: "Verder nog fouten, textuele fouten of iets dergelijks
gevonden?" Die had ik niet gericht gezocht. Alsnog gedaan: 1545 zinnen
uit de export, 857 teksten uit de code en 157 uit het dashboard.

De export en het dashboard waren schoon. De **meldingen** niet:

> de diagnostiek-export hoort weer 'n JSON-bestand te **gefkes**
> 1 onderdeel kan zichzelf neet berekenen: **gezunnedheid**

De Achterhoekse vertaling gebruikte `str.replace` **zonder
woordgrenzen**. "geven" bevat "even" en werd `g` + `efkes`;
"gezondheid" bevat "zon" en werd `ge` + `zunne` + `dheid`.

Nu met een woordgrens eromheen. De tabel bevat ook meerwoordige regels
("aan het" → "an 't"), en die werken daar net zo goed mee.

**En één echte taalfout**: *"De stand is verandert"* moet **veranderd**
zijn — voltooid deelwoord na "is", geen persoonsvorm.

### Wat géén fout bleek

*"Alle onderdelen rekent weer"* oogde als een meervoudsfout, en ik heb
het even "gerepareerd" naar "rekenen". Dat was verkeerd: het Achterhoeks
heeft een **eenvormig meervoud op -t**, net als *"Prieze gaot onder nul"*
twee regels verderop. Teruggedraaid.

**Zeven tests erbij**, waarvan de belangrijkste het mechanisme toetst in
plaats van de uitkomst: elk woord uit de tabel wordt in een langer woord
geplakt en moet daar ongemoeid blijven. Op de uitkomst toetsen zou
"vannacht" ten onrechte afkeuren, want dat bevat terecht "nacht".

**Volledige testsuite**: 2223 tests, allemaal groen.

## v2.1.0 — Hoe zwaar is een ronde?

**Gevraagd**: "Nu wordt alle data om de 5 minuten gerefreshed, wat als we
naar live gaan? Hoe belastend is dat?"

Dat viel hier niet te meten. In een testomgeving zonder echte prijzen
bouwt de kwartierplanning niet — en dat is juist het zwaarste deel. Een
lege ronde duurt 4 ms, en dat getal zegt niets over de praktijk.

Een schatting naast echte cijfers zetten is precies wat deze week een
paar keer is teruggedraaid. **Dus meet de integratie het nu zelf.**

Elke ronde wordt geklokt. Op de Zelfcontrole-pagina staat:

- de **mediaan** en de **langzaamste** ronde over de laatste honderd —
  die laatste apart, want de mediaan verbergt een uitschieter en juist
  die bepaalt of Home Assistant merkbaar hapert;
- welk **aandeel van de tijd** de integratie bezig is;
- en het **kleinste verantwoorde interval**: dat is het antwoord op "kan
  het vaker?", met een getal in plaats van een vermoeden.

Boven de vijf procent belasting verschijnt er een bevinding in de
zelfcontrole. Dat is streng genoeg om ruimte te laten voor alle andere
integraties.

De metingen overleven **bewust geen herstart**: ze gelden voor de huidige
versie op deze machine, en een herstart komt meestal juist door een
nieuwe versie.

**Volledige testsuite**: 2229 tests, allemaal groen.

## v2.1.1 — 5613 ms, en waar die tijd heen gaat

**Gemeld** na de eerste meting:

> Mediaan 5613.0 ms, langzaamste 5613.0 ms over 1 rondes.

Twintig keer meer dan ik had verwacht. Mijn schatting van 50 tot 300 ms
was er ver naast, en dat is precies waarom die meting er nu is.

### Drie dingen die dat getal nog niet zei

**Eén ronde is geen meting.** En het is uitgerekend de eerste na een
herstart, waarin het inlezen van vierhonderd dagen geschiedenis zit —
werk dat maar één keer gebeurt. Die ronde telt nu niet mee.

**Wandklok is niet hetzelfde als belasting.** Van die 5,6 seconden gaat
een deel op aan wáchten: op de Zendure, op de schijf, op de recorder. In
die tijd doet Home Assistant gewoon ander werk. Alleen **rekentijd**
blokkeert de event loop echt, en die wordt nu apart gemeten.

**Het percentage is niet de enige maat.** 1,87% klinkt onschuldig, maar
zolang een ronde rekent staat alles stil. Boven een seconde hapert Home
Assistant merkbaar, hoe weinig vaak die ronde ook draait. Dat is nu een
eigen grens naast het aandeel.

### En de uitsplitsing

Zeven onderdelen worden apart geklokt: planningsmeldingen, zelfcontrole,
energiedagstand, veroudering, terugvallen, proefstand en plantoetsing. In
de volgende diagnostiek staat waar de tijd heen gaat, in plaats van dat
we het moeten raden.

**Volledige testsuite**: 2229 tests, allemaal groen.

## v2.1.2 — De rondeduur is beantwoord, en een valse melding

### 48,6 ms

Over honderd rondes, langzaamste 59,9. Geen uitschieters meer nu de
eerste ronde na een herstart niet meer meetelt.

De **rekentijd is gelijk aan de wandklok** (48,6 tegen 48,6), dus er
wordt vrijwel niet gewacht op sensoren — het is allemaal rekenwerk. Van
die 48,6 ms zit **14,7 ms in de planningsmeldingen**; de andere zes
gemeten onderdelen kosten samen nog geen 1,5 ms.

| Interval | Belasting |
|---|---|
| 5 minuten (nu) | 0,016% |
| 1 minuut | 0,08% |
| 10 seconden | 0,5% |
| 1 seconde | 4,9% |

### Een fout die geen fout was

De zelfcontrole meldde: *"Week, maand en jaar staan alle drie op 0.09
terwijl 2 dagen een waarde hebben."*

Onterecht. Vallen beide dagen binnen de week, dan bevatten week, maand
én jaar dezelfde twee dagen — en hoort er hetzelfde getal te staan. Een
fout is het pas als de perioden **verschillende** dagen beslaan en tóch
op hetzelfde uitkomen.

Onderweg bleek de telling bovendien op `van` uit het periodeoverzicht te
leunen, en dat is het **eerste element van een ongesorteerde lijst** in
plaats van het begin van de periode. Ingelezen dagen worden vooraan
geplakt en live dagen achteraan. De reeks wordt nu op datum gesorteerd,
en de controle rekent de grenzen zelf uit.

### En het rendement per halve slag is omgeslagen

Na vier dagen wachten staat de methode op **"per halve slag"**:

| | Metingen | Mediaan |
|---|---|---|
| Laden | 89,0 / 85,2 / 84,2 | 85,2% |
| Ontladen | 94,2 / 94,1 / 93,0 / 96,6 | 94,2% |

Heen en terug **80,2%**, waar de oude methode 82,9% zei. Die 2,7
procentpunt werken door in de kostprijs en dus in de vergelijking tussen
accu en net.

**Volledige testsuite**: 2230 tests, allemaal groen.

## v2.2.0 — Het interval is instelbaar

**Gevraagd**: "instelbaar maken", nadat de gemeten rondeduur uitkwam op
**48,6 ms** — 0,016% van de tijd bij vijf minuten.

Nieuw veld bij Configureren: **Interval tussen rondes in seconden**,
standaard 300. In seconden en niet in minuten, want minuten zijn te grof
zodra je eronder wilt.

| Interval | Belasting bij 48,6 ms |
|---|---|
| 300 s (standaard) | 0,016% |
| 60 s | 0,08% |
| 10 s | 0,5% |
| 5 s (ondergrens) | 1,0% |

De **ondergrens van vijf seconden** is niet willekeurig: één seconde zou
4,9% zijn, en dat zit tegen de grens aan waarboven Home Assistant
merkbaar op deze integratie staat te wachten. Vijf seconden laat ruimte
voor een tragere ronde op een dag met een volle prijsreeks, zonder dat je
daar zelf op hoeft te letten.

Buiten de grenzen — of bij onzin in het veld — valt de integratie terug
op de standaard, met een regel in het logboek. Een interval van nul zou
haar onafgebroken laten draaien, en een verkeerd getal in de
configuratie mag geen onbruikbaar systeem opleveren.

De belastingweergave rekent nu met het **werkelijk ingestelde** interval;
anders klopt het percentage niet zodra je het aanpast. De
watchdog-drempel schaalt mee.

**Volledige testsuite**: 2238 tests, allemaal groen.

## v2.2.1 — "Entity None is neither a valid entity ID"

**Gemeld** met een screenshot van het configuratiescherm.

`vol.Optional(sleutel, default=None)` geeft de EntitySelector een lege
waarde mee, en die weigert dat — het veld is dan niet in te vullen.
Zonder `default` laat voluptuous het veld gewoon weg als er niets is
gekozen, en dat is wat een optioneel veld hoort te doen.

**Dit raakte 52 velden**, niet alleen de twee nieuwe. Die vielen alleen
op omdat ze nog nooit waren ingevuld; alle andere optionele
entiteitsvelden hadden bij jou al een waarde.

Er stond al een toets tegen precies deze fout — maar alleen voor
`NumberSelector` (v1.78.0). Die dekte `EntitySelector` niet. Nu allebei.

**Volledige testsuite**: 2240 tests, allemaal groen.

## v2.2.2 — Nul kWh opwek bij 11,8 kWh teruglevering

**Gevraagd**: "Staan de nieuwe entiteiten nu goed?" Deels — en de reeks
bevatte twee onmogelijke dagen.

### De datum kwam als tekst terug

15 en 16 augustus stonden op **0,0 kWh opwek** terwijl er 11,8 kWh was
teruggeleverd. Die energie moet ergens vandaan komen.

De dagstand bewaart de datum, en die werd als **date-object** weggezet.
Na een herstart komt hij als **tekst** uit de opslag terug, waardoor de
vergelijking altijd faalde. De afsluiting viel dan terug op de live
tellers — en die waren op dat moment al gewist.

Precies dezelfde val als bij `_plan_review_day_key` in v1.74.0, alleen
andersom: daar was een datum nodig, hier tekst. Het veld staat in
`PERSISTED_PLAIN_FIELDS` en niet in `PERSISTED_DATE_FIELDS`.

### En een vangnet

Teruglevering zonder opwek én zonder accu-ontlading wordt nu geweigerd,
net als een dag boven 500 kWh. Dat vangt deze vorm ook als hij langs een
andere weg terugkomt.

**Volledige testsuite**: 2242 tests, allemaal groen.

## v2.2.2 — Een nieuwe meter vulde de geschiedenis niet

**Gemeld** na het instellen van de accu- en kostenmeter: week, maand en
jaar bleven op **0,0** staan.

De inleesroutine vult alleen dagen **vóór de oudste bekende dag** aan, en
die reeks was al vol met vierhonderd dagen. Er gebeurde dus niets.

Het versienummer uit v1.94.0 vangt een wijziging in de **code**, maar
niet een wijziging in de **configuratie**. Nu wordt gekeken welke
kolommen de ingelezen dagen dragen tegenover welke meters er nu staan:
draagt geen enkele ingelezen dag een waarde voor een meter die wél is
ingesteld, dan wordt de geschiedenis opnieuw opgehaald.

Daarbij moest de oudste bekende dag **na** de opruiming opnieuw worden
bepaald. Zonder dat zou de routine alleen dagen vóór de oude grens
aanvullen en het zojuist gewiste gat laten staan — dezelfde vorm als de
volgordefouten van v1.74.0 en v1.95.0, en daarom staat er nu een test op.

**Volledige testsuite**: 2243 tests, allemaal groen.

## v2.2.3 — Waarom bleven accu en kosten leeg?

**Gemeld** met een diagnostiek waarin accu en kosten voor week, maand en
jaar op *"niet te bepalen"* stonden.

De opruiming uit v2.2.2 wérkte — die 0,0-waarden zijn weg. Maar het
opnieuw inlezen leverde niets op, en uit de export was **niet af te
leiden waarom**: de inleesmelding was leeg, er stond geen fout, en de
398 dagen droegen allemaal `null` voor die twee kolommen.

Zonder uitsplitsing is het gissen tussen drie oorzaken:

- de routine draaide helemaal niet;
- de sensor heeft geen langetermijnstatistieken (geen `state_class`);
- de eenheid werd niet herkend.

**Per bron wordt nu vastgelegd** welke entiteit is bevraagd, welke
eenheid die draagt, hoeveel statistiekpunten er zijn gevonden en wat er
eventueel misging. Dat staat in de diagnostiek én op de Perioden-pagina.

Dit is de tweede keer dat een optelling zonder de onderliggende gegevens
niet te controleren was — hetzelfde gat als eerder bij de meldingen
(v1.76.0) en de dagreeks (v1.98.0).

**Volledige testsuite**: 2245 tests, allemaal groen.

## v2.2.4 — De routine viel bij elke start om

De uitsplitsing per bron uit v2.2.3 gaf meteen antwoord: **leeg**. Niet
één bron bevraagd, geen inleesmelding. De routine draaide dus helemaal
niet.

### Een NameError, sinds v1.94.0

    opgeruimd = voor - len(self.energy_daily_history)

stond **boven** de regel die `voor` zet. Elke start gaf een `NameError`,
en de `try/except` in `async_setup` ving die netjes op.

Dat betekent: sinds v1.94.0 is de geschiedenis **nooit meer ingelezen**.
De 398 dagen in de reeks komen uit de inleesronde van dáárvoor — en
daarom bleven accu en kosten leeg, ongeacht welke meters er werden
ingesteld.

### En het zweeg erover

Precies de fout die deze integratie op tien andere plekken wél meldt: de
geschiedenis vulde zich niet, de melding bleef leeg, er stond geen fout
in de diagnostiek. Alleen het logboek wist ervan, en dat zit niet in de
export.

Opvangen blijft goed — het opstarten mag hier niet op stuklopen — maar
zwijgen niet. Een afgevangen fout landt nu in `internal_failures` én in
de inleesmelding.

### Wat de tests niet vingen

**Alle 2245 tests bleven groen**, want geen enkele voerde de routine
daadwerkelijk uit; ze lazen alleen de broncode. Nu wel:

- de routine wordt echt aangeroepen en moet een melding achterlaten;
- elke uitgang van de routine moet vertellen wat er gebeurde;
- en elke afgevangen fout in `async_setup` moet ergens zichtbaar worden.

Op de proef gesteld door de fout terug te zetten: dan vallen ze om.

**Volledige testsuite**: 2249 tests, allemaal groen.

## v2.3.0 — De kostenrij meet nu overal hetzelfde

**Gemeld** met een screenshot: *"Kosten (EUR) vandaag −0,54"* bij 0,04
kWh afname. Een negatief bedrag bij afname kan niet.

De dagkolom kwam uit `actual_cost_today_eur` — de eigen
kostenberekening, waar de opbrengst van teruglevering vanaf gaat. De
historische kolommen lezen de **kostenmeter**, die alleen de afname
telt. Twee verschillende grootheden in één rij, en dan is die rij niet
van links naar rechts te lezen.

Beide komen nu uit dezelfde meter. Het saldo verdwijnt niet — het staat
in de **besparingsrij**, waar het thuishoort: dat is per definitie een
verschil.

### En een valkuil die daarbij hoorde

De stand van een meter is niet hetzelfde als de kosten van vandaag. Een
dagsensor (`..._costs_today`) reset zelf, maar een levenslange teller
(`total_power_import_cost`) zou het **totaal-ooit** in de kolom "vandaag"
zetten — een verschil van jaren.

Daarom wordt de stand bij het begin van de dag onthouden en de
**aangroei** getoond. Een teller die terugspringt (middernacht, of een
meterwissel) wordt herkend: dan is de stand zelf de aangroei. Vlak na een
herstart is het ijkpunt onbekend; dan geeft een dagsensor meteen het
juiste getal en een levenslange teller pas na de eerstvolgende
dagwissel — beter dan een verzonnen ijkpunt, en het corrigeert zichzelf.

**Volledige testsuite**: 2257 tests, allemaal groen.

## v2.4.0 — De zonvoorspelling: meten waar de fout zit

**Gevraagd**: "Kun je diepgaand uitzoeken hoe we de PV voorspelling
beter kunnen maken? Het is namelijk 1 van de belangrijkste zaken."

De gemeten cijfers wezen een andere kant op dan verwacht:

| | |
|---|---|
| Mediane fout | **2,7%** |
| Gemiddelde fout | 10,8% |
| Slechtste dag | 41,6% |
| Binnen 10% | 4 van 7 dagen |

Het verschil tussen mediaan en gemiddelde is het hele verhaal: **de
meeste dagen zitten er nauwelijks naast, een paar volledig.** Een betere
gemiddelde correctie helpt daar niet — die maakt de goede dagen slechter
zonder de slechte te redden.

### 1. De correctie was zelf de grootste foutenbron

Het geleerde uurprofiel op deze installatie:

    6h → 0,334    7h → 0,856    8h → 0,385
    19h → 0,589   20h → 0,226

Zeven uur tussen zes en acht in breekt elk patroon. Dat is ruis, geen
signaal — en die factoren werden wél toegepast, waardoor de ochtend- en
avondvoorspelling met een factor drie werd gedrukt.

De oorzaak: de drempel om een verhouding te leren stond op **0,01 kWh**.
Tien wattuur. Een verhouding uit zulke getallen is betekenisloos: 0,02
gedeeld door 0,06 geeft 0,33, terwijl de absolute fout 0,04 kWh is.

Nu **0,10 kWh**. En de reeksen die er al staan worden opgeruimd: een
verhouding buiten 0,40–2,50 kan bij een redelijke voorspelling niet
voorkomen, behalve bij een deling door bijna nul. Zonder die opruiming
zou de reparatie pas over veertien dagen doorwerken.

### 2. Onzekerheid meten in plaats van de voorspelling verbeteren

Solcast levert naast de verwachting een **tiende- en
negentigste-percentiel**. Liggen die ver uit elkaar, dan is het een dag
met wisselende bewolking — en dan hoort de reserve ruimer.

Dat maakt de voorspelling niet beter. Het maakt wél dat een onzekere dag
als onzeker wordt behandeld, en dat is precies waar de slechtste dagen
pijn deden.

Twee nieuwe optionele sensoren. De extra marge loopt mee in de
**bestaande** zelfcorrigerende reserve — twee reserves naast elkaar
kostte v1.86.0 tot en met v1.88.0.

### 3. Het installatieprofiel

Dat staat op 4 van de 5 heldere dagen en heeft al beschaduwing gevonden
op azimut 80° (oost). Mogelijk verklaart dát de rare ochtendfactoren, en
is het geen ruis maar een schaduw die Solcast niet kent. Dat blijkt zodra
het profiel af is — meten voordat er iets op wordt gebouwd.

**Volledige testsuite**: 2268 tests, allemaal groen.

## v2.5.0 — Het goedkope blok, en de percentielen zaten er al

### "Om 17:00 begint 't goedkoopste blok van vandage"

**Gemeld** om 16:45. Terwijl het dagminimum om 13:00 op **16,4 ct** lag
en 17:00 op **30,7 ct** — bijna het dubbele.

De melding klopte binnen zijn eigen logica: het blok is het goedkoopste
dat er nog *resteert*. Maar om kwart voor vijf is dat alleen nog de
avond, en dan is *"een goed moment voor apparaten die kunnen wachten"*
precies het verkeerde advies.

De melding komt nu alleen nog als het blok **onder de dagmediaan** ligt.
Daarboven zegt hij alleen dat de rest van de dag nóg duurder is, en dat
is geen reden om de vaatwasser aan te zetten. De tekst noemt de
blokprijs én de dagmediaan, zodat je zelf kunt zien of het de moeite is.

### De percentielen zaten al in de sensor

De opzet van v2.4.0 vroeg om twee losse p10/p90-sensoren. **Die bestaan
niet.** Uit de aangereikte sensorattributen bleek dat Solcast de
percentielen als attributen levert op de bestaande voorspellingssensor —
en zelfs **per halfuur** in `detailedForecast`, met `pv_estimate`,
`pv_estimate10` en `pv_estimate90` naast elkaar.

Dat is beter dan losse sensoren: de onzekerheid is nu **per moment**
bekend in plaats van per dag. De twee configuratievelden zijn weer
verwijderd — velden laten instellen die nergens naar wijzen is erger dan
geen veld.

Levert een Solcast-versie die drie velden niet per regel, dan wordt
teruggevallen op de dagtotalen (`estimate`, `estimate10`, `estimate90`).
Grover, maar genoeg om een onzekere dag te herkennen.

**Volledige testsuite**: 2272 tests, allemaal groen.

## v2.6.0 — Vasthouden voor morgen: eerst meten

**Gevraagd**: "Houdt de integratie ook rekening met bijvoorbeeld minder
PV energie morgen en daardoor meer te behouden in plaats van
terugleveren?"

**Deels**, en het is goed om precies te zijn over waar de grens ligt.

De reserve kijkt naar het diepste tekort tot het **eerstvolgende
goedkope blok**. Ligt dat morgenmiddag, dan zit de hele nacht en ochtend
erin, inclusief de verwachte zon. Weinig zon morgenochtend betekent dus
al meer achterhouden. Daarbovenop komt de bonus voor opeenvolgende
zonarme dagen, en sinds v2.5.0 de bonus voor een onzekere dag.

**Waar het stopt**: bij dat goedkope blok. De reserve redeneert dan "daar
kan ik bijladen" — terwijl "goedkoop" in de winter 25 ct kan zijn, en dat
is duurder dan de zon die je vanavond weggeeft.

### De vraag erachter is een andere

Niet *"haal ik de nacht"* maar *"is deze kWh morgen meer waard dan wat
hij nu opbrengt"*. Dat is teruglevering nu tegen vermeden inkoop later,
na rendement en slijtage.

Nieuwe proefstandkandidaat die dat **meet en niets stuurt** — dezelfde
route als de slijtagekosten. Bij elke ontlading wordt vastgelegd wat de
kWh nu opbracht en wat hij na het goedkope blok zou hebben bespaard. Na
twintig metingen verschijnt de mediaan en het aandeel momenten waarop
vasthouden voordeliger was geweest.

### Wat deze meting niet weet

Of de accu die kWh straks nog **kwijt kan**. Op een zomerdag met
overschot is vasthouden zinloos: de accu is toch vol, en dan is
teruglevering het enige alternatief. Dat staat erbij, en het is precies
waarom deze kandidaat nog niets stuurt.

Na 1 januari wordt deze afweging wezenlijk scherper: teruglevering levert
dan nog 19 ct op tegen 32 ct vermeden inkoop.

**Volledige testsuite**: 2281 tests, allemaal groen.

## v2.6.1 — De zelfcontrole vond zijn eerste echte fout

**Gevonden door de zelfcontrole zelf**, niet door een screenshot:

> ❌ Dagreeks: Onmogelijke waarden op 2026-08-17

17 augustus stond op **0,0 kWh opwek met 9,8 kWh export**. En er was geen
16 augustus.

### Weer de volgorde

De dagsleutel ging op de nieuwe dag en de opwekteller werd gewist
**voordat** `_sluit_energiedag_af` werd aangeroepen. Die kreeg dus de
datum van vandaag mee, met de cijfers van gisteren en een al gewiste
opwekteller.

**Vierde keer dezelfde vorm**, na v1.74.0 (plantoetsing), v1.95.0
(opruiming op een lege lijst) en v1.98.0 (accu en kosten op nul). De dag
die wordt afgesloten wordt nu eerst vastgehouden.

### En melden is niet opruimen

De plausibiliteitscontrole bestond al en deed keurig zijn werk — maar de
foute regel bleef staan, want opruimen gebeurde alleen tijdens het
inlezen van de geschiedenis. Een fout melden zonder hem op te ruimen
betekent dat je hem elke dag opnieuw ziet.

### Wat wél goed ging

De opruiming van de PV-uurfactoren uit v2.4.0 werkte: de waarden van
0,334 en 0,226 zijn verdwenen, en 8h ging van 0,385 naar **0,783**. Het
profiel loopt nu netjes op van 0,87 in de ochtend naar 1,16 rond tien uur
en terug — een patroon in plaats van ruis.

**Volledige testsuite**: 2284 tests, allemaal groen.

## v2.7.0 — "Dure uren beginnen" op een vlakke dag

**Gemeld**: drie keer dezelfde melding op één ochtend, en het "duurste
blok" schoof telkens op:

    05:15 → "om 08:15 begint 't duurste blok"
    06:15 → "om 09:15 begint het duurste blok"
    09:15 → "om 09:30 begint het duurste blok"

Dat is geen vaste gebeurtenis maar een **horizon die meebeweegt**: het
duurste blok dat er nog *resteert*.

Twee dingen mis, en allebei gerepareerd.

### Te laat om nog iets te doen

Om 09:15 melden dat om 09:30 de piek begint, met de accu op 11%, is
nutteloos — er valt in een kwartier niets meer bij te laden. De melding
komt nu alleen nog met **minstens een uur** speling. Bij 2000 W is dat
2 kWh, een kwart van de accu.

Niet ruimer: anderhalf uur zou een melding van 1 uur 28 vooraf
wegfilteren, en die is wél bruikbaar.

### Geen piek maar gewoon ochtend

Op 17 augustus liep de prijs van **29,7 tot 38,9 ct** over de hele dag.
Het gemelde blok zat op 37,1 tegen een mediaan van 34,5 — nauwelijks
erboven. Bij zo'n vlak verloop levert bijladen weinig op.

Het blok moet nu **15% boven de dagmediaan** liggen. En de melding noemt
beide prijzen én de resterende tijd, zodat je zelf kunt beoordelen of het
de moeite is — dezelfde reden als bij het goedkope blok in v2.5.0.

**Volledige testsuite**: 2289 tests, allemaal groen.

## v2.8.0 — De integratie ijkt de bandbreedte zelf

**Gevraagd**: "Is de spreiding op de verwachting niet heeeeel erg groot?
Wat zegt dit nog?" — en daarna: "Ik wil dat de integratie dit zelf leert,
en bepaalt aan de hand van beschikbare data."

Terechte scepsis. Op 17 augustus liep de voorspelling van **2,4 tot 18,3
kWh** op een verwachting van 9,8 — een factor zeven. Zo'n band zegt op
zichzelf niets over de opbrengst.

En mijn oplossing van v2.4.0 was een aanname, geen meting: een vaste
drempel van 40% met een vaste bonus van 10 procentpunt. Verzonnen
getallen.

### Wat er nu wordt geleerd

Per dag wordt vastgelegd **waar in de band** de werkelijke opwek viel:
0 is p10, 1 is p90. Buiten de band mag — dat is juist het interessante
geval.

Daaruit volgt vanzelf:

| | |
|---|---|
| Hoe vaak de opwek **onder p10** viel | bij een goed geijkte voorspelling ongeveer 1 op 10 |
| Waar hij **meestal** landt | de mediane positie |
| Welke aanname **veilig** is | de positie die op 4 van de 5 dagen werd gehaald |

De reservemarge is nu **hoeveel die veilige aanname tekortschiet op de
verwachting**. Blijkt Solcast te optimistisch aan de onderkant, dan
schuift de aanname vanzelf omlaag; landt de opwek steevast hoog in de
band, dan mag de reserve minder somber doen.

Twee grenzen blijven van mij, en die zijn te verdedigen: **veertien
dagen** voordat er iets verandert (een verdeling uit drie metingen zegt
niets), en een **plafond van 25 procentpunt** (zonder plafond zou een
extreem brede band de hele accu blokkeren).

Nieuwe subview **Zonvoorspelling ijken**, bereikbaar vanaf de PV-pagina.

**Volledige testsuite**: 2299 tests, allemaal groen.

## v2.9.0 — Een regressiewoud, en of het iets oplevert

**Gevraagd**: "Is verder optimaliseren middels een Random Forest
Regressor nog een idee?" — en na mijn bezwaren: **"Proberen kan altijd
toch?"**

Terecht. Mijn bezwaren gingen over scikit-learn (numpy en scipy erbij,
zo'n 100 MB op een Raspberry Pi), niet over de techniek. Een woud voor
tweehonderd waarnemingen is in een paar honderd regels te schrijven,
**zonder enige afhankelijkheid**.

### Eerlijk getoetst

Het woud leert op oudere dagen en wordt getoetst op **nieuwere dagen die
het niet heeft gezien** — op tijd gesplitst, niet willekeurig.
Willekeurig splitsen zou uren van dezelfde dag in beide helften laten
belanden, en die lijken sterk op elkaar; dan lijkt elk model goed.

Op diezelfde uren wordt de **huidige uurcorrectie** doorgerekend, geleerd
uit alleen het leermateriaal. Twee getallen, één vergelijking.

### Wat een proef op nagebootste gegevens al liet zien

Met veertig dagen die op deze installatie lijken — meestal accuraat, een
kwart van de dagen fors mis door wolkenvelden:

| | Fout per uur |
|---|---|
| Huidige methode | 0,169 kWh |
| Regressiewoud | 0,213 kWh |
| **Winst** | **−25,9%** |

Het woud doet het **slechter**. De reden is te begrijpen: of wolkenvelden
overtrekken staat niet in de kenmerken, dus zoekt het woud structuur in
ruis en vindt patronen die er niet zijn.

Maar dat is mijn simulatie met mijn aannames. Daarom draait hij nu op de
**echte** gegevens, als proefstandkandidaat die niets stuurt. Onder de
tien procent winst blijft hij daar: een woud is niet uit te leggen, en
dat is een echte prijs.

Kenmerken: voorspelling, uur, zonshoogte, azimut, bewolking (mediaan van
de weerbronnen), bandbreedte en maand. Dat laatste vraagt twintig dagen
en 150 gemeten uren voordat er iets wordt beweerd.

**Volledige testsuite**: 2310 tests, allemaal groen.

## v3.0.0 — Meting en winst zijn twee verschillende dingen

**Gevraagd**: "Zijn er al zaken uit (meetkwaliteit) die nu betrouwbaar
genoeg zijn en eventueel al kunnen meedoen in plaats van alleen meten?"

Die vraag was moeilijker te beantwoorden dan nodig, en dat lag aan mij.
**"Betrouwbaar" sloeg op twee verschillende dingen:**

- de **slijtagekosten** stonden op betrouwbaar omdat het bedrag goed
  gemeten is — maar het cyclusaantal is een fabrieksbelofte, en zes dagen
  zeggen niets over de ruil tussen minder cyclen en minder opbrengst;
- de **prijsvorm** stond op betrouwbaar omdat de vorm stabiel is — 
  terwijl er letterlijk bij staat dat de winst pas te becijferen valt
  zodra de voorspelde vorm naast de werkelijke prijzen kan.

Aan de lijst was niet te zien welke van de twee bedoeld werd.

### Nu apart

Elke kandidaat draagt een **gereedheid**:

| | |
|---|---|
| ⚪ meet nog | de meting zelf klopt nog niet |
| 🟡 winst onbekend | de meting klopt, maar wat meesturen oplevert is niet becijferd |
| ✅ klaar om mee te doen | allebei rond |

Met de cijfers van 17 augustus staat er precies **één** op groen: de
slijtagekosten. De prijsvorm staat op oranje, de rest meet nog.

Bovenaan de proefstandpagina staat nu een samenvatting, zodat "is er al
iets rijp?" met één blik te beantwoorden is in plaats van door zeven
kandidaten te lezen.

Er verandert niets aan de aansturing. Maar de vraag die hierachter zit —
*welke kandidaat mag als eerste meesturen* — is nu zelf te beantwoorden.

**Volledige testsuite**: 2315 tests, allemaal groen.

## v3.0.1 — "15 gebruiksmomenten vandaag, 0 liter"

**Gemeld** met een screenshot, terwijl er niemand thuis was.

Vijftien momenten van elk nul liter is intern al tegenstrijdig, en dat
was meteen de verklikker. De sessies bleken van **14 augustus** — drie
dagen eerder.

De teller werd alleen omgezet bij een **nieuwe sessie**. Gebeurde er een
dag niets, dan bleef die van eergisteren staan. Het litertotaal klopte
wel, want dat komt uit een andere teller.

### Vijfde keer een dagwissel die niet loopt

Na v1.74.0 (plantoetsing), v1.95.0 (opruiming op een lege lijst),
v1.98.0 (accu en kosten op nul) en v2.6.1 (verkeerde datum). Steeds
dezelfde vorm: een dagteller die afhangt van een gebeurtenis in plaats
van van de klok.

De waterteller rolt nu om **op de klok**, elke ronde.

En er staat een bredere toets bij die elke dagsleutel in de code
nagaat: wordt hij ergens met de klok vergeleken, of alleen bij een
gebeurtenis die er misschien niet komt? Zonder die toets komt deze vorm
een zesde keer terug.

**Volledige testsuite**: 2320 tests, allemaal groen.

## v3.0.2 — "Accukoeling an of uut" — maar wélke?

**Gemeld**: "Melding accu koeling aan/uit is niet goed (…) Maar het is of
hij is aan (koelen) of hij is uit (niet koelen)."

De Nederlandse titel zei wél *"koeling AAN"* of *"koeling UIT"*. De
Achterhoekse vertaling verving die hele titel door één vaste tekst —
*"Accukoeling an of uut"* — en daarmee verdween precies de informatie
waar het om ging.

### Vier meldingen, niet één

Bij het nazoeken bleken er **vier** soorten een wisselende Nederlandse
titel te hebben en toch één vaste Achterhoekse: accukoeling, apparaat
klaar, goedkoop moment en afwijkend apparaat. Alle vier krijgen nu hun
onderscheid terug.

### En de actie staat nu ook in het bericht

*"De ventilator gaat AAN."* voorop, vóór de meetwaarden. Staat de actie
ook daar, dan gaat hij niet verloren als de titel wordt vervangen of
afgekapt — en dat is precies wat hier gebeurde.

### Twee eigen tests deden hun werk

Mijn eerste poging schreef *"kloar"*, en de spellingstest uit v1.35.0
viel er meteen over: de WALD-spelling kent **ao** als zelfstandig teken,
en "oa" bestaat niet. Het moet *"klaor"* zijn.

**Volledige testsuite**: 2323 tests, allemaal groen.

## v3.1.0 — "Accukoeling an of uut" zei niet wat er gebeurde

**Gemeld** met een melding van 17 augustus 14:34:

> Accukoeling an of uut
> Accu 30.0°C, buiten 20.4°C, delta 9.6°C, vermogen 1080W — accu 30.0°C,
> nog maor 9.6°C boven buiten en 1080W belasting

"Maar het is of hij is aan (koelen) of hij is uit (niet koelen)."

Terecht. De reden verraadt het wel — *"nog maar 9,6°C boven buiten"* is de
uitschakelvoorwaarde — maar dat moet je afleiden.

**En de informatie was er al.** De Nederlandse titel maakte het
onderscheid: "koeling AAN" of "koeling UIT". De Achterhoekse vertaling
gooide het weg door één vaste titel voor de hele soort te gebruiken.

Nu:

| Actie | Titel |
|---|---|
| aan | De koeling geet an |
| uit | De koeling geet uut |

De actie wordt afgeleid uit de Nederlandse titel, zodat er geen extra
parameter door de hele meldingsketen hoeft.

**Een vangnet erbij**: komt er een soort bij waarvan de titel twee kanten
op kan, dan valt de test om. Een vaste titel per soort werkt alleen als
die soort altijd hetzelfde betekent.

### En de kaartwaarden nagelopen

Bij dezelfde controle: de ingebouwde dashboardcontrole liep **69
verwijzingen** na — geen niet-bestaande entiteiten, geen ontbrekende
attributen. Zeven zichtbare waarden zijn met de hand uit de brongegevens
nagerekend (zelfvoorziening, cycli, beschikbare energie, rendement,
bandbreedte, zelfconsumptie, accuprijs per kWh) en klopten alle zeven.

De slijtage staat op 4,22 ct/kWh op drie onafhankelijke plekken in de
export — precies de kruiscontrole die eerder wél fouten opleverde.

**Volledige testsuite**: 2330 tests, allemaal groen.

## v3.2.0 — Negen tegels lazen sensoren die de integratie niet levert

**Gemeld** met een screenshot van de kostenpagina: vijf van de zes
eurotegels op **€ 0**, terwijl er onderaan wél *"−20,44 € stroom deze
week"* stond. Dat spreekt elkaar tegen.

De tegels lazen negen **zelfgemaakte helper-sensoren**:
`sensor.ems_ontlaadwaarde_*`, `..._netlaadkosten_*` en
`..._accubesparing_*`. Die maakt de integratie nergens aan, en ze staan
nergens in het changelog — ze zijn er ooit ingekomen zonder bron.

Een dashboard dat de integratie meelevert mag alleen leunen op wat die
integratie zelf levert. Anders werkt het bij de een en niet bij de ander.

### Nu uit eigen gegevens

Alle negen tegels lezen het **periodeoverzicht**: kosten, accu-ontlading
en besparing per dag, week en maand. Dezelfde bron als de
Perioden-pagina, dus dezelfde getallen — en tikken op een tegel brengt je
daar.

Wat daarbij bleek: **drie van die nullen waren correct.** De
netlaadkosten zijn werkelijk nul, want er wordt niet van het net geladen
(`total_charge_cost_eur` staat op 0,0). Alleen de ontlaadwaarde en de
besparing waren stuk.

### En de controle had een blinde vlek

`get_dashboard_health` liep 69 verwijzingen na en meldde niets — maar
keek alleen naar `state_attr`-aanroepen en alleen naar het domein
`sensor.`. Switches en buttons werden **helemaal niet** nagelopen, en een
tegel die naar een verdwenen schakelaar wijst toont "Entiteit niet
gevonden" zonder dat er iets van te zien was.

Nu alle domeinen, plus een test die omvalt zodra er weer een
`sensor.ems_*` op het dashboard belandt.

**Volledige testsuite**: 2332 tests, allemaal groen.

## v3.3.0 — Onenigheid over de bewolking als kenmerk

**Gevraagd**: "Is er een integratie beschikbaar welke de bewolking per
uur voorspelt (dus ook morgen)? Misschien kan dat nog helpen in de PV
voorspelling?"

Die bestaat, en draait al: `weather.get_forecasts` op de twee ingestelde
weerentiteiten levert `cloud_coverage` per uur, ook voor morgen. Er is
niets bij te installeren.

*(De aangedragen `openweathermap.get_minute_forecast` is het niet: die
levert alleen **neerslag** in mm/uur, en alleen voor de komende zestig
minuten.)*

### Maar de winst zit er waarschijnlijk niet

Solcast **verwerkt bewolking al** — hun voorspelling is een bewerking van
satellietbeelden en weermodellen. Bewolking van OpenWeatherMap ernaast
leggen voegt vermoedelijk een tweede afgeleide van hetzelfde weerbeeld
toe, vaak minder actueel.

En de 41% fout op de slechtste dagen komt niet doordat niemand wist dat
het bewolkt zou worden. Hij komt doordat wolkenvelden op een ander
**tijdstip** overtrokken dan voorspeld, en dat lost geen bewolkingsbron
op.

### Wat wél nieuw is: de onenigheid

Op 16 augustus stond de ene bron op **100%** bewolking en de andere op
**15%**. Dat zegt niets over de bewolking, maar wel dat de dag moeilijk
te voorspellen is — net als de Solcast-bandbreedte.

Dat verschil is nu een kenmerk van het regressiewoud. Of het helpt, wijst
het woud over drie weken zelf uit.

### En een valkuil onderweg

Een ontbrekend kenmerk maakte de **hele rij** onbruikbaar. Bij de
voorspelling en het uur is dat terecht, maar wie maar één weerbron heeft
ingesteld krijgt nooit een onenigheidsgetal — en dan zou het model
**nooit** iets leren.

Ontbreekt een los kenmerk bij alle monsters, dan valt nu de **kolom** weg
in plaats van de rijen.

**Volledige testsuite**: 2337 tests, allemaal groen.

## v3.4.0 — Wat de diagnostiek miste

**Gevraagd**: "Kun je nog wat verbeteren aan de diagnostiek van mijn EMS
zodat we hem nog beter kunnen maken?"

Drie dingen die deze week **aantoonbaar tijd kostten**.

### 1. De versie stond er niet in

Op 17 augustus kwam een koelmelding binnen met de oude tekst, terwijl de
reparatie was opgeleverd. Om te bepalen of de nieuwe code draaide moest
worden afgeleid welke *functies* aanwezig waren — twee ronden werk voor
iets wat één regel had kunnen zijn.

Nu staan versie, starttijd, draaiduur, Home Assistant-versie en
Python-versie in de export.

### 2. De eigen waarschuwingen verdwenen

Alles wat via `_LOGGER.warning` of `_LOGGER.exception` wordt
weggeschreven, verdwijnt in het logboek van Home Assistant — en dat zit
niet in de export.

De `NameError` die het inlezen van de geschiedenis bij **elke start** liet
omvallen stond alleen daar. Het duurde drie diagnostieken en twee versies
voordat die boven water kwam.

De laatste zestig eigen meldingen vanaf niveau *waarschuwing* zitten er
nu in. Alleen de eigen; wat andere integraties loggen blijft onzichtbaar.

### 3. Een half aangekomen update was niet te zien

Tijdens de GitHub-storing van diezelfde middag — 50% foutkans op
downloads — kan een installatie half aankomen: het ene bestand nieuw, het
andere oud. Aan de buitenkant is dat niet te zien, maar wel aan
wijzigingsmomenten die ver uit elkaar liggen.

Tiende kruiscontrole erbij: liggen de bronbestanden meer dan een uur uit
elkaar, dan is dat een bevinding.

*Bij het bouwen hiervan sloeg de eigen test uit v2.0.6 meteen aan: het
manifest werd in de event loop gelezen. Dat gebeurt nu bij het opstarten,
in een executor.*

**Volledige testsuite**: 2345 tests, allemaal groen.

## v3.4.1 — Het versienummer klopte al vier opleveringen niet

**Gevonden dankzij de verbetering uit v3.4.0.** In de export stond
`"versie": "3.0.2"` — terwijl de code aantoonbaar v3.4.0 was: tien
kruiscontroles, logopvang, installatiegegevens, en de koelmelding die nu
*"De koeling geet an"* zegt.

De ironie is compleet: de verbetering die deze fout aan het licht bracht,
was in dezelfde oplevering gebouwd. Zonder dat veld was hij onzichtbaar
gebleven.

### De oorzaak is de werkwijze, niet de code

Elke oplevering verhoogde het nummer met een zoek-en-vervang op de
**oude** waarde:

    sed -i 's/"version": "3.3.0"/"version": "3.4.0"/' manifest.json

Klopt die oude waarde niet, dan doet het commando **niets** — zonder
foutmelding. Vier opleveringen op rij zijn zo stilzwijgend mislukt, en ik
heb het nooit gecontroleerd.

Hetzelfde gold voor het testaantal in de README: dat stond op **2194**
terwijl er 2352 draaien.

### En het was al vaker gebeurd

Het changelog bevat vijf nummers die twee keer zijn gebruikt: 1.46.0,
2.1.0, 2.2.0, 2.2.2 en 2.3.0. Dezelfde fout, eerder opgetreden zonder dat
iemand het zag.

**Die geschiedenis wordt niet herschreven** — dat zou verslaglegging
vervalsen. De nieuwe toetsen bewaken wat er vanaf hier bij komt, met een
vangnet dat omvalt zodra er een zesde dubbel nummer verschijnt.

Manifest, README, dashboard en changelog staan nu alle vier op **3.4.0**,
en zes tests houden dat zo.

**Volledige testsuite**: 2352 tests, allemaal groen.

## v3.5.0 — Repairs, en de reserve rekent met de gemeten accu

Twee punten uit een externe review die hout sneden.

### 1. Repair Issues

> "Ik mis een vermelding van Repair Issues. Veel meldingen worden nu via
> notificaties, dashboard en diagnostiek afgehandeld. Maar Home Assistant
> heeft tegenwoordig een uitstekend Repairs-framework."

Terecht, en het beste punt uit die review. Wat er tot nu toe gebeurde bij
een ontbrekende sensor: een melding op de telefoon die je wegklikt, een
regel op een dashboardpagina die je moet opzoeken, en een veld in de
diagnostiek dat alleen bij een export zichtbaar is.

Vier soorten verschijnen nu in **Instellingen → Repairs**:

| | |
|---|---|
| Ontbrekende ingang | een onderdeel leest een sensor of attribuut dat er niet is |
| Halve installatie | de bronbestanden liggen meer dan een uur uit elkaar |
| Interne fout | een onderdeel valt om |
| Dashboardkaart wijst naar niets | de entiteit bestaat niet meer |

Ze verdwijnen zodra het probleem over is. Dat is even belangrijk als het
plaatsen: een Repairs-scherm dat vol blijft staan met opgeloste dingen
wordt niet meer gelezen.

**Alleen wat de gebruiker zelf kan verhelpen** komt hier terecht. Een
leerproces dat nog dagen nodig heeft is geen reparatie maar geduld, en
zoiets in Repairs zetten leert mensen het scherm te negeren. Een test
bewaakt dat.

### 2. De reserve rekent met de gemeten capaciteit

> "Nominaal 8,64 kWh, gemeten 7,95 kWh, degradatie 8% — en automatisch de
> reserveberekening aanpassen."

Ook terecht. De reserve rekende met de **nominale** waarde uit de sensor.
Levert de accu feitelijk minder, dan wordt er gerekend op energie die er
niet is, en is elke reserveberekening structureel optimistisch.

Vanaf nu de gemeten waarde zodra die er is — na de bestaande drempel van
trenddagen. Met twee grenzen: een meting **boven** nominaal wordt
afgekapt, en een meting die meer dan een derde **onder** nominaal ligt
wordt geweerd. Dat laatste is eerder een meetfout dan een versleten accu,
en anders zou een verkeerd uitgelezen sensor de hele accu blokkeren.

Er is één functie waar dit doorheen loopt, niet dertien losse aanroepen —
dat is precies wat er met de reservemarge misging in v1.86.0 tot en met
v1.88.0.

### Wat uit de review niet klopte

De README zou te groot zijn: die is **434 regels**, sinds v1.77.0
teruggebracht van 12.389, met het dagboek al in `docs/`. En de scheiding
tussen advies en sturing bestaat al: alle service-aanroepen zitten in de
coordinator, buiten het bereik van de adviesmodules, met tests per
kandidaat. Het versienummer klopte inderdaad niet — dat was een uur
eerder al gevonden en gerepareerd in v3.4.1.

**Volledige testsuite**: 2363 tests, allemaal groen.

## v3.6.0 — Koelen als het bijna niets kost

**Gemeld** op 18 augustus, 07:57: "De accu moet meer gekoeld worden, hij
is nu 31 graden en de buitentemperatuur is veel lager."

Terecht. De ventilator stond stil omdat 31 °C onder de aanzetdrempel van
35 ligt. Die drempel beschermt de **omvormer** — die regelt pas terug als
hij warm wordt. Maar hij zegt niets over de vraag of koelen de moeite is.

Bij **31 °C met 14,1 °C buiten** is er bijna zeventien graden te halen
voor een ventilator van een paar watt. Wachten tot 35 is dan zonde.

### Een kans, geen noodzaak

De cellen stonden op dat moment op **21 tot 23 °C** — ruim onder de
grens waarboven LFP versneld veroudert. Er was dus geen alarm. Maar
koelen dat bijna niets kost en meetbaar veroudering scheelt, is de moeite
waard.

De ventilator gaat nu ook aan onder de hoofddrempel, mits:

- de omvormer boven **28 °C** zit (instelbaar), en
- er minstens **12 °C** verschil met buiten is.

Boven 35 °C verandert er niets: de bestaande bescherming van de omvormer
blijft precies zoals hij was.

De drempel is instelbaar, want deze getallen zijn schattingen — Zendure
publiceert niet wanneer de omvormer terugregelt, zoals in v1.80.0 al
werd vastgelegd.

### Onderweg

`_battery_cooling_should_turn_on` was een `@staticmethod` en kan nu bij
de configuratie. Achttien tests vielen daardoor om — allemaal omdat ze de
functie op de klasse aanriepen, geen enkele omdat het gedrag veranderde.
De bestaande drempels zijn ongemoeid.

**Volledige testsuite**: 2369 tests, allemaal groen.

## v3.6.1 — Het regressiewoud verzamelde niets

**Gevonden door het logboek uit v3.4.0**, binnen één dag na invoering:

    ERROR coordinator:12261: Kon het PV-modelmonster niet vastleggen
    NameError("name 'hour' is not defined")

Elk afgesloten licht uur, sinds v2.9.0. De aanroep gebruikte `hour`,
terwijl het uur daar `self._pv_current_tracked_hour` heet.

De `try/except` eromheen ving dat netjes op — dus alles bleef werken en
er was niets van te zien. Behalve dan dat het regressiewoud **nul
monsters** verzamelde. De drie weken wachten op cijfers waren voor niets
geweest, en dat zou pas over drie weken zijn opgevallen als de kandidaat
nog steeds "0 van 150 uren" had gemeld.

Precies waarvoor dat logboek is toegevoegd, en sneller dan verwacht.

### En een scan die dit voortaan vangt

Er stond al een AST-scan op **methoden** die niet bestaan (die ving in
v2.9.0 nog een ontbrekende functie). Nu ook een op **variabelen**: een
naam die als argument aan een eigen methode wordt meegegeven en in die
functie niet bestaat.

Die scan kostte vier pogingen, en elke misser is het vermelden waard:

- eerst gold `hour` als bekend omdat de naam **elders in het bestand**
  bestond — en juist daardoor viel de fout niet op;
- toen omdat `ast.walk` over `boom.body` ook élke naam uit élke methode
  meenam als "modulenaam";
- toen omdat geneste functies de namen van hun omhulsel zien;
- en toen omdat `ast.walk` vanuit de buitenste functie ook de aanroepen
  in geneste functies beoordeelde.

Elke tussenversie is getoetst door de fout terug te zetten. Pas de
laatste is groen op de goede code en rood op de foute.

**Volledige testsuite**: 2370 tests, allemaal groen.

## v3.7.0 — De koeltegel zei twee keer hetzelfde

**Gemeld** met een screenshot:

> niet actief
> Accu-koeling: niet actief

Twee regels, dezelfde tekst, geen enkel getal. Terwijl er op dat moment
gewoon **31,0 °C omvormer tegen 14,1 °C buiten** in de toestand stond —
de tegel liet het alleen niet zien.

De tegel toont nu beide temperaturen, het verschil, het vermogen en de
reden waarom er wel of niet wordt gekoeld.

### En "niet actief" was misleidend

Dat kan drie dingen betekenen: geen ventilator ingesteld, geen
temperatuursensor, of nog geen ronde geweest. Geen ervan is te
onderscheiden van een defect.

De sensor zegt nu welke het is.

### Waarom de voorgestelde regel er niet is gekomen

Gevraagd: "Omvormer temp >5 graden hoger dan buiten temp = koelen? Als
het vermogen >500 is ook koelen?"

Doorgerekend op de twintig gemeten schakelmomenten:

| Regel | Zou aanslaan |
|---|---|
| Huidig (v3.6.0) | 11 van 20 |
| Delta > 5 °C | **20 van 20** |
| Vermogen > 500 W | 15 van 20 |

Bij **alle** gemeten momenten was het verschil groter dan vijf graden.
Een omvormer staat normaal boven de buitentemperatuur; dat is werking,
geen alarm. De ventilator zou dus permanent draaien — ook bij 21 °C, waar
niets te koelen valt, met cellen op 21 tot 23 °C die ruim onder de
verouderingsgrens zitten.

Wie toch vaker wil koelen: de drempel van 28 °C staat sinds v3.6.0 bij
Configureren en kan naar 25. Dat dekt de twee gemeten gevallen van 26 en
27 °C zonder dat de ventilator bij 21 °C gaat blazen.

**Volledige testsuite**: 2375 tests, allemaal groen.

## v3.7.1 — Elke ronde viel om (installeer dit met spoed)

**Gemeld** met een screenshot: twee tegels op "unknown". De oorzaak was
ernstiger dan de tegels.

`last_successful_update` stond op **None**: sinds het opstarten om 08:33
had er geen **enkele** ronde gedraaid. De integratie stuurde niets meer
aan.

    TypeError: _koelen_is_goedkoop() missing 1 required positional
    argument: 'buiten_c'

### Een decorator die aan de verkeerde functie plakte

In v3.6.0 is `_koelen_is_goedkoop` ingevoegd **tussen** een
`@staticmethod`-decorator en de functie waar die bij hoorde. De decorator
kwam daardoor op de nieuwe functie te staan: `self` werd de eerste echte
parameter, en er bleef er één over.

### Wat dit blootlegt

**Alle 2375 tests bleven groen.** Geen enkele riep die functie aan via
een echt object — de testhulpfunctie plakte hem los op een kale klasse,
en dan werkt het toevallig wél.

Twee scans erbij:

- een `@staticmethod` met `self` als eerste parameter;
- een gewone methode die zonder object wordt aangeroepen.

Beide op de proef gesteld door de fout terug te zetten.

Dat de fout via de tegels binnenkwam en niet via het logboek is geen
toeval: het logboek uit v3.4.0 **had** hem, met dertig identieke regels.
Alleen was er niet naar gekeken zolang niemand iets meldde.

### De onderliggende oorzaak

**Gemeld** uit bedrijf:

    _koelen_is_goedkoop() missing 1 required positional argument:
    'buiten_c'

Bij het invoegen van die functie in v3.6.0 schoof de `@staticmethod` van
de **onderliggende** functie naar de nieuwe. Daardoor gaf
`self._koelen_is_goedkoop(accu_c, buiten_c)` twee argumenten aan een
functie die er drie verwacht — `self` telt bij een statische methode mee
als gewone parameter.

Gevolg: de koelbeslissing viel bij elke ronde om, precies de regel die
v3.6.0 kwam toevoegen.

Deze soort fout is met het blote oog nauwelijks te zien: de decorator
staat een regel hoger en hoort visueel bij de vorige functie. In de
testsuite viel hij niet op omdat die de functie via een eigen hulpobject
aanriep, waar het wél goed ging.

**Nu een scan** die elke statische methode nagaat: heeft hij `self` als
parameter, of gebruikt hij `self` in de code? Beide kan niet. Op de proef
gesteld door de decorator terug te zetten — dan valt hij om.

Dit is de tweede structuurscan in twee dagen die uit een echte fout is
voortgekomen, na die op onbekende variabelen in v3.6.1.

**Volledige testsuite**: 2377 tests, allemaal groen.

## v3.8.0 — Eén fout legde de hele aansturing plat

**Gevraagd**: "Is het planningsprobleem daarmee ook opgelost?" — bij twee
screenshots met *"unknown / Verwachte modus"* en *"nog geen beslissing /
nog geen schema"*.

**Ja.** En het antwoord op de vraag erachter is belangrijker dan de
reparatie.

De planning was niet berekend, en dat had **niets met de planning te
maken**. Aan het eind van elke ronde stonden twintig aanroepen
ongeschermd op een rij: dagkosten, beslislogboek, accukoeling,
zelfvoorziening, CO₂, klimaatleren.

De `NameError` in de accukoeling uit v3.7.1 brak de hele ronde af. Alles
daarna verviel, de ronde eindigde nooit succesvol, en dus bleven ook de
beslissing en het schema leeg.

### Een leerroutine hoort de aansturing niet plat te leggen

Elk staartonderdeel is nu apart afgeschermd. Wat omvalt wordt gemeld in
`internal_failures` en overgeslagen; de rest loopt door.

**Stil overslaan zou net zo erg zijn** — dan werkt de integratie half
zonder dat iemand het merkt, precies de fout die v2.2.4 opleverde. Daarom
komt elke omgevallen stap in de diagnostiek terecht, en daarmee ook in
Repairs.

Een vangnettest valt om zodra er een aanroep aan het staartstuk wordt
toegevoegd die niet door dezelfde afscherming loopt. Die vond meteen nog
één ongeschermde stap: het geplande apparaat.

**Volledige testsuite**: 2381 tests, allemaal groen.

## v3.9.0 — 75 tekortmeldingen, waarvan 47 op één dag

**Gemeld**: "Deze melding op dit tijdstip is een beetje raar toch?" bij

> 18 Aug 09:30 · Den accu haalt de nacht weer

De bewoording was inderdaad raar. Maar de geschiedenis liet iets ergers
zien: **75 meldingen** over tekorten, waarvan **47 op 16 augustus
alleen**. Twaalf keer ging het om één enkel kwartier. Om 06:44 stond
"hersteld", om 06:45 weer "tekort" — en om 00:00 kwamen beide in dezelfde
minuut.

Drie dingen deugden niet.

### Een randgeval werd als alarm behandeld

Eén kwartier tekort is bij dit verbruik zo'n **0,1 kWh** van het net.
Dat is geen probleem maar een planning die precies uitkomt. Bij een
laagste stand van exact 10% kantelt elke kleine verschuiving in de
zonverwachting het.

De drempel ligt nu op **drie kwartieren**.

### Geen demping op de omslag

De planning wordt elke ronde opnieuw gebouwd en schommelt rond de grens;
elke passage gaf een bericht. "Hersteld" komt nu pas na een **half uur
stabiel**, en een terugkerend tekort zet die klok opnieuw.

### En de tekst klopte niet

"Haalt de nacht" om half tien 's ochtends slaat nergens op — het tekort
kan op elk moment binnen de horizon liggen. De melding noemt nu het
**tijdvak** uit de planning, die dat al kende: *"morgen 07:00-09:00"*.

Dezelfde fout als bij het goedkoopste blok (v2.5.0) en het duurste blok
(v2.7.0): een tekst die een tijdstip suggereert dat er niet is.

### Wat dit op de gemeten reeks doet

| | |
|---|---|
| Waarschuwingen over 1–2 kwartieren, vervallen | **17** |
| Waarschuwingen die blijven | 22 |
| Herstelmeldingen, nu met wachttijd | 36 |

**Volledige testsuite**: 2390 tests, allemaal groen.

## v3.10.0 — De reserve kijkt niet ver genoeg vooruit

**Gevraagd**: "Het gaat er mij vooral om dat er niet gewacht wordt tot
een duur kwartier om extra bij te laden. De integratie moet ruim vooruit
kijken."

Terecht, en de cijfers van 18 augustus laten het precies zien.

De reserve rekent tot het **eerstvolgende goedkope blok** — die dag tot
16:45. Wat daarna kwam telde niet mee:

| | |
|---|---|
| Goedkoopste kwartier ín het blok | 28,9 ct |
| Avondpiek ná het blok | **37,4 ct** |

Gevolg: er wordt geladen wat nodig is *tot* het blok, niet wat nodig is
tot de volgende gelegenheid. Kom je 's avonds tekort, dan zit je in de
dure uren en is het te laat.

### Eerst meten

Gevraagd: "Eerst als meting, via de diagnostiek kun je dan later bepalen
of sturen wenselijk is toch?" Precies — dezelfde route als de
slijtagekosten.

Nieuwe proefstandkandidaat die elke ronde beide reserves uitrekent: tot
het goedkope blok, en tot het eind van de bekende prijzen. Plus wat het
verschil zou **kosten** (laden in het blok, na rendement en slijtage) en
wat het zou **besparen** (het duurste kwartier daarna).

**Hij stuurt niets.** Meer reserve betekent minder verkopen, en dat loont
alleen als het prijsverschil de accukosten dekt. Bij 84,5% rendement en
4,22 ct slijtage is dat ruwweg **11 ct** — en vandaag zat er maar 8,5 ct
tussen het blok en de avondpiek.

### Wat de bestaande kandidaten er al over zeggen

*"Vasthouden voor morgen"* staat inmiddels op **klaar om mee te doen**,
met een duidelijk antwoord: bij **0 van de 200** gemeten momenten was
vasthouden voordeliger, mediaan **−8,0 ct/kWh**. Dat meet de andere kant
van dezelfde economie.

Dat verandert na 1 januari: teruglevering levert dan nog 19 ct op tegen
32 ct inkoop, en dan komt het verschil ruim boven de drempel.

**Volledige testsuite**: 2398 tests, allemaal groen.

## v3.11.0 — Bijkopen bij een verwacht tekort: eerst meten

**Gevraagd**: "Maar wat als het rendabel is om bij te kopen wanneer er
niet genoeg PV energie is?"

Een andere vraag dan arbitrage, en dat verschil is wezenlijk. Je koopt
niet om te verkopen — je koopt om **niet later duurder te moeten kopen**.

Nu gebeurt er niets. Drie grendels blokkeren het: arbitragelading is
permanent verwijderd, `smart_charging` wordt niet toegepast omdat die de
piekbuffer uitschakelt, en de vergelijking accu-tegen-net is in v1.62.0
teruggedraaid.

### De negende kandidaat

Bij elk verwacht tekort wordt nu vastgelegd:

    nu laden = prijs_nu / rendement + slijtage
    straks   = prijs op het moment van het tekort

Loopt de PV-opbrengst achter, dan groeit het tekort en verschuift het
naar duurdere uren — precies waar deze meting op let.

**Hij stuurt niets.** Bij 84,5% rendement en 4,22 ct slijtage moet er
ruim 11 ct verschil zijn; op 18 augustus was dat 8,5 ct.

### De aansturingsroute is alvast vastgelegd

Meegegeven: "let op dat het bijladen vanaf het net in de modus **manual**
gebeuren moet, net als het ontladen op dure kwartieren, maar dan laden."

Dat staat nu in de kandidaat zelf: sturen zou gaan via `manual` met een
**positief** vermogen, waar het ontladen een negatief vermogen gebruikt.
Vastgelegd voordat er iets gebouwd wordt — anders is het over drie
maanden weg.

### Wat deze meting niet weet

Of er op dat moment ruimte in de accu was, en of het laden de piekbuffer
zou verstoren. Dat staat erbij, en het is precies waarom
`smart_charging` niet wordt toegepast.

Daarmee meten drie kandidaten dezelfde economie vanuit een andere hoek:
vasthouden voor morgen, verder vooruitkijken bij de reserve, en bijkopen
bij een tekort. Na 1 januari — 19 ct teruglevering tegen 32 ct inkoop —
wijzen ze waarschijnlijk alledrie dezelfde kant op.

**Volledige testsuite**: 2408 tests, allemaal groen.

## v3.12.0 — De integratie meldt zelf wanneer een kandidaat rijp is

**Gevraagd**: "Houd je dit zelf bij middels diagnostiek?"

Het eerlijke antwoord is **nee**. Er is geen geheugen tussen gesprekken
en geen toegang tot dit systeem; elke diagnostiek wordt op dat moment
gelezen en is daarna weg. Er komt geen seintje als een kandidaat omslaat.

Wat er wél bijhoudt is de integratie zelf — de metingen lopen door en
overleven herstarts. Maar dan moet de gebruiker onthouden dat hij over
drie weken moet kijken, en drie weken is lang.

**Nu komt het naar hem toe.** Springt een kandidaat van *meet nog* of
*winst onbekend* naar **klaar om mee te doen**, dan volgt een melding met
het getal en de onderbouwing erbij.

Alleen bij de **omslag**: een kandidaat die al maanden klaar staat is
geen nieuws. De lijst overleeft een herstart, anders zou na elke start
alles opnieuw worden gemeld.

De melding staat standaard aan, net als "onderdeel van de integratie
faalt" en de zelfcontrole. Staat hij uit, dan blijft een rijpe kandidaat
ongebruikt staan — en dat is precies wat deze melding moet voorkomen.

Demping: een dag. Deze gebeurtenis komt hooguit een paar keer per jaar
voor.

**Volledige testsuite**: 2415 tests, allemaal groen.

## v3.12.1 — De melding werkte, maar zei niets

**Gemeld** met de eerste melding uit v3.12.0:

> 'n Kandidaat is now zo wied
> **4.2 ct/kWh —**
> Meting en winst bunt allebei becijferd.

Na het gedachtestreepje stond niets. En er kwam **één** bericht terwijl
er **twee** kandidaten tegelijk rijp werden.

### Twee velden voor hetzelfde

De slijtagekandidaat legt zich uit in `toelichting`, de andere in
`reden`. De melding las alleen `reden` — en dan blijft er een streepje
over zonder onderbouwing. Een waarde zonder uitleg is erger dan geen
melding: je weet dát er iets is, maar niet wat.

Nu wordt `reden`, dan `toelichting`, dan de betrouwbaarheidstekst
gelezen. En een test controleert dat **elke** kandidaat zich ergens
verklaart.

### De demping werkte tegen

Twee kandidaten werden tegelijk rijp; de demping van een dag filterde de
tweede weg. Dat is per soort ingesteld, en dat klopt bij een herhaling —
maar dit was geen herhaling, dit was een tweede gebeurtenis.

Alle nieuwe kandidaten staan nu in **één** bericht, dat de demping maar
één keer raakt.

**Alle 2415 tests bleven groen** met beide fouten erin. Geen enkele las
de inhoud van de melding; ze controleerden alleen dát er een melding
kwam.

**Volledige testsuite**: 2419 tests, allemaal groen.

## v3.13.0 — De winterguard vergat de slijtage

**Gemeld** op 18 augustus 14:15: "Waarom wordt er vandaag zoveel van het
net gehaald, is toch meer als nodig vannacht?"

De cijfers: **5,33 kWh import bij 2,68 kWh verbruik**, accu op 80%, reden
`grid_charging_low_solar_extra_dip`. Er werd dus bewust van het net
geladen omdat er weinig zon werd verwacht — 11,5 kWh tegen een typische
18,6.

### De rekensom klopte, maar was onvolledig

| | |
|---|---|
| Inkoop om 14:15 | 28,9 ct |
| Duurste kwartier vandaag (21:15) | 38,3 ct |
| Marge bij 84,5% rendement | **+3,49 ct** → boven de drempel van 3,00 |

Alleen kost elke doorgezette kWh ook **4,22 ct aan slijtage**. Met dat
erbij wordt de marge **−0,73 ct**: dat laden kostte ongeveer een cent per
kWh in plaats van dat het bespaarde.

De slijtage telt nu mee. Met de gemeten cijfers van vandaag zou er geen
enkel uur meer zijn geladen.

### Waarom dit juist nu opviel

Deze regel is gemaakt voor de **winter**, wanneer het prijsverschil groot
genoeg is om de accukosten te dekken. Op een zomerdag met een vlak
prijsverloop — vandaag 8,5 ct tussen dal en piek — pakt hij verkeerd uit.

Dat is precies wat de bijkoop-kandidaat uit v3.11.0 meet. Alleen stuurde
die niets, terwijl deze regel dat wél deed.

### Wat ongemoeid blijft

Het **hoofdblok** van de winterguard heeft bewust géén rendementstoets —
uitdrukkelijk zo gevraagd, omdat dat per definitie het goedkoopste moment
van de dag is. Die keuze staat, en een test bewaakt dat ze niet
stilzwijgend verdwijnt.

**Volledige testsuite**: 2425 tests, allemaal groen.

## v3.14.0 — Aan bij 27, uit bij 27

**Gevonden door de zelfcontrole**: *"8 schakelingen in de laatste 6 uur -
dat wijst op pendelen rond een drempel."*

En dat klopte, met een pijnlijke bijzonderheid: het pendelen liep **netjes
op de klok** van de minimale looptijd uit v1.99.0. Precies dertig minuten
tussen elke schakeling.

    09:17  aan   27 °C, 14,8 buiten
    09:47  uit   21 °C   (30 min later)
    10:18  aan   27 °C   (30 min later)
    10:49  uit   23 °C   (30 min later)
    11:19  aan   29 °C   (30 min later)

### Een tegenstelling, geen hysterese

De regel uit v3.6.0 zet de ventilator aan zodra de omvormer boven de
drempel zit en het buiten veel kouder is. Maar de gewone uitschakelregel
stopt hem onder de **32 graden** — dus aan bij 27, en meteen weer uit bij
27.

De gewone koeling heeft die marge wel: aan bij 35, uit onder 32. De
goedkope koeling had hem niet.

Nu loopt de goedkope koeling door tot **vijf graden onder de
aanzetdrempel**, mits het verschil met buiten groot genoeg blijft. Dan
draait de ventilator één keer langer in plaats van drie keer kort.

Op de gemeten schakelingen van 18 augustus vervallen daarmee **twee van
de vijf** uitschakelingen.

### Onderweg

`_battery_cooling_should_turn_off` was een `@staticmethod` en kan nu bij
de configuratie. De scan uit v3.7.1 ving dat meteen af — dezelfde fout
die daar een dag eerder in bedrijf was opgetreden, nu voordat hij de deur
uit ging.

**Volledige testsuite**: 2430 tests, allemaal groen.

## v3.15.0 — Koelen is bescherming, geen aansturing

**Gemeld**: "Koelen mag niets te maken hebben met goedkoop of dure
prijzen, hij moet wanneer nodig altijd koelen."

### De naam was ongelukkig

"Goedkoop koelen" uit v3.6.0 sloeg op de **ventilator** — een paar watt
voor veel koeling als het buiten kouder is — niet op de stroomprijs. Dat
was verwarrend, en terecht opgemerkt.

Nagekeken in de code: **geen enkele koelfunctie raakt een prijs.** Niet
`evaluate_battery_cooling`, niet de aan- of uitschakelregels, niet de
hysterese. Er staat nu een test op die dat vastlegt voor alle vijf.

### Maar er wás een blokkade

In **leermodus** of bij **handmatige overname** werd de ventilator niet
geschakeld — ook niet bij een te warme accu. Voor de accusturing is dat
terecht: die schakelaars zeggen "raak mijn accu niet aan".

Maar een ventilator laadt of ontlaadt niets; hij beschermt alleen. Wie de
sturing overneemt wil niet dat zijn accu ondertussen oververhit.

Boven **35 °C** wordt er nu doorgeschakeld, ook in die twee standen.
Daaronder blijft de oude terughoudendheid gelden: dan is koelen een
optimalisatie, en die hoort te wijken voor wie de sturing overneemt.

De reden vermeldt het expliciet: *"wél uitgevoerd ondanks force manual:
koelen is bescherming, geen aansturing"*.

**Volledige testsuite**: 2433 tests, allemaal groen.

## v3.16.0 — Zelfvoorziening van −103%

**Gemeld** met een screenshot: *"−103.2% Zelfvoorziening"*. Een schaal
die van 0 tot 100 loopt kan daar niet uitkomen.

De rekensom klopte, maar de **vraag** niet:

| | |
|---|---|
| Verbruik vandaag | 2,87 kWh |
| Import vandaag | **5,88 kWh** |

Het verschil zat in de **accu** — de winterguard had bijgeladen. De
formule nam aan dat alle import naar het huis gaat, en telde die
accu-energie dus mee als "verbruik dat niet zelf is opgewekt".

Wat er van het net de accu in gaat is geen huisverbruik. Die kWh wordt
later gebruikt of verkocht, en telt dán mee — niet nu.

Er is een dagteller bijgekomen voor netlading; die gaat er nu vanaf.

### En de zelfcontrole rekende mee

De kruiscontrole op zelfvoorziening gebruikte dezelfde oude formule. Was
die niet meegewijzigd, dan had hij vanaf nu **elke dag** een fout gemeld
die er niet is — precies het soort valse melding waar we deze week al
tweemaal iets aan hebben moeten doen.

Een test bewaakt dat beide formules gelijk blijven.

**Volledige testsuite**: 2441 tests, allemaal groen.

## v3.17.0 — Het visuele overzicht opnieuw gebouwd

**Gevraagd**: dynamisch maken, kleinere getallen, leesbaar op elk
apparaat, klikbaar, en de stromen inzichtelijk.

Vijf wensen, en ze hadden alle vijf dezelfde oorzaak: de kaart was een
**statische SVG** met `picture-elements` eroverheen, met vaste
pixelgroottes.

| Klacht | Oorzaak |
|---|---|
| Zon bij 99,6% bewolking | het weerbeeld zat ín het plaatje |
| "0.2900598 €/kWh" | rauwe sensorwaarde, geen opmaak |
| Slecht leesbaar op mobiel | vaste pixels, geen `viewBox` |
| Niets klikbaar | alleen `more-info`, geen navigatie |
| Geen stromen | niet te tekenen zonder de achtergrond te vervangen |

De plaat wordt nu elke ronde opnieuw opgebouwd in code.

### Wat er verandert

**Het weerbeeld volgt de bewolking** — zon, licht bewolkt, halfbewolkt of
wolk. De bewolking beslist, niet de opwek: 's avonds is er geen opwek
terwijl het helder kan zijn.

**Getallen zijn afgerond**: 29,0 ct/kWh, 6,65 kWh, 268 W. Boven de
kilowatt schakelt het vermogen om. Een ontbrekende waarde toont een
streepje, geen verzonnen nul.

**Eén `viewBox` zonder vaste breedte** schaalt vanzelf mee met het
scherm.

**Elk blok is klikbaar** naar zijn detailpagina, en een test controleert
dat elke link naar een pagina wijst die bestaat.

**Stromen als pijlen** waarvan de dikte en de loopsnelheid het vermogen
volgen. Onder 25 watt wordt er niets getekend — een pijl die altijd staat
zegt niets. Het netvermogen wordt afgeleid uit verbruik min zon min accu;
daar was geen sensor voor.

### Onderweg

Drie sensoren stonden **alleen** op de oude kaart en zouden zijn
verdwenen. De bestaande test ving dat af; ze hebben nu een echte plek op
de Integratiegezondheid-pagina in plaats van alleen in een plaatje.

En een test hield tegen dat de plaat `heavy_load_source` zou tonen als
grootste verbruiker — dat is een beslislogica-signaal, en die verwarring
was eerder al rechtgezet.

**Volledige testsuite**: 2434 tests, allemaal groen.

**Gevraagd** na een schermafbeelding van een Grid Support Unit: "Deze
style vind ik wel mooi." En daarna: "Ik wil alleen de 'visueel' pagina
geüpdate hebben, de rest is goed."

Alleen die pagina dus. De 31 andere blijven precies zoals ze waren.

### Wat is overgenomen

| | |
|---|---|
| Halve-cirkelmeters | accustand, omvormertemperatuur, beschikbare energie |
| Groot vermogensgetal | met LADEN / ONTLADEN / RUST eronder |
| Installatieschema | zon, huis, net, met de accu eronder |
| Staafjes per module | temperatuur en celspreiding naast elkaar |
| Één kleurschema | cyaan op donkerblauw, **rood alleen bij alarm** |

Die staafjes zijn hier het nuttigst: module 1 loopt al een week uit de
pas, en in een tabel zie je dat pas als je de getallen naast elkaar legt.

### Wat bewust níet is overgenomen

Op het voorbeeld staat *"Power capacity 413 kW"* in een halve cirkel. Dat
is versiering: een waarde die nooit beweegt hoort geen meter te krijgen.
**Alles op deze plaat beweegt**, en een test bewaakt dat.

Een ontbrekende waarde toont een **streepje**, geen nul — een naald op
nul lijkt een meting.

### Onderweg gevonden

Het huisverbruik stond gelijk aan de netafname. De P1-meter meet alleen
het net; zodra de accu bijspringt klopt dat schema niet. Nu net plus zon
min accu.

En de scan uit v3.6.1 ving meteen af dat ik `get_battery_module_live()`
aanriep terwijl dat een veld is, geen functie.

**Volledige testsuite**: 2444 tests, allemaal groen.

## v3.17.1 — De uitlijning klopte niet

**Gemeld** met een schermafbeelding van de nieuwe plaat: "Dat ziet er al
een stuk beter uit, echter is de uitlijning niet overal goed."

Drie fouten, alle drie zichtbaar in die afbeelding.

### De meters overlapten

Ze stonden 100 pixels uit elkaar met een straal van 46 — dus 92 breed.
Dat paste net niet en de bogen liepen in elkaar. Nu straal 38 op
90/194/298: veertien pixels tussen de bogen en achtentwintig aan de
randen.

### De kolommen liepen niet door

Het schema eronder stond op 84/194/304, de meters op 94/194/294. Nu
allebei op 90/194/298, en de verzamelrail is symmetrisch rond het midden.
Dan oogt de plaat als één geheel in plaats van twee losse helften.

### De staafjes schaalden vanaf de laagste meting

Daardoor werd bij 31/28/27 °C een verschil van vier graden uitvergroot
tot de volle hoogte — dat suggereert een alarm dat er niet is. En bij
drie gelijke waarden (celspreiding allemaal nul) kreeg elk staafje de
minimale hoogte, wat oogt als "bijna niets" terwijl het "allemaal gelijk"
betekent.

Nu vanaf **nul**. Gelijke waarden geven gelijke staafjes, en een
uitschieter blijft zichtbaar doordat hij als enige de accentkleur krijgt.

Vijf tests erbij, waaronder één die controleert dat alles binnen de
viewBox valt — anders wordt de onderbalk afgesneden.

**Volledige testsuite**: 2449 tests, allemaal groen.

## v3.18.0 — Uitlijning, loze ruimte en drie secties

**Gemeld** met drie schermafbeeldingen: *"deze ook nog niet correct
uitgelijnd"*, *"hier bijvoorbeeld veel loze ruimte"*, en *"er mag wat
meer relevante informatie op, misschien 3 secties naast elkaar"*.

### De meters stonden wél gelijk, de bogen niet

De teksten stonden alle drie op dezelfde hoogte. Maar 87% en 81% vullen
bijna de hele halve cirkel, terwijl 36% links blijft hangen — en dan
lijkt de middelste meter lager en kleiner.

De achtergrondboog is nu **zichtbaar**, dus je ziet altijd de volle
cirkel en verschilt alleen de vulling. Dat is wat een meter hoort te
doen. Met de schaalgrenzen erbij: zonder die twee getallen is niet te
zien of 26 °C laag of hoog is.

### De loze ruimte gevuld met wat erbij hoort

Een kader van 128 hoog voor één getal is verspilling. Naast het vermogen
staan nu de **stroomprijs**, wat een **kWh uit de accu kost**, en de
**reden** van de huidige beslissing — precies de afweging waar de
aansturing op draait.

### Drie secties onder de plaat

| | |
|---|---|
| Vandaag | opgewekt tegen voorspeld, verbruik, netafname, netlading, zelfvoorziening, besparing |
| Vooruit | laagste stand, tekortkwartieren, opbrengst, reserve, bandbreedte |
| Kosten en kwaliteit | rendement, slijtage, accu tegen net, ijking, rondeduur |

De plaat toont de **toestand**; deze secties het **verhaal**. Alles komt
uit gegevens die er al waren; er wordt niets extra berekend.

Een ontbrekende waarde toont een streepje. Een nul zou eruitzien als een
meting — dezelfde fout die deze week bij de zelfvoorziening en de
perioden is opgelost.

### Onderweg

De structuurscan ving tweemaal een aanroep van iets dat geen functie is:
`get_battery_module_live` en `get_battery_vs_grid` zijn velden.

**Volledige testsuite**: 2455 tests, allemaal groen.

## v3.19.0 — Status per onderwerp, klikbaar — en de modules eruit

**Gevraagd**: "Deze info toevoegen bijvoorbeeld? En klikbaar maken?" bij
een schermafbeelding van de statustegels. En: "de accumodules gedeelte
mag er wel uit, die info vind ik overbodig op deze pagina."

### Klikbare status per onderwerp

Onder de plaat staat nu dezelfde statuslijst als op de landingspagina —
zelfcontrole, zon, apparaten, financieel, klimaat, water, meetkwaliteit —
met per blok een **link naar de detailpagina**.

Een gekleurd streepje links geeft het betrouwbaarheidsniveau: dezelfde
schaal die de proefstand en de meetkwaliteit al gebruiken, dus geen nieuw
begrip. Onderwerpen zonder detailpagina worden overgeslagen; een blok dat
niet klikt terwijl de andere dat wel doen is verwarrend.

*SVG kent gewoon `<a>`, en Home Assistant laat dat door in een
markdown-kaart. Werkt het onverwacht niet, dan is de plaat nog steeds
leesbaar — de link is een toevoeging, geen voorwaarde.*

### De accumodules eruit

Terecht. De staafjes stonden er om een uitschieter te laten zien, maar de
drie modules liepen gelijk en de celspreiding stond op nul — zes blokjes
die niets zeiden. De accupagina heeft de cijfers met historie, en de
zelfcontrole meldt het zodra er wél iets uit de pas loopt.

Op die plek staan nu de **dagcijfers**: opgewekt tegen voorspeld,
verbruikt, van het net, teruggeleverd. Loze ruimte zou geen verbetering
zijn geweest.

De bouwsteen voor staafjes blijft bestaan, want de accupagina gebruikt
hem.

**Volledige testsuite**: 2459 tests, allemaal groen.

## v3.20.0 — Eén plaat, en nette schaalgrenzen

**Gevraagd**: "Kan status niet bij op het overzicht?" En: "tevens dit nog
niet netjes op het overzicht."

### De status zit nu in dezelfde plaat

Twee losse platen onder elkaar gaven twee achtergronden, twee kaders en
een naad ertussen. Nu één plaat die **meegroeit** met het aantal
onderwerpen — een vaste hoogte zou de onderste blokken afsnijden of loze
ruimte laten, precies de klacht van eerder.

De blokken blijven klikbaar naar hun detailpagina.

### Twee fouten bij de schaalgrenzen

De getallen stonden op `x ± straal` — precies onder de uiteinden van de
boog, waar ze tegen de lijn aan botsten. Ze staan nu ernaast, naar buiten
uitgelijnd.

En **8,6 kWh werd weergegeven als "9"**. Dat is geen afronding maar een
verkeerde grens: de accu levert 8,6 bruikbaar, niet 9. Onder de tien telt
de decimaal nu mee.

Vijf tests erbij, waaronder één die de plaat met verschillende aantallen
onderwerpen rendert en controleert dat alles binnen de viewBox blijft.

**Volledige testsuite**: 2464 tests, allemaal groen.

## v3.21.0 — Drie kolommen

**Gevraagd**: "2 blokken links, 2 blokken midden, status per onderwerp
rechts." Daarvoor liep de plaat rechts buiten het kader.

| Kolom | Inhoud |
|---|---|
| Links | accu (drie meters) en installatie (zon, net, huis, accu) |
| Midden | vermogen met prijzen en reden, en de dagcijfers |
| Rechts | status per onderwerp, klikbaar |

Onderaan een balk over de volle breedte: koeling, tekortkwartieren,
verkoopkwartieren en de grootste verbruiker.

Drie kolommen van 240 breed op 16/260/504 binnen 760 — vier pixels tussen
de kaders, zestien aan de randen. Een test controleert dat geen kader
buiten de plaat valt, want dat was precies wat er misging.

### Compacter geworden

Van **744** naar **464** hoog, terwijl er méér op staat: in het
middenblok is ruimte gekomen voor de **netlading** en de
**zelfvoorziening** — precies de twee cijfers die elkaar verklaren sinds
v3.16.0.

De meters zijn kleiner (straal 30) en de statusregels korter afgekapt op
een woordgrens. De plaat groeit nog wel mee wanneer de statuslijst langer
wordt dan de linkerkolom.

**Volledige testsuite**: 2465 tests, allemaal groen.

## v3.21.1 — Het derde meterlabel viel buiten het kader

**Gemeld** met een schermafbeelding: "dat ziet er al een heel stuk beter
uit, alleen nog steeds die gauges."

Twee fouten. De derde meter stond op y 176, dus zijn label op **202** —
terwijl het accukader op 194 eindigt. En twee meters boven met één
eronder was asymmetrisch.

De drie meters staan nu op **één rij**: straal 22 op 60/136/212 binnen
een kolom van 240. Met de schaalgrenzen erbij beslaat elke meter 68
pixels, dus er blijft acht pixels tussen — nagerekend in plaats van met
het oog beoordeeld, want zo kwam die fout erin.

Twee tests erbij:

- geen meterlabel mag buiten zijn kader vallen;
- alle bogen staan op dezelfde hoogte.

De tweede kostte een poging: het eindpunt van een boog verschuift met de
waarde, dus de test moet naar het **startpunt** kijken.

**Volledige testsuite**: 2467 tests, allemaal groen.

## v3.22.0 — Geen gauges meer

**Gemeld** met een schermafbeelding: "springt er teveel uit, misschien
compacter, en geen gauges?"

Terecht. Drie halve cirkels met een boog, een achtergrondboog en twee
schaalgrenzen zijn **acht lijnen voor drie getallen**. Dat trekt de
aandacht naar de versiering in plaats van naar de waarde.

Nu een groot getal met een balkje van drie pixels eronder. Dat zegt
hetzelfde — waar sta je tussen minimum en maximum — en het getal is weer
wat opvalt.

### En compacter

| | |
|---|---|
| Vorige versie | 464 hoog |
| Nu | **368 hoog** |

Het installatieschema stond als drie blokken op een rij met de accu
eronder; dat gaf veel lucht. Nu twee rijen van twee, met de verzamelrail
ertussen — en de accu erbij, die er eerst alleen als naam stond zonder
vermogen.

De statusregels zijn 34 pixels hoog in plaats van 40, en de kaders in het
midden zijn ingekort tot wat hun inhoud nodig heeft.

Een test rekent na dat niets buiten de plaat valt, in beide richtingen.
Bij elke indelingswijziging tot nu toe liep er iets uit, en dat is met
het oog niet betrouwbaar te beoordelen.

**Volledige testsuite**: 2466 tests, allemaal groen.

## v3.22.1 — De stroompijlen bewogen niet meer

**Gevraagd**: "Bewegen er nu ook richtingspijlen in het installatie
gedeelte?"

Nee. De pijlfunctie bestond al sinds v3.17.0 — met bewegende streepjes en
een dikte die het vermogen volgt — maar na de herindeling werd hij niet
meer aangeroepen. Er stonden alleen dunne verbindingslijnen.

Nu weer aangesloten, met de richting die de werkelijkheid volgt:

| | |
|---|---|
| Zon | altijd naar beneden — die levert |
| Net | omlaag bij afname, **omhoog** bij teruglevering |
| Accu | naar het blok toe bij laden, ervandaan bij ontladen |

De dikte volgt het vermogen en de snelheid ook: bij veel stroom lopen de
streepjes sneller. Onder 25 W wordt er niets getekend — een pijl die
altijd staat zegt niets.

Vijf tests erbij, waaronder twee die controleren dat de pijl **omdraait**
bij teruglevering en bij ontladen. Dat is precies het soort ding dat er
goed uitziet in één toestand en fout in de andere.

**Volledige testsuite**: 2471 tests, allemaal groen.

## v3.23.0 — Klikbaar, maar dan buiten de SVG

**Gemeld** met een schermafbeelding waarop de hele plaat als **platte
tekst** verscheen, met de linkgedeelten blauw onderstreept.

De oorzaak: de opschoner van de markdown-kaart accepteert `<a>` binnen
SVG niet, en zet dan het hele blok om naar tekst. Dat was mijn fout uit
v3.19.0 — ik had geschreven dat Home Assistant het "normaal doorlaat",
maar dat kon ik niet uitproberen en het bleek niet zo.

**Gevraagd**: "niet de links eruit, ik wil hem juist klikbaar hebben."

Terecht, en dat kan — alleen moet het klikken **buiten** de SVG gebeuren.
Onder de plaat staan nu negen **echte tegels** met een navigate-actie,
elk met dezelfde samenvatting en dezelfde kleurcodering als de blokken in
de SVG hadden. Die werken gegarandeerd.

De pagina is daarvoor van paneelweergave naar secties gegaan; beide
vullen de volle breedte.

### De plaat werd breder

Nu de statuskolom eruit is, mogen de twee overgebleven kolommen van 240
naar **352** breed. Meer ruimte voor de balkjes, de blokken in het
installatieschema en de tekstregels.

Twee tests erbij die dit soort fouten voortaan vangen: geen links in de
SVG, en elke tegel moet naar een pagina wijzen die werkelijk bestaat.

**Volledige testsuite**: 2469 tests, allemaal groen.

## v3.23.1 — De regel die pendelen moest voorkomen, veroorzaakte het

Twee fouten uit de diagnostiek van 18 augustus 20:42, beide van mij.

### De ventilator pendelde nog steeds

**Negen schakelingen in zes uur**, ook na de hysterese van v3.14.0:

    15:07 aan  33 °C     15:37 uit  24 °C     (30 min)
    16:40 aan  31 °C     17:10 uit  27 °C     (30 min)
    17:54 aan  32 °C     18:24 uit  26 °C     (30 min)
    19:15 aan  31 °C     19:45 uit  23 °C     (30 min)

De oorzaak: ik gebruikte **dezelfde delta-eis van 12 graden** voor
aanzetten én voor doorgaan. Zodra de ventilator zijn werk doet zakt het
verschil — 33 naar 24 bij 17,7 buiten is nog maar 6,3 graden — en dan
stopte hij, warmde de omvormer weer op, en begon het opnieuw.

Doorgaan vraagt nu **vier graden** in plaats van twaalf. Alle vier de
gemeten uitschakelingen vervallen daarmee; de ventilator draait door tot
de omvormer werkelijk koel is (20 °C bij een drempel van 25).

*Reken op langere maar veel minder frequente cycli.*

### Zelfvoorziening stond weer negatief

**−51,5%**, en de netladingteller stond op **`None`**. Die wordt alleen
gevuld door de kostprijsboekhouding, en die draait niet bij elke
laadroute — dus de reparatie van v3.16.0 leunde op een meting die kan
ontbreken.

Wat wél altijd waar is: **het huis kan nooit meer van het net krijgen dan
het zelf verbruikt heeft.** Alles daarboven is per definitie ergens
anders heen gegaan. Daarmee is de uitkomst gebonden aan 0–100 zonder van
een aparte teller af te hangen.

Met de cijfers van vanavond: **0%** in plaats van −51,5%. Laag, maar
eerlijk — vandaag kwam alles van het net.

**Volledige testsuite**: 2476 tests, allemaal groen.

## v3.24.0 — Ook meten bij een dreigend tekort

**Gevraagd** na een dag met **42,9% minder zon** dan voorspeld: wat heeft
de integratie hiervan geleerd?

Het eerlijke antwoord was gemengd. De reserve leerde direct — tien
procentpunt erbij voor "weinig zon" en "tekortdagen", die morgen
automatisch doorwerken. Maar de **bijkoop-kandidaat stond op nul
metingen**, terwijl het precies zo'n dag was waarop bijkopen relevant kon
zijn.

De reden: hij mat alleen bij een **becijferd** tekort in de planning, en
dat was er niet — de reserve had het opgevangen. Dat is geen fout, maar
het betekent wel dat de kandidaat maandenlang op nul blijft staan tot de
reserve een keer tekortschiet. En dán is er nog niets geleerd.

Een **dreigend** tekort telt nu ook mee: zakt de planning tot binnen tien
procentpunt van de ondergrens, dan had een kWh erbij verschil gemaakt.

De twee soorten worden apart geteld. Een meting bij een krappe marge
weegt lichter dan een bij een echt tekort — daar had de reserve het al
opgevangen, dus het "voordeel" is hypothetischer.

### Wat dit vandaag zou hebben gedaan

**Niets.** De laagste stand was **41%** tegen een ondergrens van 10 — dat
is geen krappe marge maar een comfortabele. De reserve werkte vandaag
gewoon goed, en dat is een uitkomst en geen tekortkoming.

De kandidaat gaat nu tellen op dagen waarop het spannend wordt zonder
mis te gaan. Dat zijn er meer dan dagen waarop het misgaat, maar nog
steeds niet veel.

**Volledige testsuite**: 2480 tests, allemaal groen.

## v3.25.0 — Wat er wérkelijk van het net de accu in ging

**Gevraagd**: "maar er is vandaag toch wel degelijk bijgekocht?" — en dat
klopte. Mijn analyse van daarvoor was fout.

En daarna: "ik denk dat het ook meer was dan 2,02 kWh." Ook dat klopte:

| | |
|---|---|
| In de accu gegaan | **6,90 kWh** |
| Ondergrens netdeel (import − verbruik) | 2,02 kWh |
| Bovengrens netdeel | 5,93 kWh |

Op dagniveau is dat niet scherper te krijgen: welk deel precies van het
net kwam hangt af van wat de zon op **elk moment** leverde.

### De bijkoop-kandidaat mat de verkeerde vraag

Die keek naar het **hypothetische** geval — had ik moeten laden bij een
verwacht tekort? Maar het laden gebeurde al, via de winterguard, en dat
mechanisme meldde zich daar niet. De kandidaat wachtte op een situatie
die nooit ontstond omdat een ander onderdeel hem had weggenomen.

Dat is een ontwerpfout: ik mat de hypothese terwijl de werkelijke
handeling ongemeten bleef.

### Nu per ronde afgerekend

Elke ronde wordt bepaald welk deel van het laadvermogen van het net kwam,
en dat wordt geboekt tegen de prijs van **dat moment**. Vier gevallen
nagerekend:

    laden zonder zon      accu 2000 W, net 2100 W  ->  2000 W van het net
    laden uit de zon      accu 2000 W, net -100 W  ->     0 W
    deels net, deels zon  accu 2000 W, net  800 W  ->   800 W
    ontladen              accu -1600 W             ->     0 W

Daar rolt een kostprijs uit: inkoopprijs gedeeld door het rendement, plus
de slijtage. Naast het duurste resterende kwartier is dat een afrekening
in plaats van een hypothese.

Een gat in de metingen — na een herstart — wordt overgeslagen; anders
boekt één ronde uren aan energie.

**Volledige testsuite**: 2489 tests, allemaal groen.

## v3.25.1 — De zon zat er al in, maar de code suggereerde anders

**Gevraagd**: "ik denk dat je PV bent vergeten?"

Een terechte controle, en het antwoord is nee — maar de code gaf reden
tot twijfel.

**De zon hoeft niet apart in de som**, want hij zit al in de P1-meter.
Die meet wat er overblijft nadat zon, huis en accu met elkaar zijn
verrekend:

    net = huis + accu − zon

Levert de zon meer, dan zakt de netafname vanzelf. Het netdeel van de
lading is dus simpelweg de netafname, begrensd op wat de accu opneemt.

*Voorbeeld: accu laadt 2000 W, zon geeft 1400, huis gebruikt 200. Dan
staat de P1-meter op 800 — en dat is het netdeel.*

### Maar er stond dode code

`zon_naar_accu` werd berekend en **nergens gebruikt** — een restant van
mijn eerste poging. Dat suggereert een som die er niet is, en dat is
erger dan geen code: het maakt de logica onnavolgbaar en roept precies
deze vraag op.

Opgeruimd, met de redenering in het commentaar zodat de volgende lezer
niet hoeft te twijfelen.

Drie tests erbij, waaronder één die **elke** variabele in die functie
nagaat: berekend maar nergens gelezen valt om. Op de proef gesteld door
de dode code terug te zetten.

**Volledige testsuite**: 2492 tests, allemaal groen.

## v3.25.2 — Visueel-pagina teruggezet

**Gemeld**: "de Visueel pagina werkt niet correct, graag terugbrengen
naar de stand van gisteren."

De dashboardcontrole vond niets: **103 verwijzingen nagelopen**, geen
ontbrekende entiteiten, geen ontbrekende attributen. Wat er precies
misging is dus niet vast te stellen — en dan is teruggaan naar een
aantoonbaar werkende stand verstandiger dan blijven sleutelen aan iets
waarvan de fout onbekend is.

De pagina staat weer op **paneelweergave met één markdown-kaart**: de
plaat en de cijfersecties eronder. Dat is de opzet die aantoonbaar
renderde.

### Wat daarmee vervalt

De sectie-indeling met de negen klikbare tegels uit v3.23.0. Die kwamen
er omdat links binnen de SVG niet werken; het klikken is dus voorlopig
weg.

Dat kan terugkomen zodra duidelijk is wat er misging. Om dat te kunnen
vaststellen helpt het te weten **wat** er niet werkte: bleef de pagina
leeg, verscheen er weer platte tekst, of stonden de tegels er wel maar
zonder inhoud? Elk van die drie wijst een andere kant op.

**Volledige testsuite**: 2492 tests, allemaal groen.

## v3.25.3 — Twee SVG's in één markdown-kaart

**Gemeld** met de volledige pagina-inhoud: de plaat verscheen als
**platte tekst**, en er stonden geen links meer in.

Dat sloot de eerdere verklaring uit. De werkelijke oorzaak: **twee
`<svg>`-blokken in dezelfde markdown-kaart.** Het eerste wordt als HTML
herkend, het tweede niet meer — en dan valt alles terug op tekst.

Dat verklaart ook waarom het eerder wél werkte: toen stond er één SVG in
de kaart. De cijfersecties uit v3.18.0 waren de tweede.

Nu **één SVG per kaart**, met een `vertical-stack` eromheen zodat ze
onder elkaar blijven staan.

Een test loopt elke markdown-kaart in het dashboard na en valt om zodra
er meer dan één SVG-bron in staat. Dat is de vorm die dit probleem
veroorzaakte, en die kan bij elke volgende toevoeging terugkomen.

*De klikbare tegels uit v3.23.0 blijven voorlopig weg; die kunnen terug
zodra dit stabiel blijkt.*

**Volledige testsuite**: 2493 tests, allemaal groen.

## v3.25.4 — Het was `<animate>`

**Gemeld**: "Visueel is nog steeds een lap tekst."

Derde poging op dezelfde pagina, en de eerste twee waren gissingen die ik
niet kon toetsen: eerst dacht ik dat de links het deden, toen dat twee
SVG's in één kaart het probleem waren.

De tijdlijn wijst één kant op. De bewegende pijlen kwamen er in
**v3.22.1**, en precies daarna begon dit — daarvoor renderde de plaat.
Home Assistant filtert **SMIL-animatie** uit de markdown-kaart, en wat
overblijft is geen geldige SVG meer.

De richting is net zo goed te zien met een **pijlpunt**, en dat is gewone
SVG. De dikte volgt nog steeds het vermogen; onder 25 W wordt er niets
getekend.

### Een vangnet voor alle platen

Een test rendert nu **elke** plaat die de integratie kan maken — leeg,
ladend, ontladend, met en zonder status — en valt om zodra er een
element in staat dat de opschoner kan weren: `animate`, `set`, `script`,
`foreignObject`, `iframe` of `a`.

Dat is de les van deze drie pogingen: niet raden welk element het
probleem is, maar de hele verzameling afschermen.

**Volledige testsuite**: 2496 tests, allemaal groen.

## v3.26.0 — De plaat gaat als afbeelding de kaart in

**Gemeld**: "Visueel-pagina toont platte tekst" — voor de vierde keer.

Drie eerdere verklaringen waren alle drie fout: de links (v3.23.0), twee
SVG's in één kaart (v3.25.3) en `<animate>` (v3.25.4). Geen ervan hielp,
want geen ervan was de oorzaak.

### Wat het wél is

De oorzaak staat in de bron van de Home Assistant frontend en is gewoon
na te lezen. `hui-markdown-card.ts` rendert:

    <ha-markdown cache breaks .content=${...}></ha-markdown>

**zonder** `allow-svg`. In `ha-markdown.ts` staat die eigenschap
standaard op `false`. Daardoor draait `markdown-worker.ts` met de gewone
witte lijst, en die kent **geen enkel SVG-element** — `<svg>` zelf ook
niet. De xss-opschoner ontsnapt alles wat er niet op staat naar tekst.
Dat is letterlijk de klacht.

Zelfs mét `allow-svg` zou het niet gaan. Die lijst is:

    svg:  xmlns, height, width
    path: transform, stroke, d
    img:  src

Geen `viewBox`, geen `rect`, `text`, `circle`, `line`, `g`, `tspan`,
`polygon` — en de plaat bestaat vrijwel volledig uit die elementen. Ruwe
SVG in een markdown-kaart kan dus nóóit werken, in geen enkele vorm.

### De reparatie

`<img>` staat wél op de gewone witte lijst, en `safeAttrValue` van de
xss-bibliotheek laat `data:image/` uitdrukkelijk toe. De plaat gaat nu
als data-URI door een `<img>` heen. Base64, want de plaat staat vol
`#`-kleurcodes en die breken een niet-gecodeerde data-URI.

De wortel van de SVG krijgt daarbij een echte maat uit de `viewBox` in
plaats van `width="100%"`: binnen een `<img>` is een percentage
betekenisloos en valt de browser terug op 300 bij 150 pixels. Met een
echte maat klopt de verhouding, en `img { max-width: 100% }` uit
`ha-markdown` laat hem alsnog meeschalen op een telefoon.

**Het dashboard verandert niet.** De kaart leest dezelfde
sensorattributen als eerst; alleen de inhoud van die attributen is
veranderd. Opnieuw importeren is niet nodig.

Wat de plaat niet terugkrijgt zijn klikbare gebieden — dat kan een
afbeelding niet. De tegels onder de plaat blijven de weg naar de
detailpagina's, net als sinds v3.23.0.

**Volledige testsuite**: 2506 tests, allemaal groen.

## v3.26.1 — De ventilator gaat ook weer uit

**Gemeld**: "Accukoeling pendelt nog steeds — negen schakelingen in zes
uur." Nagerekend aan de export van 19 augustus 08:09, en het lag anders.

### Het pendelen was al voorbij

De twintig regels in de schakelgeschiedenis zijn van een **oudere
versie**. Élke "uit" gebeurde onder de 32 graden zonder dat de goedkope
koeling werd ontzien — het gedrag van vóór v3.14.0. Twee regels sluiten
v3.14.0 ook uit: 11:49 bij 30,0 graden met 14,7 verschil, en 14:37 bij
31,0 met 13,4. Die hadden toen moeten doordraaien.

De laatste schakeling is 18 augustus 21:15. De export is elf uur later.
Daartussen staat niets. De reparatie van v3.23.1 werkt.

### Maar hij ging ook nooit meer uit

Bij een drempel van 25 ligt de ondergrens op 20 graden. De accu stond
die nacht op 23,0 met 16,5 buiten en 114 W. Die 20 graden komt nooit —
de ventilator draaide van de avond tot de ochtend door terwijl er onder
de eigen aanzetdrempel niets te halen viel.

### De reparatie kijkt naar de warmtebron

De omvormer wordt warm van **werk**. Staat de accu onder de
aanzetdrempel én gaat er minder dan 300 W doorheen, dan is er geen
warmtebron en stopt de ventilator.

Gaat er wél vermogen doorheen, dan draait hij door, ook onder de
drempel: op 18 augustus 19:45 stond de accu op 23 graden met 1623 W, en
een half uur later op 31. Dáár uitzetten is precies het verkeerde
moment.

Uitzetten mag alleen met een rem op het opnieuw aanzetten, anders is het
pendelen meteen terug — een half uur na uitschakelen stond de omvormer
weer op 27 graden bij nul watt. De goedkope koeling wacht daarom twee
uur voor hij opnieuw begint, zolang de accu stil staat. Komt er
belasting, dan geldt de gewone rusttijd van een half uur.

Van de tien gemeten uitschakelingen blijven er vier over. De
bescherming boven 32 graden is niet aangeraakt.

### Netlading: vals alarm

Gemeld als "netlading_vandaag_kwh staat op None in de export". Het veld
stond er **helemaal niet in** — `diagnostics.py` schreef alleen de
samenvatting weg. Wie de teller opvroeg kreeg `None` omdat de sleutel
ontbrak, en dat zette een halve sessie op een vals spoor.

De rauwe tellers staan er nu bij: `netlading_vandaag_kwh`,
`netlading_kosten_eur` en het moment van de laatste meting. Bij een
rustige dag is een lege samenvatting nu te onderscheiden van een meting
die niet draait.

**Volledige testsuite**: 2515 tests, allemaal groen.

## v3.27.0 — Kalibratiestand

**Gevraagd**: "Af en toe moet een kalibratie worden gedaan voor de accu.
Dit houdt in ontladen tot 5% en dan in 1 keer zonder ontladen naar 100%
laden. Dit doe ik nu manual (...) Ja lijkt me handig, stoort dit de rest
van de integratie niet?"

Die laatste vraag is de kern. Een kalibratie is geen gewone dag, en vijf
lerende onderdelen zouden hem als één opvatten.

### Nieuwe schakelaar: Kalibratie

De sturing gaat eruit, net als bij `Force manual`. Maar met één
belangrijk verschil: **de koeling blijft schakelen**. Bij handmatige
overname komt de ventilator pas boven de 35 graden, en dat is te laat
bij 2000 W — op 18 augustus stond de omvormer bij 2038 W op 42 graden.
Tijdens een kalibratie is koelen bescherming, geen optimalisatie.

### Wat er stilvalt

| Onderdeel | Waarom |
|---|---|
| netladingafrekening | zeven kWh bij 30 ct is geen bijkoopbesluit |
| piekmeting | 2000 W laden is geen huispiek; de maandpiek staat op 2294 W |
| tekortdetectie | netstroom tijdens een kalibratie is niet onverwacht — anders telt de dag als tekortdag en gaat de veiligheidsmarge omhoog, en die staat na één zo'n dag al op 40% |
| verbruiksleer | 2000 W is geen huisverbruik |
| apparaatherkenning | een blok van 2000 W dat uren aanstaat is precies het patroon waar die op zoekt |

De vakantiestand doet dit al langer met de verbruiksleer, om dezelfde
reden. Deze stand volgt dat voorbeeld.

### Momentopname bovenin

Zodra de accu boven de 99% komt wordt de celspreiding per module
vastgelegd — één keer per kalibratie, want daarna zakt de spanning weer
zodra er ontladen wordt.

Dat is waar het nu om draait: module 1 stond op 19 augustus op 2,72
tegen 3,18 V, een verschil van 0,46 bij 12% laadstand, terwijl module 2
en 3 vlak stonden. Bovenin balanceert de BMS. Zakt dat verschil mee naar
nul, dan was het een balanceerachterstand. Blijft het staan, dan is het
een zwakke cel — en dan is dit de meting om aan Zendure voor te leggen.

De opname staat als attribuut op de schakelaar en in de
diagnostiek-export. De schakelaar zelf staat op het dashboard onder
**Besturing**, naast `Force manual` — dat is een wijziging in de
dashboard-YAML, dus die pagina moet één keer opnieuw geïmporteerd
worden. De stand zelf overleeft een herstart: een kalibratie
duurt uren.

**Volledige testsuite**: 2528 tests, allemaal groen.

## v3.27.1 — Kritieke melding als de kalibratie klaar is

**Gevraagd**: "Graag melding wanneer accu in kalibratie modus 100%
bereikt, indien mogelijk kritisch."

Nieuwe meldingssoort `kalibratie_vol`, met prioriteit **kritiek**. Die
prioriteit doorbreekt de stille stand van de telefoon —
`interruption-level: time-sensitive` op iOS, hoge prioriteit op Android.

Kritiek niet omdat er iets mis is, maar omdat er iets moet gebeuren: de
kalibratiestand uit en de ondergrens in de Zendure-app terug. Blijft die
melding tot de volgende ochtend in de wachtrij, dan staat de sturing
uren onnodig stil.

De celspreiding per module gaat mee in het bericht. Dat is de reden dat
deze kalibratie gedraaid wordt, en zo is het op de telefoon meteen af te
lezen zonder de diagnostiek-export erbij te halen.

Staat standaard aan, net als `vakantie_beweging` en om dezelfde reden:
hij vuurt alleen als de kalibratiestand aan staat — een bewuste
handeling. De momentopname is meteen de rem: één melding per kalibratie.

Uit te zetten op het meldingen-tabblad.

**Volledige testsuite**: 2531 tests, allemaal groen.

## v3.27.2 — De kalibratiekaart wees naar niets

**Gemeld** met een schermafdruk: "Entiteit niet gevonden" op de
kalibratiekaart.

De kaart wees naar `switch.energy_management_system_kalibratie`, terwijl
de entiteit `switch.woonkamer_energy_management_system_kalibratie` heet.

Dat komt door een gewoonte van Home Assistant, niet van deze
integratie: entiteiten met `_attr_has_entity_name` krijgen hun id uit de
apparaatnaam. `force_manual` en `learning_only` zijn aangemaakt vóórdat
het apparaat in een gebied stond en hebben daarom geen voorvoegsel; al
het latere werk — vakantiemodus, alle meldingsschakelaars — heeft
`woonkamer_` ervoor.

Ik heb de nieuwe kaart naar het patroon van `force_manual` gebouwd, en
dat is precies de verkeerde van de twee om te kopiëren.

Nieuwe structuurscan, uit deze fout voortgekomen: elke schakelaarkaart
op het dashboard moet het voorvoegsel gebruiken dat de rest ook
gebruikt. De twee entiteiten van vóór het gebied staan als bekende
uitzondering vastgelegd. Slaat de installatie ooit om naar een ander
voorvoegsel, dan valt die scan om in plaats van dat kaarten stilletjes
leeg blijven.

**Volledige testsuite**: 2535 tests, allemaal groen.

## v3.27.3 — De uitleg wist niets van de kalibratie

**Gemeld** met een schermafdruk: "Tekst is in kalibratie mode niet
geheel correct."

De kop klopte — "Waarom doet de aansturing niets?" — maar eronder stond
het gewone verhaal: de prijs is nu 30,8 ct, de drempel voor 'duur' ligt
op 37,6 ct, geen bijzondere reden om iets anders te doen. Terwijl de
aansturing juist stilstaat omdat er een kalibratie loopt.

Twee plekken bouwen een uitleg. `_build_explanation` had zijn tak al,
`_waarom_regels` niet, en die viel door naar de terugval van
`default_smart`. Nu vertelt hij wat er stilligt en bij welke stand de
melding komt.

### En iets belangrijkers op diezelfde schermafdruk

`Learning only` stond aan. Dat betekende tot nu toe dat de ventilator
pas boven de 35 graden schakelt — precies de rem die de kalibratiestand
voor `Force manual` al ophief, maar voor de leermodus nog niet.

Bij 2000 W is dat te laat: op 18 augustus stond de omvormer bij 2038 W
op 42 graden. Wie zelf een kalibratie start wil niet dat zijn omvormer
ondertussen oploopt. De koeling schakelt nu tijdens een kalibratie,
ongeacht welke van de twee schakelaars aan staat.

**Volledige testsuite**: 2537 tests, allemaal groen.

## v3.28.0 — Twee soorten dagen, geen verschuiving

**Gemeld** met een schermafdruk van de meetkwaliteitskaart: "1 van de 26
gemeten grootheden is onbetrouwbaar: Zonvoorspelling (klopt de correctie
nog?)". De kaart wees vervuiling, een uitgevallen streng of toegenomen
beschaduwing aan.

De zes dagen eronder zeggen iets anders:

| datum | voorspeld | werkelijk | afwijking |
|---|---|---|---|
| 13 aug | 21,62 | 21,48 | −0,7% |
| 14 aug | 21,36 | 20,90 | −2,2% |
| 15 aug | 15,39 | 9,13 | −40,7% |
| 16 aug | 16,17 | 16,38 | **+1,3%** |
| 17 aug | 18,49 | 9,44 | −48,9% |
| 18 aug | 9,14 | 5,20 | −43,2% |

Een uitgevallen streng haalt élke dag met ongeveer hetzelfde percentage
omlaag. Drie van de zes dagen zitten binnen 2,2%. Een array die 21,48
kWh levert op 21,62 voorspeld mist geen streng en is niet vervuild.

### 1. De duiding onderscheidt nu twee gevallen

**Spreiding**: goede dagen én dagen die er ver naast zitten in hetzelfde
venster. Dan klopt de voorspelling op heldere dagen en niet op
wisselvallige — een bewolkingsprobleem in de voorspelling, niet in de
installatie. De kaart zegt dat nu ook.

**Verschuiving**: élke dag ongeveer even ver omlaag, geen goede dag
ertussen. Dán staat de tekst over vervuiling en strengen er nog steeds,
en dan hoort hij er ook.

### 2. De bias is de mediaan geworden, niet het gemiddelde

De geleerde bias was het gemiddelde van de afwijkingen, en dat werd
volledig door de uitschieters bepaald: −22,6% over zeven dagen waarvan
er vier binnen 4,7% lagen. Als vlakke correctie op alles maakte dat een
heldere dag die klopte 22% te laag, zonder de bewolkte dagen te dekken.

Nagerekend over dezelfde zeven dagen — de fout die na correctie
overblijft:

| correctie | gemiddelde fout | mediane fout |
|---|---|---|
| geen | 22,6% | 4,7% |
| gemiddelde-bias −22,6% | **29,6%** | 27,3% |
| mediaan-bias −4,7% | 21,9% | 4,0% |

De correctie die erin zat maakte het slechter dan helemaal niet
corrigeren. Dat is geen afweging meer maar een reparatie.

Bij een echte verschuiving — élke dag ongeveer even ver omlaag — lopen
mediaan en gemiddelde vanzelf samen, dus die wordt gewoon geleerd. Het
oude gemiddelde staat als `mean_bias_percent` in de export, om de keuze
naast elkaar te kunnen leggen.

**Let op**: zeven dagen is dun, en de mediaan is wiebelig bij een
half-om-half verdeling. Dit is de eerste stap; de correctie koppelen aan
de verwachte bewolking is de structurele oplossing.

**Volledige testsuite**: 2548 tests, allemaal groen.

## v3.29.0 — Wat de volledige doorlichting opleverde

**Gevraagd**: "controleer de volledige integratie op zaken welke niet
kloppen, beter kunnen, etc etc", en daarna "alle zaken welke je kunt
oplossen, graag nu oplossen ook al duurt dat lang".

### De slijtage was ruim twee keer te laag

De 4,22 ct/kWh rustte alleen op de 6000 cycli van de fabrikant. Gemeten:
86,3 kWh in 18 dagen, ruwweg 1.750 kWh per jaar. Dan duurt die 51.840
kWh **dertig jaar**, en zo lang gaat geen accu mee.

De berekening neemt nu de kleinste van beide doorzetten — cycli of
kalender — en dus de hoogste prijs per kWh. Bij twaalf jaar komt dat op
ongeveer 10,4 ct/kWh. Beide getallen blijven zichtbaar met
`bindende_grens` erbij, want de cycli zijn een belofte en de jaren een
aanname; geen van beide is een meting. Onder de 14 dagen meting telt de
kalendergrens niet mee.

Dit werkt door in elke afweging: de drempel van "ruwweg 11 ct" in de
proefstand wordt daarmee ruwweg 19 ct.

### De jaarkolom van € 241,60 was geen bedrag

Het afsluiten van een dag schreef het SALDO onder `kosten_eur`, terwijl
ingelezen dagen daar de meterstand dragen. Twee grootheden onder één
naam, bij elkaar opgeteld. Erger nog: dezelfde dag veranderde bij
middernacht van betekenis — overdag de meter, na afsluiten het saldo.

Het saldo staat nu apart onder `netto_eur`, en er is een migratie die
bestaande dagregels omzet. De kostenkolom van die dagen blijft leeg: de
meterstand van toen is niet meer te achterhalen, en leeg is dan het
eerlijke antwoord.

### 16 augustus was niet zoekgeraakt

De dag ontbrak tussen 15 en 17 in. Niet door een storing maar door de
opruiming van fysiek onmogelijke dagregels — alleen stond dat nergens,
en een reeks met een onzichtbaar gat maakt elke weekvergelijking stiekem
scheef. De opruiming legt nu vast wélke dag eruit ging en waarom, en er
is een toets op gaten waar géén opruiming bij hoort.

### Verder

- **`dagen_met_waarde` per grootheid.** CO2 en besparing stonden voor
  week, maand, jaar én contractjaar op hetzelfde bedrag, omdat maar twee
  dagen die kolom hadden. Nu is dat af te lezen.
- **De gelijke-waarden-toets loopt ook over de besparing.** Die viel er
  buiten omdat hij een verschil is en geen optelling — precies de kolom
  die het probleem had.
- **De reservemarge telt op.** `pv_onzekerheid_percent` ontbrak in de
  opsomming: de kaart toonde 40% totaal met onderdelen die op 30
  uitkwamen. Er staat nu ook een `sluit_aan` bij.
- **De zelfcontrole kapt af op nul.** "Sensor 0,00 kWh, uit de accustand
  van 6% volgt −0,35 kWh" — een negatieve beschikbare energie bestaat
  niet. Twee van de drie alarmen kwamen hiervandaan.
- **De slijtagetekst klopt rekenkundig.** Er stond "6000 cycli x 7,78
  kWh" bij een doorzet van 51.840, en 6000 × 7,78 is 46.680.
- **Tijdens een kalibratie ligt ook de kostentelling stil**, en blijven
  de kijkvelden wél bijwerken. Ze bevroren omdat die tak eerder
  terugkeert, en dan staat het halve dashboard stil zonder dat er iets
  mis is.
- **De kalibratie meet nu de werkelijke capaciteit.** De kandidaat
  "Accugezondheid over de tijd" las een typeplaatje dat nooit verandert
  en kon dus per definitie niets vinden. Wat er tijdens een kalibratie
  ingaat, gedeeld door het doorlopen deel van de schaal, is wél een
  meting.
- **Water telt mee voor aanwezigheid.** De toelichting bij
  `PRESENCE_WATER_MIN_LITERS_PER_MINUTE` beschreef dat gedrag al, maar de
  constante werd nergens gelezen. Een lopende kraan is het enige signaal
  dat een simulatie-automatisering niet kan nabootsen.
- **De meetfrequentie-teller overleeft een herstart.** Vier sensoren
  stonden na zes herstarts nog op 23/30, omdat hij elke keer opnieuw
  begon.
- **De terugregeltaak van de panelen wordt opgezegd** bij het ontladen
  van de integratie. Hij liep door bij een herlaad.
- **Opgeruimd**: `_oude_overzichtsplaat`, twee dode attributen,
  `HEALTH_MIN_CADENCE_PERCENT`. Er zijn nu nul ongebruikte constanten.
- **`BATTERY_MODULE_CAPACITY_KWH`** is de terugval als er geen
  capaciteitssensor is ingesteld; daarvoor gaf de berekening dan niets.

### Structuurscan 8: elke beslisreden heeft een onderbouwing

`WHY_QUESTIONS` en `_waarom_regels` moeten naast elkaar lopen. Doen ze
dat niet, dan krijgt de gebruiker het verhaal van een andere beslissing
te lezen — zoals bij de kalibratie gebeurde. Alle zestien redenen hebben
op dit moment een eigen tak; de scan houdt dat zo.

**Volledige testsuite**: 2564 tests, allemaal groen.

## v3.30.0 — Verbruiksleer opnieuw beginnen

**Gevraagd**: "Graag een reset knop aanbrengen, voor direct na de
vakantie. Vanaf dat moment dient er opnieuw geleerd te worden." En
daarna: "De reset button moet na een druk op de knop nog een keer
bevestigd worden dat een reset zeker gewenst is."

### Waarom

Sinds 14 augustus 11:00 stond het huis leeg zonder dat de vakantiestand
aan was. Vijf dagen leeg huis zijn de leerbestanden in gelopen. Het
uurprofiel staat kaarsvlak op 0,18 tot 0,29 kW — samen 5,5 kWh per dag,
terwijl het huis er op 12 en 13 augustus 12,3 en 12,6 doorjoeg. Geen
ochtendpiek, geen avondpiek: dat is een basislast, geen huishouden.

Zonder ingrijpen reserveert de integratie bij thuiskomst voor een huis
van 5,5 kWh en loopt de accu 's avonds leeg. De tekortdetectie corrigeert
dat met 5 procentpunt per dag — een week lang, met dure avonden.

### Wat de knop wist

| | |
|---|---|
| uurprofiel | het verbruik per uur van de dag |
| nachtverbruik | de reeks nachten en de geleerde mediaan |
| temperatuurrelatie | verbruik tegen buitentemperatuur |
| basislast | inclusief de sluipverbruik-referentie en de cusum-teller |
| tekortdagen | de zelfcorrectie van de ontlaadreserve |
| bedtijden | en het aanwezigheidsritme per halfuur |

De sluipverbruik-referentie moet mee: die staat nu op een leeg huis, en
normaal gebruik ziet er dan uit als een sprong. Zonder wissen krijg je
bij thuiskomst een valse melding.

### Wat blijft staan

Metingen worden niet aangeraakt: de dagreeks, de cyclustelling, de
kosten. En alles wat losstaat van bewoning blijft geleerd: de
zonvoorspelling, het accurendement, en de 25 bevestigde apparaten. Die
opnieuw laten ontdekken zou weken kosten, en er is niets mis mee.

### Twee drukken

Een knop in Home Assistant kent geen bevestigingsvenster, dus doet de
knop het zelf: de eerste druk wapent, de tweede voert uit. De aanvraag
vervalt na zestig seconden vanzelf — een knop die na een uur nog scherp
staat is gevaarlijker dan een knop zonder bevestiging, want dan drukt
iemand er een keer op zonder te weten dat de vorige druk er nog stond.

De kaart telt af zolang de knop scherp staat, en toont anders wanneer de
laatste reset was.

### En een spoor

Wat er weggegooid wordt, wordt eerst samengevat en bewaard in
`verbruiksleer_reset_historie`: hoeveel uren profiel, hoeveel nachten,
hoeveel tekortdagen. Een onomkeerbare knop zonder spoor is een knop die
je niet durft te gebruiken.

Er gaat een melding uit, standaard aan — een stille reset is niet van
een storing te onderscheiden.

**Volledige testsuite**: 2584 tests, allemaal groen.

## v3.30.1 — De reset geldt ook voor de dag die loopt

**Gevraagd**: "Moet dit dan precies om 12 uur snachts of zo? Dat is niet
handig toch dan slaap ik."

Nee — en die vraag legde bloot dat het wél uitmaakte, wat niet de
bedoeling was.

De knop wiste de reeksen maar niet de tellers van de lopende dag. Wie 's
middags drukte, kreeg het uur dat op dat moment bezig was na afloop
alsnog aan het verse profiel geplakt, met het verbruik van een leeg huis
erin. En stond de tekortvlag van vandaag aan, dan schoof die om
middernacht alsnog als tekortdag de reeks in — waarmee de eerste dag na
de reset meteen 5 procentpunt marge zou opleveren.

Nu gaan het lopende uur, de dagminimum-basislast en de tekort- en
overschotvlag van vandaag er ook uit. "Vanaf dat moment opnieuw leren"
geldt daarmee echt vanaf dát moment, en het tijdstip doet er niet meer
toe.

De samenvatting vermeldt of er een tekortvlag stond, zodat achteraf te
zien is dat die is weggevallen.

**Volledige testsuite**: 2587 tests, allemaal groen.

## v3.31.0 — De diagnostiek-export is meer dan gehalveerd

**Gevraagd**: "Is de generatie van de diagnostiek nu ook helemaal
geoptimaliseerd?"

Nee. Gemeten aan de export van 19 augustus 11:22:

| | |
|---|---|
| totaal | 1.243 KB |
| waarvan `persisted_state_snapshot` | 604 KB |
| waarvan `battery_module_health` | 109 KB |

### De momentopname droeg alles dubbel

Van die 604 KB was 496 KB een tweede afdruk van reeksen die er los al in
staan — maar dan **ongekort**. De export knipt `energy_daily_history`
netjes af op 30 regels; de momentopname ernaast droeg alle 400.
Hetzelfde bij `bijkoop_history` (30 tegen 300) en
`lange_reserve_history`. De zorgvuldige afkapping werd teniet gedaan
door het veld dat ernaast stond.

Die momentopname is er om te zien wát een herstart overleeft. Daarvoor
is de vorm genoeg: welke velden, hoeveel regels, hoe groot, en een
voorbeeldregel. De inhoud staat verderop al.

### De ruwe modulemetingen zijn een bereik geworden

Vijf reeksen van 740 monsters per module, maal drie modules: elfduizend
getallen. Wat er bij de diagnose van 19 augustus werkelijk uit gelezen
werd, was het bereik — "celspreiding liep deze week op van 0,190 naar
0,460 V" — en de laatste waarde. Die staan er nu, met het aantal
metingen en de mediaan erbij.

Het dagoverzicht en de waarschuwingen blijven heel: die dragen de trend
over dagen, en die is klein.

### En de drijvendekomma-ruis

1.298 getallen met tien of meer decimalen, zoals `0.024999999999999998`
waar 0,025 bedoeld is. Een artefact van het rekenwerk, vijftien tekens
per stuk. De laatste stap voor het wegschrijven rondt nu af op zes
decimalen — ruim voor watt, kWh, euro's en graden.

### Nagerekend op de echte export

```
voor : 1.243 KB
na   :   573 KB   (54% kleiner)
```

Zonder dat er één diagnostisch gegeven verdwijnt dat vandaag gebruikt is.

**Volledige testsuite**: 2601 tests, allemaal groen.

## v3.32.0 — Wat het gebeurtenislogboek verraadde

**Gevraagd**: "Dus geen zaken gevonden uit de diagnostiek?" — terecht,
want ik zat vooral mijn eigen reparaties af te tikken. Bij echt zoeken
kwamen er twee dingen uit.

### 16 augustus is nooit afgesloten, en werd nooit bijgehaald

De nieuwe gatentoets meldde hem meteen:

> Dagreeks — Ontbrekende dag(en): 2026-08-16. Geen opruiming
> vastgelegd, dus die dag is nooit afgesloten.

Het Home Assistant-logboek van die nacht was leeg — dat bewaart alleen
de huidige draai. Maar het antwoord stond al in deze codebase, in de
toelichting bij `_energiedag_is_onzin` (v2.2.2):

> Dit vangt het geval dat een dag met al gewiste tellers is afgesloten -
> de vorm waarin 15 en 16 augustus op 0,0 kWh opwek stonden bij 11,8 kWh
> teruglevering.

Beide dagen zijn afgesloten met tellers die al op nul stonden, en de
opruimtoets heeft ze er terecht uitgegooid. 15 augustus kwam terug via
de statistieken; 16 augustus viel buiten het inleesvenster.

`dagreeks_verwijderd` staat leeg omdat die lijst pas sinds v3.29.0
bestaat — de opruiming gebeurde onder een oudere versie, en toen nog
stil. De melding van de gatentoets is daarop aangepast: "nooit
afgesloten, of vóór v3.29.0 stil opgeruimd" in plaats van een
conclusie die de gegevens niet dragen.

Erger: hij zou ook nooit meer terugkomen. De inleesroutine vult
uitsluitend dagen aan **vóór** de oudste bekende dag, en een gat in het
midden valt daar per definitie buiten. De statistieken van 16 augustus
staan gewoon in de recorder.

Die routine kijkt nu eerst welke dagen er midden in de reeks ontbreken
en haalt het venster ver genoeg terug om ze mee te nemen. Dagen die als
onmogelijk zijn opgeruimd blijven weg — opnieuw inlezen zou ze meteen
weer weggooien — en de dag van vandaag telt niet, die is nog niet
afgesloten.

### Structuurscan 9: aanroepen met het juiste aantal argumenten

In het logboek staan twee kritieke regels van 18 augustus:

```
08:36  't Systeem löp vast
08:58  't Systeem löp vast
detail: _koelen_is_goedkoop() missing 1 required positional
        argument: 'buiten_c'
```

Twee vastgelopen rondes, en de watchdog die ze weer aan de gang trok. De
methode bestond, de variabelen bestonden — alleen werd hij met één
argument te weinig aangeroepen.

De acht bestaande structuurscans kijken allemaal naar **namen**. Deze
negende kijkt naar de vorm van de aanroep, en dat is precies het gat
waar die storing doorheen viel. De scan houdt rekening met decorators:
zonder dat onderscheid meldt hij tweeënzestig aanroepen die allemaal in
orde zijn.

Getoetst dat de scan de storing van 18 augustus werkelijk zou hebben
gevangen — een scan die niets vindt in code die klopt, bewijst niets.

### Twee kleinere

- **De reservemarge zei "nog geen reserveberekening gemaakt"** terwijl
  de integratie al uren draaide. De oorzaak was de kalibratiestand: die
  tak keert terug vóór de reserve wordt berekend. Geen storing, maar de
  kaart suggereerde van wel. Hij zegt nu waarom.
- **De rij "vandaag" miste `dagen_met_waarde`**, omdat hij uit de
  lopende tellers komt en apart wordt gebouwd. De tabel is nu van links
  naar rechts gelijk te lezen.

**Volledige testsuite**: 2622 tests, allemaal groen.

## v3.32.1 — De gatenreparatie was half

**Gemeld** door de export van 20 augustus 09:11: 16 augustus stond er
nog steeds niet in, terwijl v3.32.0 dat had moeten oplossen. De
inleesronde had wél gedraaid — 404 meetpunten per bron.

v3.32.0 verbreedde het ophaalvenster, maar de regel die daarna bepaalt
wélke opgehaalde dagen de reeks in gaan bleef staan op `dag < oudste`.
En 16 augustus ligt ver ná de oudste bekende dag. De dag werd dus keurig
opgehaald en één regel later weer weggegooid.

Die regel laat nu ook de gaten door. En de samenvoeging gaat op datum in
plaats van vooraan plakken: een bijgehaald gat hoort op zijn eigen plek,
niet tussen de dagen van juli.

**Volledige testsuite**: 2624 tests, allemaal groen.

## v3.33.0 — De zonbias houdt zich in, en de koeling krijgt een dagportie

**Gevraagd**: "Alles zo goed mogelijk maken, het moet een TOP integratie
worden."

### De zonbias sprong van -4,7 naar -36,8 in één dag

Precies de zwakte waar v3.28.0 voor waarschuwde. De verdeling is drie
goede dagen en vier slechte; daar kan een mediaan niet tussen kiezen, en
één nieuwe dag laat hem overslaan.

Nagerekend over die zeven dagen — de fout die na correctie overblijft:

| correctie | gemiddelde fout | mediane fout |
|---|---|---|
| geen | **27,6%** | 36,8% |
| mediaan −36,8% | 31,4% | **28,5%** |
| gemiddelde −27,6% | 29,2% | 32,8% |

Geen van de drie wint overtuigend, en dat is het antwoord: **een vlakke
correctie kan twee soorten dagen niet tegelijk bedienen.** Op een
heldere dag die binnen 2% klopte, maakt −36,8% de voorspelling een derde
te laag. Dat is erger dan niets doen, want het is stelselmatig fout in
plaats van soms.

Vanaf nu wordt er alleen gecorrigeerd als de dagen op één hoop liggen.
Liggen ze dat niet — en dat wordt met dezelfde grenzen bepaald als de
meetkwaliteitskaart gebruikt — dan is nul de eerlijkste correctie, en
net zo belangrijk: een stabiele. De reden staat erbij in
`bias_ingehouden_reden`.

Een reeks die wél op één hoop ligt wordt gewoon geleerd, en onder de
vijf dagen wordt er niet ingehouden — anders is één uitschieter genoeg
om nooit meer te leren.

### De koeling: derde poging, nu met een vangrail

Drie keer aan drempels gedraaid, drie keer kwam het pendelen in een
andere vorm terug. De nacht van 19 op 20 augustus, zeven schakelingen:

```
00:03 uit 24,0°C 283W    00:47 aan 28,0°C
01:18 uit 23,0°C 272W    01:57 aan 27,0°C
02:28 uit 23,0°C 231W    03:04 aan 27,0°C
...
08:57 uit 20,0°C   0W    → bleef uit
```

De stilstandgrens van 300 W uit v3.26.1 was te hoog: bij 194 tot 290 W
staat de omvormer binnen een half uur weer op 27 graden, dus daar is wel
degelijk een warmtebron. **Naar 100 W** — bij écht nul watt bleef hij
netjes uit, en dat geval blijft staan.

De lange rusttijd gold alleen bij een stille accu, en die vlag stond
door dezelfde 300 W-toets nooit aan. **Nu geldt hij voor de hele
goedkope tak.**

En dan het punt: **de oorzaak zit niet in de drempel maar in de
installatie.** Bij 200 tot 430 W klimt de omvormer binnen een half uur
van 23 naar 27 graden — daar is geen hysterese tegen bestand. Daarom
een harde bovengrens van vier keer aanslaan per etmaal. Daarboven gaat
de goedkope tak op slot tot middernacht, met één melding en het advies
om de aanzetdrempel een paar graden hoger te zetten. Bij 23 tegenover 27
graden valt er voor de cellen vrijwel niets te winnen.

De teller overleeft een herstart — anders is de bovengrens te omzeilen
door de integratie te herladen. En de **bescherming boven 35 graden valt
er buiten**: die gaat over de omvormer, niet over centen.

**Volledige testsuite**: 2634 tests, allemaal groen.

## v3.33.1 — De capaciteitsmeting overleeft een herstart

**Gevraagd**: "Is nu alles verwerkt in 3.33.0? Geen open eindjes meer?"

Eén wel, en die had ik zelf beloofd. Bij de kalibratie van 19 augustus
kwam er geen gemeten capaciteit uit: de herstart voor v3.31.0 zette de
lopende meting op nul. Hij begon opnieuw bij 71% laadstand en had 70%
van de schaal nodig — die drempel haalde hij niet meer.

Een kalibratie duurt uren en wordt zelden gedaan. Dan mag één herstart
hem niet kosten. De meting wordt nu bewaard, met het tijdstempel als
tekst zodat het de opslag overleeft.

**Volledige testsuite**: 2637 tests, allemaal groen.

## v3.34.0 — Grof afronden is geen achterstand

**Gemeld**: "Dit is toch logisch? Als de accu niets doet staat de waarde
stil."

Terecht, en het lag nog specifieker. De beschikbare-energiesensor bewoog
bij 4,9% van de ticks en heette daarom "traag", met het advies om
afgeleide tempo's over de werkelijke beweging te berekenen.

Maar de stappen in de eigen loggegevens zijn allemaal veelvouden van
**0,0864 kWh** — exact één procent van 8,64 kWh. Die sensor rapporteert
de laadstand in hele procenten en rekent dat om. Bij 300 W valt de
volgende stap pas na een kwartier, en dat komt uit op ongeveer 1 op de
17 ticks. Gemeten: 4,9%. Het klopt tot op de decimaal.

De waarde is dus niet fout en niet oud; hij komt alleen in brokken. Dat
vraagt niets, en de kaart wekte ten onrechte de indruk van wel.

De meting houdt nu ook de **kleinste stap** bij die een sensor zet.
Beweegt een sensor zelden maar dan altijd met een forse stap, dan heet
dat `grof_afgerond` en zegt de kaart dat het de resolutie is en geen
achterstand. Beweegt hij zelden met kleine stapjes, dan loopt hij
werkelijk achter en blijft het oordeel `traag` staan — daar zijn
afgeleide tempo's wél onbetrouwbaar.

De vermogenssensoren waarmee hij vergeleken wordt bewegen in stappen van
één watt; de grens ligt op een honderdste, ruim genoeg om die twee
werelden te scheiden.

### Volledige controle voor deze oplevering

| | |
|---|---|
| ongebruikte constanten | 0 van 541 |
| structuurscan 1–4 (namen, statics, dood rekenwerk) | groen |
| structuurscan 8 (beslisredenen) | groen |
| structuurscan 9 (argumentaantallen) | groen |
| versie ↔ README ↔ changelog | groen |
| dashboard-YAML en de kopie in `dashboards/` | gelijk, 32 pagina's |

De acht attributen die nog als "geschreven maar nooit gelezen" uit de
scan komen, zijn alle acht via naamstrings of `getattr` bereikbaar — dat
is nagegaan en geen van beide is dood.

**Volledige testsuite**: 2639 tests, allemaal groen.

## v3.35.0 — Structuurscan 10: de ratel op functiegrootte

**Gevraagd**: "Wat kunnen we hier nog aan doen?" — over de 27.000 regels
in één klasse.

### Eerst gemeten in plaats van gegist

`coordinator.py` telt 27.798 regels, maar **34% daarvan is
documentatie**:

| | | |
|---|---|---|
| commentaar | 3.968 | 14% |
| docstrings | 5.588 | 20% |
| leeg | 2.259 | 8% |
| code | 15.983 | 57% |

En die code is fijnmazig: 917 functies met een **mediaan van zes
uitspraken** en een negentigste percentiel van vijfentwintig. Het is
geen kluwen van verstrengelde logica maar een groot aantal kleine, goed
uitgelegde functies.

De werkelijke complexiteit zit in tweeëntwintig uitzonderingen, en twee
daarvan zijn de echte: `__init__` met 416 uitspraken en
`_async_update_locked` met 255. **Alles opsplitsen in losse bestanden
verandert daar niets aan** — die twee blijven even groot en even lastig,
alleen dan in een ander bestand.

### Dus geen verbouwing, maar een ratel

Deze scan bevriest de huidige stand. Bestaande grote functies mogen niet
verder groeien, er mogen geen nieuwe bijkomen, en zakt er een onder de
grens dan moet hij uit de lijst — anders vertelt die lijst over een jaar
iets dat niet meer waar is, en dat is precies hoe deze codebase eerder
in de problemen kwam.

Gemeten in **uitspraken, niet in regels**. Deze codebase legt uit waarom
iets zo is, en dat is de reden dat fouten hier terug te vinden zijn: de
verklaring van 16 augustus stond letterlijk in een commentaarblok uit
v2.2.2. Commentaar mag daarom nooit tegen een grens aanlopen, en er
staat een toets op dat het dat ook niet doet.

Getoetst dat de ratel werkelijk vangt: drie regels toegevoegd aan
`_waarom_regels` en de scan sloeg aan.

### Wat dit niet is

Geen oplossing voor de twee grote functies. Die blijven staan tot er een
reden is om ze aan te raken — en dan moeten ze krimpen, want anders komt
deze scan er tussen.

**Volledige testsuite**: 2664 tests, allemaal groen.

## v3.35.1 — De tweeling vergat dat de accu het huis voedt

**Gemeld** als openstaand punt: de digitale tweeling zat er over 60
vergelijkingen gemiddeld 1,25 kWh naast, zes uur vooruit. Dat is 16% van
de bruikbare capaciteit, en het stond als "onnauwkeurige simulatie" op
de kaart.

Het was geen onnauwkeurigheid maar een **ontbrekende term**. In
`smart_discharging` — verreweg de meeste kwartieren — liet de tweeling
de accustand ongemoeid. Dat stond zelfs met zoveel woorden in de eigen
toelichting: "geen huishoudverbruik/PV-modellering buiten het
geïdentificeerde goedkoopste blok."

Reken het na:

```
zes uur x 0,23 kW geleerd huisverbruik = 1,4 kWh
gemeten gemiddelde fout                = 1,25 kWh
```

De kwartierplanning rekent dat allang uit, met
`_estimate_pv_kwh_for_period` en `_estimate_consumption_kwh_for_period`.
De tweeling gebruikte ze niet en bouwde daarnaast een eigen, simpelere
wereld — precies het soort tweede waarheid waar deze codebase eerder
last van had.

Nu volgt hij buiten het goedkope blok de netto last: geleerd
huisverbruik min zonverwachting, begrensd door de accustand, de
laadruimte en het ontlaadvermogen. Zonoverschot vult de accu in plaats
van te verdampen.

Het is en blijft adviserend; er wordt niets mee aangestuurd.

### Verder

De reden waaróm de zonbias wordt ingehouden staat nu in de export.
`learned_bias_percent` op `null` was niet te onderscheiden van te weinig
dagen.

**Volledige testsuite**: 2670 tests, allemaal groen.

## v3.36.0 — Dekking op het ongeziene deel

**Gevraagd**: dekking op `solar_forecast.py` en `switch.py` — niet omdat
daar iets vermoed werd, maar juist omdat niemand er ooit naar keek.

| bestand | voor | na |
|---|---|---|
| `solar_forecast.py` | 55% | **96%** |
| `switch.py` | 54% | **83%** |
| totaal | 85% | 87% |

64 nieuwe tests, en ze leverden meteen iets op.

### Een grens die aan de onderkant nooit kon vuren

`MAX_REASONABLE_DEVIATION_PERCENT` staat op 200 en is er onder andere om
een sensor-rollover te vangen — dat staat letterlijk in de melding die
erbij hoort:

> Ignoring implausible forecast deviation (...) likely captured during a
> sensor reset/rollover

Maar een afwijking kan aan de ONDERKANT nooit verder gaan dan −100%:
minder dan nul opbrengst bestaat niet. Voor precies het geval dat de
melding noemt, kon die grens dus nooit vuren. Draait de dagteller van de
opbrengstsensor om vlak vóór de vergelijking van 23:59, dan wordt −100%
netjes als les opgeslagen en bederft die twee weken lang de geleerde
correctie.

Nu wordt een dagteller die op nul staat terwijl er meer dan 1 kWh
voorspeld was, als omslag herkend en weggegooid. De ondergrens op de
voorspelling staat erbij zodat een donkere winterdag met 0,3 kWh
voorspeld en 0,0 werkelijk gewoon geleerd wordt — daar is nul wél een
echte uitkomst.

### Wat er verder onder de dekking kwam

De inleesroutine uit de recorder (128 regels, draait bij elke start en
vult de leergegevens): de eenheidsomrekening voor Wh en MWh, een
recorder die eruit ligt, ontbrekende geschiedenis, `unavailable` in de
reeks, en de regel dat live geleerde gegevens nooit overschreven worden
— behalve als ze onzin zijn.

En de elf schakelaars: dat aan- en uitzetten werkelijk in de coordinator
landt, dat een herstart de stand terugzet, dat elke schakelaar een eigen
id heeft, en dat er geen twee hetzelfde id delen.

**Volledige testsuite**: 2734 tests, allemaal groen.

## v3.37.0 — Dekking op de bedrading en de sensoren

**Gevraagd**: de twee laatste blinde vlekken uit de dekkingsmeting.

| bestand | voor | na |
|---|---|---|
| `__init__.py` | 50% | **71%** |
| `sensor.py` | 73% | **81%** |
| totaal | 87% | **88%** |

131 nieuwe tests, 2865 in totaal.

### De opstartcode

Het kopiëren van het dashboard en de achtergrondtekening — inclusief een
schijf die vol zit, een ontbrekend sjabloon en een `www/` die nog niet
bestaat. Deze routines draaien bij élke start, en een fout daar neemt de
hele integratie mee.

En de zes NILM-diensten: dat ze maar één keer geregistreerd worden — twee
keer betekent een "service already registered"-fout bij het herladen van
de instellingen — en dat de zonvoorspelling-tracker die naast de
coordinator in `hass.data` staat, niet per ongeluk voor een coordinator
wordt aangezien. Zou dat gebeuren, dan slaat elke dienst stuk op een
object dat de methode niet heeft.

### De sensoren

Zestig klassen, waarvan er 33 in geen enkele test voorkwamen. Ze zijn nu
alle zestig getoetst tegen een **vers gebouwde coordinator** — de eerste
ronde na een herstart, als er nog niets berekend is en de sensoren al wel
worden uitgelezen.

Die toets komt uit een echte storing: in een eerdere versie was het hele
attributenblok van de GACS-sensor één dict-uitdrukking. Viel er één
waarde weg, dan bleven álle tegels leeg, en Home Assistant toont dat als
een niet-beschikbare entiteit zonder duidelijke fout in het logboek.

Uitkomst: nul van de zestig slaat stuk. Getoetst op een echte coordinator
en niet op een stub — een stub die alles op None zet meldt zesendertig
problemen die geen van alle bestaan, want de coordinator zet zijn lijsten
en woordenboeken zelf al leeg klaar.

Daarnaast: geen twee sensoren delen een unieke id, elke sensor hangt aan
het EMS-apparaat, en elk attributenblok is een woordenboek of niets.

**Volledige testsuite**: 2865 tests, allemaal groen.

## v3.38.0 — De twee inleesroutines uit de recorder

**Gevraagd**: de resterende 12% dekking ook nog.

Eerst uitgesplitst wat die 942 ongedekte regels in `coordinator.py`
werkelijk zijn:

| soort | regels |
|---|---|
| gewone code | 510 |
| vroege terugkeer | 203 |
| voorwaarde | 86 |
| lusbesturing | 63 |
| foutafhandeling | 46 |
| logregel | 34 |

En waar ze zitten: **twee functies dragen 160 regels**, de overige 550
liggen verspreid over 210 functies met twee à drie regels elk — vrijwel
allemaal foutafhandeling en vroege terugkeer bij een niet-ingestelde
sensor.

Die twee functies zijn getoetst; de staart bewust niet. Elke regel daar
kost een eigen opzet en levert een toets op die niets bewaakt wat er toe
doet.

### Wat er nu gedekt is

`async_bootstrap_night_consumption_from_history` en
`async_bootstrap_energy_history`. Allebei draaien ze bij élke start en
allebei vullen ze leergegevens die daarna de reserveberekening in gaan.
De derde van dat soort — de zonvoorspelling — leverde bij het toetsen
meteen een fout op die er jaren in had gezeten, en dat was de reden om
deze twee ook te doen.

Getoetst: een recorder die eruit ligt, een ontbrekende
recorder-component, lege geschiedenis, `unavailable` in de reeks, en de
regel dat live geleerde gegevens nooit worden overschreven. Plus dat de
dagreeks op datum gesorteerd blijft — de reparatie van v3.32.1 heeft
daarmee nu een eigen wachter.

Onderweg bleek dat de dagreeks **langetermijnstatistieken** leest en niet
de losse toestanden, anders dan de andere twee routines. Dat was uit de
code alleen met moeite te zien; nu staat het in een toets.

Ook meegenomen: de capaciteitsmeting van de kalibratie — dat hij alleen
loopt tijdens een kalibratie, dat een gat in de tijd niets optelt, en dat
onder 70% van de schaal geen uitkomst wordt gegeven.

**Volledige testsuite**: 2881 tests, allemaal groen. Totale dekking 89%.

## v3.39.0 — Een verband dat sterk oogt maar het niet is

**Gevraagd**: "Hoe zit het met correlaties welke gemaakt worden door de
integratie?"

Vier verbanden nagelopen. Drie houden stand — de weerbronnen onderling
(de spreiding van 51 procentpunt wordt netjes gemeld), de
weersvoorspelling tegen de kamertemperatuur (van 4 graden fout naar
−0,1), en de PV-uurcorrecties. De vierde niet.

### De temperatuur-verbruikreeks

```
21,3 °C -> 239 W        helling  +6,3 W per graad
19,2 °C -> 212 W        correlatie r = 0,90
17,6 °C -> 207 W        r² = 0,81
17,0 °C -> 209 W
17,0 °C -> 197 W        bereik 15,3 tot 21,3 °C
15,9 °C -> 205 W
15,3 °C -> 197 W
```

Een correlatie van 0,90 ziet er overtuigend uit. Leg hem naast het
dagverbruik en hij valt om: 12 en 13 augustus 12,3 en 12,6 kWh met
bewoners thuis, vanaf 15 augustus 4,6 tot 7,1 kWh met een leeg huis. **De
warmste meting is de laatste bewoonde nacht.** Het model zag "warmer is
meer verbruik" terwijl de oorzaak "thuis is meer verbruik" was.

En structureler: dit model is gebouwd na de analyse van 11 januari, de
koudste nacht van het jaar, waar het verband **negatief** hoort te zijn.
Deze positieve helling doorgetrokken naar 0 °C geeft 105 W waar er 400
hoort te staan.

### Drie wachters

- **Bereik.** Onder de 8 graden spreiding wordt er niet voorspeld. Zes
  graden is te smal om een helling uit af te leiden die op een
  winternacht wordt losgelaten.
- **Teken.** Een positieve helling kan in de zomer kloppen — koeling,
  koelkast — maar wordt nooit ónder het gemeten bereik toegepast.
- **Uitleg.** `get_temp_consumption_bruikbaarheid` zegt waarom er niet
  voorspeld wordt. Zonder dat lijkt het alsof er te weinig metingen zijn,
  terwijl de reeks vol staat. Staat ook in de export.

### En één ding dat bewust NIET geweigerd wordt

Buiten het gemeten bereik voorspellen blijft toegestaan. Dit model
bestaat juist voor de koudste nacht van het jaar, en die ligt per
definitie buiten wat er tot dan toe gemeten is — weigeren zou het
uitschakelen op precies het moment waarvoor het gebouwd is. Het wordt
wel gemarkeerd: doorgetrokken is niet gemeten.

Die keuze kwam uit een bestaande toets die omviel bij mijn eerste,
strengere versie. Terecht omgevallen.

**Volledige testsuite**: 2891 tests, allemaal groen.

## v3.40.0 — Nog twee conclusies uit te weinig gegevens

**Gevraagd**: "Zijn er nog meer ontwerpfouten?"

Elke geleerde reeks nagelopen op scheefheid en bereik. Twee kwamen eruit
met dezelfde fóútsoort als het temperatuurverband: een conclusie die
steviger is dan de gegevens dragen.

### Een tweede dakvlak uit acht dagen

```
pv_peak_azimuth_history: 163,6  174,8  175,3  136,9
                         203,9  137,4  240,3  149,4
spreiding: 103 graden  ->  "waarschijnlijk meerdere dakvlakken: ja"
```

Eén wolk rond het middaguur verschuift de piek al met tientallen graden.
Bij acht dagen dragen de uitersten waarschijnlijk het weer en niet het
dak — 240 tegenover 137 graden is geen tweede dakvlak, dat is bewolking.

De conclusie wacht nu tot twintig heldere dagen. De spreiding blijft
gewoon zichtbaar, met de reden erbij waarom er nog geen oordeel volgt.

### De oude rendementsreeks als terugval

```
learned_efficiency_history: [95.5, 76.9, 74.2, 82.9, 83.2, 97.6, 56.4]
```

41 procentpunt spreiding. Die reeks wordt sinds de invoering van de halve
cycli **nergens meer bijgeschreven** — hij staat alleen nog in de opslag
en dient als terugval zolang de halve metingen er niet zijn. Maar hij is
opgebouwd zonder de plausibiliteitsgrenzen die nu gelden, en 56,4% ligt
daar ruim buiten.

Een terugval hoort aan dezelfde eis te voldoen als een verse meting,
anders levert hij een getal waar de rest van de integratie niet meer mee
had willen rekenen — en dat getal schaalt de reserveberekening en de
kostprijs. De terugval gaat nu door dezelfde grenzen, en blijven er te
weinig bruikbare metingen over, dan geeft hij niets terug: dan valt de
integratie terug op de veilige 90%.

### Wat wél standhield

De weerbronnen onderling (spreiding van 51 procentpunt wordt gemeld), de
weersvoorspelling tegen de kamertemperatuur (van 4 graden fout naar
−0,1), de PV-uurcorrecties, en het rendement zelf: laden 89,0%, ontladen
94,15%, heen en terug 83,8% — netjes begrensd en plausibel.

**Volledige testsuite**: 2896 tests, allemaal groen.

## v3.41.0 — De klimaatcellen sleutelden op de verkeerde grootheid

**Besproken**: de emmers van `climate_rate_history`, waarin binnen
dezelfde cel soms opwarming en soms afkoeling stond.

```
26.0|beide_open|uit:  [-0.284, +0.137, -0.067, +0.009, -0.156]
```

Ik dacht eerst dat er een vierde dimensie bij moest — bewolking, of de
zon op het raam. Dat bleek niet zo. De cel sleutelde op de
**buitentemperatuur**, terwijl het gemeten getal de verandering van de
**binnentemperatuur** is.

Dat is geen ruis maar natuurkunde. Een kamer volgt de wet van Newton:
hoe snel de temperatuur verandert hangt af van het **verschil** met
buiten, niet van de buitentemperatuur alleen. Bij 26 graden buiten warmt
een kamer van 21 op en koelt een kamer van 28 af — zelfde cel,
tegengesteld teken. Precies wat er stond.

### Geen dimensie erbij, maar een vervangen

De sleutel is nu het verschil tussen buiten en binnen. **Het aantal
cellen blijft gelijk**, de natuurkunde klopt, en het teken wordt
voorspelbaar: positief verschil betekent opwarmen. Dat was de zorg bij
het bespreken — 252 cellen die elk hun eigen data nodig hebben — en die
zorg is hiermee van tafel.

De oude cellen zijn weggegooid. Ze zijn niet om te rekenen: de
binnentemperatuur van dat moment is niet bewaard. Ze laten staan zou
twee soorten sleutels naast elkaar geven waarvan de helft nooit meer
gelezen wordt.

### En een wachter erbovenop

Ook met de juiste sleutel blijft een cel waarin de helft opwarmt en de
helft afkoelt onbruikbaar — dan vangt hij nog iets anders, bijvoorbeeld
de zon op het raam. Zo'n cel heet nu `niet_eenduidig` en levert geen
geleerd tempo, in plaats van een mediaan zonder betekenis.

**Let op**: de klimaatprojectie begint hierdoor opnieuw met leren. Bij
een kamer die 's zomers dicht bij de buitentemperatuur zit, vullen de
cellen rond het nulverschil zich snel.

**Volledige testsuite**: 2900 tests, allemaal groen.

## v3.42.0 — Drie punten: saldering, proefstand, vertalingen

### 1. De verkoopcheck kende de saldering niet

Op 31 december 2026 vervalt de saldering. Dan wordt een teruggeleverde
kWh niet meer weggestreept tegen een ingekochte: je krijgt het kale
tarief terwijl inkoop belast blijft.

De machinerie daarvoor ligt er sinds v1.1.0 —
`_get_feedin_value_per_kwh` rekent beide werelden al uit, de
configuratie staat er, en de datum is instelbaar. Maar **de
verkoopcheck gebruikte hem niet**. Die vroeg alleen "houdt de woning het
tot het goedkope blok?" en ging er stilzwijgend van uit dat verkopen
verder gratis geld is. Precies die aanname klapt om.

Er is nu een derde rem: verkopen wordt geweigerd zodra dezelfde kWh
straks méér bespaart dan hij nu opbrengt, na rendement en slijtage.

```
verkopen nu       2,0 ct/kWh
vasthouden       27,7 ct/kWh   (duurste prijs 40 ct, 94% rendement,
                                10,9 ct slijtage)
```

**Tot 1 januari 2027 is deze rem volledig inert**, en daar staat een
toets op. Ontbreekt het teruglever-attribuut op de prijssensor, dan
wordt er niets besloten — gissen met de inkoopprijs is precies de
aanname die dan niet meer klopt.

### 2. De proefstand zegt nu wat genoeg is

Negen kandidaten, waarvan er meerdere weken op "klaar om mee te doen"
stonden, en er is er nog nooit één doorgestroomd. Wat ontbrak was geen
bewijs maar een **afspraak** — zonder criterium vooraf wordt het altijd
"nog even een week".

De eis staat nu in `const.py` en bij elke kandidaat staat wat er nog aan
ontbreekt:

| eis | waarde |
|---|---|
| gunstig bij | 90% van de metingen |
| aantal metingen | 200 |
| gemeten over | 14 dagen |
| voordeel | 2,0 ct/kWh |

Die veertien dagen zijn er bewust bij: een kandidaat meet elk kwartier,
dus driehonderd metingen kunnen uit één etmaal komen. Driehonderd
metingen op één dag is één dag.

Dit besluit niets — meesturen blijft een handmatige keuze, één kandidaat
tegelijk.

### 3. De tekstbestanden liepen uiteen

`strings.json` miste 32 sleutels die wél in `nl.json` en `en.json`
stonden: de labels van de helft van de instelvelden. Aangevuld, en er
staat nu een toets op dat de drie bestanden dezelfde sleutels dragen —
in beide richtingen, en zonder lege teksten.

**Volledige testsuite**: 2923 tests, allemaal groen.

## v3.42.1 — De opruiming werkte, maar had geen effect

**Gemeld** door de export van 20 augustus 14:10, ná het installeren van
v3.41.0: veertig klimaatcellen, allemaal nog met de oude sleutel op
buitentemperatuur, en geen enkele met de nieuwe.

De opruiming werkte wel degelijk — er staat een toets op die aantoont
dat hij de oude sleutels weggooit. Maar hij draait bij het terugzetten
van de **opslag**, en daarna komt de klimaatsensor langs die dezelfde
cellen terugzet uit zijn eigen **entiteit-attributen**. Twee paden voor
dezelfde gegevens, en de tweede won.

Precies de klasse fout die deze codebase eerder zag bij de
NILM-apparaten (v0.63.115): entiteit-attributen die de Store
overschrijven, met als gevolg dat een reparatie in de opslag geen effect
heeft.

Het herstelpad laat nu alleen het nieuwe sleutelformaat door.

### Structuurscan 11: geen twee stille herstelpaden

Een veld dat zowel in de Store staat als uit een entiteit wordt
teruggezet, heeft twee bronnen van waarheid. Dat mag — soms is het de
enige migratieweg — maar dan moet het bewust zijn en in de scan staan
met de reden erbij.

**De scan vond meteen een tweede geval, en dat was er één van mij.** In
v3.27.0 zette ik de kalibratiestand in de opslag en liet ik het
bestaande herstelpad van de schakelaar staan. De entiteit wordt opgezet
ná het terugzetten van de opslag, dus won die altijd: zet je de stand uit
en herstart je binnen de dertig seconden voordat de opslag is
weggeschreven, dan kwam de kalibratie terug alsof er niets gebeurd was.

De opslag is nu leidend. Die draagt ook de momentopname en de lopende
capaciteitsmeting, en die drie horen bij elkaar.

**Volledige testsuite**: 2929 tests, allemaal groen.

## v3.42.2 — De cel op het omslagpunt kon nooit slagen

**Gemeten** in de export van 20 augustus 20:43, de eerste cel die zich
vulde na de omzetting naar verschil-sleutels:

```
d0.0|gedeeltelijk|uit   [0.394, 0.219, -0.142, -0.068, 0.045]
mediaan 0,045 °C/uur    spreiding 0,54
```

Tekens door elkaar heen — precies waar de wachter van v3.41.0 op afgaat.
Maar hier is dat geen ruis en geen verkeerde sleutel: bij buiten gelijk
aan binnen is het werkelijke tempo per definitie ongeveer nul, en dan
wisselt het teken vanzelf.

Die wachter zou de cel rond nul verschil **altijd** afwijzen. Niet omdat
hij onbruikbaar is, maar omdat hij op het omslagpunt ligt — de ene cel
die per constructie nooit kon slagen. En het is niet zomaar een cel: bij
een kamer die 's zomers dicht bij de buitentemperatuur zit, is dat de
cel die zich het eerst vult.

Een tempo onder een tiende graad per uur verandert de kamer over een
projectie van zes uur met minder dan een halve graad. Dat is "er gebeurt
niets", en dat is een bruikbaar antwoord. Cellen met een mediaan onder
die grens mogen daarom van teken wisselen; daarboven blijft de wachter
staan.

De toets die de wachter bewaakte gebruikte cijfers met een mediaan van
−0,067 — óók onder de grens. Die is vervangen door een reeks die
werkelijk een half graad per uur beweert en zichzelf tegenspreekt, want
dát is het geval waar de wachter voor bedoeld is.

**Volledige testsuite**: 2931 tests, allemaal groen.

## v3.43.0 — Eén hand die geeft en één die het wegneemt

**Gevraagd**: "Als ik een melding krijg dat de accu de nacht niet haalt,
moet hij toch eigenlijk ook het manual terugleveren stoppen? Of zie ik
dat verkeerd?"

Niet verkeerd. Gemeten op 20 augustus, in dezelfde export:

```
20:06  KRITIEK  vier kwartieren waarin de accu niets meer kan
                leveren, morgen 06:30-07:30

20:45  verkopen  37,5 ct   soc 69%
21:00  verkopen  37,4 ct   soc 64%
...
23:00  verkopen  34,9 ct   soc 35%
```

Acht kwartieren verkoop gepland, terwijl de planning zelf waarschuwt dat
de accu morgenvroeg leegloopt.

Beide kloppen op zichzelf. `may_sell_now` kijkt tot het volgende
goedkope blok; de tekortmelding kijkt de hele planning door. Maar het is
één accu, en dan is dit één hand die geeft en één die het weer wegneemt.

Er is nu een vierde rem: voorziet de planning drie of meer
tekortkwartieren, dan wordt er niet verkocht. Dezelfde ondergrens als de
melding zelf — onder de drie is het geen tekort maar een planning die
precies uitkomt, en die reden staat uitgeschreven bij
`PLAN_SHORTFALL_ALERT_MIN_QUARTERS` na 75 meldingen waarvan 47 op één
dag.

### Twee eigen wachters die aansloegen

**De eerste versie riep de kwartierplanning aan vanuit de verkooptoets.**
Dat bouwt honderdtien kwartieren opnieuw op bij élke ronde, en een fout
daarin breekt dan de aansturing — de volledige tick-toets viel er meteen
over om. De rem leest nu de laatst berekende stand, die elke ronde toch
al wordt doorgerekend voor de melding. Eén ronde vertraging is
onschadelijk: een tekort dat over acht uur valt, verschuift niet binnen
een minuut.

**En de functiegrootte-ratel van v3.35.0 sloeg aan** omdat `__init__`
met twee uitspraken groeide. Teruggebracht naar één veld, en die ene is
bewust in de lijst bijgewerkt met de reden erbij. De ratel is een
drempel en geen verbod: hij dwingt af dat groei een besluit is.

**Volledige testsuite**: 2936 tests, allemaal groen.

## v3.44.0 — De tabel toont wat er niet gebeurt

Gemeten op 20 augustus 21:16, één minuut na het installeren van de rem
uit v3.43.0:

```
sell_check     mag_verkopen: false, "planning voorziet een tekort"
quarter_plan   30 verkoopkwartieren
```

De aansturing weigert te verkopen; de tabel toont dertig
verkoopkwartieren. Geen van beide is fout, maar samen misleiden ze.

### Waarom de simulatie NIET wordt aangepast

De eerste neiging is om de planning de rem te laten meenemen. Dat bouwt
een slinger:

```
planning simuleert mét verkoop  →  tekort  →  rem gaat aan
rem aan  →  geen verkoop  →  geen tekort  →  rem gaat uit
rem uit  →  verkoop  →  tekort  →  rem gaat aan
```

Precies het pendelen dat de koeling vier versies lang deed. De planning
**moet** met verkoop simuleren, want dat is de tegenfeitelijke wereld
die de rem rechtvaardigt: "als ik nu verkoop, kom ik morgenvroeg
tekort."

Dat de rem stabiel is, komt er dus door dat de planning hem niet kent.
Daar staat nu een toets op, zodat niemand het later per ongeluk
"repareert".

### Wat er wel is veranderd

De samenvatting draagt `verkoop_geblokkeerd` en een reden, uit dezelfde
drempel als de rem zelf — twee drempels zou betekenen dat de tabel iets
anders zegt dan de aansturing doet.

En `last_plan_shortfall` staat nu in de diagnostiek-export. Zonder dat
veld was op 21:15 niet na te gaan of de rem zweeg omdat er geen tekort
was, of omdat de stand na de herstart nog leeg was.

**Volledige testsuite**: 2942 tests, allemaal groen.

## v3.44.1 — De dagportie liet de koelronde omvallen

**Gemeld** met drie meldingen op een rij:

```
21 Aug 19:34  De koeling geet te vaak an
              De ventilator sloeg vandaag al 4 keer aan
21 Aug 19:36  1 onderde(e)l(en) kan zichzelf neet berekenen:
              ronde:accukoeling
```

Twee minuten na het aanslaan van de dagportie uit v3.33.0 lag de
koelronde eruit.

De oorzaak: die tak deed een **kale `return`** in een functie die
`-> dict` belooft, en gaf dus `None` terug. Elke andere vroege terugkeer
in `evaluate_battery_cooling` geeft `resultaat` terug; deze niet.

### Waarom de suite groen bleef

De toetsen op de dagportie keken naar wat hij **beslist** —
`_goedkope_koeling_op_slot` geeft True of False — en niet naar wat de
omliggende functie **teruggeeft**. Vijf toetsen op het besluit, nul op
de uitkomst.

Er staat nu een toets op dat er in `evaluate_battery_cooling` geen kale
`return` voorkomt, en dezelfde toets loopt over vier andere functies die
een dict beloven. Nagegaan dat hij de fout werkelijk vangt door de kale
`return` terug te zetten: twee toetsen vielen om.

### Wat er ondertussen wel goed ging

De melding zelf klopte, inclusief het advies:

> De ventilator sloeg vandaag al 4 keer aan voor goedkope koeling. Bij
> een aanzetdrempel van 25 °C komt hij op deze installatie steeds terug
> (...) Overweeg de drempel een paar graden hoger te zetten.

En de tekortrem meldde zich af zodra hij niet meer nodig was: "de
planning voorziet al een half uur geen kwartieren meer waarin het huis
aan het net hangt. Laagste stand: 22%."

**Volledige testsuite**: 2949 tests, allemaal groen.

## v3.45.0 — Een correctie per soort dag

Twee reparaties die bij elkaar horen: de zonvoorspelling, en het
meetinstrument waarmee je ziet of die klopt.

### De biascorrectie is niet meer vlak

In v3.33.0 is de vlakke correctie ingehouden omdat het twee soorten
dagen zijn: heldere binnen 2%, wisselvallige 40 tot 55% ernaast.
Nagerekend won geen van de drie mogelijkheden — gemiddelde, mediaan of
niets.

Inhouden was het eerlijke antwoord maar geen oplossing. Op 23 augustus
stond de voorspelling nog altijd ongecorrigeerd, en de integratie meldde
het zelf: "Twee soorten dagen: 2 van de 5 binnen 10% en 2 meer dan 25%
ernaast."

De oplossing is geen beter gemiddelde maar een correctie **per soort
dag**. De afwijking wordt vanaf nu bewaard mét de bewolking van die dag,
en de correctie komt uit het vakje dat bij de verwachte bewolking hoort:

| vakje | bewolking |
|---|---|
| helder | onder 30% |
| half | 30 tot 70% |
| bewolkt | boven 70% |

Vier dagen per vakje voordat het meetelt. Is een vakje nog niet vol, dan
blijft de bestaande terugval gelden — inclusief het inhouden bij een
gespreide reeks. Er verandert dus niets tot de vakjes zich gevuld
hebben, en dat duurt ongeveer twee weken.

De bewolking komt uit de coordinator, die de weerentiteiten kent; de
tracker kende die niet. Die doorgifte staat als eigen ronde-taak in de
lijst.

### De tweelingfout is gesplitst

Gemeten op 21 augustus, de dag na de reparatie van v3.35.1:

```
47 vergelijkingen zonder zon   gemiddeld +0,90 kWh
13 vergelijkingen met zon      gemiddeld +2,16 kWh
```

De simulatie zelf is nauwkeurig; wat er overdag bij komt is de
zonverwachting. Twee dagen later stond het totaal op 1,56 kWh en zag het
eruit als een verslechterende tweeling — terwijl het de voorspelling was
die het slechter deed.

Elke voorspelling draagt nu de verwachte zon over zijn venster, en de
kaart splitst de fout in nacht en dag mét een duiding welke van de twee
beweegt. Eén getal dat twee dingen meet, vertelt niet waar je moet
repareren.

### Wat de ratel deed

De functiegrootte-ratel van v3.35.0 sloeg drie keer aan bij het
inbouwen: `_async_update_locked` mocht niet groeien, en
`_update_weather_ensemble_check` ook niet. Uiteindelijk is de doorgifte
een eigen functie geworden in de rondelijst — met eigen foutafhandeling,
en beter dan waar ik hem eerst had gezet.

**Volledige testsuite**: 2966 tests, allemaal groen.

## v3.45.1 — De resetknop legde de planning plat

**Gemeld** direct na het indrukken van de resetknop bij thuiskomst van
vakantie. Elf onderdelen tegelijk:

```
kwartierplanning, kwartier_samenvatting, overzichtsplaat,
overzichtsecties, proefstand, ronde:bijkopen en vijf
diagnostiek-onderdelen

TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'
```

`_estimate_consumption_kwh_for_period` geeft **bewust** None zodra één
uur in het venster nog geen geleerde waarde heeft. De docstring zegt het
letterlijk: *"Returns None (...) so the caller can fall back to a
simpler estimate."* Zes van de negen aanroepers doen dat ook, met
`or 0.0`. De kwartierplanning niet, en die rekende er rechtstreeks mee
door.

Vóór de resetknop van v3.30.0 kwam een volledig leeg profiel in de
praktijk niet voor — er was altijd wel geschiedenis. Die knop maakte de
lege staat bereikbaar, en daarmee werd een sluimerende fout van jaren
oud opeens zichtbaar. De knop was niet fout; hij liep tegen iets aan dat
er al lag.

### De terugval is niet nul

Nul zou betekenen dat het huis niets gebruikt, en dan belooft de
planning een volle accu die er niet komt. De volgorde is nu: het
geleerde uurprofiel, anders het geleerde nachtverbruik, anders de
gemeten belasting van dit moment, en pas als laatste een vaste 0,25 kW —
de basislast die deze woning in de zomer laat zien.

### Wat er ondertussen bleef werken

De sturing zelf, de verkooptoets, de koeling en de reservemarge draaiden
gewoon door. Wat wegviel was alles wat uit de planning leest.

**Volledige testsuite**: 2973 tests, allemaal groen. Nagegaan dat de
nieuwe toets de fout werkelijk vangt door de oude aanroep terug te
zetten.

## v3.45.2 — Een bewaking die naar de verkeerde kant keek

**Gemeld** op 26 augustus 09:15, vijf onderdelen tegelijk:

```
kwartier_samenvatting, overzichtsplaat, overzichtsecties,
ronde:bijkopen, diagnostiek:quarter_plan_summary

ValueError: min() iterable argument is empty
```

Twee uur eerder, om 07:05, meldde de integratie zelf:

> `sensor.zendure_manager_available_kwh`, `sensor.hw_p1_vermogen` geeft
> al minstens 15 minuten geen waarde.

De code stond er zo:

```python
min(r["soc_bruikbaar_procent"] for r in plan
    if r.get("soc_bruikbaar_procent") is not None) if plan else None
```

De bewaking kijkt naar `plan` — de **herkomst** — terwijl de reeks die
in `min()` gaat door een filter is gehaald. Het plan bevatte 59
kwartieren, dus `if plan` was waar. Geen enkel kwartier had nog een
bruikbare accustand, want die komt uit de weggevallen sensor. De reeks
was leeg.

Eén regel hoger staat het wél goed: `min(socs) if socs`. Daar wordt de
lijst zelf getoetst.

### Structuurscan 12

Een `min` of `max` over een comprehension **mét filter**, bewaakt door
een toets op precies de lijst waar die comprehension overheen loopt. Dat
is altijd fout: het filter kan de reeks leegmaken terwijl de bron gevuld
blijft.

Getoetst dat de scan de storing van 26 augustus werkelijk vangt, en dat
hij de goede vorm — een toets op de gefilterde lijst — met rust laat.

Dit is de tweede storing in drie dagen die door een wegvallende sensor
kwam. De integratie meldde die uitval keurig; wat ontbrak was dat de
berekening erop voorbereid was.

**Volledige testsuite**: 2988 tests, allemaal groen.
