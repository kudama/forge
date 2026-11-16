# Foundry boot services

Requested 2026-11-15; tracked in issue #72. This host-specific migration moves the existing Ollama, Forge controller and Curator LaunchAgents to system LaunchDaemons. Services continue to run as the existing non-root account, with explicit HOME/USER/LOGNAME and unchanged executables, state, ports, environment and credentials. Curator reports boot startup when its managed service receives CURATOR_SERVICE_STARTUP=boot.

Run `python3 scripts/foundry_boot_services.py` for a read-only plan. Once reviewed, run `sudo /usr/bin/python3 scripts/foundry_boot_services.py --apply` on Foundry. The script requires idle Curator and no unfinished Forge jobs, stops login services before installing boot services, removes the original login definitions only after saving them, checks Curator/Forge/Ollama readiness, and automatically restores login services if installation fails. It does not reboot or start any processing queue.

Private rollback definitions are retained under `/Library/Application Support/FoundryServiceMigration/<timestamp>`. Use `sudo /usr/bin/python3 scripts/foundry_boot_services.py --rollback "<backup-directory>"` while the original user's GUI session exists. Changed definitions are preserved for inspection rather than overwritten. Do not reinstall the old login services while boot services are active. Existing Forge `mac_services.py` start/stop/status commands address the GUI domain; use `sudo launchctl print system/<label>` for these boot services.

FileVault is enabled on Foundry. Boot services run after macOS can access its startup disk; this does not bypass disk unlock. Preserve encryption. Apple silicon with macOS 26+ supports Remote Login disk unlock under Apple's documented prerequisites. Do not equate that with unattended cold-boot acceptance.

The Plex share currently uses the existing user/Finder mapping method; mounting before login has not been established. Keychain-backed GitHub credentials may also require unlock. This migration does not change mounts or move credentials into plaintext. Validate both separately.

Evidence on 2026-11-15: all three existing services running as login agents; clean idle migration plan on Foundry; four isolated migration tests cover preserved non-root configuration, existing-system-service/root-account refusal, busy preflight with no changes, and restoration after a synthetic bootstrap failure. Administrator installation and actual reboot acceptance remain pending.

## Corrected KeepAlive stop handling — 2026-11-15

The initial administrator attempt rolled back before installing system jobs: the controller received SIGTERM, then launchd immediately restarted its KeepAlive job. Waiting for a persistent stopped state timed out. All original login services and 4,303 visible Curator tasks were verified healthy afterward. The installer now unloads KeepAlive jobs with bootout, preventing respawn while launchd handles shutdown. Curator retains its successful SIGINT exit before unloading.

Five focused tests pass, including a regression for the restart race. The corrected sequence was also exercised on idle Foundry: all three jobs unloaded without respawn, then their unchanged login definitions were restored; authenticated Forge readiness, Ollama readiness and all 4,303 unchanged Curator records were verified. This validates the corrected stop/restore sequence, not system installation or reboot acceptance. A new staged installer version requires a fresh administrator invocation.
