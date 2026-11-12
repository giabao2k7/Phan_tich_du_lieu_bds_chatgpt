"""QA và đồng bộ gói chính sau biên tập tài liệu; không ghi vào dữ liệu pilot."""
import csv
import hashlib
import json
import re
import shutil
import socket
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT
from src.parser import soup_from_html, flight_objects
from scripts.build_review_dossier import DEST, excerpts, make_case_file, no_network


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    socket.socket=no_network
    core_path=DEST/'evidence/cases_17.json'
    cases=json.loads(core_path.read_text(encoding='utf-8'))
    case=next(case for case in cases if case['tin_id']=='6ae29887faae274494541131')
    content=(ROOT/case['capture']['html_path']).read_bytes()
    assert hashlib.sha256(content).hexdigest()==case['capture']['sha256']
    soup=soup_from_html(content)
    obj=max((o for o in flight_objects(soup) if o.get('_id')==case['tin_id'] and 'type' in o),key=len)
    case['description_excerpts']=excerpts(obj)
    case['source_fields'].update({key:obj.get(key) for key in ['pNumberOfBedrooms','pNumberOfBathrooms']})
    core_path.write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    make_case_file(case)
    extras=json.loads((DEST/'evidence/additional_coordinate_conflicts_3.json').read_text(encoding='utf-8'))
    assert len(cases)==17 and len(extras)==3
    assert len({case['tin_id'] for case in cases+extras})==20
    assert sum(case['user_feedback'] is not None for case in cases)==13
    assert len(list((DEST/'evidence/cases').glob('*.md')))==20
    with (DEST/'evidence/all_297_offline_audit.csv').open(encoding='utf-8-sig',newline='') as file:
        assert len(list(csv.DictReader(file)))==297
    checks=json.loads((DEST/'evidence/preservation_check.json').read_text(encoding='utf-8'))
    for relative,expected in checks['after'].items():
        assert sha(ROOT/relative)==expected, relative
    assert sha(DEST/'snapshot/pilot/data/listings.csv')==sha(ROOT/'pilot/data/listings.csv')
    for name in ['build_review_dossier.py','package_review_dossier.py','add_coordinate_conflict_evidence.py','finalize_review_dossier.py']:
        shutil.copy2(ROOT/'scripts'/name,DEST/'snapshot/scripts'/name)
    shutil.copy2(ROOT/'NOTES.md',DEST/'snapshot/NOTES.md')
    problems=[]
    for path in DEST.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if target.startswith(('http:','https:','#')):
                continue
            target=target.split('#')[0]
            if target and not (path.parent/target).exists():
                problems.append([path.relative_to(DEST).as_posix(),target])
    assert not problems, problems
    with (DEST/'FILE_INDEX.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file)
        writer.writerow(['path','bytes','sha256'])
        for path in sorted(DEST.rglob('*')):
            if path.is_file() and path.name!='FILE_INDEX.csv':
                writer.writerow([path.relative_to(DEST).as_posix(),path.stat().st_size,sha(path)])
    primary=DEST.parent/'HO_SO_DANH_GIA_MOSO.zip'
    with zipfile.ZipFile(primary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DEST.rglob('*')):
            if path.is_file():
                archive.write(path,(Path(DEST.name)/path.relative_to(DEST)).as_posix())
    with zipfile.ZipFile(primary) as archive:
        assert archive.testzip() is None
        for path in DEST.rglob('*'):
            if path.is_file():
                assert archive.read((Path(DEST.name)/path.relative_to(DEST)).as_posix())==path.read_bytes()
        file_count=len(archive.namelist())
    package_path=DEST.parent/'PACKAGE_SHA256.json'
    packages=json.loads(package_path.read_text(encoding='utf-8'))
    packages['packages'][0].update(bytes=primary.stat().st_size,sha256=sha(primary),files=file_count)
    packages['final_document_qa']='20 ca; đủ 13 phản hồi; 297 audit; link nội bộ hợp lệ; ZIP khớp từng byte với tài liệu; dữ liệu và code pilot giữ nguyên'
    for package in packages['packages']:
        path=DEST.parent/package['file']
        assert sha(path)==package['sha256']
    package_path.write_text(json.dumps(packages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(packages,ensure_ascii=False,indent=2))


if __name__=='__main__':
    run()
