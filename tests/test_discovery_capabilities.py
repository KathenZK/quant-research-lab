import pytest
from strategy_lab.discovery.capabilities import execute


@pytest.mark.parametrize('settings', [{'profile_id':'wrong'}, {'profile_id':'approved', 'manifest':'/tmp/injected'}, {'profile_id':'approved', 'code':'print(1)'}])
def test_worker_rejects_client_paths_and_unapproved_profiles(settings):
    with pytest.raises(ValueError, match='approved server profile'):
        execute({'status':'DRAFT', 'study_type':'FACTOR_DIAGNOSTIC', 'requested_settings': settings},
                {'server_config': {'profile_id':'approved'}})
