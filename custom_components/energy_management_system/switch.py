"""Switch entity that forces manual mode (bypasses the control loop entirely)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    HANDMATIG_LAADVERMOGEN_W,
    HANDMATIG_LAADVERMOGEN_W,
    HANDMATIGE_STAND_LADEN,
    HANDMATIGE_STAND_SMART_CHARGE,
    NOTIFICATION_TYPES,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ForceManualSwitch(coordinator, entry_id=entry.entry_id),
            KalibratieSwitch(coordinator, entry_id=entry.entry_id),
            LearningOnlySwitch(coordinator, entry_id=entry.entry_id),
            # v3.77.0: de accu met de hand aansturen zonder de
            # Zendure-app.
            HandmatigeStandSwitch(
                coordinator,
                entry_id=entry.entry_id,
                stand=HANDMATIGE_STAND_LADEN,
                # v3.80.0: het vermogen NIET in de naam.
                #
                # Home Assistant leidt de entiteit-ID af van de
                # weergavenaam zodra er geen expliciete is meegegeven,
                # en dan werd het `..._handmatig_laden_2000_w`. Dat
                # bakt een instelling in een identiteit: wijzigt het
                # vermogen ooit, dan klopt de naam niet meer.
                #
                # Het vermogen staat in de toelichting en op de
                # dashboardkaart, waar het thuishoort.
                naam="Handmatig laden",
                icoon="mdi:battery-charging-high",
            ),
            HandmatigeStandSwitch(
                coordinator,
                entry_id=entry.entry_id,
                stand=HANDMATIGE_STAND_SMART_CHARGE,
                naam="Handmatig smart charge",
                icoon="mdi:solar-power-variant",
            ),
            VacationModeSwitch(coordinator, entry_id=entry.entry_id),
            NuLadenSwitch(coordinator, entry_id=entry.entry_id),
            AchterhoeksSwitch(coordinator, entry_id=entry.entry_id),
            SteelstofzuigerOverrideSwitch(coordinator, entry_id=entry.entry_id),
            FietsladersOverrideSwitch(coordinator, entry_id=entry.entry_id),
            ApplianceReadyNotificationsSwitch(coordinator, entry_id=entry.entry_id),
            # v1.2.0: hoofdschakelaar plus één schakelaar per soort
            # melding. De standen worden bewaard in de gedeelde Store
            # (v1.0.4), niet in de entiteit-state - anders zou een
            # gebruikerskeuze bij een herstart terugspringen naar de
            # standaard.
            NotificationsMasterSwitch(coordinator, entry_id=entry.entry_id),
            *[
                NotificationTypeSwitch(
                    coordinator, entry_id=entry.entry_id, kind=sleutel, label=label
                )
                for sleutel, label, _, _, _ in NOTIFICATION_TYPES
            ],
        ]
    )


class KalibratieSwitch(SwitchEntity, RestoreEntity):
    """Kalibratiestand: de accu wordt met de hand geladen (v3.27.0).

    Gevraagd: "Af en toe moet een kalibratie worden gedaan voor de accu.
    Dit houdt in ontladen tot 5% en dan in 1 keer zonder ontladen naar
    100% laden."

    Verschil met `Force manual`: daar valt ook de goedkope koeling weg,
    en de ventilator komt dan pas boven 35 graden. Bij 2000 W is dat te
    laat - op 18 augustus stond de omvormer bij 2038 W op 42 graden.
    Tijdens een kalibratie blijft de koeling dus gewoon schakelen.

    Wat er wél stilvalt: netladingafrekening, piekmeting,
    tekortdetectie, verbruiksleer en apparaatherkenning. Die zouden een
    kalibratie als een gewone dag opvatten en er de verkeerde les uit
    trekken.
    """

    _attr_has_entity_name = True
    _attr_name = "Kalibratie"
    _attr_icon = "mdi:battery-sync"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_kalibratie"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.kalibratie

    @property
    def extra_state_attributes(self) -> dict:
        opname = self._coordinator.kalibratie_momentopname
        if not opname:
            return {"momentopname": "nog niet vol geweest"}
        return {
            "moment": opname.get("moment"),
            "soc_percent": opname.get("soc_percent"),
            "modules": opname.get("modules"),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # v3.42.1: de stand komt uit de Store, niet uit deze entiteit.
        #
        # Gevonden door structuurscan 11, die op dezelfde dag werd
        # geschreven naar aanleiding van de klimaatcellen. Ik had in
        # v3.27.0 de kalibratiestand in de opslag gezet én dit
        # herstelpad laten staan - twee bronnen voor dezelfde vlag.
        #
        # Deze entiteit wordt opgezet NA het terugzetten van de opslag,
        # dus won hij altijd. Zet je de stand uit en herstart je binnen
        # de dertig seconden voordat de opslag is weggeschreven, dan
        # kwam de kalibratie terug alsof er niets gebeurd was.
        #
        # De opslag is leidend: die draagt ook de momentopname en de
        # lopende capaciteitsmeting, en die drie horen bij elkaar.

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_kalibratie(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_kalibratie(False)
        self.async_write_ha_state()


class ForceManualSwitch(SwitchEntity, RestoreEntity):
    """When on, the coordinator will not touch the Zendure operation mode at all."""

    _attr_has_entity_name = True
    _attr_name = "Force manual"
    _attr_icon = "mdi:hand-back-right"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_force_manual"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.force_manual

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.force_manual = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_force_manual(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_force_manual(False)
        self.async_write_ha_state()


class LearningOnlySwitch(SwitchEntity, RestoreEntity):
    """When on: keep computing and learning, but never control the Zendure.

    Useful to validate the logic (and let the night-consumption / solar-bias
    learning build up history) before trusting it to actually steer the
    battery.
    """

    _attr_has_entity_name = True
    _attr_name = "Learning only (no control)"
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_learning_only"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.learning_only

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.learning_only = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_learning_only(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_learning_only(False)
        self.async_write_ha_state()


class HandmatigeStandSwitch(SwitchEntity, RestoreEntity):
    """De accu met de hand op laden of op smart_charging (v3.77.0).

    Gevraagd: "Ik zou hier graag 2 buttons bij hebben - Manual 2000W
    laden en Smart_charge. Dit zorgt ervoor dat ik de Zendure app niet
    meer nodig heb."

    Twee schakelaars die dezelfde klasse delen; ze sluiten elkaar uit,
    want de accu kan maar in één stand staan.

    Bewust GEEN herstel na een herstart. De andere schakelaars doen dat
    wel, maar hier zou het betekenen dat de accu na een herstart uren
    later nog handmatig staat te laden zonder dat iemand er nog aan
    denkt - en dat is precies wat er op 28 augustus een halve dag
    gebeurde.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str, stand: str, naam: str,
                 icoon: str) -> None:
        self._coordinator = coordinator
        self._stand = stand
        self._attr_name = naam
        self._attr_icon = icoon
        self._attr_unique_id = f"{entry_id}_handmatig_{stand}"
        # v3.79.0: de naam expliciet, net als bij de meldingen.
        #
        # Zonder dit leidt Home Assistant hem af van de apparaatnaam, en
        # dan is niet te voorspellen hoe hij heet - de bestaande
        # schakelaars laten zien dat dat ongelijk uitpakt:
        # `switch.energy_management_system_learning_only_no_control`
        # naast `switch.woonkamer_energy_management_system_vacation_mode`.
        #
        # Een dashboardkaart heeft een vaste naam nodig.
        self.entity_id = (
            f"switch.woonkamer_energy_management_system_handmatig_{stand}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.handmatige_stand == self._stand

    @property
    def extra_state_attributes(self) -> dict:
        sinds = self._coordinator.handmatige_stand_sinds
        return {
            "sinds": sinds.isoformat() if sinds else None,
            # v3.79.0: het vermogen als ATTRIBUUT, niet in de naam.
            #
            # Home Assistant leidt de entity_id af van de weergavenaam
            # als de entiteit al bestond, en dan ontstaat
            # `..._handmatig_laden_2000_w`. Dat getal hoort in de knop,
            # niet in de identiteit: wijzigt het ooit, dan klopt elke
            # verwijzing niet meer.
            "vermogen_w": (
                HANDMATIG_LAADVERMOGEN_W
                if self._stand == HANDMATIGE_STAND_LADEN
                else None
            ),
            "leermodus_door_deze_schakelaar": (
                self._coordinator._leermodus_door_handmatige_stand
            ),
            "vermogen_w": (
                HANDMATIG_LAADVERMOGEN_W
                if self._stand == HANDMATIGE_STAND_LADEN
                else None
            ),
            "toelichting": (
                "Zolang dit aan staat stuurt EMS niet, en komt er elk uur "
                "een herinnering. Bij een volle accu zet de integratie "
                "het zelf uit."
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_handmatige_stand(self._stand)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        # Alleen uitzetten wat DEZE schakelaar heeft aangezet; anders
        # zet de ene knop de andere uit.
        if self._coordinator.handmatige_stand == self._stand:
            await self._coordinator.async_set_handmatige_stand(None)
        self.async_write_ha_state()


class AchterhoeksSwitch(SwitchEntity, RestoreEntity):
    """Meldingen in het Achterhoeks (v1.24.0).

    Gevraagd: "kan ik door middel van 1 switch alles in het Achterhoeks
    laten tonen, dus ook de meldingen op mijn iPhone?"

    De hele integratie vertalen zou ongeveer 1.664 losse teksten in de
    code raken plus ruim 3.000 dashboardlabels. Alleen de MELDINGEN is
    een fractie daarvan en levert het leukste deel op: de telefoon
    spreekt Achterhoeks, het dashboard blijft leesbaar voor wie
    meekijkt.

    Geldt voor de telefoon én het meldingenoverzicht, zodat beide
    dezelfde taal spreken.
    """

    _attr_has_entity_name = True
    _attr_name = "Meldingen in het Achterhoeks"
    _attr_icon = "mdi:translate"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_achterhoeks"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.achterhoeks

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.achterhoeks = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._coordinator.achterhoeks = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._coordinator.achterhoeks = False
        self.async_write_ha_state()


class VacationModeSwitch(SwitchEntity, RestoreEntity):
    """When on: assume much lower household consumption (see the
    'Vacation consumption reduction (%)' option), and pause learning from
    live consumption data entirely - so the unusually low vacation
    readings don't pollute the learned "normal" profile, which would
    otherwise take a while to recover after coming back.
    """

    _attr_has_entity_name = True
    _attr_name = "Vacation mode"
    _attr_icon = "mdi:bag-suitcase-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_vacation_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.vacation_mode

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.vacation_mode = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._coordinator.vacation_mode = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._coordinator.vacation_mode = False
        self.async_write_ha_state()


class NuLadenSwitch(SwitchEntity):
    """Zet het uitstelplan opzij tot het einde van het venster (v1.56.0).

    Gevraagd: "als ik weet dat ik veel ga gebruiken is een button die
    overschakelt naar smart (en automatische reset na 2 uur bijvoorbeeld)
    een idee?"

    Geen RestoreEntity: de coordinator bewaart de EINDTIJD zelf. Zou deze
    schakelaar zijn eigen aan/uit terugzetten, dan zou hij na een
    herstart aan blijven staan terwijl de tijd allang verstreken is.
    """

    _attr_has_entity_name = True
    _attr_name = "Nu laden"
    _attr_icon = "mdi:battery-charging-high"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_nu_laden"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.nu_laden_actief()

    @property
    def extra_state_attributes(self) -> dict:
        return self._coordinator.get_nu_laden_status()

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_nu_laden(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_nu_laden(False)
        self.async_write_ha_state()


class SteelstofzuigerOverrideSwitch(SwitchEntity, RestoreEntity):
    """When on, the coordinator leaves the steelstofzuiger charger switch
    completely alone (v0.63.14) - per-appliance equivalent of
    `Force manual`, but scoped to just this one appliance instead of the
    whole battery control loop.
    """

    _attr_has_entity_name = True
    _attr_name = "Steelstofzuiger overrule"
    _attr_icon = "mdi:hand-back-right-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_steelstofzuiger_override"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.steelstofzuiger_override

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.steelstofzuiger_override = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_steelstofzuiger_override(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_steelstofzuiger_override(False)
        self.async_write_ha_state()


class FietsladersOverrideSwitch(SwitchEntity, RestoreEntity):
    """Mirror of SteelstofzuigerOverrideSwitch, for the e-bike chargers."""

    _attr_has_entity_name = True
    _attr_name = "Fietsladers overrule"
    _attr_icon = "mdi:hand-back-right-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_fietsladers_override"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.fietsladers_override

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.fietsladers_override = last_state.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_fietsladers_override(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_fietsladers_override(False)
        self.async_write_ha_state()


class ApplianceReadyNotificationsSwitch(SwitchEntity, RestoreEntity):
    """When off, suppresses the "Goedkoop moment voor de vaatwasser/
    wasmachine" suggestion notifications specifically (v0.63.54,
    requested) - independent of `appliance_notify_service` itself,
    which is shared by several other, unrelated notification types
    (mode-change, steelstofzuiger/fietsladers-done, NILM anomaly,
    sluipverbruik) that should keep working even if this one specific
    suggestion is unwanted. Defaults on (unchanged prior behaviour).
    """

    _attr_has_entity_name = True
    _attr_name = "Vaatwasser/wasmachine-meldingen"
    _attr_icon = "mdi:bell-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_appliance_ready_notifications_enabled"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    @property
    def is_on(self) -> bool:
        return self._coordinator.appliance_ready_notifications_enabled

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._coordinator.appliance_ready_notifications_enabled = (
                last_state.state == "on"
            )

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_set_appliance_ready_notifications_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_set_appliance_ready_notifications_enabled(False)
        self.async_write_ha_state()


class NotificationsMasterSwitch(SwitchEntity):
    """Hoofdschakelaar voor alle meldingen (v1.2.0).

    Handig om alles in één keer stil te zetten, bijvoorbeeld als je een
    weekend weg bent, zonder twintig schakelaars los te hoeven omzetten
    en achteraf te moeten onthouden welke aan stonden.

    Geen RestoreEntity: de stand gaat mee in de gedeelde Store, samen
    met de standen van de losse meldingen. Twee bewaarplekken naast
    elkaar zouden na een herstart uit elkaar kunnen lopen.
    """

    _attr_has_entity_name = True
    _attr_name = "Meldingen (hoofdschakelaar)"
    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_notifications_master"
        self.entity_id = (
            "switch.woonkamer_energy_management_system_meldingen_hoofdschakelaar"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def is_on(self) -> bool:
        return self._coordinator.notifications_master_enabled

    @property
    def extra_state_attributes(self) -> dict:
        overzicht = self._coordinator.get_notification_overview()
        return {
            "aantal_soorten": len(overzicht),
            "aantal_ingeschakeld": sum(
                1 for m in overzicht if m["ingeschakeld"]
            ),
            "note": (
                "Staat deze uit, dan gaat er geen enkele melding meer uit, "
                "ongeacht de losse schakelaars. Die behouden hun eigen "
                "stand, zodat je na het aanzetten weer precies hebt wat je "
                "had."
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        self._coordinator.notifications_master_enabled = True
        self._coordinator.schedule_persisted_state_save()
        self._coordinator._notify_listeners()

    async def async_turn_off(self, **kwargs) -> None:
        self._coordinator.notifications_master_enabled = False
        self._coordinator.schedule_persisted_state_save()
        self._coordinator._notify_listeners()


class NotificationTypeSwitch(SwitchEntity):
    """Aan/uit voor één soort melding (v1.2.0).

    Gevraagd: "zoveel mogelijk relevante meldingen toevoegen, let wel
    dat ze op het tabblad uit te schakelen zijn."

    Alleen de zes bestaande soorten staan standaard aan; alles wat in
    v1.2.0 is toegevoegd begint uit. Twintig meldingen die zichzelf
    aanzetten is een garantie dat er binnen een week niets meer van
    gelezen wordt - en dan is de hele functie waardeloos.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-outline"

    def __init__(self, coordinator, entry_id: str, kind: str, label: str) -> None:
        self._coordinator = coordinator
        self._kind = kind
        self._attr_name = f"Melding: {label}"
        self._attr_unique_id = f"{entry_id}_notification_{kind}"
        self.entity_id = (
            f"switch.woonkamer_energy_management_system_melding_{kind}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self.async_write_ha_state)
        await super().async_will_remove_from_hass()

    @property
    def is_on(self) -> bool:
        definitie = self._coordinator.notification_definition(self._kind)
        standaard = definitie[3] if definitie else False
        return self._coordinator.notification_enabled.get(self._kind, standaard)

    @property
    def extra_state_attributes(self) -> dict:
        definitie = self._coordinator.notification_definition(self._kind) or ()
        return {
            "soort": self._kind,
            "uitleg": definitie[2] if definitie else None,
            "dempingsvenster_minuten": definitie[4] if definitie else None,
            "laatst_verstuurd": self._coordinator.notification_last_sent.get(
                self._kind
            ),
            "onderdrukt_sinds_laatste": (
                self._coordinator.notification_suppressed_count.get(self._kind, 0)
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        self._coordinator.set_notification_enabled(self._kind, True)

    async def async_turn_off(self, **kwargs) -> None:
        self._coordinator.set_notification_enabled(self._kind, False)
