from src.TaskManager import TaskManager
from src.TerminalUI import TerminalUI

if __name__ == "__main__":
    manager = TaskManager()
    ui = TerminalUI(manager)
    ui.run()
