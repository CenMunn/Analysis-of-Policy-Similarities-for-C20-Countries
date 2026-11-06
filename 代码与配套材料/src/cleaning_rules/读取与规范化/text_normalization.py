"""原文与清洗文本保持繁简；仅分析副本转换为简体。"""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "resources" / "cleaning" / "resources" / "vendor"))

try:
    from opencc import OpenCC
except ImportError as exc:
    raise RuntimeError("缺少繁简转换依赖，请保留本项目 vendor 文件夹，或安装 requirements.txt。") from exc

_converter = OpenCC("t2s")

def to_simplified(text):
    return _converter.convert(text)
