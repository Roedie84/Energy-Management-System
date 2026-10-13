# Dagafsluiting 12-10 · EMS (ronde gestart 03:40, afgerond 11:30)

Deze ronde kon LEERLOG.md/KPI.csv niet zelf bijwerken: git-netwerkacties (fetch/pull/push) en lokale python werden in deze sessie door de toestemmingscontrole geweigerd. De metingen staan daarom hier; de volgende ronde neemt ze over in KPI.csv (type DAG, datum 2026-10-12) en LEERLOG.md, en verwijdert dit bestand.

## KPI's dag 12-10 (gemeten, HA-statistiek)
- ems_pv_kwh 11.752 (Modbus solaredge_i1_ac_energy)
- ems_pv_afwijking_pct −7.9 tegen day-ahead tracker 12.76 kWh; bewolking 17,8 % (heldere dag, weer te hoog)
- ems_pv_mae_30d_pct 10.5 (bias −7.9); 14 d 9.4 (bias −7.4); 7 d 14.9 (bias −11.8, incl. 09-10 −48)
- PV-bias naar bewolking (30 d, deviation_context): helder < 25 % n=10 gem −6.1 / mediaan −7.1; bewolkt > 85 % n=15 gem −11.5 / mediaan −6.1 → mediaan gelijk; H-EMS-2 = algemene overschatting ~6-7 %, niet bewolkingsafhankelijk (gemiddelde bewolkt gedragen door 09-10 −48)
- ems_net_import_kwh 1.018 · ems_net_export_kwh 4.003 (avondverkoop ~1.46 kWh, rest PV-overschot bij volle accu 14-17 u + regelruis)
- ems_accu_laden_kwh 6.721 · ems_accu_ontladen_kwh 6.129 (solarflow aggr) · ems_huisverbruik_kwh 8.175
- ems_verkoop_onder_reserve 0 (n=5 echte verkoopkwartieren 18:45-19:30 en 20:45; kleinste marges +0.33/+0.006/−0.02 binnen SoC-stap/+0.028/+0.016; zie tussenrondes)
- ems_herstarts 24 (03:33, 06:14, 06:47, 7× 08:26-10:53, 12:38-15:43 6×, 16:12, 18:35, 21:10-23:17 6×)
- ems_tekort_nacht_kwh 0 (nacht 12→13: 13-10 11:14 accu 28 %, beschikbaar 1.56 kWh, blok 12:15 → geen tekort); MC 22u 0 % → Brier 0, n=4
- ems_besparing_zonder_accu_eur 0.06 (sensor 23:57; 11-10 1.09, 10-10 1.06)
- ems_nabeschouwing 12-10: accu leverde € 1.31 van € 1.42 haalbaar (gemist 0.11, alles reserve); 7 d (06..12-10) € 5.10 van € 7.30 = 70 % (11-10: 48 %), gemist € 2.18; netarbitrage 12-10 € 0.04
- per dagdeel 12-10: ochtendpiek +1.29 € verschil (2.79 kWh vastgehouden, optimum had 3.0 kWh ontladen), avondpiek +0.85 (3.31 vastgehouden), nacht −0.50 (1.43 kWh "te veel ontladen" t.o.v. optimum 0)
- reserve_sprongen_aantal 0 sinds v5.94.0-herstart (avond 12-10: 0 echte sprongen, 1 herstartartefact 23:18)

## Geleerd / hypotheses
- H-EMS-2 (PV te hoog): 30 d bias −7.9 %, ook op heldere dagen (11-10 −17, 12-10 −8). Niet bewolkingsgebonden. Als het 14-d-beeld zo blijft → voorstel: day-ahead × (1 − mediaanbias) in planning (sturing → Ruud beslist). Nog geen voorstel (wacht op 3 extra dagen).
- H-EMS-10 (springende reserve): 1 avond met meetbaarheid, 0 sprongen → bijna gesloten; nog 2 avonden.
- Nieuw H-EMS-11: ochtendpiek houdt structureel accu vast (12-10 2.79 kWh, € 1.29 verschil) — nabeschouwing per dagdeel; toetsen over 7 dagen per_dagdeel zodra die reeks er is (v5.89+).

## Gebouwd / status voorstellen
- L-EMS-022 en L-EMS-023: gebouwd door de chatsessie in v5.94.0 (13-10 07:23), actief (diagnose_gezondheid meldt v5.94.0). Deze ronde had dezelfde punten ook gebouwd (branch leer-5.94, niet gepusht: push geweigerd) → vervallen; v5.94.0 is leidend.
- L-EMS-020-aanvulling (sprong na herstart markeren, `na_herstart`, niet tellen) zit NIET in v5.94.0 → blijft gepland (zelf bouwen: meetfout), volgende dagafsluiting. Werkende implementatie + test lag klaar (`_eerste_ronde_na_start` in `_begin_ronde_cache`, vergelijken met `oud["ronde"]`).
- Geen release door deze ronde.

laatste ronde: 13-10 11:30 (dagafsluiting 12-10), gemeten t/m 13-10 11:15
