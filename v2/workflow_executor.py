"""
Workflow executor - OCR-based dynamic button finding, multi-display, dropdown support.
Each rule carries its own display index and optional search region.
"""
import time
import threading
import pyautogui

from ocr_engine import (
    get_all_displays, capture_display,
    screenshot_to_global, ocr_words,
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


# ── Rule resolver ─────────────────────────────────────────────────────────────

def resolve(rule: dict, words: list[dict]) -> tuple[int, int] | None:
    """
    Locate a control using an OCR rule against a word list.
    Returns screenshot pixel coordinates (sx, sy), or None if not found.
    words are already offset to full-image space when region OCR is used.
    """
    method = rule.get('method', '')

    if method == 'ocr_label_below':
        label    = rule['label']
        min_y    = rule.get('min_y', 0)
        offset_y = rule.get('offset_y', 30)
        w = next((w for w in words
                  if w['text'].strip().lower() == label.strip().lower()
                  and w['y'] > min_y), None)
        if not w:
            return None
        return w['x'] + w['w'] // 2, w['y'] + w['h'] + offset_y

    if method == 'ocr_label_offset':
        label    = rule['label']
        min_y    = rule.get('min_y', 0)
        offset_y = rule.get('offset_y', 75)
        w = next((w for w in words
                  if w['text'].strip().lower() == label.strip().lower()
                  and w['y'] > min_y), None)
        if not w:
            return None
        return w['x'] + w['w'] // 2, w['y'] + offset_y

    if method == 'ocr_right_of':
        anchor   = rule['anchor']
        offset_x = rule.get('offset_x', 120)
        w = next((w for w in words
                  if anchor.lower() in w['text'].lower()), None)
        if not w:
            return None
        return w['x'] + w['w'] + offset_x, w['y'] + w['h'] // 2

    return None


# ── Executor ──────────────────────────────────────────────────────────────────

class WorkflowExecutor:

    def __init__(self, button_rules: dict, data_loader, steps: list,
                 display_index: int = 1, callback=None):
        self.button_rules  = button_rules
        self.data_loader   = data_loader
        self.steps         = steps
        self.display_index = display_index   # fallback if rule has no display
        self.callback      = callback

        self.is_running  = False
        self.should_stop = False
        self._thread     = None

        # Keep all display info for coordinate conversion
        all_displays = get_all_displays()
        self._displays: dict[int, dict] = {d['index']: d for d in all_displays}
        self._default_display = (
            self._displays.get(display_index) or
            all_displays[-1]
        )

    def start(self, start_row: int = 0) -> bool:
        if self.is_running:
            return False
        self.is_running  = True
        self.should_stop = False
        self._thread = threading.Thread(target=self._run,
                                        args=(start_row,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.should_stop = True
        self.is_running  = False

    def is_executing(self) -> bool:
        return self.is_running

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self, start_row: int):
        try:
            total = self.data_loader.get_row_count()
            self._log(0, total, f"Starting execution — {total} rows total")

            for idx in range(start_row, total):
                if self.should_stop:
                    break
                row = self.data_loader.get_row(idx)
                self._log(idx + 1, total, f"Row {idx + 1}/{total}")
                self._process_row(row, idx, total)
                if not self.should_stop:
                    time.sleep(1.5)

            self.is_running = False
            self._log(total, total, "Stopped" if self.should_stop else "Completed")
        except Exception as e:
            self.is_running = False
            self._log(0, 0, f"Error: {e}")

    def _process_row(self, row: dict, idx: int, total: int):
        for step in self.steps:
            if self.should_stop:
                return
            self._run_step(step, row, idx, total)

    def _run_step(self, step: dict, row: dict, idx: int, total: int):
        stype  = step.get('type')
        target = step.get('target')
        col    = step.get('excel_col')
        value  = str(row.get(col, '') or '') if col else None
        if value in (None, 'None', ''):
            value = None

        if stype == 'click_type':
            gx, gy = self._click(target)
            if gx is None:
                return
            self._log(idx+1, total, f"  click  {target} ({gx},{gy}) | {col}={value!r}")
            time.sleep(0.2)
            self._type(value)

        elif stype == 'tab_type':
            self._log(idx+1, total, f"  tab    {col}={value!r}")
            pyautogui.press('tab')
            time.sleep(0.1)
            if value:
                self._type(value)

        elif stype == 'select_type':
            rule = self.button_rules.get(target)
            gx, gy = self._click(target)
            if gx is None:
                return
            self._log(idx+1, total, f"  select {target} ({gx},{gy}) | {col}={value!r}")
            time.sleep(0.4)
            self._select_option(value, rule)

        elif stype == 'click_only':
            gx, gy = self._click(target, double=False)
            if gx is None:
                return
            self._log(idx+1, total, f"  click  {target} ({gx},{gy})")
            time.sleep(0.3)

        elif stype == 'delay':
            time.sleep(float(step.get('seconds', 1)))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _display_for(self, rule: dict | None) -> dict:
        """Return the display dict for a rule (falls back to default)."""
        if rule:
            idx = rule.get('display', self.display_index)
        else:
            idx = self.display_index
        return self._displays.get(idx, self._default_display)

    def _capture_for(self, rule: dict | None):
        """Capture the display specified in rule, run OCR with optional region."""
        display = self._display_for(rule)
        idx = display['index']
        img = capture_display(idx)
        display['_img_w'] = img.width
        display['_img_h'] = img.height
        region = tuple(rule['region']) if rule and rule.get('region') else None
        words = ocr_words(img, region=region)
        return img, display, words

    def _click(self, target: str, double: bool = True) -> tuple[int | None, int | None]:
        rule = self.button_rules.get(target)
        if not rule:
            self._log(0, 0, f"  warn: no rule for '{target}'")
            return None, None

        _img, display, words = self._capture_for(rule)
        pos = resolve(rule, words)
        if not pos:
            self._log(0, 0, f"  warn: OCR failed to locate '{target}'")
            return None, None

        gx, gy = screenshot_to_global(pos[0], pos[1], display)
        pyautogui.moveTo(gx, gy, duration=0.3)
        time.sleep(0.2)
        pyautogui.click()
        if double:
            time.sleep(0.15)
            pyautogui.click()
        return gx, gy

    def _type(self, value):
        if not value:
            return
        pyautogui.hotkey('command', 'a')
        time.sleep(0.05)
        pyautogui.press('delete')
        time.sleep(0.05)
        pyautogui.typewrite(str(value), interval=0.04)

    def _select_option(self, target_value: str, rule: dict | None = None):
        """Re-screenshot after dropdown opens (inverted OCR), then click the match."""
        if not target_value:
            return
        time.sleep(0.3)

        display = self._display_for(rule)
        img = capture_display(display['index'])
        display['_img_w'] = img.width
        display['_img_h'] = img.height
        # Dropdown list may extend beyond the annotated region — search without region
        words = ocr_words(img, invert=True)

        tl = target_value.strip().lower()
        match = next(
            (w for w in words
             if tl in w['text'].lower() or w['text'].lower() in tl),
            None,
        )
        if not match:
            self._log(0, 0, f"  warn: dropdown option not found: {target_value!r}")
            return

        gx, gy = screenshot_to_global(
            match['x'] + match['w'] // 2,
            match['y'] + match['h'] // 2,
            display,
        )
        pyautogui.moveTo(gx, gy, duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        self._log(0, 0, f"  selected: {match['text']!r} ({gx},{gy})")

    def _log(self, current: int, total: int, msg: str):
        print(msg)
        if self.callback:
            self.callback(current, total, msg)
