"""Dựng hồ sơ đối chứng từ evidence đã lưu; hoàn toàn offline, không đổi nguồn."""
import csv
import hashlib
import io
import json
import socket
import sys
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.location_review import VERSION, embed_reference, osm_reference, evaluate_case
from src.observations import haversine

BASE=ROOT/'revisions/2026-11-02_location_review_v1'
PREVIOUS=ROOT/'revisions/2026-11-02_offline_v2'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def lines(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in data),encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_protected(locked):
    def check(item):
        key,expected=item
        return key,digest(ROOT/key)==expected
    matches=[]
    with ThreadPoolExecutor(max_workers=8)as pool:
        for index,(key,ok)in enumerate(pool.map(check,locked.items()),1):
            if not ok:raise AssertionError('Nguồn thay đổi: '+key)
            matches.append(ok)
            if index%100==0:print(f'Kiểm bảo toàn: {index}/{len(locked)} tệp.',flush=True)
    return len(matches)==len(locked)and all(matches)


def build(check_inputs=True):
    locked=read(BASE/'input_hashes.json')
    if check_inputs:assert verify_protected(locked),'Nguồn hoặc bản v2 đã thay đổi'
    reviewed=read(BASE/'review_inputs.json')
    sources={p.stem:read(p)for p in(BASE/'evidence').glob('*.json')}
    web=read(BASE/'web_observations.json')
    sources.update({s['source_id']:s for s in web})
    records={e['tin_id']:e for line in(PREVIOUS/'reports/field_evidence.jsonl').read_text(encoding='utf-8').splitlines()if(e:=json.loads(line))}
    with(ROOT/'handoff/2026-11-02_review/evidence/user_feedback.csv').open(encoding='utf-8-sig',newline='')as handle:
        feedback={r['tin_id']:r for r in csv.DictReader(handle)if r['field']=='Tọa độ'}
    targets=set(feedback)|{tid for tid,e in records.items()if e['coordinate_comparisons']}
    assert targets==set(reviewed['cases']),'Phải bao phủ chín phản hồi và ba ca pin nội bộ'
    references={}
    for key,spec in reviewed['references'].items():
        source=sources[spec['evidence_id']]
        references[key]=osm_reference(source)if spec['kind']=='osm_polygon'else embed_reference(source,spec['entity_name'],spec['level'])
    result=[]
    for tid,review in reviewed['cases'].items():
        assert set(review['source_ids'])<=set(sources),tid+' thiếu nguồn'
        case=evaluate_case(records[tid],review,references.get(review.get('reference_key')))
        case['internal_coordinate_comparisons']=records[tid]['coordinate_comparisons']
        case['user_feedback']=feedback.get(tid)
        case['source_address']=records[tid]['compatibility_row']['dia_chi_goc']
        result.append(case)
    lines(BASE/'data/location_decisions.jsonl',result)
    save(BASE/'data/reference_points.json',references)
    all_status=[]
    by_id={c['tin_id']:c for c in result}
    for tid,e in records.items():
        case=by_id.get(tid)
        all_status.append(dict(e['snapshot'],external_review_status=case['external_review_status']if case else'not_reviewed_externally',
                              reference_available=bool(case and case['reference']),verified_property_coordinates=None,
                              exact_spatial_analysis_eligible=False,
                              nonspatial_eligibility='unchanged_from_v2; district_is_source_label_not_verified_boundary'))
    lines(BASE/'data/location_status_all297.jsonl',all_status)
    flat=[]
    for c in result:
        ref=c['reference']or{}
        pair=ref.get('coordinates',['',''])
        flat.append(dict(tin_id=c['tin_id'],capture_at=c['capture_at'],html_sha256=c['html_sha256'],
                         source_lng=c['source_coordinates'][0],source_lat=c['source_coordinates'][1],
                         reference_lng=pair[0],reference_lat=pair[1],reference_level=ref.get('level',''),
                         reference_entity=ref.get('entity_name',''),reference_source=ref.get('source_id',''),
                         distance_to_reference_m=c['distance_to_reference_m'],reported_distance_m=(c['user_feedback']or{}).get('reported_distance_m',''),
                         review_status=c['external_review_status'],verified_property_lng='',verified_property_lat='',
                         exact_spatial_analysis_eligible=False,unresolved=c['unresolved']))
    out=BASE/'data/coordinate_references.csv'
    with out.open('w',encoding='utf-8-sig',newline='')as handle:
        writer=csv.DictWriter(handle,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    # Ghi các ứng viên bị từ chối/không được chọn; không lẫn tâm viewport với marker.
    rejected=[dict(source_id='google_2g',reason='geocoder_returned_Dinh_Bo_Linh_2G_35_not_2G; reject_entity_mismatch',candidate_pairs=sources['google_2g']['candidate_pairs']),
              dict(source_id='mogi_thinhvuong',reason='multiple_geo_objects_and_project_point_disagrees_with_developer; no_automatic_selection',candidates=sources['mogi_thinhvuong']['coordinate_candidates']),
              dict(source_id='maison_2g',reason='multiple_iframes_include_broker_offices; no_property_pin_selected',map_links=sources['maison_2g']['map_links']),
              dict(source_id='cbre_park',reason='iframe_viewport_center_is_not_the_named_place_marker; viewport_not_selected'),
              dict(source_id='intresco_project',reason='company_headquarters_iframe_is_not_project_iframe; headquarters_not_selected'),
              dict(source_id='rever_park',reason='competing_project_reference_not_averaged_or_promoted',candidates=sources['rever_park']['coordinate_candidates'])]
    save(BASE/'reports/rejected_or_competing_candidates.json',rejected)
    competing=sources['rever_park']['coordinate_candidates']
    geo=next(x['value']for x in competing if x['key']=='schema_geo')
    secondary=[float(geo['longitude']),float(geo['latitude'])]
    save(BASE/'reports/reference_disagreements.json',dict(park_cbre=references['park']['coordinates'],park_rever=secondary,
                                                       difference_m=haversine(references['park']['coordinates'],secondary),
                                                       decision='retain_both_no_ground_truth; CBRE_marker_used_only_as_named_reference'))
    # Mỗi nguồn được dùng có locator và cấp truy cập; không xuất PDF có thông tin cá nhân.
    used_ids=sorted({s for c in reviewed['cases'].values()for s in c['source_ids']}|{r['source_id']for r in references.values()})
    lines(BASE/'reports/source_register.jsonl',[dict(source_id=s,**{k:v for k,v in sources[s].items()if k!='source_id'})for s in used_ids])
    counts=Counter(c['external_review_status']for c in result)
    summary=dict(targets=len(targets),feedback_cases=len(feedback),additional_internal_cases=len(targets-set(feedback)),
                 reviewed=len(result),with_reference=sum(c['reference']is not None for c in result),
                 no_accepted_reference=sum(c['reference']is None for c in result),verified_property_pins=sum(c['verified_property_coordinates']is not None for c in result),
                 status_counts=dict(counts),all297_status_rows=len(all_status),original_data_changed=False,
                 moso_new_requests=0,moso_historical_requests=313,full_executed=False,rule_version=VERSION,
                 warning='Chênh đến điểm tham chiếu không là sai số thực địa; không mặc định marker là cổng hoặc vị trí căn.')
    save(BASE/'reports/checks.json',summary)
    table=['# Đối chứng vị trí: kết quả từng ca','',
           'Điểm dưới đây là tham chiếu dự án/cơ sở trên nguồn công khai; chưa có pin tài sản được khảo sát độc lập. Khoảng cách làm tròn để đọc, giá trị đầy đủ ở CSV/JSONL.','',
           '| ID | Định danh đối chứng | Chênh tới điểm tham chiếu | Người dùng báo | Trạng thái |',
           '|---|---|---:|---:|---|']
    for c in result:
        name=(c['reference']or{}).get('entity_name','Chưa có điểm được chấp nhận')
        d=f"{c['distance_to_reference_m']:,.0f} m"if c['distance_to_reference_m']is not None else'Chưa tính'
        user=(c['user_feedback']or{}).get('reported_distance_m')or'Chưa có số đo'
        table.append(f"| {c['tin_id']} | {name} | {d} | {user} | {c['external_review_status']} |")
    table+=['','## Giới hạn từng ca','']
    for c in result:
        table +=[f"### {c['tin_id']}",'',c['review_reason'],'',c['unresolved'],'','Nguồn: '+', '.join(f"[{s}]({sources[s]['url']})"for s in c['source_ids'])if c['source_ids']else'Nguồn ngoài chưa đủ để định danh.','']
    (BASE/'reports/case_report.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    return summary


def verify():
    with patch.object(socket,'socket',side_effect=AssertionError('Build đối chứng offline cấm socket')):
        summary=build()
        paths=[p for folder in ['data','reports']for p in(BASE/folder).glob('*')if p.is_file()and p.name not in ['verification.json','tests.log']]
        first={p.relative_to(BASE).as_posix():digest(p)for p in paths}
        build(check_inputs=False)
        assert first=={p.relative_to(BASE).as_posix():digest(p)for p in paths}
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (BASE/'reports/tests.log').write_text(stream.getvalue(),encoding='utf-8')
    assert result.wasSuccessful(),stream.getvalue()
    locked=read(BASE/'input_hashes.json')
    preserved=verify_protected(locked)
    assert preserved
    evidence_hashes={p.relative_to(BASE).as_posix():digest(p)for p in(BASE/'evidence').glob('*')if p.is_file()}
    code_hashes={p.relative_to(ROOT).as_posix():digest(p)for p in [ROOT/'src/location_review.py',ROOT/'scripts/build_location_review.py',ROOT/'scripts/collect_location_evidence.py',ROOT/'tests/test_location_review.py']}
    save(BASE/'reports/verification.json',dict(offline_socket_blocked=True,identical_rebuild=True,generated_hashes=first,
                                             protected_files=len(locked),protected_hashes_preserved=preserved,
                                             tests_run=result.testsRun,tests_passed=result.wasSuccessful(),
                                             code_hashes=code_hashes,evidence_hashes=evidence_hashes,summary=summary))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');verify()
