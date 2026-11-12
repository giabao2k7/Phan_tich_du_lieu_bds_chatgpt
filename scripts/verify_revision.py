"""Hai lượt replay offline trên venv được chỉ định; không ghi vào pilot."""
import argparse
import hashlib
import io
import json
import platform
import socket
import sys
import unittest
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT
from src.pipeline import parse_saved
from src.revision_reports import json_file


def hashes(paths):
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def verify(base):
    base = base.resolve()
    lock = json.loads((base/'input_hashes.json').read_text(encoding='utf-8'))
    protected = {k:v for k,v in lock.items() if k.startswith('pilot/') or k.endswith('.zip')}
    before = hashes(ROOT/key for key in protected)
    assert before == protected, 'Nguồn đã thay đổi so với khóa trước sửa'
    code_paths = [*ROOT.joinpath('src').glob('*.py'), *ROOT.joinpath('tests').glob('*.py'),
                  ROOT/'main.py', ROOT/'scripts/verify_revision.py',ROOT/'requirements.txt']
    code_before = hashes(code_paths)
    with patch.object(socket,'socket',side_effect=AssertionError('Socket forbidden during offline verification')):
        rows, excluded, errors = parse_saved(ROOT/'pilot/data/raw_html',base/'data/listings.csv')
        first = {p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['data','reports','outputs'] for p in (base/folder).rglob('*') if p.is_file() and p.name not in ['verification.json','tests.log','manual_review.md']}
        replay = base/'_replay'
        parse_saved(ROOT/'pilot/data/raw_html',replay/'data/listings.csv')
    second = {p.relative_to(replay).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['data','reports','outputs'] for p in (replay/folder).rglob('*') if p.is_file()}
    assert first == second, 'Hai lượt đầu ra khác byte: ' + str(sorted(k for k in first.keys()|second.keys() if first.get(k)!=second.get(k)))
    assert not errors
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (base/'reports/tests.log').write_text(stream.getvalue(),encoding='utf-8')
    assert result.wasSuccessful(),stream.getvalue()
    after = hashes(ROOT/key for key in protected)
    assert after == before, 'Nguồn bị thay đổi trong replay'
    assert code_before == hashes(code_paths), 'Code thay đổi giữa lúc kiểm chứng'
    json_file(base/'code_hashes.json',code_before)
    checks = json.loads((base/'reports/checks.json').read_text(encoding='utf-8'))
    proof = dict(python=sys.version,executable=sys.executable,platform=platform.platform(),
                 environment='venv mới .verification/offline_v2_env; ensurepip thất bại; bootstrap bằng pip --python từ venv hiện có, cài --no-index từ .runtime/wheels',
                 packages={name:version(name)for name in ['requests','beautifulsoup4','lxml','pandas','matplotlib']},
                 socket_blocked=True,full_executed=False,new_requests=0,protected_files=len(protected),source_hashes_preserved=after==before,
                 source_before=before,source_after=after,code_hashes_file='code_hashes.json',
                 replay_byte_identical=True,replay_files=len(first),output_hashes=first,
                 tests_run=result.testsRun,tests_passed=result.wasSuccessful(),errors=len(errors),csv_rows=len(rows),separated=len(excluded),
                 checks_conserved=checks['conserved_total'],visual_review='pending')
    json_file(base/'reports/verification.json',proof)
    print(json.dumps({k:proof[k] for k in ['tests_run','tests_passed','protected_files','source_hashes_preserved','replay_byte_identical','replay_files','csv_rows','separated','errors','new_requests']},indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'revisions/2026-11-02_offline_v2')
    verify(parser.parse_args().output)
