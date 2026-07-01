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
