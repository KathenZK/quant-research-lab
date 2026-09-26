"""Offline v2 contract validation; never creates approval or controls a runner."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

CONFIG_FIELDS = ('parameters', 'market', 'universe', 'execution_config', 'risk_limits', 'data_requirements')


def validate_artifact(value, *, code_bytes, config_bytes, environment='paper', now=None):
    schema = json.loads(Path(__file__).with_name('strategy_artifact_v2.schema.json').read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    json.dumps(value, allow_nan=False)
    if environment not in {'paper', 'live'}:
        raise ValueError('Unknown target environment')
    expected = {'paper': 'APPROVED_FOR_PAPER', 'live': 'APPROVED_FOR_LIVE'}[environment]
    if value['promotion_status'] != expected or value['execution_config']['mode'] != environment:
        raise ValueError('Research-only or promotion/environment mismatch')
    for field in ('strategy_id', 'strategy_variant_id', 'research_run_id', 'version', 'market', 'approved_by', 'approval_reference'):
        if not value[field].strip():
            raise ValueError('Blank identity/approval field')
    if not all(v.strip() for v in value['universe'] + value['data_requirements']):
        raise ValueError('Blank universe/data requirement')
    if not value['execution_config']['timing'].strip() or not value['validation_summary']['evidence_uri'].strip():
        raise ValueError('Blank timing/evidence')
    approved = datetime.fromisoformat(value['approved_at'].replace('Z', '+00:00'))
    if approved > (now or datetime.now(timezone.utc)):
        raise ValueError('Approval is in the future')
    for name, raw in [('code_hash', code_bytes), ('config_hash', config_bytes)]:
        if hashlib.sha256(raw).hexdigest() != value[name]:
            raise ValueError('Artifact content hash mismatch: ' + name)
    config = json.loads(config_bytes)
    json.dumps(config, allow_nan=False)
    if config != {key: value[key] for key in CONFIG_FIELDS}:
        raise ValueError('Bound configuration differs from artifact parameters')
    return {'schema_version': '2.0', 'admission': environment.upper() + '_CONTRACT_VALID',
            'runtime_enabled': False, 'runner_authorization_required': True}
