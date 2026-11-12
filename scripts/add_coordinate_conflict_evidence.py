"""Bổ sung ba ca có tọa độ nguồn khác nhau, chỉ từ HTML đã lưu."""
import csv
import hashlib
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ROOT
from src.parser import soup_from_html, flight_objects, parse_detail
from scripts.build_review_dossier import DEST, csv_read, json_write, safe_address, excerpts, make_case_file, no_network


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    socket.socket = no_network
    audit = csv_read(DEST/'evidence/all_297_offline_audit.csv')
    selected = [row for row in audit if any(row[key] and float(row[key])>0 for key in ['source_old_pin_distance_m','source_new_pin_distance_m'])]
    rows = csv_read(ROOT/'pilot/data/listings.csv')
    by_id = {row['tin_id']: row for row in rows}
    numbers = {row['tin_id']: number for number, row in enumerate(rows,1)}
    manifest = [json.loads(line) for line in (ROOT/'pilot/data/manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    meta_by_id = {m['tin_id']: m for m in manifest if m['kind']=='detail'}
    cases=[]
    for check in selected:
        identifier=check['tin_id']
        meta=meta_by_id[identifier]
        content=(ROOT/meta['html_path']).read_bytes()
        assert hashlib.sha256(content).hexdigest()==meta['sha256']
        soup=soup_from_html(content)
        objects=[obj for obj in flight_objects(soup) if obj.get('_id')==identifier and 'type' in obj]
        obj=max(objects,key=len)
        replay,_,_=parse_detail(content,meta)
        fields={key:obj.get(key) for key in ['pLocation','pArea','pLandArea','pGrossFloorArea','pType','pTypeLvl0','type','status',
                 'listingStatus','verificationStatus','posterVerified','sourceType','_sourceApp','_publishedAt','shortId']}
        fields['pAddress']=safe_address(obj.get('pAddress'))
        fields['newPropertyAddress']=safe_address(obj.get('newPropertyAddress'))
        fields['display_h1']=soup.find('h1').get_text()
        fields['display_address']=replay['dia_chi_goc']
        case=dict(tin_id=identifier,csv_data_row=numbers.get(identifier),user_feedback=None,
            reason_for_additional_case='Khác số giữa các tọa độ trong cùng HTML; chưa xác định trường đúng ngoài thực tế',
            capture=meta,csv_record=by_id.get(identifier),replay_record=replay,source_fields=fields,
            description_excerpts=excerpts(obj),checks=check)
        cases.append(case)
        make_case_file(case)
    assert len(cases)==3
    json_write(DEST/'evidence/additional_coordinate_conflicts_3.json',cases)
    json_write(DEST/'evidence/source_capture_manifest_additional_3.json',[meta_by_id[c['tin_id']] for c in cases])
    print('Đã bổ sung ba ca tọa độ nội bộ khác nhau, không mở mạng.')


if __name__=='__main__':
    run()
