from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass
class Config:
    match_threshold_registration: float = 0.80
    match_threshold_car_select: float = 0.80
    match_threshold_go: float = 0.45
    match_threshold_inactivity: float = 0.80
    match_threshold_finish: float = 0.65
    match_threshold_enter_button: float = 0.75
    match_threshold_start: float = 0.75
    match_threshold_restart: float = 0.72
    match_threshold_restart_confirm: float = 0.78
    match_threshold_timeattack: float = 0.70
    match_threshold_pausemenu: float = 0.80
    match_threshold_colossus1: float = 0.80
    match_threshold_colossus2: float = 0.80
    match_threshold_colossus3: float = 0.85
    match_threshold_colossus4: float = 0.80
    match_threshold_changerival: float = 0.90
    match_threshold_changerival2: float = 0.80
    match_threshold_quitrival: float = 0.80
    key_hold_ms: tuple = (10, 20)
    between_keys_ms: tuple = (10, 20)
    poll_interval_ms: tuple = (15, 30)
    loop_pace_s: float = 0.10
    auto_focus: bool = True
    car_select_enter_count: int = 5
    car_select_enter_gap_s: float = 0.25
    d_taps_on_inactivity: int = 1
    inactivity_cooldown_s: float = 0.6

    # Timeout
    enroll_retry_s: float = 0.8
    timeout_race_start_s: float = 120.0
    timeout_race_max_s: float = 900.0
    timeout_after_finish_s: float = 600.0
    menu_settle_s: float = 0.7
    colossus_step_s: float = 0.25
    colossus_menu_pause_s: float = 0.5
    colossus_tab_fast_s: float = 0.22
    colossus_tab_slow_s: float = 0.25
    colossus_max_taps: int = 30
    colossus_advance_s: float = 3.0
    colossus_retries: int = 5
    colossus_after_quit_s: float = 10.0
    colossus_open_s: float = 5.0
    colossus_tile_tol: int = 60
    colossus_class_steps: int = 8
    colossus_menu_timeout_s: float = 30.0
    notify_sound: bool = False
    notify_toast: bool = False
    manual_shift: bool = False
    shift_down_frac: float = 0.6
    shift_cooldown_s: float = 0.5
    shift_down_recheck_s: float = 1.5
    race_standard: bool = True
    race_online: bool = False
    race_timeattack: bool = False
    race_rivals: bool = False
    race_colossus: bool = False
    auto_stop_enabled: bool = False
    max_races: int = 0
    max_minutes: float = 0.0
    overlay_capturable: bool = False
    ui_scale: float = 1.0
    language: str = "en"
    game_language: str = "en"
    color_primary: str = "#C6F94A"
    color_secondary: str = "#F4A93B"
    color_text_dim: str = "#7E8A97"
    color_btn_bg: str = "#C6F94A"
    color_btn_fg: str = "#0A0D12"
    color_btn_hover: str = "#D4FB6E"
    color_bg: str = "#0B0D11"
    color_card: str = "#161B22"
    color_nav_active: str = "#1B2129"
    color_control: str = "#2A323C"
    match_score_logging: bool = False
    hotkey_start_stop: str = "<f8>"
    hotkey_panic: str = "<f9>"


_TUPLE_FIELDS = {
    name for name, f in Config.__dataclass_fields__.items()
    if isinstance(f.default, tuple)
}

_LEGACY_PALETTES = (
    {
        "color_primary": "#FF0028",
        "color_text_dim": "#7a3535",
        "color_btn_bg": "#0e0000",
        "color_btn_fg": "#FF0028",
        "color_btn_hover": "#2b0005",
        "color_bg": "#080000",
        "color_card": "#0e0000",
        "color_nav_active": "#170006",
        "color_control": "#3a2222",
    },
    {
        "color_primary": "#C6F542",
        "color_text_dim": "#8b937e",
        "color_btn_bg": "#C6F542",
        "color_btn_fg": "#0b0f08",
        "color_btn_hover": "#b6e636",
        "color_bg": "#080b06",
        "color_card": "#121810",
        "color_nav_active": "#161d10",
        "color_control": "#26301d",
    },
)


def _migrate_legacy_theme(cfg) -> bool:
    cur_primary = str(getattr(cfg, "color_primary", "")).upper()
    defaults = Config()
    for palette in _LEGACY_PALETTES:
        if cur_primary != palette["color_primary"].upper():
            continue
        changed = False
        for key, old in palette.items():
            cur = getattr(cfg, key, None)
            if isinstance(cur, str) and cur.upper() == old.upper():
                setattr(cfg, key, getattr(defaults, key))
                changed = True
        return changed
    return False


RACE_TYPES = ("standard", "online", "timeattack", "rivals", "colossus")
_RACE_FIELDS = {t: f"race_{t}" for t in RACE_TYPES}
_LAP_COUNTED_TYPES = {"timeattack", "rivals", "colossus"}


def active_race_type(cfg) -> str:
    for t in RACE_TYPES:
        if getattr(cfg, _RACE_FIELDS[t], False):
            return t
    return "online"


def race_counts_laps(cfg) -> bool:
    return active_race_type(cfg) in _LAP_COUNTED_TYPES


def load_config(path=DEFAULT_CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        cfg = Config()
        save_config(cfg, path)
        return cfg
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in _TUPLE_FIELDS:
        if key in data and isinstance(data[key], list):
            data[key] = tuple(data[key])
    known = set(Config.__dataclass_fields__)
    cfg = Config(**{k: v for k, v in data.items() if k in known})
    for key, value in data.items():
        if key not in known:
            setattr(cfg, key, value)
    migrated = _migrate_legacy_theme(cfg)
    if migrated or not known.issubset(data.keys()):
        save_config(cfg, path)
    return cfg


def save_config(cfg: Config, path=DEFAULT_CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    declared = set(Config.__dataclass_fields__)
    for key, value in cfg.__dict__.items():
        if key not in declared:
            data[key] = value
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")