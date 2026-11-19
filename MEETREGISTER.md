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
| 1 | Bewaren voor vrijdag 20-11 (plan hield 55-79 % vast): loonde het? | 18-11 | dagcontrole 21-11 | 21-11 | uitkomst melden; voedt nr. 5 |
| 2 | Zonverwachting van het plan per uur (v5.237.0); planvoorspelling liep 10 dagen 9,6 tot 13,5 % te hoog | 17-11 | dagcontrole | 24-11 | uren aanwijzen -> voorstel correctie, of sluiten |
| 3 | Economische schaduw: bewaarmarge 2 ct tegen 0 ct (v5.187.0, 14 dagen vanaf 07-11) | 07-11 | dagcontrole | 21-11 | gelijk aan productie -> schaduw eruit |
| 4 | Prijsverwachting: wat kost een gemiste keuze (v5.236.0) | 16-11 | Claude | 23-11 | onder ~1,5 ct/kWh -> meting blijft als bewaking, geen modelwerk |
| 5 | Eindprijs-toets: aangenomen eindprijs tegen echte (v5.239.0) | 18-11 | Claude | 25-11 | marge-regel houden, bijstellen of terugdraaien |
| 6 | Prijsmodel-variant 'kort' (nu niet gekozen, 4,32 tegen 4,10 ct) | 18-11 | Claude | 09-12 | wint hij niet -> variant eruit |
| 7 | Deed de accu zelf wat het EMS opdroeg (v5.244.0) | 19-11 | Claude | 26-11 | vrijwel 100 % gevolgd -> Zendure lokaal sturen stopt bij stap a; anders stap b voorstellen |
| 8 | Repetitie 2027 met het waardeplan (v5.243.0) | 19-11 | Claude 20-11 (eerste cijfers), dagcontrole | 15-12 | oordeel 'klaar voor 2027' of voorstel; rond 31-12 letten op ontbrekende kale prijs |
| 9 | Schaduw-aanwezigheid in HA (mens binnen) | 19-11 | Claude | 03-12 | omschakelen, bijstellen of opruimen (helper, automatisering, schaduwsensor) |
| 11 | Regelkwaliteit nul op de meter per dag (v5.232.0) | 13-11 | Claude | 27-11 | wijzigingen aan de regeling zijn afgewezen: na twee weken sluiten en de meting eruit, tenzij hij een storing liet zien |
| 13 | Onderzoek: zijn de oude reserve-regels nog nodig als terugval nu het waardeplan stuurt (monte_carlo_vergelijking, lange_horizon_effect, pv_band_calibration en wat eraan hangt) | 19-11 (akkoord Ruud) | Claude | 26-11 | per onderdeel: blijft als terugval, of voorstel om het eruit te halen; eerst aantonen hoe vaak de terugval nog stuurt |
| 12 | Zonverwachting voorzichtiger wegen | gepland | Claude (taak 01-03-2027) | 01-03-2027 | voorstel na de winter |

## Vaste bewaking (blijft, met reden)
| Bewaking | Reden |
|---|---|
| Nieuwe apparaten herkennen (v5.247.0) | accumodule vanzelf in de bewaking; airco en sensoren pas na akkoord; melding per nieuw apparaat |
| Accumodule 1 (01029): celspanningsverschil tegen de andere modules | garantie; melding bij een drempel |
| Zendure lokaal meelezen (v5.50/v5.82) | terugval bij lezen als de Zendure-integratie hapert |
| Opdrachtcontrole (v3.87.0) | melding als de accu een opdracht niet overneemt |
| Dagcontrole: achteraf gemist bedrag, fouten/pech | hoofdmaat of de sturing goed is |
| Planvolging (percentage volgens plan) | laat zien of de accu doet wat het plan zegt |

## Nog te bouwen (toegezegd, geen meting)
| Wat | Stand |
|---|---|
| Ontdekking uitbreiden (Ruud 19-11: 'zeer uitgebreid'): regel 'Nieuw gevonden' in de cockpit; ja/nee in de melding die een voorstel zelf instelt; tweede omvormer, tweede accu en laadpaal herkennen; verdwenen apparaten melden | fase 1 staat (v5.247.0); vervolg nog te bouwen |
| Alinea PENDELEN uit de opdracht van de dagcontrole halen | bij de eerstvolgende aanpassing van die opdracht |

## Afgesloten
| Meting | Uitkomst |
|---|---|
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

Voor er iets uit de code gaat: live nakijken dat het niets voedt, en de tests.
