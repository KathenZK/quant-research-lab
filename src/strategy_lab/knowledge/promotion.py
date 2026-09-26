"""Offline artifact export; approval evidence is input, never computed from returns."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def validate_artifact(value, *, environment='paper', now=None):
    from jsonschema import Draft202012Validator, FormatChecker
    schema = Path(__file__).with_name('strategy_artifact.schema.json')
    Draft202012Validator(json.loads(schema.read_text()), format_checker=FormatChecker()).validate(value)
    # Reject NaN/Infinity inside parameters too; JSON Schema numeric bounds alone
    # do not provide a complete non-finite-number policy in every validator.
    json.dumps(value, allow_nan=False)
    for name in ('strategy_id', 'variant_id', 'research_run_id', 'version', 'market', 'approved_by', 'approval_reference'):
        if not value[name].strip():
            raise ValueError('Blank identity or approval: ' + name)
    if not value['execution_config']['timing'].strip() or not value['validation_summary']['evidence_uri'].strip():
        raise ValueError('Blank execution timing or evidence')
    if any(not x.strip() for x in value['universe'] + value['required_data']):
        raise ValueError('Blank universe or required data')
    timestamp = datetime.fromisoformat(value['approved_at'].replace('Z', '+00:00'))
    if timestamp > (now or datetime.now(timezone.utc)):
        raise ValueError('Approval is in the future')
    if environment != 'paper':
        raise ValueError('Live activation remains under runner-owned authorization; v1 is paper validation only')
    if value['promotion_status'] != 'APPROVED_FOR_PAPER' or value['execution_config']['mode'] != environment:
        raise ValueError('Promotion/environment mismatch')
    return value


def export_artifact(value, destination):
    validate_artifact(value)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    path = Path(destination)
    with path.open('xb') as stream:
        stream.write(raw)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'runtime_enabled': False, 'approval_source': value['approval_reference']}
