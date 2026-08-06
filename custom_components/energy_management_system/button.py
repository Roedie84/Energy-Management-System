"""Button entity to verify the mode/power-change notification (v0.63.8)
works end-to-end, without waiting for a genuine decision change."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_APPLIANCE_NOTIFY_SERVICE,
    DEFAULT_NAME,
    DOMAIN,
    NILM_DASHBOARD_SLOT_COUNT,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [TestNotificationButton(coordinator, entry_id=entry.entry_id)]
    for slot in range(NILM_DASHBOARD_SLOT_COUNT):
        entities.append(NilmConfirmCandidateButton(coordinator, entry.entry_id, slot))
        entities.append(NilmRejectCandidateButton(coordinator, entry.entry_id, slot))
    async_add_entities(entities)


class TestNotificationButton(ButtonEntity):
    """Sends a test notification through the same code path as the real
    mode/power-change notification (_dispatch_notification), using
    whatever CONF_APPLIANCE_NOTIFY_SERVICE is currently configured - so
    pressing it verifies the actual configured notify service works,
    not just a generic HA test notification unrelated to this
    integration's own setup.
    """

    _attr_has_entity_name = True
    _attr_name = "Test notificatie versturen"
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_test_notification"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    async def async_press(self) -> None:
        notify_service = self._coordinator.config.get(CONF_APPLIANCE_NOTIFY_SERVICE)
        self._coordinator._dispatch_notification(
            notify_service=notify_service,
            title="🔔 Testmelding Energy Management System",
            message=(
                "Dit is een testmelding om te bevestigen dat de "
                "notify-service correct is ingesteld. Als je dit ziet, "
                "werken modus/vermogen-wijziging-meldingen ook."
            ),
            notification_id="ems_test_notification",
        )


class _NilmSlotButton(ButtonEntity):
    """Shared base for the 8 confirm/reject slot-pairs (v0.63.41/.43/.47)
    - see `EnergyManagementSystemCoordinator.get_nilm_candidate_at_slot`
    for why a fixed number of slots is used instead of one dynamic
    button per candidate (a static Lovelace dashboard can't render an
    unknown-length, changing list without an extra HACS frontend card).

    v0.63.43: the entity's own `name` is dynamic (candidate name + live
    power), not a static "slot N" label - reported: a static label plus
    a separate cross-reference table got badly truncated on a narrow/
    mobile dashboard, making it unusable. Putting the actual candidate
    directly in the button's name removes the need to cross-reference
    anything.

    v0.63.47: `has_entity_name` deliberately OFF (unlike every other
    entity in this integration) - reported: with it on, Home Assistant
    prefixes every display of the name with the device name ("Energy
    Management System ..."), which in a narrow name column truncated
    down to just "E..." - defeating the whole point of v0.63.43's fix.
    These buttons are read as standalone action labels, not as
    device-scoped sub-features, so the prefix adds nothing but length.

    v0.63.48: registers itself as a coordinator listener (same pattern
    already used by `SolarForecastAccuracyTracker`) - reported: slots
    stayed empty indefinitely, even right after a fresh discovery.
    `ButtonEntity` doesn't poll by default (unlike `SensorEntity`, which
    is why the sensors in this integration refresh fine on their own),
    so without an explicit push after every coordinator update, the
    button's displayed name/attributes just froze at whatever they
    happened to be the one time Home Assistant wrote their initial
    state during setup - typically "(leeg)", since discovery hadn't run
    yet at that point.

    v0.63.74, reported ("kan niet beoordelen afwijzen etc van nieuwe
    apparaten" - nothing rendered at all under "Bevestigen / negeren"):
    without `has_entity_name` (turned off in v0.63.47) and without an
    explicit object_id, Home Assistant derives the entity_id from this
    entity's own `name` property at first registration - but that name
    is deliberately DYNAMIC (v0.63.43, shows whichever candidate
    currently occupies the slot). On a fresh registration this baked an
    unpredictable entity_id (based on whatever candidate happened to be
    in that slot the very first time, or "sleuf-n-leeg" if none yet) -
    not the stable `nilm_kandidaat_N_bevestigen/negeren` id the bundled
    dashboard hardcodes, so every dashboard reference to these buttons
    silently pointed at a non-existent entity.

    v0.63.74 first tried to fix this with `_attr_suggested_object_id` -
    reported back that deleting the entities and restarting still
    didn't help. Verified against Home Assistant's own developer docs
    (https://developers.home-assistant.io/docs/core/entity) and source:
    `_attr_suggested_object_id` is not a real, public Entity attribute
    at all (a mistaken assumption on Claude's part) - the actual
    internal mechanism (`internal_integration_suggested_object_id`) is
    explicitly documented as "only handled internally, never to be used
    by integrations". v0.63.79 fixes this properly by setting
    `self.entity_id` directly in `__init__`, before the entity is ever
    added to hass - this IS a genuine, respected override (Entity's
    `entity_id` is a plain settable attribute; Home Assistant only
    auto-generates one when the integration hasn't already set it).
    Matches the exact "woonkamer_energy_management_system_..." prefix
    the bundled dashboard already hardcodes for every other entity in
    this integration (which normally arises automatically through
    `has_entity_name` + the device's own configured name) - since these
    16 buttons deliberately don't use `has_entity_name`, that prefix has
    to be spelled out explicitly here instead.

    v0.63.80, reported ("Je kunt enkel 0 van de 16 entiteiten
    verwijderen. De andere vereisen dat de integratie stopt met ze aan
    te leveren"): Home Assistant blocks manually deleting entities that
    are still actively provided by a loaded integration, making the
    v0.63.74/.79 migration instructions (delete then restart)
    unworkable via the UI - and even restarting alone wouldn't have
    helped anyway, since HA's entity registry looks up an *existing*
    entry by `unique_id` first and reuses its stored (old, wrong)
    entity_id, never re-applying a newly-set `self.entity_id` for an
    already-registered unique_id. Fixed by bumping `unique_id` itself
    (a "_v2" suffix) - Home Assistant then has no matching registry
    entry at all, so it genuinely re-registers these 16 buttons fresh,
    correctly applying the explicit entity_id this time.

    v0.63.81, reported (still showing a "_2"-suffixed entity_id after
    deleting the old v1 entities and restarting): confirmed via
    Developer Tools > States - the "_v2" entities themselves had
    already been assigned a "_2"-deduplicated entity_id during an
    *earlier* restart, at a point where the old v1 entities (not yet
    deleted then) were still occupying the plain name. Once Home
    Assistant assigns a deduplicated entity_id for a given unique_id,
    that assignment is permanent in the registry - it never gets
    "upgraded" back to the plain name later just because the conflict
    is resolved, and by the time these "_v2" entities are themselves
    the live, actively-provided ones, they hit the exact same
    can't-delete-active-entities wall as the v1 ones did. Bumped to
    "_v3" - since the v1 entities are now genuinely gone from the
    registry (the person confirmed deleting them), this generation has
    nothing left to collide with and should register with the plain,
    correct entity_id on the very next restart. No manual deletion
    needed; the "_v2" entities simply stop being provided and can be
    ignored or cleaned up whenever convenient.
    """

    def __init__(
        self,
        coordinator,
        entry_id: str,
        slot: int,
        unique_suffix: str,
        object_id_suffix: str,
    ) -> None:
        self._coordinator = coordinator
        self._slot = slot
        # v0.63.81: bumped to "_v3" - the "_v2" generation (v0.63.80)
        # had itself already been assigned a "_2"-deduplicated
        # entity_id during an earlier restart (while the old v1
        # entities were still occupying the plain name), and once
        # assigned, Home Assistant never "upgrades" that back to the
        # plain name later. With the v1 entities now genuinely deleted,
        # this generation has nothing left to collide with. No manual
        # deletion needed - the old generations simply stop being
        # provided and can be ignored or cleaned up whenever
        # convenient. No state was ever tied to these buttons' own
        # unique_id (the coordinator's own persisted state is keyed by
        # the monitored sensor's entity_id, not by this button's
        # identity).
        self._attr_unique_id = f"{entry_id}_nilm_slot_{slot}_{unique_suffix}_v3"
        # v0.63.79: set entity_id directly - a genuine, respected
        # override, unlike the non-existent _attr_suggested_object_id
        # tried in v0.63.74. Matches the "woonkamer_energy_management_
        # system_..." prefix the bundled dashboard already hardcodes for
        # every other entity (there arising automatically through
        # has_entity_name + the device's configured name); spelled out
        # explicitly here since these buttons deliberately don't use
        # has_entity_name (v0.63.47).
        self.entity_id = (
            f"button.woonkamer_energy_management_system_nilm_kandidaat_"
            f"{slot + 1}_{object_id_suffix}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }
        # v0.63.107, gerapporteerd: "keuzes welke ik reeds gemaakt heb
        # [werden] niet opgeslagen en na een herstart dus weer terug
        # kwamen" - specifiek apparaten die al via de knop waren
        # bevestigd/afgewezen. Root cause: `async_press()` vroeg de
        # sleuf-inhoud OPNIEUW op op het moment van drukken, in plaats
        # van het entity_id te gebruiken dat op het scherm werd
        # getoond. Als er tussen het TONEN van de knop en het DRUKKEN
        # een coordinator-tick plaatsvond die de sleuf-inhoud liet
        # verschuiven (bijv. een nieuw ontdekte kandidaat die
        # alfabetisch eerder komt dan `get_nilm_candidate_at_slot`'s
        # sortering), bevestigde/wees de gebruiker in werkelijkheid een
        # ANDER apparaat af dan wat ze zagen - en het apparaat dat ze
        # écht bedoelden bleef gewoon in de lijst staan, dus kwam het
        # na een herstart "terug". Nu vastgelegd zodra het voor weergave
        # wordt opgevraagd (`_slot_label`/`extra_state_attributes`,
        # beide door HA aangeroepen vlak vóór elke state-schrijving),
        # en `async_press()` gebruikt exact diezelfde, vastgelegde
        # waarde - nooit een verse opvraag op het moment van drukken.
        self._last_displayed_entity_id: str | None = None

    def _resolve_and_cache_slot_entity_id(self) -> str | None:
        entity_id = self._coordinator.get_nilm_candidate_at_slot(self._slot)
        self._last_displayed_entity_id = entity_id
        return entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    def _slot_label(self) -> str:
        entity_id = self._resolve_and_cache_slot_entity_id()
        if entity_id is None:
            return f"Sleuf {self._slot + 1} (leeg)"
        candidate = self._coordinator.nilm_unconfirmed_candidates.get(entity_id, {})
        naam = candidate.get("friendly_name") or entity_id
        power_w = candidate.get("current_power_w")
        power_txt = f" {power_w:.0f}W" if power_w is not None else ""
        return f"{naam}{power_txt}"

    @property
    def extra_state_attributes(self) -> dict:
        entity_id = self._resolve_and_cache_slot_entity_id()
        if entity_id is None:
            return {"kandidaat_entity_id": None, "kandidaat_naam": None}
        candidate = self._coordinator.nilm_unconfirmed_candidates.get(entity_id, {})
        return {
            "kandidaat_entity_id": entity_id,
            "kandidaat_naam": candidate.get("friendly_name"),
            "kandidaat_vermogen_w": candidate.get("current_power_w"),
        }


class NilmConfirmCandidateButton(_NilmSlotButton):
    """Confirms whichever candidate currently occupies this slot."""

    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator, entry_id: str, slot: int) -> None:
        super().__init__(coordinator, entry_id, slot, "confirm", "bevestigen")

    @property
    def name(self) -> str:
        return f"✅ {self._slot_label()}"

    async def async_press(self) -> None:
        # v0.63.107: gebruik het entity_id dat op het scherm werd
        # getoond (vastgelegd in `_last_displayed_entity_id`), niet een
        # verse opvraag op het moment van drukken - zie
        # `_NilmSlotButton.__init__`'s docstring voor de volledige
        # toelichting. Terugval op een verse opvraag alleen als er om
        # wat voor reden dan ook nog nooit iets is vastgelegd (zou
        # normaal niet voorkomen, aangezien HA de state altijd eerst
        # schrijft/toont voordat een knop gedrukt kan worden).
        entity_id = self._last_displayed_entity_id
        if entity_id is None:
            entity_id = self._resolve_and_cache_slot_entity_id()
        if entity_id is not None:
            self._coordinator.confirm_nilm_device(entity_id)


class NilmRejectCandidateButton(_NilmSlotButton):
    """Rejects whichever candidate currently occupies this slot."""

    _attr_icon = "mdi:close-circle-outline"

    def __init__(self, coordinator, entry_id: str, slot: int) -> None:
        super().__init__(coordinator, entry_id, slot, "reject", "negeren")

    @property
    def name(self) -> str:
        return f"❌ {self._slot_label()}"

    async def async_press(self) -> None:
        # v0.63.107: zie NilmConfirmCandidateButton.async_press's
        # commentaar - zelfde fix, zelfde reden.
        entity_id = self._last_displayed_entity_id
        if entity_id is None:
            entity_id = self._resolve_and_cache_slot_entity_id()
        if entity_id is not None:
            self._coordinator.reject_nilm_device(entity_id)
