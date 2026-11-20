"""C: 재현성 기록 (라이브러리 버전, 랜덤 시드, 원본 데이터 경로)."""

import hashlib
import json
import os
import platform
import random
import sys
from datetime import datetime
from importlib import metadata

import numpy as np

TRACKED_PACKAGES = ("pandas", "numpy", "scipy", "matplotlib", "seaborn", "blueda")


def set_seed(seed=42):
    """파이썬 random과 numpy의 랜덤 시드를 고정합니다."""
    random.seed(seed)       # 파이썬 기본 random 고정
    np.random.seed(seed)    # numpy 랜덤 고정 (샘플링, 분할 등)
    return seed


def file_sha256(path):
    """파일 내용의 지문(해시). 데이터가 바뀌었는지 나중에 비교할 수 있습니다."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1MB씩 읽어서 메모리 절약
            h.update(chunk)
    return h.hexdigest()


def record_environment(seed=None, data_path=None):
    """분석 환경 정보를 딕셔너리로 모읍니다."""
    versions = {}
    for pkg in TRACKED_PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = "미설치"
    info = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "os": platform.platform(),
        "packages": versions,
        "random_seed": seed,
        "data_path": data_path,
    }
    if data_path and os.path.exists(data_path):
        info["data_sha256"] = file_sha256(data_path)
        info["data_size_bytes"] = os.path.getsize(data_path)
    return info


def save_environment(info, log_dir="logs", session_name="session"):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"env_{session_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return path
