"""Worker entry point. Paths and executable choices come only from server config."""
from pathlib import Path
import json
from strategy_lab.factor_study.pipeline import digest, freeze, run, write
from strategy_lab.factor_study.registered_trials import RegisteredTrialAdapter


def _get(context, key):
    return context[key] if isinstance(context, dict) else getattr(context, key)


def execute(request: dict, context) -> list[dict]:
    """Execute an approved factor profile; stable job context makes retries resumable.

    context: run_id, server_config, output_dir, registry_path, checkpoint(stage,
    progress), cancelled(). server_config is trusted worker configuration, never
    request content. It pins profile_id/settings/manifest/acquisition_contract/
    graph_root/lab_root/journal. No submitted expression or module is executed.
    """
    cfg = _get(context, 'server_config')
    if request.get('status') != 'DRAFT' or request.get('study_type') != 'FACTOR_DIAGNOSTIC':
        raise ValueError('Only approved factor diagnostic DRAFTs are supported')
    settings = request.get('requested_settings', {})
    if set(settings) - {'profile_id', 'notes'} or settings.get('profile_id') != cfg['profile_id']:
        raise ValueError('Request must select the approved server profile only')
    from quantgraph import FactorDB
    from quantgraph.factor_study import definition_identity
    from strategy_lab.factor_study.factors import definition_name
    db = FactorDB(cfg['graph_root'], profile='commercial')
    definitions = []
    for ref in request['entity_refs']:
        if ref['entity_type'] != 'FactorVariant':
            raise ValueError('A concrete factor variant is required')
        v = db.get_variant(ref['entity_id'])
        if definition_identity(v)['definition_revision'] != ref['definition_revision']:
            raise ValueError('Definition revision changed')
        definitions.append(v)
    names = [definition_name(v) for v in definitions]
    if not names or len(set(names)) != len(names) or set(names) - set(cfg['settings']['names']):
        raise ValueError('Unapproved factor selection')
    root = Path(_get(context, 'output_dir')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    binding = {'request': request, 'server_config': cfg, 'run_id': _get(context, 'run_id'),
               'registry_path': str(_get(context, 'registry_path'))}
    receipt = root / 'request-binding.json'
    if receipt.exists():
        if json.loads(receipt.read_text()) != binding:
            raise ValueError('Job inputs changed during retry')
    else:
        write(receipt, binding)
    adapter = RegisteredTrialAdapter(_get(context, 'registry_path'))
    plan = root / 'study' / 'plan.json'
    if not plan.exists():
        approved = {**cfg['settings'], 'names': names}
        draft = {k: request[k] for k in ('schema_version', 'entity_refs', 'study_type', 'status')}
        draft.update(request_id=_get(context, 'run_id'), requested_settings=approved)
        selection = {'request': draft, 'definitions': definitions, 'resolved_settings': approved}
        p = root / ('selection-' + digest(selection) + '.json')
        if not p.exists():
            write(p, selection)
        freeze(p, cfg['manifest'], cfg['acquisition_contract'], plan.parent,
               graph_root=cfg['graph_root'], lab_root=cfg['lab_root'], trial_adapter=adapter)
    for i, name in enumerate(names):
        if _get(context, 'cancelled')():
            _get(context, 'checkpoint')('CANCELLED_BETWEEN_FACTORS', {'completed': i, 'total': len(names)})
            return []
        run(plan, graph_root=cfg['graph_root'], lab_root=cfg['lab_root'], journal=cfg['journal'],
            only=name, trial_adapter=adapter)
        _get(context, 'checkpoint')('FACTOR_COMPLETE', {'completed': i + 1, 'total': len(names)})
    return [json.loads((plan.parent / 'runs' / n / 'result.json').read_text()) for n in names]
