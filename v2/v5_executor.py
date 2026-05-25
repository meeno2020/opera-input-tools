"""
V5 Executor - simple sequential input: type each field value → Enter, then Down Arrow per row.
No button location required.
"""
import os
import sys
import time
import threading
import pyautogui


class V5WorkflowExecutor:

    def __init__(self, data_loader, callback=None,
                 delay_seconds: float = 1.0, play_sound: bool = True):
        self.data_loader    = data_loader
        self.callback       = callback
        self.delay_seconds  = delay_seconds
        self.play_sound     = play_sound

        self.is_running  = False
        self.should_stop = False
        self._thread     = None

        pyautogui.PAUSE = 0.1

    def start(self, start_row: int = 0) -> bool:
        if self.is_running:
            return False
        total = self.data_loader.get_row_count()
        if not self.data_loader.is_loaded() or not (0 <= start_row < total):
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

    def _run(self, start_row: int):
        try:
            total   = self.data_loader.get_row_count()
            columns = self.data_loader.get_columns()
            self._log(0, total, f"V5: starting from row {start_row + 1} of {total}")

            for row_idx in range(start_row, total):
                if self.should_stop:
                    break
                row = self.data_loader.get_row(row_idx)

                for col in columns:
                    if self.should_stop:
                        break
                    value = str(row.get(col, ''))
                    pyautogui.write(value, interval=0.05)
                    self._log(row_idx + 1, total, f"  typed [{col}] = {value}")

                    elapsed = 0.0
                    while elapsed < self.delay_seconds and not self.should_stop:
                        time.sleep(0.1)
                        elapsed += 0.1

                    pyautogui.press('enter')

                if not self.should_stop:
                    pyautogui.press('down')
                    self._log(row_idx + 1, total,
                              f"Row {row_idx + 1} done — pressed Down")
                    self._beep()

            self.is_running = False
            self._log(total, total, "Stopped" if self.should_stop else "Completed")
        except Exception as e:
            self.is_running = False
            self._log(0, 0, f"Error: {e}")

    def _beep(self):
        if not self.play_sound:
            return
        try:
            if sys.platform == 'darwin':
                os.system("afplay /System/Library/Sounds/Tink.aiff &")
            elif sys.platform == 'win32':
                import winsound
                winsound.Beep(800, 150)
        except Exception:
            pass

    def _log(self, current: int, total: int, msg: str):
        print(msg)
        if self.callback:
            self.callback(current, total, msg)
