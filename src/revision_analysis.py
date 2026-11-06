"""Phân tích tin đăng theo điều kiện đủ và đúng loại mẫu số."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from .config import SOURCES


def analyze_revision(rows, evidence, areas, old_rows, base):
    from .pipeline import write_csv
    output = base / 'outputs'
    output.mkdir(parents=True, exist_ok=True)
    eligible_ids = {e['snapshot']['tin_id'] for e in evidence if e['semantic_eligible']}
    eligible_rows = [r for r in rows if r['tin_id'] in eligible_ids]
    available = [a for a in areas if a['eligible']]
    main = [a for a in available if a['primary'] and a['price_vnd'] and a['price_vnd'] > 0]
    snapshots = sorted({e['snapshot']['capture_at'][:10] for e in evidence})
    date_label = ', '.join(snapshots)
    summaries = []
    def summarize(kind, metric, area_type, values, denominator):
        series = pd.Series(values, dtype='float64')
        series = series[series > 0]
        q1, q3 = series.quantile(.25), series.quantile(.75)
        summaries.append(dict(loai_hinh=kind, metric=metric, area_type=area_type, count=len(series), denominator=denominator,
                              excluded=denominator-len(series), mean=series.mean(), median=series.median(), min=series.min(), max=series.max(),
                              p25=q1, p75=q3, p90=series.quantile(.9), iqr_low=q1-1.5*(q3-q1), iqr_high=q3+1.5*(q3-q1),
                              iqr_review_count=int(((series<q1-1.5*(q3-q1))|(series>q3+1.5*(q3-q1))).sum()),
                              snapshot_dates=date_label, interpretation='giá chào theo tin đăng; giữ ngoại lệ'))
    for kind in SOURCES:
        denominator = sum(e['compatibility_row']['loai_hinh'] == kind for e in evidence)
        summarize(kind, 'price_vnd', '', [r['gia_vnd'] for r in eligible_rows if r['loai_hinh']==kind and r['gia_vnd']], denominator)
        for area_type in ['thông thủy', 'tim tường', 'đất', 'đất công nhận', 'sử dụng']:
            group = [a for a in available if a['loai_hinh']==kind and a['area_type']==area_type]
            summarize(kind, 'area_m2', area_type, [a['area_m2'] for a in group], denominator)
            summarize(kind, 'price_per_m2_vnd', area_type, [float(a['price_per_m2_vnd']) for a in group if a['price_per_m2_vnd']], denominator)
    pd.DataFrame(summaries).to_csv(output/'summary_by_type.csv', index=False, encoding='utf-8-sig')
    json_lines = lambda path, values: path.write_text(''.join(json.dumps(v,ensure_ascii=False,default=str)+'\n' for v in values),encoding='utf-8')
    json_lines(output/'plot_price_rows.jsonl', eligible_rows)
    json_lines(output/'plot_primary_area_rows.jsonl', main)
    chart_counts = {}
    figure, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axis, kind in zip(axes, SOURCES):
        values = [r['gia_vnd']/1e9 for r in eligible_rows if r['loai_hinh']==kind and r['gia_vnd'] and r['gia_vnd']>0]
        total = sum(e['compatibility_row']['loai_hinh']==kind for e in evidence)
        counts, _, _ = axis.hist(values, bins=20, color='#157f85', edgecolor='white')
        chart_counts[kind] = dict(price_points=len(values), price_hist_count=int(sum(counts)), total=total)
        axis.set(title=f'{kind}: n={len(values)}, không tham gia={total-len(values)}',xlabel='Giá chào (tỷ VND)',ylabel='Số tin')
    figure.suptitle(f'Giá chào theo tin đăng — snapshot {date_label}\nThang tuyến tính; giữ ngoại lệ; phạm vi/đơn vị tài sản theo nguồn')
    figure.tight_layout()
    figure.savefig(output/'price_distribution.png',dpi=150)
    plt.close(figure)
    figure, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axis, kind in zip(axes, SOURCES):
        group = [a for a in main if a['loai_hinh']==kind]
        label = 'thông thủy' if kind=='can_ho' else 'đất công nhận'
        points = axis.scatter([a['area_m2'] for a in group],[a['price_vnd']/1e9 for a in group],alpha=.6,s=20,color='#157f85')
        total = chart_counts[kind]['total']
        chart_counts[kind].update(primary_area_points=len(group),scatter_count=len(points.get_offsets()))
        axis.set(title=f'{kind}: n={len(group)}, không tham gia={total-len(group)}',xlabel=f'Diện tích {label} (m²)',ylabel='Giá chào (tỷ VND)')
    figure.suptitle(f'Giá chào theo tin đăng và diện tích có nhãn — snapshot {date_label}\nThang tuyến tính; giữ ngoại lệ; không thay thế mẫu số')
    figure.tight_layout()
    figure.savefig(output/'price_area_scatter.png',dpi=150)
    plt.close(figure)
    counts = pd.Series([r['quan_huyen_chuan'] for r in eligible_rows],dtype='str').value_counts().sort_values()
    figure, axis = plt.subplots(figsize=(11,7))
    axis.barh(counts.index,counts.values,color='#157f85')
    axis.set(title=f'Tin đăng theo nhãn địa bàn cũ — snapshot {date_label}\nn={len(eligible_rows)}, không tham gia={len(evidence)-len(eligible_rows)}; chưa xác minh thực địa',xlabel='Số tin đăng',ylabel='Quận / huyện / thành phố (nguồn)')
    figure.tight_layout()
    figure.savefig(output/'district_counts.png',dpi=150)
    plt.close(figure)
    write_csv(output/'district_counts.csv',[dict(district=k,count=v)for k,v in counts.items()],['district','count'])
    impact = []
    for kind in SOURCES:
        for version, source_rows in [('old_compatibility_mixed_area',old_rows),('new_compatibility_arithmetic_only',rows)]:
            group = [r for r in source_rows if r['loai_hinh']==kind]
            price_values = pd.to_numeric(pd.Series([r['gia_vnd'] for r in group],dtype='object'),errors='coerce').dropna()
            ratio_values = pd.to_numeric(pd.Series([r['gia_m2_tinh_vnd'] for r in group],dtype='object'),errors='coerce').dropna()
            impact.append(dict(version=version,loai_hinh=kind,rows=len(group),price_count=len(price_values),price_median=price_values.median(),
                               compatibility_ratio_count=len(ratio_values),compatibility_ratio_median=ratio_values.median(),
                               warning='Chỉ so tác động; mẫu số trộn nghĩa không dùng làm phân bố phân tích'))
    pd.DataFrame(impact).to_csv(output/'old_new_impact.csv',index=False,encoding='utf-8-sig')
    checks = dict(counts=chart_counts,district_total=int(counts.sum()),eligible_price_rows=len(eligible_rows),
                  counts_match=all(c['price_points']==c['price_hist_count'] and c['primary_area_points']==c['scatter_count'] for c in chart_counts.values()) and int(counts.sum())==len(eligible_rows),
                  files_exist=all((output/p).exists() and (output/p).stat().st_size>0 for p in ['summary_by_type.csv','price_distribution.png','price_area_scatter.png','district_counts.png']))
    (output/'chart_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return checks
