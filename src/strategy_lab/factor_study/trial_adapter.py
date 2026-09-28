"""Task C extension point. No duplicate TrialRegistry or statistical adjudicator."""
from typing import Protocol


class TrialAdapter(Protocol):
    def register(self, plan: dict, experiments: list[dict]) -> dict: ...
    def evaluate(self, registration: dict, outcomes: list[dict]) -> dict: ...


class UnavailableTrialAdapter:
    def register(self, plan, experiments):
        return {'status': 'UNAVAILABLE', 'experiment_count': len(experiments),
                'holdout_status': 'UNKNOWN_PREVIOUS_EXPOSURE', 'plan_sha256': plan['plan_sha256'],
                'reason': 'Task C adapter not installed; complete inventory exported for later registration'}

    def evaluate(self, registration, outcomes):
        return {'status': 'NOT_ADJUDICATED', 'reason': 'Task C adapter unavailable',
                'outcome_count': len(outcomes), 'promotion_allowed': False}
