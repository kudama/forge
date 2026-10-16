"""Integration tests require real, separately fetched Checkmk APIs, never stubs."""
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('build_mkp', ROOT/'integrations/checkmk/build_mkp.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
STAGE = tempfile.TemporaryDirectory(prefix='forge-checkmk-tests-')
stage = Path(STAGE.name)
with tarfile.open(fileobj=io.BytesIO(builder.package()), mode='r:gz') as outer:
    with tarfile.open(fileobj=io.BytesIO(outer.extractfile('cmk_addons_plugins.tar').read())) as inner:
        inner.extractall(stage/'cmk_addons/plugins', filter='data')
sys.path.insert(0, str(stage))
