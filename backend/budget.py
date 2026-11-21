"""touch-budget guard: never let a branch or a run spend more touches than it should.

eval sessions get 10 touches, practice gets 30. a branch that is not working must be
capped before it burns the whole run. this is pure bookkeeping (no api calls), so it is
unit-testable on its own. the orchestrator calls spend() before each contact and sync()
with the api's own touches_used after, because the api count is the real truth (it also
accounts for retries and anything sent in parallel).
"""


class BudgetExceeded(Exception):
    """raised when a contact would go over the session or branch cap."""


class TouchBudget:
    def __init__(self, total, per_branch=None):
        self.total = total              # session cap: 10 eval, 30 practice
        self.per_branch = per_branch    # optional cap on one approach before we pivot
        self.used = 0
        self.branch_used = 0

    @property
    def remaining(self):
        return max(0, self.total - self.used)

    def exhausted(self):
        return self.remaining <= 0

    def branch_exhausted(self):
        return self.per_branch is not None and self.branch_used >= self.per_branch

    def can_spend(self, n=1):
        if self.used + n > self.total:
            return False
        if self.per_branch is not None and self.branch_used + n > self.per_branch:
            return False
        return True

    def spend(self, n=1):
        """call before a contact. raises BudgetExceeded if it would go over a cap."""
        if not self.can_spend(n):
            raise BudgetExceeded(
                f"used {self.used}/{self.total} total, {self.branch_used}"
                f"{'/' + str(self.per_branch) if self.per_branch else ''} on this branch"
            )
        self.used += n
        self.branch_used += n

    def sync(self, touches_used):
        """trust the api's own count as the truth after a contact."""
        self.used = touches_used

    def new_branch(self):
        """reset the per-branch counter when we pivot to a different approach."""
        self.branch_used = 0
