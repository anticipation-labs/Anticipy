# Migration CLI transport regression

## Observed failure

Backend API run `34742992902` on `073e0f3a96a664a7f95a09954e37cb72ea02dd7a`
stopped before deploying. Existing erasure/command fences passed, but Wrangler
rejected the first September 11 migration's leading `-- Additive migration...`
comment as an unknown command-line argument. Its only ALTER statement was not
executed; later migration, readiness, deployment and live-fixture steps skipped.

The planner and SQLite tests had passed because neither exercised the actual
Wrangler command-line parser. An argv list avoids shell interpolation but does
not stop a CLI parser from interpreting a separate argument beginning with `--`.

## Minimal correction and verification boundary

Bind SQL as one `--command=<SQL>` argument. Preserve the complete original SQL,
including comments, whitespace and literals. Do not strip comments, invoke a
shell, change migration policy, skip readiness or manually force an ALTER.

Root reproduced split-argument failure using installed Wrangler 4.129.0 and a
harmless SELECT with isolated local D1 persistence, dotenv disabled and outbound
networking denied except loopback. The equals-bound form returned the expected
single result. This is local parser proof, not a remote migration receipt.

Required regression coverage: actual `main()` to subprocess argv; local/remote
selection unchanged; byte-preserved comment/option-looking SQL; no execution
on planning/refusal; stop on command failure; and both actual September 11
migrations applied twice to isolated local D1, with columns and trigger bodies
verified afterward. Independent review and exact-head CI precede release retry.

## Local results

- Red-first transport regression: five failures before the source correction.
- Final focused suite: **43 passed, 1 explicitly skipped separate CLI proof**.
- Independent real Wrangler 4.129.0 proof: **1 passed**, 20.05 seconds. Both
  migrations were planned, applied and reapplied against a fresh local D1;
  six added columns, four trigger bodies and relevant defaults/CHECKs verified.
- Independent source/test review found no blocking issue. The only production
  source change binds the SQL option value; migration/readiness policy is intact.

The portable argv/refusal tests run in CI. The actual Wrangler proof is a
separate macOS-only command because it confines each CLI child with
`sandbox-exec`, and macOS refuses nested sandboxes. Run it without an outer
sandbox, using the repository Python environment and installed lockfile tooling:

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ANTICIPY_WRANGLER_LOCAL_PROOF=1 \
python -m pytest -q -p no:cacheprovider \
  tests/test_d1_migration_cli_transport.py \
  -k installed_wrangler_roundtrips
```

Its children prohibit non-loopback outbound connections, writes outside the
fresh temporary directory and reads of known project environment files. This
proof is not a CI/Linux execution claim or a production migration receipt.

This document does not assert a successful production retry. Record deployment
and live identity results separately. Existing customer work must not be edited
or cleared to make a release check pass.
