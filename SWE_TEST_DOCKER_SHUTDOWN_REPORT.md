# Local SWE test Docker shutdown

The user requested all test SWE Docker projects be turned off. The following four local Compose projects are stopped:

- `swe-eval`
- `swe-p27-local`
- `swe-main-p27-acceptance`
- `swe-api-retry-acceptance`

All 11 containers were stopped, with API admission stopped before workers and stubs. Every inspected evaluation queue was empty and no evaluation was active. Workers exited cleanly; no SWE candidate sandbox remains running. Containers, images, named volumes, database contents, credentials and forensic evidence were retained. Five gpt-auto/sub2api containers remained running with unchanged identities, start times and restart counts.

The local WebUI addresses in earlier deployment reports describe verified deployments; those consoles are currently offline following this explicit shutdown. No Docker project was removed, no volume was deleted, and no prune command was used.

Supporting evidence is retained privately under `data/swe-test-shutdown-20261022T165623Z/`, including before.json, queue-observations.json, stop-results.json and result.json. The ignored pointer `data/swe-test-shutdown-current.txt` identifies that directory.

To resume a chosen deployment, explicitly start only its intended project using its retained Compose wrapper/configuration and persistent volume. The Phase 2.7 operator procedure is in [PHASE27_LOCAL_OPERATIONS.md](PHASE27_LOCAL_OPERATIONS.md). Do not start all historical test projects automatically.
