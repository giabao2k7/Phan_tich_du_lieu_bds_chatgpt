import argparse
import sys
import socket
from unittest.mock import patch
from pathlib import Path
from src.config import ROOT
from src.crawler import ControlledClient, CrawlStopped
from src.collection import collect
from src.pipeline import parse_saved


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Thu thập một lượt hoặc tái lập offline dữ liệu moso.vn.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('pilot')
    sub.add_parser('full')
    offline = sub.add_parser('parse')
    offline.add_argument('html_dir', type=Path)
    offline.add_argument('output_csv', type=Path)
    args = parser.parse_args()
    if args.command == 'parse':
        with patch.object(socket, 'socket', side_effect=RuntimeError('Lệnh parse cấm truy cập mạng')):
            rows, excluded, errors = parse_saved(args.html_dir, args.output_csv)
        print(f'Offline: giữ {len(rows)}, loại {len(excluded)}, lỗi {len(errors)}.')
        return 1 if errors else 0
    base = ROOT / 'pilot' if args.command == 'pilot' else ROOT
    try:
        client = ControlledClient(base, args.command)
    except CrawlStopped as exc:
        print(str(exc))
        return 2
    collection_stopped = False
    try:
        client.load_robots()
        collect(client)
    except (CrawlStopped, ValueError) as exc:
        collection_stopped = True
        client.state['stop_reason'] = str(exc)
        client.save_state()
        print('Đã dừng thu thập:', str(exc))
    if collection_stopped and not (base / 'data/manifest.jsonl').exists():
        return 2
    rows, excluded, errors = parse_saved(base / 'data/raw_html', base / 'data/listings.csv')
    print(f'Giữ {len(rows)}, loại {len(excluded)}, lỗi {len(errors)}. Xem reports/acceptance.md.')
    return 1 if collection_stopped or errors or not rows else 0


if __name__ == '__main__':
    sys.exit(main())
