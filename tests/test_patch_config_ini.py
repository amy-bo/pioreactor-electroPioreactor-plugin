# -*- coding: utf-8 -*-
"""
Tests for scripts/patch-config-ini.py.

The script reads ~/.pioreactor/config.ini, adds plugin defaults, and
writes it back. Pre-v0.6.7 it used a default
`configparser.ConfigParser()`, which silently lower-cased every key on
round-trip — corrupting `[leds]` (A/B/C/D LED channel labels) and PID
gains (Kp/Ki/Kd) under `[stirring.pid]`,
`[dosing_automation.pid_morbidostat]`,
`[temperature_automation.thermostat]`, all of which Pioreactor looks up
case-sensitively.

These tests pin the post-fix behaviour: a round-trip through the script
preserves uppercase keys instead of folding them to lowercase.

NOTE on section scope: upstream `[od_config.photodiode_channel]` uses
*numeric* keys (1=REF, 2=90, …) — not letter keys. So letter-key
corruption appears in `[leds]`, not in the photodiode-channel section.
Tests assert the correct scope explicitly.
"""
from __future__ import annotations

import configparser
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "patch-config-ini.py"


def _load_patch_module():
    """Import patch-config-ini.py as a module despite the hyphen in its name."""
    spec = importlib.util.spec_from_file_location("patch_config_ini", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["patch_config_ini"] = mod
    spec.loader.exec_module(mod)
    return mod


def _seed_upstream_template(p: Path) -> None:
    """Write a config.ini covering the case-sensitive sections this fix is
    about: `[leds]` with letter keys A/B/C/D, `[od_config.photodiode_channel]`
    with numeric keys, and the three real upstream PID sections with
    capitalised gains. Section names + key shape verified against
    packaging/shared-assets/pioreactor/config.example.ini.

    NOTE: deliberately has NO `[PWM]` section, so the PWM-4 guard does not
    fire and the case-preservation assertions can run. A genuinely stock
    image DOES ship `[PWM] 4=waste` - see
    `TestStockImage.test_stock_pwm_4_waste_is_refused` for that path."""
    p.write_text(
        "[leds]\n"
        "A=IR\n"
        "B=\n"
        "C=\n"
        "D=\n"
        "\n"
        "[od_config.photodiode_channel]\n"
        "1=REF\n"
        "2=90\n"
        "3=\n"
        "4=\n"
        "\n"
        "[dosing_automation.pid_morbidostat]\n"
        "Kp=1\n"
        "Ki=0\n"
        "Kd=0\n"
        "\n"
        "[temperature_automation.thermostat]\n"
        "Kp=2.6\n"
        "Ki=0.0\n"
        "Kd=4.6\n"
        "\n"
        "[stirring.pid]\n"
        "Kp=0.005\n"
        "Ki=0.0\n"
        "Kd=0.0\n",
        encoding="utf-8",
    )


def _read_preserving_case(p: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.optionxform = str  # type: ignore[assignment]
    parser.read(p)
    return parser


# ── case preservation on round-trip ──────────────────────────────────────────


class TestCasePreservation:
    """The script must NOT silently lower-case existing keys when adding
    plugin defaults to ~/.pioreactor/config.ini."""

    def test_leds_letter_keys_stay_uppercase(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.ini"
        _seed_upstream_template(cfg)
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 0

        parsed = _read_preserving_case(cfg)
        keys = list(parsed["leds"].keys())
        assert keys == ["A", "B", "C", "D"], f"[leds] keys lowercased: {keys}"
        assert parsed["leds"]["A"] == "IR"

    def test_photodiode_numeric_keys_unchanged(self, tmp_path, monkeypatch):
        # Numeric keys have no case — round-trip just shouldn't damage them.
        cfg = tmp_path / "config.ini"
        _seed_upstream_template(cfg)
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 0

        parsed = _read_preserving_case(cfg)
        keys = list(parsed["od_config.photodiode_channel"].keys())
        assert keys == ["1", "2", "3", "4"]
        assert parsed["od_config.photodiode_channel"]["1"] == "REF"
        assert parsed["od_config.photodiode_channel"]["2"] == "90"

    def test_pid_gain_keys_stay_capitalised(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.ini"
        _seed_upstream_template(cfg)
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 0

        parsed = _read_preserving_case(cfg)
        for section in (
            "dosing_automation.pid_morbidostat",
            "temperature_automation.thermostat",
            "stirring.pid",
        ):
            keys = list(parsed[section].keys())
            assert keys == ["Kp", "Ki", "Kd"], (
                f"{section} keys lowercased: {keys}"
            )

    def test_plugin_defaults_still_added(self, tmp_path, monkeypatch):
        # Sanity: the case-preserving fix must not break the script's actual job.
        cfg = tmp_path / "config.ini"
        _seed_upstream_template(cfg)
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 0

        parsed = _read_preserving_case(cfg)
        assert parsed["PWM"]["4"] == "relay"
        assert parsed["electropioreactor.config"]["electrolysis_power"] == "2.5"
        assert parsed["electropioreactor.config"]["sparge_duration_seconds"] == "10.0"
        assert parsed["electropioreactor.config"]["sparge_interval_minutes"] == "60.0"
        assert parsed["electropioreactor.config"]["od_pause_after_sparge_seconds"] == "5.0"

    def test_existing_pwm_4_non_relay_still_refused(self, tmp_path, monkeypatch, capsys):
        # The v0.6.6 PWM-4 guard must survive the case-preservation refactor.
        cfg = tmp_path / "config.ini"
        cfg.write_text("[PWM]\n4=stirring\n", encoding="utf-8")
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 1
        assert "refusing to overwrite [PWM] 4" in capsys.readouterr().err


# ── behaviour on a genuinely stock image ─────────────────────────────────────


class TestStockImage:
    """Pins what the script does against the PWM block upstream actually
    ships, so the README's install steps stay honest about it."""

    # Verbatim from packaging/shared-assets/pioreactor/config.example.ini
    # (unchanged between master and tag 26.5.0).
    STOCK_PWM = (
        "[PWM]\n"
        "# map the PWM channels to externals.\n"
        "# hardware PWM are available on channels 2 & 4.\n"
        "1=stirring\n"
        "2=media\n"
        "3=alt_media\n"
        "4=waste\n"
        "5=heating\n"
    )

    def test_stock_pwm_4_waste_is_refused(self, tmp_path, monkeypatch, capsys):
        # A stock image assigns PWM 4 to `waste`, so the guard fires and the
        # script is a no-op until the user frees the channel. README step 4
        # documents this; if the guard ever silently overwrote instead, a
        # waste pump would be driven as a CO2 solenoid.
        cfg = tmp_path / "config.ini"
        cfg.write_text(self.STOCK_PWM, encoding="utf-8")
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 1
        assert "refusing to overwrite [PWM] 4 = 'waste'" in capsys.readouterr().err

    def test_refusal_leaves_config_untouched(self, tmp_path, monkeypatch):
        # The refusal path must not half-write: no [electropioreactor.config]
        # section, and the other channel assignments unchanged.
        cfg = tmp_path / "config.ini"
        cfg.write_text(self.STOCK_PWM, encoding="utf-8")
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 1
        assert cfg.read_text(encoding="utf-8") == self.STOCK_PWM

    def test_freeing_channel_4_lets_the_patch_through(self, tmp_path, monkeypatch):
        # The documented remedy: clear PWM 4, re-run, and it succeeds.
        cfg = tmp_path / "config.ini"
        cfg.write_text(self.STOCK_PWM.replace("4=waste\n", ""), encoding="utf-8")
        monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

        mod = _load_patch_module()
        assert mod.main() == 0

        parsed = _read_preserving_case(cfg)
        assert parsed["PWM"]["4"] == "relay"
        assert parsed["PWM"]["1"] == "stirring"
        assert parsed["electropioreactor.config"]["electrolysis_power"] == "2.5"
