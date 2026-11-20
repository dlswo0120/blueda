"""사용자 설정 저장·불러오기.

설정은 이 PC의 사용자 폴더에 JSON으로 저장되어 다음 실행 때도 유지됩니다.
- Windows: %APPDATA%\\BLUEDA\\settings.json
- 그 외   : ~/.config/blueda/settings.json
"""

import json
import os
from dataclasses import asdict, fields

from .config import BluedaConfig

# 화면 설정 패널에 보여줄 항목: (키, 이름, 설명, 최솟값, 최댓값, 단계)
EDITABLE = [
    ("alpha", "유의수준", "p값이 이보다 작으면 귀무가설 기각 (관례 0.05)", 0.001, 0.2, 0.01),
    ("outlier_iqr_k", "IQR 배수", "박스플롯·이상값 후보 경계 (관례 1.5)", 0.5, 5.0, 0.1),
    ("z_threshold", "|z| 기준", "이 값보다 멀면 이상값 후보 (관례 3)", 1.0, 6.0, 0.5),
    ("chart_sample_size", "차트 표본 크기", "행이 이보다 많으면 차트만 표본으로 그림", 1_000, 2_000_000, 10_000),
    ("category_max_unique", "범주 판단 고유값 수", "숫자 열 고유값이 이 이하면 범주일 수 있음", 2, 100, 1),
]


def settings_path():
    base = os.environ.get("APPDATA") if os.name == "nt" else None
    base = base or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, "BLUEDA" if os.name == "nt" else "blueda")
    return os.path.join(folder, "settings.json")


def load_settings(path=None):
    """저장된 설정을 읽어 (BluedaConfig, 화면 설정 dict)로 돌려줍니다. 파일이 없거나 깨져 있으면 기본값."""
    path = path or settings_path()
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    known = {f.name for f in fields(BluedaConfig)}
    cfg_values = {k: v for k, v in data.get("config", {}).items() if k in known}
    try:
        cfg = BluedaConfig(**cfg_values)
    except (TypeError, ValueError):
        cfg = BluedaConfig()
    ui = {"theme": "light", "recent_files": []}
    ui.update({k: v for k, v in data.get("ui", {}).items() if k in ui})
    return cfg, ui


def save_settings(cfg, ui, path=None):
    path = path or settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"config": asdict(cfg), "ui": ui}, f, ensure_ascii=False, indent=2)
    return path
