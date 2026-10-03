"""Meetlaag (v5.28): de koppeling tussen productie en de meetlog.

Leest de coördinator, schrijft alleen in zichzelf en in de meetlog. Draait
als staartstap NA het besluit en het sturen van de Zendure, en elke fout
blijft hier: hij wordt geteld in `meetlog.fouten`, nooit doorgegeven.

Per ronde (event loop, licht):
- snapshot alleen als de invoer verandert (vingerafdruk), write-once;
- evaluatierecord: besluit, stand, actie, spiegel, schaduw, reserve, oorzaak.

Per nieuw snapshot (executor, zwaar): het economische schaduwoptimum voor
vier slijtagevarianten, en de tekortverdeling voor de risicoreserve.

Per kwartiergrens (eigen timer): kwartierenergie uit de tellers.
Per nieuwe dag (executor): het dagrapport.
"""
from __future__ import annotations

import hashlib
import logging
import statistics
import time
from datetime import datetime, timedelta

from . import kwartierenergie, meetlog, schaduw, tarief

_LOGGER = logging.getLogger(__name__)

PRICE_SCALE = 10_000_000
BEWAAR_INTERVAL_S = 300
OPSLAG_DAGEN_TERUG = 31


class Meetlaag:
    def __init__(self, coordinator, opslag_factory=None) -> None:
        self.c = coordinator
        self.log = meetlog.MeetLog()
        self._opslag_factory = opslag_factory
        self._vingerafdruk = None
        self._snapshot_id = None
        self._snapshot_tijd = None
        self._kwartieren: list[dict] = []
        self._schaduw: dict = {}
        self._vorige_actie = None
        self._vorige_monotoon = time.monotonic()
        self._vorig_kwartier = None
        self._vorige_laad_id = None
        self._vorige_piek_id = None
        self._vorige_grens = None
        self._vorige_standen = None
        self._accu_in_monsters: list[float] = []
        self._laatste_bewaring = float("-inf")   # eerste keer meteen, ongeacht de uptime
        self._geladen = False
        self._laden_klaar = False
        self._dag = None
        self.laatste_evaluatie: dict | None = None
        self.laatste_kwartier: dict | None = None
        self.laatste_dagrapport: dict | None = None
        self.duur_ms: list[float] = []
        self.invoer = None
        self._risico_cache: dict = {}

    # =====================================================================
    # ronde
    # =====================================================================

    def ronde(self, now: datetime, entries) -> None:
        """Afgeschermd: een fout blijft in de meetlaag."""
        begin = time.perf_counter()
        try:
            self._ronde(now, entries or [])
        except Exception as err:  # noqa: BLE001 - meetcode mag productie nooit raken
            self.log.fouten += 1
            self.log.laatste_fout = f"{type(err).__name__}: {err}"
            _LOGGER.debug("Meetlaag: %s", err, exc_info=True)
        finally:
            self.duur_ms = (self.duur_ms + [round((time.perf_counter() - begin) * 1000, 2)])[-288:]

    def _ronde(self, now: datetime, entries) -> None:
        self._start_laden(now)
        if self._dag is not None and now.date() != self._dag:
            self._nieuwe_dag(self._dag)
        self._dag = now.date()
        self._snapshot_bijwerken(now, entries)
        self._evaluatie(now, entries)
        self._bewaar_af_en_toe()

    # =====================================================================
    # snapshot
    # =====================================================================

    def _productie_slijtage_ct(self) -> float | None:
        return (self.c.get_wear_cost_overview() or {}).get("slijtage_ct_per_kwh")

    def _vingerafdruk_van(self, now: datetime, entries) -> str:
        pv = self.c._get_pv_forecast_entries() or []
        onderdelen = (
            tuple((b.isoformat(), round(p)) for b, _e, p in entries),
            tuple((b.isoformat(), round(k, 4)) for b, _e, k in pv),
            now.date().isoformat(),
            hashlib.sha1(repr(sorted((getattr(self.c, "hourly_consumption_profile", None) or {}).items())).encode()).hexdigest(),
            round(self.c.learned_battery_efficiency_percent or 0, 1),
            self._productie_slijtage_ct(),
            self._config_hash(),
            self._versie(),
        )
        return hashlib.sha1(repr(onderdelen).encode()).hexdigest()

    def _config_hash(self) -> str:
        return hashlib.sha1(repr(sorted((self.c.config or {}).items())).encode()).hexdigest()[:10]

    def _versie(self) -> str | None:
        try:
            return (self.c.get_installation_facts() or {}).get("versie")
        except Exception:  # noqa: BLE001
            return None

    def _snapshot_bijwerken(self, now: datetime, entries) -> None:
        vinger = self._vingerafdruk_van(now, entries)
        if vinger == self._vingerafdruk:
            return
        self._vingerafdruk = vinger
        inhoud, kwartieren = self._bouw_snapshot(now, entries)
        sid = self.log.leg_snapshot_vast(inhoud, now)
        self._snapshot_id, self._snapshot_tijd, self._kwartieren = sid, now, kwartieren
        if sid not in self._schaduw:
            self._start_schaduw(sid, kwartieren, inhoud)

    def _bouw_snapshot(self, now: datetime, entries) -> tuple[dict, list[dict]]:
        c = self.c
        band = {}
        try:
            band = c._pv_band_per_interval() or {}
        except Exception:  # noqa: BLE001
            band = {}
        pv_reeks = c._get_pv_forecast_entries() or []
        profiel = getattr(c, "hourly_consumption_profile", None) or {}
        kwartieren = []
        for begin, eind, p in entries:
            prijs = p / PRICE_SCALE
            waarde = tarief.waarde(begin, prijs, saldeerruimte_kwh=None)
            verbruik = c._estimate_consumption_kwh_for_period(begin, eind)
            p10, p90 = _profielband(profiel, begin.hour, verbruik)
            zon = c._estimate_pv_kwh_for_period(begin, eind)
            laag, hoog = _zonband(band, pv_reeks, begin, eind)
            kwartieren.append({
                "begin": begin.isoformat(),
                "import": waarde["import_eur"], "export": waarde["export_eur"],
                "verbruik": round(verbruik, 4) if verbruik is not None else None,
                "verbruik_p10": p10, "verbruik_p90": p90,
                "zon": round(zon, 4) if zon is not None else None,
                "zon_laag": laag, "zon_hoog": hoog,
            })
        capaciteit, min_soc = self._capaciteit()
        kwaliteit = {
            "prijzen": "ok" if kwartieren else "unknown",
            "pv_band": "ok" if band else "unknown",
            "verbruik_band": "ok" if any(k["verbruik_p10"] is not None for k in kwartieren) else "unknown",
            "saldeerruimte": "unknown",
            "exportwaarde": "onzeker",
        }
        inhoud = {
            "kwartieren": _kolommen(kwartieren),
            "capacity_kwh": capaciteit,
            "min_soc": min_soc,
            "max_charge_kw": abs(float((c.config or {}).get("manual_charge_power") or 0)) / 1000 or None,
            "max_discharge_kw": abs(float((c.config or {}).get("manual_discharge_power") or 0)) / 1000 or None,
            "learned_efficiency": c.learned_battery_efficiency_percent,
            "saldering_remaining_kwh": None,
            "production_wear_cost_ct": self._productie_slijtage_ct(),
            "tariff_model_version": tarief.TARIEF_MODEL_VERSIE,
            "config_hash": self._config_hash(),
            "ems_version": self._versie(),
            "quality": kwaliteit,
        }
        inhoud["forecast_hash"] = meetlog.snapshot_id({"k": kwartieren})
        return inhoud, kwartieren

    def _capaciteit(self) -> tuple[float | None, float | None]:
        from .const import CONF_BATTERY_TOTAL_CAPACITY_SENSOR

        try:
            capaciteit = self.c._read_sensor_float(self.c.config.get(CONF_BATTERY_TOTAL_CAPACITY_SENSOR))
        except Exception:  # noqa: BLE001
            capaciteit = None
        try:
            min_soc = self.c.effective_min_soc_percent()
        except Exception:  # noqa: BLE001
            min_soc = None
        return capaciteit, min_soc

    # =====================================================================
    # schaduw (executor)
    # =====================================================================

    def _start_schaduw(self, sid: str, kwartieren: list[dict], inhoud: dict) -> None:
        capaciteit, min_soc = inhoud.get("capacity_kwh"), inhoud.get("min_soc")
        rendement = inhoud.get("learned_efficiency")
        if not capaciteit or min_soc is None or not rendement or not kwartieren:
            self._schaduw[sid] = {"beschikbaar": False, "reden": "capaciteit, rendement of prijzen onbekend"}
            return
        if any(k["import"] is None or k["verbruik"] is None or k["zon"] is None for k in kwartieren):
            self._schaduw[sid] = {"beschikbaar": False, "reden": "verwachting onvolledig"}
            return
        parameters = {
            "emax_kwh": capaciteit * (100 - min_soc) / 100,
            "laad_kwh": (inhoud.get("max_charge_kw") or 2.0) / 4,
            "ontlaad_kwh": (inhoud.get("max_discharge_kw") or 1.6) / 4,
            "rendement_procent": rendement,
        }
        self._schaduw[sid] = {"beschikbaar": False, "reden": "wordt berekend"}

        def rekenen():
            uit = {"beschikbaar": True, "parameters": parameters, "varianten": {}}
            for ct in schaduw.SLIJTAGEVARIANTEN_CT:
                uit["varianten"][ct] = schaduw.optimaliseer(kwartieren, slijtage_ct=ct, **parameters)
            return uit

        async def klaar():
            try:
                resultaat = await self.c.hass.async_add_executor_job(rekenen)
                self._schaduw = {k: v for k, v in self._schaduw.items() if k == sid or k == self._snapshot_id}
                self._schaduw[sid] = resultaat
            except Exception as err:  # noqa: BLE001
                self.log.fouten += 1
                self.log.laatste_fout = f"schaduw: {type(err).__name__}: {err}"
                self._schaduw[sid] = {"beschikbaar": False, "reden": "berekening mislukt"}

        self.c.hass.async_create_task(klaar())

    # =====================================================================
    # evaluatie
    # =====================================================================

    def _productie_actie(self) -> dict:
        c = self.c
        stand = getattr(c, "last_expected_mode", None)
        vermogen = None
        if stand == "manual":
            ontladen = getattr(c, "last_discharge_power_applied", None)
            laden = getattr(c, "last_charge_power_applied", None)
            vermogen = ontladen if ontladen else laden
        reden = getattr(c, "last_reason", None)
        return {"reden": reden, "stand": stand, "vermogen_w": vermogen,
                "categorie": schaduw.productie_categorie(reden, stand, vermogen)}

    def _verstuurd(self) -> list[dict]:
        nu_mono = time.monotonic()
        verstuurd = [
            {"entiteit": e, "verwacht": o.get("verwacht"), "wat": o.get("wat")}
            for e, o in (getattr(self.c, "_openstaande_opdrachten", None) or {}).items()
            if (o.get("sinds") or 0) > self._vorige_monotoon
        ]
        self._vorige_monotoon = nu_mono
        return verstuurd

    def _vers(self, attr: str, vorige_attr: str):
        """Een productieresultaat alleen als het deze ronde opnieuw is berekend."""
        waarde = getattr(self.c, attr, None)
        vers = waarde is not None and id(waarde) != getattr(self, vorige_attr)
        setattr(self, vorige_attr, id(waarde) if waarde is not None else None)
        return waarde if vers else None

    def _evaluatie(self, now: datetime, entries) -> None:
        c = self.c
        productie = self._productie_actie()
        actie = (productie["stand"], productie["vermogen_w"])
        gewijzigd = self._vorige_actie is not None and actie != self._vorige_actie
        vorige = self._vorige_actie
        self._vorige_actie = actie
        verstuurd = self._verstuurd()
        beschikbaar = c.beschikbare_energie_kwh()
        reserve = (getattr(c, "last_reserve_margin_breakdown", None) or {}).get("reserve_kwh_after_margin")
        laad = self._vers("last_laadbesluit", "_vorige_laad_id")
        piek = self._vers("last_piekverkoop", "_vorige_piek_id")
        reeks = [(b, p / PRICE_SCALE) for b, _e, p in entries]
        blok = getattr(c, "last_cheap_block_start", None)
        blok_eind = getattr(c, "last_cheap_block_end", None)
        blokprijzen = [p for b, p in reeks if blok and blok_eind and blok <= b < blok_eind]
        prijs_nu = next((p for b, p in reeks if b <= now < b + timedelta(minutes=15)), None)
        invoer = {
            "productie_categorie": productie["categorie"], "laadbesluit": laad, "piek": piek,
            "moment": now, "reeks": reeks, "blok": blok, "blokprijzen": blokprijzen,
            "rendement_procent": c.learned_battery_efficiency_percent,
            "onder_reserve": beschikbaar is not None and reserve is not None and beschikbaar <= reserve,
            "duur_kwartier": (getattr(c, "last_reason", "") or "").startswith("expensive_quarter"),
        }
        prod_ct = self._productie_slijtage_ct()
        spiegel = schaduw.spiegel(invoer, prod_ct) if prod_ct is not None else None
        spiegel_varianten = {ct: schaduw.spiegel(invoer, ct)["actie"] for ct in schaduw.SLIJTAGEVARIANTEN_CT}
        economisch = self._economisch(now, beschikbaar, prod_ct)
        risico = self._risico(now, prijs_nu)
        snapshot = self.log.snapshot(self._snapshot_id) if self._snapshot_id else None
        onvolledig = bool(snapshot) and any(
            v == "unknown" for k, v in snapshot["inhoud"]["quality"].items() if k in ("prijzen", "pv_band")
        )
        record = {
            "evaluation_timestamp": now.isoformat(),
            "snapshot_id": self._snapshot_id,
            "production_action": productie,
            "recommended_action": {"reden": productie["reden"], "stand": productie["stand"], "vermogen_w": productie["vermogen_w"]},
            "current_action": self._zendure_stand(),
            "action_changed": gewijzigd,
            "previous_action": {"stand": vorige[0], "vermogen_w": vorige[1]} if gewijzigd and vorige else None,
            "new_action": {"stand": actie[0], "vermogen_w": actie[1]} if gewijzigd else None,
            "command_sent": bool(verstuurd),
            "commands": verstuurd,
            "reason": productie["reden"],
            "mirror_action": spiegel["actie"] if spiegel else None,
            "mirror_matches_production": (spiegel["actie"] == productie["categorie"]) if spiegel else None,
            "mirror_doorgegeven": spiegel["doorgegeven"] if spiegel else None,
            "mirror_per_slijtage": spiegel_varianten,
        }
        record.update(economisch)
        record.update({
            "production_reserve_kwh": reserve,
            "shadow_risk_reserve_kwh": risico.get("kwh"),
            "reserve_difference_kwh": round(reserve - risico["kwh"], 2) if reserve is not None and risico.get("kwh") is not None else None,
            "reserve_confidence": risico.get("vertrouwen"),
            "measurements": self._metingen(beschikbaar),
        })
        record["production_vs_shadow"] = schaduw.oorzaak(
            productie["categorie"], record.get("economic_shadow_action"),
            reden=productie["reden"],
            onder_bodem=self._onder_bodem(beschikbaar),
            spiegel_lage_slijtage=spiegel_varianten.get(4.22),
            snapshot_onvolledig=onvolledig,
            vertrouwen=risico.get("vertrouwen"),
        )
        kwartier = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
        volledig = gewijzigd or kwartier != self._vorig_kwartier
        self._vorig_kwartier = kwartier
        record["record"] = "volledig" if volledig else "compact"
        self.laatste_evaluatie = record
        accu_w = record["measurements"].get("accu_w")
        if accu_w is not None:
            self._accu_in_monsters.append(max(0.0, -accu_w))
        self.log.voeg_toe("evaluatie", now, record if volledig else _compact(record))

    def _economisch(self, now: datetime, beschikbaar, prod_ct) -> dict:
        res = self._schaduw.get(self._snapshot_id) or {}
        if not res.get("beschikbaar") or beschikbaar is None:
            return {"economic_shadow_action": None, "economic_status": res.get("reden") or "geen schaduw"}
        q = self._kwartier_index(now)
        if q is None:
            return {"economic_shadow_action": None, "economic_status": "kwartier buiten het snapshot"}
        per_variant = {}
        for ct, opt in res["varianten"].items():
            waarden = schaduw.alternatieven(opt, self._kwartieren, q, beschikbaar)
            beste, tweede = schaduw.beste_twee(waarden)
            per_variant[ct] = {"actie": beste, "tweede": tweede, "waarden_eur": waarden}
        hoofd = per_variant.get(prod_ct if prod_ct in per_variant else 11.28) or {}
        waarden = hoofd.get("waarden_eur") or {}
        productie_cat = self._productie_actie()["categorie"]
        verschil = (
            round(waarden[hoofd["actie"]] - waarden[productie_cat], 4)
            if hoofd.get("actie") and productie_cat in waarden else None
        )
        return {
            "economic_shadow_action": hoofd.get("actie"),
            "second_action": hoofd.get("tweede"),
            "alternatives_eur": waarden,
            "economic_shadow_difference_eur": verschil,
            "economic_per_slijtage": {ct: v["actie"] for ct, v in per_variant.items()},
            "economic_status": "ok",
        }

    def _risico(self, now: datetime, prijs_nu) -> dict:
        """De tekortverdeling vanaf het huidige kwartier tot het blok, een keer
        per kwartier berekend in de executor - en het volgende kwartier alvast,
        zodat hij klaarstaat als het volledige record van dat kwartier wordt
        geschreven."""
        q = self._kwartier_index(now)
        if q is None or not self._kwartieren:
            return {"kwh": None}
        self._risico_cache = {k: w for k, w in self._risico_cache.items() if k[0] == self._snapshot_id and k[1] >= q}
        for index in (q, q + 1):
            if index < len(self._kwartieren) and (self._snapshot_id, index) not in self._risico_cache:
                self._plan_risico(self._snapshot_id, index)
        verdeling = self._risico_cache.get((self._snapshot_id, q))
        if not isinstance(verdeling, dict):
            return {"kwh": None, "reden": "wordt berekend"}
        waarde_nu = tarief.waarde(now, prijs_nu, saldeerruimte_kwh=None)["export_eur"]
        return schaduw.risicoreserve(verdeling, waarde_nu, self.c.learned_battery_efficiency_percent or 83.8)

    def _plan_risico(self, sid: str, index: int) -> None:
        sleutel = (sid, index)
        self._risico_cache[sleutel] = "bezig"
        kwartieren = self._kwartieren[index:]
        blok = getattr(self.c, "last_cheap_block_start", None)
        tot = len(kwartieren)
        if blok is not None:
            tot = next((i for i, k in enumerate(kwartieren) if datetime.fromisoformat(k["begin"]) >= blok), tot)
        zaad = f"{sid}-{index}"

        def rekenen():
            return schaduw.tekortverdeling(kwartieren, tot, zaad=zaad)

        async def klaar():
            try:
                self._risico_cache[sleutel] = await self.c.hass.async_add_executor_job(rekenen)
            except Exception as err:  # noqa: BLE001
                self.log.fouten += 1
                self.log.laatste_fout = f"risico: {type(err).__name__}: {err}"
                self._risico_cache[sleutel] = {"beschikbaar": False, "reden": "berekening mislukt"}

        self.c.hass.async_create_task(klaar())

    def _kwartier_index(self, now: datetime):
        return next((i for i, k in enumerate(self._kwartieren)
                     if datetime.fromisoformat(k["begin"]) <= now < datetime.fromisoformat(k["begin"]) + timedelta(minutes=15)), None)

    def _metingen(self, beschikbaar) -> dict:
        """Momentaan, alleen als context - met dezelfde zuivere lezers als
        het dagverloop."""
        from .const import CONF_CONSUMPTION_POWER_SENSOR

        c = self.c
        return {
            "beschikbaar_kwh": beschikbaar,
            "net_w": c._read_sensor_float(c.config.get(CONF_CONSUMPTION_POWER_SENSOR)),
            "accu_w": c._read_corrected_battery_power(),
            "pv_w": c._lees_pv_vermogen_w(),
        }

    def _onder_bodem(self, beschikbaar) -> bool:
        capaciteit, _ = self._capaciteit()
        if beschikbaar is None or not capaciteit:
            return False
        return beschikbaar <= capaciteit * 0.15

    def _zendure_stand(self) -> str | None:
        from .const import CONF_OPERATION_SELECT

        toestand = self.c.hass.states.get(self.c.config.get(CONF_OPERATION_SELECT) or "")
        return toestand.state if toestand else None

    # =====================================================================
    # kwartiergrens (eigen timer)
    # =====================================================================

    def kwartiergrens(self, grens: datetime) -> None:
        try:
            self._kwartiergrens(grens)
        except Exception as err:  # noqa: BLE001
            self.log.fouten += 1
            self.log.laatste_fout = f"kwartier: {type(err).__name__}: {err}"

    def _tellers(self) -> dict:
        from .const import (
            CONF_BATTERY_CHARGE_ENERGY_SENSOR,
            CONF_BATTERY_DISCHARGE_ENERGY_SENSOR,
            CONF_GRID_EXPORT_ENERGY_SENSOR,
            CONF_GRID_IMPORT_ENERGY_SENSOR,
            CONF_PV_ENERGY_SENSOR,
        )

        cfg = self.c.config or {}
        uit = {
            "grid_import": cfg.get(CONF_GRID_IMPORT_ENERGY_SENSOR),
            "grid_export": cfg.get(CONF_GRID_EXPORT_ENERGY_SENSOR),
            "pv": cfg.get(CONF_PV_ENERGY_SENSOR),
            "battery_out": cfg.get(CONF_BATTERY_DISCHARGE_ENERGY_SENSOR),
            "battery_in": cfg.get(CONF_BATTERY_CHARGE_ENERGY_SENSOR),
        }
        if not uit["battery_in"] and uit["battery_out"] and "discharge" in uit["battery_out"]:
            kandidaat = uit["battery_out"].replace("discharge", "charge")
            toestand = self.c.hass.states.get(kandidaat)
            attr = getattr(toestand, "attributes", {}) or {}
            if toestand and attr.get("unit_of_measurement") == "kWh" and attr.get("state_class") == "total_increasing":
                uit["battery_in"] = kandidaat
        return uit

    def _kwartiergrens(self, grens: datetime) -> None:
        from .const import CONF_BATTERY_CHARGE_ENERGY_SENSOR

        grens = grens.replace(second=0, microsecond=0)
        tellers = self._tellers()
        standen = {}
        for naam, entiteit in tellers.items():
            if not entiteit:
                standen[naam] = None
                continue
            toestand = self.c.hass.states.get(entiteit)
            # last_reported verandert bij elke melding, ook als de waarde
            # gelijk blijft; last_updated alleen bij een andere waarde - een
            # stilstaande teller (teruglevering 's nachts) is wel exact.
            gemeld = (getattr(toestand, "last_reported", None) or getattr(toestand, "last_updated", None)) if toestand else None
            eenheid = (getattr(toestand, "attributes", None) or {}).get("unit_of_measurement") if toestand else None
            standen[naam] = kwartierenergie.stand(toestand.state if toestand else None, gemeld, grens, eenheid)
        vorige, vorige_grens = self._vorige_standen, self._vorige_grens
        self._vorige_standen, self._vorige_grens = standen, grens
        geschat = (sum(self._accu_in_monsters) / len(self._accu_in_monsters) / 4000) if self._accu_in_monsters else None
        self._accu_in_monsters = []
        if vorige is None or vorige_grens != grens - timedelta(minutes=15):
            return
        entries = []
        try:
            entries = self.c._get_forecast_entries() or []
        except Exception:  # noqa: BLE001
            entries = []
        prijs = next((p / PRICE_SCALE for b, _e, p in entries if b == vorige_grens), None)
        record = kwartierenergie.kwartier(
            vorige_grens, vorige, standen, prijs,
            accu_in_geschat_kwh=geschat if not tellers.get("battery_in") else None,
        )
        record["bron_accu_in"] = (
            "teller" if tellers.get("battery_in") and tellers["battery_in"] == (self.c.config or {}).get(CONF_BATTERY_CHARGE_ENERGY_SENSOR)
            else ("teller (naamgenoot van de ontlaadteller)" if tellers.get("battery_in") else "geschat uit accuvermogen")
        )
        self.laatste_kwartier = record
        opslag = kwartierenergie.compact(record)
        opslag["bron"] = {"teller": "t", "teller (naamgenoot van de ontlaadteller)": "n"}.get(record["bron_accu_in"], "g")
        self.log.voeg_toe("kwartier", vorige_grens, opslag)

    # =====================================================================
    # dag, opslag
    # =====================================================================

    def _nieuwe_dag(self, dag) -> None:
        evaluaties = self.log.regels("evaluatie", dag)
        kwartieren = [kwartierenergie.uitpakken(k) for k in self.log.regels("kwartier", dag)]
        snapshot = self.log.snapshot(self._snapshot_id) if self._snapshot_id else None
        capaciteit = (snapshot or {}).get("inhoud", {}).get("capacity_kwh") or 8.64
        min_soc = (snapshot or {}).get("inhoud", {}).get("min_soc") or 10.0
        rendement = self.c.learned_battery_efficiency_percent or 83.8

        inhoud = (snapshot or {}).get("inhoud", {})
        laad = (inhoud.get("max_charge_kw") or 2.0) / 4
        ontlaad = (inhoud.get("max_discharge_kw") or 1.6) / 4

        def rekenen():
            return schaduw_dagrapport(evaluaties, kwartieren, capaciteit * (100 - min_soc) / 100, rendement,
                                      laad_kwh=laad, ontlaad_kwh=ontlaad)

        async def klaar():
            try:
                rapport = await self.c.hass.async_add_executor_job(rekenen)
                rapport["dag"] = dag.isoformat()
                self.laatste_dagrapport = rapport
                self.log.voeg_toe("dagrapport", datetime.combine(dag, datetime.min.time()), rapport)
            except Exception as err:  # noqa: BLE001
                self.log.fouten += 1
                self.log.laatste_fout = f"dagrapport: {type(err).__name__}: {err}"

        self.c.hass.async_create_task(klaar())
        for soort, dagstr in self.log.opruimen(dag + timedelta(days=1)):
            self._verwijder(soort, dagstr)

    def _start_laden(self, now: datetime) -> None:
        """Na een herstart de bewaarde dagen terugladen.

        v5.28.2: zolang dat loopt wordt er niets weggeschreven of verwijderd.
        Het eerste wegschrijven na een herstart kon het terugladen inhalen en
        het bestand van vandaag overschrijven met alleen de paar nieuwe
        records - daarmee was de geschiedenis van die dag weg. En de datum
        komt van de ronde, niet van de systeemklok (die in een container op
        UTC kan staan).
        """
        if self._geladen:
            return
        self._geladen = True
        if self._opslag_factory is None:
            self._laden_klaar = True
            return
        vandaag = now.date()

        async def laden():
            try:
                for terug in range(OPSLAG_DAGEN_TERUG):
                    dag = (vandaag - timedelta(days=terug)).isoformat()
                    for soort in meetlog.SOORTEN:
                        try:
                            inhoud = await self._opslag(meetlog.MeetLog.opslagsleutel(soort, dag)).async_load()
                            self.log.laad_dag(soort, dag, inhoud)
                        except Exception:  # noqa: BLE001
                            continue
            finally:
                self._laden_klaar = True

        self.c.hass.async_create_task(laden())

    def _bewaar_af_en_toe(self) -> None:
        if self._opslag_factory is None or not self._laden_klaar:
            return
        if time.monotonic() - self._laatste_bewaring < BEWAAR_INTERVAL_S:
            return
        self._laatste_bewaring = time.monotonic()
        te_bewaren = self.log.te_bewaren()

        async def bewaren():
            for (soort, dag), inhoud in te_bewaren.items():
                try:
                    await self._opslag(meetlog.MeetLog.opslagsleutel(soort, dag)).async_save(inhoud)
                except Exception as err:  # noqa: BLE001
                    self.log.fouten += 1
                    self.log.laatste_fout = f"opslag: {err}"

        self.c.hass.async_create_task(bewaren())

    def _verwijder(self, soort: str, dag: str) -> None:
        if self._opslag_factory is None or not self._laden_klaar:
            return

        async def weg():
            try:
                await self._opslag(meetlog.MeetLog.opslagsleutel(soort, dag)).async_remove()
            except Exception:  # noqa: BLE001
                pass

        self.c.hass.async_create_task(weg())

    def status_tekst(self) -> str:
        """Een regel voor de diagnosesensor: draait hij, klopt de spiegel,
        hoeveel komt uit tellers."""
        vandaag = self._dag
        evaluaties = self.log.regels("evaluatie", vandaag) if vandaag else []
        kwartieren = [kwartierenergie.uitpakken(k) for k in self.log.regels("kwartier", vandaag)] if vandaag else []
        kwartieren = [k for k in kwartieren if "reden" not in k]   # v5.28-formaat telt niet mee
        met_spiegel = [e for e in evaluaties if e.get("mirror_matches_production") is not None]
        spiegel = (
            f"spiegel {round(100 * sum(1 for e in met_spiegel if e['mirror_matches_production']) / len(met_spiegel))}%"
            if met_spiegel else "spiegel -"
        )
        dekking = (
            f"dekking {round(statistics.mean(k.get('coverage_percent') or 0 for k in kwartieren))}%"
            if kwartieren else "dekking -"
        )
        return f"{'ok' if not self.log.fouten else f'fouten {self.log.fouten}'} · {len(evaluaties)} evaluaties · {spiegel} · {dekking}"

    def _opslag(self, sleutel: str):
        """De opslag voor een dagbestand. Via een lokale naam: de
        structuurscan leest een opgeslagen functie anders als methode."""
        fabriek = self._opslag_factory
        return fabriek(sleutel)

    def samenvatting(self) -> dict:
        evaluaties = [d for d in self.duur_ms]
        return {
            "opslag": self.log.samenvatting(),
            "snapshot_id": self._snapshot_id,
            "schaduw": (self._schaduw.get(self._snapshot_id) or {}).get("reden")
            if not (self._schaduw.get(self._snapshot_id) or {}).get("beschikbaar") else "ok",
            "event_loop_ms": {
                "laatste": evaluaties[-1] if evaluaties else None,
                "mediaan": round(statistics.median(evaluaties), 2) if evaluaties else None,
                "max": max(evaluaties) if evaluaties else None,
            },
            "laatste_evaluatie": self.laatste_evaluatie,
            "laatste_kwartier": self.laatste_kwartier,
            "laatste_dagrapport": self.laatste_dagrapport,
        }


# ------------------------------------------------------------------------

def _compact(record: dict) -> dict:
    return {
        "evaluation_timestamp": record["evaluation_timestamp"],
        "snapshot_id": record["snapshot_id"],
        "recommended_action": record["recommended_action"],
        "current_action": record["current_action"],
        "action_changed": record["action_changed"],
        "command_sent": record["command_sent"],
        "mirror_matches_production": record.get("mirror_matches_production"),
        "economic_shadow_action": record.get("economic_shadow_action"),
        "record": "compact",
    }


def _kolommen(kwartieren: list[dict]) -> dict:
    """Snapshot-opslag per kolom: de eerste begintijd, minuten vanaf daar, en
    per veld een lijst - een derde van de grootte van een lijst woordenboeken."""
    if not kwartieren:
        return {"begin": None, "minuten": [], "kolommen": {}}
    eerste = datetime.fromisoformat(kwartieren[0]["begin"])
    velden = [k for k in kwartieren[0] if k != "begin"]
    return {
        "begin": kwartieren[0]["begin"],
        "minuten": [int((datetime.fromisoformat(k["begin"]) - eerste).total_seconds() // 60) for k in kwartieren],
        "kolommen": {veld: [k[veld] for k in kwartieren] for veld in velden},
    }


def _profielband(profiel: dict, uur: int, verbruik) -> tuple:
    monsters = profiel.get(uur) or profiel.get(str(uur)) or []
    try:
        getallen = sorted(float(m) for m in monsters if m is not None)
    except (TypeError, ValueError):
        getallen = []
    if len(getallen) < 3 or verbruik is None:
        return None, None
    p10 = getallen[int(0.1 * (len(getallen) - 1))] / 4
    p90 = getallen[int(round(0.9 * (len(getallen) - 1)))] / 4
    return round(min(p10, verbruik), 4), round(max(p90, verbruik), 4)


def _zonband(band: dict, pv_reeks: list, begin: datetime, eind: datetime) -> tuple:
    if not band:
        return None, None
    laag = hoog = 0.0
    for b, e, _k in pv_reeks:
        if e <= begin or b >= eind or b not in band:
            continue
        duur = (e - b).total_seconds()
        if duur <= 0:
            continue
        deel = (min(e, eind) - max(b, begin)).total_seconds() / duur
        lo, hi = band[b]
        laag += lo * deel
        hoog += hi * deel
    return round(laag, 4), round(hoog, 4)


def schaduw_dagrapport(evaluaties: list[dict], kwartieren: list[dict], emax: float, rendement: float,
                       laad_kwh: float = 0.5, ontlaad_kwh: float = 0.4) -> dict:
    """Per slijtagevariant: wat het economische schaduwoptimum met de gemeten
    energie van de dag had opgeleverd, en hoe vaak het afweek van productie.

    Geen oordeel over wat beter is - alleen de getallen.
    """
    eta = (rendement / 100) ** 0.5
    per_kwartier: dict = {}
    for e in evaluaties:
        sleutel = e["evaluation_timestamp"][:16]
        kwartier = sleutel[:14] + f"{int(sleutel[14:16]) // 15 * 15:02d}"
        per_kwartier.setdefault(kwartier, e)
    meting = {k["kwartier"][:16]: k for k in kwartieren}
    kwartieren = [k for k in kwartieren if "reden" not in k]   # v5.28-formaat telt niet mee
    meting = {k["kwartier"][:16]: k for k in kwartieren}
    uit = {"varianten": {}, "kwartieren_gemeten": len(meting),
           "dekking_procent": round(statistics.mean([k.get("coverage_percent") or 0 for k in kwartieren]), 1) if kwartieren else None}
    for ct in schaduw.SLIJTAGEVARIANTEN_CT:
        e_kwh = None
        kas = doorzet = boven_90 = 0.0
        socs: list[float] = []
        afwijkend = 0
        for kwartier, ev in sorted(per_kwartier.items()):
            m = meting.get(kwartier)
            actie = (ev.get("economic_per_slijtage") or {}).get(ct) or (ev.get("economic_per_slijtage") or {}).get(str(ct))
            if actie and actie != (ev.get("production_action") or {}).get("categorie"):
                afwijkend += 1
            if not m or m.get("house_kwh") is None or m.get("pv_kwh") is None or m.get("prijs_eur") is None or actie is None:
                continue
            if e_kwh is None:
                e_kwh = (ev.get("measurements") or {}).get("beschikbaar_kwh") or 0.0
            tekort = max(0.0, m["house_kwh"] - m["pv_kwh"])
            overschot = max(0.0, m["pv_kwh"] - m["house_kwh"])
            laad, ontlaad = laad_kwh, ontlaad_kwh   # v5.28.3: de ingestelde grenzen
            ac_in = ac_uit = 0.0
            if actie in ("huis_dekken", "bewaren"):
                ac_in = min(overschot, laad, (emax - e_kwh) / eta)
            if actie == "huis_dekken":
                ac_uit = min(tekort, ontlaad, e_kwh * eta)
            elif actie == "verkopen":
                ac_uit = min(ontlaad, e_kwh * eta)
            elif actie == "laden":
                ac_in = min(laad, (emax - e_kwh) / eta)
            e_kwh = e_kwh + ac_in * eta - ac_uit / eta
            net = m["house_kwh"] - m["pv_kwh"] + ac_in - ac_uit
            kas += net * m["prijs_eur"]
            doorzet += ac_uit
            socs.append(e_kwh / emax * 100 if emax else 0.0)
            boven_90 += 0.25 if emax and e_kwh / emax > 0.9 else 0.0
        uit["varianten"][ct] = {
            "kas_eur": round(kas, 3),
            "doorzet_kwh": round(doorzet, 3),
            "equivalente_cycli": round(doorzet / emax, 3) if emax else None,
            "gemiddelde_soc_procent": round(statistics.mean(socs), 1) if socs else None,
            "uren_boven_90": round(boven_90, 2),
            "afwijkende_kwartieren": afwijkend,
        }
    basis = uit["varianten"].get(11.28) or {}
    for ct, v in uit["varianten"].items():
        extra = v["doorzet_kwh"] - (basis.get("doorzet_kwh") or 0)
        v["extra_doorzet_kwh"] = round(extra, 3)
        extra_cycli = extra / emax if emax else 0
        v["opbrengst_per_extra_cyclus_eur"] = (
            round(((basis.get("kas_eur") or 0) - v["kas_eur"]) / extra_cycli, 3) if extra_cycli > 0.01 else None
        )
    return uit
