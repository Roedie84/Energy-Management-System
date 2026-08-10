# Energie Management Systeem — overdracht naar nieuwe chat

**Nieuwe chat noemen: "Energie Management Systeem"**

## Waar we staan

| | |
|---|---|
| Versie | **v1.24.3** |
| Tests | **1750**, allemaal groen |
| Repo | https://github.com/Roedie84/Energy-Management-System |
| Lokaal pad | `/home/claude/ems/` |
| Transcripts | `/mnt/transcripts/` (zie `journal.txt`) |
| Exports | `/mnt/user-data/uploads/` |

**Belangrijk:** v1.24.3 is nog niet in de praktijk beproefd. Alles vanaf
v1.22.0 is vandaag gebouwd en nauwelijks een dag in bedrijf geweest.

---

## De installatie

- Zendure SolarFlow 2400 AC, **3 × AB3000X** (8,6 kWh)
- **Harde ondergrens 10%** → 7,74 kWh bruikbaar
- Laden **2000 W**, ontladen **1600 W** — **bewust handmatig begrensd**
- SolarEdge PV, Solcast-voorspelling, Zonneplan kwartierprijzen
- Prijzen komen als **rauwe eenheden** binnen (3181681 = €0,3181681),
  delen door `PRICE_SCALE_FACTOR` (10.000.000)
- Rendement gemeten 90,8% (fabrikant claimt tot 93%)
- Koelkast en diepvries staan in de schuur

---

## Wat er vandaag is gebouwd (v1.20.2 → v1.24.3)

### Zonopvang uitstellen naar een goedkoper uur (v1.22.0)

De accu neemt een vast aantal kWh op; **wélke** dat zijn bepaalt wat je
exporteert. Vroeg laden slurpt de dure ochtendzon op (26,8 ct) en laat de
goedkope middagzon over voor het net (13,6 ct). Laat laden doet het
omgekeerd.

Gesimuleerd op 10 augustus: **+€0,49** bij omslag 13:00.

Rekent tot **16:00** (de late middagzon is dan het vangnet) met **25%**
marge. Vier remmen: te weinig zon, minder dan 5 ct verschil, accu onder
25%, of na 16:00.

### De woning gaat voor verkopen (v1.23.0)

Onder **5 kWh** verwachte dagopbrengst wordt er niet verkocht — ook niet
met een volle accu. Anders moet er na de verkoop genoeg overblijven om
het huis te voeden tot het goedkope blok, met **1,5×** marge.

Aanleiding: op een winterdag verkocht de accu 's ochtends tot nul en
stond daarna drie uur leeg terwijl het huis 25–33 ct betaalde. De reserve
klopte wel, maar verkopen gaat op 1600 W terwijl het huis 300 W trekt.

### Kwartierplanning (v1.22.2 → v1.24.3)

Eigen pagina met per kwartier: prijs, zon, modus, **echte SoC** en lopend
totaal. Negen uur vooruit (36 regels), voorbije kwartieren verdwijnen.
Gewijzigde kwartieren kleuren **rood** met "was ..." erbij.

Aparte pagina *Planning-samenvatting* met verwachte opbrengst, laagste
SoC, kwartieren met tekort.

### Meldingen (v1.23.4)

Drie soorten, elk apart uitschakelbaar:

| Melding | Standaard |
|---|---|
| Accu haalt de nacht mogelijk niet | **aan** |
| Zon opvangen uitgesteld | uit |
| Verkopen geblokkeerd voor de woning | uit |

Alleen bij een overgang, niet elke tick.

### Achterhoeks (v1.24.0)

Eén schakelaar op de Meldingen-pagina zet alle meldingen om — telefoon én
meldingenoverzicht. 26 titels en ~70 woordvervangingen in één tabel in
`const.py`. Nadrukkelijk een benadering, geen gecontroleerde streektaal.

### Overige correcties

- **v1.20.3** — de dagelijkse PV-vergelijking lukte **nooit**: de
  vastlegging van 20:00 wiste elke avond wat om 23:59 vergeleken moest
  worden
- **v1.21.0** — de diepvries was niet defect; 13 van 30 dagen was
  meetuitval, waardoor de referentie op 19,68 W stond in plaats van 76,34
- **v1.21.5** — "Nachtverbruik 403 W" bleek het **ontlaadvenster**
  (avond én nacht), niet de nacht
- **v1.23.3** — de minimum-SoC stond op 15% terwijl de accu 10%
  aanhoudt: **0,43 kWh** die in élke berekening ontbrak

---

## Openstaand

**Nog niet beproefd.** Vraag om een verse export en kijk naar:

- `quarter_plan_summary` → **tekort_kwartieren** hoort **0** te zijn
- `laagste_soc_procent` → hoort nooit onder 10% te komen
- `solar_defer_plan` → slaat het uitstelplan aan, en met welke winst?
- `sell_check` → wordt verkopen terecht wel of niet geblokkeerd?

**Twee dingen die Ruud zelf moet beoordelen:**

1. **`sensor.zendure_manager_operation_state`** — welke waarden geeft
   die precies? Staat er iets anders dan *Ontladen* / *Laden*, dan die
   term toevoegen aan `BATTERY_STATE_DISCHARGING` / `_CHARGING`.
2. **Tien van de 37 apparaten hebben geen referentiewaarde** (rolluiken,
   melkopschuimer). Daar kan geen drift worden vastgesteld.

**Uitbreidingsadvies** (met echte prijzen: module €729, omvormer €374):
één omvormer draagt **zes** modules, dus capaciteit vraagt geen tweede
omvormer. Vermogen verhogen naar 2400 W vraagt een **eigen groep** en een
elektricien — dat was mijn eerdere "gratis" advies, en dat klopte niet.

---

## Werkwijze

- **Nederlands**, terse en direct
- Elke wijziging: **eigen versienummer**, README + CHANGELOG bijwerken,
  volledige testsuite groen, zip opleveren
- Commentaar in de code legt de **aanleiding** vast, met de gemelde zin
  erbij — niet alleen wat de code doet
- Ruud levert screenshots, diagnostiek-JSON en ruwe CSV; hij duwt door
  tot de werkelijke oorzaak
- **Eerlijk zijn over eigen fouten.** Er zijn er vandaag flink wat
  geweest en dat benoemen werkt beter dan het gladstrijken

## Terugkerende valkuilen

1. `yaml.dump` verdubbelt aanhalingstekens in Jinja
2. Entity_id verandert **niet** mee bij hernoemen (`piekvermogen` v1.6.4,
   airco v1.17.6, ontlaadvenster v1.21.5)
3. **Testopstellingen die niet op de werkelijkheid lijken toetsen niets**
   — prijzen in euro's terwijl de sensor rauwe eenheden geeft (v1.24.2),
   getallen in plaats van lijsten (v1.19.5)
4. `_get_forecast_entries` gooit `KeyError` zonder prijssensor — afschermen
5. Zoeken op een vast aantal tekens breekt zodra commentaar groeit;
   verankeren op de volgende klasse
6. Dashboardpagina's hebben een grens van **2500 tekens** en **6 kolommen**

## Locked besluiten

- Dynamische reserve en energiebrug-check zijn **twee aparte** mechanismen
- Zonherlading telt **niet** mee in de prijsprioriteit-rangschikking
- Arbitrage-laden is **permanent verwijderd**
- Verkopen op `manual` mag **alleen** als de accu die dag **niet van het
  net** is geladen
