import importlib.util
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
spec=importlib.util.spec_from_file_location('boot',Path(__file__).resolve().parents[1]/'scripts/foundry_boot_services.py')
boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)
class Migration(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.home=self.root/'home';self.daemons=self.root/'daemons';self.daemons.mkdir();self.backups=self.root/'backups'
  self.account=SimpleNamespace(pw_uid=501,pw_gid=20,pw_dir=str(self.home));self.sources=self.home/'Library/LaunchAgents';self.sources.mkdir(parents=True)
  self.executable=self.home/'python';self.executable.touch();self.originals={}
  for label in boot.LABELS:
   data={'Label':label,'ProgramArguments':[str(self.executable),'--existing-argument'],'KeepAlive':True,'EnvironmentVariables':{'EXISTING':'preserved'},'WorkingDirectory':str(self.home)}
   self.originals[label]=plistlib.dumps(data);(self.sources/(label+'.plist')).write_bytes(self.originals[label])
  realpath=Path
  def mapped(value):return self.daemons if str(value)=='/Library/LaunchDaemons' else self.backups if str(value)=='/Library/Application Support/FoundryServiceMigration' else realpath(value)
  self.patches=[patch.object(boot,'Path',side_effect=mapped),patch.object(boot.pwd,'getpwnam',return_value=self.account),patch.object(boot.grp,'getgrgid',return_value=SimpleNamespace(gr_name='staff'))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def test_definitions_preserve_config_and_run_as_nonroot(self):
  _,items=boot.definitions('mike')
  for label,source,destination,raw,p in items:
   self.assertEqual(p['UserName'],'mike');self.assertTrue(p['RunAtLoad']);self.assertEqual(p['EnvironmentVariables']['HOME'],str(self.home));self.assertEqual(p['EnvironmentVariables']['EXISTING'],'preserved')
   self.assertEqual(p['ProgramArguments'],plistlib.loads(raw)['ProgramArguments'])
  self.assertEqual(items[-1][-1]['EnvironmentVariables']['CURATOR_SERVICE_STARTUP'],'boot')
 def test_existing_system_service_and_root_account_are_refused(self):
  (self.daemons/(boot.LABELS[0]+'.plist')).touch()
  with self.assertRaises(ValueError):boot.definitions('mike')
  self.account.pw_uid=0
  with self.assertRaises(ValueError):boot.definitions('root')
 def test_failed_system_bootstrap_restores_all_login_definitions(self):
  def command(*args,**kw):
   if args[1:3]==('bootstrap','system'):raise RuntimeError('synthetic bootstrap failure')
   return SimpleNamespace(returncode=0,stdout='')
  with patch.object(boot,'assert_idle'),patch.object(boot,'stop'),patch.object(boot,'loaded',return_value=False),patch.object(boot,'command',side_effect=command),patch.object(boot.os,'chown'):
   with self.assertRaisesRegex(RuntimeError,'synthetic bootstrap'):boot.apply('mike')
  for label in boot.LABELS:
   self.assertEqual((self.sources/(label+'.plist')).read_bytes(),self.originals[label]);self.assertFalse((self.daemons/(label+'.plist')).exists())
 def test_keepalive_jobs_are_unloaded_without_a_signal_restart_race(self):
  for label in ('org.forge.local.controller','org.forge.local.ollama'):
   with self.subTest(label=label):
    active=True;calls=[]
    def command(*args,**kwargs):
     nonlocal active
     calls.append(args)
     if args[1]=='kill':self.fail('Signalling a KeepAlive job lets launchd respawn it')
     if args[1]=='bootout':active=False
     return SimpleNamespace(returncode=0 if active else 113,stdout='state = running' if active else '')
    with patch.object(boot,'command',side_effect=command):boot.stop('gui/501/'+label,label)
    self.assertFalse(active);self.assertEqual(sum(call[1]=='bootout' for call in calls),1)
 def test_busy_preflight_changes_no_files(self):
  with patch.object(boot,'assert_idle',side_effect=ValueError('busy')):
   with self.assertRaisesRegex(ValueError,'busy'):boot.apply('mike')
  self.assertFalse(self.backups.exists());self.assertEqual(len(list(self.sources.iterdir())),3);self.assertEqual(list(self.daemons.iterdir()),[])
if __name__=='__main__':unittest.main()
