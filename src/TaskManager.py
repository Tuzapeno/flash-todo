import json
import uuid
import os

from .Task import Task

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
                children_ids=item.get("children_ids", []),
                project=item.get("project", "")
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

    def duplicate_task(self, task_id):
        original = self.tasks.get(task_id)
        if not original:
            return None

        def _clone_subtree(node, new_parent_id):
            new_id = str(uuid.uuid4())
            clone = Task(
                id=new_id,
                title=node.title,
                completed=node.completed,
                parent_id=new_parent_id,
                children_ids=[],
                project=node.project
            )
            self.tasks[new_id] = clone

            for child in node.children:
                child_clone = _clone_subtree(child, new_id)
                clone.children.append(child_clone)
                clone.children_ids.append(child_clone.id)
                child_clone.parent = clone

            return clone

        # Clone the entire subtree
        copy = _clone_subtree(original, original.parent_id)
        copy.title = original.title + "-copy"

        # Insert the copy as a sibling
        if original.parent:
            parent = original.parent
            copy.parent = parent
            parent.children.append(copy)
            parent.children_ids.append(copy.id)
        else:
            self.roots.append(copy)

        self.save()
        return copy

    def clear_completed_roots(self):
        to_remove = [t for t in self.roots if t.completed]
        if not to_remove:
            return 0

        def recurse_delete(node):
            for child in node.children:
                recurse_delete(child)
            if node.id in self.tasks:
                del self.tasks[node.id]

        for task in to_remove:
            recurse_delete(task)
            self.roots.remove(task)

        self.save()
        return len(to_remove)
