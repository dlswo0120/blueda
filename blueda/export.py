"""결과 내보내기: CSV, Excel.

- CSV: 표마다 파일 하나. utf-8-sig로 저장해서 엑셀에서 한글이 깨지지 않게 합니다.
- Excel: 결과 하나를 파일 하나로. 표는 시트별로, 차트는 '차트' 시트에 이미지로 넣습니다.
- Word(.docx)·PDF 보고서는 4단계에서 추가합니다.
"""

import io
import os
import re

import pandas as pd


def _safe_name(name, max_len=31):
    """파일·시트 이름에 쓸 수 없는 문자를 바꿉니다. 엑셀 시트 이름은 31자 제한."""
    return re.sub(r'[\\/*?:\[\]<>|"]', "_", str(name))[:max_len]


def to_csv(results, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for r in results:
        for tname, table in r.tables.items():
            path = os.path.join(out_dir, f"{_safe_name(r.name, 60)}_{_safe_name(tname, 60)}.csv")
            table.to_csv(path, encoding="utf-8-sig")
            paths.append(path)
    return paths


def to_excel(results, path, include_charts=True):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    used = set()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # 첫 시트: 결과 세션 요약
        summary = pd.DataFrame([{"시각": r.created_at, "상태": r.status, "분석": r.name, "메시지": r.message}
                                for r in results])
        summary.to_excel(writer, sheet_name="요약", index=False)
        used.add("요약")
        for r in results:
            for tname, table in r.tables.items():
                sheet = _safe_name(tname)
                n = 2
                while sheet in used:                     # 시트 이름 중복 방지
                    sheet = _safe_name(f"{tname[:27]}_{n}")
                    n += 1
                used.add(sheet)
                table.to_excel(writer, sheet_name=sheet)
        if include_charts:
            figs = [(name, fig) for r in results for name, fig in r.figures.items()]
            if figs:
                from openpyxl.drawing.image import Image as XLImage
                ws = writer.book.create_sheet("차트")
                row = 1
                for name, fig in figs:
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", dpi=90)  # 그림을 메모리에 PNG로 저장
                    buf.seek(0)
                    ws.cell(row=row, column=1, value=name)
                    img = XLImage(buf)
                    ws.add_image(img, f"A{row + 1}")
                    row += int(img.height / 20) + 3          # 다음 그림 위치 (행 높이 약 20px)
    return path
