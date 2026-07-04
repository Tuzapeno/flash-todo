from src.TaskManager import TaskManager
from src.TerminalUI import TerminalUI

def main():
    manager = TaskManager()
    ui = TerminalUI(manager)
    ui.run()

if __name__ == "__main__":
    main()
