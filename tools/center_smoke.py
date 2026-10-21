"""Reproducible isolated Phase 2 HTTP/mini/browser smoke. Never contacts live models.

Uses fresh project/volume, trusted predefined tasks and local inference stub.
Only its dedicated worker can control Docker. Cleanup always targets its own name.
"""
import argparse
import hashlib
import json
import pathlib
import secrets
import shutil
import subprocess
import time
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    parser.add_argument('--port',type=int,default=18090)
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--api-image',default='swe-center-smoke-api:local')
    parser.add_argument('--worker-image',default='swe-center-smoke-worker:local')
    parser.add_argument('--sandbox-image',default='swe-center-smoke-sandbox:local')
    parser.add_argument('--grader-image',default='swe-center-smoke-grader:local')
    parser.add_argument('--browser-image',default='swe-center-smoke-browser:local')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():parser.error('--output must be a NEW evidence directory')
    if not 1024<=args.port<=65535:parser.error('invalid test port')
    out.mkdir(parents=True);project='swe-center-smoke-'+secrets.token_hex(5)
    def command(argv,name):
        with (out/name).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    if args.build:
        for image,file,target,extra in [(args.sandbox_image,'sandbox',None,[]),
            (args.grader_image,'grader',None,['--build-arg','SANDBOX_IMAGE='+args.sandbox_image]),
            (args.api_image,'service','api',[]),(args.worker_image,'service','worker',[])]:
            command(['docker','build','-t',image,'-f',f'docker/{file}.Dockerfile',*(['--target',target] if target else []),*extra,'.'],'build-'+file+(target or '')+'.log')
        if args.browser:command(['docker','build','-t',args.browser_image,'-f','docker/browser-tests.Dockerfile','.'],'build-browser.log')
    tasks=out/'tasks/intervals';shutil.copytree(ROOT/'src/swe_eval/benchmarks/data/intervals',tasks,ignore=shutil.ignore_patterns('__pycache__'))
    task=json.loads((tasks/'task.json').read_text());task['runtime'].update(agent_image=args.sandbox_image,evaluator_image=args.grader_image);(tasks/'task.json').write_text(json.dumps(task))
    profiles=[dict(id=id,model_id='deterministic-local-model',upstream_id=id,base_url=f'http://stub:8080/{mode}/v1',allow_http=True,allow_no_api_key=True,data_origin='local_stub',max_agent_steps=4,max_model_calls=5,max_output_tokens=300,max_evaluation_duration=30) for id,mode in [('stub-good','repair'),('stub-bad','submit-only'),('stub-error','status503'),('stub-sleep','sleep')]]
    (out/'models.json').write_text(json.dumps(profiles));shutil.copy(ROOT/'tests/support/model_stub.py',out/'stub.py')
    salt=secrets.token_hex(16);password='phase2-browser-only-password'
    password_hash='pbkdf2_sha256$600000$'+salt+'$'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    token='phase2-local-smoke-only-admin-token'
    env=dict(SWE_DATA_DIR='/data',SWE_MODELS_FILE='/audit/models.json',SWE_TASK_DIR='/audit/tasks')
    common=dict(read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],tmpfs=['/tmp:size=128m,noexec,nosuid,nodev'])
    volumes=[f'{out}:/audit:ro','smoke-data:/data']
    api=dict(common,image=args.api_image,environment=dict(env,SWE_ADMIN_TOKEN=token,SWE_UI_PASSWORD_HASH=password_hash.replace('$','$$'),SWE_COOKIE_SECURE='false',SWE_PUBLIC_ORIGIN='http://api:8000'),volumes=volumes,ports=[f'127.0.0.1:{args.port}:8000'])
    worker=dict(common,image=args.worker_image,environment=dict(env,MSWEA_GLOBAL_CONFIG_DIR='/tmp/mini'),volumes=volumes+['/var/run/docker.sock:/var/run/docker.sock'],group_add=['0'],init=True,stop_grace_period='10s')
    stub=dict(common,image=args.api_image,command=['python','/audit/stub.py'],volumes=[f'{out}/stub.py:/audit/stub.py:ro'])
    config=out/'compose.json';config.write_text(json.dumps(dict(name=project,services=dict(api=api,worker=worker,stub=stub),volumes={'smoke-data':{}})))
    compose=['docker','compose','--env-file','/dev/null','-f',str(config)]
    def request(path,body=None):
        req=urllib.request.Request(f'http://127.0.0.1:{args.port}'+path,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
    try:
        command(compose+['config','--quiet'],'compose-validation.log')
        command(compose+['up','-d','--no-build'],'startup.log')
        for _ in range(60):
            try:
                if request('/health')['status']=='ok':break
            except OSError:pass
            time.sleep(1)
        body=dict(name='Reproducible local smoke',task_ids=['intervals-001'],model_profile_ids=['stub-good','stub-bad','stub-error'],attempts=1,idempotency_key='local-smoke-001',limits=dict(timeout=25,steps=4,requests=5,output_tokens=300,total_tokens=1000),max_duration=180,max_requests=15)
        batch=request('/api/v1/batches',body)
        for _ in range(100):
            batch=request('/api/v1/batches/'+batch['id'])
            if batch['terminal']==3:break
            time.sleep(1)
        (out/'batch.json').write_text(json.dumps(batch,indent=2))
        results={a['profile_id']:a for a in batch['attempts']}
        assert results['stub-good']['metrics']['resolved'] is True,batch
        assert results['stub-bad']['metrics']['resolved'] is False,batch
        assert results['stub-error']['state']=='failed' and results['stub-error']['metrics']['resolved'] is None,batch
        assert request('/api/v1/shadow/results')['items']==[]
        if args.browser:
            command(['docker','run','--rm','--network',project+'_default','-e','SWE_BROWSER_URL=http://api:8000','-v',f'{out}:/evidence',args.browser_image],'browser.log')
        (out/'result.json').write_text(json.dumps({'status':'PASS','project':project,'external_model_requests':0,'browser_executed':args.browser},indent=2))
        print('PASS: real local mini/Docker batch; evidence at',out)
    finally:
        try:command(compose+['logs','--no-color'],'services.log')
        finally:command(compose+['down','-v','--remove-orphans'],'cleanup.log')


if __name__=='__main__':main()
