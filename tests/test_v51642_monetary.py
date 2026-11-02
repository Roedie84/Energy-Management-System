"""v5.164.2 - sensoren in euro hebben device_class monetary (opschoonpunt 6)."""
import ast
from pathlib import Path

BRON = Path(__file__).parent.parent / "custom_components/energy_management_system/sensor.py"


def test_elke_eurosensor_is_monetary():
    boom = ast.parse(BRON.read_text())
    zonder = []
    for klasse in [n for n in boom.body if isinstance(n, ast.ClassDef)]:
        attrs = {}
        for stap in klasse.body:
            if isinstance(stap, ast.Assign) and isinstance(stap.targets[0], ast.Name):
                attrs[stap.targets[0].id] = ast.unparse(stap.value)
        eenheid = attrs.get("_attr_native_unit_of_measurement", "")
        if eenheid in ("'€'", "'EUR'") and "MONETARY" not in attrs.get("_attr_device_class", ""):
            zonder.append(klasse.name)
    assert zonder == []


def test_monetary_nooit_met_measurement():
    boom = ast.parse(BRON.read_text())
    for klasse in [n for n in boom.body if isinstance(n, ast.ClassDef)]:
        tekst = ast.unparse(klasse)
        if "SensorDeviceClass.MONETARY" in tekst:
            assert "_attr_state_class = 'measurement'" not in tekst, klasse.name


def test_monetary_nooit_met_total_increasing():
    """v5.166.1 - HA staat bij monetary alleen total of geen state_class toe."""
    boom = ast.parse(BRON.read_text())
    for klasse in [n for n in boom.body if isinstance(n, ast.ClassDef)]:
        tekst = ast.unparse(klasse)
        if "SensorDeviceClass.MONETARY" in tekst:
            assert "_attr_state_class = 'total_increasing'" not in tekst, klasse.name
            assert "SensorStateClass.TOTAL_INCREASING" not in tekst, klasse.name
