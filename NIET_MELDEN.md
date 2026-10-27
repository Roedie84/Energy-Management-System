# Niet meer melden (kopie van claude/HA-basis.md in het claude.ai-project 'Home Assistant')
# Bron is HA-basis.md; deze kopie wordt bij elke wijziging bijgewerkt.

## Niet meer melden
Enige bron voor alle geplande taken (stand 27-10). Live HA-staat gaat voor: is iets hieronder inmiddels anders, dan dat wel melden. Nieuwe besluiten "niet melden" komen alleen hier.
- Nabu Casa-verloop (verlengt automatisch).
- Offline Zigbee-contactsensoren: raamsensoren slaapkamer Jill/RM en 3× 0xa4c138… (0xa4c138000826cd53, 0xa4c138859e6a36f4, 0xa4c138e8ab4ebcde); beweging looppad schuur offline (bekend).
- Lampen light.ledstrips_speelkamer_2 en light.lamp_zolder_waskant_2 offline.
- Tijdelijke Home Connect- en Solcast-limieten; onbeschikbare Home Connect-bedieningsentiteiten.
- Gedeeld wachtwoord MariaDB/MQTT/Eufy (wordt niet aangepast).
- Oude SolarEdge API-key; poort 8123 in de router.
- switch.zendure_batterij in setup_retry.
- Schakelslot op vaatwasser-, wasmachine-, koffie- en zendure-stekker (relais onbeschikbaar is bewust).
- Zolderraam waskant staat altijd open; Twinkly buiten het seizoen; automation.ontvochtiger_zolder uit.
- Dashboards 'Test' en 'Tablet Test' (bekend, wordt apart afgeslankt); Alexa niet gekoppeld.
- HomeWizard-stekkers (terugroepactie, gaan retour); accumodule 00996 gaat terug.
- Backups ~3,8 GB (bewust); Ruud verwijdert zelf oude backups.
- Uitgeschakelde "Voorstel Claude"-automations.
- IPTV-stekker 's nachts uit en Sonos/luchtbevochtiger-stekker 23-07 uit (bewust, automations).
- Batterij gang (vervangen).
- Gebruikers/MFA/tokens controleren en een tweede DNS-server (Ruud sloeg beide over, 27-10).
- Mosquitto 1883 onversleuteld op het LAN (bewust).
- Matter Server automatisch bijwerken uit (bewust; watchdog staat aan).
- zendure_ha-deprecations (HA 2027.8): alleen melden als de maker een update uitbrengt.
- Airco woonkamer: laatste uren van de dag ontbreken in de Daikin-telling (geaccepteerd).
- Afname-euro's in het energiedashboard via P1 + kwartierprijs, niet via Zonneplan-cloud (bewust); gas en teruglevering wel via Zonneplan.
- Geparkeerde opschoononderwerpen: zithoek (lux/PIR), HOBEIAN-sensoren, ab3000_* hernoemen; lege dubbele apparaten (HACS, HomeWizard, samsungtv, GA-HUM240.DW).
- Recorder-exclude niet als algemene tip melden (alleen nieuwe, concrete kandidaten); de verwijderde brievenbus.
- HA-herstarts door HACS-updates.

