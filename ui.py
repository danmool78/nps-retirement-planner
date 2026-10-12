"""
ui.py
=====
화면 꾸밈 전용 모듈: SVG 아이콘 세트 + 공통 CSS + 카드/섹션 헤더 컴포넌트.

- 이모티콘은 쓰지 않고, 모든 아이콘은 인라인 SVG(선 굵기 1.75, currentColor)로 그린다.
- 탭·버튼·익스팬더 라벨처럼 HTML 을 넣을 수 없는 곳은 텍스트만 쓴다.
- 레이아웃은 CSS grid(auto-fit)로 짜서 좁은 화면(모바일)에서 자동으로 1~2열로 접힌다.
"""

from __future__ import annotations

import copy
import html
import time

import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# SVG 아이콘 (24x24, stroke 기반) — path 조각만 저장하고 svg() 가 감싼다.
# ---------------------------------------------------------------------------
_PATHS = {
    # 부부(두 사람)
    "couple": '<circle cx="9" cy="8" r="3.2"/><circle cx="16.5" cy="9" r="2.6"/>'
              '<path d="M3.5 19.5c0-3.2 2.5-5.5 5.5-5.5s5.5 2.3 5.5 5.5"/>'
              '<path d="M15 14.2c.5-.1 1-.2 1.5-.2 2.5 0 4.5 2 4.5 4.8"/>',
    # 지갑(생활·자산)
    "wallet": '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3"/>'
              '<rect x="4" y="8" width="16.5" height="11" rx="2.2"/>'
              '<path d="M16 13.5h2"/>',
    # 집(주택연금)
    "home": '<path d="M4 10.5 12 4l8 6.5"/><path d="M6 9v10.5h12V9"/>'
            '<path d="M10 19.5v-5h4v5"/>',
    # 슬라이더(고급 설정)
    "sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/>'
               '<circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    # 방패(안정형)
    "shield": '<path d="M12 3.5 19 6v5.5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9V6z"/>'
              '<path d="m9 12 2 2 4-4"/>',
    # 상승 추세(총수령액 극대화형)
    "trend": '<path d="M3.5 17.5 9.5 11.5l4 4 7-7.5"/><path d="M15 8h5.5v5.5"/>',
    # 선물(상속중시형)
    "gift": '<rect x="4" y="9" width="16" height="4" rx="1"/>'
            '<path d="M5.5 13v7h13v-7M12 9v11"/>'
            '<path d="M12 9c-1.5-3.5-5.5-4-5.5-1.5S9.5 9 12 9zM12 9c1.5-3.5 5.5-4 5.5-1.5S14.5 9 12 9z"/>',
    # 트로피(추천)
    "trophy": '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4"/>'
              '<path d="M12 13v3.5M8.5 20h7M9.5 20l.5-3.5h4l.5 3.5"/>',
    # 온도계(물가)
    "thermo": '<path d="M10 14.5V5a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z"/><path d="M12 9v7"/>',
    # 파동(변동성)
    "pulse": '<path d="M3 12h3.5l2.5-6 4 12 2.5-6H21"/>',
    # 막대그래프
    "chart": '<path d="M4 20h16"/><rect x="6" y="11" width="3" height="7" rx=".6"/>'
             '<rect x="10.5" y="6" width="3" height="12" rx=".6"/><rect x="15" y="13.5" width="3" height="4.5" rx=".6"/>',
    # 동전 더미(수입·연금)
    "coins": '<ellipse cx="9" cy="7" rx="5" ry="2.2"/><path d="M4 7v4c0 1.2 2.2 2.2 5 2.2s5-1 5-2.2V7"/>'
             '<path d="M10 15.6c.8.4 2 .6 3.5.6 2.8 0 5-1 5-2.2v-4c0-1.2-2.2-2.2-5-2.2"/>'
             '<path d="M18.5 14v4c0 1.2-2.2 2.2-5 2.2-1.6 0-3-.3-4-.8"/>',
    # 다운로드
    "download": '<path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M5 19.5h14"/>',
    # 정보
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/>',
    # 경고(삼각형)
    "alert": '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4.5"/><circle cx="12" cy="17" r=".6" fill="currentColor"/>',
    # 체크(원)
    "check": '<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.6 5-5.4"/>',
    # 엑스(원)
    "cross": '<circle cx="12" cy="12" r="8.5"/><path d="m9.2 9.2 5.6 5.6M14.8 9.2l-5.6 5.6"/>',
    # 달력(나이·시점)
    "calendar": '<rect x="4" y="5.5" width="16" height="14" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    # 과녁(목표·최적)
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    # 저울(비교)
    "scale": '<path d="M12 4v16M7 20h10M5 7h14"/><path d="m5 7-2.5 6a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z"/>',
    # 책(읽는 법)
    "book": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 0 4 20.5z"/>'
            '<path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5a1.5 1.5 0 0 1 1.5 1.5z"/>',
    # 브라우저(로컬 계산)
    "browser": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 8.5h17"/>'
               '<circle cx="6.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="6.5" r=".5" fill="currentColor"/>'
               '<path d="m9.5 13 2 2-2 2M13.5 17h3"/>',
    # 링크(공유)
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2"/>'
            '<path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/>',
    # 되돌리기(초기화)
    "reset": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4.5h4.5"/>',
    # 자물쇠(개인정보)
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
}


def svg(name: str, size: int = 20, color: str = "currentColor", stroke: float = 1.75) -> str:
    """이름에 해당하는 인라인 SVG 문자열."""
    return (f'<svg class="ic" xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_PATHS[name]}</svg>')


# 아이콘 원본(앱 로고) — 동전 위 상승 곡선.
LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">'
        '<rect width="44" height="44" rx="12" fill="#1D4ED8"/>'
        '<path d="M10 29.5 17 22.5l5 5 11-12" fill="none" stroke="#fff" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M26.5 15.5H33V22" fill="none" stroke="#93C5FD" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')


# ---------------------------------------------------------------------------
# 공통 CSS
# ---------------------------------------------------------------------------
_CSS = """
<style>
/* Pretendard: 한글·숫자 모두 또렷한 UI 글꼴(가변 굵기, 필요한 글자만 내려받는 subset) */
@import url('https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css');
:root{
  --ink:#0F172A; --ink2:#334155; --muted:#64748B; --line:#E2E8F0; --soft:#F8FAFC;
  --brand:#1D4ED8; --brand-soft:#EFF6FF; --good:#059669; --good-soft:#ECFDF5;
  --bad:#DC2626; --bad-soft:#FEF2F2; --warn:#B45309; --warn-soft:#FFFBEB;
}
/* 아이콘 폰트(Material Symbols)는 건드리지 않도록 본문 텍스트 요소에만 글꼴 지정 */
.stApp, .stMarkdown, .stMarkdown p, label, input, textarea,
.stTabs button[role="tab"] p, .stButton button p, .stDownloadButton button p{
  font-family:'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
}
/* 숫자는 고정폭(tabular)으로 맞춰 자릿수가 흔들리지 않게 */
.kcard .val, .rank .score, .rank .facts, table.bd td, .stApp input{
  font-variant-numeric:tabular-nums; font-feature-settings:'tnum' 1, 'ss06' 1;
}

/* 입력창: 사이드바 배경을 한 톤 어둡게, 입력 칸은 흰 바탕 + 회색 테두리, 포커스 시 파란 테두리 */
[data-testid="stSidebar"]{background:#EEF2F7 !important;}
[data-testid="stSidebar"] hr{border-color:#D5DDE8;}
[data-testid="stNumberInputContainer"], [data-testid="stSelectbox"] > div:last-child > div,
[data-testid="stTextInputRootElement"]{
  background:#FFFFFF !important; border:1px solid #C3CEDD !important; border-radius:10px !important;
  box-shadow:0 1px 1px rgba(15,23,42,.04);
}
[data-testid="stNumberInputContainer"]:focus-within, [data-testid="stSelectbox"] > div:last-child > div:focus-within,
[data-testid="stTextInputRootElement"]:focus-within{
  border-color:#1D4ED8 !important; box-shadow:0 0 0 3px rgba(29,78,216,.15);
}
[data-testid="stNumberInputField"]{font-weight:600; color:#0F172A;}
[data-testid="stSidebar"] [data-testid="stExpander"] details{background:#F8FAFC; border:1px solid #D5DDE8; border-radius:12px;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{color:#334155; font-weight:500;}

/* 계산 중 로딩 화면 */
.loading{display:flex; flex-direction:column; align-items:center; gap:14px; padding:56px 16px;
         border:1px solid var(--line); border-radius:16px; background:linear-gradient(180deg,#F5F9FF,#fff); margin:1rem 0;}
.loading .ring{width:46px; height:46px; border-radius:50%; border:4px solid #DBEAFE; border-top-color:var(--brand);
               animation:spin .9s linear infinite;}
.loading b{font-size:1.02rem; color:var(--ink);}
.loading p{margin:0; font-size:.86rem; color:var(--muted); text-align:center; line-height:1.6;}
.loading .bar{width:min(260px,70%); height:4px; border-radius:4px; background:#E2E8F0; overflow:hidden;}
.loading .bar i{display:block; height:100%; width:40%; background:var(--brand); border-radius:4px; animation:slide 1.3s ease-in-out infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
@keyframes slide{0%{transform:translateX(-100%);} 100%{transform:translateX(250%);}}
@media (prefers-reduced-motion: reduce){ .loading .ring{animation-duration:2.4s;} .loading .bar i{animation:none; width:100%;} }
/* 계산이 도는 동안 Streamlit 은 이전 결과를 흐리게 남겨두는데, 로딩 화면이 떠 있는 동안에는
   이전 결과를 숨기고 로딩 화면만 선명하게 보여준다. */
[data-stale="true"]:has(.loading){opacity:1 !important; filter:none !important;}
[data-testid="stMain"]:has(.loading) [data-stale="true"]:not(:has(.loading)){display:none !important;}
.block-container{padding-top:3.5rem; padding-bottom:4rem; max-width:1280px;}
svg.ic{vertical-align:-0.2em; flex:none;}

/* 히어로 */
.hero{display:flex; gap:14px; align-items:center; margin:0 0 6px;}
.hero > svg{flex:none;}
.hero h1{font-size:1.65rem; margin:0; padding:0; color:var(--ink); font-weight:700; letter-spacing:-.02em;}
.hero p{margin:2px 0 0; color:var(--muted); font-size:.92rem;}

/* 섹션 헤더 */
.sec{display:flex; align-items:center; gap:10px; margin:1.6rem 0 .6rem;}
.sec .bub{width:34px; height:34px; border-radius:10px; display:grid; place-items:center;
          background:var(--brand-soft); color:var(--brand); flex:none;}
.sec h3{margin:0; padding:0; font-size:1.15rem; color:var(--ink); font-weight:700;}
.sec p{margin:0; color:var(--muted); font-size:.85rem;}
.side-h{display:flex; align-items:center; gap:8px; font-weight:700; color:var(--ink);
        font-size:.95rem; margin:.4rem 0 .2rem;}
.side-h svg{color:var(--brand);}

/* 한눈에 보는 결론 */
.concl{border:1px solid #BFDBFE; background:linear-gradient(180deg,#EFF6FF,#FFFFFF 70%); border-radius:16px;
       padding:16px 18px; margin:.6rem 0 .4rem; box-shadow:0 1px 2px rgba(15,23,42,.04);}
.concl-h{display:flex; align-items:center; gap:8px; color:var(--brand); font-weight:700; font-size:.88rem; margin-bottom:8px;}
.concl p{margin:0 0 6px; color:var(--ink2); font-size:.95rem; line-height:1.7; word-break:keep-all;}
.concl p:first-of-type{color:var(--ink); font-size:1.05rem;}
.concl p:last-child{margin-bottom:0;}
.concl b{color:var(--ink);}

/* 지표 카드 그리드 */
.kgrid{display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:.4rem 0 .8rem;}
.kcard{background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px;
       box-shadow:0 1px 2px rgba(15,23,42,.04);}
.kcard .lab{display:flex; align-items:center; gap:7px; color:var(--muted); font-size:.8rem; font-weight:500;}
.kcard .val{font-size:1.35rem; font-weight:700; color:var(--ink); margin-top:6px; letter-spacing:-.01em;}
.kcard .sub{font-size:.78rem; color:var(--muted); margin-top:3px; line-height:1.4;}
.kcard.good .lab svg{color:var(--good);} .kcard.bad .lab svg{color:var(--bad);}
.kcard.warn .lab svg{color:var(--warn);} .kcard.brand .lab svg{color:var(--brand);}
.kcard.hl{border-color:#BFDBFE; background:linear-gradient(180deg,#F5F9FF,#fff);}

/* 알림 배너 */
.note{display:flex; gap:10px; align-items:flex-start; border-radius:12px; padding:12px 14px;
      font-size:.88rem; line-height:1.55; margin:.4rem 0 .6rem; border:1px solid;}
.note svg{margin-top:2px;}
.note.info{background:var(--brand-soft); border-color:#BFDBFE; color:#1E3A8A;}
.note.good{background:var(--good-soft); border-color:#A7F3D0; color:#065F46;}
.note.warn{background:var(--warn-soft); border-color:#FDE68A; color:#78350F;}
.note.bad{background:var(--bad-soft); border-color:#FECACA; color:#7F1D1D;}

/* 추천 전략 순위 카드 */
.rank{display:grid; grid-template-columns:auto 1fr; gap:14px; border:1px solid var(--line);
      border-radius:14px; padding:14px 16px; margin:0 0 10px; background:#fff;}
.rank.first{border-color:#93C5FD; box-shadow:0 0 0 3px rgba(29,78,216,.07);}
.rank .no{width:36px; height:36px; border-radius:50%; display:grid; place-items:center;
          font-weight:700; background:var(--soft); color:var(--ink2); border:1px solid var(--line);}
.rank.first .no{background:var(--brand); color:#fff; border-color:var(--brand);}
.rank .top{display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 14px;}
.rank .title{font-weight:700; color:var(--ink); font-size:1rem;}
.rank .score{font-size:.8rem; color:var(--brand); background:var(--brand-soft);
             padding:2px 8px; border-radius:999px; font-weight:500;}
.rank .facts{display:flex; flex-wrap:wrap; gap:4px 16px; color:var(--ink2); font-size:.86rem; margin-top:6px;}
.rank .facts span{white-space:nowrap;}
.rank .facts b{font-weight:500; color:var(--muted); margin-right:4px;}
.rank ul{list-style:none; margin:8px 0 0; padding:0; display:flex; flex-wrap:wrap; gap:6px;}
.rank li{display:flex; align-items:center; gap:5px; font-size:.8rem; padding:3px 9px 3px 7px;
         border-radius:999px; line-height:1.4;}
.rank li.pro{background:var(--good-soft); color:#065F46;}
.rank li.con{background:var(--bad-soft); color:#991B1B;}

/* 시작 화면 단계 카드 */
.steps{display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:.8rem 0;}
.step{border:1px solid var(--line); border-radius:14px; padding:16px; background:#fff;}
.step .n{font-size:.75rem; font-weight:700; color:var(--brand); letter-spacing:.05em;}
.step h4{margin:6px 0 4px; font-size:1rem; color:var(--ink); padding:0; display:flex; gap:8px; align-items:center;}
.step h4 svg{color:var(--brand);}
.step p{margin:0; font-size:.85rem; color:var(--muted); line-height:1.55;}

/* 월수입 구성표 */
.tbl-wrap{overflow-x:auto; border:1px solid var(--line); border-radius:12px; margin:.4rem 0 .6rem;}
table.bd{border-collapse:collapse; width:100%; font-size:.88rem; min-width:420px;}
table.bd th, table.bd td{padding:9px 12px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap;}
table.bd thead th{background:var(--soft); color:var(--muted); font-weight:500;}
table.bd tbody th{text-align:left; font-weight:500; color:var(--ink2);}
table.bd tr.total th, table.bd tr.total td{font-weight:700; color:var(--ink); background:var(--brand-soft); border-bottom:none;}
/* 제도 기준표(사이드바) */
table.pol{border-collapse:collapse; width:100%; font-size:.78rem;}
table.pol th, table.pol td{padding:6px 4px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left;}
table.pol th{font-weight:500; color:var(--muted); width:46%;}
table.pol .sm{color:var(--muted); font-size:.72rem;}
/* 표 */
.stTable table{font-size:.86rem;}

/* 탭: 모바일에서 가로 스크롤 가능하게 */
.stTabs [data-baseweb="tab-list"], .stTabs [role="tablist"]{gap:18px; overflow-x:auto; flex-wrap:nowrap;}
.stTabs button[role="tab"]{white-space:nowrap; font-weight:500;}

/* 그래프 제목(plotly 제목 대신 HTML 로 그려 좁은 화면에서도 자연스럽게 줄바꿈) */
.chart-h{font-size:.98rem; font-weight:700; color:var(--ink); margin:.6rem 0 0; line-height:1.4;}

/* 모바일 전용 버튼(입력창 열기)은 넓은 화면에서 숨김 */
.st-key-open_inputs, .st-key-open_inputs2{display:none;}
/* 스크립트 실행용 0px 컴포넌트가 여백을 만들지 않도록 */
.element-container:has(iframe[height="1"]), .stElementContainer:has(iframe[height="1"]){display:none;}

/* 모바일 */
@media (max-width: 640px){
  .block-container{padding-left:.9rem; padding-right:.9rem; padding-top:3.2rem;}
  .hero{gap:10px; align-items:flex-start;}
  .hero > svg{width:34px; height:34px; margin-top:2px;}
  .hero h1{font-size:1.12rem; line-height:1.35; word-break:keep-all;}
  .hero p{font-size:.8rem;}
  .sec{margin:1.1rem 0 .5rem; gap:8px;}
  .sec .bub{width:30px; height:30px; border-radius:9px;}
  .sec h3{font-size:1.02rem;}
  .sec p{font-size:.78rem;}
  .kgrid{grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px;}
  .kcard{padding:10px 11px; border-radius:12px;}
  .kcard .lab{font-size:.74rem; gap:5px;}
  .kcard .val{font-size:1.08rem; margin-top:4px;}
  .kcard .sub{font-size:.7rem;}
  .note{font-size:.82rem; padding:10px 12px;}
  .concl{padding:13px 14px;}
  .concl p{font-size:.88rem; line-height:1.65;}
  .concl p:first-of-type{font-size:.96rem;}
  .rank{grid-template-columns:1fr; gap:6px; padding:12px;}
  .rank .no{width:28px; height:28px; font-size:.85rem;}
  .rank .title{font-size:.93rem;}
  .rank .facts{font-size:.8rem; gap:2px 12px;}
  .rank li{font-size:.74rem;}
  .steps{gap:8px;}
  .step{padding:12px 14px;}
  .step h4{font-size:.95rem;}
  .step p{font-size:.8rem;}
  table.bd{font-size:.8rem;}
  table.bd th, table.bd td{padding:7px 9px;}
  .chart-h{font-size:.9rem;}
  .stTabs [role="tablist"]{gap:14px;}
  .stTabs button[role="tab"] p{font-size:.88rem;}
  /* iOS 는 16px 미만 입력칸에 포커스하면 화면을 확대하므로 16px 로 고정 */
  input, select, textarea, [data-baseweb="select"] div{font-size:16px !important;}
  .st-key-open_inputs, .st-key-open_inputs2{display:block;}
  /* 주요 버튼은 손가락으로 누르기 쉽게 꽉 차게 */
  .st-key-run_main, .st-key-run_again, .st-key-open_inputs, .st-key-open_inputs2,
  .st-key-run_main .stButton, .st-key-run_again .stButton, .st-key-open_inputs .stButton,
  .st-key-open_inputs2 .stButton, .st-key-run_main button, .st-key-run_again button,
  .st-key-open_inputs button, .st-key-open_inputs2 button{width:100% !important;}
  .st-key-run_main button, .st-key-run_again button, .st-key-open_inputs button,
  .st-key-open_inputs2 button{min-height:46px;}
  /* 터치 기기에선 plotly 도구모음이 항상 떠서 그래프를 가리므로 숨김 */
  .modebar-container{display:none !important;}
}
</style>
"""


def loading(target=st):
    """계산 중 로딩 화면(CSS 애니메이션이라 계산으로 Python 이 멈춰 있어도 계속 돈다)."""
    _html('<div class="loading"><div class="ring"></div><b>시뮬레이션 계산 중</b>'
          '<p>모든 수령나이·주택연금 조합을 물가 스트레스와 몬테카를로까지 포함해 평가하고 있습니다.<br>'
          '기기 성능에 따라 수 초~수십 초 걸립니다.</p><div class="bar"><i></i></div></div>', target)


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 컴포넌트
# ---------------------------------------------------------------------------
def _html(s: str, target=st):
    target.markdown(s, unsafe_allow_html=True)


def hero(title: str, subtitle: str):
    _html(f'<div class="hero">{LOGO}<div><h1>{html.escape(title)}</h1>'
          f'<p>{html.escape(subtitle)}</p></div></div>')


def section(icon: str, title: str, subtitle: str = "", target=st):
    sub = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    _html(f'<div class="sec"><div class="bub">{svg(icon, 19)}</div>'
          f'<div><h3>{html.escape(title)}</h3>{sub}</div></div>', target)


def side_header(icon: str, title: str):
    _html(f'<div class="side-h">{svg(icon, 18)}<span>{html.escape(title)}</span></div>', st.sidebar)


def note(kind: str, text_html: str, target=st):
    """kind: info / good / warn / bad. text_html 은 신뢰된(코드에서 만든) HTML."""
    icon = {"info": "info", "good": "check", "warn": "alert", "bad": "alert"}[kind]
    _html(f'<div class="note {kind}">{svg(icon, 18)}<div>{text_html}</div></div>', target)


def conclusion(body_html: str, target=st):
    """결과 맨 위 '한눈에 보는 결론' 카드. body_html 은 코드에서 만든 <p> 문단들."""
    _html(f'<div class="concl"><div class="concl-h">{svg("target", 18)}<span>한눈에 보는 결론</span></div>'
          f'{body_html}</div>', target)


def kpi(icon: str, label: str, value: str, sub: str = "", tone: str = "brand", highlight=False) -> str:
    """지표 카드 HTML 한 장(kpi_grid 로 묶어서 출력)."""
    cls = f"kcard {tone}" + (" hl" if highlight else "")
    sub_html = f'<div class="sub">{html.escape(sub)}</div>' if sub else ""
    return (f'<div class="{cls}"><div class="lab">{svg(icon, 16)}<span>{html.escape(label)}</span></div>'
            f'<div class="val">{html.escape(value)}</div>{sub_html}</div>')


def kpi_grid(cards, target=st):
    _html(f'<div class="kgrid">{"".join(cards)}</div>', target)


def rank_card(no: int, title: str, score: str, facts, pros, cons) -> str:
    """추천 전략 순위 카드. facts=[(라벨, 값)], pros/cons=문자열 리스트."""
    cls = "rank first" if no == 1 else "rank"
    facts_html = "".join(f"<span><b>{html.escape(k)}</b>{html.escape(v)}</span>" for k, v in facts)
    items = "".join(f'<li class="pro">{svg("check", 14)}{html.escape(p)}</li>' for p in pros)
    items += "".join(f'<li class="con">{svg("cross", 14)}{html.escape(c)}</li>' for c in cons)
    return (f'<div class="{cls}"><div class="no">{no}</div><div>'
            f'<div class="top"><span class="title">{html.escape(title)}</span>'
            f'<span class="score">{html.escape(score)}</span></div>'
            f'<div class="facts">{facts_html}</div><ul>{items}</ul></div></div>')


def steps(items):
    """시작 화면 단계 카드. items=[(아이콘, 제목, 설명)]"""
    cards = "".join(
        f'<div class="step"><div class="n">STEP {i}</div><h4>{svg(ic, 18)}{html.escape(t)}</h4>'
        f'<p>{html.escape(d)}</p></div>'
        for i, (ic, t, d) in enumerate(items, 1))
    _html(f'<div class="steps">{cards}</div>')


# plotly 차트 공통 옵션. 휠·드래그 확대를 꺼서 모바일에서 손가락으로 화면을 스크롤할 때
# 그래프가 터치를 가로채지 않게 한다(탭하면 값 표시는 그대로 됨).
PLOTLY_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": False,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d",
                                            "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d"]}


def chart(fig, target=st):
    """그래프 제목은 HTML 로 따로 그리고(줄바꿈 가능), 화면용 사본은 제목 여백을 줄인다.
    원본 fig 는 리포트(HTML 내보내기)에서 제목째로 쓰이므로 건드리지 않는다."""
    title = fig.layout.title.text or ""
    view = copy.deepcopy(fig)
    view.update_layout(title=None, margin=dict(t=16), dragmode=False)
    if title:
        _html(f'<div class="chart-h">{html.escape(title)}</div>', target)
    target.plotly_chart(view, width="stretch", config=PLOTLY_CONFIG)


# ---------------------------------------------------------------------------
# 사이드바(입력창) 제어 — 모바일에서는 사이드바가 화면 전체를 덮으므로
# 실행 후 자동으로 닫고, 본문 버튼으로 열 수 있게 한다. (스크립트는 같은 출처 iframe 에서 부모 문서를 조작)
# ---------------------------------------------------------------------------
_SIDEBAR_JS = """
<script>
(function(){
  const doc = window.parent.document;
  const action = "%s";
  const mobile = window.parent.innerWidth <= 768;
  const sb = doc.querySelector('[data-testid="stSidebar"]');
  const expanded = sb && sb.getAttribute("aria-expanded") === "true";
  const pick = (sel) => { const el = doc.querySelector(sel); return el && (el.tagName === "BUTTON" ? el : el.querySelector("button")); };
  if (action === "close" && mobile && expanded) {
    const b = pick('[data-testid="stSidebarCollapseButton"]'); if (b) b.click();
  }
  if (action === "open" && !expanded) {
    const b = pick('[data-testid="stExpandSidebarButton"]') || pick('[data-testid="stSidebarCollapsedControl"]');
    if (b) b.click();
  }
  if (action === "close" && mobile) {
    const main = doc.querySelector('[data-testid="stMain"]') || doc.querySelector('section.main');
    if (main) main.scrollTo({top: 0}); window.parent.scrollTo({top: 0});
  }
})();
</script>
"""


def _frame(code: str, height: int = 1, target=st):
    """같은 출처 iframe 으로 HTML/스크립트를 넣는다. height=1 이면 CSS 로 자리를 숨긴다.
    최신 Streamlit 은 st.iframe, 브라우저 실행(stlite) 쪽 구버전은 components.html 을 쓴다."""
    if hasattr(st, "iframe"):
        target.iframe(code, height=height)
    else:
        with target:
            components.html(code, height=height)


def sidebar_action(action: str):
    """'open' / 'close'(모바일 폭에서만). 매번 다른 내용으로 렌더해 스크립트가 다시 실행되게 한다."""
    _frame(_SIDEBAR_JS % action + f"<!-- {time.time()} -->")


_URL_JS = """
<script>
(function(){
  const w = window.parent;
  const want = %s;
  const cur = w.location.search;
  if (cur !== want) w.history.replaceState(w.history.state, "", w.location.pathname + want + w.location.hash);
})();
</script>
"""


def sync_url(query: str):
    """현재 입력을 주소창 URL 에 반영(새로고침 유지·링크 공유용). 내용이 같으면 다시 실행되지 않는다."""
    import json
    _frame(_URL_JS % json.dumps(("?" + query) if query else ""))


_SHARE_HTML = """
<style>
  html,body{margin:0;background:transparent;font-family:'Pretendard Variable',Pretendard,-apple-system,sans-serif;}
  button{width:100%%;height:40px;border-radius:10px;border:1px solid #C3CEDD;background:#fff;color:#0F172A;
         font:inherit;font-size:14px;font-weight:500;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;}
  button:hover{border-color:#1D4ED8;color:#1D4ED8;}
  button.ok{border-color:#059669;color:#059669;}
</style>
<button id="b" type="button">%s<span id="t">링크 복사</span></button>
<script>
  const b = document.getElementById("b"), t = document.getElementById("t");
  b.onclick = async () => {
    const url = window.parent.location.href;
    let ok = false;
    try { await navigator.clipboard.writeText(url); ok = true; } catch (e) {}
    if (!ok) {
      try {   // 클립보드 권한이 없으면 부모 문서에 임시 입력칸을 만들어 복사
        const d = window.parent.document, a = d.createElement("textarea");
        a.value = url; a.style.position = "fixed"; a.style.opacity = "0"; d.body.appendChild(a);
        a.select(); ok = d.execCommand("copy"); d.body.removeChild(a);
      } catch (e) {}
    }
    if (!ok) { window.parent.prompt("아래 링크를 복사하세요", url); ok = true; }
    b.classList.add("ok"); t.textContent = "복사됨";
    setTimeout(() => { b.classList.remove("ok"); t.textContent = "링크 복사"; }, 1800);
  };
</script>
"""


def share_button(target=st):
    """현재 입력이 담긴 주소를 복사하는 버튼(받은 사람이 열면 같은 입력으로 시작)."""
    _frame(_SHARE_HTML % svg("link", 16), height=42, target=target)
