"""화면 색과 스타일 (시안 기준).

다크 모드는 바깥 배경만 진한 회색으로 바꾸고, 흰 패널(박스) 안의 색은 그대로 둡니다.
"""

LIGHT_BG = "#F3F4F6"
DARK_BG = "#4B515A"

PANEL = "#FFFFFF"
SOFT = "#F3F4F6"
TEXT = "#1B2433"
TEXT2 = "#3B4656"
SUB = "#5F6B7A"
MUTED = "#8A94A3"
LINE = "#E5E8ED"
LINE2 = "#D5DAE1"
LINE3 = "#B8C0CC"
HOVER = "#F0F2F5"
WARN = "#8A4B0F"
ACCENT = "#2F5D9E"
ACCENT_HOVER = "#284F86"
DISABLED = "#C5CDD8"

CONSOLE_BG = "#14181F"
CONSOLE_TEXT = "#C9D1DC"
CONSOLE_TIME = "#6B7685"
STATUS_COLORS = {"SUCCESS": "#7FC8A0", "FAIL": "#E59B9B", "UNSUPPORTED": "#D9B96A", "INFO": "#8FB4EE", "RUN": "#9AA4B2"}

FONT_FAMILIES = ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "NanumGothic"]
MONO_FAMILIES = ["JetBrains Mono", "Consolas", "D2Coding", "Noto Sans Mono CJK KR", "monospace"]


def _asset(name):
    import os
    return os.path.join(os.path.dirname(__file__), "assets", name).replace("\\", "/")


def stylesheet(dark=False):
    bg = DARK_BG if dark else LIGHT_BG
    chevron = _asset("chevron.svg")
    return f"""
    QWidget {{ color: {TEXT}; font-size: 14px; }}
    QWidget#Root, QWidget#Page, QScrollArea#PageScroll, QWidget#PageInner {{ background: {bg}; }}
    QFrame#Header {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
    QFrame#Sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
    QFrame[panel="true"] {{ background: {PANEL}; border-radius: 8px; }}
    QLabel {{ background: transparent; }}
    QLabel[role="brand"] {{ font-size: 16px; font-weight: 700; letter-spacing: 0.4px; }}
    QLabel[role="sub"] {{ color: {SUB}; font-size: 12px; }}
    QLabel[role="muted"] {{ color: {SUB}; }}
    QLabel[role="title"] {{ font-size: 18px; font-weight: 700; }}
    QLabel[role="warn"] {{ color: {WARN}; font-size: 13px; }}
    QLabel[role="big"] {{ font-size: 18px; }}

    QPushButton {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 6px;
                   padding: 0 12px; min-height: 30px; color: {TEXT}; }}
    QPushButton:hover {{ background: {HOVER}; }}
    QPushButton:disabled {{ color: {MUTED}; }}
    QPushButton[kind="primary"] {{ background: {ACCENT}; border: none; color: #FFFFFF; }}
    QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton[kind="primary"]:disabled {{ background: {DISABLED}; color: #FFFFFF; }}
    QPushButton[kind="issue"] {{ background: #FFF4E5; border: 1px solid #F1C48A; color: {WARN};
        border-radius: 6px; padding: 2px 10px; font-size: 12px; min-height: 22px; }}
    QPushButton[kind="issue"][level="review"] {{ background: #F3F4F6; border: 1px solid #D1D5DB; color: {SUB}; }}
    QLabel[role="issue_need"] {{ color: {WARN}; font-size: 12px; }}
    QLabel[role="issue_review"] {{ color: {SUB}; font-size: 12px; }}
    QPushButton[kind="link"] {{ background: transparent; border: none; color: {ACCENT}; padding: 0 6px; font-size: 12px; }}
    QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {SUB}; padding: 0 8px; font-size: 12px; }}
    QPushButton[kind="ghost"]:checked {{ color: {TEXT}; font-weight: 700; }}
    QPushButton[kind="dashed"] {{ border: 1px dashed {LINE3}; color: {TEXT2}; }}
    QPushButton[kind="chip"] {{ border: 1px solid #C9D0DA; text-align: left; padding: 0 8px 0 10px; }}
    QPushButton[kind="seg"] {{ background: transparent; border: none; border-radius: 4px; color: {SUB}; min-height: 26px; }}
    QPushButton[kind="seg"]:checked {{ background: {PANEL}; color: {TEXT}; font-weight: 600; }}
    QFrame#Seg {{ background: {SOFT}; border-radius: 6px; }}
    QToolButton {{ background: transparent; border: none; color: {SUB}; padding: 2px; }}
    QToolButton:hover {{ color: {TEXT}; }}

    QLineEdit, QComboBox {{ background: {PANEL}; border: 1px solid {LINE2};
        border-radius: 4px; min-height: 30px; padding: 0 8px; color: {TEXT}; }}
    QComboBox {{ padding-right: 24px; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }}
    QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT}; selection-background-color: {HOVER};
        selection-color: {TEXT}; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}

    QTreeWidget, QListWidget, QTableView {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 4px;
        alternate-background-color: #FAFBFC; }}
    QTreeWidget::item, QListWidget::item {{ min-height: 26px; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{ background: {HOVER}; color: {TEXT}; }}
    QHeaderView::section {{ background: {SOFT}; color: {SUB}; border: none; border-bottom: 1px solid {LINE};
        padding: 4px 8px; font-size: 12px; }}
    QTableView {{ gridline-color: {LINE}; }}

    QTabWidget::pane {{ border: none; border-top: 1px solid {LINE}; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{ background: transparent; border: none; border-bottom: 2px solid transparent;
        padding: 8px 2px; margin-right: 20px; color: {SUB}; }}
    QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {TEXT}; font-weight: 600; }}

    QWidget#ResultPage {{ background: {PANEL}; }}
    QScrollArea#ResultScroll {{ background: {PANEL}; border: none; }}
    QFrame#Popup {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 6px; }}
    QProgressBar {{ background: {SOFT}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
    QPlainTextEdit#Code {{ background: {SOFT}; border: none; border-radius: 6px; }}

    QListWidget#Session {{ background: {CONSOLE_BG}; border: none; border-radius: 0; color: {CONSOLE_TEXT}; }}
    QListWidget#Session::item {{ min-height: 20px; padding: 0 4px; }}
    QListWidget#Session::item:selected {{ background: #222936; color: {CONSOLE_TEXT}; }}
    QFrame#SessionBox {{ background: {CONSOLE_BG}; }}
    QLineEdit#Command {{ background: transparent; border: none; color: #E6EBF2; }}
    QLabel#Prompt {{ color: {CONSOLE_TIME}; }}
    QSplitter::handle {{ background: {bg}; }}
    """
