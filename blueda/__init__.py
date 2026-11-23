"""BLUEDA: 전처리 판단부터 분석 로그까지 남기는 EDA 도우미."""

from .config import BluedaConfig, release_config
from .core import Blueda
from .logger import AnalysisLogger
from .preprocess_check import check_preprocessing, format_report
from .source_check import KNOWN_LICENSES, SourceInfo
from .loader import detect_file, load_file
from .result import AnalysisResult
from .scope import AnalysisScope

__version__ = "0.4.1"
__all__ = [
    "detect_file",
    "load_file",
    "AnalysisResult",
    "AnalysisScope",
    "Blueda",
    "BluedaConfig",
    "release_config",
    "AnalysisLogger",
    "check_preprocessing",
    "format_report",
    "SourceInfo",
    "KNOWN_LICENSES",
]
