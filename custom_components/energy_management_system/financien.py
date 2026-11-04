"""Financien van de coordinator: besparing, tegenfeitelijke kosten, voorraad en kostprijs (B4.2).

De financiele boekhouding (`_update_financial_tracking` en helpers), de
besparing tegen het tegenfeitelijke scenario, de voorraad- en
boekwaardecorrectie, het kostprijsmodel van de accu en de maandovergang.
Ongewijzigd verhuisd uit `coordinator.py`; de coordinator erft deze mixin.
"""
from __future__ import annotations

import math
from datetime import datetime
from homeassistant.util import dt as dt_util
from .const import (
    ACCU_AC_MIN_RENDEMENT,
    ACCU_SLUIMER_GRENS_W,
    ACCU_STAP_ZONDER_STROOM_FRACTIE,
    ACCU_STAP_ZONDER_STROOM_MAX_KWH,
    BESPARING_VERGELIJK_DAGEN,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_INVERT_BATTERY_POWER_SIGN,
    CONF_PV_POWER_SENSOR,
    FEEDIN_PREMIUM_EUR_PER_KWH,
    MIN_COST_BASIS_DELTA_KWH,
)
from .coordinator_hulp import PriceEntry


class FinancienMixin:
    """De financiele methodes van de coordinator."""

    def get_savings_correction(self) -> dict:
        """De besparing van vandaag, gecorrigeerd voor wat er nog in de
        accu zit (v1.52.0).

        Gevonden in de export van 19:40: de besparing stond op **-0,37
        euro**, alsof de aansturing slechter is dan niets doen. Maar de
        accu stond op 98% en had de zon van vanmiddag nog in huis.

        De vergelijking rekent per tick af tegen de netstroom. Laden is
        op dat moment een KOST - die kWh had ook teruggeleverd kunnen
        worden - en de opbrengst volgt pas bij het ontladen. Een dag
        afsluiten met een volle accu tegen een dag die leeg eindigt is
        dus geen eerlijke vergelijking.

        De correctie waardeert het verschil in accu-inhoud tegen wat een
        kWh op dit moment waard is. Bewust NAAST het rauwe cijfer, niet
        eroverheen: het rauwe cijfer is wat er werkelijk is afgerekend,
        de correctie is een schatting van wat er nog komt.
        """
        begin = self._savings_day_start_available_kwh
        # v5.172.0 (punt 3): de gemeten inhoud (gedempt), niet de inhoud voor
        # de sturing - zie `voorraad_inhoud_kwh`.
        nu = self.voorraad_inhoud_kwh()
        rauw = self.counterfactual_cost_today_eur - self.actual_cost_today_eur
        if begin is None or nu is None:
            # v5.118.0: valt de accustand even weg (Zendure-time-out, de
            # daggrens), dan de laatste correctie van dezelfde dag. Anders
            # sloot de dag af zonder voorraadcorrectie terwijl de dagsensor
            # hem wel liet zien, en liepen dagsensor en dagmeter uiteen.
            bewaard = self._laatste_voorraadcorrectie
            if bewaard and begin is not None and bewaard[0] == getattr(self, "_counterfactual_day_key", None):
                return {
                    **bewaard[1],
                    "besparing_vandaag_eur": round(rauw, 2),
                    "besparing_gecorrigeerd_eur": round(rauw + bewaard[1]["voorraadwaarde_exact_eur"], 2),
                    "uit_laatste_meting": True,
                }
            return {
                "besparing_vandaag_eur": round(rauw, 2),
                "correctie_beschikbaar": False,
                "reden": "De accustand bij het begin van de dag is niet bekend.",
            }

        verschil_kwh = nu - begin
        waarde, waarde_bron = self._voorraad_kwh_waarde()
        if waarde is None:
            return {
                "besparing_vandaag_eur": round(rauw, 2),
                "correctie_beschikbaar": False,
                "reden": "Geen kostprijs of terugleverwaarde bekend om de voorraad te waarderen.",
            }

        # v5.172.0 (punt 3): de verandering van de BOEKWAARDE van de voorraad
        # (inhoud x laadprijs, eind min begin), niet het inhoudsverschil
        # tegen de prijs van vandaag. Dan sluiten de dagen op elkaar aan: 7
        # dagen opgeteld = de 7 dagen in één keer, en het is hetzelfde begrip
        # als het kostprijsmodel (gerealiseerd = stromen + verandering van de
        # boekwaarde). Zonder bewaarde beginwaarde: zoals voorheen.
        boekwaarde_nu = nu * waarde
        boekwaarde_begin = self._savings_day_start_stock_eur
        if not isinstance(boekwaarde_begin, (int, float)):
            boekwaarde_begin = begin * waarde
        correctie = boekwaarde_nu - boekwaarde_begin
        uit = {
            "besparing_vandaag_eur": round(rauw, 2),
            "correctie_beschikbaar": True,
            "accu_bij_dagbegin_kwh": round(begin, 2),
            "accu_nu_kwh": round(nu, 2),
            "voorraadverschil_kwh": round(verschil_kwh, 2),
            # v5.116.0: ongerond, voor het oplopende totaal (dagafsluiting)
            "voorraadwaarde_exact_eur": correctie,
            "voorraadwaarde_eur": round(correctie, 2),
            "kwh_waarde_eur": round(waarde, 4),
            "kwh_waarde_bron": waarde_bron,
            "besparing_gecorrigeerd_eur": round(rauw + correctie, 2),
            "boekwaarde_begin_eur": round(boekwaarde_begin, 4),
            "boekwaarde_nu_eur": round(boekwaarde_nu, 4),
            "inhoud_bron": "gemeten inhoud (gedempt), zonder modulesprong of ondergrens",
            "toelichting": (
                "Laden telt op het moment zelf als kosten; de opbrengst volgt "
                "pas bij het ontladen. Staat de accu aan het eind van de dag "
                "voller dan aan het begin, dan is die energie nog niet "
                "verzilverd - en dat scheelt in het dagcijfer."
            ),
        }
        self._laatste_voorraadcorrectie = (getattr(self, "_counterfactual_day_key", None), dict(uit))
        return uit

    #: v5.118.0: (dag, correctie) van de laatste geslaagde berekening.
    _laatste_voorraadcorrectie: tuple | None = None
    # v5.181.1 (punt 3): de laatste lading gesplitst in zon en net.
    last_laadsplitsing: dict | None = None

    def _voorraad_kwh_waarde(self) -> tuple[float | None, str | None]:
        """Waarde per opgeslagen kWh voor de voorraadcorrectie (v5.116.0).

        Gemeten 21-10 (Plan tegen werkelijkheid): eigen berekening onder
        salderen € 0,35 (ontlading - lading tegen de kwartierprijs, min de
        daling van de accu-inhoud 60 -> 21 % tegen de gemeten laadprijs),
        de dagsensor € 0,06 en de dagmeter € 1,56. De dagsensor waardeerde
        de voorraad tegen de prijs van het moment (om 07:45 de ochtendpiek,
        37 ct), dus schommelde hij met de prijs; de meter rekende de
        voorraad helemaal niet mee.

        Nu: wat de energie in de accu werkelijk kostte om erin te krijgen
        (nacalculatie eerst erin, eerst eruit, `accukosten.py`). Is die er
        niet (te weinig dagverloop), dan de kostprijs van het
        kostprijsmodel, en pas daarna de terugleverwaarde van nu.
        """
        try:
            kostprijs = (self.get_accukosten().get("voorraad_kostprijs") or {}).get("eur_per_kwh")
        except Exception:  # noqa: BLE001 - een rapportagegetal mag niets breken
            kostprijs = None
        if isinstance(kostprijs, (int, float)) and kostprijs > 0:
            return float(kostprijs), "gemeten laadprijs van de voorraad"
        basis = self.battery_cost_basis_eur_per_kwh
        if isinstance(basis, (int, float)) and basis > 0:
            return float(basis), "kostprijsmodel"
        nu = self.current_feedin_value_eur_per_kwh
        if nu is not None:
            return float(nu), "terugleverwaarde nu"
        return None, None

    #: v5.116.0: de voorraadcorrecties van afgesloten dagen, opgeteld (bewaard).
    besparing_voorraadcorrectie_totaal_eur: float = 0.0

    # --- v5.172.0 punt 3: de besparingscijfers naast elkaar ------------------
    #
    # De analyse van 03-11 zag over 27-10 t/m 02-11 drie getallen: de sensor
    # EUR 0,89, het kostprijsmodel EUR 1,51 en een eigen berekening EUR 1,99,
    # met als vermoeden het sluimerverbruik. Gemeten: de HomeWizard-meter van
    # de accu staat bij stilstand op ~0 W (5-min-gemiddelden 0-0,009 W), dus
    # er is vrijwel geen sluimer om af te trekken. Het verschil kwam uit de
    # voorraad: de sensor waardeerde de inhoud met de modulesprong eraf (02-11
    # eindigde op 15-16 % = 0,58-0,69 kWh gemeten, geteld als 0,02 kWh) en
    # tegen de prijs van elke dag apart, waardoor dagen niet op elkaar
    # aansloten. Nu: gemeten inhoud, boekwaarde eind min begin, en per dag de
    # drie cijfers vastgelegd met wat ze wel en niet bevatten.

    #: Bewaard: boekwaarde van de voorraad (EUR) bij het dagbegin.
    _savings_day_start_stock_eur: float | None = None
    #: Bewaard: de stand van het kostprijsmodel bij het dagbegin.
    _kostprijs_dagbegin_eur: float | None = None
    #: Bewaard: {"kwh": .., "eur": ..} sluimer van vandaag.
    sluimer_vandaag: dict | None = None
    #: Bewaard: de afgesloten dagen (laatste 14).
    besparing_dagen: list | None = None

    def _begin_besparingsdag(self, afsluiting: dict | None) -> None:
        """Inhoud, boekwaarde en kostprijsstand bij het dagbegin (v5.172.0)."""
        self._savings_day_start_available_kwh = self.voorraad_inhoud_kwh()
        boek = (afsluiting or {}).get("boekwaarde_nu_eur")
        if not isinstance(boek, (int, float)):
            waarde, _bron = self._voorraad_kwh_waarde()
            inhoud = self._savings_day_start_available_kwh
            boek = inhoud * waarde if inhoud is not None and waarde is not None else None
        self._savings_day_start_stock_eur = boek
        self._kostprijs_dagbegin_eur = float(self.total_battery_savings_eur or 0.0)
        self.sluimer_vandaag = {"kwh": 0.0, "eur": 0.0}

    def _tel_sluimer(self, accu_w: float, uren: float, prijs: float) -> None:
        """Stilstand die stroom van het net neemt (laadrichting, < 50 W)."""
        if accu_w >= 0 or -accu_w >= ACCU_SLUIMER_GRENS_W or uren <= 0:
            return
        st = dict(self.sluimer_vandaag or {"kwh": 0.0, "eur": 0.0})
        kwh = -accu_w / 1000 * uren
        st["kwh"] = st.get("kwh", 0.0) + kwh
        st["eur"] = st.get("eur", 0.0) + kwh * prijs
        self.sluimer_vandaag = st

    def _sluit_besparingsdag(self, dag, afsluiting: dict | None) -> None:
        """Legt de besparingscijfers van een afgesloten dag vast (v5.172.0)."""
        afsluiting = afsluiting or {}
        rauw = self.counterfactual_cost_today_eur - self.actual_cost_today_eur
        begin = self._kostprijs_dagbegin_eur
        sluimer = self.sluimer_vandaag or {}
        regel = {
            "datum": dag.isoformat() if hasattr(dag, "isoformat") else str(dag),
            "hoofdgetal_eur": round(rauw + (afsluiting.get("voorraadwaarde_exact_eur") or 0.0), 4),
            "rauw_eur": round(rauw, 4),
            "voorraad_eur": round(afsluiting.get("voorraadwaarde_exact_eur") or 0.0, 4),
            "voorraad_volledig": bool(afsluiting.get("correctie_beschikbaar")),
            "kostprijsmodel_eur": (
                round(float(self.total_battery_savings_eur or 0.0) - begin, 4)
                if isinstance(begin, (int, float)) else None
            ),
            "sluimer_kwh": round(float(sluimer.get("kwh") or 0.0), 3),
            "sluimer_eur": round(float(sluimer.get("eur") or 0.0), 4),
        }
        dagen = [d for d in (self.besparing_dagen or []) if d.get("datum") != regel["datum"]]
        self.besparing_dagen = (dagen + [regel])[-14:]

    def besparing_vergelijking(self, dagen: int = BESPARING_VERGELIJK_DAGEN) -> dict:
        """De besparingscijfers van de laatste afgesloten dagen naast elkaar (v5.172.0).

        - hoofdgetal: de hele rekening tegen een huis zonder accu, met de
          verandering van de boekwaarde van de voorraad; bevat het
          sluimeren (dat staat in de netmeting), niet de slijtage.
        - kostprijsmodel: per inhoudsverandering opbrengst min kostprijs;
          ziet sluimeren niet (geen inhoudsverandering), ook geen slijtage.
        - hoofdgetal zonder sluimer: het hoofdgetal plus wat de stilstaande
          accu van het net nam; dat meet hetzelfde als het kostprijsmodel.
        """
        regels = [d for d in (self.besparing_dagen or []) if isinstance(d, dict)][-dagen:]
        if not regels:
            return {"beschikbaar": False, "reden": "nog geen afgesloten dag sinds v5.172.0"}

        def som(veld):
            waarden = [d.get(veld) for d in regels if isinstance(d.get(veld), (int, float))]
            return round(sum(waarden), 2) if waarden else None

        hoofd, kost, sluimer = som("hoofdgetal_eur"), som("kostprijsmodel_eur"), som("sluimer_eur")
        zonder = None if hoofd is None else round(hoofd + (sluimer or 0.0), 2)
        return {
            "beschikbaar": True,
            "van": regels[0]["datum"],
            "tot": regels[-1]["datum"],
            "dagen": len(regels),
            "hoofdgetal_incl_sluimer_eur": hoofd,
            "sluimer_eur": sluimer,
            "sluimer_kwh": som("sluimer_kwh"),
            "hoofdgetal_excl_sluimer_eur": zonder,
            "kostprijsmodel_excl_sluimer_excl_slijtage_eur": kost,
            "verschil_met_kostprijsmodel_eur": (
                None if zonder is None or kost is None else round(zonder - kost, 2)
            ),
            "dagen_zonder_volledige_voorraad": sum(1 for d in regels if not d.get("voorraad_volledig")),
            "betekenis": (
                "Hoofdgetal: rekening tegen geen accu + verandering boekwaarde voorraad "
                "(gemeten inhoud x laadprijs), incl. sluimer, excl. slijtage. "
                "Kostprijsmodel: opbrengst min kostprijs per ontlading, excl. sluimer, "
                "excl. slijtage. Hoofdgetal excl. sluimer hoort gelijk te zijn aan het "
                "kostprijsmodel; het restverschil is de splitsing zon/net bij het laden "
                "en de stappen die het kostprijsmodel als meetruis overslaat."
            ),
            "per_dag": regels,
        }

    def besparing_totaal_gecorrigeerd_eur(self) -> float:
        """Oplopende besparing t.o.v. zonder sturing, met de accu-inhoud (v5.116.0).

        Het rauwe totaal plus de voorraadcorrectie van elke afgesloten dag en
        die van vandaag. De meters "EMS Accubesparing - vandaag/deze maand"
        lezen dit totaal; hun dagwaarde is dan gelijk aan de gecorrigeerde
        dagbesparing en schommelt niet meer met de laadstand.
        """
        rauw = (self.counterfactual_cost_all_time_eur or 0.0) - (self.actual_cost_all_time_eur or 0.0)
        totaal = rauw + (self.besparing_voorraadcorrectie_totaal_eur or 0.0)
        corr = self.get_savings_correction() or {}
        if corr.get("correctie_beschikbaar"):
            totaal += corr.get("voorraadwaarde_exact_eur") or 0.0
        return totaal

    #: v5.128.0: de maandteller van de besparing (bewaard): maand, beginstand
    #: van het totaal, laatste totaal en de waarde. Zie `_werk_besparing_maand_bij`.
    besparing_maand: dict | None = None

    def _werk_besparing_maand_bij(self, now: datetime) -> None:
        """"Besparing deze maand": het totaal min de stand op de 1e, 00:00 (v5.128.0).

        Gevraagd 26-10 (punt 4): de meter `sensor.ems_accubesparing_deze_maand`
        (utility meter, net_consumption) boekte na elke herstart een
        verkeerde sprong. Deze teller rekent zelf:

            waarde = totaal (gecorrigeerd) - beginstand van de maand

        De beginstand wordt bewaard. Bij de maandwissel is dat het laatste
        totaal van de vorige maand: zolang Home Assistant uit staat, telt
        het totaal ook niet op, dus dat is de stand op de 1e om 00:00
        (lokale tijd). Vóór de eerste ronde of als het totaal niet te
        berekenen is, verandert er niets - de vorige waarde blijft staan.

        Eerste keer zonder bewaarde beginstand: het rauwe totaal min de
        rauwe maandteller (beide bewaard sinds v1.x): dat is het totaal aan
        het begin van de maand, met de voorraadcorrectie (sinds v5.116.0,
        22-10) volledig in deze maand.
        """
        if getattr(self, "_wacht_op_eerste_ronde", False):
            return
        try:
            totaal = float(self.besparing_totaal_gecorrigeerd_eur())
        except Exception:  # noqa: BLE001 - een rapportagegetal mag niets breken
            return
        if not math.isfinite(totaal):
            return
        lokaal = dt_util.as_local(now)
        maand = f"{lokaal:%Y-%m}"
        oud = self.besparing_maand if isinstance(self.besparing_maand, dict) else {}
        begin = oud.get("begin_eur")
        bron = oud.get("bron")
        if not isinstance(begin, (int, float)):
            rauw = (self.counterfactual_cost_all_time_eur or 0.0) - (
                self.actual_cost_all_time_eur or 0.0
            )
            rauw_maand = 0.0
            if self._counterfactual_month_key == lokaal.year * 100 + lokaal.month:
                rauw_maand = (self.counterfactual_cost_current_month_eur or 0.0) - (
                    self.actual_cost_current_month_eur or 0.0
                )
            begin = rauw - rauw_maand
            bron = "reconstructie: rauw totaal min rauwe maandteller"
        elif oud.get("maand") != maand:
            vorig = oud.get("laatste_totaal_eur")
            begin = float(vorig) if isinstance(vorig, (int, float)) else totaal
            bron = f"laatste totaal van {oud.get('maand')}"
        self.besparing_maand = {
            "maand": maand,
            "begin_eur": round(float(begin), 4),
            "laatste_totaal_eur": round(totaal, 4),
            "waarde_eur": round(totaal - float(begin), 2),
            "bron": bron,
            "bijgewerkt": now.isoformat(),
        }

    def besparing_deze_maand_eur(self) -> float | None:
        """De laatst berekende maandbesparing (v5.128.0); None = nog nooit berekend."""
        info = self.besparing_maand if isinstance(self.besparing_maand, dict) else {}
        waarde = info.get("waarde_eur")
        return float(waarde) if isinstance(waarde, (int, float)) else None

    def _split_charge_pv_vs_grid(
        self, charged_kwh: float, elapsed_hours: float
    ) -> tuple[float, float]:
        """Splitst een lading in (pv_overschot_kwh, net_kwh) - v0.63.117.

        Spiegelbeeld van `_split_discharge_export_vs_load`, en het
        ontbrekende stuk waardoor de besparing tot nu toe systematisch
        werd overschat: PV-overschot dat in de accu gaat, zou anders
        zijn teruggeleverd. Die gederfde teruglevering (inclusief de
        premie) is de werkelijke kostprijs van die kWh - niet de kale
        inkoopprijs.

        PV-overschot = opwek minus huisverbruik, begrensd op wat er
        werkelijk geladen is. Zonder PV-sensor óf zonder verbruikssensor
        is dat onderscheid niet te maken; dan wordt alles als
        net-inkoop geteld. Dat is hier de conservatieve kant: het houdt
        de kostprijs op de (hogere) inkoopprijs en overschat de
        besparing dus niet.
        """
        if charged_kwh <= 0 or elapsed_hours <= 0:
            return 0.0, max(0.0, charged_kwh)
        pv_entity = self.config.get(CONF_PV_POWER_SENSOR)
        if not pv_entity:
            return 0.0, charged_kwh
        pv_power_w = self._read_sensor_float(pv_entity)
        household_load_w = self._read_corrected_consumption_power()
        if pv_power_w is None or household_load_w is None:
            return 0.0, charged_kwh
        surplus_kw = max(0.0, (pv_power_w - household_load_w) / 1000)
        pv_kwh = min(charged_kwh, surplus_kw * elapsed_hours)
        return pv_kwh, charged_kwh - pv_kwh

    @staticmethod
    def _grid_flow_cost_eur(
        power_w: float,
        elapsed_hours: float,
        import_price_eur_per_kwh: float,
        feedin_value_eur_per_kwh: float,
    ) -> float:
        """Kosten (positief) of opbrengst (negatief) van een netstroom
        over dit interval, met APARTE tarieven voor inkoop en
        teruglevering (v0.63.117).

        Positief vermogen = import (kost de inkoopprijs), negatief =
        export (levert de terugleverwaarde op). Onder saldering zijn
        die twee vrijwel gelijk; daarna niet meer, en dan is één tarief
        voor beide richtingen niet houdbaar.
        """
        kwh = (power_w / 1000) * elapsed_hours
        if kwh >= 0:
            return kwh * import_price_eur_per_kwh
        return kwh * feedin_value_eur_per_kwh

    def _update_counterfactual_savings(
        self, now: datetime, entries: list[PriceEntry] | None = None
    ) -> None:
        """Tegenfeitelijke besparingsvergelijking (v0.63.101, gevraagd:
        "als je dit systeem niet had, had je deze maand €X betaald; nu
        betaalde je €Y").

        Reconstrueert per tick wat de netmeter zou hebben getoond
        ZONDER de accu erbij (dezelfde PV-opbrengst als nu, maar geen
        accu-sturing) - `p1_power + battery_power`, zelfde teken-
        conventie als `_read_corrected_consumption_power`. Rekent
        zowel de werkelijke als de tegenfeitelijke netstroom af tegen
        dezelfde, actuele dynamische prijs, en houdt het cumulatieve
        verschil bij op drie niveaus (vandaag, deze maand, all-time).

        Bewust een specifieke tegenfeitelijke situatie ("zelfde PV,
        geen accu-sturing") in plaats van een vage "gemiddelde
        besparing t.o.v. een vast tarief" - dat laatste zou een aparte,
        losse aanname over een vast tarief vereisen die niet uit
        bestaande sensoren is af te leiden. Puur informatief, stuurt
        niets aan.
        """
        p1_entity = self.config.get(CONF_CONSUMPTION_POWER_SENSOR)
        if not p1_entity:
            return
        p1_power_w = self._read_sensor_float(p1_entity)
        if p1_power_w is None:
            return
        price_per_kwh = self.huidige_prijs_eur_per_kwh()
        if price_per_kwh is None:
            return

        battery_power_w = 0.0
        battery_entity = self.config.get(CONF_BATTERY_POWER_SENSOR)
        if battery_entity:
            raw_battery = self._read_sensor_float(battery_entity)
            if raw_battery is not None:
                battery_power_w = raw_battery
                if self.config.get(CONF_INVERT_BATTERY_POWER_SIGN, False):
                    battery_power_w = -battery_power_w

        counterfactual_power_w = p1_power_w + battery_power_w

        today_key = now.date()
        if self._counterfactual_day_key != today_key:
            # v5.116.0: de voorraadcorrectie van de dag die afloopt blijft in
            # het oplopende totaal (vóór het nieuwe dagbegin). Geen vorige
            # dag (eerste start): niets af te sluiten.
            afsluiting = None
            if self._counterfactual_day_key is not None:
                afsluiting = self.get_savings_correction() or {}
                if afsluiting.get("correctie_beschikbaar"):
                    self.besparing_voorraadcorrectie_totaal_eur = (
                        self.besparing_voorraadcorrectie_totaal_eur or 0.0
                    ) + (afsluiting.get("voorraadwaarde_exact_eur") or 0.0)
                # v5.172.0 (punt 3): de drie besparingscijfers van die dag.
                self._sluit_besparingsdag(self._counterfactual_day_key, afsluiting)
            self._counterfactual_day_key = today_key
            self.actual_cost_today_eur = 0.0
            self.counterfactual_cost_today_eur = 0.0
            # v1.52.0: onthouden hoe vol de accu was toen de dag begon.
            #
            # Gevonden in de export van 19:40: de besparing van vandaag
            # stond op -0,37 euro, alsof de aansturing slechter is dan
            # niets doen. Dat klopt niet - de accu stond op 98% en had
            # de opbrengst van vanmiddag nog in huis.
            #
            # De vergelijking rekent per tick af tegen de netstroom, en
            # laden is op dat moment een KOST (die kWh had ook
            # teruggeleverd kunnen worden). De opbrengst volgt pas
            # vanavond bij het ontladen. Een dag afsluiten met een volle
            # accu tegen een dag die leeg eindigt is dus geen eerlijke
            # vergelijking - dezelfde soort fout als het meten over een
            # horizon die niet aansluit.
            self._begin_besparingsdag(afsluiting)
        elif self._savings_day_start_available_kwh is None and now.hour == 0:
            # v5.40: was de accustand er bij de daggrens even niet, dan de
            # eerste meting in het eerste uur - anders bleef de correctie de
            # hele dag uit. Later op de dag niet: dan is het geen dagbegin.
            self._begin_besparingsdag(None)

        month_key = now.year * 100 + now.month
        if self._counterfactual_month_key is None:
            self._counterfactual_month_key = month_key
        elif month_key != self._counterfactual_month_key:
            self.actual_cost_current_month_eur = 0.0
            self.counterfactual_cost_current_month_eur = 0.0
            self._counterfactual_month_key = month_key

        if self._counterfactual_last_sample is None:
            self._counterfactual_last_sample = now
            return
        elapsed_hours = max(
            (now - self._counterfactual_last_sample).total_seconds() / 3600, 0
        )
        self._counterfactual_last_sample = now
        if elapsed_hours <= 0 or elapsed_hours > 1:
            # Grote hiaat (bijv. na een herstart) - niet met een
            # verouderd vermogen een uur lang doorrekenen.
            return

        # v0.63.117: import en export worden niet langer tegen dezelfde
        # prijs afgerekend. Onder saldering zijn ze (op de premie na)
        # wél gelijk, dus verandert er nu praktisch niets; na saldering
        # levert een teruggeleverde kWh veel minder op dan een
        # ingekochte kWh kost, en zou één tarief voor beide de
        # vergelijking fors scheeftrekken - juist in het voordeel van
        # "geen accu", omdat het tegenfeitelijke scenario per definitie
        # méér exporteert.
        feedin_value = self._get_feedin_value_per_kwh(entries or [], now)
        if feedin_value is None:
            feedin_value = price_per_kwh

        actual_cost_eur = self._grid_flow_cost_eur(
            p1_power_w, elapsed_hours, price_per_kwh, feedin_value
        )
        counterfactual_cost_eur = self._grid_flow_cost_eur(
            counterfactual_power_w, elapsed_hours, price_per_kwh, feedin_value
        )

        self.actual_cost_today_eur += actual_cost_eur
        self.counterfactual_cost_today_eur += counterfactual_cost_eur
        self.actual_cost_current_month_eur += actual_cost_eur
        self.counterfactual_cost_current_month_eur += counterfactual_cost_eur
        self.actual_cost_all_time_eur += actual_cost_eur
        self.counterfactual_cost_all_time_eur += counterfactual_cost_eur
        # v5.172.0 (punt 3): wat de stilstaande accu zelf van het net neemt.
        self._tel_sluimer(battery_power_w, elapsed_hours, price_per_kwh)

    def _check_monthly_rollover(self, now: datetime) -> None:
        """Detect a new calendar month starting, snapshotting the current
        month's totals into "previous month" before resetting - this is
        what makes a genuine month-over-month trend comparison possible,
        on top of the existing rolling 7-day self-correction (shortfall/
        excess margin, PV bias) which only ever looks at the recent
        past, not whether things are improving release over release.
        """
        month_key = now.year * 100 + now.month
        if self._summary_month_key is None:
            self._summary_month_key = month_key
            return
        if month_key == self._summary_month_key:
            return

        self.previous_month_discharge_value_eur = round(
            self.current_month_discharge_value_eur, 2
        )
        self.previous_month_charge_cost_eur = round(
            self.current_month_charge_cost_eur, 2
        )
        self.previous_month_shortfall_days = self.current_month_shortfall_days
        self.previous_month_excess_days = self.current_month_excess_days
        self.previous_month_days_tracked = self.current_month_days_tracked

        self.current_month_discharge_value_eur = 0.0
        self.current_month_charge_cost_eur = 0.0
        self.current_month_shortfall_days = 0
        self.current_month_excess_days = 0
        self.current_month_days_tracked = 0
        self._summary_month_key = month_key

    def _update_financial_tracking(
        self,
        now: datetime,
        entries: list[PriceEntry],
        reason: str,
        discharge_power_w: float | None,
        charge_power_w: float | None,
    ) -> None:
        """Accumulate the euro value of the two actions with a clean,
        defensible calculation: energy moved x price at that exact moment.

        Deliberately does NOT attempt a "total savings" figure, since that
        would require a counterfactual (what would have happened without
        this integration) that can't be honestly verified. This only
        tracks the direct monetary value of energy discharged during
        expensive quarters, and the direct cost of energy force-charged
        from the grid during a low-solar cheap block.

        v0.63.25: the discharge value now also includes the Zonneplan
        feed-in premium (`FEEDIN_PREMIUM_EUR_PER_KWH`) for whatever
        portion of the discharge is genuine net export - same
        export-vs-covers-load split as
        `_update_battery_cost_basis_and_savings`, kept consistent so
        this sensor's "directe waarde" claim is actually accurate, not
        just an approximation that ignores the premium entirely.
        """
        elapsed_hours = 0.0
        if self._last_value_calc_time is not None:
            elapsed_hours = max(
                (now - self._last_value_calc_time).total_seconds() / 3600, 0
            )
        self._last_value_calc_time = now

        if elapsed_hours <= 0:
            return

        current_price = self._get_current_price_per_kwh(entries, now)
        if current_price is None:
            return

        if reason in ("expensive_quarter", "expensive_quarter_peak", "waardeplan_verkopen") and discharge_power_w:
            # v5.177.0 (A6): het gemeten vermogen, niet de opdracht.
            energy_kwh = (self._gemeten_accu_w(discharge_power_w, 1) / 1000) * elapsed_hours

            export_kwh, load_kwh = self._split_discharge_export_vs_load(
                energy_kwh, elapsed_hours
            )
            # v0.63.117: het geëxporteerde deel wordt gewaardeerd tegen
            # de werkelijke terugleverwaarde (onder saldering de
            # inkoopprijs plus premie; daarna het lage teruglevertarief),
            # het huisverbruik-deel tegen de vermeden inkoopprijs.
            feedin_value = self._get_feedin_value_per_kwh(entries, now)
            if feedin_value is None:
                export_kwh, load_kwh = 0.0, energy_kwh
                feedin_value = current_price

            feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
            value_eur = load_kwh * current_price + export_kwh * feedin_value
            self.total_discharge_value_eur += value_eur
            self.current_month_discharge_value_eur += value_eur
            self.total_feedin_premium_eur += feedin_premium_eur
        elif (
            reason
            in (
                "grid_charging_low_solar",
                "grid_charging_low_solar_extra_dip",
                "grid_charging_profitable",
                "grid_charging_dip",
                "emergency_low_battery",
                "celbescherming_laden",
                "waardeplan_laden",
            )
            and charge_power_w
        ):
            energy_kwh = (self._gemeten_accu_w(abs(charge_power_w), -1) / 1000) * elapsed_hours
            # v5.181.1 (punt 3): alleen het deel boven het zonoverschot is
            # netladen. Live 04-11 10:30: plan 'laden_net' terwijl de zon
            # 1,48 kW leverde en de P1 119 W terugleverde - de accu laadde
            # dus uit de zon, op een vast vermogen. Dat telde volledig als
            # netinkoop tegen de inkoopprijs.
            zon_kwh, net_kwh = self._split_charge_pv_vs_grid(energy_kwh, elapsed_hours)
            self.last_laadsplitsing = {
                "zon_kwh": round(zon_kwh, 4),
                "net_kwh": round(net_kwh, 4),
                "moment": now.isoformat(),
            }
            cost_eur = net_kwh * current_price
            self.total_charge_cost_eur += cost_eur
            self.current_month_charge_cost_eur += cost_eur

    def _gemeten_accu_w(self, opdracht_w: float, richting: int) -> float:
        """Het gemeten accuvermogen in de richting van de opdracht (W, >= 0).

        v5.177.0 (A6): de waarde van ontladen en de kosten van laden telden
        opdracht x tijd. De opdracht is niet wat de accu doet (begrensd, vol,
        leeg, de eerste seconden na een wissel); nu het gecorrigeerde gemeten
        vermogen, zoals de kostprijs. Zonder meting de opdracht.
        `richting` 1 = ontladen, -1 = laden.
        """
        try:
            gemeten = self._read_corrected_battery_power()
        except Exception:  # noqa: BLE001 - zonder meting de opdracht
            gemeten = None
        if gemeten is None:
            return abs(opdracht_w)
        return max(0.0, float(gemeten) * richting)

    def _update_battery_cost_basis_and_savings(
        self, now: datetime, entries: list[PriceEntry]
    ) -> None:
        """Track a weighted-average EUR/kWh cost basis for whatever
        energy currently sits in the battery, and realise savings/
        earnings whenever that energy leaves - regardless of *why* it
        left (an explicit sell during expensive_quarter, or simply
        covering household load to avoid an import during smart/
        smart_discharging/emergency_low_battery/etc).

        Unlike `_update_financial_tracking` above (which deliberately
        avoids a "total savings" figure, since that needs an unverifiable
        counterfactual), this IS defensible: it only uses prices this
        integration actually observed at the exact moments energy
        entered and left the battery - not a hypothetical "what if there
        were no battery" scenario. reported: "wat bespaart de batterij" -
        both buy-low-sell-high arbitrage AND PV self-consumption should
        count, using one unified mechanism rather than two.

        v0.63.25: on the discharge side, splits out how much of the
        discharge was genuine net export to the grid (vs. just covering
        household load) - confirmed via web search that Zonneplan pays a
        fixed EUR/kWh feed-in premium (`FEEDIN_PREMIUM_EUR_PER_KWH`) on
        top of the market price for every kWh actually fed back,
        including from a battery (only the separate 10% "Zonnebonus"
        excludes battery-sourced feed-in, which this integration never
        claims anyway). Covering household load isn't feed-in at all, so
        gets no premium - only the value of the avoided import.

        v0.63.117 - TWEE wijzigingen, want deze docstring beschreef tot
        nu toe twee aannames die niet (meer) houdbaar zijn:

        1. **De laadkant is nu symmetrisch.** Tot v0.63.116 werd ELKE
           geladen kWh tegen de kale inkoopprijs geboekt, ook als het
           PV-overschot betrof dat anders was teruggeleverd. De premie
           werd bij export dus wél bijgeteld maar bij het opofferen van
           export nooit afgetrokken - een structurele, altijd
           dezelfde kant op werkende overschatting van de besparing.
           De lading wordt nu gesplitst in PV-overschot en net-inkoop
           (`_split_charge_pv_vs_grid`), elk tegen het juiste tarief.

        2. **Saldering is niet langer een vaste aanname.** Zolang
           salderen geldt, is teruglevering exact de inkoopprijs waard
           en valt alles samen zoals voorheen. Daarna niet meer: dan
           bepaalt `_get_feedin_value_per_kwh` een apart, veel lager
           teruglevertarief. De kostprijs hangt daardoor af van de
           BRON (PV-overschot vs. net) en de opbrengst van de
           BESTEMMING (huisverbruik vs. export). Per-bron-lots blijven
           onnodig: de accu is één gedeelde pool en alles loopt via
           dezelfde gewogen kostprijs.

        Deliberately doesn't try to distinguish "discharge that covered
        useful load/sale" from "discharge lost to internal battery
        self-discharge/standby losses" - both show up identically as an
        available_kwh decrease. A small simplification; self-discharge
        is typically a minor fraction of total throughput.
        """
        available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        if not available_entity:
            return
        # v5.80: elke ronde de AC-energie die de accu in en uit ging.
        self._tel_accu_ac_energie(now)
        available_kwh = self._read_sensor_float(available_entity)
        if available_kwh is None:
            return

        # v1.1.4: `elapsed_hours` wordt gemeten sinds de vorige
        # BEWEGING van de sensor, niet sinds de vorige tick. Dat is
        # dezelfde fout als in de Kirchhoff-balanscheck (v1.1.3): de
        # beschikbare-energiesensor werkt trager bij dan de tick van vijf
        # minuten, dus als hij vier ticks stilstaat en dan springt, is de
        # opgebouwde energie over ~25 minuten ontstaan terwijl er met
        # ~5 minuten werd gerekend. Het afgeleide ontlaadtempo kwam
        # daardoor tot vijf keer te hoog uit, en dat tempo bepaalt hoeveel
        # van een ontlading als EXPORT wordt geboekt - met een te hoog
        # tempo lijkt er veel meer het net op te gaan dan werkelijk het
        # geval is. Dat verschoof de terugleverpremie en, na saldering,
        # de hele waardering van die kWh.
        if self._last_available_kwh_for_cost_basis is None:
            self._last_available_kwh_for_cost_basis = available_kwh
            self._last_cost_basis_calc_time = now
            return

        delta_kwh = available_kwh - self._last_available_kwh_for_cost_basis

        if abs(delta_kwh) < MIN_COST_BASIS_DELTA_KWH:
            # Sensor stond stil - niets geboekt, en het ijkpunt in tijd
            # blijft staan zodat de eerstvolgende sprong over het
            # WERKELIJKE interval wordt gerekend.
            return

        if self._stap_zonder_accustroom(delta_kwh, now):
            return

        elapsed_hours = 0.0
        if self._last_cost_basis_calc_time is not None:
            elapsed_hours = max(
                (now - self._last_cost_basis_calc_time).total_seconds() / 3600, 0
            )
        self._last_cost_basis_calc_time = now
        self._last_available_kwh_for_cost_basis = available_kwh

        current_price = self._get_current_price_per_kwh(entries, now)
        if current_price is None:
            return

        if delta_kwh > 0:
            # Geladen. v0.63.117: de kostprijs hangt af van de BRON.
            # Net-inkoop kost de inkoopprijs. PV-overschot kost de
            # gederfde teruglevering - onder saldering gelijk aan de
            # inkoopprijs plus de premie, daarna alleen nog het lage
            # teruglevertarief. Voorheen werd alles tegen de kale
            # inkoopprijs geboekt, waardoor de premie op PV-overschot
            # nooit werd afgetrokken terwijl die bij export wél werd
            # bijgeteld: een structurele, eenzijdige overschatting van
            # de besparing.
            # v5.80: wat er AAN DE WISSELSTROOMKANT in ging, inclusief het
            # laadverlies - zie `_accu_ac_kwh`. De kostprijs per opgeslagen
            # kWh wordt dan kosten / delta: het verlies zit erin.
            ac_in_kwh = self._accu_ac_kwh("in", delta_kwh)
            pv_kwh, grid_kwh = self._split_charge_pv_vs_grid(
                ac_in_kwh, elapsed_hours
            )
            feedin_value = self._get_feedin_value_per_kwh(entries, now)
            if feedin_value is None:
                # Geen betrouwbare terugleverwaarde - alles tegen de
                # inkoopprijs boeken, de conservatieve kant (hogere
                # kostprijs, dus geen overschatte besparing).
                pv_kwh, grid_kwh = 0.0, ac_in_kwh
                feedin_value = current_price

            charge_cost_eur = grid_kwh * current_price + pv_kwh * feedin_value
            self.charge_pv_kwh_total += pv_kwh
            self.charge_grid_kwh_total += grid_kwh
            # v3.16.0: ook per dag, voor de zelfvoorziening.
            self.grid_charge_today_kwh += grid_kwh
            self.forgone_feedin_eur_total += pv_kwh * feedin_value

            self._werk_kasprijs_bij(grid_kwh * current_price, delta_kwh, available_kwh)

            effective_charge_price = charge_cost_eur / delta_kwh
            if self.battery_cost_basis_eur_per_kwh is None:
                self.battery_cost_basis_eur_per_kwh = effective_charge_price
            else:
                # Weight by whatever was already stored before this
                # charge - approximated by the available_kwh just before
                # this delta (available_kwh - delta_kwh).
                previous_kwh = max(0.0, available_kwh - delta_kwh)
                total_kwh = previous_kwh + delta_kwh
                self.battery_cost_basis_eur_per_kwh = (
                    self.battery_cost_basis_eur_per_kwh * previous_kwh
                    + charge_cost_eur
                ) / total_kwh
        else:
            # Discharged (sold, or used to cover load and avoid an
            # import) - realise the difference between what this energy
            # is worth right now and what it originally cost, if a cost
            # basis exists yet. Pre-existing energy with an unknown
            # origin (e.g. right after a fresh install) is skipped
            # rather than guessed at.
            #
            # v0.63.117: de opbrengst hangt af van de BESTEMMING. Het
            # deel dat huisverbruik dekt vermijdt inkoop en is dus de
            # (belaste) inkoopprijs waard. Het deel dat werkelijk het
            # net op gaat levert de terugleverwaarde op - onder
            # saldering gelijk aan de inkoopprijs plus premie (identiek
            # aan het oude gedrag), daarna fors lager.
            if self.battery_cost_basis_eur_per_kwh is None:
                self._accu_ac_kwh("uit", -delta_kwh)  # tellers leeg
            if self.battery_cost_basis_eur_per_kwh is not None:
                discharged_kwh = -delta_kwh
                # v5.80: wat er AAN DE WISSELSTROOMKANT uit kwam - minder dan
                # de daling van de voorraad (ontlaadverlies). Alleen die kWh
                # vermijden inkoop of gaan het net op.
                ac_uit_kwh = self._accu_ac_kwh("uit", discharged_kwh)

                export_kwh, load_kwh = self._split_discharge_export_vs_load(
                    ac_uit_kwh, elapsed_hours
                )
                feedin_value = self._get_feedin_value_per_kwh(entries, now)
                if feedin_value is None:
                    # Geen betrouwbare terugleverwaarde - alles
                    # waarderen als vermeden inkoop, zonder premie.
                    export_kwh, load_kwh = 0.0, ac_uit_kwh
                    feedin_value = current_price

                revenue_eur = load_kwh * current_price + export_kwh * feedin_value
                feedin_premium_eur = export_kwh * FEEDIN_PREMIUM_EUR_PER_KWH
                savings_eur = (
                    revenue_eur
                    - discharged_kwh * self.battery_cost_basis_eur_per_kwh
                )
                self.total_battery_savings_eur += savings_eur
                self.total_feedin_premium_eur += feedin_premium_eur
                self.discharge_export_kwh_total += export_kwh

    def _stap_zonder_accustroom(self, delta_kwh: float, now: datetime) -> bool:
        """Is deze voorraadsprong een afrondingsstap zonder accustroom? (v5.155.1)

        Gemeld 01-11 (plan tegen werkelijkheid): sinds 31-10 ~20:40 sprong
        de beschikbare energie elke ~8 min tussen 1,267 en 1,382 kWh (SoC
        21/22 %) bij een accuvermogen van 0 W. Elke daling werd als ontlading
        geboekt (opbrengst x ontlaadrendement min de kostprijs), elke stijging
        als lading (kosten / laadrendement): ~EUR 0,08 verlies per uur dat er
        niet was.

        Alleen met een werkende accuvermogenssensor: de gemeten AC-energie
        sinds de vorige boeking (beide richtingen) is minder dan
        `ACCU_STAP_ZONDER_STROOM_FRACTIE` van de sprong, en de sprong is
        hooguit `ACCU_STAP_ZONDER_STROOM_MAX_KWH`. Zonder vermogenssensor,
        of bij een grotere sprong, wordt geboekt zoals voorheen. Bij True
        blijft het voorraad-ijkpunt staan en schuift alleen de tijd door: in
        dit interval ging er aantoonbaar niets in of uit.
        """
        if abs(delta_kwh) > ACCU_STAP_ZONDER_STROOM_MAX_KWH:
            return False
        if self._accu_ac_laatst is None:
            return False
        if self._read_corrected_battery_power() is None:
            return False
        gemeten = self._accu_ac_in + self._accu_ac_uit
        if gemeten >= ACCU_STAP_ZONDER_STROOM_FRACTIE * abs(delta_kwh):
            return False
        self._last_cost_basis_calc_time = now
        return True

    def _werk_kasprijs_bij(
        self, kosten_eur: float, opgeslagen_kwh: float, available_kwh: float
    ) -> None:
        """De gemiddelde kasprijs van de stroom in de accu (v5.145.0).

        Gevraagd 29-10: "Kun je ook bijhouden wat de gemiddelde prijs van de
        stroom in de accu is? 8 kWh van het net à 30 cent, de rest zon à 0
        cent." Netinkoop telt tegen de kwartierprijs, zon gratis, en de
        kosten worden gedeeld door wat er werkelijk in de accu kwam - het
        laadverlies zit er dus in. Gewogen met wat er al in zat, zoals de
        kostprijs; ontladen verandert het gemiddelde niet.
        """
        if opgeslagen_kwh <= 0:
            return
        eerder_kwh = max(0.0, available_kwh - opgeslagen_kwh)
        eerder_prijs = self.battery_cash_basis_eur_per_kwh
        if eerder_prijs is None:
            # De eerste keer (na de update): wat er al in zat is onbekend.
            # Dan de kostprijs als beginwaarde - de beste schatting die er
            # is; met elke lading telt hij minder mee.
            eerder_prijs = self.battery_cost_basis_eur_per_kwh
            if eerder_prijs is None:
                eerder_kwh = 0.0
                eerder_prijs = 0.0
        self.battery_cash_basis_eur_per_kwh = (
            eerder_prijs * eerder_kwh + kosten_eur
        ) / (eerder_kwh + opgeslagen_kwh)

    # v5.80: AC-energie in en uit de accu sinds de vorige boeking.
    _accu_ac_in: float = 0.0
    _accu_ac_uit: float = 0.0
    _accu_ac_laatst: datetime | None = None

    def _tel_accu_ac_energie(self, now: datetime) -> None:
        """Telt elke ronde het accuvermogen op (v5.80, akkoord Ruud 10-10).

        Gemeld: de besparing volgens het kostprijsmodel liep ~2x te hoog
        (01-10..09-10: model +€ 5,23, eigen afrekening ≈ € 2,57). Het model
        boekte de verandering van de VOORRAAD (beschikbare energie, de
        gelijkstroomkant): bij laden de kosten van alleen de opgeslagen kWh,
        bij ontladen de opbrengst van de hele daling. Het rondreisverlies
        (gemeten 83-84%) zat nergens in: elke geladen kWh kostte in
        werkelijkheid ~1,09 kWh van net of zon, en elke ontladen kWh leverde
        ~0,92 kWh aan het huis. Nagerekend op de auditdata: zonder verlies
        € 4,52, met de wisselstroomkant € 3,22.

        De wisselstroom komt uit de accuvermogenssensor (+ is ontladen),
        bijgehouden tot de beschikbare energie beweegt - die sensor loopt
        trager dan de ronde. Een ronde-gat van meer dan een half uur telt
        niet.
        """
        vermogen_w = self._read_corrected_battery_power()
        vorige = self._accu_ac_laatst
        self._accu_ac_laatst = now
        if vermogen_w is None or vorige is None:
            return
        uren = (now - vorige).total_seconds() / 3600
        if not 0 < uren <= 0.5:
            return
        kwh = vermogen_w / 1000 * uren
        if kwh > 0:
            self._accu_ac_uit += kwh
        else:
            self._accu_ac_in += -kwh

    def _accu_ac_kwh(self, richting: str, voorraad_kwh: float) -> float:
        """De wisselstroomenergie bij een voorraadverandering (v5.80).

        Laden ("in"): wat er van net of zon in ging, minstens de opgeslagen
        kWh en hooguit die gedeeld door `ACCU_AC_MIN_RENDEMENT`. Ontladen
        ("uit"): wat er aan het huis of het net werd geleverd, hooguit de
        daling van de voorraad en minstens die maal `ACCU_AC_MIN_RENDEMENT`.
        Zonder (bruikbare) meting: de voorraad gedeeld of vermenigvuldigd
        met het geleerde halve rendement (laden of ontladen), anders de
        wortel van het rondreisrendement. Zet de teller van die richting
        terug; de andere ook - een boeking sluit het interval af.
        """
        gemeten = self._accu_ac_in if richting == "in" else self._accu_ac_uit
        self._accu_ac_in = 0.0
        self._accu_ac_uit = 0.0
        if voorraad_kwh <= 0:
            return max(0.0, voorraad_kwh)
        half = (
            self.learned_charge_efficiency_percent if richting == "in"
            else self.learned_discharge_efficiency_percent
        )
        if half is None:
            rondreis = self.learned_battery_efficiency_percent
            half = (rondreis / 100) ** 0.5 * 100 if rondreis else None
        factor = (half or 100.0) / 100
        if richting == "in":
            schatting = voorraad_kwh / factor
            ondergrens, bovengrens = voorraad_kwh, voorraad_kwh / ACCU_AC_MIN_RENDEMENT
        else:
            # v5.169.0: ontladen (inhoud -> AC) mag boven 1,0 (rondrit.py)
            from .rondrit import ONTLADEN_MAX

            schatting = voorraad_kwh * factor
            ondergrens, bovengrens = voorraad_kwh * ACCU_AC_MIN_RENDEMENT, voorraad_kwh * ONTLADEN_MAX
        if gemeten > 0 and ondergrens <= gemeten <= bovengrens:
            return gemeten
        return min(max(schatting, ondergrens), bovengrens)
