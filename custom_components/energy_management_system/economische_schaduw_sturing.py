"""Economische schaduw (v5.187.0): de lijm tussen de coordinator en `economische_schaduw.py`.

Alleen lezen en in een eigen Store schrijven. Geen dienstaanroep, geen select
of number, en geen productiestaat (`_waardeplan_cache`, `last_waardeplan`,
`_kwartier_uitvoering`, ...) wordt aangeraakt. Elke stap loopt via
`_bewaak_stap("economische_schaduw", ...)`: een fout komt in
internal_failures en raakt de ronde nooit. Schakelaar uit = dit pad wordt
helemaal overgeslagen.

Stroom (plan sectie 2):
- na het EERSTE productieplan van een kwartier (`_async_bereken_waardeplan`):
  diepe kopie van de invoer, de varianten plannen in de executor (achtergrond-
  taak, de sturing wacht er niet op);
- op de kwartiergrens (`_meetlaag_kwartier`): het vorige kwartier afrekenen
  met de meting van de meetlaag, de virtuele accu's bijwerken, om 00:00 de
  dag sluiten.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.util import dt as dt_util

from . import economische_schaduw as es
from . import waardeplan as waardeplan_mod

_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")

SCHADUW_SLEUTEL = "economische_schaduw"
SCHADUW_STORE = "energy_management_system.economische_schaduw"
#: Zo lang wacht een nieuw schaduwplan op de afrekening van het vorige kwartier.
SCHADUW_WACHT_S = 120
SCHADUW_BEWAAR_S = 60


class EconomischeSchaduwMixin:
    """v5.187.0: de economische schaduw (C2/C0 naast productie). Toestand als
    klassestandaard: de `__init__` van de coordinator zit aan zijn grens."""

    economische_schaduw_aan: bool = True
    _schaduw_boek: es.Schaduwboek | None = None
    _schaduw_store = None
    _schaduw_laden_bezig: bool = False
    _schaduw_gepland: datetime | None = None       # kwartier waarvoor al gepland is
    _schaduw_lopend: dict | None = None            # het plan van het lopende kwartier
    _schaduw_wacht: tuple | None = None            # (lopend, invoer) tot de afrekening
    _schaduw_taak = None
    _schaduw_grens_inhoud: tuple | None = None     # (grens, echte inhoud)
    _schaduw_status: str = "nog niet gestart"

    # --- opslag --------------------------------------------------------------

    def _schaduw_opslag(self):
        if self._schaduw_store is None:
            from homeassistant.helpers.storage import Store

            self._schaduw_store = Store(self.hass, version=1, key=SCHADUW_STORE)
        return self._schaduw_store

    async def async_laad_economische_schaduw(self) -> es.Schaduwboek:
        """Het boek uit de Store (virtuele inhoud en open dag overleven een herstart)."""
        try:
            data = await self._schaduw_opslag().async_load()
        except Exception:  # noqa: BLE001 - een kapotte opslag = opnieuw beginnen
            _LOGGER.debug("Economische schaduw: opslag niet te lezen", exc_info=True)
            data = None
        self._schaduw_boek = es.Schaduwboek(data)
        self._schaduw_laden_bezig = False
        return self._schaduw_boek

    def _schaduw_boek_klaar(self) -> es.Schaduwboek | None:
        """Het boek, of None terwijl het (eenmalig, op de achtergrond) laadt."""
        if self._schaduw_boek is not None:
            return self._schaduw_boek
        if not self._schaduw_laden_bezig:
            self._schaduw_laden_bezig = True
            self._schaduw_taak_starten(self.async_laad_economische_schaduw())
        return None

    def _schaduw_bewaren(self) -> None:
        boek = self._schaduw_boek
        if boek is None:
            return
        self._schaduw_opslag().async_delay_save(boek.naar_opslag, SCHADUW_BEWAAR_S)

    def _schaduw_taak_starten(self, coro):
        hass = getattr(self, "hass", None)
        maker = getattr(hass, "async_create_background_task", None)
        if maker is not None:
            return maker(coro, "ems_economische_schaduw")
        maker = getattr(hass, "async_create_task", None)
        if maker is not None:
            return maker(coro)
        coro.close()
        return None

    # --- plannen na het productieplan ------------------------------------------

    def _economische_schaduw_na_plan(self, now: datetime, voor: dict, res) -> None:
        """Haak na het productieplan; kan niet mislukken en verandert niets aan productie."""
        if not self.economische_schaduw_aan:
            return
        try:
            self._bewaak_stap(SCHADUW_SLEUTEL, lambda: self._schaduw_start(now, voor, res))
        except Exception:  # noqa: BLE001
            pass

    def _schaduw_start(self, now: datetime, voor: dict, res) -> None:
        sleutel = self._kwartier_sleutel(now)
        if self._schaduw_gepland == sleutel:
            return                       # alleen het eerste plan van het kwartier
        boek = self._schaduw_boek_klaar()
        if boek is None:
            return
        self._schaduw_gepland = sleutel
        kwartieren, accu = copy.deepcopy((voor["kwartieren"], voor["accu"]))
        lopend = self._schaduw_lopend_van(now, sleutel, kwartieren, accu, res)
        if lopend["status"] == "gepland":
            boek.zet_waarde(dt_util.as_local(now).date().isoformat(), lopend["eindwaarde"])
        if boek.gestart is None:
            boek.resync(accu.inhoud_kwh, now.isoformat())
        vorige = self._schaduw_lopend
        if vorige is not None and vorige["t"] < sleutel.timestamp():
            if vorige["t"] == (sleutel - timedelta(minutes=15)).timestamp() and \
                    (now - sleutel).total_seconds() < SCHADUW_WACHT_S:
                self._schaduw_wacht = (lopend, kwartieren, accu)   # eerst afrekenen
                return
            self._schaduw_afrekenen_zonder_meting(vorige)
        self._schaduw_plannen_starten(lopend, kwartieren, accu)

    def _schaduw_lopend_van(self, now, sleutel, kwartieren, accu, res) -> dict:
        """Wat het kwartier nodig heeft om straks af te rekenen (alles uit de kopie)."""
        eta_l, eta_o = waardeplan_mod.rendementen(accu)
        k0 = kwartieren[0] if kwartieren else None
        r0 = res.kwartieren[0] if getattr(res, "beschikbaar", False) and res.kwartieren else {}
        return {
            "t": sleutel.timestamp(), "status": "gepland" if r0 and k0 is not None else "geen_plan",
            "pin": getattr(k0, "inkoop_eur", None), "puit": getattr(k0, "teruglever_eur", None),
            "slijt": float(accu.slijtage_eur), "huis_v": getattr(k0, "verbruik_kwh", None),
            "zon_v": getattr(k0, "zon_kwh", None), "uren": getattr(k0, "uren", 0.25),
            "p_actie": r0.get("actie"), "p_reden": r0.get("waarde_inhoud_eur_per_kwh"),
            "p_inh_plan": float(accu.inhoud_kwh),
            "eindwaarde": getattr(res, "eindwaarde_eur_per_kwh", None),
            "accu": {"capaciteit_kwh": float(accu.bruikbaar_kwh), "eta_l": eta_l, "eta_o": eta_o,
                     "ontladen_kw": float(accu.ontladen_kw), "laden_kw": float(accu.laden_kw),
                     "laden_slim_kw": float(accu.laden_slim_kw or accu.laden_kw),
                     "verkoop_kw": float(accu.verkoop_kw or accu.ontladen_kw)},
            "varianten": {}, "midk": None,
        }

    def _schaduw_plannen_starten(self, lopend: dict, kwartieren, accu) -> None:
        self._schaduw_lopend = lopend
        self._schaduw_wacht = None
        if lopend["status"] != "gepland":
            return
        boek = self._schaduw_boek
        varianten = {n: (marge, boek.virtueel.get(n) if boek.virtueel.get(n) is not None else accu.inhoud_kwh)
                     for n, marge in es.VARIANTEN.items()}
        self._schaduw_taak = self._schaduw_taak_starten(self._async_schaduw_plannen(lopend, kwartieren, accu, varianten))

    async def _async_schaduw_plannen(self, lopend: dict, kwartieren, accu, varianten: dict) -> None:
        """De varianten in de executor; daarna (op de loop) de uitkomst vastleggen."""
        try:
            uitvoeren = getattr(self.hass, "async_add_executor_job", None)
            if uitvoeren is None:
                uitkomst = es.plan_varianten(waardeplan_mod.plan, kwartieren, accu, varianten)
            else:
                uitkomst = await uitvoeren(es.plan_varianten, waardeplan_mod.plan, kwartieren, accu, varianten)
        except Exception as fout:  # noqa: BLE001
            uitkomst = fout
        self._bewaak_stap(SCHADUW_SLEUTEL, lambda: self._schaduw_plannen_klaar(lopend, uitkomst))

    def _schaduw_plannen_klaar(self, lopend: dict, uitkomst) -> None:
        if isinstance(uitkomst, Exception):
            lopend["status"] = "geen_plan"
            raise uitkomst
        for naam in es.VARIANTEN:
            lopend["varianten"][naam] = uitkomst.get(naam)
        if any(uitkomst.get(n) is None for n in es.VARIANTEN):
            lopend["status"] = "geen_plan"
        fouten = uitkomst.get("_fouten") or {}
        if fouten:
            raise RuntimeError("; ".join(f"{n}: {f}" for n, f in fouten.items()))
        self._schaduw_status = "loopt"

    # --- middenin het kwartier (alleen loggen) ----------------------------------

    def _schaduw_midkwartier(self, now: datetime, plan: dict, oud: dict, reden) -> None:
        """Een geweigerde of toegestane wissel noteren (v5.187.0, plantoets 7); gedrag gelijk."""
        if not self.economische_schaduw_aan:
            return
        try:
            lopend = self._schaduw_lopend
            if lopend is None or lopend["t"] != self._kwartier_sleutel(now).timestamp():
                return
            sleutel = plan.get("berekend_om")
            if sleutel is not None and lopend.get("_midk_plan") == sleutel:
                return
            lopend["_midk_plan"] = sleutel
            v_eind = self._midkwartier_voordeel_eur(plan, oud)
            v_marg = es.midkwartier_voordeel(plan, oud, (plan.get("nu") or {}).get("waarde_inhoud_eur_per_kwh"))
            lopend["midk"] = es.midk_bij(lopend.get("midk"), not reden, v_eind, v_marg)
        except Exception:  # noqa: BLE001 - loggen mag de keuze nooit raken
            _LOGGER.debug("Economische schaduw: midkwartier niet gelogd", exc_info=True)

    # --- afrekenen op de kwartiergrens -----------------------------------------

    def _economische_schaduw_kwartier(self, grens: datetime, laag) -> None:
        if not self.economische_schaduw_aan:
            return
        try:
            self._bewaak_stap(SCHADUW_SLEUTEL, lambda: self._schaduw_afrekenen(grens, laag))
        except Exception:  # noqa: BLE001
            pass

    def _schaduw_meting(self, kwartier: datetime, laag) -> dict | None:
        """De gemeten kwartierenergie uit de meetlaag, of None (geen_meting)."""
        rec = getattr(laag, "laatste_kwartier", None) if laag is not None else None
        if not rec or not rec.get("kwartier"):
            return None
        try:
            if abs(datetime.fromisoformat(rec["kwartier"]).timestamp() - kwartier.timestamp()) > 1:
                return None
        except (TypeError, ValueError):
            return None
        velden = {"imp": "grid_import_kwh", "exp": "grid_export_kwh", "pv": "pv_kwh",
                  "bin": "battery_in_kwh", "bout": "battery_out_kwh", "huis": "house_kwh"}
        uit = {k: rec.get(v) for k, v in velden.items()}
        if any(v is None for v in uit.values()):
            return None
        return {k: float(v) for k, v in uit.items()}

    def _schaduw_afrekenen(self, grens: datetime, laag) -> None:
        boek = self._schaduw_boek_klaar()
        if boek is None:
            return
        grens = grens.replace(second=0, microsecond=0)
        kwartier = self._kwartier_sleutel(grens) - timedelta(minutes=15)
        inhoud_nu = self.beschikbare_energie_kwh()
        vorige_grens = self._schaduw_grens_inhoud
        self._schaduw_grens_inhoud = (kwartier + timedelta(minutes=15), inhoud_nu)
        lopend = self._schaduw_lopend
        if lopend is not None and lopend["t"] == kwartier.timestamp():
            inh0 = vorige_grens[1] if vorige_grens and vorige_grens[0] == kwartier else lopend["p_inh_plan"]
            rij = self._schaduw_rij(lopend, self._schaduw_meting(kwartier, laag), inh0, inhoud_nu, kwartier)
            self._schaduw_lopend = None
            self._schaduw_boek_bij(boek, kwartier, grens, rij, lopend)
        wacht = self._schaduw_wacht
        if wacht is not None:
            self._schaduw_plannen_starten(*wacht)

    def _schaduw_afrekenen_zonder_meting(self, lopend: dict) -> None:
        boek = self._schaduw_boek
        if boek is None:
            return
        kwartier = datetime.fromtimestamp(lopend["t"], timezone.utc)
        rij = self._schaduw_rij(lopend, None, None, None, kwartier)
        self._schaduw_lopend = None
        self._schaduw_boek_bij(boek, kwartier, kwartier + timedelta(minutes=15), rij, lopend)

    def _schaduw_rij(self, lopend: dict, meting: dict | None, inh0, inh1, kwartier: datetime) -> dict:
        """De kwartierregel: productie met de meting, elke variant op zijn virtuele accu."""
        status = lopend["status"] if lopend["status"] != "gepland" else "ok"
        if status == "ok" and any(not (lopend.get("varianten") or {}).get(n) for n in es.VARIANTEN):
            status = "geen_plan"         # de planning was nog niet klaar
        if meting is None or inh0 is None or inh1 is None:
            status = "geen_meting"
        uitvoering = self._kwartier_uitvoering if isinstance(self._kwartier_uitvoering, dict) else {}
        p_actie = uitvoering.get("actie") if uitvoering.get("kwartier") == kwartier else lopend["p_actie"]
        rij = {k: lopend.get(k) for k in ("t", "pin", "puit", "slijt", "huis_v", "zon_v", "p_reden", "midk")}
        rij.update(status=status, p_actie=p_actie)
        if meting is not None:
            rij.update(huis_w=meting["huis"], zon_w=meting["pv"], p_in=meting["bin"], p_uit=meting["bout"],
                       p_imp=meting["imp"], p_exp=meting["exp"])
        if inh0 is not None and inh1 is not None:
            rij.update(p_inh0=float(inh0), p_inh1=float(inh1))
        boek = self._schaduw_boek
        for naam in es.VARIANTEN:
            plan = (lopend.get("varianten") or {}).get(naam) or {}
            rij[f"{naam}_reden"] = plan.get("waarde")
            if meting is None:
                rij[f"{naam}_actie"] = plan.get("actie")
                continue
            accu = es.VirtueleAccu(inhoud_kwh=float(boek.virtueel.get(naam) or 0.0), **lopend["accu"])
            gepland = es.gepland_voor_kwartier(plan.get("accu_kwh") or 0.0, plan.get("uren") or lopend.get("uren"))
            uit = es.uitvoeren(accu, plan.get("actie") or "huis", gepland, meting["huis"], meting["pv"])
            boek.virtueel[naam] = accu.inhoud_kwh
            rij.update({f"{naam}_{k}": v for k, v in uit.items()})
        return rij

    def _schaduw_boek_bij(self, boek: es.Schaduwboek, kwartier: datetime, grens: datetime, rij: dict, lopend: dict) -> None:
        """Rij in het boek; om middernacht de dag sluiten; opschonen en bewaren."""
        dag = dt_util.as_local(kwartier).date().isoformat()
        eta_o = float((lopend.get("accu") or {}).get("eta_o") or 0.9)
        cap = float((lopend.get("accu") or {}).get("capaciteit_kwh") or 0.0)
        if boek.open_dag is not None and boek.open_dag.get("dag") != dag:
            boek.sluit_dag(self._schaduw_dagbegin(kwartier), eta_o, cap)
        if boek.open_dag is None:
            boek.open(dag, self._schaduw_dagbegin(kwartier))
        boek.voeg_rij_toe(rij)
        if dt_util.as_local(grens).date().isoformat() != dag:
            boek.sluit_dag(grens.timestamp(), eta_o, cap)
            boek.open(dt_util.as_local(grens).date().isoformat(), grens.timestamp())
        boek.opschonen(grens.timestamp())
        self._schaduw_bewaren()

    @staticmethod
    def _schaduw_dagbegin(moment: datetime) -> float:
        lokaal = dt_util.as_local(moment)
        return lokaal.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    # --- dienst, schakelaar, sensor, diagnostiek ------------------------------

    def zet_economische_schaduw(self, aan: bool) -> None:
        """Schakelaar "Economische schaduw". Uit: het lopende kwartier vervalt
        (een half gevolgd kwartier telt niet mee)."""
        self.economische_schaduw_aan = bool(aan)
        if not aan:
            self._schaduw_lopend = None
            self._schaduw_wacht = None
            self._schaduw_gepland = None

    def economische_schaduw_resync(self) -> bool:
        """Dienst `economische_schaduw_resync`: virtuele inhoud = echte inhoud."""
        boek = self._schaduw_boek
        inhoud = self.beschikbare_energie_kwh()
        if boek is None or inhoud is None:
            return False
        boek.resync(inhoud, datetime.now(timezone.utc).isoformat())
        self._schaduw_bewaren()
        return True

    def get_economische_schaduw(self) -> dict:
        """Klein, voor het sensorattribuut (< 4 kB; recorder: uitsluiten)."""
        boek = self._schaduw_boek
        if not self.economische_schaduw_aan:
            status = "uit"
        elif boek is None:
            status = "laden"
        else:
            status = self._schaduw_status
        uit = {"status": status, "fout": (self.internal_failures or {}).get(SCHADUW_SLEUTEL)}
        if boek is not None:
            uit.update(boek.samenvatting())
        return uit

    def economische_schaduw_besparing(self):
        boek = self._schaduw_boek
        return boek.besparing_c2_14d() if boek is not None else None

    def get_economische_schaduw_diagnose(self) -> dict:
        """Volledig: alle kwartierregels (met kolomnamen) en dagregels."""
        boek = self._schaduw_boek
        if boek is None:
            return {"status": "niet geladen"}
        return {**self.get_economische_schaduw(), "kolommen": list(es.KOLOMMEN),
                "kwartieren": boek.rijen, "dagregels": boek.dagen, "waarden": boek.waarden}
