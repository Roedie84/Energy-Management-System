"""Klimaat en airco van de coordinator: de lijm rond de airco-modules (B4.6).

De airco-voorspelling en zijn leren, de buitentemperatuur (achtertuin,
live), het klimaattempo (zon, wind, rolluiken), de klimaatprojectie en
-verwachting, de airco-ronde met het ritme (ochtend, thuiskomst, zon,
buffer) en het zaaien van de airco-leerdata. Het rekenwerk staat in
`airco_sturing.py`, `airco_ritme.py`, `klimaat_zon.py` en `klimaat_wind.py`.
Ongewijzigd verhuisd uit `coordinator.py`; de coordinator erft deze mixin.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from . import airco_frequentie, airco_ritme, airco_sturing, klimaat_wind, klimaat_zon
from .const import (
    AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE,
    AIRCO_ACTIVE_HVAC_ACTIONS,
    AIRCO_LEER_VERSIE,
    AIRCO_PREDICTION_HISTORY_LENGTH,
    AIRCO_PREDICTION_LOOKAHEAD_MINUTES,
    AIRCO_PREDICTION_MIN_SAMPLES,
    AIRCO_RAAM_UITSTEL_S,
    AIRCO_ZON_DOEL_C,
    AIRCO_ZON_MINUTEN,
    AIRCO_ZON_MIN_OVERSCHOT_W,
    AIRCO_ZON_ONDER_C,
    BACKYARD_SUN_EXPOSURE_HISTORY_LENGTH,
    BACKYARD_SUN_EXPOSURE_MARGIN_DEGREES,
    BACKYARD_SUN_EXPOSURE_MIN_SAMPLES,
    BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR,
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES,
    BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN,
    BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C,
    BACKYARD_TEMP_SPIKE_TOLERANCE_C,
    CLIMATE_FORECAST_BIAS_HISTORY_LENGTH,
    CLIMATE_FORECAST_BIAS_MIN_SAMPLES,
    CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES,
    CLIMATE_FORECAST_HORIZON_HOURS,
    CLIMATE_RATE_HISTORY_LENGTH,
    CLIMATE_RATE_MAX_EXTRAPOLATIE_C,
    CLIMATE_RATE_MAX_INTERVAL_HOURS,
    CLIMATE_RATE_MIN_INTERVAL_HOURS,
    CLIMATE_RATE_MIN_SAMPLES,
    CLIMATE_RATE_NEIGHBOUR_BUCKETS,
    CLIMATE_RATE_NEUTRAL_C_PER_HOUR,
    CLIMATE_RATE_RELIABLE_SAMPLES,
    CONF_AIRCO_CLIMATE_ENTITY,
    CONF_AIRCO_POWER_SENSOR,
    CONF_AIRCO_RAAM_ENTITIES,
    CONF_AIRCO_COP_BIJ_7C,
    CONF_AIRCO_COP_PER_GRAAD,
    CONF_AIRCO_EXTERN_ENTITY,
    CONF_AIRCO_UIT_OM,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_KNMI_WEATHER_ENTITY,
    CONF_LIVING_ROOM_HUMIDITY_SENSOR,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_1,
    CONF_LIVING_ROOM_SHUTTER_ENTITY_2,
    CONF_LIVING_ROOM_TEMPERATURE_SENSOR,
    CONF_OPENWEATHERMAP_WEATHER_ENTITY,
    CONF_PV_POWER_SENSOR,
    CONF_SLAAPKAMER_CLIMATE_ENTITY,
    DEFAULT_AIRCO_COP_PER_GRAAD,
    DEFAULT_AIRCO_UIT_OM,
    DOMAIN,
    LIVING_ROOM_TEMP_BUCKET_SIZE_C,
    OUTDOOR_TEMP_BUCKET_SIZE_C,
    PRESENCE_MIN_OBSERVATIONS,
    PRICE_SCALE_FACTOR,
    WEER_OPNIEUW_MINUTEN,
    WOONKAMERTEMP_MIN_UREN,
    WOONKAMERTEMP_UREN,
)
from .tijdtekst import tijd_met_dag

# Zelfde loggernaam als voorheen, zodat logger-instellingen in HA blijven werken.
_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")



def rolluikstand_procent(toestand, attributen) -> float | None:
    """Stand van een rolluik in procent open (v5.63), of None als onbekend.

    Een gekalibreerd rolluik geeft `current_position`; anders telt "open"
    als 100 en elke andere stand ("closed", "opening", "closing") als 0,
    precies zoals voor v5.63. Onbeschikbaar of onbekend: None.
    """
    if toestand in (None, "unavailable", "unknown", ""):
        return None
    positie = (attributen or {}).get("current_position")
    try:
        if positie is not None:
            p = float(positie)
            if 0 <= p <= 100:
                return p
    except (TypeError, ValueError):
        pass
    return 100.0 if toestand == "open" else 0.0



def rolluiklabel(gemiddelde_procent: float) -> str:
    """Drie klimaatgroepen uit de gemiddelde rolluikstand (v5.63)."""
    if gemiddelde_procent >= 90:
        return "beide_open"
    if gemiddelde_procent <= 10:
        return "beide_dicht"
    return "gedeeltelijk"


class KlimaatMixin:
    """De klimaat- en airco-methodes van de coordinator."""

    @property
    def climate_forecast_learned_bias_c(self) -> float | None:
        """Geleerde bias-correctie (°C, additief) op de uurlijkse
        weersvoorspelling (v0.63.95), gebaseerd op vergelijking met de
        achtertuinsensor. Positief = voorspelling was te laag (de
        achtertuin was warmer dan voorspeld); negatief = voorspelling
        was te hoog. None zolang er nog niet genoeg samples zijn
        (`CLIMATE_FORECAST_BIAS_MIN_SAMPLES`) - een bias uit te weinig
        samples is zelf onbetrouwbaar.
        """
        if len(self.climate_forecast_bias_history) < CLIMATE_FORECAST_BIAS_MIN_SAMPLES:
            return None
        return round(
            sum(self.climate_forecast_bias_history)
            / len(self.climate_forecast_bias_history),
            1,
        )

    def _meet_woonkamertemperatuur(self, now: datetime) -> None:
        """De gemeten woonkamertemperatuur per uur (v4.9).

        Gemeld: de tabel "Woonkamertemperatuur per uur" toont wat de
        projectie voorspelt en niet wat de thermometer aanwees - dan is
        de projectie niet te beoordelen. De mediaan per uur: een deur die
        opengaat mag het uur niet bepalen.
        """
        temp = self._read_sensor_float(
            self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
        )
        if temp is None:
            return
        sleutel = now.strftime("%Y-%m-%dT%H")
        reeks = self._woonkamertemp_monsters.setdefault(sleutel, [])
        reeks.append(temp)
        if len(reeks) > 120:
            del reeks[0]
        self.woonkamertemp_gemeten_per_uur[sleutel] = round(
            statistics.median(reeks), 1
        )
        for oud in sorted(self.woonkamertemp_gemeten_per_uur)[:-WOONKAMERTEMP_UREN]:
            self.woonkamertemp_gemeten_per_uur.pop(oud, None)
            self._woonkamertemp_monsters.pop(oud, None)

    def get_klimaat_projectie_kwaliteit(self) -> dict:
        """Hoe goed is de woonkamerprojectie? (v4.9)

        Dezelfde vraag die de zonvoorspelling al van zichzelf stelt: wat
        was de afwijking op de uren die voorbij zijn?
        """
        regels = [
            r for r in self._traject_met_metingen(self.climate_forecast_trajectory)
            if r.get("afwijking_c") is not None
        ]
        if len(regels) < WOONKAMERTEMP_MIN_UREN:
            return {
                "beschikbaar": False,
                "uren": len(regels),
                "reden": (
                    f"{len(regels)} van de {WOONKAMERTEMP_MIN_UREN} uren met zowel een "
                    "projectie als een meting."
                ),
            }
        afwijkingen = [abs(r["afwijking_c"]) for r in regels]
        gemiddeld = sum(afwijkingen) / len(afwijkingen)
        grootste = max(afwijkingen)
        return {
            "beschikbaar": True,
            "uren": len(regels),
            "gemiddelde_afwijking_c": round(gemiddeld, 2),
            "grootste_afwijking_c": round(grootste, 1),
            "oordeel": (
                f"Gemiddeld {gemiddeld:.1f} °C ernaast over {len(regels)} uren, "
                f"grootste afwijking {grootste:.1f} °C. "
                + (
                    "Dat is nauwkeurig genoeg om op te bouwen."
                    if gemiddeld <= 0.5
                    else "Dat is te grof om op te bouwen; de projectie meet nog."
                )
            ),
            "toelichting": (
                "De afwijking is de projectie min de meting, over de uren die "
                "voorbij zijn. Een positieve afwijking betekent dat de projectie "
                "te warm was."
            ),
        }

    def _airco_draait(self, entity_id: str | None) -> bool:
        """Gebruikt deze airco nu noemenswaardig stroom? (v5.5)

        Hier stond alleen een toets op `hvac_action in {"heating",
        "cooling"}`. Uitgelezen in de ontwikkelaarstools:

            cool + koelend    hvac_action: cooling     gezien
            heat + stokend    hvac_action: heating     gezien
            cool net gestart  hvac_action: idle        compressor stil
            dry               hvac_action ONTBREEKT    NIET gezien

        In ontvochtigingsstand levert deze unit helemaal geen
        `hvac_action`. De herkenning las dan `None` en zag de airco niet,
        terwijl hij wel stroom gebruikt. `drying` toevoegen helpt niet -
        er komt niets.

        Dus: ontbreekt `hvac_action`, kijk dan naar de STAND.
        Ontbrekende informatie is geen bewijs van stilstand. Staat er wel
        een actie, dan is die leidend - `idle` betekent echt dat de
        compressor stilstaat.
        """
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        hvac_action = state.attributes.get("hvac_action")
        if hvac_action is not None:
            return hvac_action in AIRCO_ACTIVE_HVAC_ACTIONS
        return state.state in AIRCO_ACTIEVE_STANDEN_ZONDER_ACTIE

    def _narrate_climate(self) -> str | None:
        """Meldt de klimaat-projectie-status, als die iets te melden
        heeft (bijv. nog niet genoeg data)."""
        if self.climate_forecast_note:
            return self.climate_forecast_note
        if self.climate_forecast_trajectory:
            eerste = self.climate_forecast_trajectory[0]
            return (
                f"De woonkamer wordt over een uur rond de "
                f"{eerste.get('kort_termijn_temp_c')}°C verwacht."
            )
        return None

    def _update_living_room_airco_prediction(self, now: datetime) -> None:
        """Living-room-temperature airco activation predictor
        (v0.63.55, requested: "verwacht wanneer ik de airco aanzet").

        Genuine anticipation, not just "is the airco on right now" -
        uses the same "queue an observation, confirm it later"
        technique already established by `SolarForecastAccuracyTracker`
        (a prediction captured today, compared against tomorrow's
        actual yield): each living-room temperature reading is bucketed
        (LIVING_ROOM_TEMP_BUCKET_SIZE_C; sinds v5.60 halve graden) and queued with a
        deadline `AIRCO_PREDICTION_LOOKAHEAD_MINUTES` (60 min) later.
        Every tick, any still-open queued observation gets marked "seen
        active" the moment the airco is confirmed active (regardless of
        which tick that happens on, as long as it's before the
        deadline) - once the deadline passes, the observation is
        finalised as True/False into that bucket's learned history.

        Deliberately a SHORT, bounded rolling window per bucket
        (AIRCO_PREDICTION_HISTORY_LENGTH = 20 outcomes) rather than an
        ever-growing one - requested: spring/autumn conditions can swing
        day to day, so a bucket's learned probability should track
        recent behaviour, not get diluted by weeks-old data from a
        different regime (e.g. thermostat settings that have since
        changed).

        Humidity is tracked alongside per bucket purely as *context* for
        display (its own rolling average) - not a second bucketing
        dimension, which would fragment the already-limited sample count
        per cell too thinly to ever reach AIRCO_PREDICTION_MIN_SAMPLES.

        v5.58: niet elke meting maar per bakje hooguit één waarneming per
        uur (`_airco_bakje_mag_starten`), zodat de laatste 20 ook 20
        verschillende uren zijn. v5.60: bakje = dichtstbijzijnde halve
        graad, half naar boven (18,8 °C -> 19,0; 19,3 °C -> 19,5).
        """
        temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
        if not temp_entity:
            return
        temp_c = self._read_sensor_float(temp_entity)
        if temp_c is None:
            return
        # v0.63.92, gerapporteerd met screenshot: de live
        # woonkamertemperatuur toonde absurd veel decimalen
        # (24.1230773925781°C) op het dashboard, in tegenstelling tot
        # de buitentemperatuur (die al afgerond binnenkomt via de
        # weerentiteit). De onderliggende temperatuursensor rapporteert
        # zelf met hoge precisie (bijv. een Zigbee-sensor); hier
        # afronden op 1 decimaal, consistent met hoe elke andere
        # temperatuurweergave in deze integratie wordt getoond.
        # v5.60: half naar boven (zie `airco_sturing.een_decimaal`), net als
        # de leerstap, zodat 19,25 °C hier 19,3 wordt en niet 19,2.
        self.living_room_current_temp_c = airco_sturing.een_decimaal(temp_c)

        humidity_entity = self.config.get(CONF_LIVING_ROOM_HUMIDITY_SENSOR)
        humidity_percent = (
            self._read_sensor_float(humidity_entity) if humidity_entity else None
        )
        # v0.63.121, gezien in een diagnostiek-export:
        # 45.9213256835938%. Exact dezelfde klacht die in v0.63.92 voor
        # de TEMPERATUUR werd opgelost ("absurd veel decimalen"), maar
        # de luchtvochtigheid ernaast bleef toen ongemoeid - dezelfde
        # sensor, dezelfde hoge precisie, dus hetzelfde probleem. Hier
        # op 1 decimaal, consistent met elke andere weergave.
        self.living_room_current_humidity_percent = (
            round(humidity_percent, 1) if humidity_percent is not None else None
        )

        # v5.58/v5.60: half naar boven, vanaf de getoonde waarde (één
        # decimaal), per halve graad - 18,8 °C hoort bij bakje 19,0 en
        # 19,3 °C bij 19,5. Zie `airco_sturing.temperatuurbakje`.
        bucket_key = airco_sturing.temperatuurbakje(
            temp_c, LIVING_ROOM_TEMP_BUCKET_SIZE_C
        )

        # v5.98.0, gemeld: "EMS moet voor inschakelen airco alleen kijken
        # wanneer deze wordt aangezet." Klopt. Hier telde het vermogen
        # (`last_heavy_load_source`): stond de airco op 21 °C en sloeg de
        # compressor even af, dan startte er een waarneming, en sloeg hij
        # weer aan, dan telde dat als "aangezet" - de thermostaat, niet
        # jullie. Op 14-10 stond hij 18:38-22:00 onafgebroken op "heat",
        # met tientallen keren aan/af. Nu telt de stand van de climate-
        # entiteit (uit -> aan); zonder entiteit blijft het vermogen gelden.
        ingeschakeld = self._airco_ingeschakeld()
        # v5.99.4: is de climate-entiteit ingesteld maar even onbeschikbaar
        # (de Daikin-units vallen geregeld 2 minuten weg), dan deze ronde
        # overslaan. Anders viel de stand terug op het vermogen: een airco
        # die op "heat" stond met de compressor even af telde als uit, er
        # startte een waarneming, en na het herstel telde hij als aangezet.
        if ingeschakeld is None and self.config.get(CONF_AIRCO_CLIMATE_ENTITY):
            return
        airco_active_now = (
            ingeschakeld if ingeschakeld is not None
            else self.last_heavy_load_source == "airco"
        )

        # v5.63.1: open waarnemingen van vóór een herstart terugzetten.
        self._herstel_airco_waarnemingen(now)

        # Mark every still-open pending observation "seen active" if the
        # airco is active on this tick - a queued observation from any
        # earlier tick (as long as its deadline hasn't passed yet) counts.
        if airco_active_now:
            # v1.18.1, gevraagd: "Werkt het airco-voorspellingsmechanisme
            # ook in de winter (dus bij te koude temperaturen)?"
            #
            # Ja: de bins zijn richtingsneutraal en
            # AIRCO_ACTIVE_HVAC_ACTIONS bevat zowel "heating" als
            # "cooling". Bij 18 °C leert hij dus verwarmen, bij 26 °C
            # koelen.
            #
            # Maar de RICHTING werd niet bewaard, terwijl dat twee
            # tegengestelde acties zijn: "60% kans dat de airco aangaat"
            # betekent iets heel anders bij 18 dan bij 26 graden. Nu
            # wordt per bin bijgehouden wat er gebeurde.
            # v5.64: zette het EMS hem aan (ook vooruit, op de projectie),
            # dan is dat geen keuze van jullie - niet meetellen. Anders leert
            # het EMS van zichzelf en schuift de aanzettemperatuur op.
            if self.airco_door_ems:
                self._temp_prediction_pending = []
            richting = self._airco_richting_stand() or self.climate_airco_state
            for pending in self._temp_prediction_pending:
                pending["airco_seen_active"] = True
                if richting in ("verwarmen", "koelen"):
                    pending["airco_richting"] = richting

        # Finalise anything whose lookahead window has now elapsed.
        still_pending = []
        for pending in self._temp_prediction_pending:
            if now >= pending["deadline"]:
                history = self.living_room_temp_bucket_history.setdefault(
                    pending["bucket"], []
                )
                history.append(pending["airco_seen_active"])
                richting = pending.get("airco_richting")
                if richting:
                    richtingen = self.living_room_temp_bucket_direction.setdefault(
                        pending["bucket"], []
                    )
                    richtingen.append(richting)
                    self.living_room_temp_bucket_direction[pending["bucket"]] = (
                        richtingen[-AIRCO_PREDICTION_HISTORY_LENGTH:]
                    )
                self.living_room_temp_bucket_history[pending["bucket"]] = history[
                    -AIRCO_PREDICTION_HISTORY_LENGTH:
                ]
            else:
                still_pending.append(pending)
        self._temp_prediction_pending = still_pending

        # v5.13: alleen een waarneming starten als de airco UIT staat. De
        # vraag is "gaat hij aan?", en die bestaat niet meer zodra hij al
        # draait. Hier werd elke ronde een waarneming gestart, en stond de
        # airco al aan, dan kreeg die meteen het label "aan" - bij de
        # temperatuur die de airco zelf had veroorzaakt. Koelen van 25
        # naar 21 °C leerde zo dat je bij 21 °C aanzet.
        #
        # v5.58: en per bakje hooguit één per uur. Elke ronde (elke minuut)
        # startte er een, dus "de laatste 20" in een bakje waren ~20
        # opeenvolgende minuten van één middag - geen 20 losse momenten,
        # en niets dat "meebeweegt met het seizoen". Nu alleen als er voor
        # dit bakje geen waarneming meer open staat én de vorige start in
        # dit bakje minstens AIRCO_PREDICTION_LOOKAHEAD_MINUTES geleden is.
        if not airco_active_now and self._airco_bakje_mag_starten(bucket_key, now):
            self._temp_prediction_pending.append(
                {
                    "bucket": bucket_key,
                    "deadline": now
                    + timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES),
                    "airco_seen_active": False,
                }
            )
            self.airco_bakje_laatste_start[bucket_key] = now.isoformat()
            # v5.58: de luchtvochtigheid ook één keer per waarneming, niet
            # per ronde.
            if humidity_percent is not None:
                humidity_history = self.living_room_temp_bucket_humidity.setdefault(
                    bucket_key, []
                )
                humidity_history.append(round(humidity_percent, 1))
                self.living_room_temp_bucket_humidity[bucket_key] = humidity_history[
                    -AIRCO_PREDICTION_HISTORY_LENGTH:
                ]
        self._bewaar_airco_waarnemingen()

    def _herstel_airco_waarnemingen(self, now: datetime) -> None:
        """Zet de open airco-waarnemingen van vóór een herstart terug (v5.63.1).

        Gemeld: "vanmiddag is de airco bij 18,8 aangegaan" en dat stond
        nergens. De open waarnemingen (wacht een uur of de airco aangaat)
        stonden alleen in het geheugen. Een herstart binnen dat uur - op
        09-10 gebeurde dat vijf keer - gooide ze weg, terwijl de starttijd
        per bakje wél bewaard bleef en een nieuwe waarneming in dat bakje
        nog een uur tegenhield. De aanzet om 14:26 viel zo tussen wal en
        schip.

        Nu bewaard (`airco_open_waarnemingen`) en bij de eerste ronde terug:
        - deadline nog niet voorbij: gewoon verder wachten;
        - deadline tijdens de herstart verstreken en de airco was al gezien:
          afronden als "aan" (dat is waargenomen);
        - verstreken en niet gezien: weg, want of hij tijdens de herstart
          aanging is niet te weten - liever geen waarneming dan een
          verkeerde.
        """
        if self._airco_waarnemingen_hersteld:
            return
        self._airco_waarnemingen_hersteld = True
        bewaard = getattr(self, "airco_open_waarnemingen", None) or []
        if not isinstance(bewaard, list) or self._temp_prediction_pending:
            return
        for item in bewaard:
            if not isinstance(item, dict) or not item.get("bucket"):
                continue
            try:
                deadline = datetime.fromisoformat(str(item.get("deadline")))
            except (TypeError, ValueError):
                continue
            if deadline.tzinfo is None and now.tzinfo is not None:
                deadline = deadline.replace(tzinfo=now.tzinfo)
            gezien = bool(item.get("airco_seen_active"))
            if deadline > now:
                herstel = {
                    "bucket": item["bucket"],
                    "deadline": deadline,
                    "airco_seen_active": gezien,
                }
                if item.get("airco_richting"):
                    herstel["airco_richting"] = item["airco_richting"]
                self._temp_prediction_pending.append(herstel)
            elif gezien:
                bucket = item["bucket"]
                history = self.living_room_temp_bucket_history.setdefault(bucket, [])
                history.append(True)
                self.living_room_temp_bucket_history[bucket] = history[
                    -AIRCO_PREDICTION_HISTORY_LENGTH:
                ]
                richting = item.get("airco_richting")
                if richting:
                    richtingen = self.living_room_temp_bucket_direction.setdefault(
                        bucket, []
                    )
                    richtingen.append(richting)
                    self.living_room_temp_bucket_direction[bucket] = richtingen[
                        -AIRCO_PREDICTION_HISTORY_LENGTH:
                    ]

    def _bewaar_airco_waarnemingen(self) -> None:
        """JSON-veilige kopie van de open waarnemingen voor de opslag (v5.63.1)."""
        self.airco_open_waarnemingen = [
            {
                "bucket": p["bucket"],
                "deadline": p["deadline"].isoformat()
                if isinstance(p.get("deadline"), datetime)
                else str(p.get("deadline")),
                "airco_seen_active": bool(p.get("airco_seen_active")),
                **({"airco_richting": p["airco_richting"]} if p.get("airco_richting") else {}),
            }
            for p in self._temp_prediction_pending
        ]

    def _airco_bakje_mag_starten(self, bucket_key: str, now: datetime) -> bool:
        """Mag er in dit bakje een nieuwe waarneming starten? (v5.58)

        Nee zolang er voor dit bakje nog een open staat, en nee binnen
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES na de vorige start in dit bakje.
        Andere bakjes tellen niet mee: zakt de kamer van 22,0 naar 21,5 °C,
        dan start bakje 21,5 meteen.
        """
        if any(p.get("bucket") == bucket_key for p in self._temp_prediction_pending):
            return False
        vorige = (self.airco_bakje_laatste_start or {}).get(bucket_key)
        if not vorige:
            return True
        try:
            vorige_dt = datetime.fromisoformat(str(vorige))
            if vorige_dt.tzinfo is None and now.tzinfo is not None:
                vorige_dt = vorige_dt.replace(tzinfo=now.tzinfo)
            verstreken = now - vorige_dt
        except (TypeError, ValueError):
            return True
        # Klok teruggezet of een vreemde stand: dan niet eeuwig blokkeren.
        if verstreken < timedelta(0):
            return True
        return verstreken >= timedelta(minutes=AIRCO_PREDICTION_LOOKAHEAD_MINUTES)

    def _migreer_airco_leren(self) -> None:
        """Wist de per-ronde-historie van de airco-voorspelling, eenmalig
        (v5.58).

        Tot v5.57 kwam er elke ronde een waarneming bij, dus de opgeslagen
        bakjes bestaan uit blokken van tientallen bijna identieke minuten.
        Zonder starttijden is niet terug te halen welke daarvan echt losse
        momenten waren; inkorten zou nog steeds per-minuut-duplicaten
        bewaren. Daarom per bakje leeg, met kans, richting en
        luchtvochtigheid. Het leren begint opnieuw: per bakje eerst
        AIRCO_PREDICTION_MIN_SAMPLES uurwaarnemingen voordat het telt (ook
        voor de airco-automaat, die tot dan "leert nog" meldt). De
        gekozen setpunten blijven: die zijn per bediening, niet per ronde.

        v5.60 (AIRCO_LEER_VERSIE = 3): dezelfde wis nog één keer, omdat de
        bakjes van één graad niet op die van een halve graad passen (bakje
        "19.0" was 18,5-19,4 °C, nu 18,8-19,2 °C). Het leren begint opnieuw.
        """
        if self.airco_leer_versie == AIRCO_LEER_VERSIE:
            return
        self.living_room_temp_bucket_history = {}
        self.living_room_temp_bucket_humidity = {}
        self.living_room_temp_bucket_direction = {}
        self._temp_prediction_pending = []
        self.airco_open_waarnemingen = []
        self.airco_bakje_laatste_start = {}
        self.airco_leer_versie = AIRCO_LEER_VERSIE
        opslag = getattr(self, "_geladen_opslag", None)
        if isinstance(opslag, dict):
            for sleutel in (
                "living_room_temp_bucket_history",
                "living_room_temp_bucket_humidity",
                "living_room_temp_bucket_direction",
                "airco_bakje_laatste_start",
                "airco_open_waarnemingen",
            ):
                opslag.pop(sleutel, None)
            opslag["airco_leer_versie"] = AIRCO_LEER_VERSIE

    def get_airco_kansen_per_bakje(self) -> dict:
        """De aircokans voor alle geleerde temperatuurbakjes (v5.8).

        Voor de export. `get_airco_activation_probability` vraagt één
        bakje als argument; in v5.4 riep ik hem zonder aan en viel hij
        drie dagen om met "missing 1 required positional argument". Dit
        geeft wat de sensor ook toont - alle bakjes - zonder argument.
        """
        return {
            "bakjes": {
                sleutel: self.get_airco_activation_probability(sleutel)
                for sleutel in sorted(
                    self.living_room_temp_bucket_history or {},
                    key=lambda x: float(x),
                )
            }
        }

    def get_airco_activation_probability(self, bucket_key: str) -> dict:
        """Learned probability the airco activates within
        AIRCO_PREDICTION_LOOKAHEAD_MINUTES of a reading in this
        temperature bucket, plus sample count and readiness - used by
        both the sensor and (indirectly) the advisory-readiness table.
        """
        history = self.living_room_temp_bucket_history.get(bucket_key, [])
        humidity_history = self.living_room_temp_bucket_humidity.get(bucket_key, [])
        sample_count = len(history)
        # v1.18.1: welke kant op? Bij 18 °C betekent "airco aan"
        # verwarmen, bij 26 °C koelen - twee tegengestelde acties met een
        # tegengesteld gevolg voor het verbruik.
        richtingen = self.living_room_temp_bucket_direction.get(bucket_key, [])
        overheersend = None
        if richtingen:
            overheersend = max(set(richtingen), key=richtingen.count)

        result = {
            "bucket": bucket_key,
            "sample_count": sample_count,
            "probability_percent": None,
            "richting": overheersend,
            "gemiddelde_luchtvochtigheid_percent": (
                round(sum(humidity_history) / len(humidity_history), 1)
                if humidity_history
                else None
            ),
            "voldoende_data": sample_count >= AIRCO_PREDICTION_MIN_SAMPLES,
        }
        if history:
            result["probability_percent"] = round(
                100 * sum(history) / len(history), 1
            )
        return result

    def _get_shutter_state_label(self) -> str | None:
        """Combines the two configured shutter (rolluik) entities into
        one label (v0.63.56) - "beide_dicht" (no solar gain through
        this room's windows), "gedeeltelijk" (one open, one closed), or
        "beide_open" (maximum solar gain potential). None if neither
        entity is configured or readable.

        v5.63: met de echte stand. Een gekalibreerd rolluik meldt
        `current_position` (0 = dicht, 100 = open); een rolluik op 20% stond
        hiervoor als "open" te boek, alsof de zon volop binnenkwam. Nu telt
        het gemiddelde van de standen: >= 90% "beide_open", <= 10%
        "beide_dicht", daartussen "gedeeltelijk". Dezelfde drie labels, dus
        wat de klimaatprojectie al leerde blijft bruikbaar. Zonder positie
        (niet gekalibreerd) telt open als 100 en dicht als 0, precies zoals
        hiervoor. Onbeschikbare rolluiken tellen niet mee.
        """
        entity_1 = self.config.get(CONF_LIVING_ROOM_SHUTTER_ENTITY_1)
        entity_2 = self.config.get(CONF_LIVING_ROOM_SHUTTER_ENTITY_2)
        standen: list[float] = []
        for entity_id in (entity_1, entity_2):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            stand = rolluikstand_procent(state.state, state.attributes)
            if stand is not None:
                standen.append(stand)
        if not standen:
            return None
        return rolluiklabel(sum(standen) / len(standen))

    def _airco_ingeschakeld(self) -> bool | None:
        """Staat de airco AAN (ingeschakeld), los van of de compressor nu
        draait? None = geen of onbeschikbare climate-entiteit (v5.98.0)."""
        airco_entity = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        if not airco_entity:
            return None
        state = self.hass.states.get(airco_entity)
        if state is None or state.state in ("unavailable", "unknown", None, ""):
            return None
        return state.state != "off"

    def _airco_richting_stand(self) -> str | None:
        """Richting uit de gekozen stand (heat/cool), v5.98.0."""
        airco_entity = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        state = self.hass.states.get(airco_entity) if airco_entity else None
        if state is None:
            return None
        return {"heat": "verwarmen", "cool": "koelen"}.get(state.state)

    def _get_current_airco_state_label(self) -> str:
        """Uit/verwarmen/koelen op basis van `hvac_action` (v0.63.56) -
        meer granulair dan de bestaande grootverbruiker-detectie
        (die alleen "actief ja/nee" onderscheidt), omdat verwarmen en
        koelen tegenovergestelde effecten op de kamertemperatuur hebben.
        """
        airco_entity = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        if not airco_entity:
            return "onbekend"
        state = self.hass.states.get(airco_entity)
        if state is None:
            return "onbekend"
        hvac_action = state.attributes.get("hvac_action")
        if hvac_action == "heating":
            return "verwarmen"
        if hvac_action == "cooling":
            return "koelen"
        return "uit"

    def _sun_could_hit_the_backyard_sensor(self) -> tuple[bool, str]:
        """Kan de zon op dit moment op de achtertuinsensor schijnen?
        (v1.3.1)

        Geeft (mogelijk, reden) terug. De reden gaat mee in de melding,
        zodat er niet langer "mogelijk direct zonlicht" staat op een
        moment dat de zon aantoonbaar onder de horizon staat.

        De blootstellingsrichting wordt GELEERD uit de azimut waarbij
        eerdere flitsen optraden. De integratie weet niet waar die sensor
        hangt, en ernaar vragen zou een configuratieveld opleveren dat
        moeilijk goed in te vullen is - de meeste mensen weten niet uit
        welke windrichting hun sensorbehuizing zon vangt.
        """
        daglicht = self.is_daylight_now()
        if daglicht is False:
            return False, "de zon staat onder de horizon"
        if daglicht is None:
            # Zonnestand onbekend: het oude gedrag aanhouden in plaats
            # van te gokken.
            return True, "mogelijk kortstondig direct zonlicht op de sensor"

        azimut = self.get_sun_azimuth_degrees()
        geleerd = self.backyard_sun_exposure_azimuths
        if azimut is None or len(geleerd) < BACKYARD_SUN_EXPOSURE_MIN_SAMPLES:
            return True, "mogelijk kortstondig direct zonlicht op de sensor"

        # Cirkelvormig verschil: 350 en 10 graden liggen 20 graden uit
        # elkaar, niet 340.
        def afstand(a: float, b: float) -> float:
            verschil = abs(a - b) % 360
            return min(verschil, 360 - verschil)

        dichtstbij = min(afstand(azimut, eerder) for eerder in geleerd)
        if dichtstbij > BACKYARD_SUN_EXPOSURE_MARGIN_DEGREES:
            return (
                False,
                f"de zon staat op {azimut:.0f}°, ver buiten de richting "
                "waaruit deze sensor eerder flitsen liet zien",
            )
        return True, "mogelijk kortstondig direct zonlicht op de sensor"

    def _record_backyard_sun_exposure(self) -> None:
        """Onthoudt uit welke richting de zon kwam bij een flits
        (v1.3.1) - alleen bij daglicht, want anders zegt de azimut
        niets."""
        if self.is_daylight_now() is not True:
            return
        azimut = self.get_sun_azimuth_degrees()
        if azimut is None:
            return
        self.backyard_sun_exposure_azimuths.append(round(azimut, 1))
        self.backyard_sun_exposure_azimuths = self.backyard_sun_exposure_azimuths[
            -BACKYARD_SUN_EXPOSURE_HISTORY_LENGTH:
        ]

    def _get_filtered_backyard_temp_c(self, now: datetime) -> float | None:
        """Uitschieter-gefilterde achtertuinsensor-meting (v0.63.96,
        gerapporteerd met grafiek: de sensor kan 's ochtends kort in
        direct zonlicht hangen, wat een plotselinge, kortstondige
        sprong veroorzaakt die niets met de werkelijke luchttemperatuur
        te maken heeft - de behuizing warmt zelf op).

        Een sprong die de plausibele afkoel/opwarm-snelheid van
        buitenlucht (`BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR`) ver
        overschrijdt, wordt niet meteen vertrouwd - de vorige,
        geaccepteerde waarde blijft gelden totdat de nieuwe waarde
        minstens `BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES` aanhoudt (binnen
        een kleine tolerantiemarge, `BACKYARD_TEMP_SPIKE_TOLERANCE_C`,
        zodat kleine meetruis de teller niet steeds laat resetten). Een
        kortstondige zonneflits zakt vanzelf terug voordat dit venster
        verstrijkt en wordt dan genegeerd; een echte, aanhoudende
        verandering (bijv. een koufront) wordt na dit venster alsnog
        geaccepteerd - dit filtert dus ruis, het bevriest de meting
        niet permanent.
        """
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if not backyard_entity:
            return None
        raw_temp = self._read_sensor_float(backyard_entity)
        if raw_temp is None:
            return None

        if self._backyard_temp_last_accepted_c is None:
            self._backyard_temp_last_accepted_c = raw_temp
            self._backyard_temp_last_accepted_at = now
            return raw_temp

        elapsed_hours = max(
            (now - self._backyard_temp_last_accepted_at).total_seconds() / 3600,
            1 / 3600,  # avoid a division by ~0 on two ticks in the same second
        )
        deviation_c = abs(raw_temp - self._backyard_temp_last_accepted_c)
        implied_rate = deviation_c / elapsed_hours

        # v1.0.6: een uitschieter moet aan TWEE voorwaarden voldoen - een
        # onwaarschijnlijk tempo én een noemenswaardige sprong. Op de
        # snelheidstoets alléén was 0,4 °C tussen twee ticks van 5
        # minuten al "4,8 °C/uur" en dus verdacht, terwijl dat gewoon
        # meetruis is. Hoe korter het interval, hoe erger: over één
        # minuut haalde zelfs 0,07 °C de drempel. Het gevolg was een
        # filter dat heen en weer sloeg tussen twee normale waarden
        # (gerapporteerd: "net was het andersom") en daarmee een
        # verouderde waarde vasthield zonder dat er iets aan de hand was.
        if (
            deviation_c < BACKYARD_TEMP_SPIKE_MIN_DEVIATION_C
            or implied_rate <= BACKYARD_TEMP_MAX_PLAUSIBLE_RATE_C_PER_HOUR
        ):
            # Plausible change - accept directly, no spike suspected.
            self._backyard_temp_last_accepted_c = raw_temp
            self._backyard_temp_last_accepted_at = now
            self._backyard_temp_spike_candidate_c = None
            self._backyard_temp_spike_since = None
            # v1.0.6: de melding hoort te verdwijnen zodra er weer een
            # normale waarde binnenkomt - anders blijft een opgeloste
            # uitschieter op het dashboard staan.
            self.last_backyard_spike_filtered_note = None
            return raw_temp

        # Implausibly fast change - a suspected artifact (e.g. direct
        # sun hitting the sensor). Track it, but keep returning the
        # last trusted value until/unless it's confirmed sustained.
        if (
            self._backyard_temp_spike_candidate_c is not None
            and abs(raw_temp - self._backyard_temp_spike_candidate_c)
            <= BACKYARD_TEMP_SPIKE_TOLERANCE_C
        ):
            sustained_minutes = (
                now - self._backyard_temp_spike_since
            ).total_seconds() / 60
            mogelijk_zon, _ = self._sun_could_hit_the_backyard_sensor()
            vereist = (
                BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES
                if mogelijk_zon
                else BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN
            )
            if sustained_minutes >= vereist:
                # Sustained long enough - treat as a genuine change,
                # not a transient artifact.
                self._backyard_temp_last_accepted_c = raw_temp
                self._backyard_temp_last_accepted_at = now
                self._backyard_temp_spike_candidate_c = None
                self._backyard_temp_spike_since = None
                self.last_backyard_spike_filtered_note = None
                return raw_temp
        else:
            # A new (or first) spike candidate - start the confirmation
            # window.
            if self._backyard_temp_spike_candidate_c is not None:
                # De vorige kandidaat hield niet aan en was dus een echte
                # kortstondige flits. Onthoud uit welke richting de zon
                # toen kwam - zo leert de integratie waar deze sensor
                # blootstaat, zonder dat iemand dat hoeft in te vullen.
                self._record_backyard_sun_exposure()
            self._backyard_temp_spike_candidate_c = raw_temp
            self._backyard_temp_spike_since = now

        # v1.3.1: hoe lang er gewacht wordt hangt af van de zonnestand.
        # Kan de zon er niet op schijnen, dan is dit geen zonneflits en
        # is 45 minuten wachten onnodig lang voor iets dat vrijwel zeker
        # echt weer is.
        mogelijk_zon, zon_reden = self._sun_could_hit_the_backyard_sensor()
        venster = (
            BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES
            if mogelijk_zon
            else BACKYARD_TEMP_SPIKE_CONFIRM_MINUTES_NO_SUN
        )
        self.last_backyard_spike_filtered_note = (
            f"Uitschieter genegeerd: {raw_temp}°C wijkt te snel af van "
            f"{self._backyard_temp_last_accepted_c}°C ({zon_reden}) - "
            f"wordt vertrouwd als dit {venster} minuten aanhoudt."
        )
        return self._backyard_temp_last_accepted_c

    def _get_live_outdoor_temp_c(self, now: datetime) -> float | None:
        """Live buitentemperatuur (v0.63.56, uitgebreid in v0.63.95/.96).

        Voorkeursbron: een geconfigureerde eigen achtertuin-
        temperatuursensor (`CONF_BACKYARD_TEMPERATURE_SENSOR`) - een
        fysieke, lokale meting is nauwkeuriger voor de eigen locatie
        dan een regionale weerentiteit-schatting (gevraagd na een
        eerdere sessie waarin de weerentiteit een significante
        afwijking bleek te hebben). Loopt door `_get_filtered_
        backyard_temp_c` (v0.63.96) om kortstondige uitschieters
        (bijv. direct zonlicht op de sensor 's ochtends) eruit te
        filteren. Valt terug op de weerentiteiten (KNMI eerst, dan
        OpenWeatherMap - hergebruikt de al geconfigureerde Weather
        Ensemble-entiteiten, v0.63.30) als er geen achtertuinsensor is
        geconfigureerd of niet uitleesbaar is.
        """
        # v1.1.1, gerapporteerd: "We hebben mijn buitentemperatuur
        # sensor toegevoegd maar die zie ik niet terug?" - de sensor werd
        # wél degelijk gebruikt, maar het dashboardlabel noemde nog
        # hardgecodeerd "KNMI/OpenWeatherMap" uit de tijd vóór v0.63.95.
        # Welke bron de waarde levert wordt nu vastgelegd, zodat het
        # label dat kan tonen in plaats van het te beweren.
        self.climate_live_outdoor_source = None
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if backyard_entity:
            filtered_temp = self._get_filtered_backyard_temp_c(now)
            if filtered_temp is not None:
                self.climate_live_outdoor_source = backyard_entity
                return filtered_temp

        for entity_id in (
            self.config.get(CONF_KNMI_WEATHER_ENTITY),
            self.config.get(CONF_OPENWEATHERMAP_WEATHER_ENTITY),
        ):
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            temp = state.attributes.get("temperature")
            if temp is not None:
                try:
                    waarde = float(temp)
                except (TypeError, ValueError):
                    continue
                self.climate_live_outdoor_source = entity_id
                return waarde
        return None


    @staticmethod
    def _climate_verschil_bucket(outdoor_temp_c: float, indoor_temp_c: float) -> str:
        """Het VERSCHIL tussen buiten en binnen, in vakjes (v3.41.0).

        Gevonden bij het nalopen van de correlaties. De emmers sleutelden
        op de buitentemperatuur, terwijl het gemeten getal de verandering
        van de BINNENtemperatuur is. Binnen dezelfde emmer stonden de
        tekens door elkaar:

            26.0|beide_open|uit: [-0.284, +0.137, -0.067, +0.009, -0.156]

        Dat is geen ruis maar natuurkunde. Een kamer volgt de wet van
        Newton: hoe snel de temperatuur verandert hangt af van het
        VERSCHIL met buiten, niet van de buitentemperatuur alleen. Bij 26
        graden buiten warmt een kamer van 21 op en koelt een kamer van 28
        af - zelfde emmer, tegengesteld teken.

        Dit is uitdrukkelijk GEEN vierde dimensie. Het vervangt er een:
        buitentemperatuur wordt verschil. Het aantal cellen blijft
        gelijk, de natuurkunde klopt, en het teken wordt voorspelbaar -
        positief verschil betekent opwarmen.

        Het merkteken `d` voorop houdt oude en nieuwe sleutels uit
        elkaar; de oude zijn niet om te rekenen, want de
        binnentemperatuur van toen is niet bewaard.
        """
        verschil = outdoor_temp_c - indoor_temp_c
        vak = round(verschil / OUTDOOR_TEMP_BUCKET_SIZE_C) * OUTDOOR_TEMP_BUCKET_SIZE_C
        return f"d{vak}"

    def _climate_rate_key(
        self, outdoor_bucket: str, shutter_state: str, airco_state: str
    ) -> str:
        return f"{outdoor_bucket}|{shutter_state}|{airco_state}"

    def _ruim_oude_klimaatcellen_op(self) -> None:
        """Gooit de cellen van vóór v3.41.0 weg.

        Ze sleutelden op de buitentemperatuur en zijn niet om te rekenen:
        de binnentemperatuur van dat moment is niet bewaard. Ze laten
        staan zou betekenen dat er twee soorten sleutels naast elkaar
        leven en dat de helft van de metingen nooit meer wordt gelezen.
        """
        oud = [k for k in (self.climate_rate_history or {}) if not k.startswith("d")]
        if not oud:
            return
        for k in oud:
            del self.climate_rate_history[k]
        _LOGGER.info(
            "%d klimaatcellen van vóór v3.41.0 verwijderd - die sleutelden "
            "op de buitentemperatuur in plaats van op het verschil met "
            "binnen, en zijn niet om te rekenen",
            len(oud),
        )
        self.schedule_persisted_state_save()

    def _update_climate_rate_learning(self, now: datetime) -> None:
        """Learns the living room's own rate of temperature change
        (°C/hour) as a function of (outdoor temperature bucket, shutter
        state, airco state) - v0.63.56, requested. Deliberately leaves
        cloud cover OUT as a separate learning dimension (confirmed with
        the person) - a full model (outdoor temp x shutter x cloud x
        airco) would produce hundreds of cells that would each need
        their own data, most staying "onvoldoende data" for months in a
        typical household.

        Short, bounded rolling window per cell (CLIMATE_RATE_HISTORY_
        LENGTH = 20), same principle as the airco-activation predictor
        above - spring/autumn conditions can swing day to day, so a
        cell's learned rate should track recent behaviour.

        Measured over roughly an hour (an "anchor" reading compared
        against the next one ~an hour later), not every 5-minute tick -
        a rate computed from tick-to-tick deltas would be numerically
        unstable for a physically slow-moving quantity like room
        temperature (typical sensor resolution ~0.1°C, divided by a tiny
        5/60h timespan amplifies noise into wildly swinging rates).
        Reads the living room temperature directly (not via
        `living_room_current_temp_c`, which is set by
        `_update_living_room_airco_prediction`) so this function stays
        independently correct and testable regardless of call order.
        """
        temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
        temp_c = self._read_sensor_float(temp_entity) if temp_entity else None
        outdoor_temp_c = self._get_live_outdoor_temp_c(now)
        shutter_state = self._get_shutter_state_label()
        airco_state = self._get_current_airco_state_label()
        self.climate_shutter_state = shutter_state
        self.climate_airco_state = airco_state
        self.climate_live_outdoor_temp_c = outdoor_temp_c

        if temp_c is None or outdoor_temp_c is None or shutter_state is None:
            return

        if self._climate_anchor_time is None or self._climate_anchor_temp_c is None:
            self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)
            return

        elapsed_hours = (now - self._climate_anchor_time).total_seconds() / 3600

        if elapsed_hours > CLIMATE_RATE_MAX_INTERVAL_HOURS:
            # Restart-sized gap - don't attribute it to a single rate,
            # just start a fresh anchor from here.
            self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)
            return

        if elapsed_hours < CLIMATE_RATE_MIN_INTERVAL_HOURS:
            # Not enough time has passed yet for a stable measurement -
            # keep the current anchor, try again next tick.
            return

        rate_c_per_hour = (temp_c - self._climate_anchor_temp_c) / elapsed_hours
        key = self._climate_rate_key(
            self._climate_anchor_outdoor_bucket,
            self._climate_anchor_shutter_state,
            self._climate_anchor_airco_state,
        )
        self._leer_klimaatresiduen(key, rate_c_per_hour)
        history = self.climate_rate_history.setdefault(key, [])
        history.append(round(rate_c_per_hour, 3))
        self.climate_rate_history[key] = history[-CLIMATE_RATE_HISTORY_LENGTH:]

        self._set_climate_anchor(now, temp_c, outdoor_temp_c, shutter_state, airco_state)

    def _set_climate_anchor(
        self,
        now: datetime,
        temp_c: float,
        outdoor_temp_c: float,
        shutter_state: str,
        airco_state: str,
    ) -> None:
        self._climate_anchor_time = now
        self._climate_anchor_temp_c = temp_c
        # v3.41.0: het VERSCHIL met binnen, niet de buitentemperatuur.
        self._climate_anchor_outdoor_bucket = self._climate_verschil_bucket(
            outdoor_temp_c, temp_c
        )
        self._climate_anchor_shutter_state = shutter_state
        self._climate_anchor_airco_state = airco_state
        self._klimaat_anker_wind = self._live_wind()
        self._klimaat_anker_zon = self._live_pv_w()

    def _wind_weerentiteit(self) -> str | None:
        """De weerentiteit voor wind: dezelfde als voor de buitentemperatuur-
        voorspelling (v5.64)."""
        return self.config.get(CONF_KNMI_WEATHER_ENTITY) or self.config.get(
            CONF_OPENWEATHERMAP_WEATHER_ENTITY
        )

    def _live_wind(self) -> tuple[float | None, float | None] | None:
        """Actuele wind (km/h, graden) van de weerentiteit (v5.64)."""
        entiteit = self._wind_weerentiteit()
        toestand = self.hass.states.get(entiteit) if entiteit else None
        if toestand is None:
            return None
        kmh, graden = klimaat_wind.uit_attributen(toestand.attributes)
        return (kmh, graden) if kmh is not None else None

    def _live_pv_w(self) -> float | None:
        """Het actuele PV-vermogen (W), en meteen de piek bijwerken (v5.66)."""
        pv_w = self._read_sensor_float(self.config.get(CONF_PV_POWER_SENSOR))
        if pv_w is not None:
            klimaat_zon.werk_piek_bij(self.klimaat_zon_residuen, pv_w)
        return pv_w

    def _leer_klimaatresiduen(self, key: str, rate_c_per_hour: float) -> None:
        """Wat de kamer dit uur ANDERS deed dan haar cel gewoonlijk, bewaard
        onder de wind (v5.64) of de zon (v5.66) van dat uur.

        Alleen met de airco uit (anders meet je de airco) en alleen als de
        cel zelf al genoeg metingen heeft om een gewoonte te hebben. De
        mediaan van de cel wordt VOOR deze meting genomen.

        Niet dubbel tellen: de wind leert alleen in uren met weinig zon; de
        zon leert na aftrek van de windcorrectie die al bekend is.
        """
        cel = self.climate_rate_history.get(key) or []
        if self._climate_anchor_airco_state != "uit" or len(cel) < CLIMATE_RATE_MIN_SAMPLES:
            return
        afwijking = rate_c_per_hour - statistics.median(cel)
        windsleutel = klimaat_wind.windsleutel(*(self._klimaat_anker_wind or (None, None)))
        zon = klimaat_zon.klasse(self._klimaat_anker_zon, klimaat_zon.piek(self.klimaat_zon_residuen))
        if zon in (None, "zwak"):
            klimaat_wind.leer_residu(self.klimaat_wind_residuen, windsleutel, afwijking)
        if zon is not None:
            wind = klimaat_wind.correctie(self.klimaat_wind_residuen, windsleutel)["c_per_uur"] or 0.0
            klimaat_wind.leer_residu(
                self.klimaat_zon_residuen,
                klimaat_zon.zonsleutel(self._climate_anchor_shutter_state, self._klimaat_anker_zon,
                                       klimaat_zon.piek(self.klimaat_zon_residuen)),
                afwijking - wind,
            )

    def _zoncorrectie(self, moment: datetime, shutter_state: str, airco_state: str) -> dict:
        """De zoncorrectie voor één uur van de projectie (v5.66): de
        verwachte PV halverwege dat uur, als deel van de piek."""
        pv_w = self._get_expected_pv_power_w(moment + timedelta(minutes=30))
        sleutel = klimaat_zon.zonsleutel(shutter_state, pv_w, klimaat_zon.piek(self.klimaat_zon_residuen))
        uit = klimaat_zon.correctie(self.klimaat_zon_residuen, sleutel)
        if airco_state != "uit":
            uit = {"c_per_uur": None, "metingen": uit["metingen"], "betrouwbaar": False}
        uit["klasse"] = sleutel.split("|")[1] if sleutel else None
        return uit

    def get_klimaat_zon(self) -> dict:
        """Wat er over de zon geleerd is, voor het dashboard (v5.66)."""
        return {
            "piek_w": klimaat_zon.piek(self.klimaat_zon_residuen),
            "per_stand": klimaat_zon.overzicht(self.klimaat_zon_residuen),
            "toelichting": (
                "Per rolluikstand en zon (PV-opbrengst als deel van de piek: zwak "
                "5-30%, matig 30-60%, sterk vanaf 60%) hoeveel sneller de woonkamer "
                "per uur opwarmt dan bij dezelfde temperatuur gewoonlijk, met de "
                "airco uit. Vanaf 5 metingen in de indicatieve projectie, vanaf 15 "
                "ook in de strenge."
            ),
        }

    def _onthoud_voorspelde_wind(self, raw_forecast, entity_id: str) -> None:
        """De voorspelde wind per uur, naast de temperatuurvoorspelling (v5.64)."""
        toestand = self.hass.states.get(entity_id)
        eenheid = toestand.attributes.get("wind_speed_unit") if toestand else None
        per_uur = {}
        for item in raw_forecast or []:
            when = item.get("datetime") if isinstance(item, dict) else None
            moment = dt_util.parse_datetime(when) if isinstance(when, str) else when
            kmh = klimaat_wind.naar_kmh(item.get("wind_speed"), eenheid) if moment else None
            if kmh is None:
                continue
            per_uur[dt_util.as_local(moment).strftime("%Y-%m-%dT%H")] = (
                kmh, item.get("wind_bearing")
            )
        self._klimaat_wind_per_uur = per_uur

    def _windcorrectie(self, moment: datetime, airco_state: str) -> dict:
        """De windcorrectie voor één uur van de projectie (v5.64).

        Alleen met de airco uit - zo is hij ook geleerd. Zonder voorspelde
        wind voor dat uur, of nog te weinig metingen: geen correctie.
        """
        wind = (self._klimaat_wind_per_uur or {}).get(moment.strftime("%Y-%m-%dT%H"))
        kmh, graden = wind if wind else (None, None)
        uit = klimaat_wind.correctie(
            self.klimaat_wind_residuen, klimaat_wind.windsleutel(kmh, graden)
        )
        if airco_state != "uit":
            uit = {"c_per_uur": None, "metingen": uit["metingen"], "betrouwbaar": False}
        uit["label"] = klimaat_wind.wind_label(kmh, graden)
        return uit

    def get_rolluik_isolatie(self) -> dict:
        """Rolluiken eerder dicht tegen koude wind? (v5.66) - zie
        `klimaat_wind.isolatie_advies`. Alleen een advies: de bestaande
        rolluikautomatisering leest het."""
        nu = self._live_wind() or (None, None)
        correctie = klimaat_wind.correctie(
            self.klimaat_wind_residuen, klimaat_wind.windsleutel(*nu)
        )["c_per_uur"]
        pv_w = self._read_sensor_float(self.config.get(CONF_PV_POWER_SENSOR))
        return klimaat_wind.isolatie_advies(
            correctie,
            klimaat_zon.klasse(pv_w, klimaat_zon.piek(self.klimaat_zon_residuen)),
            self.get_sun_elevation_degrees(),
            self.climate_live_outdoor_temp_c,
            self.living_room_current_temp_c,
            klimaat_wind.wind_label(*nu),
        )

    def get_klimaat_wind(self) -> dict:
        """Wat er over wind geleerd is, voor het dashboard (v5.64)."""
        nu = self._live_wind()
        return {
            "nu": klimaat_wind.wind_label(*nu) if nu else None,
            "per_richting": [
                r for r in klimaat_wind.overzicht(self.klimaat_wind_residuen)
                if r["metingen"]
            ],
            "toelichting": (
                "Per windrichting en windklasse (matig 10-25 km/h, hard vanaf "
                "25 km/h) hoeveel sneller (min) of langzamer (plus) de woonkamer "
                "per uur afkoelt dan bij dezelfde temperatuur gewoonlijk, met de "
                "airco uit. Vanaf 5 metingen telt het mee in de indicatieve "
                "projectie, vanaf 15 ook in de strenge."
            ),
        }

    def get_climate_rate(
        self, outdoor_bucket: str, shutter_state: str, airco_state: str
    ) -> dict:
        """Learned rate of living-room temperature change (°C/hour) for
        this combination, plus sample count and a two-tier reliability
        level (v0.63.57, requested): "indicatief" once
        CLIMATE_RATE_MIN_SAMPLES (5) exist, "betrouwbaar" only once
        CLIMATE_RATE_RELIABLE_SAMPLES (15) do.
        """
        key = self._climate_rate_key(outdoor_bucket, shutter_state, airco_state)
        history = self.climate_rate_history.get(key, [])
        sample_count = len(history)
        if sample_count >= CLIMATE_RATE_RELIABLE_SAMPLES:
            betrouwbaarheid = "betrouwbaar"
        elif sample_count >= CLIMATE_RATE_MIN_SAMPLES:
            betrouwbaarheid = "indicatief"
        else:
            betrouwbaarheid = "onvoldoende_data"
        # v3.41.0: staan de metingen in deze cel het onderling eens?
        #
        # Ook met de juiste sleutel blijft een cel waarin de helft
        # opwarmt en de helft afkoelt onbruikbaar - dan vangt hij nog
        # steeds iets anders dan hij denkt, bijvoorbeeld de zon op het
        # raam. De mediaan van zo'n cel is een getal zonder betekenis,
        # en dat hoort erbij te staan in plaats van dat het als geleerd
        # tempo wordt gepresenteerd.
        eenduidig = True
        if sample_count >= CLIMATE_RATE_MIN_SAMPLES:
            positief = sum(1 for v in history if v > 0)
            middelpunt = statistics.median(history)
            # v3.42.2: een cel rond het omslagpunt mag wisselen van teken.
            #
            # Bij buiten gelijk aan binnen is het werkelijke tempo per
            # definitie ongeveer nul, en dan wisselt het teken vanzelf.
            # De toets van v3.41.0 zou die cel altijd afwijzen - niet
            # omdat hij onbruikbaar is, maar omdat hij op het omslagpunt
            # ligt. "Er gebeurt niets" is een bruikbaar antwoord.
            neutraal = abs(middelpunt) < CLIMATE_RATE_NEUTRAL_C_PER_HOUR
            eenduidig = (
                positief == 0 or positief == sample_count or neutraal
            )
            if not eenduidig:
                betrouwbaarheid = "niet_eenduidig"
        return {
            "key": key,
            "sample_count": sample_count,
            "rate_c_per_hour": (
                round(statistics.median(history), 3) if history else None
            ),
            "betrouwbaarheid": betrouwbaarheid,
            "eenduidig": eenduidig,
            "voldoende_data": (
                sample_count >= CLIMATE_RATE_MIN_SAMPLES and eenduidig
            ),
        }

    def get_climate_rate_indicative(
        self, outdoor_bucket: str, shutter_state: str, airco_state: str
    ) -> dict:
        """Geleerd tempo voor de INDICATIEVE reeks, met terugval op een
        grovere samenvatting als deze exacte cel nog te weinig data heeft
        (v1.1.2).

        `get_climate_rate` blijft ongewijzigd en streng - die voedt de
        "betrouwbaar"-reeks, en daar is exactheid juist het punt.

        Zie CLIMATE_RATE_NEIGHBOUR_BUCKETS in const.py voor de volgorde
        van terugvallen en waarom die zo is gekozen. Elke stap meldt
        welke basis is gebruikt, zodat op het dashboard te zien blijft
        hoe hard de schatting is - een terugval verzwijgen zou de
        indicatie geloofwaardiger laten lijken dan ze is.
        """
        exact = self.get_climate_rate(outdoor_bucket, shutter_state, airco_state)
        if exact["voldoende_data"]:
            return {**exact, "basis": "exact"}

        # v3.47.0: het merkteken `d` eraf voordat er gerekend wordt.
        #
        # Sinds v3.41.0 beginnen de sleutels met een `d` - "d-6.0" in
        # plaats van "6.0" - omdat ze het VERSCHIL met binnen dragen en
        # niet de buitentemperatuur. Deze omzetting liep daar stil op
        # stuk: `float("d-6.0")` werpt een ValueError, `bucket_waarde`
        # werd None, en stap 2 werd sindsdien overgeslagen.
        #
        # Gevolg: de naburige vakjes zijn zes dagen lang nooit
        # geraadpleegd. De projectie viel meteen door naar de
        # grofste terugval, en dat is precies wat er misging bij een
        # verschil van +8 graden waar geen cel voor bestond.
        try:
            bucket_waarde = float(str(outdoor_bucket).lstrip("d"))
        except (TypeError, ValueError):
            bucket_waarde = None

        def _samenvatting(sleutels: list[str], basis: str) -> dict | None:
            metingen: list[float] = []
            for sleutel in sleutels:
                metingen.extend(self.climate_rate_history.get(sleutel, []))
            if len(metingen) < CLIMATE_RATE_MIN_SAMPLES:
                return None
            return {
                "key": exact["key"],
                "sample_count": len(metingen),
                "rate_c_per_hour": round(statistics.median(metingen), 3),
                "betrouwbaarheid": "indicatief",
                "voldoende_data": True,
                "basis": basis,
            }

        # 2. Naburige buitentemperatuur, zelfde rolluik + airco.
        if bucket_waarde is not None:
            buren = []
            for stap in range(1, CLIMATE_RATE_NEIGHBOUR_BUCKETS + 1):
                for richting in (-1, 1):
                    naburig = bucket_waarde + richting * stap * OUTDOOR_TEMP_BUCKET_SIZE_C
                    buren.append(
                        self._climate_rate_key(
                            f"d{naburig}", shutter_state, airco_state
                        )
                    )
            resultaat = _samenvatting(
                [exact["key"], *buren], "naburige_buitentemperatuur"
            )
            if resultaat is not None:
                return resultaat

        # 3. Zelfde buitentemperatuur, elke rolluik-/airco-stand.
        zelfde_bucket = [
            sleutel
            for sleutel in self.climate_rate_history
            if sleutel.split("|")[0] == outdoor_bucket
        ]
        resultaat = _samenvatting(zelfde_bucket, "zelfde_buitentemperatuur")
        if resultaat is not None:
            return resultaat

        # 4. Alles wat er is - maar alleen binnen bereik.
        #
        # Gemeld met een schermafdruk van de klimaattabel: vanaf 11:00
        # stond overal `algemeen` met nul metingen, en de voorspelde
        # binnentemperatuur zakte van 21,3 naar 20,9 terwijl het buiten
        # naar 31 graden liep.
        #
        # Dat kan niet. `algemeen` neemt de mediaan over ALLE cellen, en
        # die zijn overwegend nachtcellen met dichte rolluiken die
        # afkoelen. Dat gemiddelde werd losgelaten op een middag waarin
        # buiten tien graden boven binnen staat.
        #
        # Precies de fout die deze week al vier keer langskwam: een model
        # buiten zijn geldigheidsgebied gebruikt. Het temperatuurverband,
        # de dakvlakken, de rendementsterugval, de klimaatcellen - en nu
        # de terugval van die klimaatcellen zelf.
        #
        # Een projectie die zegt "het koelt af terwijl het buiten tien
        # graden warmer is" is erger dan geen projectie: hij oogt
        # geloofwaardig en klopt niet. Buiten het bereik waar cellen
        # bestaan, hoort hij niets te zeggen.
        if bucket_waarde is not None:
            gemeten = []
            for sleutel in self.climate_rate_history:
                try:
                    gemeten.append(float(sleutel.split("|")[0].lstrip("d")))
                except ValueError:
                    continue
            if gemeten and not (
                min(gemeten) - CLIMATE_RATE_MAX_EXTRAPOLATIE_C
                <= bucket_waarde
                <= max(gemeten) + CLIMATE_RATE_MAX_EXTRAPOLATIE_C
            ):
                return {
                    **exact,
                    "basis": "buiten_bereik",
                    "toelichting": (
                        f"Een verschil van {bucket_waarde:+.0f} °C valt "
                        f"buiten de gemeten reeks ({min(gemeten):+.0f} tot "
                        f"{max(gemeten):+.0f} °C). Er wordt geen tempo "
                        "geraden; de kamertemperatuur blijft staan tot er "
                        "voor deze omstandigheden gemeten is."
                    ),
                }

        resultaat = _samenvatting(list(self.climate_rate_history), "algemeen")
        if resultaat is not None:
            return resultaat

        return {**exact, "basis": "geen"}

    #: v5.177.0 (A13): de weerentiteit was er nog niet (opstarten).
    _weer_opnieuw_proberen: bool = False
    _weer_niet_klaar_gemeld: bool = False

    def _weer_nog_niet_klaar(self, entity_id: str, err: Exception) -> bool:
        """Is de weerentiteit gewoon nog niet geladen? (v5.177.0, A13)"""
        try:
            weer = self.hass.states.get(entity_id)
            # v5.176.4 + v5.177.0: ook een weerentiteit die nog 'unavailable' is.
            return weer is None or weer.state == "unavailable"
        except Exception:  # noqa: BLE001
            return "did not match any entities" in str(err)

    async def _async_fetch_hourly_outdoor_forecast(
        self, entity_id: str
    ) -> list[tuple[datetime, float]] | None:
        """Fetches the hourly outdoor temperature forecast via the
        `weather.get_forecasts` service (v0.63.56) - a genuinely
        different kind of call than anything else in this integration
        (needs `return_response=True`, unlike every other service call
        here, which are all fire-and-forget). Defensive: any failure
        (service missing, malformed response, an integration that uses
        different attribute names) is caught and treated as "no
        forecast available" rather than crashing the whole update tick.
        """
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 - a forecast fetch must never crash the tick
            # v5.177.0 (A13): bij het opstarten is de weerentiteit vaak nog
            # niet geladen ("Service call requested response data but did not
            # match any entities"). Dat is geen fout: een waarschuwing (één
            # keer) en over een paar minuten opnieuw. Andere fouten blijven
            # een uitzondering in het log.
            if self._weer_nog_niet_klaar(entity_id, err):
                self._weer_opnieuw_proberen = True
                if not self._weer_niet_klaar_gemeld:
                    self._weer_niet_klaar_gemeld = True
                    _LOGGER.warning(
                        "Weerentiteit %s is nog niet beschikbaar (%s); de uurverwachting "
                        "wordt over enkele minuten opnieuw opgehaald", entity_id, err,
                    )
                return None
            _LOGGER.exception(
                "Kon geen uurlijkse weersvoorspelling ophalen bij %s", entity_id
            )
            return None

        if not response or entity_id not in response:
            return None
        raw_forecast = response[entity_id].get("forecast")
        if not raw_forecast:
            return None

        entries = []
        for item in raw_forecast:
            temp = item.get("temperature")
            when = item.get("datetime")
            if temp is None or when is None:
                continue
            parsed_when = dt_util.parse_datetime(when) if isinstance(when, str) else when
            if parsed_when is None:
                continue
            # v0.63.93, gerapporteerd: "de temperature verwachting van
            # KNMI klopt niet in de tabellen" - bleek uiteindelijk twee
            # aparte dingen: (1) KNMI's eigen brondata week af van de
            # live meting (opgelost door over te stappen op een
            # nauwkeurigere weerentiteit), en (2) deze weerentiteit
            # rapporteert in UTC (+00:00) i.p.v. lokale tijd (+02:00
            # zoals KNMI toevallig deed) - zonder conversie zou de
            # getoonde "Uur"-kolom 2 uur achterlopen op de werkelijke
            # lokale tijd. Altijd expliciet naar lokale tijd converteren
            # bij het parsen, ongeacht welke tijdzone de brondata zelf
            # gebruikt - laat dit niet toevallig kloppen doordat één
            # specifieke bron nu net lokale tijd gebruikt.
            parsed_when = dt_util.as_local(parsed_when)
            try:
                entries.append((parsed_when, float(temp)))
            except (TypeError, ValueError):
                continue
        self._onthoud_voorspelde_wind(raw_forecast, entity_id)
        return entries or None

    async def _async_update_climate_forecast(self, now: datetime) -> None:
        """Klimaat-tabblad (v0.63.56/.57/.58): projects the living room
        temperature forward hour by hour, using the KNMI/OpenWeatherMap
        hourly outdoor-temperature forecast to drive the walk and the
        learned per-cell rate (see `_update_climate_rate_learning`) to
        translate outdoor conditions into indoor change. Shutter state
        and airco state are held CONSTANT at their current values for
        the whole projection (limitation, stated plainly) - there's no
        way to know what either will be doing in 6 hours.

        Two parallel projections per hour (v0.63.57, requested), not two
        separate models - just two different thresholds applied to the
        same learned rate:
        - `kort_termijn_temp_c`: applies the rate once
          CLIMATE_RATE_MIN_SAMPLES (5) samples exist - "indicatief",
          usable early even with still-thin data.
        - `betrouwbaar_temp_c`: only applies the rate once
          CLIMATE_RATE_RELIABLE_SAMPLES (15) do - a more conservative,
          slower-to-mature projection.
        Either series carries forward unchanged (not a guessed rate)
        for any hour below its own threshold, rather than silently
        compounding a made-up number forward through the 24-hour chain.

        v0.63.58, requested ("correctie op de actueel gemeten waarde"):
        split into two parts with two different cadences -
        `_async_maybe_refresh_outdoor_forecast` (this method) only
        RE-FETCHES the outdoor forecast at most once per
        CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES (30 min, since that's a
        genuine `return_response=True` service call, not a cheap
        state-machine read, and hourly forecast data doesn't change
        meaningfully every 5 minutes anyway) - but
        `_recompute_climate_trajectory` (called every tick, cheap, no
        network/service call) always re-walks the projection from
        whatever the CURRENT live-measured temperature is, using the
        cached forecast. Without this split, the projection's starting
        point would drift stale for up to 30 minutes between fetches,
        even though the actual room temperature keeps changing in the
        meantime.
        """
        await self._async_maybe_refresh_outdoor_forecast(now)
        self._recompute_climate_trajectory(now)

    async def _async_maybe_refresh_outdoor_forecast(self, now: datetime) -> None:
        """Throttled fetch of the hourly outdoor-temperature forecast -
        see `_async_update_climate_forecast`'s docstring for why this is
        split from the (cheap, every-tick) trajectory recomputation.
        """
        if (
            self._climate_forecast_last_fetch is not None
            and (now - self._climate_forecast_last_fetch).total_seconds() / 60
            < CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES
        ):
            return
        self._climate_forecast_last_fetch = now

        weather_entity = self.config.get(CONF_KNMI_WEATHER_ENTITY) or self.config.get(
            CONF_OPENWEATHERMAP_WEATHER_ENTITY
        )
        if not weather_entity:
            self._climate_cached_forecast = None
            # v0.63.120: de reden wordt nu OOK in een eigen veld
            # bewaard, zodat `_recompute_climate_trajectory` hem elke
            # tick opnieuw kan tonen - deze fetch draait immers maar
            # eens per 30 minuten.
            self._climate_forecast_fetch_note = (
                "Geen knmi_weather_entity/openweathermap_weather_entity "
                "geconfigureerd - geen buitentemperatuur-voorspelling "
                "beschikbaar om de projectie op te baseren."
            )
            self.climate_forecast_note = self._climate_forecast_fetch_note
            return

        self._weer_opnieuw_proberen = False
        forecast = await self._async_fetch_hourly_outdoor_forecast(weather_entity)
        if self._weer_opnieuw_proberen:
            # v5.177.0 (A13): over WEER_OPNIEUW_MINUTEN opnieuw, niet pas na
            # het gewone interval.
            self._climate_forecast_last_fetch = now - timedelta(
                minutes=max(0, CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES - WEER_OPNIEUW_MINUTEN)
            )
        if not forecast:
            # v5.114.0: de vorige verwachting blijft gelden voor de uren die nog komen
            nog = [r for r in (self._climate_cached_forecast or []) if r and r[0] > now]
            self._climate_cached_forecast = nog or None
            self._climate_forecast_fetch_note = (
                "Kon geen uurlijkse buitentemperatuur-voorspelling ophalen "
                f"bij {weather_entity}."
            )
            self.climate_forecast_note = self._climate_forecast_fetch_note
            return
        self._climate_cached_forecast = forecast
        self._climate_forecast_fetch_note = None

        # v0.63.95: bias-sample - vergelijk de eerstvolgende voorspelde
        # waarde met de actuele achtertuinsensor-meting op ditzelfde
        # moment. Alleen relevant/mogelijk als er een achtertuinsensor
        # is geconfigureerd (anders zou dit de weerentiteit tegen
        # zichzelf vergelijken, zinloos). Loopt door het uitschieter-
        # filter (v0.63.96) - anders zou een kortstondige zonneflits op
        # de sensor de bias-leerhistorie kunnen vervuilen.
        backyard_entity = self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
        if backyard_entity and forecast:
            backyard_temp = self._get_filtered_backyard_temp_c(now)
            if backyard_temp is not None:
                _, nearest_forecast_temp = forecast[0]
                deviation_c = backyard_temp - nearest_forecast_temp
                self.climate_forecast_bias_history.append(round(deviation_c, 2))
                self.climate_forecast_bias_history = self.climate_forecast_bias_history[
                    -CLIMATE_FORECAST_BIAS_HISTORY_LENGTH:
                ]

    def _recompute_climate_trajectory(self, now: datetime) -> None:
        """Re-walks the 24-hour projection from the CURRENT
        live-measured living room temperature, using whichever outdoor
        forecast is currently cached (see
        `_async_maybe_refresh_outdoor_forecast`). Cheap, no network/
        service call - safe to run every tick, so the projection's
        starting point is always corrected to the actual measured
        value, not just whenever the forecast happens to be re-fetched
        (v0.63.58, requested).
        """
        self.climate_forecast_trajectory = []

        temp_c = self.living_room_current_temp_c
        if temp_c is None:
            # v0.63.120, gerapporteerd met screenshot van een INGEVULD
            # configuratieveld: "Maar ze staan wel ingevuld?" - de oude
            # tekst gooide "niet geconfigureerd" en "niet uitleesbaar"
            # op één hoop, waardoor een tijdelijk onbereikbare sensor
            # eruitzag als een configuratiefout. Nu twee losse,
            # accurate meldingen, met de entity_id erbij zodat direct
            # te zien is WELKE sensor het betreft.
            temp_entity = self.config.get(CONF_LIVING_ROOM_TEMPERATURE_SENSOR)
            if not temp_entity:
                self.climate_forecast_note = (
                    "Geen woonkamertemperatuur-sensor geconfigureerd - vul "
                    "'living_room_temperature_sensor_entity' in bij "
                    "Configureren om de projectie te activeren."
                )
            else:
                self.climate_forecast_note = (
                    f"Woonkamertemperatuur-sensor {temp_entity} is "
                    "geconfigureerd maar op dit moment niet uitleesbaar "
                    "(status 'unknown'/'unavailable' of geen getal). De "
                    "projectie start automatisch zodra de sensor weer "
                    "een waarde geeft."
                )
            return

        if not self._climate_cached_forecast:
            # v0.63.120: de reden NIET meer overlaten aan wat de fetch
            # ooit heeft achtergelaten. Die draait maar eens per 30
            # minuten, dus op alle tussenliggende ticks bleef hier de
            # melding van een VORIGE situatie staan - concreet: nadat
            # de temperatuursensor eenmalig kort onbereikbaar was
            # (bijv. tijdens het opstarten), bleef "geen
            # living_room_temperature_sensor_entity geconfigureerd of
            # niet uitleesbaar" eeuwig staan, ook toen die sensor
            # allang weer prima werkte en de werkelijke oorzaak de
            # ontbrekende buitentemperatuur-voorspelling was. Een
            # verkeerde diagnose die de zoekrichting compleet verlegt.
            self.climate_forecast_note = self._climate_forecast_fetch_note or (
                "Nog geen buitentemperatuur-voorspelling opgehaald - de "
                "projectie verschijnt zodra die beschikbaar is."
            )
            return

        shutter_state = self.climate_shutter_state or "onbekend"
        airco_state = self.climate_airco_state or "onbekend"

        # v0.63.95: geleerde bias-correctie op de HELE voorspelling
        # (niet alleen het startpunt), gebaseerd op de achtertuinsensor
        # - zie `climate_forecast_learned_bias_c`'s docstring.
        bias_c = self.climate_forecast_learned_bias_c or 0.0

        kort_termijn_temp = temp_c
        betrouwbaar_temp = temp_c
        trajectory = []
        for hour_dt, raw_outdoor_temp_c in self._climate_cached_forecast[
            :CLIMATE_FORECAST_HORIZON_HOURS
        ]:
            outdoor_temp_c = raw_outdoor_temp_c + bias_c
            # v3.41.0: het verschil met de kamer zoals die er op dit punt
            # van de projectie voor staat - dat is de grootheid die het
            # tempo bepaalt.
            outdoor_bucket = self._climate_verschil_bucket(
                outdoor_temp_c, betrouwbaar_temp
            )
            # v1.1.2: de twee reeksen gebruiken nu elk hun eigen bron.
            # De strenge reeks blijft uitsluitend op deze exacte cel
            # rekenen - dat is haar bestaansreden. De indicatieve reeks
            # mag terugvallen op een grovere samenvatting, want anders
            # bevriest ze maandenlang op vrijwel elk uur van de projectie
            # (252 mogelijke cellen, en de projectie loopt langs telkens
            # een ander buitentemperatuur-vakje).
            rate = self.get_climate_rate(outdoor_bucket, shutter_state, airco_state)
            indicatief = self.get_climate_rate_indicative(
                outdoor_bucket, shutter_state, airco_state
            )
            rate_value = rate["rate_c_per_hour"]
            indicatief_value = indicatief["rate_c_per_hour"]

            # v5.64: de geleerde windcorrectie erbovenop - zie `klimaat_wind`.
            # v5.66: en de zon - zie `klimaat_zon`.
            wind = self._windcorrectie(hour_dt, airco_state)
            zon = self._zoncorrectie(hour_dt, shutter_state, airco_state)
            if indicatief["voldoende_data"] and indicatief_value is not None:
                kort_termijn_temp += indicatief_value + (wind["c_per_uur"] or 0.0) + (zon["c_per_uur"] or 0.0)
            if rate["betrouwbaarheid"] == "betrouwbaar" and rate_value is not None:
                betrouwbaar_temp += rate_value + sum(
                    c["c_per_uur"] for c in (wind, zon) if c["betrouwbaar"]
                )

            trajectory.append(
                {
                    "tijd": hour_dt.isoformat(),
                    "buitentemp_voorspeld_c": round(outdoor_temp_c, 1),
                    "kort_termijn_temp_c": round(kort_termijn_temp, 1),
                    "betrouwbaar_temp_c": round(betrouwbaar_temp, 1),
                    # v0.63.94, gerapporteerd met screenshot: "de 2
                    # tabellen lijken hetzelfde weer te geven" - beide
                    # dashboardtabellen lazen tot nu toe hetzelfde,
                    # ene "betrouwbaarheid"-veld (het niveau voor de
                    # SOEPELE kort_termijn-drempel, ≥5 metingen), ook
                    # in de tabel die specifiek ≥15 metingen belooft.
                    # Een cel met bijv. 8 metingen toonde daardoor
                    # "indicatief" in BEIDE tabellen, terwijl de
                    # strengere tabel daar "onvoldoende_data" hoort te
                    # tonen (8 < 15). Nu twee aparte velden: het
                    # bestaande "betrouwbaarheid" blijft ongewijzigd
                    # (voor de kort-termijn-tabel), en een nieuw
                    # "betrouwbaarheid_streng" specifiek voor de
                    # betrouwbare-tabel - alleen "betrouwbaar" als de
                    # ≥15-drempel echt gehaald is, anders altijd
                    # "onvoldoende_data" (nooit "indicatief" daar, dat
                    # zou alsnog de verkeerde indruk wekken).
                    "betrouwbaarheid": indicatief["betrouwbaarheid"],
                    # v1.1.2: waarop de indicatieve schatting rust -
                    # exact deze cel, of een grovere samenvatting. Een
                    # terugval verzwijgen zou de indicatie
                    # geloofwaardiger laten lijken dan ze is.
                    "basis": indicatief["basis"],
                    "betrouwbaarheid_streng": (
                        "betrouwbaar"
                        if rate["betrouwbaarheid"] == "betrouwbaar"
                        else "onvoldoende_data"
                    ),
                    "aantal_metingen": rate["sample_count"],
                    "wind": wind["label"],
                    "windcorrectie_c_per_uur": wind["c_per_uur"],
                    "zon": zon["klasse"],
                    "zoncorrectie_c_per_uur": zon["c_per_uur"],
                }
            )

        self.climate_forecast_trajectory = trajectory
        self._onthoud_projectie(trajectory, now)
        self.climate_forecast_note = (
            "Adviserend - rolluikstand en airco-status worden voor de "
            "hele projectie constant gehouden op de huidige stand "
            "(onbekend wat die over enkele uren zijn). 'kort_termijn_"
            "temp_c' toont al een indicatie vanaf 5 samples per cel, "
            "'betrouwbaar_temp_c' pas vanaf 15 - beide bevriezen op het "
            "voorgaande uur zolang hun eigen drempel niet is gehaald, "
            "in plaats van te gokken. De projectie wordt elke tick "
            "opnieuw verankerd aan de actueel gemeten "
            "woonkamertemperatuur (de onderliggende buitentemperatuur-"
            "voorspelling wordt wél maar om de "
            f"{CLIMATE_FORECAST_FETCH_INTERVAL_MINUTES} minuten ververst). "
            "Stuurt nooit een commando."
        )

    def _airco_ronde(self, now: datetime) -> None:
        """Het airco-besluit van deze ronde (v5.27) - zie `airco_sturing`.

        Altijd berekend en zichtbaar; alleen met de knop "Airco automaat"
        aan wordt het uitgevoerd. Leert onderweg op welke temperatuur jullie
        de airco zetten als hij verwarmt, en herkent wanneer iemand hem zelf
        bedient: dan blijft het EMS eraf tot de aanwezigheid verandert.

        Alleen de woonkamer. De slaapkamer-airco wordt nooit aangeraakt.
        """
        entiteit = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        if not entiteit or entiteit == self.config.get(CONF_SLAAPKAMER_CLIMATE_ENTITY):
            self.last_airco_besluit = {
                "actie": "niets",
                "tekst": "Geen woonkamer-airco ingesteld.",
                "redenen": [], "redenen_tekst": "", "knop": self.airco_automaat_aan,
                "toegepast": False,
            }
            return
        toestand = self.hass.states.get(entiteit)
        stand = toestand.state if toestand else None
        doel_nu = toestand.attributes.get("temperature") if toestand else None
        gezien = (stand, doel_nu)
        vorige = self._airco_laatst_gezien
        self._airco_laatst_gezien = gezien
        ems = self._airco_laatste_ems
        door_ems = ems is not None and (ems.get("stand"), ems.get("doel")) == gezien
        # v5.208.0: een eigen automatisering (koken) is geen handbediening -
        # ook niet in de ronde direct na afloop, waarin hij terugzet.
        extern = self._airco_extern_bezig()
        extern_net = extern or self._airco_extern_vorige
        self._airco_extern_vorige = extern
        if vorige is not None and gezien != vorige and not door_ems and not extern_net:
            # Iemand bediende de airco zelf: dat gaat voor, tot de
            # aanwezigheid verandert - en wat hij nu doet is niet meer van het
            # EMS.
            self._airco_handmatig_bij = self.presence_state
            self.airco_door_ems = False
            # v5.65: en het dagritme leert ervan - zie `airco_ritme`.
            airco_ritme.noteer_bediening(self._airco_ritme(), now, stand, doel_nu)
            if stand == "heat" and doel_nu is not None:
                self.airco_setpunten = (list(self.airco_setpunten or []) + [float(doel_nu)])[
                    -AIRCO_PREDICTION_HISTORY_LENGTH:
                ]
        if self._airco_handmatig_bij is not None and self.presence_state != self._airco_handmatig_bij:
            self._airco_handmatig_bij = None
        bakjes = (self.get_airco_kansen_per_bakje() or {}).get("bakjes") or {}
        uit = airco_sturing.besluit(
            woonkamer_c=self.living_room_current_temp_c,
            aanwezigheid=self.presence_state,
            aanzet_c=airco_sturing.aanzettemperatuur(bakjes),
            doel_c=airco_sturing.gewenste_temperatuur(
                self.airco_setpunten, AIRCO_PREDICTION_MIN_SAMPLES
            ),
            advies=(self.get_verwarmingsadvies() or {}).get("advies"),
            handmatig=self._airco_handmatig_bij is not None,
            airco_stand=stand,
            door_ems_aan=self.airco_door_ems,
            setpunten_gezien=len(self.airco_setpunten or []),
            setpunten_nodig=AIRCO_PREDICTION_MIN_SAMPLES,
            vooruit=self._airco_vooruitblik(),
            # v5.171.0 (L-EMS-057): geen nachtstart na de vaste uit
            nachtrust=airco_sturing.in_nachtrust(
                airco_ritme.minuut(now),
                airco_ritme.minuten_uit_klok(
                    self.instelling(CONF_AIRCO_UIT_OM, DEFAULT_AIRCO_UIT_OM)
                ),
                airco_ritme.OCHTEND_VAN,
            ),
            # v5.177.0 (A16): 's ochtends alleen verwarmen als jullie dat doen
            ochtend=airco_ritme.ochtend_kans(self._airco_ritme(), now),
        )
        uit = self._airco_ritme_ronde(now, uit, stand)
        uit = self._airco_kort_weg_ronde(now, uit)
        uit = self._airco_weg_ronde(now, uit, stand, doel_nu)
        uit = self._airco_thuiskomst_ronde(now, uit, stand)
        uit = self._airco_zon_ronde(now, self._airco_buffer_ronde(now, uit, stand), stand)
        # v5.208.0: zolang de eigen automatisering loopt, stelt het EMS het doel
        # van een airco die al verwarmt niet bij; uitzetten mag wel.
        if extern and uit.get("actie") == "verwarmen" and stand == "heat":
            redenen = list(uit.get("redenen") or []) + ["een eigen automatisering bedient de airco"]
            uit = dict(
                uit, actie="niets", redenen=redenen, redenen_tekst=" · ".join(redenen),
                tekst="Een eigen automatisering bedient de airco; het EMS wacht tot die klaar is.",
            )
        # v5.195.0: niet kort schakelen (vóór de raamregel: een open raam gaat voor)
        uit = airco_sturing.niet_kort_schakelen(uit, getattr(self, "_airco_geschakeld", None), now)
        # v5.77: als laatste - een raam open en de airco gaat nooit aan.
        uit = airco_sturing.raam_open(
            uit,
            self._airco_ramen(),
            airco_stand=stand,
            door_ems_aan=self.airco_door_ems,
            open_sinds_s=self._airco_raam_open_sinds_s(now),
            uitstel_s=AIRCO_RAAM_UITSTEL_S,
        )
        uit["knop"] = self.airco_automaat_aan
        # v5.67.2: de vaste uittijd geldt ook met de knop uit.
        uit["toegepast"] = bool(
            (self.airco_automaat_aan or uit.get("altijd")) and uit["actie"] in ("verwarmen", "uit")
        )
        # Een regel voor het dashboard - tekst uit de code, niet uit een sjabloon.
        uit["status_tekst"] = (
            "Uitgevoerd."
            if uit["toegepast"]
            else (
                "Niet uitgevoerd: de knop Airco automaat staat uit."
                if uit["actie"] in ("verwarmen", "uit")
                else ("Knop aan." if self.airco_automaat_aan else "Knop uit.")
            )
        )
        uit["samenvatting"] = f"{uit['tekst']} {uit['status_tekst']} ({uit['redenen_tekst']})"
        uit["moment"] = now.isoformat()
        self.last_airco_besluit = uit
        if uit["toegepast"]:
            self.hass.async_create_task(self._async_pas_airco_toe(entiteit, uit))

    _airco_extern_vorige: bool = False

    def _airco_extern_bezig(self) -> bool:
        """Een eigen automatisering stelt de airco nu bij (v5.208.0) - zie
        `CONF_AIRCO_EXTERN_ENTITY`."""
        entiteit = self.config.get(CONF_AIRCO_EXTERN_ENTITY)
        if not entiteit:
            return False
        toestand = self.hass.states.get(entiteit)
        return toestand is not None and toestand.state == "on"

    def _airco_ramen(self) -> dict:
        """De ramen van woonkamer en keuken (v5.77) - zie `airco_sturing.ramen`."""
        toestanden = []
        for entiteit in self.config.get(CONF_AIRCO_RAAM_ENTITIES) or []:
            toestand = self.hass.states.get(entiteit)
            naam = (
                toestand.attributes.get("friendly_name") if toestand is not None else None
            ) or entiteit
            toestanden.append((naam, toestand.state if toestand is not None else None))
        return airco_sturing.ramen(toestanden)

    def _airco_raam_open_sinds_s(self, now) -> float | None:
        """Hoe lang (s) het langst openstaande raam al open is (v5.78)."""
        sinds = None
        for entiteit in self.config.get(CONF_AIRCO_RAAM_ENTITIES) or []:
            toestand = self.hass.states.get(entiteit)
            if toestand is None or toestand.state != "on":
                continue
            gewijzigd = getattr(toestand, "last_changed", None)
            if gewijzigd is None:
                continue
            duur = (now - gewijzigd).total_seconds()
            sinds = duur if sinds is None else max(sinds, duur)
        return sinds

    def _airco_ritme(self) -> dict:
        """Het geleerde dagritme, altijd in een bruikbare vorm (v5.65)."""
        self.airco_ritme = airco_ritme.geldig(self.airco_ritme)
        return self.airco_ritme

    def _airco_opwarmtempo(
        self, buiten_c: float | None = None, binnen_c: float | None = None
    ) -> float | None:
        """Hoe snel de airco de woonkamer opwarmt (°C per uur): de mediaan
        van alle geleerde klimaatmetingen met de airco op verwarmen (v5.65).

        v5.97.0 (Ruud 14-10: "houdt de airco-voorspelling rekening met de
        buitentemperatuur de komende uren?"): met een buiten- en
        binnentemperatuur erbij eerst het tempo uit het vakje van dat
        verschil - op een koude ochtend warmt de airco langzamer op dan
        gemiddeld. Te weinig metingen in dat vakje: het algemene tempo."""
        cellen = self.climate_rate_history or {}
        if buiten_c is not None and binnen_c is not None:
            vak = self._climate_verschil_bucket(buiten_c, binnen_c)
            eigen = [
                w
                for sleutel, reeks in cellen.items()
                if str(sleutel).startswith(f"{vak}|") and str(sleutel).endswith("|verwarmen")
                for w in reeks
            ]
            if len(eigen) >= CLIMATE_RATE_MIN_SAMPLES:
                tempo = statistics.median(eigen)
                if tempo > 0:
                    return tempo
        waarden = [
            w
            for sleutel, reeks in cellen.items()
            if str(sleutel).endswith("|verwarmen")
            for w in reeks
        ]
        if len(waarden) < CLIMATE_RATE_MIN_SAMPLES:
            return None
        tempo = statistics.median(waarden)
        return tempo if tempo > 0 else None

    def _buiten_verwacht_op(self, moment: datetime) -> float | None:
        """De voorspelde buitentemperatuur in het uur van `moment` (v5.97.0),
        uit dezelfde projectie als `_woonkamer_verwacht_op`."""
        uur = moment.strftime("%Y-%m-%dT%H")
        for regel in self.climate_forecast_trajectory or []:
            if str(regel.get("tijd") or "")[:13] == uur:
                return regel.get("buitentemp_voorspeld_c")
        return None

    def _airco_ochtend_tempo(self, now: datetime) -> float | None:
        """Het opwarmtempo voor de eerstvolgende ochtend (v5.97.0): bij de
        verwachte buitentemperatuur op het geleerde warm-moment en de
        verwachte woonkamertemperatuur van dat moment."""
        try:
            # Alleen lezen: `_airco_ritme()` zou het opgeslagen ritme
            # vervangen terwijl de ronde het nog bijwerkt.
            ritme = airco_ritme.geldig(self.airco_ritme)
            lokaal = dt_util.as_local(now)
            for dagen in (0, 1):
                datum = lokaal + timedelta(days=dagen)
                leer = airco_ritme.geleerd(ritme, airco_ritme.dagsoort(datum))
                warm_om = leer.get("warm_om")
                if warm_om is None:
                    continue
                moment = datum.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                    minutes=int(warm_om)
                )
                if moment + timedelta(minutes=airco_ritme.NA_WARM_OM_MIN) < lokaal:
                    continue
                return self._airco_opwarmtempo(
                    self._buiten_verwacht_op(moment),
                    self._woonkamer_verwacht_op(moment),
                )
        except Exception:  # noqa: BLE001 - een tempo mag de sturing niet breken
            pass
        return self._airco_opwarmtempo()

    def _airco_tempo_nu(self) -> float | None:
        """Het opwarmtempo van dit moment (v5.97.0): buiten volgens het
        eerste uur van de projectie, binnen gemeten."""
        traject = self.climate_forecast_trajectory or []
        buiten = traject[0].get("buitentemp_voorspeld_c") if traject else None
        return self._airco_opwarmtempo(buiten, self.living_room_current_temp_c)

    def _woonkamer_verwacht_om(self, minuut: int) -> float | None:
        """De voorspelde woonkamertemperatuur op een minuut van vandaag (v5.65)."""
        middernacht = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return self._woonkamer_verwacht_op(middernacht + timedelta(minutes=minuut))

    def _woonkamer_verwacht_op(self, moment: datetime) -> float | None:
        """De voorspelde woonkamertemperatuur in het uur van `moment` (v5.67)."""
        uur = moment.strftime("%Y-%m-%dT%H")
        for regel in self.climate_forecast_trajectory or []:
            if str(regel.get("tijd") or "")[:13] == uur:
                return regel.get("kort_termijn_temp_c")
        return None

    def _airco_vermogen_w(self) -> float | None:
        """Het vermogen van de woonkamer-airco in W (v5.67): de ingestelde
        sensor, of vanzelf gevonden bij hetzelfde apparaat als de airco - een
        sensor in W of kW met "power" in de naam."""
        # v5.200.0: zonder ingestelde sensor het vermogen uit de
        # compressorfrequentie (de Daikin-schatting springt 0-5 kW).
        if not self.config.get(CONF_AIRCO_POWER_SENSOR):
            hz = self._airco_bron_waarde("frequentie")
            if hz is not None:
                # alleen lezen: `_airco_ritme()` zou het ritme vervangen
                # terwijl een ronde het bijwerkt
                return airco_frequentie.vermogen_w((self.airco_ritme or {}).get("frequentie"), hz)
        entiteit = self.config.get(CONF_AIRCO_POWER_SENSOR) or getattr(self, "_airco_vermogen_gevonden", None)
        if entiteit is None and not getattr(self, "_airco_vermogen_gezocht", False):
            self._airco_vermogen_gezocht = True
            entiteit = self._airco_vermogen_gevonden = self._zoek_airco_vermogen()
        toestand = self.hass.states.get(entiteit) if entiteit else None
        if toestand is None:
            return None
        waarde = klimaat_wind.naar_kmh(toestand.state, None)
        if waarde is None:
            return None
        return waarde * 1000 if toestand.attributes.get("unit_of_measurement") == "kW" else waarde

    _airco_bronnen: dict | None = None

    def _airco_bron_waarde(self, soort: str) -> float | None:
        """v5.200.0: de compressorfrequentie (Hz) of de energieteller van de
        compressor (kWh) van de woonkamer-airco, vanzelf gevonden bij
        hetzelfde apparaat. None als die er niet is of niets meldt."""
        if not self._airco_bronnen:
            # nog niets gevonden (register nog niet klaar): hooguit 20 keer zoeken
            self._airco_bronnen_pogingen = getattr(self, "_airco_bronnen_pogingen", 0) + 1
            if self._airco_bronnen_pogingen > 20:
                return None
            self._airco_bronnen = self._zoek_airco_bronnen()
        entiteit = self._airco_bronnen.get(soort)
        toestand = self.hass.states.get(entiteit) if entiteit else None
        if toestand is None:
            return None
        try:
            return float(toestand.state)
        except (TypeError, ValueError):
            return None

    def _zoek_airco_bronnen(self) -> dict:
        gevonden: dict = {}
        try:
            from homeassistant.helpers import entity_registry as er

            register = er.async_get(self.hass)
            airco = register.async_get(self.config.get(CONF_AIRCO_CLIMATE_ENTITY) or "")
            if airco is None or not airco.device_id:
                return gevonden
            for item in er.async_entries_for_device(register, airco.device_id):
                toestand = self.hass.states.get(item.entity_id)
                eenheid = toestand.attributes.get("unit_of_measurement") if toestand else None
                if not item.entity_id.startswith("sensor."):
                    continue
                if "compressor_frequency" in item.entity_id and eenheid == "Hz":
                    gevonden["frequentie"] = item.entity_id
                elif "compressor_energy" in item.entity_id and eenheid == "kWh":
                    gevonden["teller"] = item.entity_id
        except Exception:  # noqa: BLE001 - zoeken mag de ronde nooit breken
            return {}
        return gevonden

    def get_airco_vermogen(self) -> dict:
        """v5.202.0: het berekende airco-vermogen en wat erachter zit, voor
        de sensor "Airco vermogen (berekend)", de cockpit en de diagnose."""
        try:
            model = (self.airco_ritme or {}).get("frequentie") or {}
            hz = self._airco_bron_waarde("frequentie")
            ingesteld = self.config.get(CONF_AIRCO_POWER_SENSOR)
            a, b, geleerd = airco_frequentie.coefficienten(model)
            houd = airco_frequentie.houd_w_per_graad(model)
            opwarm = airco_frequentie.opwarm_kw(model)
            loop = self._airco_freq_loop
            return {
                "vermogen_w": round(self._airco_vermogen_w(), 0) if self._airco_vermogen_w() is not None else None,
                "bron": (
                    "ingestelde sensor" if ingesteld
                    else "compressorfrequentie" if hz is not None
                    else "Daikin-schatting" if self._airco_vermogen_w() is not None
                    else "geen"
                ),
                "frequentie_hz": hz,
                "w_per_hz": round(a, 1),
                "basis_w": round(b, 0),
                "omrekening_geleerd": geleerd,
                "meetvensters": len(model.get("vensters") or []),
                "meetvensters_nodig": airco_frequentie.VENSTERS_MIN,
                "opwarm_kw": round(opwarm, 2) if opwarm is not None else None,
                "opwarm_metingen": len(model.get("opwarm_w") or []),
                "warm_houden_w_per_graad": round(houd, 1) if houd is not None else None,
                "warm_houden_metingen": len(model.get("houd_w_per_graad") or []),
                "teller_vandaag_kwh": self._airco_bron_waarde("teller"),
                "geteld_sinds_start_kwh": (
                    round(airco_frequentie.stand_kwh(loop), 2)
                    if loop is not None and airco_frequentie.stand_kwh(loop) is not None else None
                ),
                "bronnen": dict(self._airco_bronnen or {}),
            }
        except Exception as err:  # noqa: BLE001 - een overzicht mag nooit breken
            return {"vermogen_w": None, "fout": str(err)}

    _airco_freq_loop: dict | None = None
    _airco_freq_vorige: tuple | None = None

    def _noteer_airco_frequentie(self, now: datetime, ritme: dict) -> None:
        """v5.200.0: model bijleren uit de teller, opwarmen en vasthouden
        meten - zie `airco_frequentie.ronde`."""
        hz = self._airco_bron_waarde("frequentie")
        if hz is None:
            return
        if self._airco_freq_loop is None:
            self._airco_freq_loop = airco_frequentie.nieuwe_teller()
        vorige = self._airco_freq_vorige
        self._airco_freq_vorige = (now, hz)
        if vorige is None:
            uren = 0.0
            hz_vorig = hz
        else:
            uren = (now - vorige[0]).total_seconds() / 3600
            hz_vorig = vorige[1]
        entiteit = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        toestand = self.hass.states.get(entiteit) if entiteit else None
        doel = toestand.attributes.get("temperature") if toestand else None
        try:
            buiten = self._airco_buiten_nu(now)
        except Exception:  # noqa: BLE001
            buiten = None
        airco_frequentie.ronde(
            ritme["frequentie"], self._airco_freq_loop,
            hz=hz_vorig,
            teller_kwh=self._airco_bron_waarde("teller"),
            uren=uren,
            binnen_c=self.living_room_current_temp_c,
            buiten_c=buiten,
            doel_c=float(doel) if isinstance(doel, (int, float)) else None,
            verwarmt=toestand is not None and toestand.state == "heat",
        )

    def _zoek_airco_vermogen(self) -> str | None:
        try:
            from homeassistant.helpers import entity_registry as er

            register = er.async_get(self.hass)
            airco = register.async_get(self.config.get(CONF_AIRCO_CLIMATE_ENTITY) or "")
            if airco is None or not airco.device_id:
                return None
            for item in er.async_entries_for_device(register, airco.device_id):
                toestand = self.hass.states.get(item.entity_id)
                if (
                    item.entity_id.startswith("sensor.") and "power" in item.entity_id
                    and toestand is not None
                    and toestand.attributes.get("unit_of_measurement") in ("W", "kW")
                ):
                    return item.entity_id
        except Exception:  # noqa: BLE001 - zoeken mag de ronde nooit breken
            return None
        return None

    _airco_uur_stand: tuple | None = None

    def _noteer_airco_verbruik(self, now: datetime, ritme: dict) -> None:
        """Vermogen en verbruik per klokuur van de airco bijhouden (v5.67)."""
        vermogen_w = self._airco_vermogen_w()
        if vermogen_w is None:
            return
        airco_ritme.noteer_vermogen(ritme, vermogen_w)
        uur = now.replace(minute=0, second=0, microsecond=0)
        vorige = self._airco_uur_acc
        if vorige is None or vorige[0] != uur:
            stand = (
                airco_frequentie.stand_kwh(self._airco_freq_loop)
                if self._airco_freq_loop is not None else None
            )
            begin = self._airco_uur_stand
            if vorige is not None and uur - vorige[0] == timedelta(hours=1):
                staart = (uur - vorige[2]).total_seconds() / 3600
                laatste = vorige[3] / 1000 * staart if 0 <= staart <= 0.5 else 0.0
                kwh_uur = vorige[1] + laatste
                # v5.200.0: uit de energieteller als die het hele uur liep
                if stand is not None and begin is not None and begin[0] == vorige[0] and stand >= begin[1]:
                    kwh_uur = stand - begin[1]
                airco_ritme.noteer_uur(ritme, vorige[0].hour, kwh_uur,
                                       buiten_c=self._airco_buiten_nu(now))
            self._airco_uur_stand = (uur, stand) if stand is not None else None
            self._airco_uur_acc = (uur, 0.0, now, vermogen_w)
            return
        _, kwh, t0, w0 = vorige
        uren = (now - t0).total_seconds() / 3600
        if 0 < uren <= 0.5:
            kwh += w0 / 1000 * uren
        self._airco_uur_acc = (uur, kwh, now, vermogen_w)

    def _airco_buiten_nu(self, now: datetime) -> float | None:
        """v5.107.0: de buitentemperatuur nu (eigen sensor, anders de
        verwachting) - voor het uurverbruik van de airco."""
        try:
            gemeten = self._get_filtered_backyard_temp_c(now)
        except Exception:  # noqa: BLE001
            gemeten = None
        return gemeten if gemeten is not None else self._buiten_verwacht_c(now)

    def _buiten_verwacht_c(self, moment: datetime) -> float | None:
        """v5.107.0: de verwachte buitentemperatuur op dit uur, uit de
        uurverwachting die de klimaatprojectie al ophaalt."""
        reeks = getattr(self, "_climate_cached_forecast", None) or []
        beste = None
        for tijd, temp in reeks:
            try:
                afstand = abs((tijd - moment).total_seconds())
            except TypeError:
                continue
            if afstand <= 5400 and (beste is None or afstand < beste[0]):
                beste = (afstand, temp)
        return float(beste[1]) if beste is not None and beste[1] is not None else None

    def _airco_tempfactor(self, ritme: dict):
        """v5.107.0: de temperatuurfactor per uur (zie airco_ritme)."""

        def factor(moment: datetime) -> float:
            return airco_ritme.temperatuurfactor(ritme, moment.hour, self._buiten_verwacht_c(moment))

        return factor

    def _airco_thuisfactor(self, now: datetime):
        """v5.107.0: hoe waarschijnlijk is er iemand thuis in dit uur,
        vergeleken met een gemiddelde dag? (functie per uur)

        - per dag van de week: de geleerde thuis-kans van dit uur op DEZE
          weekdag gedeeld door die over alle dagen (tussen 0 en 1,5);
        - staat het huis NU op "weg": tot het eerste halfuur waarop jullie op
          deze dag meestal (>= 50 %) thuis zijn, telt de airco niet. Zonder
          geleerd patroon hooguit het eerstvolgende uur, zodat de reserve
          nooit langer dan dat op een onbekende thuiskomst gokt.
        """
        profiel = self.presence_week_profile or {}

        def kans(dag: int, uur: int, half: str) -> float | None:
            aan, totaal = (profiel.get(f"{dag}-{uur:02d}{half}") or [0, 0])
            return aan / totaal if totaal >= PRESENCE_MIN_OBSERVATIONS else None

        def uur_kans(dag: int, uur: int) -> float | None:
            waarden = [k for k in (kans(dag, uur, "00"), kans(dag, uur, "30")) if k is not None]
            return sum(waarden) / len(waarden) if waarden else None

        terug_om = None
        if self.presence_state == "weg":
            terug_om = now + timedelta(hours=1)
            stap = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
            for _ in range(48):
                stap += timedelta(minutes=30)
                k = kans(stap.weekday(), stap.hour, "30" if stap.minute >= 30 else "00")
                if k is not None and k >= 0.5:
                    terug_om = stap
                    break

        def factor(uur: datetime) -> float:
            if terug_om is not None and uur + timedelta(hours=1) <= terug_om:
                return 0.0
            deze = uur_kans(uur.weekday(), uur.hour)
            alle = [k for d in range(7) if (k := uur_kans(d, uur.hour)) is not None]
            if deze is None or not alle:
                return 1.0
            gemiddeld = sum(alle) / len(alle)
            if gemiddeld < 0.05:
                return 1.0
            return round(min(max(deze / gemiddeld, 0.0), 1.5), 3)

        return factor

    def _airco_ochtend_extra_kwh(self, now: datetime, tot: datetime) -> dict:
        """De ochtendverwarming in de nachtplanning (v5.67) - zie
        `airco_ritme.nacht_extra_kwh`. Alleen met de knop Airco automaat aan:
        anders stookt het EMS 's ochtends niet."""
        if not self.airco_automaat_aan or tot <= now:
            return {"extra_kwh": 0.0, "verwacht_kwh": 0.0, "al_in_profiel_kwh": 0.0}
        return airco_ritme.nacht_extra_kwh(
            self._airco_ritme(), now, tot, self._woonkamer_verwacht_op, self._airco_ochtend_tempo(now)
        )

    def _airco_gebruik_extra_kwh(self, now: datetime, tot: datetime) -> dict:
        """Het verwachte airco-gebruik in de reserve (v5.83) - zie
        `airco_ritme.gebruik_kwh`. Ook met de knop Airco automaat uit: dan
        zetten jullie hem zelf aan, en dat verbruik is er net zo goed. Met de
        knop aan blijft de ochtend bij `_airco_ochtend_extra_kwh`."""
        leeg = {"extra_kwh": 0.0, "verwacht_kwh": 0.0, "al_in_profiel_kwh": 0.0, "uren": []}
        if tot is None or tot <= now:
            return leeg
        try:
            loopt, loopt_tot = self._airco_loopt_tot(now)
            ritme = self._airco_ritme()
            return airco_ritme.gebruik_kwh(
                ritme, now, tot,
                zonder_ochtend=bool(self.airco_automaat_aan),
                loopt_nu=loopt, loopt_tot=loopt_tot,
                thuis_factor=self._airco_thuisfactor(now),
                temp_factor=self._airco_tempfactor(ritme),
            )
        except Exception:  # noqa: BLE001 - de reserve mag hier nooit op breken
            return leeg

    # --- v5.186.0 (punt 34): de klimaat-extra's ook in de planenergie ------
    #
    # De airco-extra's (ochtendverwarming, verwacht gebruik) en het
    # temperatuurmodel zaten alleen in de reserve (`_bereken_dynamische_reserve_kwh`),
    # niet in het verbruik van de plankwartieren. Het plan liet de accu dan
    # langzamer leeglopen dan de reserve (de vloer) aannam. Nu per uur verdeeld.

    def _klimaat_extra_kwh_in(self, van: datetime, tot: datetime) -> float:
        """De klimaat-extra's die in [van, tot) vallen (v5.186.0, punt 34)."""
        try:
            kaart = self._klimaat_extra_per_uur()
        except Exception:  # noqa: BLE001 - het plan mag hier nooit op breken
            _LOGGER.debug("Klimaat-extra's per uur niet bepaald", exc_info=True)
            return 0.0
        totaal = 0.0
        for kwh, a, b in kaart:
            if b <= van or a >= tot or kwh <= 0:
                continue
            lengte = (b - a).total_seconds()
            if lengte > 0:
                totaal += kwh * (min(b, tot) - max(a, van)).total_seconds() / lengte
        return totaal

    def _klimaat_extra_per_uur(self) -> list[tuple[float, datetime, datetime]]:
        """(kWh, van, tot) per stuk; per ronde en minuut één keer berekend."""
        now = dt_util.now()
        sleutel = (getattr(self, "_forecast_cache_ronde", None), now.replace(second=0, microsecond=0))
        bewaard = getattr(self, "_klimaat_extra_cache", None)
        if bewaard is not None and bewaard[0] == sleutel:
            return bewaard[1]
        from .const import WAARDEPLAN_HORIZON_UUR

        tot = now + timedelta(hours=WAARDEPLAN_HORIZON_UUR + 1)
        stukken = self._airco_extra_stukken(now, tot)
        stukken += self._temperatuur_extra_stukken(now, tot, stukken)
        self._klimaat_extra_cache = (sleutel, stukken)
        return stukken

    def _airco_extra_stukken(self, now: datetime, tot: datetime) -> list:
        """Het verwachte airco-gebruik per uur en de ochtendverwarming,
        verdeeld naar het uur waarin die verwarmt."""
        stukken = []
        for u in self._airco_gebruik_extra_kwh(now, tot).get("uren") or []:
            begin = datetime.fromisoformat(u["begin"]) if u.get("begin") else None
            if begin is not None:
                stukken.append((float(u["kwh"]), max(begin, now), min(begin + timedelta(hours=1), tot)))
        ochtend = self._airco_ochtend_extra_kwh(now, tot).get("extra_kwh") or 0.0
        if ochtend > 0:
            ritme, tempo = self._airco_ritme(), self._airco_ochtend_tempo(now)
            per_uur = []
            uur = now.replace(minute=0, second=0, microsecond=0)
            while uur < tot:
                a, b = max(uur, now), min(uur + timedelta(hours=1), tot)
                per_uur.append((airco_ritme.ochtend_kwh(ritme, a, b, self._woonkamer_verwacht_op, tempo), a, b))
                uur += timedelta(hours=1)
            som = sum(k for k, _a, _b in per_uur)
            if som > 0:
                stukken += [(ochtend * k / som, a, b) for k, a, b in per_uur if k > 0]
        return stukken

    def _temperatuur_extra_stukken(self, now: datetime, tot: datetime, airco: list) -> list:
        """Het temperatuurmodel per nacht (VASTE_NACHT_VAN_UUR-VASTE_NACHT_TOT_UUR,
        het venster waarop het model leert), gelijk over de nacht verdeeld."""
        from .const import VASTE_NACHT_TOT_UUR, VASTE_NACHT_VAN_UUR

        stukken = []
        dag = (now - timedelta(days=1)).replace(hour=VASTE_NACHT_VAN_UUR, minute=0, second=0, microsecond=0)
        while dag < tot:
            a = max(dag, now)
            b = min((dag + timedelta(days=1)).replace(hour=VASTE_NACHT_TOT_UUR), tot)
            if b > a:
                al = sum(
                    k * max(0.0, (min(y, b) - max(x, a)).total_seconds()) / max(1.0, (y - x).total_seconds())
                    for k, x, y in airco
                )
                extra = self._temperatuur_extra_kwh(a, b, al).get("extra_kwh") or 0.0
                if extra > 0:
                    stukken.append((extra, a, b))
            dag += timedelta(days=1)
        return stukken

    def _airco_loopt_tot(self, now: datetime) -> tuple[bool, datetime | None]:
        """Draait de airco nu, en tot wanneer telt hij als zeker (v5.83; uit
        `_airco_gebruik_extra_kwh` gehaald in v5.186.0)."""
        vermogen = self._airco_vermogen_w()
        loopt = vermogen is not None and vermogen >= airco_ritme.VERMOGEN_AAN_W
        if not loopt:
            return False, None
        m = airco_ritme.minuten_uit_klok(self.instelling(CONF_AIRCO_UIT_OM, DEFAULT_AIRCO_UIT_OM))
        if m is None:
            return True, None
        grens = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=m)
        loopt_tot = grens if grens > now else now.replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
        return True, loopt_tot

    def _airco_zeker_meegeteld(self, now: datetime) -> bool:
        """Telt de draaiende airco nu als zeker in de airco-extra's? (v5.186.0,
        punt 35). Dan hoort hij niet ook in de live verbruikscorrectie."""
        try:
            loopt, loopt_tot = self._airco_loopt_tot(now)
        except Exception:  # noqa: BLE001 - bij twijfel het oude gedrag
            return False
        return loopt and loopt_tot is not None and loopt_tot > now

    def _airco_kost_per_uur(self, now: datetime, ritme: dict):
        """Wat een uur verwarmen op vol vermogen vanaf een minuut van vandaag
        kost (v5.192.0, L-EMS-074): kwartierprijs x vermogen, gecorrigeerd voor
        het rendement bij de voorspelde buitentemperatuur (t.o.v. nu). None als
        er geen prijs is; dan blijft het opwarmmoment zoals het was."""
        from .slimme_bronnen import cop_bij

        vermogen = airco_ritme.verwarmvermogen_kw(ritme) or 1.0
        cop_opties = dict(
            cop_bij_7c=self.instelling(CONF_AIRCO_COP_BIJ_7C, None),
            cop_per_graad=self.instelling(CONF_AIRCO_COP_PER_GRAAD, DEFAULT_AIRCO_COP_PER_GRAAD),
        )
        try:
            buiten_nu = self._get_live_outdoor_temp_c(now)
        except Exception:  # noqa: BLE001
            buiten_nu = None
        cop_nu = cop_bij(buiten_nu, **cop_opties)
        middernacht = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cache: dict = {}

        def kost(minuut: int):
            if minuut in cache:
                return cache[minuut]
            moment = middernacht + timedelta(minutes=minuut)
            try:
                prijs = self.huidige_prijs_eur_per_kwh(moment)
            except Exception:  # noqa: BLE001
                prijs = None
            if prijs is None:
                cache[minuut] = None
                return None
            try:
                buiten = self._voorspelde_buitentemp_c(moment, moment + timedelta(minutes=15))
            except Exception:  # noqa: BLE001
                buiten = None
            cop = cop_bij(buiten if buiten is not None else buiten_nu, **cop_opties)
            cache[minuut] = float(prijs) * vermogen * (cop_nu / cop if cop else 1.0)
            return cache[minuut]

        return kost

    def _airco_ritme_ronde(self, now: datetime, uit: dict, stand: str | None) -> dict:
        """Het dagritme naast het gewone besluit (v5.65) - zie `airco_ritme`.

        - bedtijd: "uit" gaat voor, ook als iemand hem zelf aanzette (één keer
          per avond);
        - ochtend: "verwarmen" alleen als het gewone besluit niets doet en
          niemand de airco zelf bedient;
        - ochtendverwarming loopt: een "uit" omdat iedereen nog slaapt, wordt
          tegengehouden tot een uur na het geleerde moment.
        """
        ritme = self._airco_ritme()
        if self.presence_state not in (None, "weg"):
            airco_ritme.noteer_ochtend_thuis(ritme, now)
        if self.presence_state == "thuis":
            airco_ritme.noteer_dag_thuis(ritme, now)
        self._noteer_airco_frequentie(now, ritme)
        self._noteer_airco_verbruik(now, ritme)
        vraag = airco_ritme.besluit(
            ritme,
            nu=now,
            woonkamer_c=self.living_room_current_temp_c,
            verwacht_bij_warm_om=self._woonkamer_verwacht_om,
            tempo_c_per_uur=self._airco_ochtend_tempo(now),
            aanwezigheid=self.presence_state,
            advies=(self.get_verwarmingsadvies() or {}).get("advies"),
            airco_stand=stand,
            bedtijd_vast=airco_ritme.minuten_uit_klok(self.instelling(CONF_AIRCO_UIT_OM, DEFAULT_AIRCO_UIT_OM)),
            kost_per_uur=self._airco_kost_per_uur(now, ritme),
        )
        if vraag is None:
            # v5.101: overdag en 's avonds - zie `airco_ritme.besluit_dag`
            vraag = airco_ritme.besluit_dag(
                ritme,
                nu=now,
                woonkamer_c=self.living_room_current_temp_c,
                verwacht_om=self._woonkamer_verwacht_om,
                tempo_c_per_uur=self._airco_ochtend_tempo(now),
                aanwezigheid=self.presence_state,
                advies=(self.get_verwarmingsadvies() or {}).get("advies"),
                airco_stand=stand,
                kost_per_uur=self._airco_kost_per_uur(now, ritme),
            )
        if vraag is None:
            return uit
        if vraag.get("markeer_uit") and (
            self.airco_automaat_aan or vraag.get("altijd") or vraag["actie"] != "uit"
        ):
            airco_ritme.noteer_ems_uit(ritme, now)
        if not vraag["reden"]:
            return uit
        nieuw = dict(uit)
        nieuw["redenen"] = list(uit.get("redenen") or []) + [vraag["reden"]]
        nieuw["redenen_tekst"] = " · ".join(nieuw["redenen"])
        if vraag["actie"] == "uit":
            nieuw.update(actie="uit", tekst=vraag["tekst"], altijd=bool(vraag.get("altijd")))
        elif vraag.get("houd_aan"):
            if uit["actie"] == "uit":
                nieuw.update(actie="niets", tekst=vraag["tekst"])
        elif uit["actie"] == "niets" and self._airco_handmatig_bij is None:
            nieuw.update(actie="verwarmen", tekst=vraag["tekst"], doel_c=vraag["doel_c"])
            if self.airco_automaat_aan:
                if vraag.get("dag"):
                    airco_ritme.noteer_ems_dag_aan(ritme, now)
                else:
                    airco_ritme.noteer_ems_aan(ritme, now)
        return nieuw

    def _nadering(self) -> tuple[str | None, float | None]:
        """Richting en afstand (km) van wie het dichtst bij huis is, uit de
        Home Assistant-integratie Nabijheid (v5.66). Vanzelf gevonden: de
        sensor die eindigt op `_nearest_direction_of_travel`."""
        bekend = getattr(self, "_nadering_entiteit", None)
        kandidaten = [self.hass.states.get(bekend)] if bekend else self.hass.states.async_all()
        for toestand in kandidaten:
            if toestand is None or not toestand.entity_id.startswith("sensor.") or not (
                toestand.entity_id.endswith("_nearest_direction_of_travel")
            ):
                continue
            self._nadering_entiteit = toestand.entity_id
            afstand = self.hass.states.get(
                toestand.entity_id.replace("_direction_of_travel", "_distance")
            )
            km = None
            if afstand is not None:
                waarde = klimaat_wind.naar_kmh(afstand.state, None)
                eenheid = afstand.attributes.get("unit_of_measurement")
                if waarde is not None:
                    km = waarde / 1000 if eenheid == "m" else (waarde * 1.609344 if eenheid == "mi" else waarde)
            return toestand.state, km
        return None, None

    def _airco_kort_weg_ronde(self, now: datetime, uit: dict) -> dict:
        """Kort weg: de airco niet meteen uit (v5.69) - zie `airco_ritme.kort_weg`.

        Houdt bij hoe lang afwezigheden duren, en houdt een "uit omdat
        niemand thuis is" tegen zolang het een kort uitstapje lijkt. De
        vaste uittijd van 22:00 gaat altijd voor.
        """
        ritme = self._airco_ritme()
        if self.presence_state == "weg":
            if self._weg_sinds is None:
                self._weg_sinds = now
        elif self._weg_sinds is not None:
            if self.presence_state == "thuis":
                airco_ritme.noteer_afwezigheid(ritme, (now - self._weg_sinds).total_seconds() / 60)
            self._weg_sinds = None
        if uit.get("actie") != "uit" or uit.get("altijd") or self.presence_state != "weg":
            return uit
        _, km = self._nadering()
        vraag = airco_ritme.kort_weg(ritme, (now - self._weg_sinds).total_seconds() / 60, km)
        if vraag is None:
            return uit
        redenen = list(uit.get("redenen") or []) + [vraag["reden"]]
        return dict(uit, actie="niets", tekst=vraag["tekst"], redenen=redenen,
                    redenen_tekst=" · ".join(redenen))

    _airco_weg_keuze: dict | None = None
    _airco_weg_vast: bool = False

    def _verwachte_thuiskomst(self, now: datetime) -> datetime | None:
        """v5.199.0: het eerste halfuur (binnen 24 uur) waarop jullie op die
        dag meestal (>= 50 %) thuis zijn, of None zonder geleerd patroon."""
        profiel = self.presence_week_profile or {}
        stap = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        for _ in range(48):
            stap += timedelta(minutes=30)
            aan, totaal = profiel.get(
                f"{stap.weekday()}-{stap.hour:02d}{'30' if stap.minute >= 30 else '00'}"
            ) or [0, 0]
            if totaal >= PRESENCE_MIN_OBSERVATIONS and aan / totaal >= 0.5:
                return stap
        return None

    def _airco_weg_ronde(self, now: datetime, uit: dict, stand: str | None, doel_nu) -> dict:
        """Langer weg: uit, of vasthouden op 18 °C als dat goedkoper is
        (v5.199.0) - zie `airco_sturing.weg_keuze`. Eén keer per
        afwezigheid besloten; bij thuiskomst weer naar de gewone temperatuur.
        De vaste uittijd en handmatige bediening gaan voor."""
        vast_c = airco_sturing.AIRCO_WEG_VAST_C
        if self.presence_state != "weg":
            self._airco_weg_keuze = None
            if not self._airco_weg_vast:
                return uit
            self._airco_weg_vast = False
            doel = uit.get("doel_c")
            if (
                uit.get("actie") == "niets" and stand == "heat" and self.airco_door_ems
                and self._airco_handmatig_bij is None and doel is not None
                and doel_nu is not None and float(doel_nu) < float(doel) - 0.05
            ):
                redenen = list(uit.get("redenen") or []) + [f"terug: van {vast_c:.0f} °C naar {doel:.1f} °C"]
                return dict(uit, actie="verwarmen", doel_c=doel, redenen=redenen,
                            redenen_tekst=" · ".join(redenen),
                            tekst=f"Welkom thuis: van {vast_c:.0f} °C weer naar {doel:.1f} °C.")
            return uit
        if uit.get("altijd") or self._airco_handmatig_bij is not None:
            self._airco_weg_vast = False
            return uit
        if self._airco_weg_vast:
            # Vasthouden loopt: niet uitzetten zolang hij op 18 °C staat.
            if stand == "heat" and self.airco_door_ems and uit.get("actie") == "uit":
                redenen = list(uit.get("redenen") or []) + [f"vasthouden op {vast_c:.0f} °C tot thuiskomst"]
                return dict(uit, actie="niets", redenen=redenen, redenen_tekst=" · ".join(redenen),
                            tekst=f"Niemand thuis: houdt {vast_c:.0f} °C vast tot jullie terug zijn.")
            if stand != "heat":
                self._airco_weg_vast = False
            return uit
        if uit.get("actie") != "uit":
            return uit
        if self._airco_weg_keuze is None:
            self._airco_weg_keuze = self._airco_weg_bereken(now, uit)
        keuze = self._airco_weg_keuze
        redenen = list(uit.get("redenen") or []) + [keuze["reden"]]
        if keuze["keuze"] != "vast":
            return dict(uit, redenen=redenen, redenen_tekst=" · ".join(redenen))
        self._airco_weg_vast = True
        return dict(uit, actie="verwarmen", doel_c=vast_c, redenen=redenen,
                    redenen_tekst=" · ".join(redenen), weg_keuze=keuze,
                    tekst=f"Niemand thuis: {vast_c:.0f} °C vasthouden tot jullie terug zijn ({keuze['reden']}).")

    def _airco_weg_bereken(self, now: datetime, uit: dict) -> dict:
        try:
            if (self.get_verwarmingsadvies() or {}).get("advies") != "airco":
                return {"keuze": "uit", "reden": "gas is nu goedkoper dan de airco"}
            terug = self._verwachte_thuiskomst(now)
            if terug is None:
                return {"keuze": "uit", "reden": "nog niet geleerd wanneer jullie thuiskomen"}
            kost = self._airco_kost_per_uur(now, self._airco_ritme())
            middernacht = now.replace(hour=0, minute=0, second=0, microsecond=0)

            def minuut(moment: datetime) -> int:
                return int((moment - middernacht).total_seconds() // 60)

            onderweg = []
            stap = now
            while stap < terug:
                onderweg.append(kost(minuut(stap)))
                stap += timedelta(minutes=15)
            kost_vast = (
                sum(onderweg) / len(onderweg) if onderweg and None not in onderweg else None
            )
            keuze = airco_sturing.weg_keuze(
                binnen_c=self.living_room_current_temp_c,
                buiten_c=self._airco_buiten_nu(now),
                doel_c=uit.get("doel_c"),
                tempo_c_per_uur=self._airco_tempo_nu(),
                uren_weg=(terug - now).total_seconds() / 3600,
                kost_vast=kost_vast,
                kost_terug=kost(minuut(terug)),
                houd_w_graad=airco_frequentie.houd_w_per_graad((self.airco_ritme or {}).get("frequentie")),
                vermogen_kw=airco_ritme.verwarmvermogen_kw(airco_ritme.geldig(self.airco_ritme)) or 1.0,
            )
            keuze["terug_om"] = terug.isoformat()
            return keuze
        except Exception:  # noqa: BLE001 - bij twijfel gewoon uit
            return {"keuze": "uit", "reden": "vergelijken lukte niet"}

    def _airco_thuiskomst_ronde(self, now: datetime, uit: dict, stand: str | None) -> dict:
        """Warm bij thuiskomst (v5.66) - zie `airco_ritme.thuiskomst`."""
        richting, km = self._nadering()
        ritme = self._airco_ritme()
        if richting == "towards" and km is not None:
            airco_ritme.noteer_nadering(ritme, self._nadering_vorige, now, km)
            self._nadering_vorige = (now, km)
        else:
            self._nadering_vorige = None
        vraag = airco_ritme.thuiskomst(
            ritme,
            koers=richting,
            km=km,
            aanwezigheid=self.presence_state,
            woonkamer_c=self.living_room_current_temp_c,
            doel_c=uit.get("doel_c"),
            tempo_c_per_uur=self._airco_tempo_nu(),
            advies=(self.get_verwarmingsadvies() or {}).get("advies"),
            airco_stand=stand,
            door_ems=self.airco_door_ems,
        )
        if vraag is None:
            return uit
        nieuw = dict(uit)
        nieuw["redenen"] = list(uit.get("redenen") or []) + [vraag["reden"]]
        nieuw["redenen_tekst"] = " · ".join(nieuw["redenen"])
        if vraag.get("houd_aan"):
            if uit.get("actie") == "uit":
                nieuw.update(actie="niets", tekst=vraag["tekst"])
        elif uit.get("actie") == "niets" and self._airco_handmatig_bij is None:
            nieuw.update(actie="verwarmen", tekst=vraag["tekst"], doel_c=vraag["doel_c"])
        return nieuw

    _airco_zon_aan: bool = False
    _airco_zon_sinds: datetime | None = None

    def _airco_zon_ronde(self, now: datetime, uit: dict, stand: str | None) -> dict:
        """Verwarmen op zonoverschot (v5.132.0) - zie `airco_sturing.verwarm_op_zonoverschot`."""
        try:
            toestand = self._overschot_toestand()
        except Exception:  # noqa: BLE001 - bij twijfel geen zonverwarmen
            toestand = {}
        if toestand.get("accu_vol") and (toestand.get("overschot_w") or 0.0) >= AIRCO_ZON_MIN_OVERSCHOT_W:
            self._airco_zon_sinds = self._airco_zon_sinds or now
        else:
            self._airco_zon_sinds = None
        # Alleen zolang de airco verwarmt zoals het EMS hem zette.
        zon_aan = self._airco_zon_aan and stand == "heat" and bool(self.airco_door_ems)
        uit, self._airco_zon_aan = airco_sturing.verwarm_op_zonoverschot(
            uit,
            woonkamer_c=self.living_room_current_temp_c,
            aanwezigheid=self.presence_state,
            overschot_minuten=(
                (now - self._airco_zon_sinds).total_seconds() / 60 if self._airco_zon_sinds else None
            ),
            airco_stand=stand,
            zon_aan=zon_aan,
            handmatig=self._airco_handmatig_bij is not None,
            onder_c=AIRCO_ZON_ONDER_C,
            doel_c=AIRCO_ZON_DOEL_C,
            minuten_nodig=AIRCO_ZON_MINUTEN,
        )
        return uit

    def _airco_buffer_ronde(self, now: datetime, uit: dict, stand: str | None) -> dict:
        """Voorverwarmen op goedkope stroom (v5.66) - zie `airco_sturing.buffer`.

        Alleen wat het EMS zelf stookt: een nieuw "verwarmen", of een airco
        die het EMS aanzette en die nog verwarmt. Wat jullie zelf instellen,
        blijft staan.
        """
        laatste = self._airco_laatste_ems or {}
        bijstellen = (
            uit.get("actie") == "niets" and stand == "heat" and self.airco_door_ems
            and self._airco_handmatig_bij is None and laatste.get("basis") is not None
        )
        if uit.get("actie") != "verwarmen" and not bijstellen:
            return uit
        basis = uit.get("doel_c") if uit.get("actie") == "verwarmen" else laatste["basis"]
        # v5.141.0 (L-EMS-043): de reeks staat in eenheden van 1e-7 euro
        # (PRICE_SCALE_FACTOR); de prijs van nu in euro. Zonder deling was
        # 'straks' altijd duurder en elk verwarmbesluit een halve graad hoger.
        komende = [
            prijs / PRICE_SCALE_FACTOR
            for start, _eind, prijs in (self._get_forecast_entries() or [])
            if now < start <= now + timedelta(hours=airco_sturing.BUFFER_VOORUIT_UREN)
        ]
        b = airco_sturing.buffer(basis, self.huidige_prijs_eur_per_kwh(now), komende)
        if bijstellen and b["doel_c"] == laatste.get("doel"):
            return uit
        nieuw = dict(uit, basis_doel_c=basis, doel_c=b["doel_c"])
        if b["reden"]:
            nieuw["redenen"] = list(uit.get("redenen") or []) + [b["reden"]]
            nieuw["redenen_tekst"] = " · ".join(nieuw["redenen"])
        if b["reden"] and not bijstellen:
            nieuw["tekst"] = f"{uit.get('tekst') or ''} Doel nu {b['doel_c']:.1f} °C ({b['reden']})."
        if bijstellen:
            nieuw.update(
                actie="verwarmen",
                tekst=f"Bijstellen naar {b['doel_c']:.1f} °C: " + (b["reden"] or "terug naar het gewone doel") + ".",
            )
        return nieuw

    def get_airco_ritme(self) -> dict:
        """Wat er van jullie dagritme geleerd is (v5.65)."""
        return airco_ritme.overzicht(self._airco_ritme())

    def get_airco_verwachting(self, now: datetime | None = None) -> dict:
        """Gaat de airco naar verwachting aan tot het volgende goedkope blok,
        en hoeveel daarvan rekent de reserve mee? (v5.93.0)

        Gevraagd 12-10: op de cockpit bij "Huis en apparaten" zien of de
        airco verwacht wordt, omdat dat de accu raakt. Dezelfde getallen als
        de reserve (`_airco_ochtend_extra_kwh` + `_airco_gebruik_extra_kwh`),
        tot het volgende blok; loopt het blok nu of is er geen, tot 09:00.
        """
        now = now or dt_util.now()
        tot = self.last_cheap_block_start
        if tot is None or tot <= now:
            tot = self._monte_carlo_terugval_horizon(now)
        try:
            ochtend = self._airco_ochtend_extra_kwh(now, tot)
            gebruik = self._airco_gebruik_extra_kwh(now, tot)
        except Exception:  # noqa: BLE001 - alleen weergave
            return {"beschikbaar": False}
        uren = list(gebruik.get("uren") or [])
        try:
            basis = airco_ritme.verwachting_basis(self._airco_ritme(), now, tot)
        except Exception:  # noqa: BLE001 - alleen weergave
            basis = {}
        reserve_som = (ochtend.get("extra_kwh") or 0.0) + (gebruik.get("extra_kwh") or 0.0)
        verwacht_som = (ochtend.get("verwacht_kwh") or 0.0) + (gebruik.get("verwacht_kwh") or 0.0)
        loopt = any(u.get("zeker") for u in uren)
        if loopt:
            tekst = "airco draait"
        elif uren:
            eerste, laatste = uren[0]["uur"], uren[-1]["uur"]
            kans = max(u.get("kans") or 0 for u in uren)
            span = eerste if eerste == laatste else f"{eerste[:2]}-{int(laatste[:2]) + 1:02d} u"
            tekst = f"verwacht rond {span} (kans {round(kans * 100)}%)"
        elif (ochtend.get("extra_kwh") or 0) > 0:
            tekst = "ochtendverwarming verwacht"
        else:
            tekst = "niet verwacht"
        return {
            "beschikbaar": True,
            "tot": tot.isoformat(),
            "tot_tekst": tijd_met_dag(tot),
            "verwacht": bool(uren) or (ochtend.get("extra_kwh") or 0) > 0,
            "tekst": tekst,
            "in_reserve_kwh": round(reserve_som, 2),
            "verwacht_kwh": round(verwacht_som, 2),
            "ochtend_kwh": round(ochtend.get("extra_kwh") or 0.0, 2),
            "uren": uren,
            # v5.93.1: waar dat op rust
            "basis": basis,
            "knop_automaat": bool(self.airco_automaat_aan),
        }

    def _airco_vooruitblik(self) -> dict:
        """De woonkamertemperatuur over een uur volgens de projectie, en of
        die goed genoeg is om vooruit op te verwarmen (v5.64).

        Alleen als de projectie over de voorbije uren gemiddeld binnen een
        halve graad zat - dezelfde grens die de pagina Klimaat "nauwkeurig
        genoeg om op te bouwen" noemt - en het eerste uur zelf op metingen
        rust. Anders geen vooruitblik, en dus alleen aanzetten op de meting.
        """
        traject = self.climate_forecast_trajectory or []
        eerste = traject[0] if traject else {}
        kwaliteit = self.get_klimaat_projectie_kwaliteit()
        verwacht = eerste.get("kort_termijn_temp_c")
        bruikbaar = (
            verwacht is not None
            and eerste.get("betrouwbaarheid") in ("indicatief", "betrouwbaar")
            and kwaliteit.get("beschikbaar")
            and (kwaliteit.get("gemiddelde_afwijking_c") or 99) <= 0.5
        )
        if not bruikbaar:
            reden = (
                "geen projectie voor het komende uur"
                if verwacht is None
                else "projectie nog niet nauwkeurig genoeg om vooruit te verwarmen"
            )
            return {"verwacht_c": None, "reden": reden}
        return {"verwacht_c": verwacht, "wind": eerste.get("wind"), "reden": None}

    async def _async_pas_airco_toe(self, entiteit: str, besluit: dict) -> None:
        """Het besluit uitvoeren - alleen met de knop aan (v5.27)."""
        if entiteit == self.config.get(CONF_SLAAPKAMER_CLIMATE_ENTITY):
            return
        if besluit["actie"] == "verwarmen":
            # Afgeschermd: een onbereikbare airco breekt de ronde niet af.
            try:
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": entiteit, "temperature": besluit["doel_c"], "hvac_mode": "heat"},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                besluit["fout"] = f"opdracht kwam niet aan: {err}"
                return
            self._airco_laatste_ems = {
                "stand": "heat",
                "doel": besluit["doel_c"],
                "basis": besluit.get("basis_doel_c", besluit["doel_c"]),
            }
            self.airco_door_ems = True
            self._airco_geschakeld = ("verwarmen", dt_util.now())
        elif besluit["actie"] == "uit":
            try:
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {"entity_id": entiteit, "hvac_mode": "off"},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                besluit["fout"] = f"opdracht kwam niet aan: {err}"
                return
            toestand = self.hass.states.get(entiteit)
            self._airco_laatste_ems = {
                "stand": "off",
                "doel": toestand.attributes.get("temperature") if toestand else None,
            }
            self.airco_door_ems = False
            self._airco_geschakeld = ("uit", dt_util.now())

    _airco_zaai_bezig: bool = False

    def _plan_airco_zaaien(self) -> None:
        """v5.101: eenmalig het dagritme overdag vullen uit de geschiedenis van
        de airco, zodat het EMS jullie patroon meteen kent."""
        if self._airco_zaai_bezig or self._airco_ritme().get("dag_gezaaid"):
            return
        # hooguit drie pogingen per keer dat HA draait (recorder nog niet klaar)
        self._airco_zaai_pogingen = getattr(self, "_airco_zaai_pogingen", 0) + 1
        if self._airco_zaai_pogingen > 3:
            return
        if not self.config.get(CONF_AIRCO_CLIMATE_ENTITY):
            return
        self._airco_zaai_bezig = True
        if not self._start_achtergrondtaak(self._async_zaai_airco(), f"{DOMAIN} airco-dagritme"):
            self._airco_zaai_bezig = False

    async def _async_zaai_airco(self) -> None:
        entiteit = self.config.get(CONF_AIRCO_CLIMATE_ENTITY)
        try:
            from homeassistant.components.recorder import get_instance, history

            begin = dt_util.utcnow() - timedelta(days=14)
            toestanden = await get_instance(self.hass).async_add_executor_job(
                history.state_changes_during_period, self.hass, begin, None, entiteit
            )
            lijst = (toestanden or {}).get(entiteit) or []
            overgangen = [
                (dt_util.as_local(t.last_changed), t.state, (t.attributes or {}).get("temperature"))
                for t in lijst
            ]
            gisteren = dt_util.now().date() - timedelta(days=1)
            eerste = overgangen[0][0].date() if overgangen else gisteren
            dagen = [eerste + timedelta(days=i) for i in range((gisteren - eerste).days + 1)]
            ritme = self._airco_ritme()
            aantal = airco_ritme.zaai_dag_uit_historie(
                ritme, [o for o in overgangen if o[0].date() <= gisteren], dagen
            )
            self.internal_failures.pop("airco_zaaien", None)
            _LOGGER.info("Airco-dagritme: %s dagen uit de geschiedenis geleerd", aantal)
            self.schedule_persisted_state_save()
        except Exception as fout:  # noqa: BLE001 - leren mag de sturing nooit raken
            self.internal_failures["airco_zaaien"] = f"{type(fout).__name__}: {fout}"
        finally:
            self._airco_zaai_bezig = False
