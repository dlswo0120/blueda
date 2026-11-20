"""파일 형식 자동 판별과 불러오기.

확장자만 믿지 않고 파일 앞부분(매직 바이트)도 확인합니다.
- CSV/TSV/TXT : 인코딩 자동 판별 (utf-8, utf-8-sig, cp949, euc-kr 순서로 시도)
- Excel(.xlsx): 시트 목록 확인 후 지정 시트 읽기
- Word, PDF, 구형 .xls : 형식은 판별하되, 표 추출은 5단계에서 지원 (미지원 알림)
"""

import csv
import os
from dataclasses import dataclass, field

import pandas as pd

CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp949", "euc-kr")

# 파일 맨 앞 몇 바이트로 실제 형식을 확인 (확장자가 틀린 파일 대비)
MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip",                         # xlsx, docx는 내부가 zip
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "ole",   # 구형 .xls, .doc
}


@dataclass
class FileInfo:
    path: str
    file_type: str                 # csv / excel / word / pdf / xls / unknown
    size_bytes: int = 0
    encoding: str = ""             # CSV만 해당
    delimiter: str = ""            # CSV만 해당
    sheets: list = field(default_factory=list)  # Excel만 해당
    supported: bool = True
    detail: str = ""

    def summary(self):
        size_kb = self.size_bytes / 1024
        extra = []
        if self.encoding:
            extra.append(f"인코딩 {self.encoding}")
        if self.delimiter:
            extra.append(f"구분자 {self.delimiter!r}")
        if self.sheets:
            extra.append(f"시트 {len(self.sheets)}개: {', '.join(self.sheets)}")
        name = os.path.basename(self.path)
        return f"{name} → {self.file_type.upper()} ({size_kb:,.1f} KB){' · ' + ' · '.join(extra) if extra else ''}"


def _read_magic(path, n=8):
    with open(path, "rb") as f:
        return f.read(n)


def _zip_kind(path):
    """zip 안의 폴더 이름으로 xlsx / docx 구분."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        return "unknown"
    if any(n.startswith("xl/") for n in names):
        return "excel"
    if any(n.startswith("word/") for n in names):
        return "word"
    return "unknown"


SNIFF_BYTES = 1_000_000  # 인코딩 판별에 쓰는 앞부분 크기 (한글이 뒤에서 처음 나오는 파일 대비)


def _decode_sample(data, enc):
    """바이트를 지정 인코딩으로 풀어봅니다. 잘린 마지막 글자 때문에 생기는 오류는 무시합니다."""
    try:
        return data.decode(enc)
    except UnicodeDecodeError as e:
        if e.start >= len(data) - 4:          # 1MB 경계에서 한글 한 글자가 잘린 경우
            return data[:e.start].decode(enc)
        return None


def _detect_csv(path):
    """인코딩과 구분자를 차례로 시도해서 찾습니다."""
    with open(path, "rb") as f:
        data = f.read(SNIFF_BYTES)
    for enc in CSV_ENCODINGS:
        sample = _decode_sample(data, enc)
        if sample is None:
            continue
        try:
            delim = csv.Sniffer().sniff(sample[:20000], delimiters=",\t;|").delimiter  # 구분자 추정
        except csv.Error:
            delim = ","
        return enc, delim
    return None, None


def detect_file(path):
    """파일 형식을 판별해서 FileInfo로 돌려줍니다."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    info = FileInfo(path=path, file_type="unknown", size_bytes=os.path.getsize(path))
    ext = os.path.splitext(path)[1].lower()
    head = _read_magic(path)

    kind = next((v for k, v in MAGIC.items() if head.startswith(k)), None)
    if kind == "zip":
        info.file_type = _zip_kind(path)
    elif kind == "pdf":
        info.file_type = "pdf"
    elif kind == "ole":
        info.file_type = "xls" if ext == ".xls" else "doc"
    elif ext in (".csv", ".tsv", ".txt"):
        info.file_type = "csv"

    if info.file_type == "csv":
        enc, delim = _detect_csv(path)
        if enc is None:
            info.supported, info.detail = False, "인코딩을 판별하지 못했습니다."
        else:
            info.encoding, info.delimiter = enc, delim
    elif info.file_type == "excel":
        info.sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
    elif info.file_type in ("word", "pdf", "xls", "doc"):
        info.supported = False
        info.detail = "형식은 확인했지만 표 추출은 5단계에서 지원합니다."
    else:
        info.supported = False
        info.detail = "알 수 없는 형식입니다."
    return info


CHUNK_ROWS = 200_000  # CSV를 이만큼씩 나눠 읽음 (진행률 표시·취소 가능)


class LoadCancelled(Exception):
    """사용자가 읽기를 취소했을 때."""


def estimate_memory(path, info=None, sample_rows=20_000):
    """파일을 다 읽기 전에 메모리 사용량(바이트)을 추정합니다.

    앞부분 표본의 '행당 메모리'와 '행당 파일 크기'의 비율로 전체를 어림합니다.
    문자열이 많은 파일은 오차가 클 수 있어 대략적인 값입니다.
    """
    info = info or detect_file(path)
    if info.file_type != "csv" or not info.supported:
        return None
    sample = pd.read_csv(path, encoding=info.encoding, sep=info.delimiter, nrows=sample_rows)
    if sample.empty:
        return 0
    with open(path, "rb") as f:
        head_bytes = sum(len(f.readline()) for _ in range(len(sample) + 1))
    per_byte = sample.memory_usage(deep=True).sum() / max(head_bytes, 1)
    return int(per_byte * info.size_bytes)


def total_memory():
    """이 PC의 전체 메모리(바이트). 알 수 없으면 None."""
    try:
        if os.name == "nt":
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = _MS()
            ms.dwLength = ctypes.sizeof(_MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return int(ms.ullTotalPhys)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, ValueError, OSError):
        return None


def optimize_dtypes(df, category_ratio=0.5):
    """메모리를 줄입니다. 통계 정밀도를 해치지 않는 변환만 합니다.

    - 반복이 많은 문자열 열 → category (고유값 비율이 category_ratio 미만일 때)
    - 정수 열 → 값 범위에 맞는 더 작은 정수형
    - 실수 열은 바꾸지 않습니다 (float32로 줄이면 평균·분산 계산이 부정확해질 수 있음)
    반환: (최적화된 df, 바뀐 열 정보 dict)
    """
    changed = {"category": [], "int": []}
    for c in df.columns:
        s = df[c]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            n = s.notna().sum()
            if n and s.nunique(dropna=True) / n < category_ratio:
                df[c] = s.astype("category")
                changed["category"].append(c)
        elif pd.api.types.is_integer_dtype(s) and not pd.api.types.is_bool_dtype(s):
            down = pd.to_numeric(s, downcast="integer")
            if down.dtype != s.dtype:
                df[c] = down
                changed["int"].append(c)
    return df, changed


def load_file(path, sheet=None, progress=None, cancelled=None, usecols=None, optimize=False):
    """파일을 DataFrame으로 읽습니다. (FileInfo, DataFrame, 실행 코드) 반환.

    progress : 0~1 진행률을 받는 함수 (CSV만 실제 진행률, Excel은 시작·끝만)
    cancelled: True를 돌려주면 읽기를 멈추는 함수 → LoadCancelled 발생
    usecols  : 일부 열만 읽기 (메모리가 부족할 때)
    optimize : 읽은 뒤 optimize_dtypes 적용
    """
    info = detect_file(path)
    if not info.supported:
        return info, None, ""
    report = progress or (lambda p: None)
    stop = cancelled or (lambda: False)
    if info.file_type == "csv":
        parts = []
        with open(path, "rb") as fh:  # 바이너리로 열어야 읽은 위치(바이트)로 진행률 계산 가능
            reader = pd.read_csv(fh, encoding=info.encoding, sep=info.delimiter,
                                 usecols=usecols, chunksize=CHUNK_ROWS, low_memory=False)
            for chunk in reader:
                if stop():
                    raise LoadCancelled()
                parts.append(chunk)
                report(min(fh.tell() / max(info.size_bytes, 1), 0.99))
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        cols = f", usecols={list(usecols)!r}" if usecols else ""
        code = (
            "# [목적] CSV 파일 불러오기 (인코딩·구분자는 자동 판별 결과)\n"
            f"df = pd.read_csv({path!r}, encoding={info.encoding!r}, sep={info.delimiter!r}{cols})"
        )
    else:  # excel
        report(0.05)
        sheet = sheet if sheet is not None else info.sheets[0]
        df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl", usecols=usecols)
        code = (
            "# [목적] Excel 시트 불러오기\n"
            f"df = pd.read_excel({path!r}, sheet_name={sheet!r})  # 지정한 시트만 읽기"
        )
    if stop():
        raise LoadCancelled()
    if optimize:
        before = df.memory_usage(deep=True).sum()
        df, changed = optimize_dtypes(df)
        after = df.memory_usage(deep=True).sum()
        info.detail = (f"메모리 최적화 {before / 2**20:,.0f}MB → {after / 2**20:,.0f}MB "
                       f"(범주형 {len(changed['category'])}개, 정수 축소 {len(changed['int'])}개)")
        code += ("\n# 메모리 최적화: 반복 문자열 → category, 정수 → 작은 정수형\n"
                 + "".join(f"df[{c!r}] = df[{c!r}].astype('category')\n" for c in changed["category"])
                 + "".join(f"df[{c!r}] = pd.to_numeric(df[{c!r}], downcast='integer')\n" for c in changed["int"]))
    report(1.0)
    return info, df, code
