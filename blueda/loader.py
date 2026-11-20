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


def _detect_csv(path):
    """인코딩과 구분자를 차례로 시도해서 찾습니다."""
    for enc in CSV_ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                sample = f.read(20000)
        except (UnicodeDecodeError, UnicodeError):
            continue
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter  # 구분자 추정
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


def load_file(path, sheet=None):
    """파일을 DataFrame으로 읽습니다. (FileInfo, DataFrame, 실행 코드) 반환."""
    info = detect_file(path)
    if not info.supported:
        return info, None, ""
    if info.file_type == "csv":
        df = pd.read_csv(path, encoding=info.encoding, sep=info.delimiter)
        code = (
            "# [목적] CSV 파일 불러오기 (인코딩·구분자는 자동 판별 결과)\n"
            f"df = pd.read_csv({path!r}, encoding={info.encoding!r}, sep={info.delimiter!r})"
        )
    else:  # excel
        sheet = sheet if sheet is not None else info.sheets[0]
        df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
        code = (
            "# [목적] Excel 시트 불러오기\n"
            f"df = pd.read_excel({path!r}, sheet_name={sheet!r})  # 지정한 시트만 읽기"
        )
    return info, df, code
