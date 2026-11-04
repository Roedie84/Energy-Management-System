"""NILM van de coordinator: apparaatherkenning uit het verbruik (B4.7).

De ontdekking van kandidaat-apparaten (met uitsluitingen), bevestigen,
afwijzen en drift accepteren, de opslag van de bevestigde apparaten, de
dubbele paren, de dagafsluiting per apparaat met de marges, en de
NILM-zinnen voor het verhaal en de tabel. Ongewijzigd verhuisd uit
`coordinator.py`; de coordinator erft deze mixin.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime
from homeassistant.util import dt as dt_util
from .const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_BACKYARD_TEMPERATURE_SENSOR,
    CONF_BATTERIJLADER_POWER_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_DISHWASHER_POWER_SENSOR,
    CONF_FIETSLADERS_POWER_SENSOR,
    CONF_PV_POWER_SENSOR,
    CONF_QUOOKER_POWER_SENSOR,
    CONF_STEELSTOFZUIGER_POWER_SENSOR,
    CONF_WASHING_MACHINE_POWER_SENSOR,
    CUSUM_BASELINE_HISTORY_DAYS,
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
    CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS,
    DOMAIN,
    NILM_COMPRESSOR_ON_THRESHOLD_W,
    NILM_COOLING_MIN_DUTY_CYCLE,
    NILM_CUSUM_ALARM_THRESHOLD,
    NILM_CUSUM_MARGE_MAX,
    NILM_CUSUM_MAX_DAILY_CONTRIBUTION,
    NILM_CUSUM_RESET_STREAK_DAYS,
    NILM_CUSUM_SLACK_FRACTION,
    NILM_DRIFT_MIN_ABSOLUTE_W,
    NILM_DRIFT_MIN_REFERENCE_W,
    NILM_DUPLICATE_MIN_ACTIVE_W,
    NILM_DUPLICATE_MIN_SHARED_DAYS,
    NILM_DUPLICATE_TOLERANCE_FRACTION,
    NILM_MIN_SAMPLES_FOR_DAY,
    NILM_MIN_UREN_VOOR_DAG,
    NILM_PATTERN_EXCLUDED_KEYWORDS,
    NILM_TREND_FALLING_THRESHOLD_PERCENT,
    NILM_TREND_RISING_THRESHOLD_PERCENT,
)

# Zelfde loggernaam als voorheen, zodat logger-instellingen in HA blijven werken.
_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")


class NilmMixin:
    """De NILM-methodes van de coordinator."""

    async def _bewaar_nilm_lopende_dag(self) -> None:
        """Schrijft de NILM-Store weg, inclusief de lopende dag
        (v5.149.0).

        Gevonden bij een "mogelijk defect" van de CV-ketel: EMS rekende
        29-10 een daggemiddelde van 13,56 W, de recorder 9,89 W. De
        laatste herstart was om 15:54, en de Store werd alleen om
        middernacht weggeschreven - dus de tellers van de dag begonnen
        na die herstart opnieuw bij nul. Over 15:54-24:00 (8,1 uur,
        net genoeg voor een dagcijfer) zit de avond met het stoken erin
        en de zuinige nacht niet: precies 13,5 W. Elke dag met een
        herstart werd zo een avonddag.
        """
        if not getattr(self, "_nilm_store_loaded", False):
            # Nooit een lege lijst over een Store heen schrijven die nog
            # niet gelezen is.
            return
        try:
            await self._async_save_nilm_confirmed_devices_store()
        except Exception:  # noqa: BLE001 - afsluiten mag hier niet op stuklopen
            _LOGGER.exception("Kon de NILM-apparaten niet wegschrijven")

    def _nilm_excluded_entity_ids(self) -> set[str]:
        """Entities already tracked elsewhere in this integration -
        never suggested as a "new" NILM candidate, to avoid double-
        counting the battery/PV/grid meter or an already-named
        appliance under a second identity.
        """
        keys = (
            CONF_BATTERY_POWER_SENSOR,
            CONF_PV_POWER_SENSOR,
            CONF_CONSUMPTION_POWER_SENSOR,
            CONF_DISHWASHER_POWER_SENSOR,
            CONF_WASHING_MACHINE_POWER_SENSOR,
            CONF_QUOOKER_POWER_SENSOR,
            CONF_STEELSTOFZUIGER_POWER_SENSOR,
            CONF_FIETSLADERS_POWER_SENSOR,
            CONF_BATTERIJLADER_POWER_SENSOR,
        )
        return {self.config[k] for k in keys if self.config.get(k)}

    @staticmethod
    def _is_nilm_pattern_excluded(entity_id: str, friendly_name: str) -> bool:
        """Structurele uitsluiting op naampatroon (v0.63.89, gevraagd:
        "alles waar fase 1 bij staat mag sowieso uitgesloten worden net
        als solaredge en zendure entiteiten") - een substring-match
        tegen zowel entity_id als friendly_name, kleine letters. Anders
        dan `_nilm_excluded_entity_ids()` (exacte match tegen specifiek
        geconfigureerde entiteiten), dit sluit hele categorieën uit
        zonder losse afwijzing per sub-fase-sensor of accu-/omvormer-
        signaal.
        """
        haystack = f"{entity_id} {friendly_name}".lower()
        return any(keyword in haystack for keyword in NILM_PATTERN_EXCLUDED_KEYWORDS)

    @staticmethod
    def _is_own_integration_entity(entity_id: str) -> bool:
        """True als deze entity_id bij deze integratie zelf hoort
        (v0.63.103, gerapporteerd: "elke keer terug krijg onbevestigde
        kandidaten na herstart" - deze integratie stelde inmiddels ook
        haar EIGEN, afgeleide sensoren voor als NILM-kandidaat, bijv.
        "Hourly consumption profile", "Piekvermogen"). Elke entity_id
        van deze integratie volgt het patroon
        sensor.<apparaat>_energy_management_system_<naam>, dus DOMAIN
        als substring is een betrouwbare, generieke uitsluiting die
        geen onderhoud per nieuwe sensor vereist.
        """
        return f"_{DOMAIN}_" in entity_id or entity_id.endswith(f"_{DOMAIN}")

    def _prune_nilm_pattern_excluded_entries(self) -> None:
        """Ruimt entiteiten op die al als kandidaat, bevestigd of
        afgewezen stonden vóórdat het naampatroon werd ingesteld
        (v0.63.89) - anders zou een structurele uitsluiting alleen
        NIEUW ontdekte entiteiten raken, niet wat er al in de lijsten
        stond. v0.63.103: ruimt nu ook eigen-integratie-sensoren op
        (zie `_is_own_integration_entity`).
        """
        # v5.136.0: en wat inmiddels elders wordt gevolgd (Quooker,
        # batterijlader, P1 ...), al bevestigd of al afgewezen is. Die
        # uitsluitingen golden alleen bij het ONTDEKKEN; een kandidaat van
        # vóór de instelling bleef staan (26-10: Quooker, batterijlader en
        # een al bevestigde houten lamp bleven als "onbevestigd" hangen).
        al_gevolgd = self._nilm_excluded_entity_ids()
        for entity_id in list(self.nilm_unconfirmed_candidates.keys()):
            candidate = self.nilm_unconfirmed_candidates[entity_id]
            if (
                self._is_own_integration_entity(entity_id)
                or self._is_nilm_pattern_excluded(entity_id, candidate.get("friendly_name", entity_id))
                or entity_id in al_gevolgd
                or entity_id in self.nilm_confirmed_devices
                or entity_id in self.nilm_rejected_entities
            ):
                del self.nilm_unconfirmed_candidates[entity_id]

        removed_confirmed = False
        for entity_id in list(self.nilm_confirmed_devices.keys()):
            device = self.nilm_confirmed_devices[entity_id]
            if self._is_own_integration_entity(entity_id) or self._is_nilm_pattern_excluded(
                entity_id, device.get("friendly_name", entity_id)
            ):
                del self.nilm_confirmed_devices[entity_id]
                removed_confirmed = True

        # Ook eerder afgewezen entiteiten die nu al patroon-uitgesloten
        # zijn, uit de aparte lijst verwijderen - overbodig geworden nu
        # de patroonmatch dat werk structureel doet, en houdt die lijst
        # klein en betekenisvol.
        pruned_rejected = [
            entity_id
            for entity_id in self.nilm_rejected_entities
            if not self._is_own_integration_entity(entity_id)
            and not self._is_nilm_pattern_excluded(entity_id, entity_id)
        ]
        rejected_changed = len(pruned_rejected) != len(self.nilm_rejected_entities)
        self.nilm_rejected_entities = pruned_rejected

        if removed_confirmed or rejected_changed:
            self.hass.async_create_task(
                self._async_save_nilm_confirmed_devices_store()
            )

    def _update_nilm_discovery(self, now: datetime) -> None:
        """NILM-like device auto-discovery (v0.63.39).

        NOT genuine NILM (blind disaggregation of a single aggregate
        power signal into individual appliance loads - a research-grade
        problem this integration has no training data for). Instead:
        discovers *existing* power-measuring sensor entities already in
        Home Assistant (smart plugs, appliances that report their own
        consumption) that aren't already tracked elsewhere in this
        integration, and lists them as unconfirmed candidates.

        Deliberately requires explicit human confirmation
        (`confirm_nilm_device`/`reject_nilm_device` services) before any
        drift-detection tracking begins - broad auto-discovery (any W/kW
        sensor) will pick up false positives (a random utility sensor
        that happens to report Watts, or this integration's own derived
        sensors), and confirming/rejecting is the only way to keep the
        confirmed list actually meaningful. Never influences any battery
        decision - purely informational (confirmed with the person
        before building this).

        v0.63.89: structural name-pattern exclusion ("fase 1"/"fase_1"/
        "solaredge"/"zendure") runs once per tick, before the discovery
        scan itself, pruning anything already in the candidate/
        confirmed/rejected lists that matches - so this reaches
        everything already present, not just newly-discovered entities
        going forward.
        """
        self._prune_nilm_pattern_excluded_entries()
        excluded = self._nilm_excluded_entity_ids()
        for state in self.hass.states.async_all():
            entity_id = getattr(state, "entity_id", None)
            if not entity_id or not entity_id.startswith("sensor."):
                continue
            if self._is_own_integration_entity(entity_id):
                continue
            if entity_id in excluded:
                continue
            if entity_id in self.nilm_confirmed_devices:
                continue
            if entity_id in self.nilm_rejected_entities:
                continue
            friendly_name = state.attributes.get("friendly_name", entity_id)
            if self._is_nilm_pattern_excluded(entity_id, friendly_name):
                continue
            unit = state.attributes.get("unit_of_measurement")
            if unit not in ("W", "kW"):
                continue
            power_w = self._read_sensor_float(entity_id)
            existing = self.nilm_unconfirmed_candidates.get(entity_id, {})
            self.nilm_unconfirmed_candidates[entity_id] = {
                "friendly_name": friendly_name,
                "current_power_w": power_w,
                "first_seen": existing.get("first_seen", now.date().isoformat()),
            }

    def confirm_nilm_device(self, entity_id: str) -> bool:
        """Move a discovered candidate to the confirmed list, starting
        per-device CUSUM drift-detection for it. Returns False if the
        entity isn't a currently-known candidate (e.g. a typo, or it's
        already confirmed/rejected).

        Notifies listeners immediately (v0.63.50) - reported: after
        pressing confirm/reject on one slot's button, its sibling button
        (the other action for that same slot) kept showing the old
        candidate until the next 5-minute update tick. A button press
        only writes *that one entity's* own state automatically; it
        doesn't know its slot-sibling exists. Since a slot's occupant
        can shift right after any confirm/reject (the next candidate
        moves in), every registered NILM button needs to refresh right
        away, not just the one that was pressed.

        Also persists to the dedicated Store (v0.63.66) - fire-and-
        forget, since this method itself isn't async and every caller
        (button presses, services) already triggers its own
        async_update() right after anyway.
        """
        candidate = self.nilm_unconfirmed_candidates.pop(entity_id, None)
        if candidate is None:
            return False
        self.nilm_confirmed_devices[entity_id] = {
            "friendly_name": candidate["friendly_name"],
            # v1.48.0: de datum van Home Assistant, niet van het proces.
            "confirmed_at": dt_util.now().date().isoformat(),
            "daily_avg_history": [],
            "cusum_accumulator": 0.0,
            "anomaly_detected": False,
            "estimated_drift_percent": None,
            "reference_avg_w": None,
            "_today_sum": 0.0,
            "_today_count": 0,
            "_check_date": None,
        }
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def reject_nilm_device(self, entity_id: str) -> bool:
        """Permanently ignore a discovered candidate - never suggested
        again. Also removes it from the confirmed list, if it was
        confirmed earlier and the person changed their mind.

        Notifies listeners immediately - see `confirm_nilm_device`'s
        docstring for why (v0.63.50). Also persists to the dedicated
        Store (v0.63.66) - see `confirm_nilm_device`'s docstring.
        """
        self.nilm_unconfirmed_candidates.pop(entity_id, None)
        self.nilm_confirmed_devices.pop(entity_id, None)
        if entity_id not in self.nilm_rejected_entities:
            self.nilm_rejected_entities.append(entity_id)
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def accept_nilm_device_drift(self, entity_id: str) -> bool:
        """Accepteert het huidige verbruiksniveau als het nieuwe normaal
        (v1.1.7, gevraagd: "1 apparaat mogelijk defect: Koelkast schuur.
        Hoe kan dit als acceptabel worden gezien?").

        Tot nu toe was er geen nette uitweg. De drift-detectie herstelt
        zichzelf alleen als het verbruik vijf dagen op rij TERUGKEERT naar
        het oude niveau (`NILM_CUSUM_RESET_STREAK_DAYS`). Doet het dat
        niet - omdat het apparaat werkelijk structureel meer is gaan
        gebruiken, of gewoon omdat het zomer is en een koelkast dan
        harder werkt - dan blijft de melding weken staan tot de mediaan
        van de geschiedenis vanzelf is meegekropen.

        De enige alternatieven waren bot: `unconfirm_nilm_device` wist
        de hele leergeschiedenis, en `reject_nilm_device` haalt het
        apparaat er helemaal uit. Beide gooien maanden aan opgebouwde
        kennis weg voor iets wat eigenlijk "ja, dit klopt, ga verder"
        is.

        Wat deze actie doet: het apparaat blijft bevestigd en blijft
        gevolgd, maar de referentie wordt opnieuw verankerd op het
        RECENTE niveau. De oudste dagen verdwijnen uit de geschiedenis,
        zodat de mediaan meteen het nieuwe normaal weerspiegelt in plaats
        van er dertig dagen over te doen. Het alarm en de opgebouwde
        CUSUM-som worden gewist.

        Bewust NIET de hele geschiedenis wissen: dan zou er tien dagen
        lang geen referentie zijn en kon een échte verslechtering in die
        periode ongemerkt blijven.
        """
        device = self.nilm_confirmed_devices.get(entity_id)
        if device is None:
            return False

        history = device.get("daily_avg_history") or []
        if history:
            device["daily_avg_history"] = history[-CUSUM_MIN_HISTORY_FOR_REFERENCE:]
        device["cusum_accumulator"] = 0.0
        device["anomaly_detected"] = False
        device["estimated_drift_percent"] = None
        device["_normal_streak_days"] = 0
        device["drift_accepted_at"] = dt_util.now().isoformat()
        # De referentie zelf wordt bij de eerstvolgende dagafronding
        # opnieuw berekend uit de ingekorte geschiedenis; hem hier al
        # zetten zou een tweede, afwijkende berekening introduceren.
        device["reference_avg_w"] = None

        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        _LOGGER.info(
            "Drift van %s geaccepteerd als nieuw normaal - referentie wordt "
            "opnieuw opgebouwd uit de laatste %d dagen",
            entity_id,
            CUSUM_MIN_HISTORY_FOR_REFERENCE,
        )
        return True

    def unconfirm_nilm_device(self, entity_id: str) -> bool:
        """Removes a confirmed device and its entire learned CUSUM
        history (baseline, drift state, daily averages) so it can be
        re-discovered and re-confirmed fresh with a brand-new baseline
        (v0.63.68, requested: "hoe kan ik een NILM apparaat verwijderen
        en opnieuw beoordelen?") - e.g. the appliance itself changed
        (replaced, repaired) so its old learned baseline no longer
        applies.

        Deliberately different from `reject_nilm_device`: does NOT add
        the entity to `nilm_rejected_entities`, so the next discovery
        scan is free to surface it again as a fresh, unconfirmed
        candidate - unlike reject, which permanently blacklists it.
        Returns False if the entity wasn't actually a confirmed device.

        Notifies listeners immediately and persists to the dedicated
        Store, same as confirm/reject (v0.63.50/.66).
        """
        removed = self.nilm_confirmed_devices.pop(entity_id, None)
        if removed is None:
            return False
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    @property
    def nilm_store_had_data(self) -> bool:
        """True zodra de Store van schijf is gelezen én daar echte
        bevestigde/afgewezen NILM-data in stond (v0.63.115). Dit is het
        enige betrouwbare signaal dat de Store de bron van waarheid is;
        "de lijsten in het geheugen zijn leeg" is dat NIET (die zijn óók
        leeg als de Store simpelweg nog niet gelezen is).
        """
        return self._nilm_store_had_data

    async def async_load_persisted_nilm_state(self) -> None:
        """Publieke ingang om de NILM-Store te laden (v0.63.115).

        Wordt in `async_setup_entry` aangeroepen VÓÓR
        `async_forward_entry_setups`, zodat de Store gegarandeerd
        gelezen is voordat `NilmConfirmedDevicesSensor.
        async_added_to_hass` draait. Zie
        `_async_load_nilm_confirmed_devices_store` voor waarom die
        volgorde cruciaal is.
        """
        await self._async_load_nilm_confirmed_devices_store()

    async def _async_load_nilm_confirmed_devices_store(self) -> None:
        """Loads confirmed NILM devices + rejected entities from the
        dedicated Store (v0.63.66) - see the `_nilm_confirmed_devices_
        store` init comment for why this exists separately from the
        entity's own restored HA state. Leaves existing in-memory state
        untouched if the Store is empty (e.g. a genuinely fresh install,
        or an existing install upgrading before this Store has ever been
        written - `NilmConfirmedDevicesSensor.async_added_to_hass`
        handles that one-time migration from the entity's restored
        state instead).

        v0.63.115, gerapporteerd (na v0.63.107): "keuzes voor NILM
        apparaten worden nog steeds niet opgeslagen, de onbevestigde
        lijst blijft terug komen na een herstart". ECHTE root cause,
        los van de knop-race van v0.63.107:

        `async_setup_entry` deed `async_forward_entry_setups(...)`
        VOORDAT `coordinator.async_setup()` (en dus deze load) draaide.
        Daardoor liep `NilmConfirmedDevicesSensor.async_added_to_hass`
        altijd met een nog volledig LEGE `nilm_confirmed_devices` /
        `nilm_rejected_entities`. Die methode gebruikte "leeg" als
        bewijs dat de Store leeg was, viel dus bij ELKE herstart terug
        op de eenmalig-bedoelde migratiepad vanuit de eigen herstelde
        entiteit-state - en die attributen zijn met opzet AFGEKAPT op
        NILM_SENSOR_ATTRIBUTE_PREVIEW_LIMIT (20). Vervolgens schreef
        die methode dat afgekapte resultaat meteen terug naar de Store,
        waarmee de volledige, goede inhoud werd OVERSCHREVEN. Pas
        daarna las deze load de zojuist verminkte Store terug.

        Netto per herstart: bevestigde apparaten hard afgekapt op 20
        (de gebruiker zag exact 20), en afgewezen entiteiten óók op 20 -
        alles daarboven kwam terug als "onbevestigde kandidaat". Precies
        het gerapporteerde beeld.

        Deze load is nu idempotent (een tweede aanroep leest niet
        opnieuw over verser geheugen heen) en registreert expliciet of
        er echte data in de Store stond, zodat het migratiepad in de
        sensor niet meer hoeft te gissen.
        """
        if self._nilm_store_loaded:
            # Al gelezen (de load draait nu zowel vóór platform-setup
            # als vanuit async_setup) - niet nogmaals over geheugen
            # heen lezen dat inmiddels verser kan zijn.
            return
        stored = await self._nilm_confirmed_devices_store.async_load()
        self._nilm_store_loaded = True
        if not isinstance(stored, dict):
            return
        devices = stored.get("nilm_confirmed_devices")
        if isinstance(devices, dict):
            # v5.149.0: de Store bewaart de datum als tekst. Zonder
            # terugzetten is hij nooit gelijk aan vandaag en begint de
            # lopende dag na elke herstart opnieuw bij nul.
            for device in devices.values():
                if isinstance(device, dict):
                    device["_check_date"] = self._nilm_datum(
                        device.get("_check_date")
                    )
            self.nilm_confirmed_devices = devices
            if devices:
                self._nilm_store_had_data = True
            # v1.50.0: het opgebouwde alarm van een koelapparaat kan op
            # uitvaldagen rusten. Eenmalig herrekenen zonder die dagen.
            self._herijk_koelapparaten_na_meetuitval()
            # v5.152.0: en eenmalig met de eigen marge per apparaat.
            self._herijk_nilm_marges()
        rejected = stored.get("nilm_rejected_entities")
        if isinstance(rejected, list):
            self.nilm_rejected_entities = rejected
            if rejected:
                self._nilm_store_had_data = True
        # v0.63.118: beoordeelde duplicaatparen horen bij dezelfde
        # door de gebruiker gecureerde staat en gaan door dezelfde
        # Store - inclusief de volgorde-borging van v0.63.115.
        dismissed = stored.get("nilm_dismissed_duplicate_pairs")
        if isinstance(dismissed, list):
            self.nilm_dismissed_duplicate_pairs = dismissed
            if dismissed:
                self._nilm_store_had_data = True

    @staticmethod
    def _nilm_datum(waarde):
        """Een opgeslagen controledatum als `date` (v5.149.0)."""
        if isinstance(waarde, datetime):
            return waarde.date()
        if isinstance(waarde, date) or waarde is None:
            return waarde
        try:
            return date.fromisoformat(str(waarde)[:10])
        except ValueError:
            return None

    async def _async_save_nilm_confirmed_devices_store(self) -> None:
        """Persists confirmed NILM devices + rejected entities to the
        dedicated Store (v0.63.66)."""
        await self._nilm_confirmed_devices_store.async_save(
            {
                "nilm_confirmed_devices": self.nilm_confirmed_devices,
                "nilm_rejected_entities": self.nilm_rejected_entities,
                "nilm_dismissed_duplicate_pairs": (
                    self.nilm_dismissed_duplicate_pairs
                ),
            }
        )

    def get_nilm_devices_table(self) -> list[dict]:
        """Simple 3-column overview (naam, huidig vermogen, trend) of
        all confirmed NILM devices, requested for the dashboard
        (v0.63.51). Live power read fresh on every call; trend derived
        from the existing CUSUM tracking (v0.63.39) - no new tracking
        mechanism needed. Sorted by name for a stable, predictable
        display order.
        """
        rows = []
        for entity_id, device in sorted(
            self.nilm_confirmed_devices.items(),
            key=lambda item: item[1].get("friendly_name") or item[0],
        ):
            rows.append(
                {
                    "naam": device.get("friendly_name") or entity_id,
                    "huidig_vermogen_w": self._read_sensor_float(entity_id),
                    "trend": self._describe_nilm_trend(device),
                }
            )
        return rows

    def get_nilm_duplicate_pairs(self) -> list[dict]:
        """Waarschijnlijke duplicaten onder bevestigde NILM-apparaten
        (v0.63.91, gevonden tijdens een diagnostiek-review: 5
        "Eetkamer lamp"-sensoren deelden een identieke vermogens-
        geschiedenis - vermoedelijk hetzelfde fysieke circuit onder
        meerdere HA-entiteiten).

        Vergelijkt elk paar bevestigde apparaten op basis van hun
        `daily_avg_history` over de gedeelde dagen: als alle gedeelde
        dagwaarden binnen
        `NILM_DUPLICATE_TOLERANCE_FRACTION` van elkaar liggen (en er
        genoeg gedeelde dagen zijn, `NILM_DUPLICATE_MIN_SHARED_DAYS`),
        is dat een sterke aanwijzing dat beide entiteiten hetzelfde
        onderliggende signaal meten. Puur informatief - stuurt niets
        aan, beslist niets automatisch.

        v0.63.118: paren die de gebruiker heeft beoordeeld als "geen
        duplicaat" worden overgeslagen (`nilm_dismissed_duplicate_
        pairs`). Zonder dat bleef een bewust geaccepteerd paar elke
        keer opnieuw opduiken zonder enige manier om het weg te
        krijgen - precies de aanleiding voor deze wijziging.
        """
        entities = sorted(self.nilm_confirmed_devices.keys())
        dismissed = set(self.nilm_dismissed_duplicate_pairs)
        pairs = []
        for i, entity_a in enumerate(entities):
            history_a = self.nilm_confirmed_devices[entity_a].get(
                "daily_avg_history"
            ) or []
            if len(history_a) < NILM_DUPLICATE_MIN_SHARED_DAYS:
                continue
            for entity_b in entities[i + 1 :]:
                if self._duplicate_pair_key(entity_a, entity_b) in dismissed:
                    continue
                history_b = self.nilm_confirmed_devices[entity_b].get(
                    "daily_avg_history"
                ) or []
                shared_len = min(len(history_a), len(history_b))
                if shared_len < NILM_DUPLICATE_MIN_SHARED_DAYS:
                    continue

                shared_a = history_a[-shared_len:]
                shared_b = history_b[-shared_len:]
                # v5.161.1: alleen dagen waarop minstens een van beide iets
                # gebruikte tellen; twee apparaten die uit staan zijn geen
                # duplicaat.
                actieve_dagen = sum(
                    1 for value_a, value_b in zip(shared_a, shared_b)
                    if max(abs(value_a), abs(value_b)) >= NILM_DUPLICATE_MIN_ACTIVE_W
                )
                if actieve_dagen < NILM_DUPLICATE_MIN_SHARED_DAYS:
                    continue
                all_close = True
                for value_a, value_b in zip(shared_a, shared_b):
                    reference = max(abs(value_a), abs(value_b), 0.01)
                    if (
                        abs(value_a - value_b) / reference
                        > NILM_DUPLICATE_TOLERANCE_FRACTION
                    ):
                        all_close = False
                        break

                if all_close:
                    pairs.append(
                        {
                            "apparaat_1": (
                                self.nilm_confirmed_devices[entity_a].get(
                                    "friendly_name"
                                )
                                or entity_a
                            ),
                            "apparaat_2": (
                                self.nilm_confirmed_devices[entity_b].get(
                                    "friendly_name"
                                )
                                or entity_b
                            ),
                            "entity_id_1": entity_a,
                            "entity_id_2": entity_b,
                            "gedeelde_dagen": shared_len,
                        }
                    )
        return pairs

    @staticmethod
    def _duplicate_pair_key(entity_a: str, entity_b: str) -> str:
        """Richting-onafhankelijke sleutel voor een duplicaatpaar
        (v0.63.118). Alfabetisch gesorteerd, zodat (A,B) en (B,A)
        dezelfde sleutel opleveren - anders zou een beoordeeld paar
        alsnog terugkomen zodra de detectie de volgorde omdraait
        (bijvoorbeeld na een hernoeming die de sortering verandert).
        """
        first, second = sorted([entity_a, entity_b])
        return f"{first}|{second}"

    def get_nilm_duplicate_pair_at_slot(self, slot_index: int) -> dict | None:
        """Welk duplicaatpaar op dit moment dashboard-sleuf
        `slot_index` bezet (v0.63.118) - zelfde sleuf-principe als
        `get_nilm_candidate_at_slot`, om dezelfde reden: een statisch
        Lovelace-dashboard kan geen lijst van onbekende lengte met
        knoppen renderen. Volgorde is die van
        `get_nilm_duplicate_pairs()`, die zelf al deterministisch
        alfabetisch sorteert.
        """
        pairs = self.get_nilm_duplicate_pairs()
        if slot_index < 0 or slot_index >= len(pairs):
            return None
        return pairs[slot_index]

    def dismiss_nilm_duplicate_pair(self, entity_a: str, entity_b: str) -> bool:
        """Markeert een paar als "geen duplicaat" - het verdwijnt uit
        de lijst en komt nooit meer terug (v0.63.118, gevraagd: "dit
        dan ook daadwerkelijk niet meer terug komt als mogelijk
        duplicaat").

        Beide apparaten blijven gewoon bevestigd en getrackt; alleen de
        duplicaat-suggestie over dit specifieke paar verdwijnt. Geeft
        False terug als het paar al beoordeeld was, zodat een dubbele
        druk geen tweede opslag veroorzaakt.
        """
        key = self._duplicate_pair_key(entity_a, entity_b)
        if key in self.nilm_dismissed_duplicate_pairs:
            return False
        self.nilm_dismissed_duplicate_pairs.append(key)
        self._notify_listeners()
        self.hass.async_create_task(self._async_save_nilm_confirmed_devices_store())
        return True

    def confirm_nilm_duplicate_pair(self, entity_a: str, entity_b: str) -> bool:
        """Bevestigt dat een paar écht hetzelfde fysieke signaal meet,
        en handelt daar meteen naar (v0.63.118).

        De zinvolle actie bij een bevestigd duplicaat is er één van de
        twee permanent uitsluiten - anders blijft hetzelfde verbruik
        dubbel geteld worden in elke NILM-weergave. Uitgesloten wordt
        `entity_b`: de alfabetisch tweede van het paar, precies zoals
        het paar wordt getoond. De knop zet die naam ook in zijn eigen
        label, zodat vooraf zichtbaar is WELK apparaat verdwijnt -
        raden hoort hier niet bij.

        Hergebruikt bewust `reject_nilm_device`, zodat het uitgesloten
        apparaat ook echt op de zwarte lijst komt en niet bij de
        volgende scan terugkeert als verse kandidaat. Het paar
        verdwijnt daarmee vanzelf uit `get_nilm_duplicate_pairs()`
        (een van beide is geen bevestigd apparaat meer), dus een aparte
        registratie is niet nodig.
        """
        if entity_b not in self.nilm_confirmed_devices:
            return False
        return self.reject_nilm_device(entity_b)

    def _narrate_nilm(self) -> str | None:
        """Meldt openstaande NILM-kandidaten of recent gevonden
        mogelijke defecten - alleen als er iets te melden is."""
        bits = []
        candidate_count = len(self.nilm_unconfirmed_candidates)
        if candidate_count > 0:
            bits.append(
                f"er {'staat' if candidate_count == 1 else 'staan'} "
                f"{candidate_count} nog onbeoordeelde NILM-"
                f"{'kandidaat' if candidate_count == 1 else 'kandidaten'}"
            )
        defective = [
            d.get("friendly_name")
            for d in self.nilm_confirmed_devices.values()
            if d.get("anomaly_detected")
        ]
        if defective:
            bits.append(
                f"{len(defective)} apparaat/apparaten tonen mogelijk defect "
                f"gedrag ({', '.join(defective)})"
            )
        if not bits:
            return None
        return "Verder " + " en ".join(bits) + "."

    def _describe_nilm_trend(self, device: dict) -> str:
        """A lighter-weight, more granular trend label than
        `anomaly_detected` (which only fires on a *sustained* CUSUM
        breach, v0.63.39) - just compares the most recent daily average
        against the learned reference, so a modest move shows up well
        before it would ever reach the alarm threshold.

        v0.63.90, gevonden tijdens een diagnostiek-analyse (5 "Eetkamer
        lamp"-sensoren toonden "⚠️ aanhoudend stijgend (-0%) - mogelijk
        defect" - een negatief/nul percentage naast "stijgend"). De
        CUSUM-detector zelf is bewust eenzijdig (accumuleert alleen bij
        afwijkingen boven de referentie, geklemd op minimaal 0), dus
        "stijgend" is conceptueel altijd correct zodra het alarm
        afgaat - maar `estimated_drift_percent` is puur de afwijking
        van de LAATSTE dag, die toevallig rond nul kan liggen ook al
        was de OPGEBOUWDE geschiedenis (over meerdere eerdere dagen)
        wél voldoende om het alarm te triggeren. Een niet-positief
        getal naast "stijgend" tonen is dan misleidend/tegenstrijdig
        ogend - toon het percentage daarom alleen als het ook echt een
        stijging weergeeft.
        """
        reference_avg_w = device.get("reference_avg_w")
        history = device.get("daily_avg_history") or []
        if reference_avg_w is None or not history or reference_avg_w <= 0:
            return "onbekend (nog niet genoeg data)"

        # v1.50.0: vergelijk met de laatste ECHTE dag.
        #
        # De referentie filtert uitvaldagen al weg (v1.21.0), maar deze
        # regel keek naar `history[-1]` - en die kon zelf een uitvaldag
        # zijn. In de export van 11 augustus stond daar 0,9 W tegen een
        # referentie van 76,34: "-98,8% drift, mogelijk defect", terwijl
        # de diepvries de dag ervoor gewoon 80,57 W deed.
        echte_dagen = self._zonder_meetuitval(history)
        latest_avg_w = echte_dagen[-1] if echte_dagen else history[-1]
        change_percent = 100 * (latest_avg_w - reference_avg_w) / reference_avg_w

        if device.get("anomaly_detected"):
            drift = device.get("estimated_drift_percent")
            drift_txt = f" ({drift:+.0f}%)" if drift is not None and drift > 0 else ""
            return f"⚠️ aanhoudend stijgend{drift_txt} - mogelijk defect"
        if change_percent >= NILM_TREND_RISING_THRESHOLD_PERCENT:
            return f"↗ licht stijgend ({change_percent:+.0f}%)"
        if change_percent <= -NILM_TREND_FALLING_THRESHOLD_PERCENT:
            return f"↘ dalend ({change_percent:+.0f}%)"
        return "→ stabiel"

    def get_nilm_candidate_at_slot(self, slot_index: int) -> str | None:
        """Which candidate entity_id currently occupies dashboard slot
        `slot_index` (0-based) - v0.63.41. Sorted alphabetically by
        entity_id for a deterministic, stable ordering (so a given
        candidate doesn't visibly jump between slots from one tick to
        the next just because dict iteration order shifted). Returns
        None if fewer candidates exist than that slot index.
        """
        sorted_ids = sorted(self.nilm_unconfirmed_candidates.keys())
        if slot_index < 0 or slot_index >= len(sorted_ids):
            return None
        return sorted_ids[slot_index]

    def _update_nilm_confirmed_devices(self, now: datetime) -> None:
        """Per-device daily-average tracking + CUSUM drift-detection for
        every confirmed NILM device - same principle as the household
        sluipverbruik detector (v0.63.29), but per device and
        percentage-based (device power levels vary too much for one
        fixed Watt slack/threshold to make sense across all of them).
        """
        any_finalized = False
        for entity_id, device in self.nilm_confirmed_devices.items():
            power_w = self._read_sensor_float(entity_id)

            check_date = self._nilm_datum(device.get("_check_date"))
            device["_check_date"] = check_date
            if check_date != now.date():
                # v1.21.3: pas afronden bij genoeg metingen. Met vijf
                # metingen - een kwartier na een herstart - meldde de
                # diepvries "-98,8% drift, mogelijk defect", terwijl de
                # compressor in dat kwartier gewoon niet draaide.
                #
                # Een apparaat dat in cycli werkt heeft een halve dag
                # nodig voordat een dagcijfer iets zegt.
                if (
                    check_date is not None
                    # v5.14.2: acht uur, omgerekend met het interval.
                    and device.get("_today_count", 0)
                    >= self._metingen_voor(
                        NILM_MIN_UREN_VOOR_DAG, NILM_MIN_SAMPLES_FOR_DAY
                    )
                ):
                    daily_avg_w = device["_today_sum"] / device["_today_count"]
                    self._finalize_nilm_device_day(entity_id, device, daily_avg_w)
                    any_finalized = True
                device["_today_sum"] = 0.0
                device["_today_count"] = 0
                device["_today_on_count"] = 0
                device["_today_on_sum"] = 0.0
                device["_check_date"] = now.date()

            if power_w is not None:
                device["_today_sum"] = device.get("_today_sum", 0.0) + power_w
                device["_today_count"] = device.get("_today_count", 0) + 1
                # v1.50.0: apart bijhouden hoe vaak de compressor DRAAIDE
                # en hoe hard. Gevraagd: "Het is toch simpelweg,
                # aan/uit?" - en dat klopt: het daggemiddelde is het
                # product van draaivermogen en inschakelduur, en die
                # twee door elkaar meten verbergt wat er aan de hand is.
                if power_w >= NILM_COMPRESSOR_ON_THRESHOLD_W:
                    device["_today_on_count"] = (
                        device.get("_today_on_count", 0) + 1
                    )
                    device["_today_on_sum"] = (
                        device.get("_today_on_sum", 0.0) + power_w
                    )

        # v5.149.0: ook elk uur, zodat een herstart (of crash) de lopende
        # dag niet meer wist - zie `_bewaar_nilm_lopende_dag`.
        uur = (now.date(), now.hour)
        if any_finalized or (
            self.nilm_confirmed_devices
            and getattr(self, "_nilm_bewaard_uur", None) != uur
        ):
            self._nilm_bewaard_uur = uur
            # v0.63.66: persist the newly-learned daily history/CUSUM
            # state to the dedicated Store, not just kept in memory.
            self.hass.async_create_task(
                self._async_save_nilm_confirmed_devices_store()
            )

    def _herijk_koelapparaten_na_meetuitval(self) -> None:
        """Herrekent het alarm van koelapparaten zonder de uitvaldagen
        (v1.50.0).

        Het opgebouwde alarm van de diepvries rust op een reeks waarin
        12 van de 30 dagen meetuitval waren. Vanaf nu komen die er niet
        meer in, maar wat er al staat blijft staan - en dan blijft
        "mogelijk defect" hangen op een apparaat dat het gewoon doet.

        Eenmalig, herkenbaar aan een vlag. Bewust GEEN blinde reset: de
        opgeschoonde reeks wordt opnieuw afgespeeld, zodat een apparaat
        dat écht meer is gaan verbruiken zijn alarm houdt.
        """
        for entity_id, device in self.nilm_confirmed_devices.items():
            if device.get("_meetuitval_herijkt") or not self._is_koelapparaat(
                device
            ):
                continue
            device["_meetuitval_herijkt"] = True
            reeks = device.get("daily_avg_history") or []
            echt = self._zonder_meetuitval(reeks)
            if len(echt) == len(reeks) or len(echt) < 3:
                continue

            referentie = statistics.median(echt)
            if referentie <= 0:
                continue
            cusum = 0.0
            for dag in echt:
                afwijking = min(
                    (dag - referentie) / referentie - NILM_CUSUM_SLACK_FRACTION,
                    NILM_CUSUM_MAX_DAILY_CONTRIBUTION,
                )
                cusum = max(0.0, cusum + afwijking)
            device["daily_avg_history"] = echt
            device["reference_avg_w"] = round(referentie, 2)
            device["cusum_accumulator"] = cusum
            device["anomaly_detected"] = cusum >= NILM_CUSUM_ALARM_THRESHOLD
            if not device["anomaly_detected"]:
                device["estimated_drift_percent"] = None
            _LOGGER.info(
                "%s: %d van de %d dagen waren meetuitval; alarm herrekend "
                "over de overgebleven dagen (referentie %.1f W, cusum %.2f)",
                entity_id,
                len(reeks) - len(echt),
                len(reeks),
                referentie,
                cusum,
            )

    @staticmethod
    def _nilm_marge_uit(waarden: list[float]) -> float:
        """De normale schommeling boven de mediaan, als fractie
        (v5.152.0). Minstens de vaste marge, hoogstens 50 %."""
        echt = [w for w in waarden if w is not None and w > 0]
        if len(echt) < 4:
            return NILM_CUSUM_SLACK_FRACTION
        mediaan = statistics.median(echt)
        if mediaan <= 0:
            return NILM_CUSUM_SLACK_FRACTION
        bovenkwartiel = statistics.quantiles(echt, n=4)[2]
        return min(
            NILM_CUSUM_MARGE_MAX,
            max(NILM_CUSUM_SLACK_FRACTION, (bovenkwartiel - mediaan) / mediaan),
        )

    def _nilm_marge(self, device: dict, reference_samples: list[float]) -> float:
        """Hoeveel boven de referentie nog gewoon is voor dit apparaat
        (v5.152.0, akkoord 31-10).

        Gevonden bij de CV-ketel: die verbruikt om de dag 8,2 of 9,9 W.
        Met een vaste marge van 10 % telde elke 9,9-dag (+17 %) mee in de
        optelling, die stond daardoor op 3,5 terwijl het alarm bij 1
        afgaat. Elke dag die toevallig 5 W hoger lag gaf dan meteen
        "mogelijk defect". En de reset (vijf dagen op rij op of onder de
        mediaan) kwam bij zo'n afwisselend patroon nooit.

        De marge is nu het bovenkwartiel van de referentiedagen ten
        opzichte van de mediaan: wat een kwart van de normale dagen al
        haalt, is geen afwijking.

        Niet bijleren tijdens een afwijking: staat het alarm aan, of is de
        optelling al halverwege, dan blijft de laatst geleerde marge staan.
        Anders schuiven de afwijkende dagen het bovenkwartiel op en heet
        het defect na een week vanzelf normaal.
        """
        opgeslagen = device.get("normale_marge")
        if opgeslagen is not None and (
            device.get("anomaly_detected")
            or (device.get("cusum_accumulator") or 0)
            >= NILM_CUSUM_ALARM_THRESHOLD / 2
        ):
            return opgeslagen
        marge = self._nilm_marge_uit(reference_samples)
        device["normale_marge"] = round(marge, 4)
        device["normale_marge_procent"] = round(marge * 100, 1)
        return marge

    def _herijk_nilm_marges(self) -> None:
        """Eenmalig: de optelling opnieuw afspelen met de eigen marge
        van elk apparaat (v5.152.0). Een alarm blijft alleen staan als
        het ook met die marge nog boven de drempel uitkomt."""
        for entity_id, device in self.nilm_confirmed_devices.items():
            if device.get("_marge_herijkt"):
                continue
            reeks = self._zonder_meetuitval(device.get("daily_avg_history") or [])
            if len(reeks) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
                continue
            referentie_reeks = reeks[:-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS] or reeks
            referentie = statistics.median(referentie_reeks)
            if referentie <= 0:
                continue
            marge = self._nilm_marge_uit(referentie_reeks)
            cusum = 0.0
            for dag in reeks:
                cusum = max(
                    0.0,
                    cusum
                    + min(
                        (dag - referentie) / referentie - marge,
                        NILM_CUSUM_MAX_DAILY_CONTRIBUTION,
                    ),
                )
            oud = device.get("cusum_accumulator")
            if oud is not None and abs(cusum - oud) < 0.05:
                continue
            device["_marge_herijkt"] = True
            device["normale_marge"] = round(marge, 4)
            device["normale_marge_procent"] = round(marge * 100, 1)
            device["cusum_accumulator"] = cusum
            if cusum < NILM_CUSUM_ALARM_THRESHOLD:
                device["anomaly_detected"] = False
                device["estimated_drift_percent"] = None
            _LOGGER.info(
                "%s: optelling herrekend met eigen marge %.0f%% (%s -> %.2f)",
                entity_id, marge * 100, oud, cusum,
            )

    def _finalize_nilm_device_day(
        self, entity_id: str, device: dict, daily_avg_w: float
    ) -> None:
        # v1.50.0: eerst de vraag of er überhaupt gekoeld is.
        #
        # Gevraagd: "Het is toch simpelweg, aan/uit?" Precies - en op een
        # dag waarop de compressor vrijwel nooit aansloeg, heeft het
        # daggemiddelde niets te maken met hoe de diepvries het doet.
        #
        # In de reeks van 11 augustus staan 12 van de 30 dagen op 0,8 W
        # en 13 dagen op 76-81 W. Een diepvries doet dat niet; een
        # sensor die hele dagen niets doorgeeft wel. Toch werd elke
        # 0,8-dag als "-98,8% drift, mogelijk defect" gelezen.
        aan = device.get("_today_on_count", 0)
        totaal = device.get("_today_count", 0) or 1
        inschakelduur = aan / totaal
        # De tellers bestaan pas sinds deze versie. Een dag die al liep
        # tijdens de opwaardering - of een aanroep van buitenaf - heeft
        # ze niet, en dan mag deze regel niet toeslaan: anders zou élke
        # dag als meetuitval gelden en zou het hele apparaat na een
        # opwaardering stilvallen.
        kan_oordelen = "_today_on_count" in device
        if self._is_koelapparaat(device) and kan_oordelen:
            if inschakelduur < NILM_COOLING_MIN_DUTY_CYCLE:
                device["meetuitval_dagen"] = (
                    device.get("meetuitval_dagen", 0) + 1
                )
                device["laatste_meetuitval"] = (
                    device.get("_check_date").isoformat()
                    if hasattr(device.get("_check_date"), "isoformat")
                    else str(device.get("_check_date"))
                )
                _LOGGER.debug(
                    "%s: dag overgeslagen, compressor draaide %.1f%% van "
                    "de tijd (%d van %d metingen) - dat is meetuitval, "
                    "geen drift",
                    entity_id,
                    inschakelduur * 100,
                    aan,
                    totaal,
                )
                return
            device["inschakelduur_procent"] = round(inschakelduur * 100, 1)
            device["draaivermogen_w"] = (
                round(device.get("_today_on_sum", 0.0) / aan, 1) if aan else None
            )
            reeks = device.setdefault("duty_cycle_history", [])
            reeks.append(device["inschakelduur_procent"])
            device["duty_cycle_history"] = reeks[-CUSUM_BASELINE_HISTORY_DAYS:]
            vermogens = device.setdefault("draaivermogen_history", [])
            if device["draaivermogen_w"] is not None:
                vermogens.append(device["draaivermogen_w"])
                device["draaivermogen_history"] = vermogens[
                    -CUSUM_BASELINE_HISTORY_DAYS:
                ]

        history = device.setdefault("daily_avg_history", [])
        history.append(round(daily_avg_w, 2))
        device["daily_avg_history"] = history[-CUSUM_BASELINE_HISTORY_DAYS:]
        history = device["daily_avg_history"]

        # v1.21.0: bij koelapparaten ook de buitentemperatuur van die dag
        # bewaren, zodat de referentie weet bij welk weer hij is
        # opgebouwd.
        if self._is_koelapparaat(device):
            buiten = self._read_sensor_float(
                self.config.get(CONF_BACKYARD_TEMPERATURE_SENSOR)
            )
            if buiten is not None:
                temps = device.setdefault("outdoor_temp_history", [])
                temps.append(round(buiten, 1))
                device["outdoor_temp_history"] = temps[-30:]

        if len(history) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
            return
        if len(history) > CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS:
            reference_samples = history[:-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS]
        else:
            reference_samples = history
        if not reference_samples:
            return

        # v1.21.0: dagen zonder meting eerst weggooien.
        #
        # De diepvries wisselde tussen 0,8 W en 90 W - dertien dagen
        # onder 5 W, twaalf boven 60. Een dagGEMIDDELDE van 0,8 W
        # betekent dat de compressor die hele dag niet draaide, en dat
        # kan niet. Dat zijn dagen waarop de meter niets doorgaf.
        #
        # De mediaan over álle dagen belandde daardoor op 19,68 W,
        # precies tussen beide groepen in - en meldde vervolgens "+57,4%
        # drift" terwijl 40,8 W een normale dag was.
        reference_samples = self._zonder_meetuitval(reference_samples)
        if not reference_samples:
            return

        reference_avg_w = statistics.median(reference_samples)
        if reference_avg_w <= 0:
            return
        device["reference_avg_w"] = round(reference_avg_w, 2)

        # v0.63.100: auto-reset bij aanhoudende, genuine terugkeer naar
        # normaal gedrag - zie NILM_CUSUM_RESET_STREAK_DAYS's docstring.
        # Bewust vóór het v0.63.99-plafond gemeten (de RUWE dagwaarde
        # t.o.v. de referentie, niet de al-geplafonneerde bijdrage) -
        # "normaal" betekent hier echt op of onder de referentie, niet
        # slechts "iets minder ver boven de marge".
        # v5.152.0: "normaal" is binnen de eigen schommeling van het
        # apparaat, niet strikt op of onder de mediaan - zie `_nilm_marge`.
        if daily_avg_w <= reference_avg_w * (1 + self._nilm_marge(device, reference_samples)):
            device["_normal_streak_days"] = device.get("_normal_streak_days", 0) + 1
        else:
            device["_normal_streak_days"] = 0

        if (
            device.get("cusum_accumulator", 0.0) > 0
            and device["_normal_streak_days"] >= NILM_CUSUM_RESET_STREAK_DAYS
        ):
            device["cusum_accumulator"] = 0.0
            device["anomaly_detected"] = False
            device["estimated_drift_percent"] = None
            _LOGGER.debug(
                "NILM CUSUM auto-reset voor %s: %d opeenvolgende dagen "
                "terug op/onder referentie (%.2fW)",
                entity_id,
                device["_normal_streak_days"],
                reference_avg_w,
            )
            return

        deviation_fraction = (
            (daily_avg_w - reference_avg_w) / reference_avg_w
            - self._nilm_marge(device, reference_samples)
        )
        # v0.63.99: begrens de bijdrage van één enkele dag, zodat een
        # geïsoleerde uitschieter (zie de constante's docstring) het
        # alarm niet in zijn eentje kan laten afgaan - alleen negatieve
        # kant (te lage waarden) blijft ongeplafonneerd, want die trekt
        # de accumulator juist omlaag (nooit de oorzaak van een
        # onterecht alarm).
        deviation_fraction = min(
            deviation_fraction, NILM_CUSUM_MAX_DAILY_CONTRIBUTION
        )
        device["cusum_accumulator"] = max(
            0.0, device.get("cusum_accumulator", 0.0) + deviation_fraction
        )

        was_detected = device.get("anomaly_detected", False)
        # v1.12.3: een PROCENTUELE drempel is bij kleine vermogens
        # betekenisloos. In een export stond een televisie met
        # referentie 0,79 W als "mogelijk defect" bij -24% drift - dat is
        # 0,19 watt verschil, oftewel meetruis. Vijf meldingen waarvan
        # drie over tienden van watts gaan, leert je ze te negeren, en
        # dan mis je de koelkast die echt stukgaat.
        #
        # Twee ondergrenzen: het apparaat moet noemenswaardig verbruiken
        # ÉN het verschil moet in absolute zin de moeite waard zijn.
        groot_genoeg = reference_avg_w >= NILM_DRIFT_MIN_REFERENCE_W
        verschil_w = abs(daily_avg_w - reference_avg_w)

        # v1.21.0: bij koelapparaten telt de buitentemperatuur mee. Een
        # koelkast in een schuur werkt harder als het buiten warm is;
        # zonder correctie leest een warme week als een defect.
        #
        # De marge werkt alleen naar BOVEN: koeler weer mag geen drift
        # verbergen.
        marge_procent = self._koeling_temperatuurmarge_procent(device)
        device["temperatuurmarge_procent"] = round(marge_procent, 1)
        verklaard_w = reference_avg_w * marge_procent / 100
        boven_verwachting = daily_avg_w > reference_avg_w
        if boven_verwachting and verklaard_w > 0:
            verschil_w = max(0.0, verschil_w - verklaard_w)

        device["anomaly_detected"] = (
            device["cusum_accumulator"] >= NILM_CUSUM_ALARM_THRESHOLD
            and groot_genoeg
            and verschil_w >= NILM_DRIFT_MIN_ABSOLUTE_W
        )
        if device["anomaly_detected"]:
            device["estimated_drift_percent"] = round(
                100 * (daily_avg_w - reference_avg_w) / reference_avg_w, 1
            )
            if not was_detected:
                notify_service = self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
                if notify_service:
                    self._dispatch_notification(
                        notify_service=notify_service,
                        title=f"🔍 Mogelijk defect: {device['friendly_name']}",
                        message=(
                            f"Het verbruik van {device['friendly_name']} ligt "
                            f"structureel ~{device['estimated_drift_percent']:.0f}% "
                            f"hoger dan normaal - mogelijk een beginnend defect. "
                            f"Gebaseerd op een aanhoudende trend, niet één losse dag."
                        ),
                        notification_id=f"ems_nilm_anomaly_{entity_id}",
                        kind="device_drift",
                    )
