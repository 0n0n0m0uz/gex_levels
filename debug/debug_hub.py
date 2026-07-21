# debug_hub.py
from rich.table import Table



class DebugHub:
    ENABLED = True
    
    def __init__(self):
        self.variables = {}
    def set(self, key, value):
        self.variables[key] = value
    def __init__(self):
        self.variables = {}

    def set(self, key, value):
        self.variables[key] = value

    def render_table(self) -> Table:
        table = Table(title="Live Terminal Debugger", border_style="cyan")
        table.add_column("Variable", style="magenta", no_wrap=True)
        table.add_column("Value", style="green")

        for k, v in self.variables.items():
            table.add_row(str(k), repr(v))

        return table

# Global singleton instance
hub = DebugHub()