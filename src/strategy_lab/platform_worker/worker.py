"""Leased local worker; requests never select code, shell commands or file paths."""
import argparse
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time
import traceback
from uuid import uuid4


CAPABILITIES = {'discovery-v1'}


def _write(path, value):
    temp = path.with_suffix('.tmp-' + uuid4().hex)
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    os.replace(temp, path)


def _repository(config):
    from quantgraph.graph.research_jobs import ResearchJobRepository
    return ResearchJobRepository(config['job_db'], config['profiles'], **config.get('limits', {}))


def _child(config, job, pipe):
    """The watchdog also exits an orphan child after supervisor/lease loss."""
    repo = _repository(config)
    root = Path(config['output_root']).resolve() / job['job_id']
    root.mkdir(parents=True, exist_ok=True)
    profile = config['profiles'][job['profile']]
    token = job['lease_token']
    stopped = threading.Event()

    def still_owned():
        current = repo.get(job['job_id'])
        return (current['status'] == 'RUNNING' and current['lease_token'] == token
                and current['lease_until'] > time.time() and not current['cancel_requested'])

    def watchdog():
        while not stopped.wait(.5):
            try:
                if not still_owned() or time.time() - job['started'] > job['seconds_budget']:
                    os._exit(75)
            except Exception:
                # Without authoritative lease state, computation must stop.
                os._exit(76)

    threading.Thread(target=watchdog, daemon=True).start()
    with (root / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not still_owned():
            stopped.set()
            return
        try:
            from quantgraph.factor_study import digest
            binding = digest({'request':job['request'],'profile':profile})
            cached = root / 'worker-result.json'
            if cached.exists():
                value = json.loads(cached.read_text())
                if value['binding'] != binding:
                    raise ValueError('Completed job binding changed')
                pipe.send(('done', value['results']))
                return
            capability = profile['capability']
            if capability not in CAPABILITIES:
                raise ValueError('Capability is not registered in this worker')
            # This import is fixed in trusted source, never derived from a request.
            from strategy_lab.discovery.capabilities import execute

            def checkpoint(stage, progress):
                if isinstance(progress, dict):
                    progress = progress['completed'] / max(1, progress['total'])
                pipe.send(('progress', (stage, float(progress))))

            context = dict(run_id=job['run_id'], server_config=profile['server_config'],
                           output_dir=root / 'research', registry_path=Path(config['registry_path']),
                           checkpoint=checkpoint, cancelled=lambda: not still_owned())
            results = execute(job['request'], context)
            if not still_owned():
                return
            _write(cached, {'binding':binding, 'results':results})
            pipe.send(('done', results))
        except Exception as exc:
            _write(root / ('failure-' + str(job['attempts']) + '.json'),
                   {'type':type(exc).__name__, 'message':str(exc), 'traceback':traceback.format_exc()})
            pipe.send(('error', {'code':'CAPABILITY_FAILED',
                                 'message':f'Registered capability failed ({type(exc).__name__}); evidence retained under run {job["run_id"]}'}))
        finally:
            stopped.set()
            pipe.close()


class Worker:
    def __init__(self, config):
        self.config = config
        self.worker_id = 'worker-' + uuid4().hex
        self.repo = _repository(config)
        self.profiles = [key for key,p in config['profiles'].items() if p['capability'] in CAPABILITIES]
        if not self.profiles:
            raise ValueError('No registered capabilities configured')

    def run_once(self):
        from quantgraph.graph.research_jobs import LeaseLost
        self.repo.announce(self.worker_id, self.profiles)
        job = self.repo.claim(self.worker_id, self.profiles)
        if job is None:
            return False
        ctx = multiprocessing.get_context('spawn')
        receive, send = ctx.Pipe(duplex=False)
        child = ctx.Process(target=_child, args=(self.config,job,send))
        child.start()
        send.close()
        stage, progress = 'EXECUTING_REGISTERED_CAPABILITY', 0
        status, results, error = 'FAILED', None, None
        last_heartbeat = 0
        try:
            while True:
                now = time.time()
                if now-last_heartbeat >= 2:
                    self.repo.announce(self.worker_id,self.profiles)
                    cancelled = self.repo.heartbeat(job['job_id'],job['lease_token'],stage=stage,progress=progress)
                    last_heartbeat = now
                    if cancelled:
                        status = 'CANCELLED'
                        break
                    if now-job['started'] > job['seconds_budget']:
                        error = {'code':'BUDGET_EXCEEDED','message':'Registered runtime budget exceeded; partial artifacts retained'}
                        break
                if receive.poll(.2):
                    try:
                        kind, value = receive.recv()
                    except EOFError:
                        error = {'code':'WORKER_CHILD_EXITED','message':'Research process stopped before completing; artifacts retained'}
                        break
                    if kind == 'progress':
                        stage, progress = value
                    elif kind == 'done':
                        results = value
                        good = [v for v in results if v.get('status', 'SUCCESS') == 'SUCCESS']
                        status = 'SUCCEEDED' if good and len(good)==len(results) else ('PARTIAL' if good else 'FAILED')
                        if not good:
                            error = {'code':'NO_SUCCESSFUL_RESULT','message':'Research completed without a valid result; failure evidence retained'}
                        break
                    elif kind == 'error':
                        error = value
                        break
                if not child.is_alive() and not receive.poll():
                    error = {'code':'WORKER_CHILD_EXITED','message':'Research process stopped before completing; artifacts retained'}
                    break
            try:
                self.repo.finish(job['job_id'],job['lease_token'],status=status,results=results,error=error)
            except ValueError as exc:
                root = Path(self.config['output_root'])/job['job_id']
                _write(root/'writeback-failure.json', {'reason':str(exc)})
                self.repo.finish(job['job_id'],job['lease_token'],status='BLOCKED',
                                 error={'code':'RESULT_CONTRACT_FAILED','message':'Lab result failed bridge validation; original evidence retained'})
        except LeaseLost:
            # Another worker owns recovery; this worker must not change its state.
            pass
        finally:
            if child.is_alive():
                child.terminate()
            child.join(timeout=5)
            if child.is_alive():
                child.kill()
                child.join()
            receive.close()
        return True


def main():
    parser = argparse.ArgumentParser(description='Run only registered Lab research capabilities')
    parser.add_argument('--config', type=Path, required=True, help='Trusted operator configuration; never HTTP input')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    worker = Worker(config)
    while True:
        worked = worker.run_once()
        if args.once:
            break
        if not worked:
            time.sleep(1)


if __name__ == '__main__':
    main()
