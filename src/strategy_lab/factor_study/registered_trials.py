"""Thin factor-study adapter to the existing C registry and integrity API."""
from strategy_lab.research.accounting import digest
from strategy_lab.research.trials import TrialRegistry
from strategy_lab.research.integrity import assess_research_integrity


class RegisteredTrialAdapter:
    def __init__(self, path):
        self.registry = TrialRegistry(path)

    def register(self, plan, experiments):
        campaign = 'factor-study-' + plan['request_id']
        self.registry.register_campaign(
            campaign, selection_goal='Reproduce every requested factor diagnostic; no winner selection',
            scope_definition='All requested definitions and label horizons in this integration request',
            history_completeness='UNKNOWN',
            history_reason='Prior A studies and external observation exist; historical search inventory is incomplete')
        settings = plan['settings']
        entries = []
        for experiment in experiments:
            spec = dict(
                hypothesis_family_id='factor-research-loop', selection_campaign_id=campaign,
                identity={k: experiment[k] for k in ('factor_variant_id', 'definition_revision', 'implementation_id')},
                parameters=experiment['parameters'], label_horizon=experiment['horizon_bars'],
                objective='Descriptive time-series association and baseline incremental error',
                selection_rule='Retain all outcomes including invalid and failed; no performance ranking',
                dataset_fingerprint=plan['dataset']['sha256'],
                sample_fingerprint=digest({k: settings[k] for k in ('start', 'end', 'segments', 'symbols')}),
                code_hash=digest(plan['code_files']), config_hash=digest(settings), parent_experiment_id=None)
            attempt = self.registry.plan(plan['request_id'] + ':' + experiment['experiment_id'], spec)
            entries.append({**experiment, 'attempt_id': attempt})
        return dict(status='REGISTERED', registry_version='TrialRegistry/v1', campaign_id=campaign,
                    plan_sha256=plan['plan_sha256'], experiments=entries,
                    contract={'frozen_at': plan['frozen_at'], 'oos_start': settings['split'],
                              'oos_end': settings['end'], 'holdout_status': 'RETROSPECTIVE_PREVIOUSLY_OBSERVED'},
                    dataset_sha256=plan['dataset']['sha256'])

    def start(self, registration, variant_id):
        for exp in registration['experiments']:
            if exp['factor_variant_id'] == variant_id:
                self.registry.record(exp['attempt_id'], event_id='start', state='started',
                                     results_observed='UNOBSERVED', affects_selection='NO',
                                     reason='Starting registered factor computation on historically observed input')

    def complete(self, registration, outcome):
        variant_id = outcome['mapping']['identity']['factor_variant_id']
        for exp in registration['experiments']:
            if exp['factor_variant_id'] == variant_id:
                self.registry.record(exp['attempt_id'], event_id='outcome',
                                     state='failed' if outcome['status'] == 'FAILED' else 'completed',
                                     results_observed='OBSERVED', affects_selection='YES',
                                     reason='All diagnostic outcomes retained, without selecting a winner',
                                     result_refs={'run_id': outcome['run_id'], 'outcome_sha256': digest(outcome)})
        return self.evaluate(registration, [outcome])

    def evaluate(self, registration, outcomes):
        scope = self.registry.snapshot([registration['campaign_id']])
        return assess_research_integrity(
            study_kind='EXPLORATORY_ANALYSIS', contract=registration['contract'],
            selection_scope=scope, dataset_fingerprint=registration['dataset_sha256'],
            statistical_methods={name: {'status': 'NOT_APPLICABLE', 'decision_use': 'NONE',
                'reason': 'Factor association is not a portfolio-return series'} for name in ('dsr', 'pbo')})
