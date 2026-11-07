"""Waardeplan-sturing: de lijm tussen de coordinator en `waardeplan.py` (B4.1).

Bouwt de invoer van het waardeplan, draait het, voert de keuzes uit en legt
ze uit. Ongewijzigd verhuisd uit `coordinator.py`; de coordinator erft deze
mixin.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from homeassistant.util import dt as dt_util
from . import (
    salderingspositie as salderingspositie_mod,
    waardeplan as waardeplan_mod,
)
from .const import (
    BALANCEER_KLAAR_UUR,
    CONF_BATTERY_MAX_CHARGE_POWER_ENTITY,
    BALANCEER_MAX_PRIJS_EUR,
    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
    CONF_FEEDIN_COST_EUR_PER_KWH,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_MANUAL_POWER_NUMBER,
    CONF_OPERATION_SELECT,
    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
    DEFAULT_FEEDIN_COST_EUR_PER_KWH,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_MANUAL_DISCHARGE_POWER,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    OPTION_MANUAL,
    OPTION_SMART,
    OPTION_SMART_CHARGING,
    PLAN_SPAREN_LEEG_KWH,
    PRICE_SCALE_FACTOR,
    TEKORT_LEEG_MARGE_PROCENT,
    WAARDEPLAN_EINDPRIJS_UREN,
    WAARDEPLAN_HERREKEN_AFWIJKING_KWH,
    WAARDEPLAN_INHAAL_FACTOR,
    WAARDEPLAN_MIDKWARTIER_WISSEL_EUR,
    WAARDEPLAN_ZON_AFWIJKING_FRACTIE,
    WAARDEPLAN_HORIZON_UUR,
    WAARDEPLAN_LIVE_AFWIJKING_KWH,
    WAARDEPLAN_MIN_ACTIE_W,
    WAARDEPLAN_MIN_KWARTIEREN,
    WAARDEPLAN_BEWAARKOST_EUR_PER_KWH_UUR,
    WAARDEPLAN_BEWAARMARGE_EUR,
    WAARDEPLAN_HUIS_EERST,
    WAARDEPLAN_MIN_LAAD_W,
    WAARDEPLAN_MIN_VERMOGEN_W,
    WAARDEPLAN_SLIJTAGE_TERUGVAL_CT,
    WAARDEPLAN_STUURT,
    WAARDEPLAN_VERMOGEN_TOLERANTIE_W,
    WAARDEPLAN_WEG_AANDACHT_MINUTEN,
)
from .tijdtekst import periode_met_dag
from .coordinator_hulp import _nl, accu_is_leeg

# Zelfde loggernaam als voorheen, zodat logger-instellingen in HA blijven werken.
_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")


class WaardeplanSturingMixin:
    """De waardeplan-methodes van de coordinator."""

    _WAARDEPLAN_MODUS = {
        "laden_net": "manual (laden)",
        "verkopen": "manual (verkopen)",
        "huis": "smart",
        "houden": "smart_charging (sparen)",
        "zon": "smart",
        # v5.177.0 (A11): zon terugleveren in plaats van opslaan.
        "zon_export": "manual (terugleveren)",
    }

    def _met_waardeplan(self, plan: list[dict]) -> list[dict]:
        """Het kwartierplan met de keuzes van het waardeplan (v5.158.0).

        Zolang het waardeplan stuurt, hoort de Vooruitblik te laten zien wat
        het waardeplan van plan is: per kwartier de stand, de accu-inhoud en
        het net. De rest van de regel (prijs, zon, verbruik) blijft.
        """
        rijen = getattr(self, "_waardeplan_rijen", None)
        if not WAARDEPLAN_STUURT or not rijen or not plan:
            return plan
        per_begin = {}
        for r in rijen:
            b = r.get("begin")
            if hasattr(b, "isoformat"):
                per_begin[b.astimezone(timezone.utc)] = r
        capaciteit = self.bruikbare_capaciteit_kwh()
        # v5.181.2 (b): de inhoud van het waardeplan telt boven de EFFECTIEVE
        # ondergrens (`bereken_waardeplan`, en `beschikbare_energie_kwh` trekt
        # de ondergrenscorrectie af). Hier stond de min-SoC: live 04-11 11:31
        # begon de lijn in "Prijs en lading" op ~20 % bij een accu van 35 %
        # (bodem ~25 %, min-SoC 10 %). Nu dezelfde grens als de inhoud.
        try:
            min_soc = float(self.effectieve_ondergrens_procent())
        except Exception:  # noqa: BLE001 - veilig terugvallen op de min-SoC
            min_soc = self.effective_min_soc_percent()
        bruikbaar = capaciteit * (100 - min_soc) / 100 if capaciteit else None
        uit = []
        eerste = rijen[0]
        leeg_kwh = self.accu_leeg_grens_plan_kwh()  # v5.177.0 (A7)
        # v5.175.0: "tot bijladen" = tot de eerste netlading van het
        # waardeplan, niet tot het goedkope blok van de oude planning.
        geladen = False
        for regel in plan:
            start = dt_util.parse_datetime(regel.get("start") or "")
            r = per_begin.get(start.astimezone(timezone.utc)) if start is not None else None
            if r is not None and r.get("actie") == "laden_net":
                geladen = True
            if r is None:
                if geladen and regel.get("voor_bijladen", True):
                    regel = {**regel, "voor_bijladen": False}
                uit.append(regel)
                continue
            nieuw = dict(regel)
            nieuw["voor_bijladen"] = not geladen
            nieuw["modus"] = self._WAARDEPLAN_MODUS.get(r.get("actie"), regel.get("modus"))
            nieuw["soc_kwh"] = r.get("inhoud_kwh")
            nieuw["net_kwh"] = self._waardeplan_net_kwh(r, regel.get("uren"), r is eerste)
            # v5.161.3: wat het plan in dit kwartier in de accu doet, los van
            # de startstand. Voor het vermogen; zie planvolging._accu_w.
            nieuw["inhoud_delta_kwh"] = r.get("inhoud_delta_kwh")
            # v5.183.3: huis en zon zoals het waardeplan ze rekende, voor de tabel.
            # v5.183.4: over de rest van het kwartier, net als `net_kwh`
            # (de eerste rij is van de laatste berekening, de planregel van nu).
            if r.get("verbruik_kwh") is not None:
                deel = self._waardeplan_deel(r, regel.get("uren"), r is eerste)
                nieuw["plan_verbruik_kwh"] = round(r["verbruik_kwh"] * deel, 4)
                nieuw["plan_zon_kwh"] = None if r.get("zon_kwh") is None else round(r["zon_kwh"] * deel, 4)
            # v5.175.0: zon opslaan - het overschot aan de netkant.
            if r.get("accu_ac_w") is not None:
                nieuw["accu_ac_w"] = r["accu_ac_w"]
            else:
                nieuw.pop("accu_ac_w", None)
            # v5.162.0: wat de accu van het net vraagt, niet wat er na het
            # rendement in de cellen komt (toonde 2,0 kW bij 2,4 kW laden).
            if r.get("actie") == "laden_net":
                nieuw["laden_w"] = self._waardeplan_laadvermogen_w(r)
                # v5.181.1 (punt 2): het lopende kwartier toont wat er echt
                # naar de accu ging - plan, opdracht en planvolging één getal.
                opdracht = (self.last_waardeplan or {}).get("opdracht_w")
                if r is eerste and opdracht:
                    nieuw["laden_w"] = abs(opdracht)
            nieuw["tekort"] = self._waardeplan_tekort(r, leeg_kwh)
            nieuw["bron"] = "waardeplan"
            if bruikbaar:
                nieuw["soc_procent"] = round(min_soc + (100 - min_soc) * r["inhoud_kwh"] / bruikbaar)
                nieuw["soc_bruikbaar_procent"] = round(100 * r["inhoud_kwh"] / bruikbaar)
            uit.append(nieuw)
        # v5.183.1: de ondergrens (laadstand bij een lege accu) voor de
        # grafiek; alleen op de eerste rij (attribuutgrootte).
        if uit and bruikbaar:
            uit[0] = {**uit[0], "ondergrens_procent": round(min_soc)}
        return self._plan_opbrengst_opnieuw(uit)

    @staticmethod
    def _plan_opbrengst_opnieuw(plan: list[dict]) -> list[dict]:
        """Opbrengst en looptotaal uit het net van het plan (v5.184.3).

        `_met_waardeplan` verving het net, maar `opbrengst_eur` en
        `cumulatief_eur` bleven van de oude planregel. Live 04-11 18:12:
        00:15-00:45 kostte € 0,24 per kwartier bij een net van 228 W (~€ 0,02).
        Alleen weergave en dagvergelijking; de sturing leest dit niet.
        """
        loper = 0.0
        uit = []
        for regel in plan:
            prijs_ct = regel.get("prijs_ct")
            if prijs_ct is None:
                uit.append(regel)
                continue
            opbrengst = -(regel.get("net_kwh") or 0.0) * prijs_ct / 100
            loper += opbrengst
            uit.append({**regel, "opbrengst_eur": round(opbrengst, 4), "cumulatief_eur": round(loper, 3)})
        return uit

    @staticmethod
    def _waardeplan_tekort(rij: dict, leeg_kwh: float = PLAN_SPAREN_LEEG_KWH) -> bool:
        """Hangt het huis in dit waardeplankwartier aan het net omdat de accu
        niets meer kan leveren? (v5.164.1)

        Gemeld 02-11 20:00: "Den accu kump neet meer tekort" terwijl de accu
        leeg was en het huis aan het net hing. `_met_waardeplan` zette elk
        kwartier op tekort=False, dus de teller bleef nul. Een tekort is
        netafname terwijl de accu na het kwartier leeg is; een lege accu
        spaart niets (zie PLAN_SPAREN_LEEG_KWH). Netafname met nog inhoud is
        een keuze van het plan (bewaren voor duurder), net als laden en
        verkopen.
        """
        if rij.get("actie") in ("laden_net", "verkopen", "zon_export"):
            return False
        if (rij.get("net_kwh") or 0.0) <= 0.01:
            return False
        # v5.183.1: levert de accu nog (laatste kwartieren boven de bodem), dan
        # is het "huis voeden", geen tekort (04-11 14:33: "Accu leeg" om 20:00
        # terwijl de accu nog 615 W leverde en de lijn op 13 % stond).
        if (rij.get("accu_kwh") or 0.0) < -0.05:
            return False
        # v5.177.0 (A7): de grens van `accu_leeg`, op de stap van het plan.
        return (rij.get("inhoud_kwh") or 0.0) <= leeg_kwh + 1e-9

    @staticmethod
    def _waardeplan_deel(rij: dict, uren: float | None, eerste: bool) -> float:
        """Welk deel van een waardeplanrij nog telt voor de planregel van nu (v5.183.4).

        Zelfde rekening als het huis-min-zon-deel van `_waardeplan_net_kwh`:
        verbruik en zon van de rij gelden voor de duur waarover de rij rekende.
        """
        if not uren or uren >= 0.25:
            return 1.0
        rij_uren = rij.get("uren") or (uren if eerste else 0.25)
        return min(1.0, uren / rij_uren) if rij_uren > 0 else 0.0

    @staticmethod
    def _waardeplan_net_kwh(rij: dict, uren: float | None, eerste: bool) -> float | None:
        """Het net van een waardeplanregel over de rest van het kwartier (v5.161.3).

        Het waardeplan rekent elke stap als een heel kwartier. Bij de eerste
        rij zijn zon en verbruik al de rest van het kwartier en is alleen de
        accustap heel; een oudere rij van het lopende kwartier is helemaal heel.

        v5.165.0 (akkoord Ruud 02-11): gemeld "10.511 W net terwijl het huis
        559 W gebruikte". Het waardeplan rekent één keer per kwartier; de
        eerste rij van die berekening gold voor de rest van het kwartier OP
        DAT MOMENT (vaak het hele kwartier), terwijl de planregel een paar
        minuten later nog maar een minuut telt. Verbruik min zon van een
        heel kwartier, gedeeld door één minuut, gaf 10 kW. Nu schaalt het
        deel verbruik - zon met de duur waarover de waardeplanrij rekende
        (`uren` in de rij), en de accustap met het deel van een kwartier.
        Rijen zonder `uren` (van vóór v5.165.0) houden de oude aanname.
        """
        net = rij.get("net_kwh")
        if net is None or not uren or uren >= 0.25:
            return net
        accu = rij.get("accu_kwh") or 0.0
        rij_uren = rij.get("uren") or (uren if eerste else 0.25)
        huis_min_zon = (net - accu) * min(1.0, uren / rij_uren) if rij_uren > 0 else 0.0
        return round(huis_min_zon + accu * uren / 0.25, 3)

    def _plan_volgt_waardeplan(self) -> bool:
        """Stuurt het waardeplan nu, met een plan? (v5.175.0)"""
        return bool(
            WAARDEPLAN_STUURT
            and (self.last_waardeplan or {}).get("beschikbaar")
            and getattr(self, "_waardeplan_rijen", None)
        )

    def waardeplan_tekort(self) -> dict | None:
        """Het tekort zoals het waardeplan het ziet (v5.175.0).

        Een tekortkwartier is netafname terwijl de accu leeg is
        (`_waardeplan_tekort`); netafname met inhoud is een keuze van het plan
        (vasthouden voor duurder). Tot en na de eerste netlading apart, zoals
        `verwacht_tekort`. `vastgehouden_kwh` = de lading die het plan vóór het
        eerste tekortkwartier bewust vasthoudt terwijl het huis van het net
        neemt ('houden'). None zonder waardeplan.
        """
        if not self._plan_volgt_waardeplan():
            return None
        rijen = self._waardeplan_rijen or []
        leeg_kwh = self.accu_leeg_grens_plan_kwh()  # v5.177.0 (A7)
        tot, na = 0.0, 0.0
        geladen = False
        perioden: list[list] = []
        vastgehouden = None
        eerste_tekort = False
        for r in rijen:
            if r.get("actie") == "laden_net":
                geladen = True
            if self._waardeplan_tekort(r, leeg_kwh):
                net = max(0.0, float(r.get("net_kwh") or 0.0))
                if geladen:
                    na += net
                else:
                    tot += net
                eerste_tekort = True
                b = r.get("begin")
                eind = b + timedelta(minutes=15) if hasattr(b, "isoformat") else b
                if perioden and perioden[-1][1] == b:
                    perioden[-1][1] = eind
                else:
                    perioden.append([b, eind])
            elif (
                not eerste_tekort and r.get("actie") == "houden"
                and float(r.get("net_kwh") or 0.0) > 0.01
                and float(r.get("inhoud_kwh") or 0.0) > leeg_kwh + 1e-9
            ):
                inhoud = float(r.get("inhoud_kwh") or 0.0)
                vastgehouden = inhoud if vastgehouden is None else max(vastgehouden, inhoud)

        def _tekst(b, e) -> str:
            if hasattr(b, "isoformat"):
                return f"{dt_util.as_local(b):%d-%m %H:%M}-{dt_util.as_local(e):%H:%M}"
            return f"{b}-{e}"

        return {
            "tot_bijladen_kwh": round(tot, 2),
            "na_bijladen_kwh": round(na, 2),
            "perioden": [_tekst(b, e) for b, e in perioden],
            "vastgehouden_kwh": round(vastgehouden, 2) if vastgehouden is not None else None,
        }

    # --- v5.158.0: het waardeplan -----------------------------------------

    last_waardeplan: dict | None = None
    _waardeplan_cache: tuple | None = None
    #: v5.177.0 (A5): waar een gat de horizon afknipte; sinds wanneer er geen plan is.
    _waardeplan_knip: datetime | None = None
    _waardeplan_weg_sinds: datetime | None = None
    waardeplan_weg_teller: dict | None = None

    def _waardeplan_kwartieren(self, now: datetime, entries) -> list | None:
        """De kwartieren vooruit voor het waardeplan, met verwacht verbruik,
        verwachte zon (de gewone verwachting, niet de voorzichtige band),
        inkoopprijs en terugleverwaarde. None als iets ontbreekt.

        v5.177.0 (A5): één gat (geen verbruik/zon of geen kale prijs) liet het
        hele plan wegvallen en de oude regels stil overnemen. Nu knipt het gat
        de horizon af; pas met minder dan WAARDEPLAN_MIN_KWARTIEREN kwartieren
        vóór het gat is er geen plan. Waar geknipt is: `_waardeplan_knip`.
        """
        horizon = now + timedelta(hours=WAARDEPLAN_HORIZON_UUR)
        kaal = {}
        try:
            for a, _b, prijs in self._kale_entries() or []:
                kaal[a] = prijs / PRICE_SCALE_FACTOR
        except Exception:  # noqa: BLE001
            kaal = {}
        feedin_cost = float(
            self.instelling(CONF_FEEDIN_COST_EUR_PER_KWH, DEFAULT_FEEDIN_COST_EUR_PER_KWH) or 0.0
        )
        uit = []
        self._waardeplan_knip = None
        # v5.160.0: per kwartier de verkoopreserve die de sturing dan toepast.
        reserve_cache: dict = {}
        for begin, eind, prijs in entries or []:
            if eind <= now or begin >= horizon:
                continue
            k = self._waardeplan_kwartier(now, begin, eind, prijs, kaal, feedin_cost, reserve_cache, entries)
            if k is None:
                self._waardeplan_knip = begin
                break
            uit.append(k)
        if self._waardeplan_knip is not None and len(uit) < WAARDEPLAN_MIN_KWARTIEREN:
            return None
        # v5.181.2: één vloer langs het plan - de marge van nu, daarna zakt
        # hij met het huisverbruik (zie `waardeplan.vloeren_gelijktrekken`).
        if uit:
            # v5.186.0 (punt 10): met het ontlaadrendement (inhoud per kWh huis).
            uit = waardeplan_mod.vloeren_gelijktrekken(uit, self._reserve_bodem_kwh(), self._waardeplan_eta_o(now))
        return uit or None

    def _waardeplan_eta_o(self, now: datetime) -> float:
        """Het ontlaadrendement van het plan (v5.186.0), voor de verkoopvloer;
        1,0 als het (nog) niet te bepalen is."""
        try:
            rendement = self.learned_battery_efficiency_percent or float(
                self.instelling(CONF_BATTERY_ROUND_TRIP_EFFICIENCY, DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT)
            )
            accu = waardeplan_mod.Accu(inhoud_kwh=0.0, bruikbaar_kwh=1.0, rendement=float(rendement) / 100,
                                       **self._waardeplan_rendementen(now))
            return waardeplan_mod.rendementen(accu)[1]
        except Exception:  # noqa: BLE001 - de vloer rekent dan aan de netkant
            return 1.0

    def _waardeplan_kwartier(self, now, begin, eind, prijs, kaal, feedin_cost, reserve_cache, entries):
        """Eén kwartier voor het waardeplan, of None bij een gat (v5.177.0)."""
        from . import overschotwaarde as OW

        van = max(begin, now)
        segmenten = self._segmenten_verbruik_zon(van, eind, veilig=False)
        if segmenten is None:
            return None
        # v5.186.0 (punt 34): ook de klimaat-extra's die de reserve meeneemt.
        verbruik = sum(v for v, _z in segmenten) + self._klimaat_extra_kwh_in(van, eind)
        if self._pv_gat_in(van, eind):  # v5.186.0 (punt 38): geen zon bekend = gat
            return None
        zon = self._estimate_pv_kwh_for_period(van, eind, veilig=False)
        inkoop = prijs / PRICE_SCALE_FACTOR
        incl = inkoop
        teruglever_accu = None
        if self._is_salderen_active(begin):
            # v5.168.0: bij een verwacht overschot aan het eind van het
            # salderingsjaar de marginale prijs (zonder belastingdeel).
            # v5.177.0 (A11): terugleveren levert onder de saldering de
            # inkoopprijs plus de premie op - zon opslaan kost dus die prijs.
            inkoop, teruglever = salderingspositie_mod.marginale_prijzen(
                incl, self._salderingskorting_eur(begin), FEEDIN_PREMIUM_EUR_PER_KWH, True
            )
        elif begin in kaal:
            teruglever = OW.terugleverwaarde_2027(kaal[begin], feedin_cost)
            # v5.177.0 (A9): uit de accu zonder zonnebonus.
            teruglever_accu = OW.terugleverwaarde_accu_2027(kaal[begin], feedin_cost)
        else:
            return None
        vloer = self._planning_verkoopreserve_kwh(begin, reserve_cache, entries, incl)
        return waardeplan_mod.Kwartier(
            begin, max(0.0, verbruik), max(0.0, zon or 0.0), inkoop, teruglever, max(0.0, vloer or 0.0),
            uren=(eind - van).total_seconds() / 3600,
            prijs_incl_eur=incl if inkoop != incl else None,
            teruglever_accu_eur=teruglever_accu,
        )

    def _waardeplan_slijtage_ct(self) -> float:
        """Slijtage per kWh uit de accu voor het plan (v5.177.0, A5): de
        berekening, anders de vaste terugval (geen plan zonder slijtage meer)."""
        slijt_ct = (self.get_wear_cost_overview() or {}).get("slijtage_ct_per_kwh")
        return WAARDEPLAN_SLIJTAGE_TERUGVAL_CT if slijt_ct is None else float(slijt_ct)

    def _waardeplan_eindprijs(self, kwartieren: list) -> float | None:
        """De (reken)prijs voor de uren direct na de horizon (v5.177.0, A10).

        Het 75e percentiel van de prijsverwachting over WAARDEPLAN_EINDPRIJS_UREN
        uur na het laatste plankwartier. Tijdens de saldering zonder het
        belastingdeel, net als de planprijzen. None zonder verwachting.
        """
        if not kwartieren:
            return None
        eind = kwartieren[-1].begin + timedelta(minutes=15)
        tot = eind + timedelta(hours=WAARDEPLAN_EINDPRIJS_UREN)
        prijzen = []
        for d in ((self.prijsverwachting or {}).get("dagen") or {}).values():
            for u in ((d or {}).get("model") or {}).get("uren") or []:
                try:
                    t = datetime.strptime(u["sleutel"], "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
                except (KeyError, TypeError, ValueError):
                    continue
                if eind <= t < tot and u.get("prijs_eur") is not None:
                    prijzen.append(float(u["prijs_eur"]))
        if len(prijzen) < 4:
            return None
        prijzen.sort()
        p75 = prijzen[min(len(prijzen) - 1, int(round(0.75 * (len(prijzen) - 1))))]
        if any(k.prijs_incl_eur is not None for k in kwartieren) and self._is_salderen_active(eind):
            p75 -= max(0.0, self._salderingskorting_eur(eind))
        return p75

    def bereken_waardeplan(self, now: datetime, entries) -> dict:
        """Het waardeplan van nu (v5.158.0) - zie waardeplan.py.

        v5.186.0 (punt 20): synchroon (tests, terugval). De sturing gebruikt
        `_async_bereken_waardeplan`: zelfde invoer en afronding, maar het
        rekenwerk (`waardeplan.plan`, puur Python/numpy) in een executor.
        """
        voor = self._waardeplan_invoer(now, entries)
        if "uitkomst" in voor:
            return voor["uitkomst"]
        res = waardeplan_mod.plan(voor["kwartieren"], voor["accu"])
        # v5.189.1: ook hier de schaduwhaak. In de ronde vraagt `_secundaire_laag`
        # het plan vaak eerst synchroon op; dat vulde de cache en de schaduw
        # (alleen in het async pad) plande dan nooit (live 05-11 18:30 - 07-11).
        self._economische_schaduw_na_plan(now, voor, res)
        return self._waardeplan_afronden(now, voor, res)

    async def _async_bereken_waardeplan(self, now: datetime, entries) -> dict:
        """`bereken_waardeplan` met het rekenwerk buiten de event loop (v5.186.0, punt 20).

        De invoer (HA-toestanden, instellingen) en de afronding (attributen,
        log) blijven op de loop; alleen `waardeplan.plan` gaat naar de
        executor: het raakt alleen zijn eigen invoer (dataclasses) aan.
        """
        if "bereken_waardeplan" in vars(self):
            # testhaak: een test die `bereken_waardeplan` vervangt, blijft werken
            return self.bereken_waardeplan(now, entries)
        voor = self._waardeplan_invoer(now, entries)
        if "uitkomst" in voor:
            return voor["uitkomst"]
        hass = getattr(self, "hass", None)
        uitvoeren = getattr(hass, "async_add_executor_job", None)
        if uitvoeren is None:
            res = waardeplan_mod.plan(voor["kwartieren"], voor["accu"])
        else:
            res = await uitvoeren(waardeplan_mod.plan, voor["kwartieren"], voor["accu"])
        # v5.187.0: de economische schaduw krijgt een kopie van deze invoer
        # (alleen bij het eerste plan van het kwartier); productie wacht er niet op.
        self._economische_schaduw_na_plan(now, voor, res)
        return self._waardeplan_afronden(now, voor, res)

    def _waardeplan_invoer(self, now: datetime, entries) -> dict:
        """De invoer van het waardeplan (v5.186.0 uit `bereken_waardeplan`):
        {"kwartieren", "accu", "bruikbaar", "balans"}, of {"uitkomst": ...}
        als er niets te rekenen valt."""
        uit: dict = {"beschikbaar": False, "berekend_om": now.isoformat()}
        beschikbaar = self.beschikbare_energie_kwh()
        capaciteit = self.bruikbare_capaciteit_kwh()
        rendement = self.learned_battery_efficiency_percent or float(
            self.instelling(CONF_BATTERY_ROUND_TRIP_EFFICIENCY, DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT)
        )
        # slijtage per kWh uit de accu (zoals bij verkopen); de datacorrectie
        # op netladen komt er sinds v5.165.0 apart bij (`_waardeplan_rendementen`)
        if beschikbaar is None or not capaciteit or not rendement:
            uit["reden"] = "accu-inhoud, capaciteit of rendement onbekend"
            return {"uitkomst": uit}
        # v5.172.0 (punt 4): boven de effectieve ondergrens (gelijk aan de
        # min-SoC zolang de accu niet eerder stopt), net als de inhoud.
        bruikbaar = capaciteit * (100 - self.effectieve_ondergrens_procent(now)) / 100
        # v5.164.1: één budget voor de live correctie over het hele plan.
        with self._gedeeld_correctiebudget():
            kwartieren = self._waardeplan_kwartieren(now, entries)
        if not kwartieren:
            uit["reden"] = "geen verbruiksverwachting of prijzen vooruit"
            return {"uitkomst": uit}
        accu = self._waardeplan_accu(now, beschikbaar, bruikbaar, rendement, kwartieren)
        balans = self._waardeplan_balanceren(now, kwartieren, accu)
        accu.vol_na_kwartier = balans.get("kwartier")
        return {"kwartieren": kwartieren, "accu": accu, "bruikbaar": bruikbaar, "balans": balans}

    def _waardeplan_afronden(self, now: datetime, voor: dict, res) -> dict:
        """Van de uitkomst van `waardeplan.plan` naar de attributen (v5.186.0
        uit `bereken_waardeplan`)."""
        uit: dict = {"beschikbaar": False, "berekend_om": now.isoformat()}
        kwartieren, accu, bruikbaar, balans = voor["kwartieren"], voor["accu"], voor["bruikbaar"], voor["balans"]
        # v5.186.0 (punt 14): de huis-eerst-toets van v5.179.1 zit in het plan zelf.
        self.waardeplan_zon_export_geweigerd = bool(getattr(res, "zon_export_geweigerd", 0))
        if getattr(res, "rondelimiet", False):
            # v5.186.0 (punt 15): de toetsen raakten niet uitgerekend; eens per uur in de log.
            sleutel = now.strftime("%Y-%m-%d %H")
            if getattr(self, "_rondelimiet_gemeld", None) != sleutel:
                self._rondelimiet_gemeld = sleutel
                _LOGGER.warning(
                    "Waardeplan: na %s rondes staan er nog overtredingen in het plan: %s",
                    getattr(res, "rondes", "?"), getattr(res, "resterend", {}) or "-")
        # v5.184.2 (vangnet): het lopende kwartier kon alleen zonder de
        # dekregels; eens per kwartier in de log, zodat het opvalt.
        if res.beschikbaar and res.kwartieren and res.kwartieren[0].get("vangnet"):
            sleutel = now.strftime("%Y-%m-%d %H:") + str(now.minute // 15)
            if getattr(self, "_vangnet_gemeld", None) != sleutel:
                self._vangnet_gemeld = sleutel
                _LOGGER.warning(
                    "Waardeplan: geen stap paste in de regels voor dit kwartier (%s); "
                    "gekozen zonder de dekregels (vangnet)", res.kwartieren[0].get("actie"))
        if not res.beschikbaar:
            uit["reden"] = res.reden
            return uit
        self._waardeplan_rijen = res.kwartieren
        uit.update(self._waardeplan_uitkomst(res, accu, bruikbaar, kwartieren, balans))
        return uit

    def _waardeplan_accu(self, now, beschikbaar, bruikbaar, rendement, kwartieren):
        """De accu voor het waardeplan (v5.177.0 uit `bereken_waardeplan`)."""
        laden_kw = abs(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER) or 0) / 1000
        ontladen_kw = abs(self.instelling(CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER) or 0) / 1000
        # v5.183.5: de slimme stand dekt het huis tot de ontlaadgrens van de
        # omvormer (2,4 kW); alleen een verkoop loopt op het handmatige
        # vermogen (1,2 kW). Het plan rekende ook het huis dekken met 1,2 kW
        # (04-11 16:45: koken op 2,2-4,6 kW, accu op sparen).
        try:
            slim_kw = float(self.slimme_ontlaadgrens_w()) / 1000
        except Exception:  # noqa: BLE001
            slim_kw = None
        # v5.186.0 (punt 13): de slimme stand slaat zon op tot de laadgrens van
        # de omvormer (max. laadvermogen-entiteit), niet tot het handmatige
        # laadvermogen; zonder entiteit het handmatige.
        laden_slim_kw = None
        try:
            gemeten = self._read_sensor_float(self.config.get(CONF_BATTERY_MAX_CHARGE_POWER_ENTITY))
            if gemeten is not None and 100 <= abs(gemeten) <= 12000:
                laden_slim_kw = abs(gemeten) / 1000
        except Exception:  # noqa: BLE001
            laden_slim_kw = None
        return waardeplan_mod.Accu(
            inhoud_kwh=max(0.0, beschikbaar),
            bruikbaar_kwh=bruikbaar,
            laden_kw=laden_kw or 2.4,
            laden_slim_kw=laden_slim_kw,
            ontladen_kw=max(slim_kw or 0.0, ontladen_kw or 2.4),
            verkoop_kw=ontladen_kw or 2.4,
            rendement=rendement / 100,
            slijtage_eur=self._waardeplan_slijtage_ct() / 100,
            verkoopmarge_eur=self._verkoop_min_winst_eur(),
            netladen=True,
            verkopen=True,
            # v5.182.0 (akkoord Ruud 04-11): woning eerst, alleen overschot verkopen.
            huis_eerst=WAARDEPLAN_HUIS_EERST,
            # v5.183.0 (akkoord Ruud 04-11 14:04): bewaarmarge en onzekerheid vooruit.
            bewaarmarge_eur=WAARDEPLAN_BEWAARMARGE_EUR,
            bewaarkost_eur_per_kwh_uur=WAARDEPLAN_BEWAARKOST_EUR_PER_KWH_UUR,
            # v5.172.0 (punt 2): geen mini-opdrachten (zie waardeplan.actie_van).
            min_actie_w=WAARDEPLAN_MIN_ACTIE_W,
            # v5.177.0 (A12): netladen vanaf 500 W.
            min_laad_w=WAARDEPLAN_MIN_LAAD_W,
            # v5.177.0 (A11): de sturing kan terugleveren afdwingen (handmatig,
            # zie `_waardeplan_als_nodig`), dus mag het plan het kiezen.
            zon_export_afdwingbaar=True,
            # v5.177.0 (A10): de waarde aan het eind uit de prijsverwachting.
            eindprijs_eur=self._waardeplan_eindprijs(kwartieren),
            **self._waardeplan_rendementen(now),
        )

    def _waardeplan_uitkomst(self, res, accu, bruikbaar, kwartieren, balans) -> dict:
        """De attributen van een berekend waardeplan (v5.177.0 uit `bereken_waardeplan`)."""
        nu = res.kwartieren[0]
        return {
            "beschikbaar": True,
            "inhoud_kwh": round(accu.inhoud_kwh, 2),
            "bruikbaar_kwh": round(bruikbaar, 2),
            "kwartieren": len(res.kwartieren),
            # v5.179.1: zon terugleveren geweigerd omdat het huis daarna leeg zou staan.
            # v5.186.0 (punt 14): uit het plan zelf (kwartieren met geweigerd terugleveren).
            "zon_export_geweigerd": bool(getattr(res, "zon_export_geweigerd", 0)),
            "zon_export_geweigerd_kwartieren": int(getattr(res, "zon_export_geweigerd", 0) or 0),
            # v5.177.0 (A5): tot waar het plan reikt als een gat het afknipte.
            "afgeknipt_bij": self._waardeplan_knip.isoformat() if self._waardeplan_knip else None,
            "kosten_plan_eur": res.kosten_plan_eur,
            "kosten_zonder_accu_eur": res.kosten_zonder_accu_eur,
            "besparing_plan_eur": round(
                (res.kosten_zonder_accu_eur or 0) - (res.kosten_plan_eur or 0), 2
            ),
            "eindwaarde_eur_per_kwh": res.eindwaarde_eur_per_kwh,
            # v5.186.0 (punt 4): tot de knik telt de eindwaarde hierboven (het
            # huistekort na de horizon), daarboven de lage waarde.
            "eindwaarde_knik_kwh": getattr(res, "eindwaarde_knik_kwh", None),
            "eindwaarde_laag_eur_per_kwh": getattr(res, "eindwaarde_laag_eur_per_kwh", None),
            # v5.186.0 (punt 15): de toetsen achteraf - rondes, wat er nog
            # overtreden wordt (hoort leeg te zijn) en of de rondegrens geraakt is.
            "toets_rondes": getattr(res, "rondes", None),
            "toets_resterend": getattr(res, "resterend", None) or {},
            "toets_rondelimiet": bool(getattr(res, "rondelimiet", False)),
            # v5.184.2: kwartieren die het plan alleen zonder de dekregels kon
            # vullen (vangnet); hoort 0 te zijn.
            "vangnet_kwartieren": sum(1 for r in res.kwartieren if r.get("vangnet")),
            "eindprijs_bron": "prijsverwachting" if accu.eindprijs_eur is not None else "75e percentiel plan",
            "verkoopmarge_eur": accu.verkoopmarge_eur,
            # v5.165.0: de datacorrectie op netladen en de rendementen.
            "netlaadmarge_eur": accu.netlaadmarge_eur,
            "laadrendement_procent": round(waardeplan_mod.rendementen(accu)[0] * 100, 1),
            "ontlaadbanden": [
                {"tot_w": None if g == math.inf else g, "rendement_procent": None if e is None else round(e * 100, 1)}
                for g, e in accu.ontlaadbanden
            ],
            "nu": {**nu, "begin": nu["begin"].isoformat() if hasattr(nu["begin"], "isoformat") else nu["begin"]},
            "vooruit": [
                {**r, "begin": r["begin"].isoformat() if hasattr(r["begin"], "isoformat") else r["begin"]}
                for r in res.kwartieren[:24]
            ],
            "verwachte_inhoud_kwh": nu["inhoud_kwh"],
            "balanceren": balans or None,
            # v5.168.0: met welke prijs het plan rekent tijdens de saldering.
            "rekenbasis": (
                "marginaal: prijs zonder belastingdeel (verwacht salderingsoverschot)"
                if any(k.prijs_incl_eur is not None for k in kwartieren) else "prijs incl. belasting"
            ),
            "salderingspositie": self.salderingspositie_weergave(),
        }

    def _waardeplan_rendementen(self, now: datetime) -> dict:
        """De datacorrectie en de rendementen voor het waardeplan (v5.165.0).

        Akkoord Ruud 02-11, twee punten:

        1. Datacorrectie op netladen. Het oude laadbesluit eist dat een kWh
           uit het net de slijtage plus de datacorrectie goedmaakt
           (`_laadkosten_ct`): gemeten netladingen leverden minder op dan
           voorspeld. Het waardeplan negeerde die; op 02-11 laadde het om
           14:00-14:45 voor 34,6/37,3/36,9 ct voor een avond van 50-51 ct.
           Nu kost elke kWh die boven het zonoverschot uit het net de accu
           in gaat dezelfde correctie (`laadcorrectie_ct`, max. 5 ct).
        2. Rendement per vermogensband (`get_rendement_per_band`) als die
           betrouwbaar is, anders het ene getal. v5.166.0: banden per hele
           ronde gemeten (de 69 % bij 500 W was kwartier-selectie); laden
           uit de laadbanden, anders het geleerde, anders wortel rondrit.
        """
        from . import accukosten as A

        uit: dict = {}
        try:
            uit["netlaadmarge_eur"] = max(0.0, float(self.laadcorrectie_ct() or 0.0)) / 100
        except Exception:  # noqa: BLE001 - zonder correctie rekent het plan door
            _LOGGER.debug("Datacorrectie voor het waardeplan niet beschikbaar", exc_info=True)
        try:
            alle = self.get_rendement_per_band(now) or {}
        except Exception:  # noqa: BLE001
            alle = {}
        # v5.166.0: laden uit dezelfde rondemeting (AC-teller) als de
        # ontlaadbanden zodra een laadband betrouwbaar is; anders het
        # geleerde laadrendement (vermogenssensor, hele stukken >= 1,5 kWh).
        laden = A.laadrendement_uit_banden(alle)
        if laden is None and self.learned_charge_efficiency_percent:
            laden = self.learned_charge_efficiency_percent / 100
        # v5.169.0: met de rondrit uit de kWh-meter hetzelfde splitspunt als
        # het geleerde rendement, zodat laden x ontladen = de gemeten rondrit.
        anker = self._rondrit_anker()
        if anker is not None:
            laden = anker["laden"]
        if laden:
            uit["rendement_laden"] = laden
        # v5.167.0 (audit punt 4): een onbetrouwbare ontlaadband viel terug op
        # rondrit / laden (0,83/0,819 -> 1,0) terwijl de huisband 95,8 % had:
        # verkopen op hoog vermogen leek ~4 pt zuiniger. Nu het gemeten
        # ontlaadrendement over alle rondes (zelfde grondslag) als terugval.
        ontladen = self.learned_discharge_efficiency_percent
        if ontladen:
            uit["rendement_ontladen"] = min(A.ONTLAAD_RENDEMENT_MAX, ontladen / 100)
        banden = alle.get("ontladen") or {}
        grenzen = tuple(A.BANDEN_W) + (math.inf,)
        rijen = []
        for grens, naam in zip(grenzen, A.BAND_NAMEN):
            b = banden.get(naam) or {}
            eta = b["rendement_procent"] / 100 if b.get("betrouwbaar") and b.get("rendement_procent") else None
            rijen.append((grens, eta))
        if any(eta for _g, eta in rijen):
            uit["ontlaadbanden"] = tuple(rijen)
        return uit

    #: v5.162.0: het moment waarop de lopende balanceerlading klaar moet zijn.
    _balanceer_doel: datetime | None = None

    def _waardeplan_balanceren(self, now: datetime, kwartieren: list, accu) -> dict:
        """Moet het waardeplan vol laden voor de balans? (v5.162.0, L-EMS-055)

        Het waardeplan beslist vóór de oude regels, dus `_balanceer_laadbesluit`
        kwam niet meer aan bod. Dezelfde vraag, hier als eis aan het plan: vol
        vóór het vaste moment (zie BALANCEER_KLAAR_UUR); het plan kiest de
        goedkoopste kwartieren. Leeg = geen eis.
        """
        bal = self.balanceerlading(now)
        ruimte = self._resterende_laadruimte_kwh()
        if not bal.get("nodig") or ruimte is None or ruimte <= 0.05:
            self._balanceer_doel = None
            return {}
        if self._balanceer_zon_vult_vandaag(now, accu.inhoud_kwh, ruimte):
            return {"reden": f"{bal['reden']}; de zon maakt de accu vandaag vol"}
        einde = kwartieren[-1].begin + timedelta(minutes=15)
        # v5.186.0 (punt 6): het laadrendement van het plan (was de wortel van de rondrit).
        per_kwartier = accu.laden_kw * accu.duur_h * waardeplan_mod.rendementen(accu)[0]
        doel = self._balanceer_doel
        if doel is None or doel <= now:
            # Een nieuw moment; niet meer haalbaar vóór 08:00 = de dag erna,
            # anders laadt hij op het laatste moment tegen elke prijs.
            doel = dt_util.as_local(now).replace(
                hour=BALANCEER_KLAAR_UUR, minute=0, second=0, microsecond=0
            )
            if doel <= now:
                doel += timedelta(days=1)
            nodig = math.ceil((accu.bruikbaar_kwh - accu.inhoud_kwh) / per_kwartier)
            if sum(1 for k in kwartieren if k.begin < doel) < nodig:
                doel += timedelta(days=1)
        if doel > einde:
            self._balanceer_doel = None
            return {"reden": f"{bal['reden']}; wacht op de prijzen tot {doel:%d-%m %H:%M}"}
        index = sum(1 for k in kwartieren if k.begin < doel) - 1
        # v5.163.0: alleen als er vóór het doel genoeg kwartieren onder de
        # prijsgrens zijn; anders geen eis, zodat het plan niet duurder bijkoopt.
        nodig = math.ceil((accu.bruikbaar_kwh - accu.inhoud_kwh) / per_kwartier)
        # v5.177.0 (A2): de grens is een prijs incl. belasting; tijdens de
        # saldering met overschot is `inkoop_eur` de marginale prijs (~11 ct
        # lager) en kwamen er te veel kwartieren onder de grens.
        goedkoop = sum(
            1 for k in kwartieren[: index + 1]
            if (k.inkoop_eur if k.prijs_incl_eur is None else k.prijs_incl_eur) < BALANCEER_MAX_PRIJS_EUR
        )
        if goedkoop < nodig:
            self._balanceer_doel = None
            grens = BALANCEER_MAX_PRIJS_EUR * 100
            return {"reden": f"{bal['reden']}; wacht op een prijs onder {grens:.0f} ct"}
        self._balanceer_doel = doel
        return {
            "kwartier": index,
            "vol_om": doel.isoformat(),
            "reden": f"{bal['reden']}: vol vóór {dt_util.as_local(doel):%d-%m %H:%M}",
        }

    def _waardeplan_uit_cache(self, now: datetime) -> tuple:
        """(kwartier, het plan uit de cache of None) - v5.186.0 uit `_waardeplan_nu`."""
        kwartier = self._kwartier_sleutel(now)
        cache = self._waardeplan_cache
        inhoud = self.beschikbare_energie_kwh()
        if cache is not None and cache[0] == kwartier and cache[1].get("beschikbaar"):
            begin_inhoud = cache[1].get("inhoud_kwh")
            if (
                inhoud is None or begin_inhoud is None
                or (
                    abs(max(0.0, inhoud) - begin_inhoud) < WAARDEPLAN_HERREKEN_AFWIJKING_KWH
                    + abs(float((cache[1].get("nu") or {}).get("accu_kwh") or 0.0))
                    and not self._waardeplan_wijkt_live_af(now, cache[1], max(0.0, inhoud))
                )
            ):
                return kwartier, cache[1]
            # v5.186.0 (B11): een herplanning midden in het kwartier, geteld.
            self._tel_herplanning(now, "midkwartier")
        return kwartier, None

    def _waardeplan_nu(self, now: datetime, entries) -> dict:
        """Het plan voor dit kwartier: één keer per kwartier rekenen, of
        opnieuw als de accu-inhoud ver van het plan afwijkt."""
        kwartier, plan = self._waardeplan_uit_cache(now)
        if plan is not None:
            return plan
        laatst = getattr(self, "_waardeplan_laatst", None)
        if laatst is not None and laatst[0] == now:
            return laatst[1]   # v5.186.0: deze ronde al (async) berekend
        try:
            plan = self.bereken_waardeplan(now, entries)
        except Exception:  # noqa: BLE001 - het plan mag de sturing nooit breken
            _LOGGER.exception("Waardeplan niet te berekenen; de oude regels gelden")
            plan = {"beschikbaar": False, "reden": "rekenfout"}
        return self._waardeplan_bewaar(now, kwartier, plan)

    async def _async_waardeplan_nu(self, now: datetime, entries) -> dict:
        """`_waardeplan_nu` met het rekenwerk in de executor (v5.186.0, punt 20)."""
        kwartier, plan = self._waardeplan_uit_cache(now)
        if plan is not None:
            return plan
        try:
            plan = await self._async_bereken_waardeplan(now, entries)
        except Exception:  # noqa: BLE001 - het plan mag de sturing nooit breken
            _LOGGER.exception("Waardeplan niet te berekenen; de oude regels gelden")
            plan = {"beschikbaar": False, "reden": "rekenfout"}
        # v5.186.0: ook een plan zonder uitkomst geldt voor de rest van deze
        # ronde (`_waardeplan_gaat_sturen` rekent dan niet nog eens synchroon).
        self._waardeplan_laatst = (now, plan)
        return self._waardeplan_bewaar(now, kwartier, plan)

    def _waardeplan_bewaar(self, now: datetime, kwartier, plan: dict) -> dict:
        """Een vers plan vastleggen (v5.186.0 uit `_waardeplan_nu`)."""
        if not plan.get("beschikbaar"):
            # v5.175.0: dan sturen de oude regels; de tabel toont die.
            self._waardeplan_rijen = None
        # v5.175.0: het kwartierplan van deze ronde opnieuw, met DIT plan.
        # Na de herstart van 03-11 14:59 bouwde een eerder onderdeel van de
        # ronde het kwartierplan vóór het waardeplan er was; de melding "Den
        # accu kump tekort" (20:15-06:00, laagste 10 %) kwam uit de oude
        # planning, terwijl de tabel 20 % vasthield.
        self._kwartierplan_cache = None
        # v5.181.1 (punt 6): een plan uit de opstartfase niet voor het hele
        # kwartier vasthouden (04-11 10:17: de rij van de opstart bleef tot
        # 10:30 sturen); de eerste volle ronde daarna rekent opnieuw.
        if not self._opstart_stuurstil(now):
            self._waardeplan_cache = (kwartier, plan)
        return plan

    @staticmethod
    def _waardeplan_wijkt_live_af(now: datetime, plan: dict, inhoud: float) -> bool:
        """Wijkt de accu NU meer dan een planstap af van het plan? (v5.181.1, punt 8)

        Live 04-11 10:56: de verwachte accustand begon bij "nu" op ~19 %
        terwijl de accu op ~31 % stond. Het plan rekende één keer per
        kwartier en hield de inhoud van het begin vast. Verwacht voor nu:
        de inhoud bij het rekenen plus het deel van de planstap dat er
        inmiddels had moeten zijn. Wijkt de echte inhoud daar meer dan
        WAARDEPLAN_LIVE_AFWIJKING_KWH van af, dan opnieuw plannen.
        """
        nu = plan.get("nu") or {}
        berekend = dt_util.parse_datetime(str(plan.get("berekend_om") or ""))
        begin = plan.get("inhoud_kwh")
        eind = nu.get("inhoud_kwh")
        if berekend is None or begin is None or eind is None:
            return False
        uren = float(nu.get("uren") or 0.25)
        deel = 1.0 if uren <= 0 else min(1.0, max(0.0, (now - berekend).total_seconds() / 3600 / uren))
        verwacht = float(begin) + (float(eind) - float(begin)) * deel
        return abs(float(inhoud) - verwacht) > WAARDEPLAN_LIVE_AFWIJKING_KWH

    def _waardeplan_laadvermogen_w(self, rij: dict) -> float:
        """Het laadvermogen van een planrij, gemeten aan het net (v5.162.0)."""
        ingesteld = abs(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER) or 0)
        if rij.get("vol_vermogen"):
            return ingesteld
        # v5.177.0 (A4): energie gedeeld door de duur van de rij (het lopende
        # kwartier is korter dan 0,25 uur), niet x 4000.
        return min(ingesteld, float(rij.get("accu_kwh") or 0.0) * self._per_uur_w(rij))

    @staticmethod
    def _per_uur_w(rij: dict) -> float:
        """kWh van een planrij naar W: 1000 / de duur van de rij (v5.177.0)."""
        uren = float(rij.get("uren") or 0.25)
        return 1000 / uren if uren > 0 else 4000

    def _waardeplan_laadvermogen_nu_w(self, rij: dict, plan: dict, now: datetime) -> float:
        """Het laadvermogen voor de rest van het lopende kwartier (v5.181.1, punt 2).

        Live 04-11: om 10:17:45 (opstart) schreef het EMS -1782 W - de energie
        van de planrij gedeeld door de rest van het kwartier OP DAT MOMENT -
        en daarna tot 10:30 niets meer, terwijl er minder tijd overbleef en
        de accu tussendoor niet had geladen. Het plan rekent één keer per
        kwartier; het vermogen hoort elke ronde te volgen uit wat er van de
        rij nog over is: (energie van de rij - al geladen sinds het plan) /
        resterende tijd, hooguit het ingestelde laadvermogen. Zonder
        tijdstip of inhoud van het plan: de rij zelf (zoals voorheen).
        """
        ingesteld = abs(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER) or 0)
        basis = self._waardeplan_laadvermogen_w(rij)
        if rij.get("vol_vermogen"):
            return basis
        berekend = dt_util.parse_datetime(str(plan.get("berekend_om") or ""))
        begin_inhoud = plan.get("inhoud_kwh")
        inhoud = self.beschikbare_energie_kwh()
        if berekend is None or begin_inhoud is None or inhoud is None or now <= berekend:
            return basis
        lokaal = dt_util.as_local(berekend)
        kwartier = lokaal.replace(minute=lokaal.minute // 15 * 15, second=0, microsecond=0)
        eind = kwartier + timedelta(minutes=15)
        if not (kwartier <= dt_util.as_local(now) < eind):
            return basis
        rest_uren = max((eind - dt_util.as_local(now)).total_seconds() / 3600, 1 / 60)
        rendement = float(plan.get("laadrendement_procent") or 100) / 100
        geladen = max(0.0, float(inhoud) - float(begin_inhoud)) / (rendement if rendement > 0 else 1.0)
        nog = max(0.0, float(rij.get("accu_kwh") or 0.0) - geladen)
        # v5.186.0 (B23): inhalen begrensd. Aan het eind van het kwartier
        # (rest minimaal 1 minuut) werd de rest bijna op vol vermogen gezet -
        # en dat liep het volgende kwartier in tot de eerste ronde daar.
        return min(ingesteld, nog * 1000 / rest_uren, basis * WAARDEPLAN_INHAAL_FACTOR)

    def _als_al_ingesteld(self, vermogen: float) -> float:
        """Staat de accu al handmatig binnen de marge van dit vermogen, dan
        dat vermogen (v5.181.1, punt 2): niet elke ronde een paar watt
        bijschrijven, wel zodra het verschil groter is."""
        stand = self.hass.states.get(self.config.get(CONF_OPERATION_SELECT) or "")
        getal = self.hass.states.get(self.config.get(CONF_MANUAL_POWER_NUMBER) or "")
        if stand is None or getal is None or stand.state != OPTION_MANUAL:
            return vermogen
        try:
            huidig = float(getal.state)
        except (TypeError, ValueError):
            return vermogen
        if abs(huidig - vermogen) < WAARDEPLAN_VERMOGEN_TOLERANTIE_W:
            return huidig
        return vermogen

    def _waardeplan_niet_gestuurd(self, now: datetime) -> str | None:
        """Waarom het besluit niet naar de accu gaat, of None (v5.181.1, punt 1).

        Live 04-11 09:45-10:14: de reden stond op "waardeplan_terugleveren"
        terwijl de accu op smart_charging bleef. De knop "Handmatig smart
        charge" (09:34) had de leermodus aangezet: het EMS rekende door, maar
        schreef terecht niets. Dat stond nergens bij het besluit.
        """
        if self.learning_only:
            stand = getattr(self, "handmatige_stand", None)
            return f"leermodus (handmatige stand {stand})" if stand else "leermodus"
        if self._opstart_stuurstil(now):
            return "opstartfase: de accu blijft zoals hij staat tot de eerste volle ronde"
        return None

    async def _waardeplan_als_nodig(self, now: datetime, entries) -> bool:
        """Past het waardeplan toe (v5.158.0, akkoord Ruud 02-11).
        True als de beslissing klaar is; False = de oude regels gelden."""
        if not WAARDEPLAN_STUURT:
            self.last_waardeplan = {"beschikbaar": False, "reden": "uitgezet"}
            return False
        if self._is_emergency_low_battery():
            # Bijna leeg: de noodregel van de oude sturing gaat voor.
            return False
        # v5.186.0 (punt 20): het rekenwerk buiten de event loop.
        plan = self.last_waardeplan = dict(await self._async_waardeplan_nu(now, entries))
        self._noteer_waardeplan_beschikbaar(now, plan)
        if not plan.get("beschikbaar"):
            return False
        actie, charge_power, discharge_power, uitvoerplan = self._waardeplan_kies(now, plan)
        plan["uitgevoerd"] = actie
        # v5.181.1 (punten 1 en 2): wat er naar de accu gaat (W, + ontladen,
        # - laden; 0 bij terugleveren), en of het er wel heen gaat.
        plan["opdracht_w"] = (
            charge_power if charge_power is not None
            else discharge_power if discharge_power is not None
            else 0 if actie == "zon_export" else None
        )
        plan["niet_gestuurd"] = self._waardeplan_niet_gestuurd(now)
        geschreven = await self._waardeplan_schrijf(now, actie, charge_power, discharge_power)
        if not geschreven:
            # v5.186.0 (B22): plan en uitvoering apart vastleggen - geen
            # opdracht_w claimen die niet is geschreven, en zeggen waarom.
            plan["opdracht_w"] = None
            if not plan["niet_gestuurd"]:
                plan["niet_gestuurd"] = getattr(self, "laatste_schrijfuitkomst", None) or "schrijven mislukt"
        self._kwartier_uitvoering = {"kwartier": self._kwartier_sleutel(now), "plan": uitvoerplan, "actie": actie}
        plan["herplanningen"] = {k: v for k, v in (self.waardeplan_herplanningen or {}).items()
                                 if not k.startswith("_")}
        self.last_waardeplan = plan
        self._update_financial_tracking(now, entries, self.last_reason, discharge_power, charge_power)
        self._update_shortfall_detection(
            now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge
        )
        self._finish_decision_tick(now)
        return True

    async def _waardeplan_schrijf(self, now: datetime, actie: str, charge_power, discharge_power) -> bool:
        """De gekozen actie naar de accu; True als die er nu staat (v5.186.0,
        uit `_waardeplan_als_nodig`)."""
        if charge_power is not None:
            gelukt = await self._async_apply_manual(charge_power)
            self.last_reason = "waardeplan_laden"
            self.last_charge_power_applied = charge_power
        elif discharge_power is not None:
            gelukt = await self._async_apply_manual(discharge_power)
            self.last_reason = "waardeplan_verkopen"
        elif actie == "zon_export":
            # v5.177.0 (A11): het overschot het net op - handmatig op 0 W, de
            # slimme standen zouden het zelf opladen.
            gelukt = await self._async_apply_manual(0)
            self.last_reason = "waardeplan_terugleveren"
        elif actie == "huis":
            gelukt = await self._async_apply_operation(OPTION_SMART)
            self.last_reason = "waardeplan_huis"
        else:
            gelukt = await self._async_apply_operation(OPTION_SMART_CHARGING)
            # v5.175.3: een lege accu bewaart niets - alleen de naam wijkt af.
            if self._waardeplan_accu_leeg(now):
                self.last_reason = "waardeplan_leeg"
            else:
                self.last_reason = "waardeplan_houden"
        return gelukt is not False

    # --- v5.186.0 (B11/B12): niet wisselen midden in het kwartier ------------

    _kwartier_uitvoering: dict | None = None
    waardeplan_herplanningen: dict | None = None
    _zon_herplan_kwartier = None

    _STAND_VAN_ACTIE = {
        "laden_net": OPTION_MANUAL, "verkopen": OPTION_MANUAL, "zon_export": OPTION_MANUAL,
        "huis": OPTION_SMART, "zon": OPTION_SMART, "houden": OPTION_SMART_CHARGING,
    }

    @staticmethod
    def _kwartier_sleutel(now: datetime) -> datetime:
        # v5.186.0: in UTC - de klok van 02:15 komt bij de wintertijd twee keer.
        utc = now.astimezone(timezone.utc)
        return utc.replace(minute=(utc.minute // 15) * 15, second=0, microsecond=0)

    def _waardeplan_kies(self, now: datetime, plan: dict) -> tuple:
        """(actie, laadvermogen, ontlaadvermogen, uitvoerplan) (v5.186.0, B11).

        Live 04-11 17:02: smart -> smart_charging -> smart binnen 23 s. Een
        afwijking van 0,15 kWh liet het plan midden in het kwartier opnieuw
        rekenen, en de nieuwe eerste rij koos een andere stand. Na zo'n
        herplanning geldt voor de rest van het kwartier de stand van het
        plan dat dit kwartier al uitvoerde; alleen het vermogen volgt.
        Een andere stand alleen als die duidelijk beter is of de veiligheid
        erom vraagt (`_midkwartier_wissel_reden`).
        """
        actie, charge_power, discharge_power = self._waardeplan_opdracht(now, plan, plan.get("nu") or {})
        actie = self._zonder_smart_charging(actie)
        oud = self._midkwartier_vasthouden(now, plan, actie)
        if oud is None:
            return actie, charge_power, discharge_power, plan
        actie, charge_power, discharge_power = self._waardeplan_opdracht(now, oud, oud.get("nu") or {})
        return self._zonder_smart_charging(actie), charge_power, discharge_power, oud

    def _zonder_smart_charging(self, actie: str) -> str:
        if actie in ("houden", "zon") and not self.smart_charging_supported():
            return "huis"
        return actie

    def _midkwartier_vasthouden(self, now: datetime, plan: dict, actie: str) -> dict | None:
        """Het plan om dit kwartier mee door te gaan, of None (v5.186.0, B11)."""
        vorige = self._kwartier_uitvoering
        if not vorige or vorige.get("kwartier") != self._kwartier_sleutel(now):
            return None
        oud = vorige.get("plan") or {}
        if not oud.get("beschikbaar") or oud.get("berekend_om") == plan.get("berekend_om"):
            return None
        oud_actie = vorige.get("actie")
        if self._STAND_VAN_ACTIE.get(actie, actie) == self._STAND_VAN_ACTIE.get(oud_actie, oud_actie):
            return None
        reden = self._midkwartier_wissel_reden(now, plan, oud, oud_actie)
        # v5.187.0 (plantoets 7): alleen noteren voor de economische schaduw.
        self._schaduw_midkwartier(now, plan, oud, reden)
        plan["midkwartier"] = {
            "actie_plan": actie,
            "actie_dit_kwartier": oud_actie,
            "gewisseld": bool(reden),
            "reden": reden or "vastgehouden: alleen het vermogen bijstellen tot het kwartier om is",
        }
        self._tel_herplanning(now, "wissel_toegestaan" if reden else "wissel_tegengehouden",
                              plan.get("berekend_om"))
        return None if reden else oud

    def _midkwartier_wissel_reden(self, now: datetime, plan: dict, oud: dict, oud_actie) -> str | None:
        """Waarom midden in het kwartier tóch van stand wisselen, of None."""
        toestand = self._overschot_toestand()
        if oud_actie in ("verkopen", "huis") and self._waardeplan_accu_leeg(now):
            return "veiligheid: de accu is leeg"
        if oud_actie in ("laden_net", "zon", "zon_export", "houden") and toestand.get("accu_vol"):
            return "veiligheid: de accu is vol"
        overschot = toestand.get("overschot_w")
        if oud_actie == "zon_export" and overschot is not None and overschot <= 0:
            return "veiligheid: geen zonoverschot meer; terugleveren zou het huis uit het net voeden"
        voordeel = self._midkwartier_voordeel_eur(plan, oud)
        if voordeel is not None and voordeel >= WAARDEPLAN_MIDKWARTIER_WISSEL_EUR:
            return f"duidelijk beter: naar schatting € {voordeel:.2f} in de rest van het kwartier"
        return None

    @staticmethod
    def _midkwartier_voordeel_eur(plan: dict, oud: dict) -> float | None:
        """Grove schatting van wat de nieuwe stand in de rest van het kwartier
        scheelt: het verschil in accu-energie (nieuwe rij tegen het restant van
        de oude) maal het verschil tussen de prijs nu en de waarde van een kWh
        aan het eind van het plan. Zonder die twee: None (dan vasthouden)."""
        nieuw, vorig = plan.get("nu") or {}, oud.get("nu") or {}
        uren_n, uren_o = float(nieuw.get("uren") or 0.0), float(vorig.get("uren") or 0.0)
        prijs, waarde = nieuw.get("rekenprijs_eur"), plan.get("eindwaarde_eur_per_kwh")
        if uren_n <= 0 or uren_o <= 0 or prijs is None or waarde is None:
            return None
        rest_oud = float(vorig.get("accu_kwh") or 0.0) * min(1.0, uren_n / uren_o)
        verschil = abs(float(nieuw.get("accu_kwh") or 0.0) - rest_oud)
        return verschil * abs(float(prijs) - float(waarde))

    def _tel_herplanning(self, now: datetime, soort: str, sleutel=None) -> None:
        """Telt herplanningen per dag (v5.186.0, B11). Met `sleutel` hooguit
        één keer per plan (een vastgehouden wissel komt elke ronde langs)."""
        dag = dt_util.as_local(now).date().isoformat()
        teller = self.waardeplan_herplanningen
        if not isinstance(teller, dict) or teller.get("dag") != dag:
            teller = {"dag": dag, "midkwartier": 0, "wissel_tegengehouden": 0,
                      "wissel_toegestaan": 0, "zon_afwijking": 0, "_laatst": {}}
        if sleutel is not None:
            if teller["_laatst"].get(soort) == sleutel:
                self.waardeplan_herplanningen = teller
                return
            teller["_laatst"][soort] = sleutel
        teller[soort] = int(teller.get(soort) or 0) + 1
        self.waardeplan_herplanningen = teller

    def _zon_export_laadvermogen(self, now: datetime, gepland_w: float) -> float | None:
        """Het laadvermogen bij zon_export, elke ronde begrensd tot het echte
        zonoverschot (pv - huis) (v5.186.0, B12).

        Het plan sloeg een deel van de zon op met een vast vermogen. Kwam er
        een wolk, dan bleef de accu op dat vermogen laden - uit het net.
        Wijkt het overschot sterk af van het plan, dan eens per kwartier
        opnieuw plannen. Onder het minimale laadvermogen: None (alles terug,
        handmatig 0 W). Zonder meting: het geplande vermogen, zoals voorheen.
        """
        overschot = self._overschot_toestand().get("overschot_w")
        if overschot is None:
            return -round(gepland_w)
        if overschot < gepland_w * (1 - WAARDEPLAN_ZON_AFWIJKING_FRACTIE):
            kwartier = self._kwartier_sleutel(now)
            if self._zon_herplan_kwartier != kwartier:
                self._zon_herplan_kwartier = kwartier
                self._waardeplan_cache = None
                self._tel_herplanning(now, "zon_afwijking")
        toegestaan = min(gepland_w, max(0.0, float(overschot)))
        if toegestaan < WAARDEPLAN_MIN_LAAD_W - 1:
            return None
        return -round(toegestaan)

    def _waardeplan_opdracht(self, now: datetime, plan: dict, nu: dict) -> tuple:
        """(actie, laadvermogen, ontlaadvermogen) voor de planrij van nu (v5.177.0).

        Uit `_waardeplan_als_nodig` gehaald. Eén vermogensgrens met het plan
        (A12) en de duur van de rij in plaats van x 4000 (A4).
        """
        actie = nu.get("actie")
        charge_power = None
        discharge_power = None
        if actie == "laden_net":
            # v5.181.1 (punt 2): elke ronde de rest van het kwartier.
            vermogen = self._waardeplan_laadvermogen_nu_w(nu, plan, now)
            if vermogen < WAARDEPLAN_MIN_VERMOGEN_W:
                actie = "houden"
            else:
                charge_power = self._als_al_ingesteld(-round(vermogen))
        elif actie == "zon_export":
            # v5.177.0 (A11): een deel opslaan op een vast vermogen, de rest terug.
            vermogen = float(nu.get("kwh") or 0.0) * self._per_uur_w(nu)
            if vermogen >= WAARDEPLAN_MIN_LAAD_W - 1:
                ingesteld = abs(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER) or 0)
                # v5.186.0 (B12): niet meer dan het zonoverschot van nu.
                charge_power = self._zon_export_laadvermogen(now, min(ingesteld, vermogen))
        elif actie == "verkopen":
            actie, discharge_power = self._waardeplan_verkoop(now, plan, nu)
        return actie, charge_power, discharge_power

    def _waardeplan_verkoop(self, now: datetime, plan: dict, nu: dict) -> tuple:
        """Verkopen volgens het plan, boven de vloer die het plan zelf gebruikte.

        v5.177.0 (A1): de sturing toetste een verkoop opnieuw aan de oude
        verkoopreserve (`verkoopreserve`, het goedkope blok) en maakte er dan
        'huis' van, terwijl het plan al rekende met zijn eigen vloer per
        kwartier (`Kwartier.verkoop_vloer_kwh`). Nu alleen die vloer.
        """
        vloer = float(nu.get("verkoop_vloer_kwh") or 0.0)
        inhoud = self.beschikbare_energie_kwh()
        vrij = None if inhoud is None else max(0.0, inhoud - vloer)
        plan["verkoopreserve_kwh"] = round(vloer, 2)
        if not vrij or vrij <= 0.05:
            # Het huis gaat voor: niets verkopen onder de vloer van het plan.
            plan["verkoop_tegengehouden"] = (
                "accu-inhoud onbekend" if inhoud is None else "onder de verkoopreserve van het plan"
            )
            return "huis", None
        tekort = max(0.0, -float(nu.get("accu_kwh") or 0.0) - float(nu.get("kwh") or 0.0))
        verkoop = min(float(nu.get("kwh") or 0.0), vrij)
        vermogen = min(
            abs(self.instelling(CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER) or 0),
            (tekort + verkoop) * self._per_uur_w(nu),
        )
        if vermogen < WAARDEPLAN_MIN_VERMOGEN_W:
            return "huis", None
        return "verkopen", round(vermogen)

    def _noteer_waardeplan_beschikbaar(self, now: datetime, plan: dict) -> None:
        """Telt hoe vaak en sinds wanneer er geen waardeplan is (v5.177.0, A5).

        Zonder plan sturen de oude regels; dat stond alleen in een attribuut
        `reden`. Nu een teller per dag en, na WAARDEPLAN_WEG_AANDACHT_MINUTEN,
        een aandachtspunt (`_waardeplan_aandachtspunt`).
        """
        dag = dt_util.as_local(now).date().isoformat()
        teller = self.waardeplan_weg_teller
        if not isinstance(teller, dict) or teller.get("dag") != dag:
            teller = self.waardeplan_weg_teller = {"dag": dag, "rondes": 0, "laatste_reden": None}
        if plan.get("beschikbaar"):
            self._waardeplan_weg_sinds = None
            return
        teller["rondes"] = int(teller.get("rondes") or 0) + 1
        teller["laatste_reden"] = plan.get("reden")
        teller["laatst"] = now.isoformat()
        if self._waardeplan_weg_sinds is None:
            self._waardeplan_weg_sinds = now

    def _waardeplan_aandachtspunt(self, now: datetime | None = None) -> str | None:
        """Een aandachtspunt als het waardeplan al een tijd niet rekent (v5.177.0)."""
        sinds = self._waardeplan_weg_sinds
        if not WAARDEPLAN_STUURT or sinds is None:
            return None
        now = now or dt_util.now()
        minuten = (now - sinds).total_seconds() / 60
        if minuten < WAARDEPLAN_WEG_AANDACHT_MINUTEN:
            return None
        reden = (self.waardeplan_weg_teller or {}).get("laatste_reden") or "onbekend"
        return (
            f"Het waardeplan rekent al {minuten:.0f} minuten niet ({reden}); "
            "de oude regels sturen de accu zolang."
        )

    def _waardeplan_accu_leeg(self, now: datetime) -> bool:
        """Staat de accu leeg, met dezelfde maat als de tekortmeting? (v5.175.3)"""
        try:
            return self.accu_leeg(now)
        except Exception:  # noqa: BLE001 - bij twijfel de gewone naam
            return False

    # --- v5.177.0 (A7): één definitie van "leeg" ---------------------------
    #
    # Er waren er zes: TEKORT_LEEG_INHOUD_KWH (0,1), PLAN_SPAREN_LEEG_KWH (0,3),
    # EMERGENCY_LOW_BATTERY_KWH_THRESHOLD (0,3 op de ruwe sensor, zonder
    # modulecorrectie), ondergrens + 3 % in `accu_is_leeg`, en in de noodregel
    # de min-SoC in plaats van de effectieve ondergrens. v5.176.1 kwam
    # daaruit voort (plan "kump neet meer tekort", status "accu leeg"). Nu:
    # leeg = de gecorrigeerde bruikbare inhoud (boven de effectieve
    # ondergrens) tot en met TEKORT_LEEG_MARGE_PROCENT van de capaciteit;
    # zonder inhoud de laadstand tegen de effectieve ondergrens + die marge.

    def accu_leeg_grens_kwh(self, extra_procent: float = 0.0) -> float:
        """Tot en met deze inhoud (kWh boven de ondergrens) heet de accu leeg."""
        try:
            cap = self.bruikbare_capaciteit_kwh()
        except Exception:  # noqa: BLE001 - zonder capaciteit de vaste grens
            cap = None
        if not cap:
            return PLAN_SPAREN_LEEG_KWH + extra_procent / 100 * 8.64
        return cap * (TEKORT_LEEG_MARGE_PROCENT + extra_procent) / 100

    def accu_leeg_grens_plan_kwh(self) -> float:
        """De grens op de stap van het waardeplan (0,1 kWh, naar boven): 0,26
        kWh bij 8,64 kWh wordt 0,3 - de inhoud in het plan staat op stappen."""
        return math.ceil(self.accu_leeg_grens_kwh() / 0.1 - 1e-6) * 0.1

    def accu_leeg(self, now: datetime | None = None, extra_procent: float = 0.0) -> bool:
        """Staat de accu leeg? De ene definitie (v5.177.0, A7)."""
        now = now or dt_util.now()
        try:
            inhoud = self.beschikbare_energie_kwh()
        except Exception:  # noqa: BLE001 - zonder inhoud de laadstand
            inhoud = None
        return accu_is_leeg(
            self.accustand_procent(), inhoud,
            self.effectieve_ondergrens_procent(now) + TEKORT_LEEG_MARGE_PROCENT + extra_procent,
            self.accu_leeg_grens_kwh(extra_procent),
        )

    def _waarom_waardeplan(self) -> list[str]:
        """Waarom-regels bij het waardeplan (v5.158.0)."""
        p = self.last_waardeplan or {}
        nu = p.get("nu") or {}
        regels = []
        if nu.get("prijs_eur") is not None:
            regels.append(f"stroom kost dit kwartier {nu['prijs_eur'] * 100:.1f} ct")
        if p.get("inhoud_kwh") is not None:
            # v5.177.0 (A8): `bruikbaar_kwh` van het plan is de capaciteit
            # boven de ondergrens, niet wat erin zit. "er zit 0,7 kWh in de
            # accu (bruikbaar 7,8)" las als 7,8 kWh beschikbaar.
            ruimte = max(0.0, float(p.get("bruikbaar_kwh") or 0.0) - float(p["inhoud_kwh"]))
            regels.append(
                f"er zit {_nl(p['inhoud_kwh'])} kWh boven de ondergrens "
                f"(ruimte tot vol {_nl(ruimte)} kWh)"
            )
        # v5.172.0 (punt 4): zegt het als de accu eerder stopt dan de min-SoC.
        try:
            if zin := self.ondergrens_zin():
                regels.append(zin)
        except Exception:  # noqa: BLE001 - uitleg mag niets breken
            pass
        duurder = [
            r for r in (p.get("vooruit") or [])[1:]
            if r.get("actie") in ("huis", "verkopen")
        ]
        if duurder:
            regels.append(
                "de lading gaat naar: "
                + ", ".join(f"{str(r['begin'])[11:16]} ({r['prijs_eur'] * 100:.0f} ct)" for r in duurder[:4])
            )
        if p.get("besparing_plan_eur") is not None:
            regels.append(
                f"het plan scheelt over {p.get('kwartieren', 0) // 4} uur "
                f"EUR {p['besparing_plan_eur']:.2f} tegen geen accu"
            )
        if p.get("verkoop_tegengehouden"):
            regels.append("verkopen tegengehouden: " + p["verkoop_tegengehouden"])
        if (p.get("balanceren") or {}).get("reden"):
            regels.append("balanceerlading: " + p["balanceren"]["reden"])
        # v5.165.0: wanneer en hoeveel het plan uit het net laadt.
        if zin := self._waardeplan_lading_zin():
            regels.append(zin)
        # v5.168.0: zegt erbij als het plan met de marginale prijs rekent.
        if zin := self._saldering_uitlegzin():
            regels.append(zin)
        return regels or ["het waardeplan rekent elk kwartier de goedkoopste inzet uit"]

    # --- v5.165.0: de uitleg volgt het waardeplan ---------------------------
    #
    # Akkoord Ruud 02-11. De uitleg kwam nog uit de oude regels terwijl het
    # waardeplan stuurde: "laadblok 23:30" terwijl het plan om 23:45 laadde,
    # "bijladen uit het net loont niet" naast een geplande netlading, en
    # "wordt in het laadblok bijgeladen 5,58 kWh" terwijl het plan ~1,2 kWh
    # laadt. Zolang het waardeplan stuurt, komen tijden en hoeveelheden van
    # de volgende lading uit het plan.

    def _waardeplan_stuurt_nu(self) -> bool:
        """Stuurt het waardeplan deze ronde, met een plan? (v5.165.0)"""
        p = self.last_waardeplan or {}
        return bool(
            WAARDEPLAN_STUURT and p.get("beschikbaar")
            and str(self.last_reason or "").startswith("waardeplan_")
        )

    def _waardeplan_volgende_lading(self, now: datetime | None = None) -> dict | None:
        """De eerstvolgende lading uit het net volgens het waardeplan (v5.165.0).

        None als het waardeplan niet stuurt. {"geen": True, "uren": ...} als
        het plan over zijn horizon niet uit het net laadt. Anders het eerste
        aaneengesloten blok laadkwartieren: van, tot, kWh uit het net.
        """
        if not self._waardeplan_stuurt_nu():
            return None
        now = now or dt_util.now()
        rijen = getattr(self, "_waardeplan_rijen", None) or (self.last_waardeplan or {}).get("vooruit") or []
        kwartier = timedelta(minutes=15)
        blok: list = []
        tel = 0
        for r in rijen:
            begin = r.get("begin")
            if isinstance(begin, str):
                begin = dt_util.parse_datetime(begin)
            if begin is None or begin + kwartier <= now:
                continue
            tel += 1
            if r.get("actie") == "laden_net" and (not blok or begin == blok[-1][0] + kwartier):
                blok.append((begin, r))
            elif blok:
                break
        if not blok:
            return {"geen": True, "uren": tel / 4}
        return {
            "van": blok[0][0],
            "tot": blok[-1][0] + kwartier,
            "kwh": round(sum(float(r.get("kwh") or 0.0) for _b, r in blok), 2),
            "kwartieren": len(blok),
        }

    def _waardeplan_lading_zin(self, now: datetime | None = None) -> str | None:
        """De volgende netlading van het waardeplan als halve zin (v5.165.0)."""
        lading = self._waardeplan_volgende_lading(now)
        if lading is None:
            return None
        if lading.get("geen"):
            return f"het waardeplan laadt de komende {lading['uren']:.0f} uur niet uit het net"
        return (
            f"het waardeplan laadt {periode_met_dag(lading['van'], lading['tot'], now)} "
            f"{_nl(lading['kwh'])} kWh uit het net"
        )

    def _waardeplan_laadbesluit_stand(self) -> str | None:
        """De stand van het laadbesluit volgens het waardeplan (v5.165.0).

        Het oude laadbesluit draait niet meer zolang het waardeplan stuurt;
        zijn laatste stand bleef staan en gaf "bijladen uit het net loont
        niet" naast een geplande netlading. Een geplande (of al gedane)
        netlading is `loont`; een plan zonder netlading `loont_niet`, behalve
        als de zon de accu zou vullen (`zon` blijft staan). None = de oude
        regels.
        """
        lading = self._waardeplan_volgende_lading()
        if lading is None:
            return None
        if not lading.get("geen") or self._laadbesluit_stand == "loont":
            return "loont"
        return "zon" if self._laadbesluit_stand == "zon" else "loont_niet"

    def _waardeplan_gaat_sturen(self, now: datetime, entries) -> bool:
        """Stuurt het waardeplan deze ronde? (v5.177.0, A15) Het plan van dit
        kwartier (gecachet; `_waardeplan_als_nodig` gebruikt hetzelfde)."""
        if not WAARDEPLAN_STUURT:
            return False
        try:
            return bool(self._waardeplan_nu(now, entries).get("beschikbaar"))
        except Exception:  # noqa: BLE001 - bij twijfel de oude regels
            return False
