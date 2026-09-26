"""Transactional, checksummed replicate storage with a completion journal.

SQLite transactions commit a result and its journal entry together. Checksums
detect accidental alteration; they are not an authentication/signature scheme.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib


class IntegrityError(ValueError):
    """Saved evidence is incomplete, inconsistent or incompatible."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, ensure_ascii=True).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ReplicateStore:
    """One database per frozen run. Never silently initializes an existing file."""

    def __init__(self, path, manifest, *, create=False):
        self.path = Path(path)
        self.manifest = manifest
        self.manifest_bytes = canonical(manifest)
        self.manifest_hash = digest(self.manifest_bytes)
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents accidental replacement of a prior run.
            with self.path.open('xb'):
                pass
        elif not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.db = sqlite3.connect(self.path, timeout=0, isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        if create:
            with self.transaction():
                self.db.execute('CREATE TABLE manifest (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL, sha256 TEXT NOT NULL)')
                self.db.execute('CREATE TABLE records (cell TEXT NOT NULL, replicate INTEGER NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(cell, replicate))')
                self.db.execute('CREATE TABLE events (sequence INTEGER PRIMARY KEY, time_utc TEXT NOT NULL, kind TEXT NOT NULL, cell TEXT, replicate INTEGER, sha256 TEXT)')
                self.db.execute('INSERT INTO manifest VALUES (1, ?, ?)',
                                (self.manifest_bytes, self.manifest_hash))
                self.event('created')
        try:
            self.verify()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def transaction(self, *, write=True):
        self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def event(self, kind, cell=None, replicate=None, sha256=None):
        if not self.db.in_transaction:
            raise RuntimeError('Journal writes require a transaction')
        self.db.execute('INSERT INTO events(time_utc,kind,cell,replicate,sha256) VALUES (?,?,?,?,?)',
                        (utc_now(), kind, cell, replicate, sha256))

    def contains(self, cell, replicate):
        return self.db.execute('SELECT 1 FROM records WHERE cell=? AND replicate=?',
                               (cell, replicate)).fetchone() is not None

    def put(self, cell, replicate, result):
        if not self.db.in_transaction:
            raise RuntimeError('Record writes require a transaction')
        self._check_key(cell, replicate)
        if result.get('cell') != cell or result.get('replicate') != replicate:
            raise IntegrityError('Payload identity differs from record key')
        raw = canonical(result)
        checksum = digest(raw)
        self.db.execute('INSERT INTO records VALUES (?,?,?,?)',
                        (cell, replicate, zlib.compress(raw), checksum))
        self.event('record_committed', cell, replicate, checksum)

    def _check_key(self, cell, replicate):
        sizes = {item['name']: item['requested'] for item in self.manifest['plan']['cells']}
        if cell not in sizes or type(replicate) is not int or not 0 <= replicate < sizes[cell]:
            raise IntegrityError('Record outside frozen cell/replicate design')

    def iter_records(self):
        for cell, replicate, packed, checksum in self.db.execute(
                'SELECT cell,replicate,payload,sha256 FROM records ORDER BY cell,replicate'):
            self._check_key(cell, replicate)
            try:
                raw = zlib.decompress(packed)
                value = json.loads(raw)
            except (zlib.error, ValueError, TypeError) as error:
                raise IntegrityError('Unreadable record payload') from error
            if digest(raw) != checksum or canonical(value) != raw:
                raise IntegrityError('Record checksum or canonical encoding mismatch')
            if value.get('cell') != cell or value.get('replicate') != replicate:
                raise IntegrityError('Payload identity differs from record key')
            yield value

    def verify(self):
        """Streaming full scan; deleted completed records cannot become new work."""
        with self.transaction(write=False):
            if self.db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise IntegrityError('SQLite integrity check failed')
            rows = self.db.execute('SELECT payload,sha256 FROM manifest').fetchall()
            if rows != [(self.manifest_bytes, self.manifest_hash)]:
                raise IntegrityError('Run manifest differs from requested code/environment/design')
            bad = self.db.execute('''
                SELECT 1 FROM records r LEFT JOIN events e
                ON e.kind='record_committed' AND e.cell=r.cell AND e.replicate=r.replicate
                GROUP BY r.cell,r.replicate,r.sha256
                HAVING COUNT(e.sequence)!=1 OR MIN(e.sha256) IS NOT r.sha256 LIMIT 1
            ''').fetchone()
            orphan = self.db.execute('''
                SELECT 1 FROM events e LEFT JOIN records r
                ON e.cell=r.cell AND e.replicate=r.replicate
                WHERE e.kind='record_committed' AND r.cell IS NULL LIMIT 1
            ''').fetchone()
            if bad or orphan:
                raise IntegrityError('Completion journal and stored records disagree')
            return sum(1 for _ in self.iter_records())

    def backup(self, destination):
        """Create a new verified snapshot; never overwrite an older checkpoint."""
        destination = Path(destination)
        with destination.open('xb'):
            pass
        with sqlite3.connect(destination) as copied:
            self.db.backup(copied)
        with ReplicateStore(destination, self.manifest) as copied:
            count = copied.verify()
        return {'records': count, 'sha256': digest(destination.read_bytes())}


def read_manifest(path):
    """Read a saved manifest without creating a missing database."""
    path = Path(path).resolve()
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT payload,sha256 FROM manifest WHERE id=1').fetchone()
        if row is None or digest(row[0]) != row[1]:
            raise IntegrityError('Manifest checksum mismatch')
        value = json.loads(row[0])
        if canonical(value) != row[0]:
            raise IntegrityError('Noncanonical manifest')
        return value
