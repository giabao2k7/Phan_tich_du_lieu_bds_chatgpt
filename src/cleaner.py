import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from .config import TZ, DISTRICTS


def decimal_number(text):
    text = text.strip().replace(' ', '').replace('\u00a0', '')
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return float(Decimal(text))
    except InvalidOperation:
        return None


def money(text):
    if not text or 'thỏa thuận' in text.lower() or 'thoả thuận' in text.lower():
        return None
    match = re.fullmatch(r'\s*~?\s*(\d[\d.,]*)\s*(tỷ|tỉ|triệu|nghìn|ngàn|đồng|vnd|đ)(?:\s*/\s*m[²2])?\s*', text.lower())
    if not match:
        return None
    token = match[1]
    # Không đoán 1.234 là 1234 hay 1,234 đơn vị tiền.
    if token.count('.') + token.count(',') > 1 or re.fullmatch(r'\d+[.,]\d{3}', token):
        return None
    try:
        number = Decimal(token.replace(',', '.'))
    except InvalidOperation:
        return None
    factor = {'tỷ': 10**9, 'tỉ': 10**9, 'triệu': 10**6, 'nghìn': 1000, 'ngàn': 1000}.get(match[2], 1)
    return int((number * factor).quantize(Decimal('1')))


def area(text):
    match = re.fullmatch(r'\s*(\d[\d.,]*)\s*m[²2]\s*', text)
    return decimal_number(match[1]) if match else None


def posting_date(text, crawled_at, explicit_datetime=''):
    stamp = datetime.fromisoformat(crawled_at)
    if stamp.tzinfo is None:
        raise ValueError('Metadata thời điểm tải thiếu múi giờ.')
    stamp = stamp.astimezone(TZ)
    value = text.strip().lower()
    if value in ['hôm nay', 'vừa xong']:
        return stamp.date().isoformat()
    if value == 'hôm qua':
        return (stamp - timedelta(days=1)).date().isoformat()
    match = re.fullmatch(r'(\d+)\s*(phút|giờ|ngày|tuần)\s*trước', value)
    if match:
        delta = {'phút': 'minutes', 'giờ': 'hours', 'ngày': 'days', 'tuần': 'weeks'}[match[2]]
        return (stamp - timedelta(**{delta: int(match[1])})).date().isoformat()
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    if explicit_datetime:
        try:
            exact = datetime.fromisoformat(explicit_datetime.replace('Z', '+00:00'))
            if exact.tzinfo is not None:
                return exact.astimezone(TZ).date().isoformat()
        except ValueError:
            return ''
    return ''


def district(text):
    text = re.sub(r'^(Quận|Huyện|Thành phố)\s+', '', text or '', flags=re.I)
    if text.isdigit():
        text = 'Quận ' + text
    return text if text in DISTRICTS else ''
