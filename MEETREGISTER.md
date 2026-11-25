# EMS-meetregister – wat loopt er aan metingen en wanneer valt het besluit

Opgezet 19-11-2026 op verzoek van Ruud: "vele metingen in het EMS; monitor jij deze allemaal en update je mij wat te doen, zodat het EMS schoon blijft".

**Regels**
- Elke meting die 'alleen meten' is, staat hier met: sinds wanneer, wie kijkt, wanneer het oordeel valt en wat er dan gebeurt.
- Op de besluitdatum krijgt Ruud één van drie uitkomsten: (a) het levert iets op -> voorstel, (b) het levert niets op -> meting stopt en de code gaat er in de volgende release uit, (c) blijft als vaste bewaking (met reden).
- Een meting zonder besluitdatum mag niet: dan is het vaste bewaking en hoort hij in het tweede lijstje.
- Nieuwe meting = nieuwe regel hier, in dezelfde beurt als de release.

## Lopende metingen met een besluitdatum
| # | Meting | Sinds | Wie kijkt | Besluit | Wat er dan gebeurt |
|---|---|---|---|---|---|
| 5 | Eindprijs-toets: aangenomen eindprijs tegen echte (v5.239.0). Stand 24-11: 5 dagen, gemiddeld -1,0 ct. OORDEEL 25-11 (dagcontrole): 6 dagen, gemiddeld -1,84 ct (5 van 6 dagen te laag; 25-11 32,9 tegen 39,0), gemiddeld 2,73 ct ernaast, 1 dag te hoog (20-11 +2,7). De marge-regel (netladen op verwachting weigeren) bijt bij een te lage verwachting niet: in het plan van 25-11 06:45 0 kwartieren geweigerd. Uitkomst: marge-regel HOUDEN. Bijstellen van de eindprijs zelf (+1,8 ct) raakt de sturing en is met 6 dagen niet in euro's te onderbouwen: opnieuw bekijken 09-12 samen met nr. 6 (>= 14 dagen; bias buiten +-1 ct -> naspeling in euro's en eventueel voorstel aan Ruud) | 18-11 | dagcontrole | 09-12 | bias blijft buiten +-1 ct -> naspeling en voorstel; anders vaste bewaking |
| 6 | Prijsmodel-variant 'kort' (nu niet gekozen, 4,32 tegen 4,10 ct) | 18-11 | Claude | 09-12 | wint hij niet -> variant eruit |
| 7 | Deed de accu zelf wat het EMS opdroeg (v5.244.0) | 19-11 | Claude | 26-11 | vrijwel 100 % gevolgd -> Zendure lokaal sturen stopt bij stap a; anders stap b voorstellen. Stand 20-11: 29/31 (93,5 %); beide missers = laden op 93-95 % SoC (afbouw bovenin), dus feitelijk 'kan_niet'. Stand 22-11: 80/80 (100 %) sinds herstart 20-11, 7 onbekend (geen verse eigen lezing). Stand 23-11: nacht 10 gevolgd, 9 niet_gevolgd; alle zichtbare missers laden bij SoC 83-98 % (gemeten 1,29-1,99 kW tegen 1,95-2,4 opgedragen, dalend met SoC = afbouw); totaal 94/103 (91,3 %). Sinds v5.251.0 (23-11, akkoord Ruud) telt laden bij SoC >= 80 % met afbouw (>= 40 % van de opdracht) als kan_niet; de oude tellingen blijven staan, beoordeel 26-11 op de dagen na de herstart. Stand 24-11 (sinds herstart 23-11 ~14:53, v5.251.1): 44 gevolgd, 2 niet_gevolgd (beide laden bij 95 %, 37 en 33 % van de opdracht, net onder de 40 %-grens), 5 kan_niet = 95,7 % Stand 25-11 06:45 (sinds herstart 05:05, v5.258.1): 8 gevolgd, 0 niet = 100 % |
| 8 | Repetitie 2027 met het waardeplan (v5.243.0); eerste dag 19-11: laat EUR 0,03 liggen (5,23 tegen best 5,21); 20-11 t/m 23-11: EUR 0,00 (5 dagen samen 0,03) | 19-11 | dagcontrole | 15-12 | oordeel 'klaar voor 2027' of voorstel; rond 31-12 letten op ontbrekende kale prijs |
| 9 | Schaduw-aanwezigheid in HA (mens binnen) | 19-11 | Claude | 03-12 | omschakelen, bijstellen of opruimen (helper, automatisering, schaduwsensor) |
| 11 | Regelkwaliteit nul op de meter per dag (v5.232.0) | 13-11 | Claude | 27-11 | wijzigingen aan de regeling zijn afgewezen: na twee weken sluiten en de meting eruit, tenzij hij een storing liet zien |
| 13 | Onderzoek: zijn de oude reserve-regels nog nodig als terugval nu het waardeplan stuurt (monte_carlo_vergelijking, lange_horizon_effect, pv_band_calibration en wat eraan hangt; sinds v5.251.0 ook `_reserve_margin_factor` en `_piekverkoop`, die nergens meer worden aangeroepen) | 19-11 (akkoord Ruud) | Claude | 26-11 | per onderdeel: blijft als terugval, of voorstel om het eruit te halen; eerst aantonen hoe vaak de terugval nog stuurt |
| 14 | Laadtoeslag bovenin in het waardeplan (v5.252.0, 24-11; Ruud: "doen wat het beste is"). Uit H-EMS-25 van de dagcontrole: nagemeten over 40 dagen dagverloop (alle kwartieren): rondrit 85 % onder 80 % SoC, 82 % van 80-90 %, 78 % daarboven; ontladen in elke band gelijk. Het plan telt voor het netdeel van een lading +4,5 % stroom vanaf 80 % en nog +3 % vanaf 90 % (WAARDEPLAN_LAADTOESLAG_SOC). DAGCONTROLE: H-EMS-25 is hiermee gebouwd, geen eigen voorstel meer; wel volgen | 24-11 | dagcontrole | 08-12 | komt 'ochtend verkopen, middag bijladen tot vol met verlies' nog voor? Nee -> vaste bewaking en de grenzen bij de volgende rendementsronde opnieuw meten; ja -> grenzen bijstellen |
| 15 | Vermoedelijke ontdooibeurten airco tellen (v5.256.0, 24-11, akkoord Ruud). Geen ontdooisignaal van de Daikin; afgeleid uit compressorfrequentie + temperatuur binnenunit (verwarmt, buiten <= 7 °C, compressor draaide 10 min, binnenunit zakt >= 2 °C binnen 10 min). Gebaseerd op een waarneming (24-11 11:05). Attribuut 'ontdooien' op sensor Airco vermogen (berekend). Alleen meting CLAUDE 25-11: 2 beurten geteld op 24-11 (15:38 bij +2,2 °C en 18:19), beide twijfelachtig (frequentie zakte nauwelijks, 'niet hersteld'): voorwaarden lijken te ruim. | 24-11 | Claude | 08-12 | klopt de herkenning met een door Ruud gezien moment en met de vorstdagen? Ja -> voorstel: ochtendstart bij vorst eerder; nee -> voorwaarden bijstellen of eruit |
| 16 | Kosten van de wijzigingen van 24-11 (Ruud: "goed bijhouden wat goedkoper is en wat de aanpassingen in de accusturing kosten"). (a) AIRCO nieuw regime (sinds 24-11 19:30: 22:00 uit zoals voorheen, werkdag aan om 06:30 tot 21 °C en vasthouden tot 08:00, overdag 21 °C (24-11 20:20; daarvoor die middag 23 en 22), knop iedereen weg; de nacht op 18 °C heeft alleen 24-11 overdag ingesteld gestaan en nooit een nacht gedraaid). Nulmeting 09-23/11 (14 dagen, zonder 20-11): 6,3 kWh/dag, 0,45 kWh per graad verschil (daggemiddelde woonkamer min buiten), woonkamer gemiddeld 18,5 °C; ca. EUR 2,50/dag bij ~40 ct. Bron: statistiek sensor.woonkamer_compressor_energy_consumption (change per dag), sensor.ultimatesensor_scd41_temperature, sensor.stormchase_meting_weerstation. Per dag noteren: kWh, kWh per graad, gemiddelde woonkamertemperatuur, kosten tegen de uurprijs. (b) ACCU: nulmeting nabeschouwing 12-23/11 (12 dagen): gemist gemiddeld EUR 0,18/dag (som 2,15), accu leverde op EUR 0,43/dag (som 5,18). Vergelijken met de dagen vanaf 25-11 (laadtoeslag v5.252.0 + ander huisverbruik door de airco). DAGCONTROLE: deze cijfers per dag in het eindbericht meenemen CLAUDE 25-11 08:25: 24-11 (overgangsdag) airco 10,8 kWh = 0,55 kWh/graad (18,6 binnen, -1,1 buiten) tegen 0,45 in de nulmeting; 25-11 tot 08:20 2,5 kWh, waarvan 0,8 door de nachtfout en ca. 1,7 de ochtend (06:30-08:20). | 24-11 | Claude + dagcontrole | 01-12 | per onderdeel: goedkoper of duurder dan de nulmeting, in euro per dag en gecorrigeerd voor de buitentemperatuur; duurder zonder comfortwinst -> voorstel terugdraaien of bijstellen STAND 24-11 (dagcontrole): (a) airco 10,8 kWh, 0,55 kWh per graad, woonkamer 18,6 C, buiten -1,1 C, EUR 4,88 tegen de uurprijs (gem. 45,2 ct); overgangsdag (middag 23/22/21 C). 25-11 04:24-04:55 airco aan door een fout in v5.253-v5.258.0 (opgelost v5.258.1, actief 05:05): 0,8 kWh, EUR 0,30; 06:30 werkdagstart zoals ingesteld. (b) accu nabeschouwing 24-11: gemist EUR 0,08, accu leverde EUR 0,22 (dagcontrole-LP 24-11 06:45 t/m 25-11 06:45: gemist EUR 0,13) |
| 12 | Zonverwachting voorzichtiger wegen | gepland | Claude (taak 01-03-2027) | 01-03-2027 | voorstel na de winter |

## Vaste bewaking (blijft, met reden)
| Bewaking | Reden |
|---|---|
| Zonverwachting van het plan per uur (v5.237.0, uit nr. 2) | 24-11: geen correctie nodig; nr. 12 (01-03-2027) gebruikt de uurcijfers |
| Tweede prijsbron EnergyZero (v5.251.0) | reserve bij een storing van Zonneplan; opslag geleerd uit de laatste 672 kwartieren; status in get_prijsbron.reserve en de diagnose. 24-11 nagekeken: 96 geleerde kwartieren, opslag 13,1 ct incl., fout null |
| Bedradingstoets (v5.251.0) | elke functie moet in de integratie gebruikt worden, elke bewaakte meting een aangeroepen vuller hebben (vond eigen_ingrepen en de logopvang; reden_afwijkingen in v5.250.1) |
| Nieuwe apparaten herkennen (v5.247.0) | accumodule vanzelf in de bewaking; airco en sensoren pas na akkoord; melding per nieuw apparaat |
| Accumodule 1 (01029): celspanningsverschil tegen de andere modules | garantie; melding bij een drempel |
| Zendure lokaal meelezen (v5.50/v5.82) | terugval bij lezen als de Zendure-integratie hapert |
| Opdrachtcontrole (v3.87.0) | melding als de accu een opdracht niet overneemt |
| Dagcontrole: achteraf gemist bedrag, fouten/pech | hoofdmaat of de sturing goed is |
| Planvolging (percentage volgens plan) | laat zien of de accu doet wat het plan zegt |
| Prijsverwachting: gemiste keuze (v5.236.0) | 23-11 uit nr. 4: kost minder dan 1,5 ct/kWh; blijft zichtbaar om een slechtere periode te zien |

## Nog te bouwen (toegezegd, geen meting)
| Wat | Stand |
|---|---|
| Ontdekking van nieuwe apparaten (Ruud 19-11: 'zeer uitgebreid') | COMPLEET: v5.247.0 (basis), v5.248.0 (cockpit, omvormer/accu/laadpaal, verdwenen), v5.249.0 (knoppen in de melding). Na de herstart de eerste ronde nakijken; de knoppen zijn nog niet met een echte melding geprobeerd |
| Alinea PENDELEN uit de opdracht van de dagcontrole halen | bij de eerstvolgende aanpassing van die opdracht |

## Afgesloten
| Meting | Uitkomst |
|---|---|
| Zonverwachting van het plan per uur (nr. 2) | 24-11: 6 dagen per uur (18-23/11): 10 u +100 % (+0,30 kWh/dag te laag voorspeld), 9 u +25 %, 13 u +17 %, 8 u -45 %, 15 u -23 %; dagtotaal 10 dagen -3 % (was 9,6-13,5 % te hoog bij de start). Onder saldering geen euro-effect: de zon om 10 u wordt teruggeleverd op 42-46 ct en het plan laadt pas vanaf 11 u bij. Geen correctie; vaste bewaking omdat nr. 12 de uurcijfers nodig heeft |
| Economische schaduw 2 ct / 0 ct (nr. 3) | 21-11: 2 ct kostte € 0,69 in 14 dagen. 23-11 (akkoord Ruud) uit de code in v5.251.0, ook het cockpit-tabblad Schaduw. 24-11: entiteiten zijn weg |
| Eindwaarde begrenzen op de bijlaadkosten van de nacht (23-11) | narekening over 125 dagen echte prijzen: de begrenzing bijt 6 keer, bovengrens € 0,46 in totaal; niet gebouwd. De afwijking van de prijsverwachting zelf volgt uit nr. 5 |
| reden_afwijkingen kreeg nooit iets (cockpit 23-11) | fout sinds v4.22: de nabeschouwing gaf de acties niet door. Opgelost in v5.250.1; de melding verdwijnt na de eerste dagwissel na de herstart |
| Prijsverwachting: wat kost een gemiste keuze (nr. 4) | 23-11: goedkoopste meerprijs d1 live 1,44 ct (35 dagen; laatste 7 dagen 0,32), duurste gemist 0,80 ct; terugtoets 21 d 2,2/0,85. Onder de grens van ~1,5 ct: vaste bewaking (attributen nauwkeurigheid_live/backtest_21_dagen blijven), geen modelwerk |
| Bewaren voor vrijdag 20-11 (nr. 1) | 21-11: bewaren 18-11 avond (38,1 ct) en verkopen 19-11 (43,4 ct) loonde, ca. € 0,30; vasthouden voor 20-11 terecht losgelaten (verwachting piek 49,6, werkelijk 44,1). Prijsverwachting te hoog: meegenomen in nr. 5 |
| P1-regeldoel factor 0,5 (pendelen na een lastsprong) | weekoordeel dagcontrole 18-11: regeloverschot 0,003-0,015 kWh per kwartier tegen 0,045 bij de nulmeting (65 tot 95 % minder), nulregeling niet trager; factor houden. Uitdoven na een sprong niet gemeten. Ruud 19-11: de dagelijkse pendelmeting stopt. DAGCONTROLE: de alinea 'PENDELEN VAN DE ACCUREGELING' in de opdracht niet meer uitvoeren, geen KPI-regels p1_pendel_wh_dag / ems_regeloverschot_huis_kwh_per_kw meer en 'pendelenergie gisteren' niet meer in het eindbericht. De code (pendel_wh_gisteren op de sensor P1 regeldoel) staat er nog: bij de volgende opruimronde nagaan of iets hem leest |
| Ontlaadrendement een week (H-EMS-23) | 19-11: 99,2 % tegen ~101 % in het plan, onder de grens; geen wijziging |
| Vervolgmeting accuplan 12 t/m 18-11 | 19-11: 89 % van het optimum; geen voorstel |
| Uitvalproef accu (wat doet hij zonder HA) | 19-11 door Ruud achterwege gelaten; 64 s gemeten: houdt het laatste vermogen vast |
| Opruimronde HA | 19-11: vrijwel niets op te ruimen |

## Nagelopen 19-11 (uit de code beoordeeld, niet uit live cijfers)
| Onderdeel | Wat het is | Oordeel |
|---|---|---|
| `soc_demper` | dempt het flapperen van de beschikbare energie bij 0 W (v5.172.0) | telt mee in de meting waarop gestuurd wordt: blijft |
| `spiegelcontrole` | vergelijkt eigen getallen met de bron (v3.49.0) | vaste bewaking: blijft |
| `herspeel` | speelt dagen na per EMS-versie, voedt de zelfanalyse | vaste bewaking: blijft |
| `extra_dip_margin` | marge uit de oude regelset bij weinig zon | hoort bij de terugval als het waardeplan er niet uitkomt: blijft zolang de terugval blijft |
| `powercalc_proef` | proef uit v3.97: maakt Powercalc de apparaatherkenning rustiger | VERWIJDERD in v5.245.0 (19-11): niets gebruikte de uitkomst |
| `gacs_assessment` | zelfbeoordeling tegen GACS-eisen; geldt volgens de eigen toelichting niet voor een woning | v5.246.0 (19-11): de spiegel langs de vier eisen is VERWIJDERD (las niets). De sensor 'GACS-zelfbeoordeling' blijft: hij draagt de gegevens van de cockpit (waarom nu, verkooptoets, reservemarge, zon) en de verbetermogelijkheden; alleen de naam is historisch |
| `weather_source_reliability` | betrouwbaarheid per weerbron; sinds 29-10 is er nog maar een weerbron | NIET ongebruikt (eerdere inschatting was fout): op 7 plekken in gebruik, o.a. bij het wegen van de weerbron en een melding. Blijft |
| `monte_carlo_vergelijking`, `lange_horizon_effect`, `pv_band_calibration` | rapportage rond de oude reserve-regels (tekortkans, lange horizon, onderkant Solcast) | een besluit samen: zijn de oude reserve-regels nog nodig als terugval nu het waardeplan stuurt? Apart en voorzichtig uitzoeken |
| `safe_sell_shadow` | verkoopschaduw in het terugvalpad (v4.22); in het meetregister van stilstand met 60 dagen | wordt alleen gevuld als de oude regels sturen; hoort bij nr. 13 |

Voor er iets uit de code gaat: live nakijken dat het niets voedt, en de tests.
