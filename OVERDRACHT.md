# Overdracht EMS — stand 19 augustus 2026

## Wat dit is
Custom Home Assistant integratie voor een Zendure SolarFlow 2400 AC accu
met SolarEdge PV, Solcast voorspelling en Zonneplan kwartierprijzen.
Locatie Lochem. Communicatie in het Nederlands, terse stijl.

- Repo: https://github.com/Roedie84/Energy-Management-System
- Lokaal: `/home/claude/ems/`
- **Huidige versie: v3.34.0**, 2639 tests groen
- Zip: `/mnt/user-data/outputs/energy_management_system_v3.34.0.zip`

## Werkwijze (belangrijk)
1. Diagnostiek-export lezen uit `/mnt/user-data/uploads/`
2. Fout **narekenen** met de echte cijfers voordat er iets verandert
3. Test schrijven die de fout vangt, dan pas repareren
4. Toetsen dat de test omvalt bij de oude code
5. Versie ophogen in manifest, README (versie + testaantal) en dashboard
6. Changelog met de gemelde klacht letterlijk erin
7. Volledige suite groen, dan zippen

**Valkuil**: versie ophogen met `sed` op de oude waarde faalt stilzwijgend
als die waarde niet klopt. Vier opleveringen zijn zo misgegaan (v3.4.1).
Er staan nu tests op consistentie tussen manifest, README en changelog.

---

## OPENSTAAND — met voorrang

### 1. Visueel-pagina toont platte tekst — OPGELOST in v3.26.0
Oorzaak nagelezen in de bron van de Home Assistant frontend:
`hui-markdown-card.ts` rendert `<ha-markdown cache breaks>` **zonder**
`allow-svg`, en die eigenschap staat standaard op `false`. De opschoner
draait daardoor met de gewone witte lijst, die geen enkel SVG-element
kent — ook `<svg>` zelf niet. Alles wat er niet op staat wordt naar
tekst ontsnapt. Gecontroleerd op alle tags vanaf 20230802.0: `allow-svg`
heeft daar nooit gestaan.

Zelfs mét die vlag zou het niet gaan: de SVG-lijst is `svg` (xmlns,
height, width), `path` (transform, stroke, d) en `img` (src). Geen
`viewBox`, `rect`, `text`, `circle`, `line`, `g`, `tspan`, `polygon`.

Reparatie: de plaat gaat als base64 data-URI door een `<img>`, want die
staat wél op de gewone lijst en `safeAttrValue` laat `data:image/`
uitdrukkelijk toe. De SVG-wortel krijgt een echte maat uit de `viewBox`
in plaats van `width="100%"`.

Nagerekend door de kaartinhoud door marked 18 + xss 1.0.15 te halen met
de configuratie van `markdown-worker.ts`: oud 123 ontsnapte tags en nul
afbeeldingen, nieuw nul ontsnapte tags en één `<img>`.

**Nog te bevestigen door de gebruiker**: staat de plaat er na een
herstart? Het dashboard hoeft niet opnieuw geïmporteerd te worden — de
YAML is niet veranderd, alleen de inhoud van het sensorattribuut.

### 2. Accukoeling — OPGELOST in v3.26.1
Het pendelen was al voorbij: de twintig regels in de schakel-
geschiedenis zijn van vóór v3.14.0 (élke "uit" onder de 32 graden zonder
dat de goedkope koeling werd ontzien). Laatste schakeling 18 augustus
21:15, export elf uur later, niets ertussen.

Nieuw probleem dat daaruit kwam: hij ging ook nooit meer uit. Drempel 25
betekent ondergrens 20, en de accu staat 's nachts op 23. Sinds v3.26.1
stopt hij als de accu onder de aanzetdrempel staat én er minder dan
300 W doorheen gaat, met twee uur wachttijd voor het opnieuw aanzetten
bij een stille accu.

**Nog te bevestigen**: schakelgeschiedenis van een hele dag onder
v3.26.1. Verwacht: vier uitschakelingen in plaats van tien, en 's nachts
uit.

### 3. Netlading — vals alarm, opgelost in v3.26.1
`netlading_vandaag_kwh` stond niet op `None` maar zat helemaal niet in
de export. Diagnostics schreef alleen de samenvatting weg. De rauwe
tellers staan er nu bij. Of de meting echt werkt is pas te zien op een
dag waarop er van het net geladen is.

### 4. Module 1 celspreiding
Opgelopen deze week: 0,190 → 0,230 → 0,260 → 0,350 → 0,340 → **0,460** V.
Op 19 aug 08:46: cel_min 2,72 tegen cel_max 3,18 bij 12% laadstand,
modules 2 en 3 op 0,00 en 0,01. De integratie waarschuwt zelf.

De gebruiker draait nu een kalibratie (5% → 100% met 2000 W). De
momentopname bij 99% uit v3.27.0 is het bewijsstuk: zakt de spreiding
bovenin mee naar nul dan was het balanceerachterstand, blijft hij staan
dan is het een zwakke cel. Niet nóg een keer naar 5% zolang dit loopt.
Alleen module 1; 2 en 3 staan op 0,00. Bij structureel patroon: Zendure
melden met de reeks als bewijs.

---

## Recent opgeleverd (18 augustus)

| Versie | Wat |
|---|---|
| v3.13.0 | winterguard vergat de slijtage — laadde tegen verlies |
| v3.14.0 | hysterese goedkope koeling |
| v3.15.0 | koelen = bescherming: draait door in leermodus/handmatig boven 35 °C |
| v3.16.0 | zelfvoorziening: netlading telt niet als huisverbruik |
| v3.17.0–3.25.4 | visuele plaat in SCADA-stijl (zie openstaand punt 1) |
| v3.23.1 | zelfvoorziening begrensd 0–100 zonder afhankelijke teller |
| v3.24.0 | bijkoop-kandidaat meet ook bij dreigend tekort |
| v3.25.0 | werkelijke netlading per ronde gemeten en afgerekend |
| v3.26.0 | plaat als afbeelding: markdown-kaart ontsnapt élk SVG-element |
| v3.26.1 | koeling stopt bij stille accu; netlading-tellers in de export |
| v3.27.0 | kalibratiestand: sturing eruit, koeling erin, leren gepauzeerd |
| v3.27.1 | kritieke melding zodra de accu vol is in kalibratiestand |
| v3.27.2 | kalibratiekaart wees naar een entiteit-id zonder gebiedsvoorvoegsel |
| v3.27.3 | uitleg kende de kalibratie niet; koeling nu ook los van leermodus |
| v3.28.0 | zonbias mediaan i.p.v. gemiddelde; duiding spreiding vs verschuiving |
| v3.29.0 | volledige doorlichting: slijtage, kostenkolom, dagreeks, marge |
| v3.30.0 | knop om de verbruiksleer opnieuw te beginnen, met bevestiging |
| v3.30.1 | reset wist ook de lopende dag, dus het tijdstip doet er niet toe |
| v3.31.0 | diagnostiek-export 54% kleiner zonder verlies aan inhoud |
| v3.32.0 | dagreeks vult eigen gaten; structuurscan op argumentaantallen |

## Proefstand (9 kandidaten, sturen niets)
- **Slijtagekosten** 4,22 ct/kWh — klaar om mee te doen
- **Vasthouden voor morgen** −8,0 ct/kWh — klaar, maar wijst de verkeerde
  kant op: bij 0 van de 200 metingen was vasthouden voordeliger
- Prijsvorm — winst onbekend
- Overige zes — meten nog

De gereedheid staat los van het oordeel: "klaar om mee te doen" betekent
becijferd, niet gunstig.

## Structuurscans (uit echte fouten voortgekomen)
1. AST-scan op methoden die niet bestaan
2. AST-scan op variabelen die in die functie niet bestaan (v3.6.1)
3. `@staticmethod` die `self` gebruikt (v3.7.1)
4. Berekend maar nergens gelezen (v3.25.1)
5. Onveilige SVG-elementen in alle platen (v3.25.4)
6. Getters die ruwe SVG naar een markdown-kaart teruggeven (v3.26.0)
7. Schakelaarkaarten met een afwijkend entiteit-voorvoegsel (v3.27.2)
8. Beslisredenen zonder eigen onderbouwing (v3.29.0)
9. Aanroepen met een verkeerd aantal argumenten (v3.32.0)

## Vaste afspraken
- Proefstandkandidaten sturen pas na bewijs, één tegelijk
- Apparaten niet automatisch starten, alleen melden
- Geen LLM in de integratie voor aansturing
- Hoofdblok winterguard heeft bewust géén rendementstoets
- Saldering eindigt 31-12-2026: dan 19 ct teruglevering tegen 32 ct
  inkoop, en draaien de proefstandcijfers waarschijnlijk om
