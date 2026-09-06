# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
import datetime as dt

import streamlit as st

from core import config as C, load, metrics as M
from core.load import to_dt
from viz import charts, ui


def _month_options(dates) -> list[str]:
    """날짜 컬럼에서 실제로 데이터가 있는 월(YYYY-MM) 목록을 뽑는다."""
    return sorted(to_dt(dates).dropna().dt.strftime("%Y-%m").unique())


def _qp(key: str, options: list[str], fallback: str) -> str:
    """URL 쿼리 파라미터에서 값을 읽는다. 없거나 후보에 없으면 기본값 —
    에러를 내지 않고 조용히 떨어진다."""
    val = st.query_params.get(key)
    return val if val in options else fallback


@st.dialog("이 값을 왜 보여주지 않나")
def show_hidden_reason(condition: str, actual: str, fix: str) -> None:
    """감춰진 카드의 근거 모달. 조건 값만 보여준다 — 지표 값·증감·p값은 넣지 않는다."""
    st.table({"항목": ["걸린 조건", "실제 값", "믿으려면"],
              "내용": [condition, actual, fix]})

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '대시보드</div>', unsafe_allow_html=True)
# 확인용 — @st.fragment가 진짜 그 부분만 다시 그리는지 보려고 찍는다. 나중에 지운다.
st.caption(f"페이지 전체 렌더링 시각: {dt.datetime.now():%H:%M:%S}")

# ── 지표 카드 ─────────────────────────────────────────────────────
k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), "", lv),
                        unsafe_allow_html=True)
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

    # st.metric 버전 (비교용). ui.kpi_card 는 위에 그대로 둔다.
    st.caption("st.metric 버전 — 비교용")
    LEVEL_LABEL = {"ok": "정상", "warn": "경고", "block": "위험"}
    deltas = ui.guard(M.kpi_deltas, t) or {}
    cols2 = st.columns(len(k))
    for col, (name, v) in zip(cols2, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            d = deltas.get(name)
            delta = v["fmt"].format(d) if d is not None else None
            st.metric(
                label=name,
                value=v["fmt"].format(v["value"]),
                delta=delta,
                delta_color="inverse" if name in M.HIGHER_IS_WORSE else "normal",
                border=True,
            )
            th = C.THRESHOLDS.get(name)
            if th:
                st.caption(f"경고선 {v['fmt'].format(th['경고'])} / "
                           f"현재 {LEVEL_LABEL[lv]}")
            with st.popover("정의", width="stretch"):
                st.write(f"**계산식**  \n{M.KPI_DEFS.get(name, '(정의 없음)')}")
                reason = C.THRESHOLD_REASONS.get(name)
                if reason:
                    st.write(f"**임계값 근거**  \n{reason}")

# ── 획득 퍼널 / 유지 퍼널 ────────────────────────────────────────────
@st.fragment
def render_acquisition_funnel(t: dict, dim: str, start: str | None,
                              end: str | None) -> None:
    # 확인용 — 이 조각만 다시 그려지는지 보려고 찍는다. 나중에 지운다.
    st.caption(f"[획득 퍼널 조각] 렌더링 시각: {dt.datetime.now():%H:%M:%S}")

    leads = t["leads"]
    if start is None or end is None:
        st.caption("리드 데이터가 없습니다.")
        return

    lead_month = to_dt(leads.inquiry_date).dt.strftime("%Y-%m")
    sel_leads = leads[lead_month.between(start, end)]
    lead_ids = set(sel_leads.lead_id)
    sel_contracts = t["contracts"][t["contracts"].lead_id.isin(lead_ids)]
    ft = {
        "leads": sel_leads,
        "consultations": t["consultations"][t["consultations"].lead_id.isin(lead_ids)],
        "visits": t["visits"][t["visits"].lead_id.isin(lead_ids)],
        "contracts": sel_contracts,
        "rent_payments": t["rent_payments"][
            t["rent_payments"].contract_id.isin(set(sel_contracts.contract_id))],
    }

    f = ui.guard(M.funnel, ft)
    if f is None:
        return
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(charts.funnel_bars(f), width="stretch",
                        config={"displayModeBar": False})
        bn = f[f.is_bottleneck].iloc[0]
        bi = max(int(f.index[f.label == bn.label][0]), 1)
        prev = f.iloc[bi - 1]
        ui.callout(
            f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
            f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
            f"<b>{(1-bn.step_rate)*100:.1f}%가 이탈</b>합니다.")

    with right:
        # 분해 축 선택(담당자/유입채널)은 fragment 밖, 탭 위쪽으로 옮겼다 —
        # URL과 연결된 위젯을 fragment 안에 두면 조각만 다시 그려져 URL과
        # 화면이 어긋난다.
        i = st.selectbox(
            "구간", range(len(f) - 1),
            format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
            index=min(bi - 1, len(f) - 2), key="acq_gap")
        g = ui.guard(M.funnel_by, ft, dim, f.step.iloc[i], f.step.iloc[i + 1])
        if g is not None and len(g):
            st.plotly_chart(charts.device_compare(g), width="stretch",
                            config={"displayModeBar": False})
            name_col = g.columns[0]
            # 못 믿을 조건 분기 — config.DECOMPOSE_MIN_SAMPLE 미만인 칸은
            # 전환율 자체가 없다(NaN). 계산해 놓고 숨기는 게 아니라 값이 없다.
            reliable = g[g.믿음]
            excluded = g[~g.믿음]
            if len(reliable) >= 2:
                hi = reliable.loc[reliable.전환율.idxmax()]
                lo = reliable.loc[reliable.전환율.idxmin()]
                if hi[name_col] != lo[name_col]:
                    ui.callout(
                        f"<b>{lo[name_col]}</b>이(가) 전체의 "
                        f"<b>{lo.비중*100:.0f}%</b>인데 전환율은 "
                        f"<b>{lo.표시}</b>로 "
                        f"{hi[name_col]}({hi.표시})보다 낮습니다.")
            elif not len(reliable):
                st.caption(
                    f"모든 칸이 표본 부족(config.DECOMPOSE_MIN_SAMPLE="
                    f"{C.DECOMPOSE_MIN_SAMPLE}건 미만)이라 비교하지 않습니다. "
                    "실제 값: " + ", ".join(
                        f"{r[name_col]} {r.표시}" for _, r in g.iterrows()))
            for _, r in excluded.iterrows():
                # 색만으로 전달하지 않는다 — 배지(●▲✕○ + 글자)로 색맹도 읽게 한다.
                bcol, ccol = st.columns([5, 1])
                with bcol:
                    st.markdown(ui.badge("block", f"{r[name_col]} — {r.가림사유}"),
                               unsafe_allow_html=True)
                with ccol:
                    if st.button("왜 감췄나", key=f"why_{dim}_{i}_{r[name_col]}"):
                        show_hidden_reason(
                            condition=f"표본 부족 (config.DECOMPOSE_MIN_SAMPLE 미만)",
                            actual=r["가림사유"],
                            fix=f"이 칸의 도달 수가 {C.DECOMPOSE_MIN_SAMPLE}건 이상이 "
                                "되면 전환율을 계산합니다 — 기간을 늘리거나 더 굵게 묶으십시오.")

    # 차트는 위에 그대로 두고, 표로도 본다.
    disp = f[["label", "n", "step_rate", "cum_rate"]].rename(columns={
        "label": "단계", "n": "도달 수",
        "step_rate": "단계 전환율", "cum_rate": "누적 전환율",
    })
    for col in ("단계 전환율", "누적 전환율"):
        if disp[col].max(skipna=True) is not None and disp[col].max(skipna=True) > 1:
            disp[col] = disp[col] / 100
    st.dataframe(
        disp, hide_index=True, use_container_width=True,
        column_config={
            "단계": st.column_config.TextColumn("단계"),
            "도달 수": st.column_config.NumberColumn("도달 수", format="%,d"),
            "단계 전환율": st.column_config.ProgressColumn(
                "단계 전환율", min_value=0, max_value=1, format="%.1f%%"),
            "누적 전환율": st.column_config.ProgressColumn(
                "누적 전환율", min_value=0, max_value=1, format="%.1f%%"),
        },
    )


@st.fragment
def render_retention_funnel(t: dict, start: str | None, end: str | None) -> None:
    # 확인용 — 이 조각만 다시 그려지는지 보려고 찍는다. 나중에 지운다.
    st.caption(f"[유지 퍼널 조각] 렌더링 시각: {dt.datetime.now():%H:%M:%S}")

    if not C.RETENTION_STEPS:
        st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
                   "7주차에 정한 유지·이탈의 정의를 옮기면 여기에 그려집니다.")
        return

    contracts = t["contracts"]
    if start is None or end is None:
        st.caption("계약 데이터가 없습니다.")
        return

    c_month = to_dt(contracts.contract_start_date).dt.strftime("%Y-%m")
    sel_contracts = contracts[c_month.between(start, end)]
    rt = {
        "contracts": sel_contracts,
        "rent_payments": t["rent_payments"][
            t["rent_payments"].contract_id.isin(set(sel_contracts.contract_id))],
    }

    rf = ui.guard(M.retention_funnel, rt)
    if rf is None or not len(rf):
        return
    if "is_bottleneck" not in rf.columns:
        rf = rf.assign(is_bottleneck=False)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        ui.callout(
            "유지는 <b>관측 기간이 대상마다 다릅니다.</b> "
            "먼저 들어온 대상은 오래 관측됐고 나중에 들어온 대상은 짧게 관측됐습니다. "
            "<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b> "
            "비율(단위 기간당)로 바꾸거나 같은 시점에 시작한 것끼리 묶으십시오.",
            "info")


ui.section("퍼널", "그레인을 먼저 확인한다")
tab_acq, tab_ret = st.tabs(["획득 퍼널", "유지 퍼널"])

# ── 필터 위젯은 fragment 밖에 둔다 ────────────────────────────────
# ⚠ st.fragment 안에서 st.query_params 를 갱신하면 조각만 다시 그려져
#   URL과 화면이 어긋난다 — 그래서 축·기간 선택은 여기, 탭 본문 위에서 한다.
acq_months = _month_options(t["leads"].inquiry_date)
acq_dims = list(M.DIM_SOURCE)
with tab_acq:
    if acq_months:
        d_from = _qp("acq_from", acq_months, acq_months[0])
        d_to = _qp("acq_to", acq_months, acq_months[-1])
        acq_from, acq_to = st.select_slider(
            "기간(문의 접수월)", options=acq_months, value=(d_from, d_to),
            key="acq_period")
    else:
        acq_from = acq_to = None

    d_dim = _qp("acq_dim", acq_dims, acq_dims[0])
    acq_dim = st.segmented_control(
        "분해 축", acq_dims, default=d_dim, required=True, key="acq_dim_ui")

    st.query_params["acq_dim"] = acq_dim
    if acq_from and acq_to:
        st.query_params["acq_from"] = acq_from
        st.query_params["acq_to"] = acq_to

    render_acquisition_funnel(t, acq_dim, acq_from, acq_to)

ret_months = _month_options(t["contracts"].contract_start_date)
with tab_ret:
    if ret_months:
        d_from2 = _qp("ret_from", ret_months, ret_months[0])
        d_to2 = _qp("ret_to", ret_months, ret_months[-1])
        ret_from, ret_to = st.select_slider(
            "기간(계약 체결월)", options=ret_months, value=(d_from2, d_to2),
            key="ret_period")
        st.query_params["ret_from"] = ret_from
        st.query_params["ret_to"] = ret_to
    else:
        ret_from = ret_to = None

    render_retention_funnel(t, ret_from, ret_to)

st.caption("현재 화면 링크 (필터 상태 포함 — 복사해서 공유)")
st.code("?" + "&".join(f"{k}={v}" for k, v in st.query_params.to_dict().items()),
        language=None)

# ── 실험 ──────────────────────────────────────────────────────────
ui.section("실험 결과", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
res = ui.guard(M.experiment_results, t)


@st.fragment
def render_before_after(t: dict) -> None:
    """실험이 없는 도메인의 대체 카드 — 시간 기준 전후 비교.

    무작위 배정이 없으므로 인과를 주장할 수 없다는 문장을 각주가 아니라
    카드 본문에 넣는다(Day3 실습 C, "내 도메인이라면").
    """
    months = _month_options(t["leads"].inquiry_date)
    if len(months) < 2:
        st.caption("비교할 만큼 기간이 안 됩니다.")
        return
    split = st.select_slider(
        "비교 기준월 (이 월부터 '이후')", options=months[1:],
        value=months[len(months) // 2], key="ba_split")
    ba = ui.guard(M.before_after, t, f"{split}-01")
    if ba is None:
        return

    st.markdown(ui.badge(ba["color"], ba["판정"]), unsafe_allow_html=True)

    # 판정 과정 — 접힌 채로 시작. 결과(배지)가 먼저 보이고, 펼쳐야 어디서
    # 갈렸는지 보인다. 못 믿을 조건에 걸리면 2)·3)엔 값 대신 "계산하지 않음".
    with st.status("판정 과정", expanded=False) as box:
        if ba["판정"] == "판정 보류":
            st.write(f"1) 표본 확인 — ✕ 걸림 ({ba['사유']})")
            st.write("2) 주지표 — 계산하지 않음")
            st.write("3) 가드레일 — 계산하지 않음")
            box.update(label="판정 보류", state="error")
        else:
            st.write("1) 표본 확인 — ✓ 통과")
            st.write(f"2) 주지표({M.BEFORE_AFTER_PRIMARY}) — "
                     f"{ba['주지표_변화']:+.2f}%p (기준 {M.BEFORE_AFTER_MOVE}%p)")
            if ba["판정"] == "효과 없음":
                st.write(f"3) 가드레일 — 확인 안 함 "
                         f"(주지표가 기준 미만이라 여기서 끝)")
            else:
                mark = "✕" if ba["판정"] == "주의 필요" else "✓"
                st.write(f"3) 가드레일({M.BEFORE_AFTER_GUARD}) — {mark} "
                         f"{ba['가드레일_변화']:+.2f}%p "
                         f"(기준 -{M.BEFORE_AFTER_GUARD_WORSEN}%p)")
            box.update(label=ba["판정"], state="complete")

    if ba["판정"] == "판정 보류":
        # 못 믿을 조건 — 계산은 했지만 값을 보여주지 않는다. 사유만 남긴다.
        st.caption(f"표본 부족: {ba['사유']} — 지표 값을 표시하지 않습니다.")
        if st.button("왜 감췄나", key="why_ba"):
            show_hidden_reason(
                condition="표본 부족 (config.DECOMPOSE_MIN_SAMPLE 미만)",
                actual=ba["사유"],
                fix=f"이전·이후 두 구간 모두 {C.DECOMPOSE_MIN_SAMPLE}건 이상이 되도록 "
                    "기준월을 데이터 양끝에서 떨어뜨려 고르십시오.")
        return

    prev, cur = ba["이전"], ba["이후"]
    cols = st.columns(len(prev))
    for col, name in zip(cols, prev):
        with col:
            st.metric(
                label=name,
                value=cur[name]["fmt"].format(cur[name]["value"]),
                delta=cur[name]["fmt"].format(
                    cur[name]["value"] - prev[name]["value"]),
                delta_color="inverse" if name in M.HIGHER_IS_WORSE else "normal",
                border=True,
            )
    st.caption(
        f"이전 {ba['n_이전']:,}건 (~{split} 이전) · 이후 {ba['n_이후']:,}건 ({split}~) · "
        f"주지표({M.BEFORE_AFTER_PRIMARY}) 변화 {ba['주지표_변화']:+.2f}%p "
        f"(기준 {M.BEFORE_AFTER_MOVE}%p) · "
        f"가드레일({M.BEFORE_AFTER_GUARD}) 변화 {ba['가드레일_변화']:+.2f}%p "
        f"(기준 -{M.BEFORE_AFTER_GUARD_WORSEN}%p)")
    ui.callout(
        "<b>이 비교는 인과를 주장할 수 없습니다.</b> "
        "무작위 배정이 없었으므로 다른 요인의 영향을 배제하지 못합니다.")


if not res:
    render_before_after(t)

for r in (res or []):
    cls = r["color"]
    head = (f'<div class="exp {cls}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">{r["id"]}</div>'
            f'<div class="nm">{r["name"]}</div>'
            f'<div class="hy">{r["hypothesis"]}</div></div>'
            f'<div>{ui.badge(cls, r["verdict"])}</div></div>')

    if r["verdict"] == "무효":
        # 못 믿을 실험의 숫자는 보여주지 않는다.
        # 계산해 놓고 숨기는 것이 아니라 계산 자체를 하지 않았다.
        head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                 f'{r["reason"]}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    if "rc" not in r:
        head += (f'<div style="margin-top:12px;font-size:13px;color:#64748b">'
                 f'{r.get("reason", "")}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    head += (f'<div style="margin-top:14px;display:flex;gap:28px;'
             f'align-items:baseline;flex-wrap:wrap">'
             f'<div><div style="font-size:11px;color:#64748b">{r["primary"]}</div>'
             f'<div class="mv">{r["rc"]*100:.2f}% → {r["rt"]*100:.2f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">상대 효과</div>'
             f'<div class="mv">{r["lift"]*100:+.1f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">p값</div>'
             f'<div class="mv">{r["p"]:.4f}</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">표본</div>'
             f'<div style="font-size:13px;color:#475569" class="num">'
             f'{r["nc"]:,} / {r["nt"]:,}</div></div></div>')
    st.markdown(head + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.1])
    with c1:
        st.caption("효과 크기와 95% 신뢰구간 (0을 지나면 유의하지 않음)")
        st.plotly_chart(charts.forest(r), width="stretch",
                        config={"displayModeBar": False}, key=f"fr_{r['id']}")
    with c2:
        if r.get("guard"):
            gd = r["guard"]
            bad = gd["delta"] < -0.03
            st.markdown(
                f'<div class="card tight" style="border-color:'
                f'{C.COLORS["warn"] if bad else C.BRAND["line"]}">'
                f'<div style="font-size:11px;color:#64748b">가드레일 · {gd["name"]}</div>'
                f'<div style="font-size:20px;font-weight:700;margin-top:4px" class="num">'
                f'{gd["control"]*100:.1f}% → {gd["treatment"]*100:.1f}% '
                f'<span style="color:{C.COLORS["warn"] if bad else C.COLORS["ok"]}">'
                f'({gd["delta"]*100:+.1f}%p)</span></div>'
                + ('<div class="note">주지표는 개선됐지만 가드레일이 무너졌습니다.</div>'
                   if bad else
                   '<div style="font-size:12px;color:#64748b;margin-top:6px">'
                   '이상 없음</div>')
                + '</div>', unsafe_allow_html=True)
        elif r.get("reason"):
            st.markdown(f'<div class="card tight">'
                        f'<div style="font-size:13px;color:#64748b">{r["reason"]}</div>'
                        f'</div>', unsafe_allow_html=True)

    # 기간을 쪼개야 드러나는 것 — 초기 효과가 남아 있는가
    w = M.weekly_effect(r, r["start"])
    if not w.empty and len(w) >= 3:
        with st.expander("기간을 쪼개서 보기 — 효과가 유지되는가"):
            st.plotly_chart(charts.effect_decay(w), width="stretch",
                            config={"displayModeBar": False})
            ui.callout(
                f"전체 평균은 <b>{r['lift']*100:+.1f}%</b>인데 "
                f"초반 <b>{w.lift.iloc[0]*100:+.0f}%</b>에서 "
                f"후반 <b>{w.lift.iloc[-1]*100:+.0f}%</b>로 갑니다. "
                f"기간 평균만 보면 안 보이는 것입니다.")

    # 그때 멈췄다면 무엇을 봤을까
    pc = M.peeking_curve(r, r["start"])
    if not pc.empty and len(pc) >= 3:
        with st.expander("만약 여기서 멈췄다면? — 조기 중단 시뮬레이터"):
            cuts = list(pc.cut.astype(int))
            sel = st.select_slider("실험 종료일", options=cuts, value=cuts[0],
                                   key=f"peek_{r['id']}")
            row = pc[pc.cut == sel].iloc[0]
            a, b = st.columns([1, 1.4])
            with a:
                lv = "warn" if row.sig else "none"
                st.markdown(
                    ui.kpi_card(f"{sel}일차에 종료했다면", f"{row.lift*100:+.1f}%",
                                "유의 — 성공으로 보고" if row.sig
                                else "유의하지 않음", lv),
                    unsafe_allow_html=True)
                st.caption(f"p = {row.p:.3f}")
            with b:
                st.plotly_chart(charts.peeking(pc, r["lift"]), width="stretch",
                                config={"displayModeBar": False})
            ui.callout("종료 시점은 실험을 **시작하기 전에** 정해야 합니다.")

# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
ui.section("획득 경로 효율", "비용만 보면 순위가 뒤집힌다")
ce = ui.guard(M.channel_efficiency, t)
if ce is not None and len(ce):
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.plotly_chart(charts.cac_compare(ce), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        naive = list(ce.sort_values("CAC").channel)
        real = list(ce.sort_values("유효CAC").channel)
        st.markdown(
            f'<div class="card tight">'
            f'<div style="font-size:12px;color:#64748b">단순 비용 순위</div>'
            f'<div style="font-size:14px;margin:4px 0 12px">{" < ".join(naive)}</div>'
            f'<div style="font-size:12px;color:#64748b">유지율 반영 순위</div>'
            f'<div style="font-size:14px;font-weight:700;color:{C.COLORS["block"]}">'
            f'{" < ".join(real)}</div></div>', unsafe_allow_html=True)
        st.caption("비용은 가정값입니다. 리포트에 쓸 때 '가정값 기반'을 남기십시오.")
