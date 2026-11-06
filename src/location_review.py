"""Đối chứng vị trí ngoài nguồn: luôn tách điểm tham chiếu khỏi pin tài sản đã xác minh."""
import json
import math
from pathlib import Path
from .observations import valid_coordinates, haversine

VERSION = 'external-location-review/1.0'


def polygon_centroid(ring):
    if len(ring) < 4 or ring[0] != ring[-1] or not all(valid_coordinates(p) for p in ring):
        raise ValueError('Cần polygon khép kín, tọa độ hợp lệ.')
    # Dời gốc trước tích chéo để giảm triệt tiêu số khi tọa độ gần nhau.
    origin = ring[0]
    points = [[x-origin[0],y-origin[1]]for x,y in ring]
    cross=[a[0]*b[1]-b[0]*a[1]for a,b in zip(points,points[1:])]
    twice_area=sum(cross)
    if abs(twice_area)<1e-15:
        raise ValueError('Polygon không có diện tích.')
    return [origin[i]+sum((a[i]+b[i])*c for a,b,c in zip(points,points[1:],cross))/(3*twice_area)for i in (0,1)]


def inside_polygon(point, ring):
    x,y=point;inside=False
    for (ax,ay),(bx,by) in zip(ring,ring[1:]):
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:
            inside=not inside
    return inside


def embed_reference(evidence, name, level):
    pairs=evidence.get('candidate_pairs',[])
    unique={(p['longitude'],p['latitude'])for p in pairs}
    if evidence.get('http_status')!=200 or len(unique)!=1:
        raise ValueError('Không có đúng một cặp điểm từ phản hồi bản đồ đã đọc.')
    coordinates=list(next(iter(unique)))
    if not valid_coordinates(coordinates):
        raise ValueError('Điểm tham chiếu không hợp lệ.')
    return dict(entity_name=name,coordinates=coordinates,level=level,
                source_id=evidence['source_id'],source_locator='candidate_pairs; Google embed response named place context',
                observed_at=evidence['observed_at'],source_sha256=evidence['content_sha256'],
                crs='WGS84_assumed_provider_coordinates',point_definition='provider_place_marker_not_confirmed_entrance',
                accuracy_m=None,accuracy_note='Nguồn không công bố sai số đo; số chữ số không là độ chính xác.',
                status='reference_only_not_surveyed')


def osm_reference(evidence):
    if evidence.get('status')!='geometry_captured':
        raise ValueError('Thiếu geometry OSM đã lấy.')
    ring=evidence['geometry'];point=polygon_centroid(ring)
    if not inside_polygon(point,ring):
        raise ValueError('Centroid ngoài polygon; không tự chọn pin khác.')
    return dict(entity_name=evidence['tags']['name'],coordinates=point,level='project',
                source_id=evidence['source_id'],source_locator='geometry; planar area centroid of OSM way '+evidence['osm_id'],
                observed_at=evidence['observed_at'],source_sha256=evidence['content_sha256'],
                source_feature_version=evidence['version'],source_feature_timestamp=evidence['timestamp'],
                crs='WGS84_OSM',point_definition='area_centroid_of_community_mapped_residential_polygon',
                accuracy_m=None,accuracy_note='Geometry cộng đồng; centroid là điểm đại diện tính toán, không là cổng hoặc vị trí căn hộ.',
                status='reference_only_not_surveyed')


def evaluate_case(source, review, reference=None):
    snapshot=source['snapshot'];row=source['compatibility_row']
    original=[row['kinh_do'],row['vi_do']]
    result=dict(snapshot,tin_url=row['url'],source_coordinates=original,
                source_coordinate_status=source['coordinate_verification'],
                external_review_status=review['status'],review_reason=review['reason'],
                source_ids=review['source_ids'],identity_match_level=review['identity_match_level'],
                unresolved=review['unresolved'],reference=reference,
                verified_property_coordinates=None,
                exact_spatial_analysis_eligible=False,
                coarse_reference_comparison_eligible=reference is not None,
                historical_scope_review=review.get('historical_scope_review','source_label_not_replaced'),
                rule_version=VERSION)
    if reference is not None:
        result['distance_to_reference_m']=haversine(original,reference['coordinates']) if valid_coordinates(original) else None
        result['distance_meaning']='source_pin_to_selected_external_reference_not_surveyed_property_error'
    else:
        result['distance_to_reference_m']=None
        result['distance_meaning']='no_accepted_reference_do_not_impute'
    return result
