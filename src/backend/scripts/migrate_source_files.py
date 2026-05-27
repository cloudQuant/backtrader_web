"""Migrate source files from MongoDB to local disk and update KB documents."""
import json
import sqlite3
import sys
from pathlib import Path

import pymongo

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

SOURCE_FILE_DIR = BACKEND_ROOT / 'data' / 'reqdocs_source_files'
SOURCE_FILE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = REPO_ROOT / 'data' / 'dev' / 'backtrader.db'
MONGODB_URL = 'mongodb://localhost:27017/'
MONGODB_DB = 'document_management'


def get_connection():
    return sqlite3.connect(DB_PATH, timeout=60)


def update_document_metadata(conn, doc_uuid: str, metadata: dict) -> None:
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE kb_documents SET metadata = ? WHERE id = ?',
        (json.dumps(metadata), doc_uuid)
    )
    conn.commit()


def migrate_source_files(dry_run: bool = True):
    print(f"{'[DRY RUN] ' if dry_run else ''}Starting source file migration...")
    print(f"Source file dir: {SOURCE_FILE_DIR}")

    mongo = pymongo.MongoClient(MONGODB_URL, serverSelectionTimeoutMS=10000)
    db = mongo[MONGODB_DB]

    conn = get_connection()

    print("Finding documents needing source files...")
    cursor = conn.execute('''
        SELECT id, title, metadata
        FROM kb_documents
        WHERE metadata IS NOT NULL AND metadata != ''
    ''')

    docs_needing_migration = []
    for row in cursor.fetchall():
        doc_uuid, title, metadata_json = row
        try:
            metadata = json.loads(metadata_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if not metadata.get('reqdocs_document_id'):
            continue
        if metadata.get('reqdocs_source_file_path'):
            continue

        docs_needing_migration.append((doc_uuid, metadata))

    print(f"Documents needing migration: {len(docs_needing_migration)}")

    migrated = 0
    errors = 0
    skipped_no_match = 0

    for doc_uuid, metadata in docs_needing_migration:
        try:
            reqdocs_id = int(metadata['reqdocs_document_id'])

            mongo_doc = db.source_files.find_one(
                {'document_id': reqdocs_id},
                {
                    'filename': 1,
                    'mime_type': 1,
                    'file_size': 1,
                    'storage_type': 1,
                    'gridfs_id': 1,
                    'data': 1,
                }
            )

            if not mongo_doc:
                skipped_no_match += 1
                continue

            filename = mongo_doc.get('filename')
            file_data = mongo_doc.get('data')
            if not filename or not file_data:
                skipped_no_match += 1
                continue

            safe_name = Path(filename).name
            target_path = SOURCE_FILE_DIR / f'{reqdocs_id}_{safe_name}'

            if not dry_run:
                target_path.write_bytes(file_data)

            new_metadata = dict(metadata)
            new_metadata.update({
                'reqdocs_source_filename': filename,
                'reqdocs_source_mime_type': mongo_doc.get('mime_type') or 'application/octet-stream',
                'reqdocs_source_file_size': mongo_doc.get('file_size'),
                'reqdocs_source_storage_type': mongo_doc.get('storage_type'),
                'reqdocs_source_file_path': str(target_path),
            })

            if not dry_run:
                update_document_metadata(conn, doc_uuid, new_metadata)

            migrated += 1
            if migrated % 50 == 0:
                print(f"  Migrated {migrated}...")

        except Exception as e:
            errors += 1
            print(f"  [ERROR] doc {doc_uuid}: {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  No MongoDB match: {skipped_no_match}")
    print(f"  Errors: {errors}")

    conn.close()
    mongo.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate_source_files(dry_run=dry_run)
