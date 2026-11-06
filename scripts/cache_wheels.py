"""Đóng lại wheel từ cache uv; kiểm tra nguyên vẹn mọi hash RECORD trước khi dùng."""
import base64
import csv
import hashlib
import zipfile
import sys
from pathlib import Path
from packaging.tags import sys_tags


def run():
    sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    output = root / '.runtime/wheels'
    output.mkdir(exist_ok=True)
    count = 0
    supported = {str(tag) for tag in sys_tags()}
    for folder in (root / '.runtime/uv-cache/archive-v0').iterdir():
        for info in folder.glob('*.dist-info'):
            wheel_meta = (info / 'WHEEL').read_text(encoding='utf-8')
            tags = [line.removeprefix('Tag: ') for line in wheel_meta.splitlines() if line.startswith('Tag: ')]
            chosen_tag = next(tag for tag in tags if tag in supported)
            name = info.name.removesuffix('.dist-info') + '-' + chosen_tag + '.whl'
            with (info / 'RECORD').open(encoding='utf-8', newline='') as file:
                records = list(csv.reader(file))
            for relative, digest, length in records:
                content = (folder / relative).read_bytes()
                if digest:
                    algorithm, expected = digest.split('=', 1)
                    actual = base64.urlsafe_b64encode(hashlib.new(algorithm, content).digest()).rstrip(b'=').decode()
                    assert actual == expected, f'Hash không khớp: {relative}'
                if length:
                    assert len(content) == int(length)
            with zipfile.ZipFile(output / name, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for relative, _, _ in records:
                    archive.write(folder / relative, relative)
            count += 1
    print(f'Đã tạo {count} wheel, xác minh hash RECORD của toàn bộ nội dung.')


if __name__ == '__main__':
    run()
