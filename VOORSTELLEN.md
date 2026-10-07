# Voorstellen Energy Management System

Status: open / akkoord / afgewezen / gebouwd vX / geverifieerd / teruggedraaid. Ruud keurt goed via de chat ("akkoord L-EMS-00x").

## L-EMS-001 · nachtlek naar het net meetellen in de nachtbehoefte (of het P1-doel 's nachts op 0)
- Status: **open** (raakt reserve/sturing → Ruud beslist)
- Onderbouwing: 28-09..07-10, n=50 nachturen met accu-ontlading: mediaan 60 Wh/u teruglevering (P1 ≈ −50 W in smart-modus). Het geleerde nachtverbruik meet huisverbruik (p1+accu+pv) en mist deze ~50 W. Over een ontlaadvenster van 10-16 u is dat 0,5-0,8 kWh/nacht; tekortnachten waren 0,68-1,88 kWh.
- Voorstel (één van twee): (a) gemeten nachtlek (W, mediaan 7 nachten) optellen bij de nachtbehoefte in reserve/Monte Carlo; of (b) in nachtkwartieren zonder verkoopbesluit het terugleverdoel van zendure-ha op 0 W (raakt externe configuratie).
- Verwacht effect: minder planning-tekortnachten; ~0,4-0,8 kWh/nacht niet meer goedkoop weg en duur terug.
- Meten na bouw: nacht-export 00-07 (KPI ems_nacht_export_00_07_kwh) en tekort-kWh per nacht, 7 nachten voor/na.
- Zelf te bouwen zonder akkoord (meetbaarheid): diagnose-attribuut "nachtlek_w" (gemeten teruglevering tijdens accu-ontlading per nacht). Gepland voor een dagafsluiting.
