"""Read-only preflight and resumable environment bootstrap. Runs on Python 3.9+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.forge-install.json'
PROBE = ("import json,sys; print(json.dumps({'version':list(sys.version_info[:3]),"
         "'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix}))")


def python_info(executable):
    # Preserve invocation paths: resolving a venv's interpreter symlink loses its identity.
    response = subprocess.run([str(executable), '-I', '-c', PROBE], capture_output=True,
                              text=True, timeout=10, check=True)
    data = json.loads(response.stdout)
    if not isinstance(data, dict) or set(data) != {'version','executable','prefix','base_prefix'}:
        raise ValueError('Interpreter returned an invalid probe response')
    version = data['version']
    if (not isinstance(version, list) or len(version) != 3
            or any(type(part) is not int or part < 0 for part in version)
            or any(not isinstance(data[key], str) or not data[key]
                   for key in ('executable','prefix','base_prefix'))):
        raise ValueError('Interpreter returned invalid version/path fields')
    return data


def minimum_python(root):
    match = re.search(r'^requires-python\s*=\s*[\'"]>=(\d+)\.(\d+)[\'"]\s*$',
                      (root/'pyproject.toml').read_text(), re.MULTILINE)
    if not match:
        raise ValueError('Unsupported requires-python format; review bootstrap against pyproject.toml')
    return tuple(map(int, match.groups()))


def environment_identity(root, info):
    return {'version':1,'python_version':info['version'],
            'inputs':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                      for name in ('pyproject.toml','requirements.lock','requirements-mcp.lock')}}


def private_state(root):
    return {name:(root/name).exists() or (root/name).is_symlink() for name in ('.secrets','state')}


def ollama_status():
    result = {'executable':shutil.which('ollama'),'reachable':False,'models':[],
              'required_models':['qwen3:8b','qwen3-coder:30b']}
    try:
        # This bootstrap checks the default local runtime; never inherit proxy settings.
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:11434/api/tags',timeout=2) as response:
            raw=response.read(1048577)
        if len(raw)>1048576:
            raise ValueError('Runtime model catalog exceeds limit')
        data=json.loads(raw)
        models=data['models']
        if not isinstance(models,list) or len(models)>1000:
            raise ValueError('Invalid runtime model catalog')
        names=[item['name'] for item in models if isinstance(item,dict) and isinstance(item.get('name'),str)]
        result.update(reachable=True,models=names)
        result['missing_models']=[name for name in result['required_models'] if name not in names]
    except (OSError,ValueError,KeyError,TypeError):
        result['catalog_status']='unavailable; no installation or model download was attempted'
    return result


def service_status():
    if sys.platform!='darwin':
        return {'manager':'launchd','status':'not applicable on this host'}
    domain='gui/'+str(os.getuid())
    status={}
    for name in ('ollama','controller'):
        result=subprocess.run(['launchctl','print',domain+'/org.forge.local.'+name],
                              capture_output=True,timeout=5)
        status[name]={'loaded':result.returncode==0,
            'definition_exists':(Path.home()/'Library/LaunchAgents'/('org.forge.local.'+name+'.plist')).exists()}
    return status


def port_status():
    binary=shutil.which('lsof')
    if not binary:
        return {'status':'unknown; lsof is unavailable'}
    result={}
    for port in (8787,11434):
        response=subprocess.run([binary,'-nP','-iTCP:'+str(port),'-sTCP:LISTEN'],
                                capture_output=True,text=True,timeout=5)
        if response.returncode==0:
            result[str(port)]={'occupied':True}
        elif response.returncode==1 and not response.stderr.strip():
            result[str(port)]={'occupied':False}
        else:
            result[str(port)]={'status':'unknown; listener inspection failed'}
    return result


def check(root, executable):
    root=root.expanduser().absolute()
    brew=shutil.which('brew')
    if not brew:
        brew=next((str(p) for p in (Path('/opt/homebrew/bin/brew'),Path('/usr/local/bin/brew')) if p.is_file()),None)
    result={'checkout':str(root),'host':{'system':platform.system(),'architecture':platform.machine(),
        'disk_free_bytes':shutil.disk_usage(root).free},'brew':{'executable':brew},
        'private_state':private_state(root),'actions':[]}
    required=minimum_python(root)
    result['minimum_python']=list(required)
    try:
        info=python_info(executable)
        info['supported_by_metadata']=tuple(info['version'][:2])>=required
        pip=subprocess.run([str(executable),'-I','-m','pip','--version'],
                           capture_output=True,text=True,timeout=10)
        match=re.match(r'^pip ([^\s]+) from ',pip.stdout)
        info['pip_version']=match.group(1) if pip.returncode==0 and match else None
        result['selected_python']=info
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        result['selected_python']={'executable':str(executable),'supported_by_metadata':False,
                                   'probe_error':type(error).__name__}
    venv=root/'.venv'
    result['environment']={'exists':venv.exists() or venv.is_symlink(),'tool_owned':(venv/MARKER).is_file()}
    if (venv/'bin/python').exists():
        try:result['environment']['python']=python_info(venv/'bin/python')
        except (OSError,ValueError,subprocess.SubprocessError):result['environment']['probe_status']='failed'
    result['ollama']=ollama_status()
    result['services']=service_status()
    result['ports']=port_status()
    if not result['selected_python']['supported_by_metadata']:
        result['actions'].append('Choose an explicit supported interpreter; Python 3.12 matches current CI.')
    if sys.platform=='darwin' and not brew:
        result['actions'].append('Homebrew is absent; follow its official installer before using brew commands.')
    if result['environment']['exists'] and not result['environment']['tool_owned']:
        result['actions'].append('Preserve the existing environment; this installer will not replace it.')
    if any(result['private_state'].values()):
        result['actions'].append('Private configuration/state already exists; use migration or a reviewed upgrade, not fresh initialization.')
    if not result['ollama']['reachable']:
        result['actions'].append('Identify the Ollama launcher before starting or installing a service; do not create a second listener.')
    elif result['ollama']['missing_models']:
        result['actions'].append('Install only missing approved role models after reviewing disk and memory capacity.')
    result['environment_ready']=result['selected_python']['supported_by_metadata']
    return result


def write_marker(path, value):
    fd,name=tempfile.mkstemp(prefix='.forge-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump(value,output,indent=2)
            output.write('\n')
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def install(root, executable):
    root=root.expanduser().absolute()
    executable=executable.expanduser().absolute()
    if root.resolve()!=root:
        raise ValueError('Checkout path must be canonical')
    info=python_info(executable)
    if tuple(info['version'][:2])<minimum_python(root):
        raise ValueError('Unsupported Python; select an explicit interpreter meeting pyproject.toml')
    identity=environment_identity(root,info)
    environment=root/'.venv';marker=environment/MARKER
    if environment.is_symlink():
        raise ValueError('Existing environment is a symlink; preserving it')
    if environment.exists():
        if not environment.is_dir() or marker.is_symlink() or not marker.is_file():
            raise ValueError('Existing environment was not created by this installer; preserving it')
        old=json.loads(marker.read_text())
        if not isinstance(old,dict):
            raise ValueError('Invalid installation marker; preserving environment')
        if {key:old.get(key) for key in identity}!=identity:
            raise ValueError('Interpreter or lock inputs changed; preserve the environment and plan an upgrade')
        if old.get('phase')=='complete':
            actual=python_info(environment/'bin/python')
            if Path(actual['prefix']).resolve()!=environment.resolve() or actual['version']!=info['version']:
                raise ValueError('Existing interpreter no longer matches the validated environment')
            return {'environment':str(environment),'status':'already-installed','services_changed':False}
        if old.get('phase')!='incomplete':
            raise ValueError('Unknown installation marker; preserving environment')
    if any(private_state(root).values()):
        raise ValueError('Private state exists; environment bootstrap requires a fresh checkout or reviewed migration')
    if not environment.exists():
        environment.mkdir(mode=0o700)
        write_marker(marker,{**identity,'phase':'incomplete'})
    python=environment/'bin/python'
    if not python.exists():
        subprocess.run([str(executable),'-m','venv',str(environment)],cwd=root,check=True)
    actual=python_info(python)
    if Path(actual['prefix']).resolve()!=environment.resolve() or actual['version']!=info['version']:
        raise ValueError('Virtual environment probe does not match the selected interpreter')
    steps=[['-m','pip','install','--upgrade','pip','setuptools','wheel'],
           ['-m','pip','install','-r',str(root/'requirements-mcp.lock')],
           ['-m','pip','install','--no-deps','-e',str(root)],
           ['-m','pip','check'],['-m','pytest','-q']]
    for arguments in steps:
        subprocess.run([str(python),*arguments],cwd=root,check=True)
    if environment_identity(root,info)!=identity:
        raise ValueError('Installation inputs changed during setup; environment retained for review')
    write_marker(marker,{**identity,'phase':'complete'})
    return {'environment':str(environment),'status':'installed','tests_passed':True,'services_changed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','install'])
    parser.add_argument('--checkout',type=Path,default=ROOT)
    parser.add_argument('--python',type=Path)
    args=parser.parse_args()
    if args.action=='install' and args.python is None:
        parser.error('install requires an explicit --python /absolute/path/to/python')
    try:
        if args.action=='check':
            result=check(args.checkout,args.python or Path(sys.executable))
            print(json.dumps(result,indent=2))
            if not result['environment_ready']:raise SystemExit(1)
        else:
            print(json.dumps(install(args.checkout,args.python)))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print('Setup stopped: '+str(error),file=sys.stderr)
        print('Existing files are preserved. An incomplete tool-owned environment can resume with the same command.',file=sys.stderr)
        raise SystemExit(1) from None


if __name__=='__main__':
    main()
