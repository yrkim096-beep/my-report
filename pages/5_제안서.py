# -*- coding: utf-8 -*-
"""제안서 — 결정을 요청하는 문서. 리포트와는 다른 독립 메뉴다.

9주차 Day3. 주제를 고르면 그 주제로 절 전체가 조립된다.
계산 과정·함수 이름·컬럼 이름은 화면에 넣지 않는다 — 읽는 사람은 결정 권한을
가진 사람이지, 이 앱을 만든 사람이 아니다.
"""
from datetime import datetime

import streamlit as st

from core import config as C, load, metrics as M
from report import proposal as P, sections as S
from viz import ui

st.set_page_config(page_title="제안서", page_icon="📝", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None
if "proposal_human" not in st.session_state:
    st.session_state.proposal_human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '제안서</div>'
            '<div style="color:#64748b;font-size:13px;margin-bottom:18px">'
            '"이 문서를 읽은 팀장이 오늘 안에 결정을 내릴 수 있는가?"</div>',
            unsafe_allow_html=True)

topics = M.proposal_topics(t)
cards = P.parse_cards()

ui.section("주제 선택", "후보를 전부 뽑아 놓고 고른다 — 기각된 것도 남긴다")
labels = []
for x in topics:
    tag = "" if not x["기각사유"] else " (기각)"
    labels.append(f"{x['제목']} — 연 {x['규모_연간건수']:,.1f}건{tag}")
label_to_key = dict(zip(labels, [x["키"] for x in topics]))

pick_label = st.selectbox("주제", labels)
topic_key = label_to_key[pick_label]
topic = next(x for x in topics if x["키"] == topic_key)

if topic["기각사유"]:
    ui.callout(f"이 주제는 기각 후보다 — {topic['기각사유']}", "info")

st.caption(f"근거 요약 — {topic['한줄']}")

psecs = P.build(t, topic_key, cards, st.session_state.proposal_human)

ui.section("조립된 문서")
pnav, pbody = st.columns([1, 3.4])
with pnav:
    ptitles = [s["title"] for s in psecs]
    ppick = st.radio("목차", ptitles, label_visibility="collapsed", key=f"nav_{topic_key}")

psec = next(s for s in psecs if s["title"] == ppick)

with pbody:
    pkind = {"auto": "자동 생성", "human": "사람 작성"}[psec["kind"]]
    plvl = "ok" if psec["kind"] == "auto" or psec["body"].strip() else "warn"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{psec["title"]}</div>'
        f'{ui.badge(plvl, pkind)}</div>', unsafe_allow_html=True)

    if psec["kind"] == "auto":
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">{psec["body"]}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(psec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")
        if psec.get("svg"):
            st.markdown(f'<div class="card">{psec["svg"]}</div>', unsafe_allow_html=True)
    else:
        if psec["title"] == "6. 무엇을 결정해 주셔야 합니까":
            st.caption("자동으로 붙는 것 — 규모·선택지·미룰 때의 누적치")
            for ln in psec.get("auto_lines", []):
                st.markdown(f"- {ln}")
        st.caption(psec["placeholder"])
        key = f"ph_{topic_key}_{psec['title']}"
        ptxt = st.text_area("본문", value=psec["body"], height=200,
                            key=key, label_visibility="collapsed")
        if st.button("저장", key=f"save_{key}", type="primary"):
            st.session_state.proposal_human[psec["title"]] = ptxt
            st.rerun()
        if psec["body"].strip():
            bad = S.check_phrasing(psec["body"])
            if bad:
                ui.callout(f"인과를 단정하는 표현이 있습니다: <b>{', '.join(bad)}</b>.")
            else:
                st.caption("✓ 인과 단정 표현 검사 통과")

st.divider()
ui.section("내보내기")
phtml = P.to_html(psecs, {
    "title": topic["제목"],
    "dataset": C.DATASET,
    "period": f"{C.PERIOD[0]}~{C.PERIOD[1]}",
    "date": datetime.now().strftime("%Y-%m-%d"),
})
st.download_button("제안서 HTML 내려받기", phtml,
                   file_name=f"제안서_{topic['키']}.html", mime="text/html")
st.caption("파일 하나로 열립니다. 브라우저 인쇄 미리보기 → PDF 저장으로 A4 문서를 받을 수 있습니다.")
