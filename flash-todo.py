import src.TaskManager as TaskManager
import src.TerminalUI as TerminalUI

if __name__ == "__main__":
    manager = TaskManager()
    ui = TerminalUI(manager)
    ui.run()
