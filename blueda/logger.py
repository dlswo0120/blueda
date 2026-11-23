"""B: 분석 로그 (목적 → 코드 → 결과 → 해석).

BLUEDA가 내부에서 실행한 분석도, 사용자가 직접 실행한 코드도
같은 4칸 형식으로 남깁니다. 나중에 수동으로 옮겨 적기 쉽게
Markdown(.md)과 코드만 모은 파이썬 파일(.py) 두 가지로 저장합니다.
"""

import contextlib
import io
import os
from datetime import datetime


class AnalysisLogger:
    """분석 로그: 단계마다 목적 → 실행 코드 → 결과 → 해석을 기록하고 .md(읽기용)·.py(재실행용)로 저장합니다."""
    def __init__(self, log_dir="logs", print_code=True, session_name=None):
        """print_code=True면 단계마다 코드를 화면(터미널)에도 출력합니다."""
        self.log_dir = log_dir
        self.print_code = print_code
        self.session_name = session_name or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.steps = []          # 단계별 기록을 쌓아두는 리스트
        self.lecture_links = {}  # G: 단계 번호 → 강의 개념 메모

    # ------------------------------------------------------------
    def log(self, purpose, code, result="", interpretation=""):
        """이미 실행한 분석을 4칸 형식으로 기록합니다."""
        step = {
            "no": len(self.steps) + 1,
            "purpose": purpose,
            "code": code.strip("\n"),
            "result": str(result).strip("\n"),
            "interpretation": interpretation,
        }
        self.steps.append(step)
        if self.print_code:
            self._print_step(step)
        return step["no"]

    def run(self, purpose, code, namespace, interpretation=""):
        """코드 문자열을 직접 실행하고, 출력 결과까지 함께 기록합니다.

        namespace: 코드가 사용할 변수 모음. 보통 globals()를 넘깁니다.
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):   # print 결과를 가로채서 저장
            exec(code, namespace)                   # 문자열로 받은 코드를 실행
        return self.log(purpose, code, buffer.getvalue(), interpretation)

    def interpret(self, step_no, text):
        """결과를 본 뒤 해석을 나중에 채워 넣습니다."""
        self.steps[step_no - 1]["interpretation"] = text

    def link_lecture(self, step_no, concept, source):
        """G: 이 단계에 적용한 강의 개념과 출처를 남깁니다."""
        self.lecture_links[step_no] = {"concept": concept, "source": source}

    # ------------------------------------------------------------
    def _print_step(self, step):
        """단계 하나를 터미널에 출력합니다."""
        line = "=" * 60
        print(f"\n{line}\n[STEP {step['no']}] 목적: {step['purpose']}\n{line}")
        print("[코드]")
        print(step["code"])
        if step["result"]:
            print("[결과]")
            print(step["result"])
        if step["interpretation"]:
            print(f"[해석] {step['interpretation']}")

    def to_markdown(self, include_lecture_links=True):
        """전체 로그를 마크다운 문서로 만듭니다. 강의 개념 연결은 설정에 따라 포함합니다."""
        lines = [f"# BLUEDA 분석 로그 ({self.session_name})", ""]
        for s in self.steps:
            lines += [f"## STEP {s['no']}. {s['purpose']}", "", "**코드**", "", "```python", s["code"], "```", ""]
            lines += ["**결과**", "", "```", s["result"] or "(출력 없음)", "```", ""]
            lines += ["**해석**", "", s["interpretation"] or "(작성 필요)", ""]
            link = self.lecture_links.get(s["no"])
            if include_lecture_links and link:
                lines += [f"> 적용 개념: {link['concept']}  ", f"> 출처: {link['source']}", ""]
        return "\n".join(lines)

    def to_script(self):
        """실행한 코드만 순서대로 모은 .py 내용을 만듭니다."""
        parts = [f"# BLUEDA 분석 코드 모음 ({self.session_name})", ""]
        for s in self.steps:
            parts += [f"# ===== STEP {s['no']}. {s['purpose']} =====", s["code"], ""]
        return "\n".join(parts)

    def save(self, include_lecture_links=True):
        """로그를 .md와 .py로 저장하고 경로를 돌려줍니다."""
        os.makedirs(self.log_dir, exist_ok=True)
        md_path = os.path.join(self.log_dir, f"log_{self.session_name}.md")
        py_path = os.path.join(self.log_dir, f"code_{self.session_name}.py")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown(include_lecture_links))
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(self.to_script())
        return md_path, py_path
