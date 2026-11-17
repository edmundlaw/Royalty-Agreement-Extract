"""Verify the SHA-256 release file inventory (standard library only)."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
data=json.loads((root/'RELEASE_SHA256.json').read_text(encoding='utf-8'))
fail=[]
checksums=data.get('checksums')
if data.get('release')!='v0.13.5' or not isinstance(checksums,dict):
    fail.append('release manifest schema/version mismatch')
    checksums={}
for rel,digest in checksums.items():
    file=root/rel
    if not file.is_file() or file.is_symlink():fail.append('missing/unreadable: '+rel);continue
    if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:fail.append('changed: '+rel)
actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
        and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and '.git' not in p.parts
        and '.egg-info' not in str(p) and p.name!='.DS_Store'}
expected=set(checksums)|{'RELEASE_SHA256.json'}
for rel in sorted(actual-expected):fail.append('unmanifested: '+rel)
for rel in sorted(expected-actual):fail.append('missing: '+rel)
if data.get('file_count')!=len(checksums):fail.append('count mismatch')
print(json.dumps({'release':data.get('release'),'files_checked':len(checksums),
                  'errors':fail,'status':'PASS' if not fail else 'FAIL'}))
sys.exit(bool(fail))
