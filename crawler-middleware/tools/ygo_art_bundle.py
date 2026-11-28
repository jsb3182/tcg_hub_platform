"""Prepare an owner's YGOResources Git mirror on a PC and import its verified files on a server."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile

from tcg_worker import local_art
from tcg_worker.jobs import connect
from tcg_worker.media import LIMIT_BYTES, publish


REPOS = ('artworks-ko-db', 'artworks-en-n', 'artworks-jp-n')
SOURCES = {'artworks-ko-db':'ko_path', 'artworks-en-n':'en_path', 'artworks-jp-n':'ja_path'}
IMAGE_PATH = re.compile(r'[0-9]+/[0-9]+/[0-9]+_[0-9]+\.png')
DIGEST = re.compile(r'[a-f0-9]{64}')


def encode(path, data):
    image = local_art.webp(data)
    return {
        'path': path, 'original': hashlib.sha256(data).hexdigest(),
        'encoded': hashlib.sha256(image).hexdigest(), 'fingerprint':local_art.capture_hash(image),
    }, image


def prepare(repo, mirror, destination):
    host = repo + '.ygoresources.com'
    git = ['git', '-C', str(mirror.resolve())]
    def read(*args):
        return subprocess.check_output(git + list(args)).decode('ascii').strip()
    remote = read('remote','get-url','origin').removesuffix('.git').removesuffix('/')
    revision = read('rev-parse','HEAD')
    if (remote != 'https://github.com/yugioh-artworks/' + repo
            or not re.fullmatch(r'[a-f0-9]{40}', revision) or read('show',revision+':CNAME') != host):
        raise ValueError('Unexpected upstream Git repository or CNAME')
    manifest = {'repo':repo,'revision':revision,'images':[],'emptyPlaceholders':0}
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.NamedTemporaryFile(dir=destination.parent,delete=False,suffix='.tmp') as f:
        tmp = Path(f.name)
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED) as package, ThreadPoolExecutor(max_workers=4) as pool:
            queue = deque()
            def write_one():
                entry, data = queue.popleft().result()
                package.writestr(entry['path']+'.webp', data)
                manifest['images'].append(entry)
            proc = subprocess.Popen(git+['archive','--format=tar',revision], stdout=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=proc.stdout,mode='r|') as tree:
                    for file in tree:
                        tree.members.clear()
                        if not file.isfile() or not IMAGE_PATH.fullmatch(file.name):
                            continue
                        if file.size==0:
                            manifest['emptyPlaceholders']+=1
                            continue
                        if file.size > LIMIT_BYTES:
                            raise ValueError('Unexpected upstream image size')
                        queue.append(pool.submit(encode,file.name,tree.extractfile(file).read()))
                        if len(queue)>=12:
                            write_one()
                if proc.wait():
                    raise ValueError('Could not read complete Git archive')
            finally:
                proc.stdout.close()
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
            while queue:
                write_one()
            if not manifest['images']:
                raise ValueError('No supported images in upstream archive')
            package.writestr('manifest.json',json.dumps(manifest,separators=(',',':')).encode())
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)
    print(json.dumps({'repo':repo,'revision':revision,'files':len(manifest['images'])}),flush=True)


def read_manifest(package):
    info=package.getinfo('manifest.json')
    if info.file_size>30_000_000 or len(package.infolist())>80000:
        raise ValueError('Unexpected bundle size')
    manifest=json.loads(package.read(info))
    if manifest['repo'] not in REPOS or not re.fullmatch('[a-f0-9]{40}',manifest['revision']):
        raise ValueError('Invalid source identity')
    seen=set()
    for row in manifest['images']:
        path=row['path']
        if (not IMAGE_PATH.fullmatch(path) or path in seen or not DIGEST.fullmatch(row['encoded'])
                or not DIGEST.fullmatch(row['original']) or not re.fullmatch('[01]{64}',row['fingerprint'])):
            raise ValueError('Invalid entry in artwork manifest')
        seen.add(path)
    if not seen or len(seen)+1!=len(package.infolist()):
        raise ValueError('Incomplete image bundle')
    return manifest


def import_page(db, media, package, repo, entries):
    origin='https://'+repo+'.ygoresources.com/'
    by_url={origin+e['path']:e for e in entries}
    with db.transaction():
        if not db.execute('SELECT pg_try_advisory_xact_lock(%s)',(local_art.LOCK,)).fetchone()[0]:
            return None
        enabled=db.execute("""SELECT EXISTS (SELECT FROM collection_control WHERE crawler_enabled AND scheduler_enabled)
            AND EXISTS (SELECT FROM feed_source WHERE source_key='YUGIOH' AND provider='CATALOG' AND enabled AND policy_note IS NULL)""").fetchone()[0]
        if not enabled:
            raise RuntimeError('Operator paused catalog collection')
        if shutil.disk_usage(media).free < 768*1024*1024 + len(entries)*LIMIT_BYTES:
            raise RuntimeError('Insufficient media storage')
        # The database must independently grant this exact regional image to a public card.
        # The bundle supplies pixels, never card IDs or new card-to-picture assignments.
        sql="""SELECT f.id,f.source_url FROM catalog_art_file f WHERE f.game_code='YUGIOH' AND f.storage_key IS NULL
            AND f.source_url=ANY(%s) AND EXISTS (
              SELECT FROM catalog_art_card a JOIN card c ON c.id=a.card_id AND c.status='PUBLISHED' AND c.game_code='YUGIOH'
              LEFT JOIN legacy_card_edition e ON e.card_id=c.id AND e.matched_name=c.original_name AND e.matched_number=c.number
              JOIN yugioh_reference_art y ON y.cid=coalesce(nullif(c.specs->>'konami_id',''),e.konami_id::text)
              WHERE a.file_id=f.id AND f.source_url=%s||y."""+SOURCES[repo]+') FOR UPDATE OF f'
        granted=db.execute(sql,(list(by_url),origin.rstrip('/'))).fetchall()
        updates=[]
        for fid,url in granted:
            entry=by_url[url]
            info=package.getinfo(entry['path']+'.webp')
            if not 0<info.file_size<=LIMIT_BYTES:
                raise ValueError('Invalid WebP size')
            data=package.read(info)
            if hashlib.sha256(data).hexdigest()!=entry['encoded'] or local_art.capture_hash(data)!=entry['fingerprint']:
                raise ValueError('WebP verification failed')
            updates.append((publish(media,'cards',data),entry['original'],entry['fingerprint'],fid))
        with db.cursor() as cur:
            cur.executemany("""UPDATE catalog_art_file SET storage_key=%s,source_sha256=%s,capture_hash=%s::bit(64),
                checked_at=now(),next_attempt=now()+interval '90 days',failures=0,last_error=NULL WHERE id=%s""",updates)
    return len(granted)


def load_bundle(bundle,digest):
    media=Path(os.getenv('MEDIA_ROOT','/var/lib/tcg-hub/media'))
    with bundle.open('rb') as f:
        if not DIGEST.fullmatch(digest) or hashlib.file_digest(f,'sha256').hexdigest()!=digest:
            raise ValueError('Bundle SHA-256 differs from prepared file')
        f.seek(0)
        with zipfile.ZipFile(f) as package, connect() as db:
            db.autocommit=True
            manifest=read_manifest(package)
            entries=manifest['images']
            saved=0
            for offset in range(0,len(entries),48):
                count=import_page(db,media,package,manifest['repo'],entries[offset:offset+48])
                while count is None:
                    time.sleep(1)
                    count=import_page(db,media,package,manifest['repo'],entries[offset:offset+48])
                saved+=count
                if offset%960==0:
                    print(json.dumps({'examined':offset+len(entries[offset:offset+48]),'saved':saved}),flush=True)
                time.sleep(.04)
    print(json.dumps({'complete':True,'repo':manifest['repo'],'revision':manifest['revision'],'examined':len(entries),'saved':saved}),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cmd=cli.add_subparsers(dest='action',required=True)
    build=cmd.add_parser('prepare')
    build.add_argument('repo',choices=REPOS)
    build.add_argument('mirror',type=Path)
    build.add_argument('bundle',type=Path)
    load=cmd.add_parser('load')
    load.add_argument('bundle',type=Path)
    load.add_argument('sha256')
    args=cli.parse_args()
    if args.action=='prepare':
        prepare(args.repo,args.mirror,args.bundle)
    else:
        load_bundle(args.bundle,args.sha256)
