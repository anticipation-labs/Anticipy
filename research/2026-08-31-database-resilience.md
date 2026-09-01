# Production database resilience — 2026-08-31

## What production actually runs

- PocketBase 0.30.4 on Railway.
- Customer collections live in SQLite at `/pb_data/data.db` on one 5 GB
  Railway volume.
- The measured customer database is about 264 MB.
- PocketBase's disposable request ledger is a separate SQLite file,
  `/pb_data/auxiliary.db`.
- Scheduled PocketBase backups currently live under `/pb_data/backups` on the
  same volume as the database they are meant to recover.

## Reproduced failure

The request ledger was 3.96 GB during the earlier full-volume outage. On
2026-08-31 it had grown to 2.77 GB again, despite a migration setting two days
of retention. At that rate a retention window does not bound the 5 GB disk.
`start.sh` deletes the ledger at boot, but a boot-time recovery cannot stop it
from filling the disk between deployments.

The prior gate stated that `settings.logs.maxDays = 0` meant unlimited
retention. PocketBase's own documentation says zero disables activity request
logging. Migration 51 corrects the setting and the executable gate. Railway
process logs and explicit hook logs remain available for diagnosis.

## Migration decision

Replacing PocketBase with Postgres is not a data copy. The iPhone, Mac,
extension, worker, hooks, migrations and realtime behavior all speak the
PocketBase API. At the present database size and owner count, an engine rewrite
adds more failure surface than it removes.

The appropriate migration now is operational:

1. Disable the disposable request-log database at its source.
2. Move scheduled backups to a separate private Cloudflare R2 bucket.
3. Encrypt PocketBase settings before storing backup S3 credentials.
4. Produce a fresh off-volume backup and prove it can be listed, downloaded,
   opened and restored into an isolated PocketBase instance.
5. Keep the Railway volume as the live low-latency database until real HA,
   compliance, or multi-instance requirements justify an engine migration.

The existing R2 bucket is not a valid destination: it contains public build
artifacts under `archive/` and `builds/`, holds roughly 12.7 GB, and has no
backup-specific lifecycle. Customer database snapshots require a new private
bucket and separate retention policy.
