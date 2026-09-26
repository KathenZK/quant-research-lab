import copy
import json
from pathlib import Path
import pytest
from strategy_lab.knowledge.promotion_v2 import validate_artifact

ROOT = Path(__file__).resolve().parents[1] / 'contracts/fixtures-v2'


def test_bound_paper_fixture_and_research_only_rejection():
    value = json.loads((ROOT / 'synthetic-artifact.json').read_text())
    args = {'code_bytes': (ROOT / 'synthetic-code.txt').read_bytes(), 'config_bytes': (ROOT / 'synthetic-config.json').read_bytes()}
    assert validate_artifact(value, **args)['runtime_enabled'] is False
    for field, replacement in [('promotion_status', 'RESEARCH_ONLY'), ('producer', 'quant-knowledge-graph'),
                               ('approved_at', '2999-01-01T00:00:00Z'), ('approved_by', ' ')]:
        bad = copy.deepcopy(value)
        bad[field] = replacement
        with pytest.raises(Exception):
            validate_artifact(bad, **args)
    with pytest.raises(ValueError):
        validate_artifact(value, environment='live', **args)
    with pytest.raises(ValueError, match='hash'):
        validate_artifact(value, **{**args, 'code_bytes': b'changed'})
    value['parameters']['injected'] = True
    with pytest.raises(ValueError, match='configuration'):
        validate_artifact(value, **args)
