"""Deny all Python socket audit events, inherited through PYTHONPATH by replay child."""
import os,sys,json,time
log=os.environ.get('M1358_OFFLINE_AUDIT_LOG')
def audit(event,args):
    if event.startswith('socket.'):
        if log:
            with open(log,'a') as f:f.write(json.dumps({'event':'DENIED','audit_event':event,'pid':os.getpid()})+'\n')
        raise PermissionError('M1358 QA offline socket guard: '+event)
sys.addaudithook(audit);sys._m1358_offline_guard=True
if log:
    with open(log,'a') as f:f.write(json.dumps({'event':'GUARD_ACTIVE','pid':os.getpid(),'executable':sys.executable,'time':time.time()})+'\n')
