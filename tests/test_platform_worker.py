"""Transport-level tests. Test stubs are never registered production capabilities."""
import json
from pathlib import Path

import pytest

pytest.importorskip('quantgraph.graph.research_jobs')
from quantgraph.graph.research_jobs import ResearchJobRepository
from strategy_lab.platform_worker.worker import Worker, _child


def setup(tmp_path):
    profile=dict(study_type='FACTOR_DIAGNOSTIC',entity_types=['FactorVariant'],
                 capability='discovery-v1',max_trials=2,max_seconds=60,
                 server_config={'profile_id':'approved'})
    config=dict(job_db=str(tmp_path/'jobs.sqlite'),profiles={'approved':profile},
                output_root=str(tmp_path/'runs'),registry_path=str(tmp_path/'trials.jsonl'))
    repo=ResearchJobRepository(config['job_db'],config['profiles'])
    request=dict(request_id='test-only',study_type='FACTOR_DIAGNOSTIC',
                 entity_refs=[dict(entity_type='FactorVariant',entity_id='test',definition_revision='a'*64)],
                 requested_settings={'profile_id':'approved'})
    job,_=repo.submit(request,owner='test',resolve_ref=lambda **r:r)
    return config,repo,job


class Pipe:
    def __init__(self):self.messages=[]
    def send(self,value):self.messages.append(value)
    def close(self):pass


def test_cached_recovery_reuses_same_registered_attempt(tmp_path,monkeypatch):
    from strategy_lab.discovery import capabilities
    from strategy_lab.research.trials import TrialRegistry
    config,repo,job=setup(tmp_path)
    attempts=[]

    def execute(request,context):
        registry=TrialRegistry(context['registry_path'])
        registry.register_campaign('test',selection_goal='Transport test',scope_definition='Explicit fixture',
                                   history_completeness='UNKNOWN',history_reason='Test only')
        spec=dict(hypothesis_family_id='test',selection_campaign_id='test',identity={'id':'test'},
                  parameters={},label_horizon=1,objective='test',selection_rule='retain',
                  dataset_fingerprint='a'*64,sample_fingerprint='b'*64,code_hash='c'*64,
                  config_hash='d'*64,parent_experiment_id=None)
        attempt=registry.plan(context['run_id'],spec)
        attempts.append(attempt)
        context['checkpoint']('TEST_COMPUTED',{'completed':1,'total':1})
        return [{'test_only':True,'attempt_id':attempt}]

    monkeypatch.setattr(capabilities,'execute',execute)
    claimed=repo.claim('first',['approved'])
    pipe=Pipe()
    _child(config,claimed,pipe)
    assert pipe.messages[-1][0]=='done'
    second=Pipe()
    _child(config,claimed,second)
    assert second.messages[-1]==pipe.messages[-1]
    assert len(attempts)==1
    assert repo.get(job['job_id'])['attempts']==1


def test_registered_process_failure_is_retained_and_not_swallowed(tmp_path):
    config,repo,job=setup(tmp_path)
    # Intentionally incomplete trusted configuration fails before reading data.
    assert Worker(config).run_once()
    completed=repo.get(job['job_id'])
    assert completed['status']=='FAILED'
    assert completed['error']['code']=='CAPABILITY_FAILED'
    assert completed['error']['message'].startswith('Registered capability failed')
    private=json.loads((Path(config['output_root'])/job['job_id']/'failure-1.json').read_text())
    assert private['type']=='KeyError' and 'traceback' in private


def test_arbitrary_module_name_is_not_a_capability(tmp_path):
    config,_,_=setup(tmp_path)
    config['profiles']['approved']['capability']='os.system'
    with pytest.raises(ValueError,match='No registered'):
        Worker(config)
