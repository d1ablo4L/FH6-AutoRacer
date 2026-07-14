from __future__ import annotations
import logging
import random
import time
from . import actions, capture, vision
from .vision import Screen
from .config import active_race_type

log = logging.getLogger("tool.racer")
_shiftdiag = logging.getLogger("tool_matchdiag")

_LAP_MIN_S = 8.0
_LAP_RESET_S = 2
_LAP_MIN_PROGRESS_S = 5

_TA_LOST_S = 15.0
_TA_RESET_MAX = 12


class GameIO:

    def __init__(self, cfg, templates, gear_templates=None, lap_digits=None,
                 ta_digits=None):
        self.cfg = cfg
        self.templates = templates
        self.gear_templates = gear_templates or {}
        self.lap_digits = lap_digits or {}
        self.ta_digits = ta_digits or {}
        self._last_screen = None
        self._memo_fid = None
        self._memo: dict = {}

    def _read(self, key, fn):
        frame, fid = capture.latest_frame(capture.GAME_WINDOW_TITLE)
        if fid != self._memo_fid:
            self._memo_fid = fid
            self._memo = {}
            if fid and getattr(self.cfg, "match_score_logging", False):
                try:
                    vision.log_match_diagnostics(
                        frame, self.templates, self.cfg)
                except Exception:
                    log.exception("match diagnostics failed")
        if key not in self._memo:
            self._memo[key] = fn(frame)
        return self._memo[key]

    def screen(self, targets=None) -> Screen:
        key = ("screen", frozenset(targets) if targets is not None else None)
        thresholds = vision.thresholds_from_config(self.cfg)
        fallback = getattr(self.cfg, "match_threshold",
                           vision.DEFAULT_MATCH_THRESHOLD)
        result = self._read(
            key,
            lambda f: vision.identify_screen(
                f, self.templates, fallback,
                targets=targets, thresholds=thresholds))
        if result != self._last_screen:
            log.info("screen -> %s", result.name)
            self._last_screen = result
        return result

    def focused(self) -> bool:
        return capture.is_game_focused(capture.GAME_WINDOW_TITLE)

    def enter_available(self) -> bool:
        th = getattr(self.cfg, "match_threshold_enter_button", 0.75)
        return self._read(
            "enter_btn", lambda f: vision.enter_button_available(f, th))

    def rpm_fraction(self):
        return self._read("rpm", lambda f: vision.read_rpm_fraction(f))

    def over_rev(self):
        return self._read("overrev", lambda f: vision.gear_over_rev(f))

    def gear(self):
        return self._read(
            "gear", lambda f: vision.read_gear(f, self.gear_templates))

    def lap_seconds(self):
        return self._read(
            "lapsec", lambda f: vision.read_lap_seconds(f, self.lap_digits))

    def ta_seconds(self):
        return self._read(
            "tasec", lambda f: vision.read_ta_seconds(f, self.ta_digits))

    def selection_x(self):
        return self._read("selx", vision.colossus_selection_x)

    def class_r_x(self):
        rng = self._read("rrange", vision.colossus_class_r_range)
        return None if rng is None else (rng[0] + rng[1]) // 2

    def on_class_r(self):
        return self._read("onr", vision.colossus_on_class_r)

    def press(self, name: str, times: int = 1) -> None:
        log.info("press %s%s", name, f" x{times}" if times > 1 else "")
        actions.tap_key(name, times,
                        self.cfg.key_hold_ms, self.cfg.between_keys_ms)
        self._memo = {}
        self._memo_fid = None

    def hold(self, name: str) -> None:
        log.info("hold %s", name)
        actions.hold_key(name)

    def release(self, name: str) -> None:
        log.info("release %s", name)
        actions.release_key(name)


class Loop:
    def __init__(self, io, cfg, clock=time.monotonic, sleeper=time.sleep,
                 on_race=None, on_status=None, on_running=None):
        self.io = io
        self.cfg = cfg
        self.clock = clock
        self.sleeper = sleeper
        self.on_race = on_race
        self.on_status = on_status
        self.on_running = on_running
        self.races_done = 0
        self.started_at = None
        self._stop = False
        self._driving = False
        self._last_status = None
        self._last_shift_at = 0.0
        self._down_since = 0.0
        self._gear_est = 1
        self._last_shift_diag = 0.0

    def request_stop(self) -> None:
        self._stop = True

    def _status(self, msg: str, **kwargs) -> None:
        key = (msg, tuple(sorted(kwargs.items())))
        if key == self._last_status:
            return
        self._last_status = key
        shown = msg.format(**kwargs) if kwargs else msg
        log.info("[status] %s", shown)
        if self.on_status:
            self.on_status(msg, kwargs)

    def _race_completed(self) -> None:
        self.races_done += 1
        log.info("race completed: %d", self.races_done)
        if self.on_race:
            self.on_race(self.races_done)

    def _poll_delay(self) -> None:
        lo, hi = self.cfg.poll_interval_ms
        self.sleeper(random.uniform(lo, hi) / 1000.0)

    def _guard_focus(self) -> None:
        if self.io.focused():
            return
        self._release_drive()
        self._status("Paused: FH6 not in foreground")
        auto = getattr(self.cfg, "auto_focus", True)
        deadline = self.clock() + 5.0
        while not self.io.focused() and not self._stop:
            if auto:
                capture.focus_window(capture.GAME_WINDOW_TITLE)
            if self.clock() >= deadline:
                break
            self.sleeper(0.2)

    def _press(self, name: str, times: int = 1) -> None:
        self._guard_focus()
        if self._stop:
            return
        self.io.press(name, times)

    def _settle(self) -> None:
        if self._stop:
            return
        self.sleeper(max(0.0, getattr(self.cfg, "menu_settle_s", 0.7)))

    # ── gestione "tieni premuto W" ────────────────────────────────────────────
    def _hold_drive(self) -> None:
        if not self._driving:
            self.io.hold("w")
            self._driving = True

    def _release_drive(self) -> None:
        if self._driving:
            self.io.release("w")
            self._driving = False

    # ── cambio manuale (HUD digitale) ─────────────────────────────────────────
    def _maybe_shift(self) -> None:
        if not getattr(self.cfg, "manual_shift", False):
            return
        now = self.clock()
        try:
            over_rev = self.io.over_rev()
            frac = self.io.rpm_fraction()
        except Exception:
            return
        if getattr(self.cfg, "match_score_logging", False):
            _shiftdiag.info(
                "shift | frac=%s over_rev=%s gear_read=%s gear_est=%s "
                "down_thr=%.2f",
                "n/a" if frac is None else "%.2f" % frac,
                over_rev, self.io.gear(), self._gear_est,
                getattr(self.cfg, "shift_down_frac", 0.42))
        if now < self._last_shift_at + getattr(self.cfg, "shift_cooldown_s", 0.5):
            return
        if self.io.gear() == vision.REVERSE:
            self.io.press("e")
            self._gear_est = 1
            self._last_shift_at = now
            self._down_since = 0.0
            return
        if over_rev:
            self.io.press("e")
            self._gear_est = min(self._gear_est + 1, 10)
            self._last_shift_at = now
            self._down_since = 0.0
            return
        if frac is None:
            self._down_since = 0.0
            return
        if frac > getattr(self.cfg, "shift_down_frac", 0.42):
            self._down_since = 0.0
            return
        recheck = getattr(self.cfg, "shift_down_recheck_s", 3.0)
        if self._down_since and (now - self._down_since) < recheck:
            return
        read = self.io.gear()
        if isinstance(read, int):
            self._gear_est = read
        if self._gear_est > 1:
            self.io.press("q")
            self._gear_est = max(self._gear_est - 1, 1)
            self._last_shift_at = now
        self._down_since = now

    # ── attese ────────────────────────────────────────────────────────────────
    def _wait_for(self, screens: set, timeout: float):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            if self._stop:
                return None
            s = self.io.screen(targets=screens)
            if s in screens:
                return s
            self._poll_delay()
        return None

    def _auto_stop_reached(self) -> bool:
        cfg = self.cfg
        if not cfg.auto_stop_enabled:
            return False
        if cfg.max_races and self.races_done >= cfg.max_races:
            return True
        if cfg.max_minutes:
            elapsed_min = (self.clock() - self.started_at) / 60.0
            if elapsed_min >= cfg.max_minutes:
                return True
        return False

    # ── fasi (dispatch sulla schermata corrente) ─────────────────────────────
    def _online_handle_registration(self) -> None:
        if self.io.enter_available():
            self._status("Players found, enrolling")
            self._press("enter")
            self._wait_for({Screen.CAR_SELECT}, self.cfg.enroll_retry_s)
        else:
            self._status("Waiting for players")
            self._poll_delay()

    def _online_choose_car(self) -> None:
        self._status("Selecting car and color")
        n = max(1, int(self.cfg.car_select_enter_count))
        for _ in range(n):
            if self._stop:
                return
            self._press("enter")
            self.sleeper(self.cfg.car_select_enter_gap_s)
        deadline = self.clock() + self.cfg.timeout_race_start_s
        while self.clock() < deadline and not self._stop:
            if self.io.screen(targets={Screen.CAR_SELECT}) != Screen.CAR_SELECT:
                return
            self._poll_delay()

    def _online_drive_until_finish(self, end_targets=None) -> bool:
        self._status("Race in progress")
        self._gear_est = 1
        auto = getattr(self.cfg, "auto_focus", True)
        d_cooldown_until = 0.0
        focus_retry_until = 0.0
        deadline = self.clock() + self.cfg.timeout_race_max_s
        if end_targets is None:
            end_targets = {Screen.REGISTRATION, Screen.CAR_SELECT}
        scan_targets = {Screen.FINISH, Screen.INACTIVITY} | end_targets
        hud_watchdog = "go2.png" in getattr(self.io, "templates", {})
        last_race_seen = self.clock()
        GO_LOST_S = 15.0
        try:
            while self.clock() < deadline and not self._stop:
                if self.io.focused():
                    self._hold_drive()
                    base_status = "Race in progress"
                    self._maybe_shift()
                else:
                    self._release_drive()
                    if auto and self.clock() >= focus_retry_until:
                        capture.focus_window(capture.GAME_WINDOW_TITLE)
                        focus_retry_until = self.clock() + 0.7
                    base_status = "Paused: FH6 not in foreground"
                self._status(base_status)
                s = self.io.screen(targets=scan_targets)
                if s == Screen.FINISH:
                    self._status("Race finished")
                    self._race_completed()
                    return True
                if s in end_targets:
                    self._status("Race finished")
                    self._race_completed()
                    return True
                if s == Screen.INACTIVITY:
                    last_race_seen = self.clock()
                    if self.clock() >= d_cooldown_until:
                        self._status("Inactivity warning: pressing D")
                        self.io.press("d", self.cfg.d_taps_on_inactivity)
                        d_cooldown_until = (self.clock()
                                            + self.cfg.inactivity_cooldown_s)
                        self._status(base_status)
                if hud_watchdog:
                    if self.io.screen(targets={Screen.GO}) == Screen.GO:
                        last_race_seen = self.clock()
                    if (self.clock() - last_race_seen) >= GO_LOST_S:
                        self._status("Race finished")
                        self._race_completed()
                        return True
                self._poll_delay()
            return False
        finally:
            self._release_drive()

    def _online_drive_remaining_races(self) -> None:
        targets = {Screen.GO, Screen.INACTIVITY,
                   Screen.REGISTRATION, Screen.CAR_SELECT}
        while not self._stop:
            if self._auto_stop_reached():
                return
            self._status("Waiting for the next race")
            s = self._wait_for(targets, self.cfg.timeout_after_finish_s)
            if s in (Screen.GO, Screen.INACTIVITY):
                self._online_drive_until_finish()
                continue
            return

    # ── dispatcher  ───────────────────────────────────────────
    def run(self) -> str:
        rt = active_race_type(self.cfg)
        if rt == "standard":
            return self._run_standard()
        if rt == "rivals":
            return self._run_rivals()
        if rt == "timeattack":
            return self._run_timeattack()
        if rt == "colossus":
            return self._run_colossus()
        return self._run_online()

    # ── ONLINE ────────────────────────────────────
    def _run_online(self) -> str:
        self.started_at = self.clock()
        log.info("=== loop started ===")
        self._status("Running")
        if self.on_running:
            self.on_running(True)
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    self._status("Auto-stop limit reached")
                    return "auto_stop"

                screen = self.io.screen()

                if screen == Screen.REGISTRATION:
                    self._online_handle_registration()
                elif screen == Screen.CAR_SELECT:
                    self._online_choose_car()
                    self._online_drive_remaining_races()
                elif screen in (Screen.GO, Screen.INACTIVITY):
                    self._online_drive_until_finish()
                    self._online_drive_remaining_races()
                elif screen == Screen.FINISH:
                    self._online_drive_remaining_races()
                else:
                    self._poll_delay()

                self.sleeper(self.cfg.loop_pace_s)
            self._status("Stopped")
            return "stopped"
        finally:
            self._release_drive()
            if self.on_running:
                self.on_running(False)

    # ── fasi delle gare STANDARD ──────────────────────────────────────────────
    def _standard_start_race(self) -> None:
        self._status("Starting the race")
        self._settle()
        self._press("enter")
        self._wait_for({Screen.GO, Screen.INACTIVITY},
                       self.cfg.timeout_race_start_s)

    def _standard_restart_sequence(self) -> None:
        if self._wait_for({Screen.RESTART},
                          self.cfg.timeout_after_finish_s) != Screen.RESTART:
            return
        self._status("Restarting event")
        self._settle()
        self._press("x")
        if self._wait_for({Screen.RESTART_CONFIRM},
                          self.cfg.timeout_race_start_s) == Screen.RESTART_CONFIRM:
            self._settle()
            self._press("enter")
            self._wait_for({Screen.START, Screen.GO, Screen.INACTIVITY},
                           self.cfg.timeout_race_start_s)

    # ── STANDARD ──────────────────────────────────
    def _run_standard(self) -> str:
        self.started_at = self.clock()
        log.info("=== standard loop started ===")
        self._status("Running")
        if self.on_running:
            self.on_running(True)
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    self._status("Auto-stop limit reached")
                    return "auto_stop"

                screen = self.io.screen()

                if screen == Screen.START:
                    self._standard_start_race()
                elif screen in (Screen.GO, Screen.INACTIVITY):
                    self._online_drive_until_finish({Screen.RESTART})
                    self._standard_restart_sequence()
                elif screen in (Screen.FINISH, Screen.RESTART):
                    self._standard_restart_sequence()
                elif screen == Screen.RESTART_CONFIRM:
                    self._settle()
                    self._press("enter")
                    self._wait_for({Screen.GO, Screen.INACTIVITY},
                                   self.cfg.timeout_race_start_s)
                else:
                    self._poll_delay()

                self.sleeper(self.cfg.loop_pace_s)
            self._status("Stopped")
            return "stopped"
        finally:
            self._release_drive()
            if self.on_running:
                self.on_running(False)

    # ──  RIVALS ────────────────────────────────
    def _rivals_start_race(self) -> None:
        self._status("Starting the race")
        self._settle()
        self._press("enter")
        self._wait_for({Screen.GO, Screen.INACTIVITY},
                       self.cfg.timeout_race_start_s)

    def _rivals_drive(self) -> None:
        self._status("Race in progress")
        self._gear_est = 1
        auto = getattr(self.cfg, "auto_focus", True)
        d_cooldown_until = 0.0
        focus_retry_until = 0.0
        prev_total = None
        last_count = 0.0
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    return
                if self.io.focused():
                    self._hold_drive()
                    base_status = "Race in progress"
                    self._maybe_shift()
                else:
                    self._release_drive()
                    if auto and self.clock() >= focus_retry_until:
                        capture.focus_window(capture.GAME_WINDOW_TITLE)
                        focus_retry_until = self.clock() + 0.7
                    base_status = "Paused: FH6 not in foreground"
                self._status(base_status)
                now = self.clock()
                if self.io.screen(targets={Screen.INACTIVITY}) == Screen.INACTIVITY:
                    if now >= d_cooldown_until:
                        self._status("Inactivity warning: pressing D")
                        self.io.press("d", self.cfg.d_taps_on_inactivity)
                        d_cooldown_until = now + self.cfg.inactivity_cooldown_s
                        self._status(base_status)
                total = self.io.lap_seconds()
                if total is not None:
                    if (prev_total is not None
                            and prev_total >= _LAP_MIN_PROGRESS_S
                            and total <= _LAP_RESET_S
                            and (now - last_count) >= _LAP_MIN_S):
                        self._status("Lap completed")
                        self._race_completed()
                        self._status(base_status)
                        last_count = now
                    prev_total = total
                self._poll_delay()
        finally:
            self._release_drive()

    def _run_rivals(self) -> str:
        self.started_at = self.clock()
        log.info("=== rivals loop started ===")
        self._status("Running")
        if self.on_running:
            self.on_running(True)
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    self._status("Auto-stop limit reached")
                    return "auto_stop"

                screen = self.io.screen()

                if screen == Screen.START:
                    self._rivals_start_race()
                    self._rivals_drive()
                elif screen in (Screen.GO, Screen.INACTIVITY):
                    self._rivals_drive()
                else:
                    self._poll_delay()

                self.sleeper(self.cfg.loop_pace_s)
            self._status("Stopped")
            return "stopped"
        finally:
            self._release_drive()
            if self.on_running:
                self.on_running(False)

    # ── COLOSSUS ─────────────────────────────────────────────
    def _colossus_tap(self, name: str, times: int = 1) -> None:
        step = max(0.0, getattr(self.cfg, "colossus_step_s", 0.6))
        for _ in range(times):
            if self._stop:
                return
            self._press(name)
            self.sleeper(step)

    def _colossus_long_pause(self) -> None:
        self.sleeper(max(0.0, getattr(self.cfg, "colossus_menu_pause_s", 1.5)))

    def _colossus_key_until(self, from_screens: set, key: str,
                            next_screens: set, what: str) -> bool:
        attempts = max(1, int(getattr(self.cfg, "colossus_retries", 4)))
        wait_s = max(1.0, getattr(self.cfg, "colossus_advance_s", 6.0))
        timeout = getattr(self.cfg, "colossus_menu_timeout_s", 30.0)
        for i in range(attempts):
            if self._stop:
                return False
            self._colossus_long_pause()
            self._colossus_tap(key, 1)
            if self._wait_for(next_screens, wait_s) is not None:
                return True
            if self.io.screen(targets=from_screens) not in from_screens:
                return self._wait_for(next_screens, timeout) is not None
            log.info("colossus: no response for %s, retrying %s (%d/%d)",
                     what, key, i + 1, attempts)
        return False

    def _colossus_enter_until(self, from_screens: set, next_screens: set,
                              what: str) -> bool:
        return self._colossus_key_until(from_screens, "enter", next_screens, what)

    def _colossus_open_pause(self, target: set, what: str) -> bool:
        attempts = max(1, int(getattr(self.cfg, "colossus_retries", 5)))
        wait_s = max(2.0, getattr(self.cfg, "colossus_open_s", 5.0))
        for i in range(attempts):
            if self._stop:
                return False
            if self.io.screen(targets=target) in target:
                return True
            self._colossus_tap("esc", 1)
            if self._wait_for(target, wait_s) is not None:
                return True
            log.info("colossus: %s did not open, retrying esc (%d/%d)",
                     what, i + 1, attempts)
        return False

    def _colossus_d_until(self, target: set, pause_s: float, what: str) -> bool:
        max_taps = max(1, int(getattr(self.cfg, "colossus_max_taps", 12)))
        for i in range(max_taps):
            if self._stop:
                return False
            if self.io.screen(targets=target) in target:
                return True
            self._press("d")
            if self._wait_for(target, pause_s) is not None:
                return True
        found = self.io.screen(targets=target) in target
        if not found:
            log.info("colossus: %s not reached after %d taps", what, max_taps)
        return found

    def _colossus_setup(self) -> bool:
        timeout = getattr(self.cfg, "colossus_menu_timeout_s", 30.0)
        fast = max(0.1, getattr(self.cfg, "colossus_tab_fast_s", 0.35))
        slow = max(0.1, getattr(self.cfg, "colossus_tab_slow_s", 0.6))
        self._release_drive()
        self._status("Colossus: opening pause menu")
        pages = {Screen.PAUSEMENU, Screen.PAUSEMENU2, Screen.PAUSEMENU3,
                 Screen.PAUSEMENU4}
        if not self._colossus_open_pause(pages, "pause menu"):
            return False

        self._status("Colossus: pause menu (online)")
        if not self._colossus_d_until({Screen.PAUSEMENU4}, slow, "online page"):
            return False

        self._status("Colossus: selecting Rivals")
        critical = max(0.3, getattr(self.cfg, "colossus_menu_pause_s", 0.5))
        self.sleeper(critical)
        self._press("d")
        self.sleeper(critical)
        self._press("s")
        self.sleeper(critical)
        if not self._colossus_enter_until({Screen.PAUSEMENU4}, {Screen.COLOSSUS1},
                                          "rivals menu"):
            return False

        self._status("Colossus: Rivals menu")
        if not self._colossus_enter_until({Screen.COLOSSUS1}, {Screen.COLOSSUS2},
                                          "horizon rivals"):
            return False

        self._status("Colossus: Horizon Rivals")
        if not self._colossus_enter_until({Screen.COLOSSUS2}, {Screen.COLOSSUS3},
                                          "routes"):
            return False

        self._status("Colossus: routes")
        self._colossus_long_pause()
        self._colossus_tap("a", 2)
        if not self._colossus_enter_until({Screen.COLOSSUS3}, {Screen.COLOSSUS4},
                                          "event page"):
            return False

        self._status("Colossus: event page")
        deadline = self.clock() + timeout
        r_x = None
        while r_x is None:
            if self._stop or self.clock() >= deadline:
                log.info("colossus: class R tile never appeared")
                return False
            r_x = self.io.class_r_x()
            if r_x is None:
                self._poll_delay()

        steps = max(2, int(getattr(self.cfg, "colossus_class_steps", 8)))
        on_r = False
        for i in range(steps):
            if self._stop:
                return False
            ok = self.io.on_class_r()
            if ok:
                on_r = True
                break
            if ok is None:
                self._poll_delay()
                continue
            x = self.io.selection_x()
            if x is None:
                self._poll_delay()
                continue
            self._press("a" if x <= r_x else "d")
            self._colossus_long_pause()

        if not on_r:
            log.info("colossus: class R not confirmed, restarting setup")
            return False

        self._status("Colossus: changing rival")
        if self._wait_for({Screen.CHANGE_RIVAL}, timeout) is None:
            return False
        if not self._colossus_key_until({Screen.CHANGE_RIVAL}, "y",
                                        {Screen.CHANGE_RIVAL2}, "rival list"):
            return False

        self._status("Colossus: rival list")
        if not self._colossus_enter_until({Screen.CHANGE_RIVAL2},
                                          {Screen.CHANGE_RIVAL},
                                          "rival loaded"):
            return False

        self._status("Colossus: confirming event")
        if not self._colossus_enter_until({Screen.CHANGE_RIVAL},
                                          {Screen.CAR_SELECT}, "car select"):
            return False

        self._status("Colossus: car select")
        return self._colossus_enter_until({Screen.CAR_SELECT}, {Screen.START},
                                         "start rivals")

    def _colossus_drive(self) -> bool:
        self._status("Race in progress")
        self._gear_est = 1
        auto = getattr(self.cfg, "auto_focus", True)
        d_cooldown_until = 0.0
        focus_retry_until = 0.0
        prev_total = None
        started = self.clock()
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    return False
                if self.io.focused():
                    self._hold_drive()
                    base_status = "Race in progress"
                    self._maybe_shift()
                else:
                    self._release_drive()
                    if auto and self.clock() >= focus_retry_until:
                        capture.focus_window(capture.GAME_WINDOW_TITLE)
                        focus_retry_until = self.clock() + 0.7
                    base_status = "Paused: FH6 not in foreground"
                self._status(base_status)
                now = self.clock()
                if self.io.screen(targets={Screen.INACTIVITY}) == Screen.INACTIVITY:
                    if now >= d_cooldown_until:
                        self._status("Inactivity warning: pressing D")
                        self.io.press("d", self.cfg.d_taps_on_inactivity)
                        d_cooldown_until = now + self.cfg.inactivity_cooldown_s
                        self._status(base_status)
                total = self.io.lap_seconds()
                if total is not None:
                    if (prev_total is not None
                            and prev_total >= _LAP_MIN_PROGRESS_S
                            and total <= _LAP_RESET_S
                            and (now - started) >= _LAP_MIN_S):
                        self._status("Lap completed")
                        self._race_completed()
                        return True
                    prev_total = total
                self._poll_delay()
            return False
        finally:
            self._release_drive()

    def _colossus_quit(self) -> None:
        self._release_drive()
        self._status("Colossus: quitting event")
        if not self._colossus_open_pause({Screen.PAUSEMENU5}, "race pause menu"):
            return
        slow = max(0.1, getattr(self.cfg, "colossus_tab_slow_s", 1.5))
        self.sleeper(slow)
        self._press("d")
        self.sleeper(slow)
        if not self._colossus_enter_until({Screen.PAUSEMENU5},
                                          {Screen.QUIT_RIVAL, Screen.QUIT_RIVAL2},
                                          "quit confirm"):
            return
        self._settle()
        self._colossus_tap("enter", 1)
        self._status("Colossus: returning to freeroam")
        self.sleeper(max(0.0, getattr(self.cfg, "colossus_after_quit_s", 15.0)))

    def _run_colossus(self) -> str:
        self.started_at = self.clock()
        log.info("=== colossus loop started ===")
        self._status("Running")
        if self.on_running:
            self.on_running(True)
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    self._status("Auto-stop limit reached")
                    return "auto_stop"

                screen = self.io.screen()

                if screen == Screen.START:
                    self._rivals_start_race()
                    if self._colossus_drive():
                        self._colossus_quit()
                elif screen in (Screen.GO, Screen.INACTIVITY):
                    if self._colossus_drive():
                        self._colossus_quit()
                else:
                    if self._colossus_setup():
                        self._rivals_start_race()
                        if self._colossus_drive():
                            self._colossus_quit()

                self.sleeper(self.cfg.loop_pace_s)
            self._status("Stopped")
            return "stopped"
        finally:
            self._release_drive()
            if self.on_running:
                self.on_running(False)

    # ── TIME ATTACK ──────────────────────────────────────────
    def _run_timeattack(self) -> str:
        self.started_at = self.clock()
        log.info("=== timeattack loop started ===")
        self._status("Running")
        if self.on_running:
            self.on_running(True)
        auto = getattr(self.cfg, "auto_focus", True)
        d_cooldown_until = 0.0
        focus_retry_until = 0.0
        prev_total = None
        last_count = 0.0
        last_seen = self.clock()
        seen_ever = False
        start_deadline = self.clock() + self.cfg.timeout_race_start_s
        self._gear_est = 1
        try:
            while not self._stop:
                if self._auto_stop_reached():
                    self._status("Auto-stop limit reached")
                    return "auto_stop"
                if self.io.focused():
                    self._hold_drive()
                    base_status = ("Race in progress" if seen_ever
                                   else "Driving to start line")
                    self._maybe_shift()
                else:
                    self._release_drive()
                    if auto and self.clock() >= focus_retry_until:
                        capture.focus_window(capture.GAME_WINDOW_TITLE)
                        focus_retry_until = self.clock() + 0.7
                    base_status = "Paused: FH6 not in foreground"
                self._status(base_status)
                now = self.clock()
                if self.io.screen(targets={Screen.TIMEATTACK}) == Screen.TIMEATTACK:
                    last_seen = now
                    seen_ever = True
                elif seen_ever and (now - last_seen) >= _TA_LOST_S:
                    self._status("Race ended")
                    return "stopped"
                elif not seen_ever and now >= start_deadline:
                    self._status("Start line not detected")
                    return "stopped"
                if self.io.screen(targets={Screen.INACTIVITY}) == Screen.INACTIVITY:
                    if now >= d_cooldown_until:
                        self._status("Inactivity warning: pressing D")
                        self.io.press("d", self.cfg.d_taps_on_inactivity)
                        d_cooldown_until = now + self.cfg.inactivity_cooldown_s
                        self._status(base_status)
                if seen_ever:
                    total = self.io.ta_seconds()
                    if total is not None:
                        if (prev_total is not None
                                and prev_total > _TA_RESET_MAX
                                and total <= _TA_RESET_MAX
                                and (now - last_count) >= _LAP_MIN_S):
                            self._status("Lap completed")
                            self._race_completed()
                            self._status(base_status)
                            last_count = now
                        prev_total = total
                self._poll_delay()
            self._status("Stopped")
            return "stopped"
        finally:
            self._release_drive()
            if self.on_running:
                self.on_running(False)