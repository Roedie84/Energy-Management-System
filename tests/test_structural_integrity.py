"""Structural integrity checks via static analysis (AST).

These exist specifically because of two real incidents in this project
where a str_replace-style edit accidentally merged two classes/functions
together while inserting new code nearby:

1. `_read_corrected_consumption_power`'s `def` line was overwritten,
   leaving its body as dead code inside a different property (v0.34.3).
2. `CheapestBlockStartSensor`'s `__init__`/`native_value` were displaced
   into the newly-added `CurrentPricePerKwhSensor`, crashing the entire
   sensor platform setup at Home Assistant startup (v0.40.1).

Both bugs still *compiled* fine (no syntax error) and were only caught
by actually running the code. These tests catch the same class of bug
automatically, without needing a live Home Assistant instance.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_DIR = REPO_ROOT / "custom_components" / "energy_management_system"

# Base classes (from sensor.py) that require the subclass to supply its
# own __init__ (the base class's __init__ takes a unique_suffix argument
# that differs per subclass, so subclasses can never just inherit it).
BASES_REQUIRING_OWN_INIT = {"_CoordinatorDiagnosticSensor"}

# Known-benign "self.<name>(...)" calls that don't correspond to a method
# defined in this codebase - either inherited from a Home Assistant base
# class, or a callable instance attribute (not a method).
KNOWN_FRAMEWORK_OR_ATTRIBUTE_CALLS = {
    "async_get_last_state",
    "async_write_ha_state",
    "async_added_to_hass",
    "_unsub_interval",
    "_unsub_state",
    "_unsub_water_state",
    # v0.63.122: callable attribuut (unsubscribe van de accu-koeling-
    # listener), geen methode - zelfde soort als _unsub_water_state.
    "_unsub_battery_cooling_state",
    "_unsub_compare",
    "_unsub_capture",
    "_abort_if_unique_id_configured",
    "async_create_entry",
    "async_show_form",
    "async_set_unique_id",
}


def _iter_python_files():
    for path in INTEGRATION_DIR.glob("*.py"):
        yield path


def test_every_file_parses_and_compiles():
    """A syntax-level sanity check - both real incidents still passed
    this, so it's necessary but not sufficient on its own (see the
    other tests below for what actually caught them)."""
    for path in _iter_python_files():
        source = path.read_text()
        compile(source, str(path), "exec")  # raises SyntaxError if broken


def test_no_orphaned_self_method_calls():
    """Every `self.<name>(...)` call must correspond to either a method
    defined somewhere in this file, or a known framework/attribute
    exception. This is what would have caught the
    `_read_corrected_consumption_power` incident: the call site survived
    intact, but the method definition it pointed to had been
    accidentally merged into a different function."""
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))

        defined_methods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined_methods.add(item.name)

        called_methods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    called_methods.add(node.func.attr)

        missing = called_methods - defined_methods - KNOWN_FRAMEWORK_OR_ATTRIBUTE_CALLS
        assert not missing, f"{path.name}: calls to undefined self.<method>(): {missing}"


def test_sensor_subclasses_have_their_own_init():
    """Every class inheriting from a base that requires a per-subclass
    __init__ must define one directly in its own body. This is what
    would have caught the CheapestBlockStartSensor/CurrentPricePerKwhSensor
    incident: the class survived with the right name and bases, but its
    __init__ had been displaced into the wrong class entirely."""
    sensor_path = INTEGRATION_DIR / "sensor.py"
    tree = ast.parse(sensor_path.read_text(), filename=str(sensor_path))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
        if base_names & BASES_REQUIRING_OWN_INIT:
            has_own_init = any(
                isinstance(item, ast.FunctionDef) and item.name == "__init__"
                for item in node.body
            )
            if not has_own_init:
                offenders.append(node.name)

    assert not offenders, f"classes missing their own __init__: {offenders}"


def test_sensor_platform_setup_instantiates_every_registered_sensor():
    """The strongest version of the regression test: actually import
    sensor.py and instantiate every class passed to a `*Sensor(...)`
    style constructor inside async_setup_entry, exactly like Home
    Assistant would at startup. A displaced __init__ raises a
    TypeError here, exactly as it did in production."""
    import inspect
    import re

    from custom_components.energy_management_system import sensor as sensor_mod

    sensor_path = INTEGRATION_DIR / "sensor.py"
    source = sensor_path.read_text()

    # Find every "SomeSensor(coordinator, ...)" construction inside the
    # file (the pattern used throughout async_setup_entry). DOTALL so a
    # constructor call spanning multiple lines (extra positional args on
    # their own line) still matches - this is what would have missed
    # ApplianceUsageHoursSensor/ApplianceReadyNotificationSensor, which
    # take extra args beyond (coordinator, entry_id).
    class_names = set(
        re.findall(r"\b([A-Z]\w*Sensor)\(\s*coordinator", source, re.DOTALL)
    )
    assert class_names, "no sensor classes found - check the regex still matches"

    class _StubCoordinator:
        last_cheap_block_start = None
        last_cheap_block_end = None
        last_current_price_per_kwh = None
        last_reason = "default_smart"
        last_expected_mode = "smart"
        last_simulated_action = None
        last_is_expensive = False
        last_effective_expensive_quarters_count = 0
        last_discharge_start = None
        last_soc_percent = None
        last_available_kwh = None
        last_needed_kwh_to_bridge = None
        last_has_enough_energy = None
        energy_bridge_transition_log = []
        last_timeline = []
        last_transitions = []
        night_consumption_history = []
        was_bootstrapped_from_history = False
        total_discharge_value_eur = 0.0
        total_charge_cost_eur = 0.0
        reserve_shortfall_history = []
        _shortfall_detected_today = False
        reserve_excess_history = []
        _excess_detected_today = False
        learned_efficiency_history = []
        dishwasher_usage_hourly_history = {}
        washing_machine_usage_hourly_history = {}
        last_dishwasher_notification = None
        last_washing_machine_notification = None

        def learned_hourly_avg_kw(self, hour):
            return None

        def learned_pv_hourly_ratio(self, hour):
            return None

        def raw_pv_hourly_avg(self, hour):
            return None

        def learned_appliance_usage_hours(self, history, threshold=0.15):
            return []

        @property
        def learned_night_consumption_kw(self):
            return None

        @property
        def learned_battery_efficiency_percent(self):
            return None

    stub = _StubCoordinator()
    failures = {}
    for class_name in class_names:
        cls = getattr(sensor_mod, class_name)
        # Build a plausible argument list from the __init__ signature,
        # instead of assuming every sensor takes exactly (coordinator,
        # entry_id) - some take extra positional args (e.g. which
        # appliance, a display name, an icon).
        try:
            params = list(inspect.signature(cls.__init__).parameters.values())[1:]
        except (TypeError, ValueError):
            params = []
        args = []
        for param in params:
            if param.name == "coordinator":
                args.append(stub)
            elif param.name == "entry_id":
                args.append("test_entry_id")
            elif param.default is not inspect.Parameter.empty:
                break  # remaining params are optional - stop here
            else:
                args.append("test_value")  # generic filler for str-typed extras

        try:
            cls(*args)
        except Exception as exc:  # noqa: BLE001 - we want to see every failure
            failures[class_name] = repr(exc)

    assert not failures, f"sensor classes failed to instantiate: {failures}"


def test_no_call_uses_an_undefined_local_name():
    """v3.6.1: `self._leg_pv_modelmonster_vast(hour, ...)` gebruikte een
    naam die in die functie niet bestond.

    Elke afgesloten lichte uur gaf een NameError, netjes opgevangen door
    de try/except eromheen - dus het regressiewoud verzamelde NUL
    monsters, en de drie weken wachten waren voor niets geweest.

    Gevonden door het logboek uit v3.4.0, binnen een dag. De AST-scan
    hierboven kijkt naar METHODEN die niet bestaan; deze naar
    VARIABELEN.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    fouten = []
    for bestand in ("coordinator.py", "sensor.py", "solar_forecast.py"):
        pad = Path(pkg.__file__).parent / bestand
        if not pad.exists():
            continue
        boom = ast.parse(pad.read_text())
        # Alleen toewijzingen op het HOOGSTE niveau. `boom.body` bevat
        # ook de klasse, en `ast.walk` daarop levert elke naam uit elke
        # methode - waardoor `hour` als bekend gold en de fout niet werd
        # gezien.
        modulenamen = {
            doel.id
            for knoop in boom.body
            if isinstance(knoop, (ast.Assign, ast.AnnAssign, ast.AugAssign))
            for doel in (
                knoop.targets if isinstance(knoop, ast.Assign) else [knoop.target]
            )
            if isinstance(doel, ast.Name)
        } | {
            (alias.asname or alias.name).split(".")[0]
            for knoop in boom.body
            if isinstance(knoop, (ast.Import, ast.ImportFrom))
            for alias in knoop.names
        }

        # Per functie ook de namen uit de OMSLUITENDE functies, want een
        # geneste functie ziet die. Zonder dat worden `moment` en `tekst`
        # ten onrechte als onbekend gemeld.
        omhullend: dict[int, set[str]] = {}

        def _verzamel(knoop, buiten: set[str]) -> None:
            for kind in ast.iter_child_nodes(knoop):
                if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    omhullend[id(kind)] = set(buiten)
                    eigen = set(buiten)
                    eigen |= {a.arg for a in kind.args.args}
                    eigen |= {a.arg for a in kind.args.kwonlyargs}
                    for n in ast.walk(kind):
                        if isinstance(n, ast.Name) and isinstance(
                            n.ctx, (ast.Store, ast.Del)
                        ):
                            eigen.add(n.id)
                    _verzamel(kind, eigen)
                else:
                    _verzamel(kind, buiten)

        _verzamel(boom, set())

        for functie in ast.walk(boom):
            if not isinstance(functie, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Namen die in deze functie beschikbaar zijn.
            bekend = set(omhullend.get(id(functie), set()))
            bekend |= {a.arg for a in functie.args.args}
            bekend |= {a.arg for a in functie.args.kwonlyargs}
            if functie.args.vararg:
                bekend.add(functie.args.vararg.arg)
            if functie.args.kwarg:
                bekend.add(functie.args.kwarg.arg)
            for knoop in ast.walk(functie):
                if isinstance(knoop, ast.Name) and isinstance(
                    knoop.ctx, (ast.Store, ast.Del)
                ):
                    bekend.add(knoop.id)
                elif isinstance(knoop, (ast.Import, ast.ImportFrom)):
                    for alias in knoop.names:
                        bekend.add((alias.asname or alias.name).split(".")[0])
                elif isinstance(knoop, ast.ExceptHandler) and knoop.name:
                    bekend.add(knoop.name)
                elif isinstance(
                    knoop, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    bekend.add(knoop.name)
                elif isinstance(knoop, (ast.comprehension,)):
                    for n in ast.walk(knoop.target):
                        if isinstance(n, ast.Name):
                            bekend.add(n.id)

            # Namen die als ARGUMENT aan een eigen methode worden
            # meegegeven: die moeten bestaan.
            # Alleen aanroepen die bij DEZE functie horen. `ast.walk`
            # daalt af in geneste functies, en dan werd een aanroep in
            # een binnenfunctie ook vanuit de buitenste beoordeeld -
            # waar de parameter van de binnenfunctie niet bestaat.
            def _eigen_aanroepen(knoop):
                for kind in ast.iter_child_nodes(knoop):
                    if isinstance(
                        kind, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        continue
                    if isinstance(kind, ast.Call):
                        yield kind
                    yield from _eigen_aanroepen(kind)

            for aanroep in _eigen_aanroepen(functie):
                if not isinstance(aanroep, ast.Call):
                    continue
                doel = aanroep.func
                if not (
                    isinstance(doel, ast.Attribute)
                    and isinstance(doel.value, ast.Name)
                    and doel.value.id == "self"
                ):
                    continue
                for arg in aanroep.args:
                    if isinstance(arg, ast.Name) and arg.id not in bekend:
                        # Ingebouwde namen en modulevariabelen overslaan.
                        if arg.id in dir(__builtins__) or arg.id.isupper():
                            continue
                        # NIET overslaan omdat de naam elders in het
                        # bestand bestaat: `hour` bestond in twintig
                        # andere functies, en juist daardoor viel deze
                        # fout niet op. Alleen namen op MODULENIVEAU
                        # tellen als bekend.
                        if arg.id in modulenamen:
                            continue
                        fouten.append(
                            f"{bestand}:{arg.lineno}: "
                            f"self.{doel.attr}(... {arg.id} ...) - "
                            f"{arg.id!r} bestaat hier niet"
                        )

    assert not fouten, fouten


def test_no_staticmethod_uses_self():
    """v3.7.1: een `@staticmethod` met `self` als eerste parameter.

    Gemeld met een screenshot: twee tegels op "unknown". De oorzaak was
    ernstiger dan de tegels: `last_successful_update` stond op None - er
    had sinds het opstarten geen ENKELE ronde gedraaid.

        TypeError: _koelen_is_goedkoop() missing 1 required positional
        argument: 'buiten_c'

    In v3.6.0 is `_koelen_is_goedkoop` ingevoegd TUSSEN een
    `@staticmethod`-decorator en de functie waar die bij hoorde. De
    decorator plakte daardoor aan de nieuwe functie: `self` werd de
    eerste echte parameter, en er bleef er één over.

    Alle 2375 tests bleven groen, want geen enkele riep die functie aan
    via een echt object - de testhulpfunctie plakte hem los op een kale
    klasse. In bedrijf viel elke ronde om.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    fouten = []
    for bestand in ("coordinator.py", "sensor.py", "switch.py", "button.py"):
        pad = Path(pkg.__file__).parent / bestand
        if not pad.exists():
            continue
        for knoop in ast.walk(ast.parse(pad.read_text())):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            statisch = any(
                isinstance(d, ast.Name) and d.id == "staticmethod"
                for d in knoop.decorator_list
            )
            eerste = knoop.args.args[0].arg if knoop.args.args else None
            if statisch and eerste == "self":
                fouten.append(f"{bestand}:{knoop.lineno}: {knoop.name}")

    assert not fouten, (
        "deze functies zijn @staticmethod maar hebben `self` als eerste "
        f"parameter: {fouten}"
    )


def test_no_method_with_self_is_called_as_static():
    """De andere kant: een gewone methode die zonder object wordt
    aangeroepen. Dat gaf in v3.6.0 achttien testfouten voordat het in
    bedrijf kwam."""
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    pad = Path(pkg.__file__).parent / "coordinator.py"
    boom = ast.parse(pad.read_text())

    # Namen van gewone methoden (met self, zonder staticmethod).
    gewoon = {
        k.name
        for k in ast.walk(boom)
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))
        and k.args.args
        and k.args.args[0].arg == "self"
        and not any(
            isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod")
            for d in k.decorator_list
        )
    }

    fouten = [
        f"{aanroep.lineno}: {aanroep.func.attr}"
        for aanroep in ast.walk(boom)
        if isinstance(aanroep, ast.Call)
        and isinstance(aanroep.func, ast.Attribute)
        and isinstance(aanroep.func.value, ast.Name)
        and aanroep.func.value.id
        == "EnergyManagementSystemCoordinator"
        and aanroep.func.attr in gewoon
    ]

    assert not fouten, fouten


def test_no_staticmethod_uses_self():
    """v3.7.1: `_koelen_is_goedkoop` kreeg per ongeluk een
    `@staticmethod` boven zich.

    Bij het invoegen van die functie schoof de decorator van de
    ONDERLIGGENDE functie naar de nieuwe. Gevolg in bedrijf:

        _koelen_is_goedkoop() missing 1 required positional argument:
        'buiten_c'

    Want `self._koelen_is_goedkoop(accu_c, buiten_c)` geeft bij een
    statische methode twee argumenten aan een functie die er drie
    verwacht - `self` telt dan mee als gewone parameter.

    Deze soort fout is met het blote oog nauwelijks te zien: de
    decorator staat een regel hoger en hoort visueel bij de vorige
    functie.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    fouten = []
    for bestand in ("coordinator.py", "sensor.py", "switch.py", "solar_forecast.py"):
        pad = Path(pkg.__file__).parent / bestand
        if not pad.exists():
            continue

        for knoop in ast.walk(ast.parse(pad.read_text())):
            if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            statisch = any(
                isinstance(d, ast.Name) and d.id == "staticmethod"
                for d in knoop.decorator_list
            )
            if not statisch:
                continue

            # Een statische methode mag `self` niet als parameter hebben,
            # en mag hem ook niet gebruiken.
            if knoop.args.args and knoop.args.args[0].arg == "self":
                fouten.append(
                    f"{bestand}:{knoop.lineno}: {knoop.name} is statisch "
                    "maar heeft `self` als eerste parameter"
                )
                continue
            for n in ast.walk(knoop):
                if isinstance(n, ast.Name) and n.id == "self":
                    fouten.append(
                        f"{bestand}:{knoop.lineno}: {knoop.name} is statisch "
                        "maar gebruikt `self`"
                    )
                    break

    assert not fouten, fouten


# --- structuurscan 18: elke gebruikte naam is geïmporteerd -----------


def test_every_module_imports_what_it_uses():
    """De fout van 30 augustus (v3.78.0).

    De twee handmatige schakelaars verschenen niet in Home Assistant,
    terwijl de bestandscontrole zei dat alle bestanden klopten en er
    geen logboekmelding was.

    De oorzaak: `HANDMATIGE_STAND_LADEN` werd in `switch.py` gebruikt
    maar nooit geïmporteerd. Bij het opzetten van de schakelaars werpt
    dat een NameError, en dan wordt die hele stap stil overgeslagen -
    geen entiteiten, geen zichtbare fout.

    Mijn toetsen misten het volledig: die controleerden of de KLASSE in
    het bestand stond, niet of hij ook opgezet kon worden.

    Deze scan kijkt per bestand of elke naam in HOOFDLETTERS die
    gebruikt wordt, ook geïmporteerd of gedefinieerd is.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    fouten = []
    for pad in sorted(Path(pkg.__file__).parent.glob("*.py")):
        boom = ast.parse(pad.read_text())
        beschikbaar = set()
        for n in ast.walk(boom):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                beschikbaar |= {
                    (a.asname or a.name).split(".")[0] for a in n.names
                }
            elif isinstance(n, ast.Assign):
                beschikbaar |= {
                    t.id for t in n.targets if isinstance(t, ast.Name)
                }
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                beschikbaar.add(n.target.id)

        gebruikt = {
            n.id
            for n in ast.walk(boom)
            if isinstance(n, ast.Name)
            and isinstance(n.ctx, ast.Load)
            and n.id.isupper()
            and len(n.id) > 3
        }
        ontbreekt = sorted(gebruikt - beschikbaar - set(dir(__builtins__)))
        if ontbreekt:
            fouten.append(f"{pad.name}: {ontbreekt}")

    assert not fouten, (
        "namen die gebruikt worden maar nergens vandaan komen - dat "
        f"werpt een NameError bij het opstarten: {fouten}"
    )


# --- structuurscan 20: schakelaars luisteren mee ---------------------


def test_every_switch_that_reads_the_coordinator_listens():
    """De fout van 30 augustus (v3.83.0).

    Gemeld met een schermafdruk: "Handmatig laden 2000 W - Aan", terwijl
    de export op datzelfde moment `handmatige_stand: None` gaf.

    Die twee spraken elkaar tegen omdat de schakelaar zich nergens op
    abonneerde. `is_on` leest het juiste veld, maar Home Assistant vraagt
    dat alleen opnieuw op als iemand het zegt - en dat gebeurt pas als je
    de knop aanraakt.

    Gevolg: de integratie zet de stand uit - bij een herstart, of omdat
    de accu vol is - en het dashboard blijft "Aan" tonen. Dan denk je dat
    je aan het laden bent terwijl er niets gebeurt.

    Twee andere schakelaars hadden hetzelfde: de kalibratie, die vanzelf
    afrondt bij een volle accu, en `Nu laden`, waarvan het uitstel
    afloopt.

    Een schakelaar die zijn stand uit de coordinator leest, moet
    meeluisteren. Tenzij hij zijn stand uit de Store herstelt - dan is
    hij zelf de bron.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "switch.py").read_text()
    boom = ast.parse(bron)

    fouten = []
    for kl in ast.walk(boom):
        if not isinstance(kl, ast.ClassDef) or not kl.name.endswith("Switch"):
            continue
        tekst = ast.get_source_segment(bron, kl) or ""
        leest = "self._coordinator." in tekst
        luistert = "register_listener" in tekst
        eigen_bron = "async_get_last_state" in tekst
        if leest and not luistert and not eigen_bron:
            fouten.append(kl.name)

    assert not fouten, (
        "deze schakelaars lezen hun stand uit de coordinator maar "
        f"luisteren niet mee - dan blijft het dashboard hangen: {fouten}"
    )


# --- structuurscan 21: het accuvermogen via de juiste helper ---------


def test_battery_power_is_always_read_sign_corrected():
    """De fout van 30 augustus (v3.88.0).

    `_richting_van_de_accu` las de vermogenssensor RECHTSTREEKS en
    negeerde daarmee `invert_battery_power_sign` - een instelling die bij
    deze installatie aan staat. Laden en ontladen zouden precies
    omgekeerd zijn vastgelegd, en dan meet de hele patroonanalyse het
    tegenovergestelde van wat er gebeurde.

    `_read_corrected_battery_power` bestaat sinds v0.39.0 en doet het
    goed: positief is ontladen, negatief is laden.

    Deze scan zoekt naar plekken die `CONF_BATTERY_POWER_SENSOR` zelf
    lezen in plaats van die helper te gebruiken.
    """
    import ast
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "coordinator.py").read_text()
    boom = ast.parse(bron)

    # Wie de sensor rechtstreeks leest, MOET het teken zelf verrekenen.
    #
    # Acht functies doen dat laatste al met dezelfde vier regels als de
    # helper. Dat is dubbele code - een van de punten uit de
    # doorlichting - maar geen fout: het teken klopt er.
    #
    # Deze scan slaat alleen aan als de correctie ONTBREEKT, want dan
    # staat er stilzwijgend een omgekeerde waarde.
    fouten = []
    for fn in ast.walk(boom):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name == "_read_corrected_battery_power":
            continue
        tekst = ast.get_source_segment(bron, fn) or ""
        code = "\n".join(
            r for r in tekst.split("\n") if not r.strip().startswith("#")
        )
        if "CONF_INVERT_BATTERY_POWER_SIGN" in code:
            continue
        if "_read_corrected_battery_power" in code:
            continue

        # Alleen waar de WAARDE wordt gelezen, niet waar alleen wordt
        # gekeken of de sensor bestaat. Twee functies controleren de
        # beschikbaarheid van vier sensoren tegelijk in een lus - die
        # lezen wel `_read_sensor_float`, maar op een andere entiteit.
        import re

        rechtstreeks = re.search(
            r"_read_sensor_float\(\s*\n?\s*(self\.config\.get\()?"
            r"CONF_BATTERY_POWER_SENSOR",
            code,
        ) or re.search(
            r"battery_entity\s*=\s*self\.config\.get\("
            r"CONF_BATTERY_POWER_SENSOR\)[\s\S]{0,400}"
            r"_read_sensor_float\(battery_entity\)",
            code,
        )
        if rechtstreeks:
            fouten.append(fn.name)

    assert not fouten, (
        "deze functies lezen de accuvermogenssensor rechtstreeks en "
        "negeren daarmee `invert_battery_power_sign` - gebruik "
        f"`_read_corrected_battery_power`: {fouten}"
    )
