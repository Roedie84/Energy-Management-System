# Leerlog Energy Management System

Doorlopende leerronde (elke 4 uur). Alleen gemeten getallen; KPI's in KPI.csv, referenties in BASELINE.md, voorstellen in VOORSTELLEN.md.

## 07-10 23:15 · tussenronde (eerste ronde, baseline uit ~10 dagen historie)
- Gemeten: PV, net, accu per dag 28-09..06-10 (statistics); PV-voorspelling 31 dagen (pv_forecast_accuracy); tekortnachten 7 n; uurlijkse teruglevering 's nachts.
- PV-voorspelling: MAE 10,5% (30 d) → 5,2% (7 d); bias −4,4% / −1,7% (voorspelling iets te hoog). Geen duidelijk verschil bewolkt >70% vs ≤70% (bias −6,8 vs −4,6, n=16/13).
- Tekortnachten 4 van 7 (5,68 kWh): 2 economisch, 2 planning, 0 capaciteit. Reserve te hoog: 0 van 7.
- Opvallend: als de accu 's nachts levert, gaat er constant ~60 Wh/u naar het net (mediaan 60, n=50 uren, 00-07 u gem. 0,35 kWh/nacht). Oorzaak: smart-modus van zendure-ha volgt een P1-doel van ~−50 W (CHANGELOG v0.63.19). Steekproef 07-10 02:00: accu 290 W, P1 −50 W.
- Gevolg: het geleerde nachtverbruik (`p1 + accu + pv`) is huisverbruik zonder dit lek; de accu levert ~50 W meer dan de reserve verwacht → ~0,5-0,8 kWh/nacht over het hele ontlaadvenster. Dit is energie die verkocht wordt terwijl de reserve nodig is (HARDE REGEL "huis gaat voor") → gemeld, voorstel L-EMS-001.
- Hypothese H-EMS-1: het nachtlek verklaart een deel van de tekort-kWh in planning-nachten. Toets volgende ronden: lek-kWh per nacht naast tekort-kWh.
- Hypothese H-EMS-2: PV-bias is nu klein (−2%) en daalt; geen correctie nodig. Volgen tot 14 dagen.
- Niet gemeten (meetbaarheid): uurlijkse PV-voorspelling per uur (geen historie van uurvoorspelling in attributen gevonden; volgt), kwartierbeslissingen tegen achteraf-optimum (nog geen replay gebouwd), SoC-voorspelling tegen werkelijk.
- Geen release (tussenronde; 10 releases vandaag door andere sessies, v5.44 geïnstalleerd).

laatste ronde: 07-10 23:15, gemeten t/m 07-10 23:00

## 07-10 23:40 · tussenronde (handmatig gestart)
- Correctie: de vorige ronde was om 23:15, niet 23:30 (tijdstempels aangepast).
- Sinds 23:15 geen nieuwe gebeurtenis om te meten; geen release.

laatste ronde: 07-10 23:40, gemeten t/m 07-10 23:40
