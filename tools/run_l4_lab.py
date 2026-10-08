"""Manual foreground L4 synthetic lab. Ctrl+C stops only this lab instance."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.l4_lab import L4SyntheticLab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024..65535')
    lab = L4SyntheticLab(ROOT, args.port)
    try:
        lab.register()
        target, row = lab.provision()
        print('L4 隔离合成业务靶场：' + lab.origin, flush=True)
        print('内存合成数据库、独立测试会话；没有生产连接。', flush=True)
        print('请在「业务验证准备」载入：' + row['id'], flush=True)
        print('可勾选固定输入正负对照；标准模式不调用 AI。', flush=True)
        print('按 Ctrl+C 关闭此靶场；目标草稿和密文会话保留，但不会自动续跑。', flush=True)
        lab.server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt: pass
    finally: lab.close()


if __name__ == '__main__': main()
