"""
Workflow configuration.

Two separate file types:
  Button Library  (buttons.yaml) — named control rules, display/region info
  Workflow        (workflow.yaml) — ordered steps referencing library names

Old combined format (buttons + steps in one file) is still supported on load.
"""
import os
import yaml


class WorkflowConfig:

    def __init__(self):
        self.excel_file: str  = ''
        self.buttons:    dict = {}   # name -> rule dict
        self.steps:      list = []

    # ── Steps ─────────────────────────────────────────────────────────────────

    def add_step(self, step: dict):          self.steps.append(step)
    def get_steps(self)        -> list:      return list(self.steps)
    def get_step(self, i: int) -> dict|None: return self.steps[i] if 0 <= i < len(self.steps) else None
    def get_step_count(self)   -> int:       return len(self.steps)
    def clear_steps(self):                   self.steps = []

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

    # ── Buttons ───────────────────────────────────────────────────────────────

    def set_buttons(self, rules: dict): self.buttons = dict(rules)
    def get_buttons(self)  -> dict:     return dict(self.buttons)

    # ── Button Library file ───────────────────────────────────────────────────

    def save_library(self, filepath: str) -> bool:
        """Save button rules only → buttons.yaml"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(self.buttons, f,
                          allow_unicode=True,
                          default_flow_style=False,
                          sort_keys=False)
            return True
        except Exception as e:
            print(f"Save library failed: {e}")
            return False

    def load_library(self, filepath: str) -> bool:
        """Load button rules from a library file (flat name→rule mapping)."""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return False
            # Support old format: {buttons: {...}} or new flat format
            if 'buttons' in data and isinstance(data['buttons'], dict):
                self.buttons = data['buttons']
            else:
                self.buttons = {k: v for k, v in data.items()
                                if isinstance(v, dict) and 'method' in v}
            return True
        except Exception as e:
            print(f"Load library failed: {e}")
            return False

    # ── Workflow file (steps only) ────────────────────────────────────────────

    def save_workflow(self, filepath: str) -> bool:
        """Save steps only → workflow.yaml (no button rules embedded)."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump({'steps': self.steps}, f,
                          allow_unicode=True,
                          default_flow_style=False,
                          sort_keys=False)
            return True
        except Exception as e:
            print(f"Save workflow failed: {e}")
            return False

    def load_workflow(self, filepath: str) -> bool:
        """Load steps only from a workflow file (ignores any embedded buttons)."""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self.steps = data.get('steps', []) or []
            return True
        except Exception as e:
            print(f"Load workflow failed: {e}")
            return False

    # ── Legacy combined format (backward compatibility) ───────────────────────

    def save(self, filepath: str) -> bool:
        """Save everything (library + steps) in one file — legacy format."""
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
        """Load combined file (legacy). Populates both buttons and steps."""
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
