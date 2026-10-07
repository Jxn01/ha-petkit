"""The integration's face: every entity key has an English name, a Hungarian name and an
icon; the language files agree; the brand images meet the brands spec.

Home Assistant is stubbed in this suite, so the entity keys are read from the platform
sources. Each guard has a positive control proving it still bites.
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "petkit_ble"
EN = json.loads((PACKAGE / "translations" / "en.json").read_text(encoding="utf-8"))
HU = json.loads((PACKAGE / "translations" / "hu.json").read_text(encoding="utf-8"))
ICONS = json.loads((PACKAGE / "icons.json").read_text(encoding="utf-8"))
PLATFORMS = ("sensor", "binary_sensor", "button", "number", "select", "switch", "time")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
ICON = re.compile(r"^mdi:[a-z0-9]+(-[a-z0-9]+)*$")

# These keep the icon of their device class, which is state-aware (battery level,
# plug, signal bars) -- an icons.json entry would replace it with a fixed one.
DEVICE_CLASS_ICON = {
    ("sensor", "battery_percent"),
    ("sensor", "battery_voltage_mv"),
    ("sensor", "power"),
    ("sensor", "energy_today"),
    ("sensor", "energy_today_wh"),
    ("sensor", "rssi"),
    ("binary_sensor", "on_ac_power"),
    ("binary_sensor", "low_battery"),
}

# homeassistant.components.brands.const.ALLOWED_IMAGES (HA 2026.9); HA is stubbed here.
ALLOWED_IMAGES = {
    "icon.png",
    "logo.png",
    "icon@2x.png",
    "logo@2x.png",
    "dark_icon.png",
    "dark_logo.png",
    "dark_icon@2x.png",
    "dark_logo@2x.png",
}


def entity_keys(platform: str, source: str) -> set[str]:
    """Every translation key a platform module gives its entities."""
    keys = set(re.findall(r'translation_key="([a-z0-9_]+)"', source))
    if platform == "switch":  # PetkitSettingsSwitch(coordinator, "<key>", "<field>") sets key == translation_key
        keys |= set(re.findall(r'PetkitSettingsSwitch\(\s*coordinator,\s*"([a-z0-9_]+)"', source))
    return keys


def _code_keys() -> dict[str, set[str]]:
    return {p: entity_keys(p, (PACKAGE / f"{p}.py").read_text(encoding="utf-8")) for p in PLATFORMS}


def _leaves(tree: dict, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            out |= _leaves(value, (*prefix, key))
        else:
            out[(*prefix, key)] = value
    return out


def test_the_key_reader_bites():
    assert entity_keys("sensor", 'x = D(key="a", translation_key="filter_percent")') == {"filter_percent"}
    assert entity_keys("switch", 'PetkitSettingsSwitch(coordinator, "child_lock", "is_locked")') == {"child_lock"}
    assert sum(len(k) for k in _code_keys().values()) >= 40


def test_strings_json_is_the_english_translation():
    assert json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8")) == EN


def test_every_entity_key_has_both_names_and_nothing_else_is_named():
    for platform, keys in _code_keys().items():
        for lang, tree in (("en", EN), ("hu", HU)):
            named = set(tree["entity"].get(platform, {}))
            assert keys == named, (lang, platform, sorted(keys ^ named))
            for key in keys:
                assert tree["entity"][platform][key]["name"].strip(), (lang, platform, key)


def test_every_entity_key_has_an_icon_or_a_device_class_icon():
    for platform, keys in _code_keys().items():
        iconed = set(ICONS["entity"].get(platform, {}))
        assert iconed <= keys, (platform, sorted(iconed - keys))
        for key in keys:
            if (platform, key) in DEVICE_CLASS_ICON:
                assert key not in iconed, f"{platform}.{key} would lose its device-class icon"
                continue
            spec = ICONS["entity"][platform].get(key)
            assert spec, f"no icon for {platform}.{key}"
            for icon in [spec["default"], *spec.get("state", {}).values()]:
                assert ICON.match(icon), (platform, key, icon)


def test_select_states_are_translated_and_iconed():
    for lang, tree in (("en", EN), ("hu", HU)):
        assert set(tree["entity"]["select"]["mode"]["state"]) == {"normal", "smart"}, lang
    assert set(ICONS["entity"]["select"]["mode"]["state"]) <= {"normal", "smart"}


def test_hungarian_covers_exactly_what_english_does_with_the_same_placeholders():
    en, hu = _leaves(EN), _leaves(HU)
    assert sorted(set(en) - set(hu)) == [], "missing in hu.json"
    assert sorted(set(hu) - set(en)) == [], "in hu.json but not in English"
    for path, text in en.items():
        assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(hu[path])), path


def test_model_names_only_for_known_aliases():
    from custom_components.petkit_ble.const import KNOWN_ALIASES, MODEL_NAMES

    assert MODEL_NAMES
    assert set(MODEL_NAMES) <= KNOWN_ALIASES


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path.name
    return struct.unpack(">II", data[16:24])


def test_brand_images_meet_the_brands_spec():
    images = {p.name: _png_size(p) for p in (PACKAGE / "brand").iterdir()}
    assert {"icon.png", "icon@2x.png", "logo.png", "logo@2x.png"} <= set(images)
    assert set(images) <= ALLOWED_IMAGES
    for name, (w, h) in images.items():
        hidpi = "@2x" in name
        if "icon" in name:
            assert (w, h) == ((512, 512) if hidpi else (256, 256)), name
        else:
            low, high = (256, 512) if hidpi else (128, 256)
            assert low <= min(w, h) <= high, name
            assert w >= h, f"{name}: landscape preferred"
