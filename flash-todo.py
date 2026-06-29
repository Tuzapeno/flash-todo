import curses
import os
import sys
import json
import uuid

# Set ESCDELAY to make ESC key responsive in curses
os.environ.setdefault('ESCDELAY', '25')


class Task:
    def __init__(self, id, title, completed=False, parent_id=None, children_ids=None):
        self.id = id
        self.title = title
        self.completed = completed
        self.parent_id = parent_id
        self.children_ids = children_ids if children_ids is not None else []

        # References to other Task objects (reconstructed on load)
        self.parent = None
        self.children = []

    def is_leaf(self):
        return len(self.children) == 0

    def set_completed(self, val):
        """
        Marks a leaf task as completed or incomplete and propagates the status upward.
        Returns a list of Task objects whose completion status changed.
        """
        if not self.is_leaf():
            return []

        if self.completed == val:
            return []

        self.completed = val
        changed = [self]

        if val:
            # Propagate completion up: parent is complete if ALL of its children are complete
            curr = self.parent
            while curr is not None:
                if curr.children and all(c.completed for c in curr.children):
                    if not curr.completed:
                        curr.completed = True
                        changed.append(curr)
                    curr = curr.parent
                else:
                    break
        else:
            # Propagate incomplete up: if any child is incomplete, all ancestors are incomplete
            curr = self.parent
            while curr is not None:
                if curr.completed:
                    curr.completed = False
                    changed.append(curr)
                    curr = curr.parent
                else:
                    break

        return changed

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "completed": self.completed,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids
        }


class TaskManager:
    def __init__(self, filepath=None):
        if filepath is None:
            # Save in a common user directory (~/.branch_tasks/tasks.json)
            home = os.path.expanduser("~")
            data_dir = os.path.join(home, ".branch_tasks")
            try:
                os.makedirs(data_dir, exist_ok=True)
            except Exception:
                pass
            self.filepath = os.path.join(data_dir, "tasks.json")
        else:
            self.filepath = filepath

        self.tasks = {}  # id -> Task
        self.roots = []  # list of root Task objects

    def load(self):
        """Loads tasks from a JSON file and reconstructs the tree hierarchy."""
        if not os.path.exists(self.filepath):
            self.tasks = {}
            self.roots = []
            return

        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
        except Exception:
            self.tasks = {}
            self.roots = []
            return

        # Phase 1: Create Task instances
        self.tasks = {}
        for item in data:
            task = Task(
                id=item["id"],
                title=item["title"],
                completed=item.get("completed", False),
                parent_id=item.get("parent_id"),
                children_ids=item.get("children_ids", [])
            )
            self.tasks[task.id] = task

        # Phase 2: Resolve references
        self.roots = []
        for task in self.tasks.values():
            if task.parent_id:
                task.parent = self.tasks.get(task.parent_id)
            else:
                self.roots.append(task)

            task.children = [self.tasks[cid]
                             for cid in task.children_ids if cid in self.tasks]

    def save(self):
        """Saves current tasks to the JSON file."""
        # Ensure the directory exists before saving
        data_dir = os.path.dirname(self.filepath)
        if data_dir:
            try:
                os.makedirs(data_dir, exist_ok=True)
            except Exception:
                pass

        data = [task.to_dict() for task in self.tasks.values()]
        try:
            with open(self.filepath, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def add_root_task(self, title):
        """Creates and adds a new root task."""
        new_id = str(uuid.uuid4())
        task = Task(id=new_id, title=title)
        self.tasks[new_id] = task
        self.roots.append(task)
        self.save()
        return task

    def add_child_task(self, parent_id, title):
        """Adds a child branch task to a parent task."""
        parent = self.tasks.get(parent_id)
        if not parent:
            return None

        new_id = str(uuid.uuid4())
        child = Task(id=new_id, title=title, parent_id=parent.id)
        child.parent = parent

        parent.children.append(child)
        parent.children_ids.append(new_id)

        # If parent was completed, it now becomes incomplete as a new branch is incomplete
        if parent.completed:
            parent.completed = False
            curr = parent.parent
            while curr is not None:
                if curr.completed:
                    curr.completed = False
                    curr = curr.parent
                else:
                    break

        self.tasks[new_id] = child
        self.save()
        return child

    def delete_task(self, task_id):
        """
        Deletes a task and its descendants.
        Adjusts parent references and updates completion status.
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        def recurse_delete(node):
            for child in node.children:
                recurse_delete(child)
            if node.id in self.tasks:
                del self.tasks[node.id]

        recurse_delete(task)

        if task.parent:
            parent = task.parent
            if task in parent.children:
                parent.children.remove(task)
            if task.id in parent.children_ids:
                parent.children_ids.remove(task.id)

            # Recalculate parent's completion status if children remain
            if parent.is_leaf():
                parent.completed = False
            else:
                if all(c.completed for c in parent.children):
                    parent.completed = True
                    curr = parent.parent
                    while curr is not None:
                        if curr.children and all(c.completed for c in curr.children):
                            curr.completed = True
                            curr = curr.parent
                        else:
                            break
        else:
            if task in self.roots:
                self.roots.remove(task)

        self.save()


class TerminalUI:
    def __init__(self, manager):
        self.manager = manager
        self.focus_node = None       # Task (or None for root level)
        self.selected_task = None     # Task currently highlighted
        # Scroll offset for Left Panel (active tasks)
        self.active_scroll_y = 0
        # Scroll offset for Right Panel (subtask preview)
        self.preview_scroll_y = 0

        # Windows
        self.stdscr = None
        self.header_win = None
        self.left_win = None
        self.right_win = None
        self.details_win = None
        self.footer_win = None

    def run(self):
        curses.wrapper(self._main)

    def _main(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)  # Hide cursor
        stdscr.keypad(True)

        # Color configuration
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1)   # Standard
            curses.init_pair(2, curses.COLOR_CYAN, -1)    # Headers/Cyan
            curses.init_pair(3, curses.COLOR_GREEN, -1)   # Completed
            curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Focus / Highlight
            curses.init_pair(5, curses.COLOR_RED, -1)     # Accents/Incomplete
            curses.init_pair(6, curses.COLOR_CYAN, -1)  # Borders

        # Load initial state
        self.manager.load()
        if self.manager.roots:
            self.selected_task = self.manager.roots[0]

        while True:
            self._resize_and_draw()
            ch = stdscr.getch()

            if ch in (ord('q'), ord('Q')):
                break

            elif ch in (ord('r'), ord('R')):
                if self.selected_task:
                    new_title = self._prompt_input(
                        "RENAME TASK", f"Rename '{self.selected_task.title[:75]}':")
                    if new_title:
                        self.selected_task.title = new_title
                        self.manager.save()

            elif ch in (ord('a'), ord('A')):
                # Add task:
                # - If at root: adds a new root task.
                # - If inside a branch: adds a branch to the current focus node.
                if self.focus_node is None:
                    title = self._prompt_input(
                        "ADD NEW TASK", "Enter task title:")
                    if title:
                        task = self.manager.add_root_task(title)
                        if not self.selected_task:
                            self.selected_task = task
                else:
                    title = self._prompt_input(
                        "ADD BRANCH", f"Add branch to '{self.focus_node.title}':")
                    if title:
                        child = self.manager.add_child_task(
                            self.focus_node.id, title)
                        self.selected_task = child

            elif ch in (ord('b'), ord('B')):
                # Divide/Branch task (adds child branch to the selected task)
                if self.selected_task:
                    if self.selected_task.completed:
                        self._show_message(
                            "WARNING", "Cannot add a branch to a completed task.")
                        continue

                    title = self._prompt_input(
                        "ADD BRANCH", f"Enter branch title: ")
                    if title:
                        child = self.manager.add_child_task(
                            self.selected_task.id, title)
                        # Zoom in to the newly branched task
                        self.focus_node = self.selected_task
                        self.selected_task = child

            elif ch == ord(' '):
                # Complete/Toggle task
                if self.selected_task:
                    if not self.selected_task.is_leaf():
                        self._show_message(
                            "INFO", "Completion of parent tasks is determined by their branches.")
                    else:
                        new_status = not self.selected_task.completed
                        changed = self.selected_task.set_completed(new_status)
                        if changed:
                            self.manager.save()

                            # Handle auto-up recursion when completing tasks
                            if new_status:
                                curr_focus = self.focus_node
                                while curr_focus is not None and curr_focus.completed:
                                    parent_focus = curr_focus.parent
                                    # Highlight the completed node
                                    self.selected_task = curr_focus
                                    curr_focus = parent_focus
                                self.focus_node = curr_focus

            elif ch in (curses.KEY_LEFT, ord('h'), 27, 8, 127):  # Left Arrow, h, ESC, Backspace
                # Zoom out / Move up level
                if self.focus_node is not None:
                    old_focus = self.focus_node
                    self.focus_node = self.focus_node.parent
                    self.selected_task = old_focus

            elif ch in (curses.KEY_RIGHT, ord('l'), 10, 13, curses.KEY_ENTER):  # Right Arrow, l, Enter
                # Zoom in / Move down level
                if self.selected_task and not self.selected_task.is_leaf():
                    self.focus_node = self.selected_task
                    self.selected_task = self.focus_node.children[0]

            elif ch in (curses.KEY_UP, ord('k')):
                # Move selection up
                self._move_selection(-1)

            elif ch in (curses.KEY_DOWN, ord('j')):
                # Move selection down
                self._move_selection(1)

            elif ch in (ord('d'), ord('D'), curses.KEY_DC):  # d, D or Delete
                # Delete task
                if self.selected_task:
                    if self._prompt_confirm("Confirm Deletion Y/N"):
                        task_to_del = self.selected_task
                        parent = task_to_del.parent
                        self.manager.delete_task(task_to_del.id)

                        if parent:
                            if parent.is_leaf():
                                # Zoom out since parent has lost all children and is a leaf again
                                self.focus_node = parent.parent
                                self.selected_task = parent
                            else:
                                # Stay at this level and select another sibling
                                self.selected_task = parent.children[0]
                        else:
                            # At root level
                            self.focus_node = None
                            self.selected_task = self.manager.roots[0] if self.manager.roots else None

    def _move_selection(self, direction):
        if self.focus_node is None:
            # Navigating roots
            if not self.manager.roots:
                return
            try:
                curr_idx = self.manager.roots.index(self.selected_task)
            except ValueError:
                curr_idx = 0
            new_idx = (curr_idx + direction) % len(self.manager.roots)
            self.selected_task = self.manager.roots[new_idx]
        else:
            # Navigating active branch children
            children = self.focus_node.children
            if not children:
                return
            try:
                curr_idx = children.index(self.selected_task)
            except ValueError:
                curr_idx = 0
            new_idx = (curr_idx + direction) % len(children)
            self.selected_task = children[new_idx]

    def _resize_and_draw(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()

        if h < 20 or w < 70:
            self.stdscr.addstr(0, 0, "Terminal window too small.",
                               curses.color_pair(5) | curses.A_BOLD)
            self.stdscr.addstr(
                1, 0, "Please resize to at least 70x20.", curses.color_pair(1))
            self.stdscr.refresh()
            return

        # Setup windows dynamically
        header_h = 3
        footer_h = 1
        details_h = 5
        main_h = h - header_h - footer_h - details_h

        left_w = w // 2 - 1
        right_w = w - left_w - 2

        self.header_win = curses.newwin(main_h, left_w, header_h, 0)
        self.right_win = curses.newwin(main_h, right_w, header_h, left_w + 2)
        self.header_win_border = curses.newwin(
            header_h, w, 0, 0)  # header panel
        self.details_win = curses.newwin(details_h, w, header_h + main_h, 0)
        self.footer_win = curses.newwin(footer_h, w, h - 1, 0)

        # Draw vertical separator in stdscr
        for y in range(header_h, header_h + main_h):
            self.stdscr.addch(y, left_w, curses.ACS_VLINE,
                              curses.color_pair(6))
            self.stdscr.addch(y, left_w + 1, ' ')

        # Horizontal separator
        self.stdscr.hline(header_h + main_h, 0,
                          curses.ACS_HLINE, w, curses.color_pair(6))
        self.stdscr.refresh()

        self._draw_header()
        self._draw_current_level()
        self._draw_subtasks_preview()
        self._draw_details()
        self._draw_footer()

        curses.doupdate()

    def _draw_header(self):
        win = self.header_win_border
        win.erase()
        h, w = win.getmaxyx()

        win.addstr(0, 2, "FLASH TODO", curses.color_pair(2) | curses.A_BOLD)

        # Build path display
        path_strs = ["Root"]
        if self.focus_node:
            curr = self.focus_node
            curr_path = []
            while curr:
                curr_path.append(curr.title)
                curr = curr.parent
            curr_path.reverse()
            path_strs.extend(curr_path)

        path_display = " > ".join(path_strs)
        if len(path_display) > w // 2 - 5:
            path_display = "..." + path_display[-(w // 2 - 8):]

        win.addstr(0, w - len(path_display) - 3,
                   f"Level: {path_display}", curses.color_pair(1) | curses.A_DIM)
        win.hline(1, 0, curses.ACS_HLINE, w, curses.color_pair(6))

        win.noutrefresh()

    def _draw_current_level(self):
        win = self.header_win
        win.erase()
        h, w = win.getmaxyx()

        # Draw Header
        if self.focus_node is None:
            title_text = "ROOT TASKS"
            items = self.manager.roots
        else:
            title_text = f"TASKS UNDER: {self.focus_node.title.upper()}"
            items = self.focus_node.children

        win.addstr(0, 2, title_text, curses.color_pair(2) | curses.A_BOLD)
        win.hline(1, 2, curses.ACS_HLINE, w - 4, curses.color_pair(6))

        if not items:
            win.addstr(
                3, 2, "No tasks. Press [A] to add.", curses.color_pair(1))
            win.noutrefresh()
            return

        # Scrolling logic
        visible_h = h - 3
        selected_idx = 0
        for idx, item in enumerate(items):
            if self.selected_task and item.id == self.selected_task.id:
                selected_idx = idx
                break

        if selected_idx < self.active_scroll_y:
            self.active_scroll_y = selected_idx
        elif selected_idx >= self.active_scroll_y + visible_h:
            self.active_scroll_y = selected_idx - visible_h + 1

        for i in range(visible_h):
            idx = self.active_scroll_y + i
            if idx >= len(items):
                break

            item = items[idx]
            is_sel = (self.selected_task and item.id == self.selected_task.id)
            status = "[x]" if item.completed else "[ ]"

            # Show navigation folder indicator if task has children
            branch_indicator = " ↳" if not item.is_leaf() else ""
            text = f"{status} {item.title}{branch_indicator}"

            if len(text) > w - 6:
                text = text[:w - 9] + "..."

            attr = curses.color_pair(1)
            if item.completed:
                attr = curses.color_pair(3)

            y = 2 + i
            if is_sel:
                win.addstr(y, 1, ">", curses.color_pair(4) | curses.A_BOLD)
                win.addstr(y, 3, text, attr | curses.A_REVERSE | curses.A_BOLD)
            else:
                win.addstr(y, 3, text, attr)

        win.noutrefresh()

    def _draw_subtasks_preview(self):
        win = self.right_win
        win.erase()
        h, w = win.getmaxyx()
        if h < 5 or w < 20:
            win.noutrefresh()
            return

        win.addstr(0, 2, "SUBTASKS PREVIEW",
                   curses.color_pair(2) | curses.A_BOLD)
        win.hline(1, 2, curses.ACS_HLINE, w - 4, curses.color_pair(6))

        if not self.selected_task:
            win.addstr(3, 2, "No task selected.", curses.color_pair(1))
            win.noutrefresh()
            return

        task = self.selected_task

        if task.is_leaf():
            win.addstr(3, 2, f"'{task.title}' has no subtasks.",
                       curses.color_pair(1) | curses.A_DIM)
            win.addstr(4, 2, "Press [B] to branch it.", curses.color_pair(1))
            win.noutrefresh()
            return

        items = task.children
        visible_h = h - 3

        # Preview scroll (simple clamp)
        if self.preview_scroll_y >= len(items):
            self.preview_scroll_y = 0

        for i in range(visible_h):
            idx = self.preview_scroll_y + i
            if idx >= len(items):
                break

            item = items[idx]
            status = "[x]" if item.completed else "[ ]"
            branch_indicator = " ↳" if not item.is_leaf() else ""
            text = f"{status} {item.title}{branch_indicator}"

            if len(text) > w - 6:
                text = text[:w - 9] + "..."

            attr = curses.color_pair(1)
            if item.completed:
                attr = curses.color_pair(3)

            win.addstr(2 + i, 3, text, attr)

        win.noutrefresh()

    def _draw_details(self):
        win = self.details_win
        win.erase()
        h, w = win.getmaxyx()

        win.addstr(0, 2, "SELECTED TASK DETAILS",
                   curses.color_pair(2) | curses.A_BOLD)

        if not self.selected_task:
            win.addstr(2, 2, "No task selected.", curses.color_pair(1))
            win.noutrefresh()
            return

        task = self.selected_task
        status_str = "COMPLETED" if task.completed else "INCOMPLETE"
        status_color = curses.color_pair(
            3) if task.completed else curses.color_pair(5)

        win.addstr(2, 2, "Title: ", curses.color_pair(1) | curses.A_BOLD)
        win.addstr(2, 9, task.title[:w - 12], curses.color_pair(1))

        win.addstr(3, 2, "Status: ", curses.color_pair(1) | curses.A_BOLD)
        win.addstr(3, 10, status_str, status_color | curses.A_BOLD)

        # Breadcrumb path
        path = []
        curr = task
        while curr:
            path.append(curr.title)
            curr = curr.parent
        path.reverse()
        path_str = " > ".join(path)
        if len(path_str) > w - 12:
            path_str = "..." + path_str[-(w - 15):]

        win.addstr(4, 2, "Path: ", curses.color_pair(1) | curses.A_BOLD)
        win.addstr(4, 8, path_str, curses.color_pair(1) | curses.A_DIM)

        win.noutrefresh()

    def _draw_footer(self):
        win = self.footer_win
        win.erase()
        h, w = win.getmaxyx()

        shortcuts = "[A] Add Task  [B] Divide/Branch  [R] Rename Task [Space] Complete/Toggle  [Esc/←] Zoom Out  [Enter/→] Zoom In  [D/Del] Delete  [Q] Quit"
        if len(shortcuts) < w:
            win.addstr(0, (w - len(shortcuts)) // 2, shortcuts,
                       curses.color_pair(2) | curses.A_REVERSE)
        else:
            win.addstr(0, 0, shortcuts[:w],
                       curses.color_pair(2) | curses.A_REVERSE)

        win.noutrefresh()

    def _prompt_input(self, title, prompt_label):
        sh, sw = self.stdscr.getmaxyx()
        h = 8
        w = min(60, sw - 4)
        y = (sh - h) // 2
        x = (sw - w) // 2

        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        curses.echo()
        curses.curs_set(1)

        win.box()
        win.addstr(1, (w - len(title)) // 2, title,
                   curses.color_pair(2) | curses.A_BOLD)
        win.addstr(3, 2, prompt_label)
        win.move(4, 2)
        win.refresh()

        input_str = ""
        while True:
            ch = win.getch()
            if ch in (10, 13, curses.KEY_ENTER):
                break
            elif ch == 27:  # ESC
                input_str = ""
                break
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if len(input_str) > 0:
                    input_str = input_str[:-1]
                    win.move(4, 2)
                    win.clrtoeol()
                    win.box()
                    win.addstr(1, (w - len(title)) // 2, title,
                               curses.color_pair(2) | curses.A_BOLD)
                    win.addstr(3, 2, prompt_label)
                    win.addstr(4, 2, input_str)
            elif 32 <= ch <= 126:
                if len(input_str) < w - 6:
                    input_str += chr(ch)
                    win.addstr(4, 2, input_str)

        curses.noecho()
        curses.curs_set(0)
        return input_str.strip()

    def _prompt_confirm(self, title):
        sh, sw = self.stdscr.getmaxyx()
        h = 5
        w = min(40, sw - 4)
        y = (sh - h) // 2
        x = (sw - w) // 2

        win = curses.newwin(h, w, y, x)
        win.box()
        win.addstr(2, (w - len(title)) // 2, title,
                   curses.color_pair(5) | curses.A_BOLD)
        win.refresh()

        while True:
            ch = win.getch()
            if ch in (ord('y'), ord('Y')):
                return True
            elif ch in (ord('n'), ord('N'), 27):  # y / n / ESC
                return False

    def _show_message(self, title, message):
        sh, sw = self.stdscr.getmaxyx()
        h = 6
        w = min(50, sw - 4)
        y = (sh - h) // 2
        x = (sw - w) // 2

        win = curses.newwin(h, w, y, x)
        win.box()
        win.addstr(1, (w - len(title)) // 2, title,
                   curses.color_pair(5) | curses.A_BOLD)

        words = message.split()
        lines = []
        curr_line = ""
        for word in words:
            if len(curr_line) + len(word) + 1 > w - 4:
                lines.append(curr_line)
                curr_line = word
            else:
                curr_line = (curr_line + " " + word).strip()
        if curr_line:
            lines.append(curr_line)

        for idx, line in enumerate(lines[:2]):
            win.addstr(3 + idx, (w - len(line)) //
                       2, line, curses.color_pair(1))

        win.refresh()
        win.getch()


if __name__ == "__main__":
    manager = TaskManager()
    ui = TerminalUI(manager)
    ui.run()
