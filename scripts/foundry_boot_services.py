#!/usr/bin/python3
"""Plan, install or roll back Foundry's three user-owned boot services.

No reboot, credential changes, media processing or automatic mount changes.
"""
import argparse
import grp
import http.cookiejar
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.request

LABELS=('org.forge.local.ollama','org.forge.local.controller','com.curator.foundry')

def command(*args, check=True):
    return subprocess.run(args,check=check,capture_output=True,text=True,timeout=35)

def loaded(target):
    return command('/bin/launchctl','print',target,check=False).returncode==0

def definitions(user):
    account=pwd.getpwnam(user)
    if account.pw_uid==0:raise ValueError('Services must run as a non-root account')
    home=Path(account.pw_dir);items=[]
    for label in LABELS:
        source=home/'Library/LaunchAgents'/(label+'.plist')
        destination=Path('/Library/LaunchDaemons')/(label+'.plist')
        if source.is_symlink() or not source.is_file():raise ValueError('Expected regular source plist: '+str(source))
        if destination.exists() or destination.is_symlink():raise ValueError('Existing system service preserved: '+str(destination))
        raw=source.read_bytes();properties=plistlib.loads(raw)
        if properties.get('Label')!=label:raise ValueError('Unexpected source label')
        if not properties.get('KeepAlive'):raise ValueError('Source must already support relaunch')
        if not properties.get('ProgramArguments') or not Path(properties['ProgramArguments'][0]).is_file():raise ValueError('Missing executable')
        properties.update(UserName=user,GroupName=grp.getgrgid(account.pw_gid).gr_name,RunAtLoad=True)
        properties.pop('LimitLoadToSessionType',None)
        environment=properties.setdefault('EnvironmentVariables',{})
        environment.update(HOME=str(home),USER=user,LOGNAME=user)
        if label=='com.curator.foundry':environment['CURATOR_SERVICE_STARTUP']='boot'
        items.append((label,source,destination,raw,properties))
    return account,items

def assert_idle(home):
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client.open('http://10.0.0.106:8790/',timeout=5).close()
    with client.open('http://10.0.0.106:8790/api/state',timeout=15) as response:s=json.load(response)
    if s.get('queue_running') or any(t['status'] in ('running','publishing') for t in s['tasks']) or any(x.get('running') for key in ('scans','presence') for x in s.get(key,{}).values()):
        raise ValueError('Curator has active work; wait before migration')
    db=Path(home)/'Projects/forge/state/tasks.sqlite3'
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as connection:
        count=connection.execute("select count(*) from tasks where status not in ('succeeded','failed','cancelled')").fetchone()[0]
    if count:raise ValueError('Forge has unfinished tasks; wait before migration')

def verify_ready(home):
    context=ssl.create_default_context(cafile=str(Path(home)/'forge-tls/server-cert.pem'))
    token=json.loads((Path(home)/'Projects/forge/.secrets/mcp-token.json').read_text())['token']
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    request=urllib.request.Request('https://10.0.0.106:8787/health/ready',headers={'Authorization':'Bearer '+token})
    with client.open(request,timeout=5) as response:
        if response.status!=200:raise RuntimeError('Forge is not ready')
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5) as response:json.load(response)


def stop(target,label):
    if not loaded(target):return
    command('/bin/launchctl','kill','SIGINT' if label=='com.curator.foundry' else 'SIGTERM',target)
    end=time.monotonic()+30
    while time.monotonic()<end:
        info=command('/bin/launchctl','print',target,check=False)
        if info.returncode or not re.search(r'^\s*state = running$',info.stdout,re.M):break
        time.sleep(.2)
    else:raise RuntimeError('Service did not stop gracefully: '+label)
    if loaded(target):command('/bin/launchctl','bootout',target)
    end=time.monotonic()+10
    while loaded(target) and time.monotonic()<end:time.sleep(.2)
    if loaded(target):raise RuntimeError('Service remains loaded: '+label)

def restore(backup):
    manifest=json.loads((backup/'manifest.json').read_text())
    for item in reversed(manifest['items']):
        destination=Path(item['destination']);source=Path(item['source']);label=item['label']
        # Delete only the exact generated definition; preserve unrelated changes.
        generated=backup/(label+'.system.plist')
        if destination.exists():
            if not generated.exists() or destination.read_bytes()!=generated.read_bytes():raise ValueError('System definition changed; inspect before rollback')
            if loaded('system/'+label):stop('system/'+label,label)
            destination.unlink()
        original=backup/(label+'.agent.plist')
        if not source.exists():
            shutil.copyfile(original,source);os.chown(source,manifest['uid'],manifest['gid']);source.chmod(0o600)
        elif source.read_bytes()!=original.read_bytes():raise ValueError('Login definition changed; inspect before rollback')
    for item in manifest['items']:
        target='gui/'+str(manifest['uid'])+'/'+item['label']
        if not loaded(target):command('/bin/launchctl','bootstrap','gui/'+str(manifest['uid']),item['source'])

def apply(user):
    account,items=definitions(user);assert_idle(account.pw_dir)
    backup=Path('/Library/Application Support/FoundryServiceMigration')/time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    manifest={'uid':account.pw_uid,'gid':account.pw_gid,'items':[]}
    for label,source,destination,raw,properties in items:
        (backup/(label+'.agent.plist')).write_bytes(raw)
        (backup/(label+'.system.plist')).write_bytes(plistlib.dumps(properties))
        manifest['items'].append(dict(label=label,source=str(source),destination=str(destination)))
    (backup/'manifest.json').write_text(json.dumps(manifest))
    try:
        # Pause ingress first, then inference; no duplicate system/login processes.
        for label,source,destination,raw,properties in reversed(items):stop('gui/'+str(account.pw_uid)+'/'+label,label)
        for label,source,destination,raw,properties in items:
            if source.read_bytes()!=raw:raise ValueError('Source definition changed during migration')
            with destination.open('xb') as output:output.write(plistlib.dumps(properties))
            os.chown(destination,0,0);destination.chmod(0o600)
            source.unlink()
        for label,source,destination,raw,properties in items:
            command('/bin/launchctl','bootstrap','system',str(destination))
        end=time.monotonic()+60
        while time.monotonic()<end:
            ready=True
            for label in LABELS:
                output=command('/bin/launchctl','print','system/'+label,check=False)
                ready=ready and output.returncode==0 and bool(re.search(r'^\s*state = running$',output.stdout,re.M))
            if ready:
                try:
                    assert_idle(account.pw_dir)
                    verify_ready(account.pw_dir)
                    break
                except Exception:pass
            time.sleep(1)
        else:raise RuntimeError('Boot services did not become ready')
    except BaseException:
        print('Migration failed; restoring login services from '+str(backup),flush=True)
        restore(backup);raise
    print(json.dumps({'installed_boot_services':list(LABELS),'run_as':user,'backup':str(backup),'reboot_verified':False,'filevault_changed':False,'mounts_changed':False}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user',default='mike')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--apply',action='store_true')
    action.add_argument('--rollback',type=Path)
    args=parser.parse_args()
    if sys.platform!='darwin':parser.error('This migration requires macOS')
    if args.apply or args.rollback:
        if os.geteuid()!=0:parser.error('Administrator access required; run with sudo')
        if args.rollback:restore(args.rollback.resolve())
        else:apply(args.user)
    else:
        account,items=definitions(args.user);assert_idle(account.pw_dir)
        print(json.dumps({'plan_only':True,'run_as':args.user,'services':[{'label':x[0],'source':str(x[1]),'destination':str(x[2]),'run_at_load':x[4]['RunAtLoad'],'explicit_home':x[4]['EnvironmentVariables']['HOME']} for x in items],'filevault_changed':False,'reboot_required_for_acceptance':True}))

if __name__=='__main__':main()
