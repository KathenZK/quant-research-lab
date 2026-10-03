"""Run one authorized command and retain measured runtime and all output."""
import argparse
import datetime as dt
import json
from pathlib import Path
import resource
import subprocess
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);p.add_argument('--stdout',type=Path,required=True);p.add_argument('--stderr',type=Path,required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    cmd=a.command[1:] if a.command[0]=='--' else a.command
    assert not a.receipt.exists() and not a.stdout.exists() and not a.stderr.exists()
    before=resource.getrusage(resource.RUSAGE_CHILDREN);start=dt.datetime.now(dt.timezone.utc).isoformat();tick=time.perf_counter()
    with a.stdout.open('xb') as out,a.stderr.open('xb') as err:
        process=subprocess.run(cmd,stdout=out,stderr=err,check=False)
    elapsed=time.perf_counter()-tick;end=dt.datetime.now(dt.timezone.utc).isoformat();after=resource.getrusage(resource.RUSAGE_CHILDREN)
    report=dict(start_utc=start,end_utc=end,wall_seconds=elapsed,child_cpu_user_seconds=after.ru_utime-before.ru_utime,child_cpu_system_seconds=after.ru_stime-before.ru_stime,child_cpu_seconds=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime),max_child_rss_kib=after.ru_maxrss,exit_code=process.returncode,command=cmd)
    with a.receipt.open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));raise SystemExit(process.returncode)

if __name__=='__main__':main()
