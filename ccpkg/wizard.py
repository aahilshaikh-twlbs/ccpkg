"""Interactive install wizard. Stdlib only, Python 3.9.

WizardState is a pure, I/O-free state machine (unit-tested directly). The
renderers (raw-mode termios + numbered fallback) are added separately and only
drive this state.
"""
from typing import List, Set

from .selection import Stage


class WizardState:
    def __init__(self, stages, preselected):
        # type: (List[Stage], Set[str]) -> None
        self.stages = stages
        self.selected = set(preselected)
        self.stage_index = 0
        self.cursor = 0
        self._done = False

    # --- queries -------------------------------------------------------
    def current_stage(self):
        # type: () -> Stage
        return self.stages[self.stage_index]

    def is_selected(self, entry_id):
        # type: (str) -> bool
        return entry_id in self.selected

    def is_done(self):
        # type: () -> bool
        return self._done

    def selected_ids(self):
        # type: () -> Set[str]
        return set(self.selected)

    # --- mutations -----------------------------------------------------
    def move(self, delta):
        # type: (int) -> None
        n = len(self.current_stage().entries)
        if n == 0:
            self.cursor = 0
            return
        self.cursor = max(0, min(n - 1, self.cursor + delta))

    def toggle(self):
        # type: () -> None
        entries = self.current_stage().entries
        if not entries:
            return
        eid = entries[self.cursor].id
        if eid in self.selected:
            self.selected.discard(eid)
        else:
            self.selected.add(eid)

    def select_all(self):
        # type: () -> None
        for e in self.current_stage().entries:
            self.selected.add(e.id)

    def select_none(self):
        # type: () -> None
        for e in self.current_stage().entries:
            self.selected.discard(e.id)

    def next_stage(self):
        # type: () -> None
        if self.stage_index >= len(self.stages) - 1:
            self._done = True
            return
        self.stage_index += 1
        self.cursor = 0

    def prev_stage(self):
        # type: () -> None
        if self._done:
            self._done = False
            return
        if self.stage_index > 0:
            self.stage_index -= 1
            self.cursor = 0
