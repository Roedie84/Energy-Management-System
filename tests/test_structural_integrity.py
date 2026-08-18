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
