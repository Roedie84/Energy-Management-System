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

## 07-10 23:45 · tussenronde
- **Correctie 23:15:** de −50 W op de P1 ("nachtlek") is een bewuste instelling (Zendure regelt op P1+50) en zit sinds v5.20 in de reserve (`regelverschuiving_w` = 50, live gecontroleerd in gacs_zelfbeoordeling); de tekorttelling telt hem niet als verkoop (v5.42). Geen schending HARDE REGEL. L-EMS-001 vervallen.
- H-EMS-1 getoetst met uurdata 29-09..07-10 (9 nachten): beide planning-tekortnachten volgden op avondverkoop via `expensive_quarter_peak` onder de reserve (03-10: 1,37 kWh → 0,68 kWh tekort; 04-10: 5,14 kWh, vanaf 19:55 beschikbaar < reserve → 1,68 kWh tekort). Al gevonden en hersteld in v5.28.4 (04-10 10:32). H-EMS-1 verworpen; oorzaak = piekregel.
- Effect v5.28.4 gemeten: sinds 04-10 10:32 0× `expensive_quarter_peak`; 4 nachten (05-10..07-10 + 04→05) zonder tekort; avondverkoop 04-10 alleen boven de reserve (`expensive_quarter`).
- MC-kalibratie (nieuw): tekortkans om 22:00 vs uitkomst, 8 nachten 30-09..07-10: tekortnachten 98/100/45/97%, overige 0/0/0/0% → Brier 0,038 (n=8). Goed onderscheid, n klein → H-EMS-3.
- PV per uur (meetbaar via attribuut `profile` van pv_hourly_forecast_bias): werkelijk/Solcast mediaan 0,90-0,98 rond de middag, 0,52-0,69 om 06-07 en 15-17 UTC. De integratie leert en gebruikt dit profiel al zelf. Tweede voorspelling 13 d: Solcast 6,1% mediaanfout, tweede bron 31,6%.
- Lopend vannacht (→08-10): beschikbaar 4,23 kWh, nodig 4,54 kWh tot blok 12:15 → verwacht tekort 0,31 kWh; MC 41,7%. Toetsen in de dagafsluiting van 09-10.
- Meetbaarheid: MC-tekortkans heeft geen state_class → geen lange statistiek, alleen ~10 d historie. Kandidaat (zelf te bouwen, dagafsluiting): MC-waarde om 22:00 in het dagrecord bewaren.
- Geen release (tussenronde, geen acute bug).

laatste ronde: 07-10 23:45, gemeten t/m 07-10 23:44
