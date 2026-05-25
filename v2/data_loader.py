"""
Data loader - CSV and Excel file support.
"""
import os
import pandas as pd


class DataLoader:

    def __init__(self):
        self._data     = None
        self._columns  = []
        self.filepath  = None

    def load_file(self, filepath: str) -> bool:
        try:
            if not os.path.exists(filepath):
                return False
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.csv':
                self._data = pd.read_csv(filepath, dtype=str,
                                         encoding='utf-8', keep_default_na=False)
            elif ext in ('.xlsx', '.xls'):
                self._data = pd.read_excel(filepath, dtype=str,
                                           keep_default_na=False)
            else:
                return False
            self._columns = list(self._data.columns)
            self.filepath = filepath
            return True
        except Exception as e:
            print(f"Load error: {e}")
            return False

    def get_columns(self)   -> list:       return list(self._columns)
    def get_data(self):                     return self._data
    def get_row_count(self) -> int:         return len(self._data) if self._data is not None else 0
    def is_loaded(self)     -> bool:        return self._data is not None

    def get_row(self, index: int) -> dict | None:
        if self._data is None or not (0 <= index < len(self._data)):
            return None
        return self._data.iloc[index].to_dict()

    def preview_data(self, max_rows: int = 10):
        return self._data.head(max_rows) if self._data is not None else None
