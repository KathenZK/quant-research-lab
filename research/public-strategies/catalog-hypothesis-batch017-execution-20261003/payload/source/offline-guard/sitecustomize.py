"""Frozen Python-only no-network audit guard; not an OS network namespace."""
import os
import sys
def reject_network(event, args):
    if event.startswith('socket.') and event not in ('socket.__new__',):
        path=os.environ.get('BATCH017_DENIED_SOCKET_LOG')
        if path:
            with open(path,'a') as f:f.write(event+'\n')
        raise RuntimeError('Offline research guard denied '+event)
sys.addaudithook(reject_network)
