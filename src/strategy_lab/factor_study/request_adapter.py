"""Resolve a web DRAFT against public definitions and separately reviewed settings."""
import json
from pathlib import Path
from quantgraph import FactorDB
from quantgraph.factor_study import definition_identity
from .factors import definition_name
from .pipeline import validate_schema


def resolve_request(request_path, settings_path, graph_root):
    request = json.loads(Path(request_path).read_text())
    validate_schema(request, graph_root, 'research-request')
    if request['study_type'] != 'FACTOR_DIAGNOSTIC':
        raise ValueError('This adapter accepts factor diagnostics only')
    settings = json.loads(Path(settings_path).read_text())
    requested = request['requested_settings']
    allowed = {'market', 'start_date', 'end_date', 'notes'}
    if set(requested) - allowed:
        raise ValueError('Unreviewed requested settings; explicit review required')
    expected = {'market': settings['study_asset_class'], 'start_date': settings['start'][:10],
                'end_date': settings['end'][:10]}
    if any(requested.get(k) and requested[k] != v for k, v in expected.items()):
        raise ValueError('Requested scope differs from reviewed frozen settings')
    db = FactorDB(graph_root, profile='commercial')
    definitions = []
    for ref in request['entity_refs']:
        if ref['entity_type'] != 'FactorVariant':
            raise ValueError('Choose a concrete FactorVariant')
        variant = db.get_variant(ref['entity_id'])
        if definition_identity(variant)['definition_revision'] != ref['definition_revision']:
            raise ValueError('Requested definition revision is stale')
        definitions.append(variant)
    names = [definition_name(v) for v in definitions]
    if names != settings['names'] or len(set(names)) != len(names):
        raise ValueError('Reviewed factor selection differs from DRAFT')
    return {'request': request, 'definitions': definitions, 'resolved_settings': settings,
            'graph_release': db.stats()['release']}
