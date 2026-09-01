# Production database resilience — 2026-08-31

## What production actually runs

- PocketBase 0.30.4 on Railway.
- Customer collections live in SQLite at `/pb_data/data.db` on one 5 GB
  Railway volume.
- The measured customer database is about 264 MB.
- PocketBase's disposable request ledger is a separate SQLite file,
  `/pb_data/auxiliary.db`.
- PocketBase is configured to write scheduled backups to a private R2 bucket;
  the Railway volume keeps only the newest local pre-migration archive.
- The brain worker has a second Railway volume. It contains the founder's
  legacy memory database plus nine owner state directories; a PocketBase-only
  recovery would therefore lose durable assistant memory.

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

The private bucket `anticipy-pocketbase-backups-production` was created and
verified with public access disabled, server-side AES-256 encryption, and a
one-day abort rule for incomplete multipart uploads. The production account
token `anticipy-production-database-backups` has Object Read & Write access to
that bucket only and a non-expiring production lifetime. A live scope probe
could read/write/delete its own object in the backup bucket while Cloudflare
denied the same credential access to `anticipy-downloads`. The broad
build-artifact credential was not installed on the backend or worker.

## Recovery boundary

An operationally complete generation has two parts:

1. PocketBase's native archive of `/pb_data`, written directly to the private
   R2 bucket and retained for fourteen generations.
2. A worker-state archive created with SQLite's online backup API, checked
   with `PRAGMA quick_check`, accompanied by per-file SHA-256 hashes, uploaded
   with server-side encryption, and retained for fourteen generations.

The worker uploader fails loudly on absent or partial production configuration
and on symlinks, invalid JSON, failed SQLite checks, wrong uploaded size, or
missing digest metadata.

## Restore proof and bootstrap copy

The newest Railway PocketBase archive was downloaded and tested before it was
called a backup. The ZIP CRC passed, `data.db` passed `PRAGMA quick_check`, and
the restored database contained 9 owners, 8 owner profiles, 1,649 events, 196
jobs, and 446 agent rows. Its 144,812,113-byte archive was uploaded under the
`pocketbase/bootstrap/` prefix, downloaded again, and matched SHA-256
`9371476cba8f7b44ade02429538903e206c457f489253c33410ba2a7a28ababd`.

The worker volume's 18 durable SQLite/JSON files, spanning all nine owner
directories and the legacy root databases, were snapshotted through the new
backup path and uploaded under `worker/bootstrap/`. The downloaded archive's
CRC, all 18 file lengths, and all 18 manifest SHA-256 hashes passed.

## Production proof

- Backend deployment `3a80fc9a-a063-4589-957e-696c0b9bbefe` succeeded.
  Migration 53 is present in the live `_migrations` table, the settings row is
  encrypted rather than JSON plaintext, `/api/health` returns 200, and the
  request ledger was 4 KB after restart.
- Worker deployment `48c75e12-d103-4024-a86e-b8d722e77060` succeeded and wrote
  `worker/state-20260901T035746Z.zip` from the production volume. A separate
  download verified the ZIP CRC and every length and SHA-256 for all 18 files.
- The exact PocketBase 0.30.4 native backup engine was run against the final
  restricted R2 configuration. It created an R2 archive that was independently
  downloaded, CRC-tested, extracted, and passed `PRAGMA quick_check`; the
  disposable verification object was then removed. Production PocketBase now
  runs its daily schedule at 09:00 UTC with fourteen generations retained.
- The implementation is commit `50378915`. The full Python suite passed 2,337
  tests and the extension runner passed all 68 suites before deployment.
