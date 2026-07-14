from __future__ import annotations
import logging
import sys
import threading
from pynput import keyboard
from . import capture, notifier, paths, vision
from .config import load_config, save_config, active_race_type
from .racer import GameIO, Loop
from .overlay import Overlay, normalize_race_type, normalize_game_language


def _setup_logging():
    log_path = paths.app_dir() / "logs" / "racer.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(message)s", "%H:%M:%S")
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root = logging.getLogger("tool")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    diag_path = log_path.parent / "match_diag.log"
    diag = logging.getLogger("tool_matchdiag")
    diag.setLevel(logging.INFO)
    diag.handlers.clear()
    diag_handler = logging.FileHandler(diag_path, mode="w", encoding="utf-8")
    diag_handler.setFormatter(fmt)
    diag.addHandler(diag_handler)
    diag.propagate = False
    return log_path


def _templates_for(cfg):
    log = logging.getLogger("tool")
    base = paths.resource_dir() / "templates"
    lang = getattr(cfg, "game_language", "en") or "en"
    race_type = active_race_type(cfg)

    def _leaf(root):
        sub = root / race_type
        return sub if sub.is_dir() else root

    en_dir = base / "en"
    lang_dir = base / lang
    if lang_dir.is_dir():
        primary = _leaf(lang_dir)
        en_leaf = _leaf(en_dir) if en_dir.is_dir() else None
        fallback = en_leaf if (en_leaf is not None and en_leaf != primary) else None
    elif en_dir.is_dir():
        log.warning("template folder for '%s' missing: using 'en'", lang)
        primary, fallback = _leaf(en_dir), None
    else:
        primary, fallback = _leaf(base), None
    log.info("loading templates for language '%s' / race type '%s' from %s",
             lang, race_type, primary)
    return vision.load_templates(primary, fallback_dir=fallback,
                                 race_type=race_type)


def main() -> None:
    log_path = _setup_logging()
    log = logging.getLogger("tool")
    log.info("AutoRacer started (log: %s)", log_path)
    config_path = paths.app_dir() / "config.json"
    cfg = load_config(config_path)
    if normalize_race_type(cfg):
        log.warning("saved race type is no longer selectable: falling back to online")
        save_config(cfg, config_path)
    if normalize_game_language(cfg):
        log.warning("saved game language is not supported in beta: falling back to 'en'")
        save_config(cfg, config_path)

    gear_templates = vision.load_gear_templates(
        paths.resource_dir() / "templates" / vision.GEAR_TEMPLATE_DIR_NAME)

    lap_digits = vision.load_lap_digits(
        paths.resource_dir() / "templates" / vision.LAP_DIGIT_DIR_NAME)

    ta_digits = vision.load_ta_digits(
        paths.resource_dir() / "templates" / vision.TA_DIGIT_DIR_NAME)

    overlay = Overlay(
        cfg=cfg,
        on_save=lambda c: save_config(c, config_path),
        hide_from_capture=not getattr(cfg, "overlay_capturable", False))

    overlay.attach_logging(logging.getLogger("tool"))

    io = None
    template_error = None
    try:
        templates = _templates_for(cfg)
        io = GameIO(cfg, templates, gear_templates, lap_digits, ta_digits)
    except Exception as e:
        template_error = str(e)
        log.exception("template loading failed")

    state = {"loop": None, "thread": None,
             "display_races": 0, "last_bot_races": 0, "carry_races": 0}
    races_log = paths.app_dir() / "logs" / "races.csv"

    def on_race(total):
        delta = max(0, total - state["last_bot_races"])
        state["display_races"] += delta
        state["last_bot_races"] = total
        overlay.set_races(state["display_races"])
        if delta > 0:
            notifier.log_race(races_log, "finished", state["display_races"])

    def start():
        if io is None:
            overlay.set_status("Templates missing: see racer.log")
            return
        if state["thread"] and state["thread"].is_alive():
            return
        capture.focus_window(capture.GAME_WINDOW_TITLE)
        carry = (state.get("carry_races", 0)
                 if getattr(cfg, "auto_stop_enabled", False) else 0)
        state["last_bot_races"] = carry
        loop = Loop(io, cfg,
                    on_race=on_race,
                    on_status=overlay.set_status,
                    on_running=overlay.set_running)
        loop.races_done = carry

        def _run_safe():
            outcome = None
            try:
                outcome = loop.run()
            except Exception:
                logging.getLogger("tool.main").exception("loop crash")
                try:
                    overlay.set_status("Crash: see racer.log")
                except Exception:
                    pass
            finally:
                if outcome == "auto_stop":
                    notifier.notify_autostop(
                        state["display_races"],
                        getattr(cfg, "notify_sound", True),
                        getattr(cfg, "notify_toast", True))
                state["carry_races"] = (
                    loop.races_done
                    if (outcome != "auto_stop"
                        and getattr(cfg, "auto_stop_enabled", False))
                    else 0)
                capture.stop_capture()
                if state.get("thread") is thread:
                    state["thread"] = None
                    state["loop"] = None
                try:
                    overlay.set_running(False)
                except Exception:
                    pass

        thread = threading.Thread(target=_run_safe, daemon=True)
        state["loop"], state["thread"] = loop, thread
        overlay.set_running(True)
        thread.start()

    def stop():
        loop = state.get("loop")
        if loop:
            loop.request_stop()

    def panic():
        stop()
        overlay.request_close()

    def toggle():
        if state["thread"] and state["thread"].is_alive():
            stop()
        else:
            start()

    hk_state = {"listener": None}

    def apply_hotkeys(config):
        old = hk_state.get("listener")
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        try:
            listener = keyboard.GlobalHotKeys({
                config.hotkey_start_stop: toggle,
                config.hotkey_panic: panic,
            })
            listener.start()
            hk_state["listener"] = listener
        except Exception:
            hk_state["listener"] = None

    apply_hotkeys(cfg)

    def suspend_hotkeys(active):
        if active:
            listener = hk_state.get("listener")
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
                hk_state["listener"] = None
        else:
            apply_hotkeys(cfg)

    overlay.set_hotkeys_changed(apply_hotkeys)
    overlay.set_capture_active_cb(suspend_hotkeys)

    def apply_game_language(config):
        nonlocal io, template_error
        try:
            new_templates = _templates_for(config)
        except Exception as e:
            template_error = str(e)
            logging.getLogger("tool").exception(
                "reloading templates for game language failed")
            overlay.set_status("Templates missing: see racer.log")
            return
        if io is None:
            io = GameIO(config, new_templates, gear_templates, lap_digits, ta_digits)
        else:
            io.templates = new_templates
        template_error = None
        logging.getLogger("tool").info(
            "templates reloaded for game language '%s'",
            getattr(config, "game_language", "en"))
        overlay.set_status("Idle")

    overlay.set_game_language_changed(apply_game_language)
    overlay.set_race_type_changed(apply_game_language)
    overlay.on_toggle(toggle)
    if template_error:
        overlay.set_status("Templates missing: see racer.log")
    else:
        overlay.set_status("Idle")
    try:
        overlay.run()
    finally:
        stop()
        listener = hk_state.get("listener")
        if listener is not None:
            listener.stop()


if __name__ == "__main__":
    main()