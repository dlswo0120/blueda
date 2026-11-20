"""검정 결과를 사람이 읽는 문장으로 바꿉니다.

p값 해석 원칙 (보고서에도 그대로 쓰입니다):
- p값은 '귀무가설이 맞다고 가정했을 때, 지금 같은(또는 더 극단적인) 결과가 나올 확률'입니다.
- p < 유의수준이면 귀무가설을 기각합니다. '대립가설이 증명됐다'가 아니라 '근거가 있다'로 씁니다.
- p ≥ 유의수준이면 '차이가 없다'가 아니라 '차이가 있다고 할 근거가 부족하다'로 씁니다.
- 통계적 유의성과 실제 크기는 다릅니다. 효과 크기를 함께 봅니다.
"""


def fmt_p(p):
    """p값 표기: 아주 작으면 '< 0.001'."""
    if p is None:
        return "-"
    return "< 0.001" if p < 0.001 else f"{p:.4f}"


def _p_phrase(p):
    """문장 안에서 쓰는 p값 표현: 'p < 0.001' 또는 'p = 0.0321'."""
    return "p < 0.001" if p < 0.001 else f"p = {p:.4f}"


# 받침에 따라 바뀌는 조사 쌍 (받침 있음, 받침 없음)
_JOSA = {"을/를": ("을", "를"), "이/가": ("이", "가"), "은/는": ("은", "는"), "과/와": ("과", "와")}


def josa(word, pair):
    """단어 끝 받침에 맞는 조사를 붙입니다. 예: josa("매출", "을/를") → "매출을"

    한글이 아니면(영문·숫자 등) 받침을 정확히 알 수 없어 '을(를)' 형태로 둘 다 적습니다.
    """
    word = str(word)
    with_final, without_final = _JOSA[pair]
    last = word[-1] if word else ""
    if "가" <= last <= "힣":
        has_final = (ord(last) - ord("가")) % 28 != 0   # 한글 음절 코드로 받침 유무 계산
        return word + (with_final if has_final else without_final)
    if last.isdigit():
        # 숫자는 읽는 소리로 판단: 0(십·백·천·만)·1(일)·3(삼)·6(육)·7(칠)·8(팔)은 받침 있음
        return word + (with_final if last in "013678" else without_final)
    return f"{word}{with_final}({without_final})"


def interpret_p(p, alpha, h0, h1):
    """귀무가설(h0)·대립가설(h1) 문장을 받아 결론 문장을 만듭니다."""
    if p < alpha:
        return (f"{_p_phrase(p)}로 유의수준 {alpha}보다 작으므로 귀무가설({h0})을 기각합니다. "
                f"{h1}고 볼 통계적 근거가 있습니다.")
    return (f"{_p_phrase(p)}로 유의수준 {alpha} 이상이므로 귀무가설({h0})을 기각하지 못합니다. "
            f"{h1}고 할 근거가 부족합니다. ('차이가 없다'는 뜻은 아닙니다.)")


def effect_label(value, kind):
    """효과 크기 해석. Cohen(1988)의 관례 기준이며 분야마다 다를 수 있습니다."""
    v = abs(value)
    cuts = {
        "d": (0.2, 0.5, 0.8),          # Cohen's d
        "eta2": (0.01, 0.06, 0.14),    # 에타제곱
        "cramer_v": (0.1, 0.3, 0.5),   # Cramér's V (자유도 1 기준)
        "r": (0.1, 0.3, 0.5),          # 상관계수
    }[kind]
    if v < cuts[0]:
        return "매우 작음"
    if v < cuts[1]:
        return "작음"
    if v < cuts[2]:
        return "중간"
    return "큼"


EFFECT_NOTE = "효과 크기 기준(작음·중간·큼)은 Cohen(1988)의 관례입니다. 분야마다 기준이 다를 수 있습니다."
