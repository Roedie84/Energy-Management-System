"""Jaarafrekening (v5.188.0): de lijm tussen de coordinator en `jaarafrekening.py`.

Alleen lezen: eens per uur (op een kwartiergrens, op de achtergrond) de
dagtotalen van het contractjaar en het jaar ervoor uit de langetermijnstatistiek
van de recorder, en daar de kaart van maken. Stuurt niets; een fout blijft in
internal_failures["jaarafrekening"] en raakt de ronde nooit.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from homeassistant.util import dt as dt_util

from . import jaarafrekening as ja
from .const import (
    CONF_CONTRACT_START_DATE,
    CONF_GAS_EUR_VANDAAG_SENSOR,
    CONF_GAS_METER_TOTAL_SENSOR,
    CONF_GAS_M3_VANDAAG_SENSOR,
    CONF_GAS_NIEUW_KORTING_JAAR,
    CONF_GAS_NIEUW_PRIJS_ENTITY,
    CONF_GAS_NIEUW_TERMIJN_EUR,
    CONF_GAS_NIEUW_VASTRECHT_MND,
    CONF_GAS_OVERSTAP_DATUM,
    CONF_GRID_EXPORT_ENERGY_SENSOR,
    CONF_GRID_IMPORT_ENERGY_SENSOR,
    CONF_INKOOP_EUR_VANDAAG_SENSOR,
    CONF_JAAR_AFSCHRIJFDAG,
    CONF_JAAR_NETBEHEER_GAS_JAAR,
    CONF_JAAR_NETBEHEER_STROOM_JAAR,
    CONF_JAAR_TERMIJN_EUR,
    CONF_JAAR_VASTRECHT_GAS_MND,
    CONF_JAAR_VASTRECHT_STROOM_MND,
    CONF_JAAR_VERMINDERING_EB_JAAR,
    CONF_SALDEREN_END_DATE,
    CONF_TERUGLEVER_EUR_VANDAAG_SENSOR,
    DEFAULT_GAS_NIEUW_KORTING_JAAR,
    DEFAULT_GAS_NIEUW_VASTRECHT_MND,
    DEFAULT_JAAR_AFSCHRIJFDAG,
    DEFAULT_JAAR_NETBEHEER_GAS_JAAR,
    DEFAULT_JAAR_NETBEHEER_STROOM_JAAR,
    DEFAULT_JAAR_TERMIJN_EUR,
    DEFAULT_JAAR_VASTRECHT_GAS_MND,
    DEFAULT_JAAR_VASTRECHT_STROOM_MND,
    DEFAULT_JAAR_VERMINDERING_EB_JAAR,
    DEFAULT_SALDEREN_END_DATE,
    JAARAFREKENING_VERVERS_S,
)

_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")

#: veld in de dagwaarden -> config-sleutel van de bronsensor (dagtotaal of meterstand)
BRONNEN = {
    "afname_eur": CONF_INKOOP_EUR_VANDAAG_SENSOR,
    "terug_eur": CONF_TERUGLEVER_EUR_VANDAAG_SENSOR,
    "gas_eur": CONF_GAS_EUR_VANDAAG_SENSOR,
    "gas_m3": CONF_GAS_M3_VANDAAG_SENSOR,
    "afname_kwh": CONF_GRID_IMPORT_ENERGY_SENSOR,
    "terug_kwh": CONF_GRID_EXPORT_ENERGY_SENSOR,
}


def _datum(rauw) -> date | None:
    if not rauw:
        return None
    try:
        return date.fromisoformat(str(rauw))
    except (TypeError, ValueError):
        return None


def _getal(rauw, standaard):
    if rauw in (None, ""):
        return standaard
    try:
        return float(str(rauw).replace(",", "."))
    except (TypeError, ValueError):
        return standaard


def dagen_uit_statistiek(rijen: dict, ids: dict) -> dict:
    """{entiteit: [rij met start/change]} -> {date: {veld: waarde}} (lokale datum)."""
    dagen: dict = {}
    for veld, entiteit in ids.items():
        for rij in (rijen or {}).get(entiteit, []) or []:
            verandering = rij.get("change")
            start = rij.get("start")
            if not isinstance(verandering, (int, float)) or start is None:
                continue
            if isinstance(start, (int, float)):
                moment = datetime.fromtimestamp(start, tz=timezone.utc)
            else:
                moment = start
            dag = dt_util.as_local(moment).date()
            dagen.setdefault(dag, {})[veld] = float(verandering)
    return dagen


class JaarafrekeningMixin:
    """v5.188.0. Toestand als klassestandaard (de `__init__` zit aan zijn grens)."""

    _jaarafrekening: dict | None = None
    _jaarafrekening_ververst: datetime | None = None
    _jaarafrekening_bezig: bool = False
    _jaarafrekening_status: str = "nog niet berekend"

    def get_jaarafrekening(self) -> dict:
        if self._jaarafrekening is None:
            return {"status": self._jaarafrekening_status}
        return {**self._jaarafrekening, "status": self._jaarafrekening_status}

    def jaarafrekening_saldo(self):
        return (self._jaarafrekening or {}).get("verwacht_saldo_eur")

    _gasmeter_dagstart: tuple | None = None

    def get_kosten_vandaag(self) -> dict:
        """v5.203.0: stroom en gas van vandaag inclusief de vaste kosten -
        zie `ja.kosten_vandaag`. De vaste kosten tellen voor de hele dag.
        Na de gasoverstap: m3 vandaag (gasmeter sinds middernacht) x de
        prijs van de nieuwe leverancier."""
        try:
            nu = dt_util.now()
            vandaag = dt_util.as_local(nu).date()
            inst = self._jaarafrekening_instellingen()
            c = self.config
            afname = self._read_sensor_float(c.get(CONF_INKOOP_EUR_VANDAAG_SENSOR))
            terug = self._read_sensor_float(c.get(CONF_TERUGLEVER_EUR_VANDAAG_SENSOR))
            gas = self._read_sensor_float(c.get(CONF_GAS_EUR_VANDAAG_SENSOR))
            m3 = self._read_sensor_float(c.get(CONF_GAS_M3_VANDAAG_SENSOR))
            bron_gas = "Zonneplan"
            if inst.gas_overstap is not None and vandaag >= inst.gas_overstap:
                bron_gas = "nieuwe leverancier"
                m3 = self._gas_m3_vandaag_meter(vandaag)
                gas = (m3 * inst.gas_nieuw_prijs_m3
                       if m3 is not None and inst.gas_nieuw_prijs_m3 is not None else None)
            uit = ja.kosten_vandaag(afname_eur=afname, terug_eur=terug, gas_eur=gas,
                                    vast=ja.vaste_kosten_dag(inst, vandaag))
            uit.update(gas_m3=None if m3 is None else round(m3, 3), gas_bron=bron_gas,
                       vast_hele_dag=True)
            return uit
        except Exception as err:  # noqa: BLE001 - een overzicht mag nooit breken
            return {"stroom_eur": None, "gas_eur": None, "totaal_eur": None, "fout": str(err)}

    def _gas_m3_vandaag_meter(self, vandaag: date) -> float | None:
        """m3 sinds middernacht uit de gasmeterstand (na de overstap)."""
        stand = self._read_sensor_float(self.config.get(CONF_GAS_METER_TOTAL_SENSOR))
        if stand is None:
            return None
        start = self._gasmeter_dagstart
        if start is None or start[0] != vandaag:
            # na een herstart midden op de dag is het begin onbekend: vanaf nu
            self._gasmeter_dagstart = start = (vandaag, stand)
        return max(0.0, stand - start[1])

    def _jaarafrekening_instellingen(self) -> ja.Instellingen:
        c = self.config
        prijs = None
        bron = c.get(CONF_GAS_NIEUW_PRIJS_ENTITY)
        if bron:
            prijs = self._read_sensor_float(bron)
        termijn_gas = _getal(c.get(CONF_GAS_NIEUW_TERMIJN_EUR), None)
        return ja.Instellingen(
            termijn_eur=_getal(c.get(CONF_JAAR_TERMIJN_EUR), DEFAULT_JAAR_TERMIJN_EUR),
            afschrijfdag=int(_getal(c.get(CONF_JAAR_AFSCHRIJFDAG), DEFAULT_JAAR_AFSCHRIJFDAG)),
            vastrecht_stroom_mnd=_getal(c.get(CONF_JAAR_VASTRECHT_STROOM_MND), DEFAULT_JAAR_VASTRECHT_STROOM_MND),
            vastrecht_gas_mnd=_getal(c.get(CONF_JAAR_VASTRECHT_GAS_MND), DEFAULT_JAAR_VASTRECHT_GAS_MND),
            netbeheer_stroom_jaar=_getal(c.get(CONF_JAAR_NETBEHEER_STROOM_JAAR), DEFAULT_JAAR_NETBEHEER_STROOM_JAAR),
            netbeheer_gas_jaar=_getal(c.get(CONF_JAAR_NETBEHEER_GAS_JAAR), DEFAULT_JAAR_NETBEHEER_GAS_JAAR),
            vermindering_eb_jaar=_getal(c.get(CONF_JAAR_VERMINDERING_EB_JAAR), DEFAULT_JAAR_VERMINDERING_EB_JAAR),
            saldering_eind=_datum(c.get(CONF_SALDEREN_END_DATE) or DEFAULT_SALDEREN_END_DATE),
            gas_overstap=_datum(c.get(CONF_GAS_OVERSTAP_DATUM)),
            gas_nieuw_prijs_m3=prijs if prijs and prijs > 0 else None,
            gas_nieuw_vastrecht_mnd=_getal(c.get(CONF_GAS_NIEUW_VASTRECHT_MND), DEFAULT_GAS_NIEUW_VASTRECHT_MND),
            gas_nieuw_korting_jaar=_getal(c.get(CONF_GAS_NIEUW_KORTING_JAAR), DEFAULT_GAS_NIEUW_KORTING_JAAR),
            gas_nieuw_termijn_eur=termijn_gas,
        )

    def _jaarafrekening_kwartier(self, now: datetime) -> None:
        """Haak op de kwartiergrens: hooguit eens per uur verversen, op de achtergrond."""
        if self._jaarafrekening_bezig:
            return
        laatst = self._jaarafrekening_ververst
        if laatst is not None and (now - laatst).total_seconds() < JAARAFREKENING_VERVERS_S:
            return
        start = _datum(self.config.get(CONF_CONTRACT_START_DATE))
        if start is None:
            self._jaarafrekening_status = "geen startdatum contract ingesteld"
            return
        hass = getattr(self, "hass", None)
        maker = getattr(hass, "async_create_background_task", None)
        if maker is None:
            return
        self._jaarafrekening_bezig = True
        self._jaarafrekening_ververst = now
        maker(self._async_jaarafrekening_ververs(start, now), "ems_jaarafrekening")

    async def _async_jaarafrekening_ververs(self, start: date, now: datetime) -> None:
        try:
            ids = {veld: self.config.get(sleutel) for veld, sleutel in BRONNEN.items() if self.config.get(sleutel)}
            vandaag = dt_util.as_local(now).date()
            begin, _eind = ja.contractjaar(start, vandaag)
            van = dt_util.start_of_local_day(datetime.combine(begin - timedelta(days=366), datetime.min.time()))
            rijen = await self._async_jaarafrekening_statistiek(van, set(ids.values()))
            dagen = dagen_uit_statistiek(rijen, ids)
            self._jaarafrekening = ja.bereken(dagen, start, vandaag, self._jaarafrekening_instellingen())
            self._jaarafrekening_status = "ok" if ids.get("afname_eur") else "geen bron voor de stroomkosten"
            self.internal_failures.pop("jaarafrekening", None)
        except Exception as fout:  # noqa: BLE001 - meten mag de integratie nooit raken
            _LOGGER.debug("Jaarafrekening niet te berekenen", exc_info=True)
            self.internal_failures["jaarafrekening"] = f"{type(fout).__name__}: {fout}"
            self._jaarafrekening_status = "fout bij berekenen"
        finally:
            self._jaarafrekening_bezig = False

    async def _async_jaarafrekening_statistiek(self, van: datetime, ids: set) -> dict:
        if not ids:
            return {}
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period

        return await get_instance(self.hass).async_add_executor_job(
            statistics_during_period, self.hass, van, None, ids, "day", None, {"change"}
        )
