"""Build a deterministic Checkmk 2.4/2.5 MKP using only the standard library."""
import argparse
import gzip
import io
import json
from pathlib import Path
import pprint
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def package():
    family = ROOT / 'integrations/checkmk/forge_agents'
    files = {'forge_agents/' + str(p.relative_to(family)): p.read_bytes()
             for p in family.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    # One protocol source of truth; bundle private stdlib-only modules for the site.
    for module in ('core.py', 'health.py', 'telemetry.py'):
        files['forge_agents/lib/' + module] = (ROOT / 'packages/agent-core/src/forge_agent_core' / module).read_bytes()
    files['forge_agents/lib/__init__.py'] = b''
    files['forge_agents/lib/LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    manifest = dict(title='Forge AI agent health', name='forge_agents', description='Structured agent health, central policy and telemetry graphs.',
                    version='0.1.1', author='Forge', download_url='https://github.com/kudama/forge',
                    files={'cmk_addons_plugins': sorted(files)})
    manifest.update({'version.packaged': '2.5.0p14', 'version.min_required': '2.4.0', 'version.usable_until': '2.6.0'})
    return gzip.compress(archive({'info': (pprint.pformat(manifest) + '\n').encode(),
                                  'info.json': json.dumps(manifest, sort_keys=True).encode(),
                                  'cmk_addons_plugins.tar': archive(files)}), mtime=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_bytes(package())
    print(args.output)
