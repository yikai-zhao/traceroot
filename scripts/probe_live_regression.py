#!/usr/bin/env python3
"""Real localhost HTTP frontend->backend timing audit against TraceRoot compare_runs.

Two services share a Python process and CLOCK_MONOTONIC identity. This exercises
real TCP/HTTP, not cross-machine clocks, production tracing, or causal inference.
"""
from __future__ import annotations
import argparse
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import re
from pathlib import Path
import socket
import sys
import threading
import time
from statistics import median

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from traceroot.core import Event
from traceroot.traces import compare_runs

HOST='127.0.0.1'


def observed_clock_host_identity() -> str:
    """Linux boot identity for this one-host demonstration only.

    Self-reported by the local process. Not authenticated across machines.
    """
    boot=Path('/proc/sys/kernel/random/boot_id')
    if not boot.is_file():
        raise RuntimeError('Linux clock host identity unavailable; refusing to label clock provenance verified')
    value=boot.read_text().strip()
    if not re.fullmatch(r'[0-9a-fA-F-]{36}',value):
        raise RuntimeError('invalid Linux boot identifier')
    return 'linux-boot-'+value


def cpu_work(ms):
    start=time.thread_time_ns()
    acc=1
    while time.thread_time_ns()-start < ms*1_000_000:
        for _ in range(200):
            acc=(acc*1664525+1013904223)&0xffffffff
    return time.thread_time_ns()-start,acc

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_args):pass
    def do_GET(self):
        if self.path!='/work':self.send_error(404);return
        trace=self.headers.get('X-Trace-Id')
        if not trace or len(trace)>80 or not trace.replace('-','').isalnum():
            self.send_error(400);return
        s=self.server
        start=time.monotonic_ns()
        if s.role=='backend':
            cpu,checksum=cpu_work(s.cpu_ms)
            result={'trace_id':trace,'start_ns':start,'end_ns':time.monotonic_ns(),
                    'cpu_ns':cpu,'checksum':checksum}
        else:
            conn=HTTPConnection(HOST,s.backend_port,timeout=3)
            try:
                conn.request('GET','/work',headers={'X-Trace-Id':trace})
                resp=conn.getresponse()
                if resp.status!=200:raise RuntimeError('HTTP backend rejected request')
                backend=json.loads(resp.read())
            finally:conn.close()
            cpu,checksum=cpu_work(s.cpu_ms)
            end=time.monotonic_ns()
            if not start<=backend['start_ns']<=backend['end_ns']<=end:
                raise RuntimeError('measured span containment failed')
            result={'trace_id':trace,'start_ns':start,'end_ns':end,'cpu_ns':cpu,
                    'backend':backend,'checksum':checksum}
        data=json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)


def make_server(role,backend_port=0):
    server=ThreadingHTTPServer((HOST,0),Handler)
    server.role=role;server.cpu_ms=1 if role=='frontend' else 2
    server.backend_port=backend_port
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread


def capture(frontend,cohort,n=7,host_id=None):
    if host_id is None:host_id=observed_clock_host_identity()
    rows=[];cpu=[]
    for k in range(n):
        trace=f'{cohort.replace(chr(95), chr(45))}-{k}'
        conn=HTTPConnection(HOST,frontend.server_address[1],timeout=3)
        try:
            conn.request('GET','/work',headers={'X-Trace-Id':trace})
            resp=conn.getresponse()
            if resp.status!=200:raise RuntimeError('HTTP frontend failed')
            observation=json.loads(resp.read())
        finally:conn.close()
        backend=observation['backend']
        if backend['trace_id']!=trace or observation['trace_id']!=trace:
            raise RuntimeError('broken HTTP trace propagation')
        for sid,service,span,parent in [('front','api',observation,None),
                                        ('db','db',backend,'front')]:
            fields={'trace_id':trace,'span_id':sid,'service':service,'operation':'GET /work',
                    'duration_ms':(span['end_ns']-span['start_ns'])/1e6,
                    'clock_domain':'local_monotonic','clock_host_id':host_id}
            if parent:fields['parent_span_id']=parent
            rows.append(Event(f'{trace}-{sid}',span['start_ns'],'service_span',service,fields))
        cpu.append({'trace_id':trace,'front_cpu_ms':observation['cpu_ns']/1e6,
                    'backend_cpu_ms':backend['cpu_ns']/1e6})
    return rows,cpu


def dump(path,events):
    path.write_text(''.join(json.dumps({'id':e.id,'time_ns':e.time_ns,'kind':e.kind,
                   'source':e.source,'fields':e.fields},sort_keys=True)+'\n' for e in events))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reproduce(output:Path,n=7):
    if not 3<=n<=40:raise ValueError('requires 3..40 independent localhost requests per cohort')
    output.mkdir(parents=True,exist_ok=True)
    back,bt=make_server('backend')
    front,ft=make_server('frontend',back.server_address[1])
    try:
        cohorts={}
        scenarios=(('baseline',1,2),('backend_slow',1,42),('frontend_slow',41,2),('control',1,2))
        for label,f,b in scenarios:
            front.cpu_ms=f;back.cpu_ms=b
            traces,cpu=capture(front,label,n)
            path=output/f'{label}.jsonl'
            cohorts[label]={'traces':traces,'cpu':cpu,'sha256':dump(path,traces)}
        baseline=cohorts['baseline']['traces']
        decisions={label:compare_runs(baseline,cohorts[label]['traces'])
                   for label in ('backend_slow','frontend_slow','control')}
        if decisions['backend_slow']['decision']!='regression_observed' or decisions['backend_slow']['hypothesis']['service']!='db':
            raise RuntimeError('backend intervention attribution incorrect')
        if decisions['frontend_slow']['decision']!='regression_observed' or decisions['frontend_slow']['hypothesis']['service']!='api':
            raise RuntimeError('frontend intervention attribution incorrect')
        if decisions['control']['decision']!='no_threshold_regression_observed':
            raise RuntimeError('negative control falsely classified')
        # Red-team cohort: remove *all* provenance IDs from candidate while
        # baseline remains tagged; the analyzer must refuse attribution.
        mixed=[]
        for e in cohorts['backend_slow']['traces']:
            fields=dict(e.fields);fields.pop('clock_host_id')
            mixed.append(Event(e.id,e.time_ns,e.kind,e.source,fields))
        withheld=compare_runs(baseline,mixed)
        if withheld['decision']!='insufficient_comparable_evidence' or withheld['hypothesis'] is not None:
            raise RuntimeError('mixed clock provenance falsely accepted')
        result={'status':'PASS','scope':'two real local Python HTTP servers, not distributed hardware',
                'requests_per_cohort':n,'total_actual_http_requests':n*4,
                'host_clock_identity_source':'Linux /proc/sys/kernel/random/boot_id (self-reported)',
                'traces':n*4,'span_rows':n*8,'sha256':{name:c['sha256'] for name,c in cohorts.items()},
                'decisions':decisions,'clock_provenance_negative':withheld,
                'measured_cpu_medians_ms':{name:{'frontend':round(median(x['front_cpu_ms'] for x in c['cpu']),3),
                                                'backend':round(median(x['backend_cpu_ms'] for x in c['cpu']),3)}
                                              for name,c in cohorts.items()},
                'limitations':['Both services run as real TCP HTTP servers on one host/process; no independent clock synchronization.',
                               'CPU work is deliberately injected and known in advance; source-identity labels are self-reported, not cryptographically verified.',
                               'Decision is a measured exclusive-span contributor, not autonomous causal root-cause proof.',
                               'Request cohorts are sequential and under low load; no distributed tracing service, profiling or AI agent.']}
        (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        return result
    finally:
        front.shutdown();back.shutdown();front.server_close();back.server_close()
        ft.join(timeout=1);bt.join(timeout=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('lab-output/live-http'))
    p.add_argument('--requests',type=int,default=7);args=p.parse_args()
    report=reproduce(args.output,args.requests)
    print(json.dumps({'status':report['status'],'requests':report['total_actual_http_requests'],
                      'decisions':{k:v['decision'] for k,v in report['decisions'].items()},
                      'cpu':report['measured_cpu_medians_ms']},indent=2))

if __name__=='__main__':main()
