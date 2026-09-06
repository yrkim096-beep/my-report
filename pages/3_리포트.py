# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M
from report import sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "human" not in st.session_state:
    st.session_state.human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

if "limit_rows" not in st.session_state:
    st.session_state.limit_rows = S.default_limit_rows(t)
    st.session_state.limit_rows_original = [dict(r) for r in st.session_state.limit_rows]

secs = S.build(t, st.session_state.human, st.session_state.limit_rows)

# 리포트 차트에 쓸 분해 축 — 손을 쓸 수 있는 두 축(담당자·유입채널) 중
# 첫 번째. funnel_by()/M.DIM_SOURCE 와 이름을 맞춘다(Day3 실습 A).
DIM = next(iter(M.DIM_SOURCE))

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '리포트</div>', unsafe_allow_html=True)

nav, body = st.columns([1, 3.4])

with nav:
    titles = [s["title"] for s in secs]
    pick = st.radio("목차", titles, label_visibility="collapsed")
    st.divider()
    done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
    need = sum(1 for s in secs if s["kind"] == "human")
    left = sum(1 for s in secs if s["kind"] == "todo")
    st.caption(f"사람 작성 {done}/{need}장")
    st.progress(done / need if need else 0)
    if left:
        st.caption(f"아직 안 만든 장 {left}개")

sec = next(s for s in secs if s["title"] == pick)

with body:
    kind = {"auto": "자동 생성", "human": "사람 작성",
            "todo": "아직 안 만듦"}[sec["kind"]]
    lvl = {"auto": "ok", "todo": "none"}.get(
        sec["kind"], "ok" if sec["body"].strip() else "warn")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
        f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["kind"] == "auto":
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">{sec["body"]}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(sec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                       f"주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")

        if "funnel" in sec.get("charts", []):
            f = M.funnel(t)
            st.image(pdf_charts.funnel_png(f), width="stretch")
        if "device" in sec.get("charts", []):
            f = M.funnel(t)
            bn = f[f.is_bottleneck].iloc[0]
            bi = max(int(f.index[f.label == bn.label][0]), 1)
            g = M.funnel_by(t, DIM, f.step.iloc[bi - 1], f.step.iloc[bi])
            g = g[g.믿음]  # 표본 미달 칸은 차트에도 안 보여준다
            if len(g):
                st.image(pdf_charts.device_png(g), width="stretch")
        if "experiments" in sec.get("charts", []):
            st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                     width="stretch")

        if sec["title"] == "7. 한계":
            st.divider()
            st.caption("표에서 직접 고치거나 행을 더할 수 있습니다. "
                       "'포함'을 끄면 리포트 본문에서 빠집니다.")
            edited = st.data_editor(
                pd.DataFrame(st.session_state.limit_rows),
                column_config={
                    "출처": st.column_config.SelectboxColumn(
                        options=["검증 경고", "못 한 것", "찾았는데 없음"],
                        required=True),
                    "내용": st.column_config.TextColumn(required=True),
                    "포함": st.column_config.CheckboxColumn(default=True),
                },
                num_rows="dynamic", width="stretch", hide_index=True,
                key="limit_editor")
            new_rows = edited.to_dict("records")

            # ★ 검증 경고 행을 지웠으면 남긴다 — 검증에서 난 경고가
            #   한계 절에서 조용히 빠지면 그 경고는 사라진 것과 같다.
            orig_warn = {r["내용"] for r in st.session_state.limit_rows_original
                        if r["출처"] == "검증 경고"}
            cur_warn = {r.get("내용") for r in new_rows
                       if r.get("출처") == "검증 경고"}
            removed = orig_warn - cur_warn
            if removed:
                ui.callout("검증 경고를 뺐습니다 — " + " / ".join(removed))

            if new_rows != st.session_state.limit_rows:
                st.session_state.limit_rows = new_rows
                st.rerun()
    else:
        HUMAN_SECS = [s for s in secs if s["kind"] == "human"]
        with st.form("사람이 쓰는 장"):
            for hs in HUMAN_SECS:
                st.text_area(
                    hs["title"], value=hs["body"], height=200,
                    placeholder=hs["placeholder"], key=f"form_{hs['title']}")
            submitted = st.form_submit_button("저장", type="primary")

        if submitted:
            problems = {}
            for hs in HUMAN_SECS:
                v = st.session_state[f"form_{hs['title']}"]
                st.session_state.human[hs["title"]] = v
                bad = S.check_phrasing(v)
                if bad:
                    problems[hs["title"]] = bad
            if problems:
                msg = " / ".join(f"{k} — {', '.join(v)}"
                                for k, v in problems.items())
                ui.callout(f"인과를 단정하는 표현이 있습니다: <b>{msg}</b>. "
                           f"저장은 했지만 관측 데이터로는 인과를 주장할 수 "
                           f"없습니다.")
            else:
                st.caption("✓ 저장했습니다. 인과 단정 표현 검사 통과")
            st.rerun()

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    if st.button("PDF 만들기", type="primary"):
        with st.status("리포트를 만드는 중", expanded=True) as box:
            try:
                st.write("장별 내용 모으는 중...")
                built = secs  # 이미 조립되어 있다 — 여기서 다시 모은다는 표시만

                st.write("차트 이미지 만드는 중...")
                f = M.funnel(t)
                bn = f[f.is_bottleneck].iloc[0]
                bi = max(int(f.index[f.label == bn.label][0]), 1)
                g = M.funnel_by(t, DIM, f.step.iloc[bi - 1], f.step.iloc[bi])
                g = g[g.믿음]  # 표본 미달 칸은 차트에도 안 보여준다
                charts = {"funnel": pdf_charts.funnel_png(f)}
                if len(g):
                    charts["device"] = pdf_charts.device_png(g)

                st.write("PDF 조립하는 중...")
                pdf = to_pdf.build_pdf(built, charts)
            except Exception as e:
                box.update(label="실패", state="error", expanded=True)
                st.write(f"실패: {e}")
                raise
            box.update(label="완성", state="complete", expanded=False)
        st.session_state.pdf = pdf
        st.session_state.pdf_made_at = datetime.now()
        st.toast("리포트가 만들어졌습니다", icon="📄")
    if st.session_state.get("pdf"):
        ts = st.session_state.pdf_made_at.strftime("%Y%m%d-%H%M%S")
        st.download_button("PDF 내려받기", st.session_state.pdf,
                           file_name=f"성장리포트_{C.PERIOD[0][:7]}_{ts}.pdf",
                           mime="application/pdf")

with c2:
    st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
    draft = S.email_draft(t, secs)
    st.text_input("받는 사람", draft["to"], disabled=True)
    st.text_input("제목", draft["subject"], disabled=True)
    with st.expander("본문 미리보기"):
        st.markdown(draft["html"], unsafe_allow_html=True)

    run = st.session_state.run
    if run and gates.is_passed(run, 2):
        st.markdown('<div class="gate final" style="margin-top:12px">'
                    '<div class="q">게이트 3 · 발송</div>'
                    '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                    '<b>되돌릴 수 없습니다.</b> 통과시키면 발송 기록이 남습니다.</div>'
                    '</div>', unsafe_allow_html=True)
        if gates.is_passed(run, 3):
            st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
        else:
            ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
            if st.button("확정", disabled=(ok != "발송")):
                gates.pass_gate(run, 3, "초안 확정 (실제 발송 없음)")
                gates.save(run)
                st.rerun()
    else:
        st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")
