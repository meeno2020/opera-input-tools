"""
Workflow configuration - load/save YAML with buttons + steps structure.
"""
import os
import yaml


class WorkflowConfig:

    def __init__(self):
        self.excel_file: str  = ''
        self.buttons:    dict = {}
        self.steps:      list = []

    # ── Steps ─────────────────────────────────────────────────────────────────

    def add_step(self, step: dict):
        self.steps.append(step)

    def remove_step(self, index: int) -> bool:
        if 0 <= index < len(self.steps):
            del self.steps[index]
            return True
        return False

    def move_step(self, from_idx: int, to_idx: int) -> bool:
        if 0 <= from_idx < len(self.steps) and 0 <= to_idx < len(self.steps):
            self.steps.insert(to_idx, self.steps.pop(from_idx))
            return True
        return False

    def get_steps(self)          -> list:      return list(self.steps)
    def get_step(self, i: int)   -> dict|None: return self.steps[i] if 0 <= i < len(self.steps) else None
    def get_step_count(self)     -> int:       return len(self.steps)
    def clear_steps(self):                     self.steps = []

    # ── Buttons ───────────────────────────────────────────────────────────────

    def set_buttons(self, rules: dict): self.buttons = dict(rules)
    def get_buttons(self)  -> dict:     return dict(self.buttons)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, filepath: str) -> bool:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(
                    {'excel_file': self.excel_file,
                     'buttons':    self.buttons,
                     'steps':      self.steps},
                    f, allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
            return True
        except Exception as e:
            print(f"Save failed: {e}")
            return False

    def load(self, filepath: str) -> bool:
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self.excel_file = data.get('excel_file', '')
            self.buttons    = data.get('buttons', {}) or {}
            self.steps      = data.get('steps',   []) or []
            return True
        except Exception as e:
            print(f"Load failed: {e}")
            return False
