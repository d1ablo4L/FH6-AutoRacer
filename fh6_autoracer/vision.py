from __future__ import annotations
import logging
from enum import Enum, auto
from pathlib import Path
import cv2
import numpy as np

_diag = logging.getLogger("tool_matchdiag")


# ── Stati riconosciuti (uno per template) ─────────────────────────────────────────
class Screen(Enum):
    UNKNOWN = auto()
    REGISTRATION = auto()
    CAR_SELECT = auto()
    GO = auto()
    INACTIVITY = auto()
    FINISH = auto()
    START = auto()
    RESTART = auto()
    RESTART_CONFIRM = auto()
    TIMEATTACK = auto()
    PAUSEMENU = auto()
    PAUSEMENU2 = auto()
    PAUSEMENU3 = auto()
    PAUSEMENU4 = auto()
    PAUSEMENU5 = auto()
    COLOSSUS1 = auto()
    COLOSSUS2 = auto()
    COLOSSUS3 = auto()
    COLOSSUS4 = auto()
    CHANGE_RIVAL = auto()
    CHANGE_RIVAL2 = auto()
    QUIT_RIVAL = auto()
    QUIT_RIVAL2 = auto()


TEMPLATE_SCREENS: dict[str, Screen] = {
    "registration.png": Screen.REGISTRATION,
    "car_select.png":   Screen.CAR_SELECT,
    "go.png":           Screen.GO,
    "go2.png":          Screen.GO,
    "go2rivals.png":    Screen.GO,
    "inactivity.png":   Screen.INACTIVITY,
    "finish.png":    Screen.FINISH,
    "finish2.png":   Screen.FINISH,
    "startrace.png":     Screen.START,
    "startrivals.png":   Screen.START,
    "restart.png":       Screen.RESTART,
    "restartconfirm.png": Screen.RESTART_CONFIRM,
    "timeattack.png":    Screen.TIMEATTACK,
    "pausemenu.png":     Screen.PAUSEMENU,
    "pausemenu2.png":    Screen.PAUSEMENU2,
    "pausemenu3.png":    Screen.PAUSEMENU3,
    "pausemenu4.png":    Screen.PAUSEMENU4,
    "pausemenu5.png":    Screen.PAUSEMENU5,
    "colossus1.png":     Screen.COLOSSUS1,
    "colossus2.png":     Screen.COLOSSUS2,
    "colossus3.png":     Screen.COLOSSUS3,
    "colossus4.png":     Screen.COLOSSUS4,
    "changerival.png":   Screen.CHANGE_RIVAL,
    "changerival2.png":  Screen.CHANGE_RIVAL2,
    "quitrival.png":     Screen.QUIT_RIVAL,
    "quitrival2.png":    Screen.QUIT_RIVAL2,
}

_COMMON_TEMPLATES = ("go.png", "inactivity.png")

RACE_TYPE_TEMPLATES: dict[str, tuple] = {
    "online":     ("registration.png", "car_select.png", "go2.png",
                   "finish.png", "finish2.png"),
    "standard":   ("startrace.png", "restart.png", "restartconfirm.png",
                   "go2.png", "finish.png", "finish2.png"),
    "rivals":     ("startrivals.png", "go2rivals.png"),
    "timeattack": ("timeattack.png",),
    "colossus":   ("startrivals.png", "go2rivals.png", "car_select.png",
                   "pausemenu.png", "pausemenu2.png", "pausemenu3.png",
                   "pausemenu4.png", "pausemenu5.png",
                   "colossus1.png", "colossus2.png",
                   "colossus3.png", "colossus4.png", "changerival.png",
                   "changerival2.png", "quitrival.png", "quitrival2.png"),
}

_OPTIONAL_TEMPLATES = {"finish2.png", "go2.png", "go2rivals.png"}

_FULL_RES_TEMPLATES = {"go2.png", "go2rivals.png", "inactivity.png",
                       "timeattack.png", "pausemenu.png", "pausemenu2.png",
                       "pausemenu3.png", "pausemenu4.png", "pausemenu5.png",
                       "colossus1.png",
                       "colossus2.png", "colossus3.png", "colossus4.png",
                       "changerival.png", "changerival2.png", "quitrival.png",
                       "quitrival2.png"}

SCREEN_THRESHOLD_KEYS: dict[Screen, str] = {
    Screen.REGISTRATION: "match_threshold_registration",
    Screen.CAR_SELECT:   "match_threshold_car_select",
    Screen.GO:           "match_threshold_go",
    Screen.INACTIVITY:   "match_threshold_inactivity",
    Screen.FINISH:    "match_threshold_finish",
    Screen.START:            "match_threshold_start",
    Screen.RESTART:          "match_threshold_restart",
    Screen.RESTART_CONFIRM:  "match_threshold_restart_confirm",
    Screen.TIMEATTACK:       "match_threshold_timeattack",
    Screen.PAUSEMENU:        "match_threshold_pausemenu",
    Screen.PAUSEMENU2:       "match_threshold_pausemenu",
    Screen.PAUSEMENU3:       "match_threshold_pausemenu",
    Screen.PAUSEMENU4:       "match_threshold_pausemenu",
    Screen.PAUSEMENU5:       "match_threshold_pausemenu",
    Screen.COLOSSUS1:        "match_threshold_colossus1",
    Screen.COLOSSUS2:        "match_threshold_colossus2",
    Screen.COLOSSUS3:        "match_threshold_colossus3",
    Screen.COLOSSUS4:        "match_threshold_colossus4",
    Screen.CHANGE_RIVAL:     "match_threshold_changerival",
    Screen.CHANGE_RIVAL2:    "match_threshold_changerival2",
    Screen.QUIT_RIVAL:       "match_threshold_quitrival",
    Screen.QUIT_RIVAL2:      "match_threshold_quitrival",
}

TEMPLATE_REGIONS: dict[str, tuple | None] = {
    "registration.png": (370, 111, 696, 190),
    "car_select.png":   (87, 78, 398, 163),
    "go.png":           (632, 292, 1314, 595),
    "go2.png":          (11, 100, 157, 188),
    "go2rivals.png":    (55, 236, 105, 259),
    "inactivity.png":   (710, 57, 1211, 177),
    "finish.png":    (337, 448, 1432, 718),
    "finish2.png":   (554, 505, 1418, 681),
    "startrace.png":      (60, 645, 285, 712),
    "startrivals.png":    (60, 645, 285, 705),
    "restart.png":        (245, 978, 390, 1035),
    "restartconfirm.png": (610, 385, 1310, 480),
    "timeattack.png":    (890, 922, 1030, 955),
    "pausemenu.png":     (530, 265, 810, 470),
    "pausemenu2.png":    (530, 265, 905, 465),
    "pausemenu3.png":    (530, 265, 845, 460),
    "pausemenu4.png":    (525, 258, 845, 475),
    "pausemenu5.png":    (1395, 550, 1575, 685),
    "colossus1.png":     (360, 195, 545, 295),
    "colossus2.png":     (75, 190, 380, 285),
    "colossus3.png":     (95, 175, 295, 275),
    "colossus4.png":     (110, 525, 790, 690),
    "changerival.png":   (340, 960, 570, 1050),
    "changerival2.png":  (160, 135, 450, 235),
    "quitrival.png":     (595, 390, 1325, 515),
    "quitrival2.png":    (595, 390, 1325, 515),
}

DEFAULT_MATCH_THRESHOLD = 0.80
_MATCH_SCALE = 0.5


def thresholds_from_config(cfg) -> dict:
    default = getattr(cfg, "match_threshold", DEFAULT_MATCH_THRESHOLD)
    out = {}
    for scr, key in SCREEN_THRESHOLD_KEYS.items():
        v = getattr(cfg, key, None)
        out[scr] = default if v is None else v
    return out


# ── Template matching ─────────────────────────────────────────────────────────────
def _gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _downscale(img: np.ndarray) -> np.ndarray:
    return cv2.resize(img, None, fx=_MATCH_SCALE, fy=_MATCH_SCALE,
                      interpolation=cv2.INTER_AREA)


def match_template(scene: np.ndarray, template: np.ndarray) -> float:
    s, t = _gray(scene), _gray(template)
    if t.shape[0] > s.shape[0] or t.shape[1] > s.shape[1]:
        return 0.0
    result = cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


_DOWNSCALED_TEMPLATES: dict[int, np.ndarray] = {}


def _small(tmpl: np.ndarray) -> np.ndarray:
    key = id(tmpl)
    cached = _DOWNSCALED_TEMPLATES.get(key)
    if cached is None:
        cached = _downscale(tmpl)
        _DOWNSCALED_TEMPLATES[key] = cached
    return cached


def _resolve_template(primary_dir, name, fallback_dir):
    p = Path(primary_dir) / name
    if p.exists():
        return p
    if fallback_dir is not None:
        fp = Path(fallback_dir) / name
        if fp.exists():
            return fp
    return p


def load_templates(template_dir, fallback_dir=None, race_type="online") -> dict:
    _DOWNSCALED_TEMPLATES.clear()
    names = list(_COMMON_TEMPLATES) + list(RACE_TYPE_TEMPLATES.get(race_type, ()))
    out = {}
    for name in names:
        path = _resolve_template(template_dir, name, fallback_dir)
        img = cv2.imread(str(path)) if path.exists() else None
        if img is None:
            if name in _OPTIONAL_TEMPLATES:
                logging.getLogger("tool").debug(
                    "optional template missing, skipping: %s", path)
                continue
            raise FileNotFoundError(f"missing template: {path}")
        gray = _gray(img)
        out[name] = gray
        _DOWNSCALED_TEMPLATES[id(gray)] = _downscale(gray)
    global _ENTER_TEMPLATE
    if race_type == "online":
        ep = _resolve_template(template_dir, ENTER_BUTTON_TEMPLATE_NAME, fallback_dir)
        eimg = cv2.imread(str(ep)) if ep.exists() else None
        if eimg is None:
            raise FileNotFoundError(f"missing template: {ep}")
        _ENTER_TEMPLATE = _gray(eimg)
    else:
        _ENTER_TEMPLATE = None
    return out


ENTER_BUTTON_TEMPLATE_NAME = "enter_button.png"
_ENTER_MATCH_DEFAULT = 0.75
_ENTER_TEMPLATE = None
ENTER_BUTTON_REGION = (36, 965, 217, 1046)


def _enter_score(scene_gray, region) -> float:
    if _ENTER_TEMPLATE is None:
        return 0.0
    x1, y1, x2, y2 = region
    h, w = scene_gray.shape[:2]
    crop = scene_gray[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    th, tw = _ENTER_TEMPLATE.shape[:2]
    if crop.shape[0] < th or crop.shape[1] < tw:
        return 0.0
    res = cv2.matchTemplate(crop, _ENTER_TEMPLATE, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(res)[1])


def enter_button_available(scene_bgr, threshold=_ENTER_MATCH_DEFAULT,
                           region=ENTER_BUTTON_REGION) -> bool:
    return _enter_score(_gray(scene_bgr), region) >= threshold


def screen_scores(scene_bgr, templates: dict, targets=None) -> dict:
    if targets is not None:
        names = {n for n, scr in TEMPLATE_SCREENS.items() if scr in targets}
        templates = {n: t for n, t in templates.items() if n in names}
    gray = _gray(scene_bgr)
    h, w = gray.shape[:2]
    scores = {}
    for name, tmpl in templates.items():
        region = TEMPLATE_REGIONS.get(name)
        if region:
            x1, y1, x2, y2 = region
            crop = gray[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        else:
            crop = gray
        if name in _FULL_RES_TEMPLATES:
            scores[name] = match_template(crop, tmpl)
        else:
            scores[name] = match_template(_downscale(crop), _small(tmpl))
    return scores


def identify_screen(scene_bgr, templates: dict, threshold: float,
                    targets=None, thresholds=None) -> Screen:
    scores = screen_scores(scene_bgr, templates, targets=targets)

    def _thr(name: str) -> float:
        if thresholds:
            return thresholds.get(TEMPLATE_SCREENS[name], threshold)
        return threshold

    best_screen, best_margin, found = Screen.UNKNOWN, 0.0, False
    for name, score in scores.items():
        t = _thr(name)
        if score >= t:
            margin = score - t
            if not found or margin > best_margin:
                best_screen, best_margin, found = (
                    TEMPLATE_SCREENS[name], margin, True)
    return best_screen


def log_match_diagnostics(scene_bgr, templates: dict, cfg) -> None:
    thresholds = thresholds_from_config(cfg)
    scores = screen_scores(scene_bgr, templates)
    parts = []
    for name, sc in scores.items():
        scr = TEMPLATE_SCREENS[name]
        thr = thresholds.get(scr, DEFAULT_MATCH_THRESHOLD)
        flag = "*" if sc >= thr else " "
        parts.append(f"{scr.name}:{sc:.3f}/{thr:.2f}{flag}")
    enter_thr = getattr(cfg, "match_threshold_enter_button", _ENTER_MATCH_DEFAULT)
    enter_sc = _enter_score(_gray(scene_bgr), ENTER_BUTTON_REGION)
    parts.append(
        f"ENTER_BTN:{enter_sc:.3f}/{enter_thr:.2f}"
        f"{'*' if enter_sc >= enter_thr else ' '}")
    _diag.info("match | %s", "  ".join(parts))


GEAR_REGION = (1575, 940, 1655, 1010)
GEAR_TEMPLATE_DIR_NAME = "_gears"
REVERSE = "R"
_GEAR_MIN_SCORE = 0.55

RPM_BAR = (1600, 1835, 1019, 1029)   # x1, x2, y1, y2
_RPM_MIN_CONTRAST = 25
_GEAR_MAGENTA_MIN = 100


def load_gear_templates(gears_dir) -> dict:
    out = {}
    base = Path(gears_dir)
    for n in range(1, 11):
        p = base / f"{n}.png"
        img = cv2.imread(str(p)) if p.exists() else None
        if img is not None:
            out[n] = _gray(img)
    rp = base / "r.png"
    rimg = cv2.imread(str(rp)) if rp.exists() else None
    if rimg is not None:
        out[REVERSE] = _gray(rimg)
    if not out:
        logging.getLogger("tool").warning(
            "no gear templates found in %s (manual shift downshift disabled)",
            base)
    return out


def read_gear(scene_bgr, gear_templates, min_score=_GEAR_MIN_SCORE):
    if not gear_templates:
        return None
    x1, y1, x2, y2 = GEAR_REGION
    g = _gray(scene_bgr)
    h, w = g.shape[:2]
    crop = g[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    best_n, best_s = None, 0.0
    for n, t in gear_templates.items():
        if t.shape[0] > crop.shape[0] or t.shape[1] > crop.shape[1]:
            continue
        res = cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED)
        s = float(cv2.minMaxLoc(res)[1])
        if s > best_s:
            best_n, best_s = n, s
    return best_n if best_s >= min_score else None


def read_rpm_fraction(scene_bgr):
    x1, x2, y1, y2 = RPM_BAR
    band = scene_bgr[y1:y2, x1:x2]
    if band.size == 0:
        return None
    prof = band.astype(np.float32).mean(axis=2).mean(axis=0)
    if prof.size < 8:
        return None
    k = 5
    pad = k // 2
    padded = np.pad(prof, pad, mode="edge")
    prof = np.convolve(padded, np.ones(k, np.float32) / k, mode="valid")
    edge = max(3, prof.size // 20)
    hi = float(prof[:edge].max())
    lo = float(prof.min())
    if hi - lo < _RPM_MIN_CONTRAST:
        return None
    thr = lo + (hi - lo) * 0.5
    below = np.where(prof < thr)[0]
    filled = prof.size if below.size == 0 else int(below[0])
    return filled / prof.size


def gear_over_rev(scene_bgr) -> bool:
    x1, y1, x2, y2 = GEAR_REGION
    b = scene_bgr[y1:y2, x1:x2].astype(np.int32)
    if b.size == 0:
        return False
    R, G, B = b[:, :, 2], b[:, :, 1], b[:, :, 0]
    return int(((R > 150) & (G < 100) & (B > 110)).sum()) > _GEAR_MAGENTA_MIN


LAP_DIGIT_DIR_NAME = "_lapdigits"
LAP_TIME_Y = (164, 194)
LAP_DIGIT_SLOTS = ((255, 275), (267, 287), (285, 305), (297, 317))
TA_DIGIT_DIR_NAME = "_tadigits"
TA_TIME_Y = (968, 1016)
TA_DIGIT_SLOTS = ((855, 891), (881, 917), (917, 953), (945, 981))
_TA_WHITE_MAX_SAT = 45
_TA_WHITE_MIN_PIXELS = 30

_LAP_DIGIT_MIN_SCORE = 0.5


def load_digit_set(digits_dir) -> dict:
    out = {}
    base = Path(digits_dir)
    for n in range(10):
        p = base / f"{n}.png"
        img = cv2.imread(str(p)) if p.exists() else None
        if img is not None:
            out[n] = _gray(img)
    if len(out) < 10:
        logging.getLogger("tool").warning(
            "digit templates incomplete in %s (lap count may fail)", base)
    return out


def load_lap_digits(digits_dir) -> dict:
    return load_digit_set(digits_dir)


def load_ta_digits(digits_dir) -> dict:
    return load_digit_set(digits_dir)


def _read_mmss(g, digits, y_band, slots, min_score):
    if len(digits) < 10:
        return None
    h, w = g.shape[:2]
    y1, y2 = y_band
    vals = []
    for x1, x2 in slots:
        crop = g[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        best_n, best_s = None, 0.0
        for n, t in digits.items():
            if t.shape[0] > crop.shape[0] or t.shape[1] > crop.shape[1]:
                continue
            r = cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED)
            s = float(cv2.minMaxLoc(r)[1])
            if s > best_s:
                best_n, best_s = n, s
        if best_n is None or best_s < min_score:
            return None
        vals.append(best_n)
    return (vals[0] * 10 + vals[1]) * 60 + (vals[2] * 10 + vals[3])


def read_lap_seconds(scene_bgr, lap_digits, min_score=_LAP_DIGIT_MIN_SCORE):
    return _read_mmss(_gray(scene_bgr), lap_digits,
                      LAP_TIME_Y, LAP_DIGIT_SLOTS, min_score)

COLOSSUS_TILE_BAND = (100, 720, 1850, 890)
_TILE_LIME_MIN = 60
_TILE_R_MIN = 800


def _band(scene_bgr):
    x1, y1, x2, y2 = COLOSSUS_TILE_BAND
    h, w = scene_bgr.shape[:2]
    return scene_bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)], x1


def _xrange(mask, x_off, min_px):
    if int(mask.sum()) < min_px:
        return None
    xs = np.where(mask.any(axis=0))[0]
    return (int(xs.min()) + x_off, int(xs.max()) + x_off)


def colossus_class_r_range(scene_bgr):
    c, x_off = _band(scene_bgr)
    if c.size == 0:
        return None
    c = c.astype(np.int16)
    b, g, r = c[:, :, 0], c[:, :, 1], c[:, :, 2]
    return _xrange((r > 140) & (b > 120) & (g < 110), x_off, _TILE_R_MIN)


def colossus_selection_range(scene_bgr):
    c, x_off = _band(scene_bgr)
    if c.size == 0:
        return None
    c = c.astype(np.int16)
    b, g, r = c[:, :, 0], c[:, :, 1], c[:, :, 2]
    return _xrange((g > 200) & (b < 120) & (r > 150), x_off, _TILE_LIME_MIN)


def colossus_selection_x(scene_bgr):
    rng = colossus_selection_range(scene_bgr)
    return None if rng is None else (rng[0] + rng[1]) // 2


def colossus_on_class_r(scene_bgr):
    sel = colossus_selection_range(scene_bgr)
    r = colossus_class_r_range(scene_bgr)
    if sel is None or r is None:
        return None
    overlap = min(sel[1], r[1]) - max(sel[0], r[0])
    sel_w = max(1, sel[1] - sel[0])
    return overlap > sel_w * 0.5


def read_ta_seconds(scene_bgr, ta_digits, min_score=_LAP_DIGIT_MIN_SCORE):
    if not _ta_text_is_white(scene_bgr):
        return None
    return _read_mmss(_gray(scene_bgr), ta_digits,
                      TA_TIME_Y, TA_DIGIT_SLOTS, min_score)


def _ta_text_is_white(scene_bgr) -> bool:
    x1, x2 = TA_DIGIT_SLOTS[0][0], TA_DIGIT_SLOTS[-1][1]
    y1, y2 = TA_TIME_Y
    h, w = scene_bgr.shape[:2]
    crop = scene_bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return False
    c = crop.astype(np.int16)
    mx = c.max(axis=2)
    mn = c.min(axis=2)
    bright = mx > 150
    if int(bright.sum()) < _TA_WHITE_MIN_PIXELS:
        return False
    return float((mx[bright] - mn[bright]).mean()) < _TA_WHITE_MAX_SAT