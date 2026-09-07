"""Check the tracked Worker download assets against their actual source bytes."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

root=Path(__file__).resolve().parents[2]
public=root/'migration/workers/public'
names=['anticipy-extension.zip','anticipy-claude-version-extension.zip','anticipy-codex-version-extension.zip']
digests=set()
for name in names:
    path=public/name
    digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
    with ZipFile(path) as archive:
        assert 'manifest.json' in archive.namelist()
        assert 'backend_transport.js' in archive.namelist()
        for entry in archive.infolist():
            if entry.is_dir(): continue
            source=root/'extension'/entry.filename
            assert source.is_file(), f'Unknown packaged path: {entry.filename}'
            assert archive.read(entry)==source.read_bytes(), f'Stale asset: {entry.filename}'
        version=json.loads(archive.read('manifest.json'))['version']
        assert f'const ENGINE_BUILD = "{version}";' in archive.read('background.js').decode()
assert len(digests)==1,'Download aliases disagree'
print(f'Extension {version}: all three downloads match source; sha256={next(iter(digests))}')
