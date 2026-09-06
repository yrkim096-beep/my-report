# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 실험 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core import config as C, metrics as M, validate as V
from core.load import to_dt
from core.todo import todo

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
#   아래 다섯은 임대주택 PM 도메인에서 실제로 쓸 법한 표현 중 이 앱이 계산하는
#   지표(전환율·이탈·수익)에 직접 붙는 것만 골랐다 — 근거 없이 다 넣지 않았다.
BANNED = [
    "때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
    "공실을 해소했다", "이탈을 방지했다", "유치에 성공했다",
    "안정화시켰다", "수익성을 개선했다",
]


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


def _ro(word: str) -> str:
    """"로"/"으로" 조사를 받침에 맞게 고른다. 받침이 없거나 ㄹ받침이면 "로"."""
    if not word:
        return "로"
    code = ord(word[-1]) - 0xAC00
    if not (0 <= code <= 11171):
        return "로"
    final = code % 28
    return "로" if final in (0, 8) else "으로"


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


def _signed(x: float, fmt: str) -> str:
    """부호를 강제로 붙인다. fmt는 kpis() 의 그 fmt(예: "{:.2f}%")를 그대로 쓴다."""
    return ("+" if x >= 0 else "-") + fmt.format(abs(x))


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약

    ★ Day4 실습 A에서 채웁니다.

    **수치는 쓰되 인과는 쓰지 않는다.** "A가 낮다"는 되고 "B 때문에 A가 낮다"는 안 된다.
    다 쓰고 나서 check_phrasing() 으로 자기 문장을 검사한다.

    반환: {"title": "1. 요약", "kind": "auto", "body": "..."}
    """
    k = M.kpis(t)
    deltas = M.kpi_deltas(t)

    lines = [f"기간 {C.PERIOD[0]} ~ {C.PERIOD[1]}"]
    for name, v in k.items():
        cur = v["fmt"].format(v["value"])
        d = deltas.get(name)
        if d is None:
            lines.append(f"{name} {cur}")
        else:
            lines.append(f"{name} {cur} (직전 달 대비 {_signed(d, v['fmt'])})")

    f = M.funnel(t)
    bn = f[f.is_bottleneck].iloc[0]
    lines.append(f"가장 낮은 구간 {bn.label} — 전 단계 대비 {bn.step_rate*100:.1f}%")

    body = "\n".join(lines)
    # 자기 문장 검사 — 실습 B에서 화면에 걸리게 만들지만, 여기서도 미리 확인한다.
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "1. 요약", "kind": "auto", "body": body}


def _s3_method(t: dict) -> dict:
    """3. 방법

    ★ Day4 실습 A에서 채웁니다.

    **분석 단위(그레인)를 반드시 밝힌다.** 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 검정을 썼는지.

    지표의 정의는 **위키가 원본**이다. 여기서 새로 정의하지 않는다.
    """
    leads = t["leads"]
    lines = [
        f"분석 단위(그레인): 리드 1건 — leads.lead_id 로 고유하게 센다. "
        f"같은 사람의 재문의는 별도 lead_id로 새 행이 되므로 인물 단위가 아니다.",
        f"데이터 기간과 건수: {C.PERIOD[0]} ~ {C.PERIOD[1]}, {leads.lead_id.nunique():,}건.",
        "비율 지표(전환율·납부이행률)는 성숙 구간 보정 없이 관측 기간 전체를 "
        "그대로 쓴다 — 최근 접수분을 따로 빼지 않았다.",
        "체결소요일은 문의 접수일부터 계약 체결일까지 일수의 중앙값이다 "
        "(계약까지 못 간 리드는 분모에서 빠진다).",
    ]
    body = "\n".join(lines)
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "3. 방법", "kind": "auto", "body": body}


def _s4_results(t: dict) -> dict:
    """4. 결과

    ★ Day4 실습 A에서 채웁니다.

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이다.

    charts 키에 차트 이름을 넣으면 PDF에 그려진다. 예) ["funnel", "device"]
    """
    f = M.funnel(t)
    lines = ["단계별 값"]
    for _, row in f.iterrows():
        if pd.isna(row.step_rate):
            lines.append(f"  {row.label} {row.n:,}건")
        else:
            lines.append(
                f"  {row.label} {row.n:,}건 (전 단계 대비 {row.step_rate*100:.1f}%, "
                f"누적 {row.cum_rate*100:.1f}%)"
                + (" (병목)" if row.is_bottleneck else ""))

    bn = f[f.is_bottleneck].iloc[0]
    bi = max(int(f.index[f.label == bn.label][0]), 1)
    prev_step, gap_step = f.step.iloc[bi - 1], f.step.iloc[bi]

    lines.append("")
    lines.append(f"분해 결과 ({f.label.iloc[bi-1]} → {bn.label} 구간)")
    for dim in M.DIM_SOURCE:
        g = M.funnel_by(t, dim, prev_step, gap_step)
        lines.append(f"  [{dim}]")
        for _, row in g.sort_values("전환율", na_position="last").iterrows():
            lines.append(f"    {row[dim]} — {row.표시}")

    body = "\n".join(lines)
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "4. 결과", "kind": "auto", "body": body,
            "charts": ["funnel", "device"]}


def _s5_experiments(t: dict) -> dict:
    """5. 실험

    ★ Day4 실습 A에서 채웁니다.

    **무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다.** 화면에서 감춘 숫자를
    리포트에 쓰면 감춘 의미가 없다. metrics.experiment_results() 의 verdict 를 보고
    분기한다.

    실험이 없으면 이 장을 빼거나, 전후 비교를 적되
    **"인과를 주장할 수 없다"를 같은 문단에 남긴다.**
    """
    results = M.experiment_results(t)

    if results:
        lines = []
        for r in results:
            if r["verdict"] == "무효":
                # ★ 무효 판정 — 사유만 적는다. 화면에서 감춘 숫자를 여기 쓰면
                # 감춘 의미가 없다.
                lines.append(f"{r['id']} {r['name']}: 무효 — {r['reason']}")
            else:
                lines.append(
                    f"{r['id']} {r['name']}: {r['verdict']} "
                    f"(표본 {r['nc']:,}/{r['nt']:,}건)")
        body = "\n".join(lines)
    else:
        # 이 도메인엔 실험(A/B)이 없다 — 전후 비교로 대신한다.
        months = sorted(to_dt(t["leads"].inquiry_date).dropna()
                        .dt.strftime("%Y-%m").unique())
        split = f"{months[len(months) // 2]}-01"
        ba = M.before_after(t, split)

        lines = [
            "이 비교는 인과를 주장할 수 없습니다. 무작위 배정이 없었으므로 "
            "다른 요인의 영향을 배제하지 못합니다.",
        ]
        if ba["판정"] == "판정 보류":
            # ★ 못 믿을 조건 — 사유만 적고 값은 쓰지 않는다.
            lines.append(f"판정 보류 — {ba['사유']}")
        else:
            lines.append(
                f"기준월 {ba['split'][:7]} — 이전 {ba['n_이전']:,}건 / "
                f"이후 {ba['n_이후']:,}건. 판정: {ba['판정']}")
            for name, prev in ba["이전"].items():
                cur = ba["이후"][name]
                lines.append(
                    f"  {name}: {prev['fmt'].format(prev['value'])} → "
                    f"{cur['fmt'].format(cur['value'])}")
        body = "\n".join(lines)

    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "5. 실험", "kind": "auto", "body": body}


def default_limit_rows(t: dict) -> list[dict]:
    """한계 절 편집기의 초기 행. 조립되는 것(검증 경고 · 못 한 것)과
    사람이 직접 찾아 적은 것(찾았는데 없음)을 모두 행으로 낸다.

    **표시용 문자열만 낸다.** 감춘 항목의 실제 수치는 이 함수가 부르는
    funnel_by()/before_after() 안에서 이미 걸러졌으므로(믿음==False → 사유만),
    여기 나오는 문장에도 원시 수치가 섞일 수 없다.
    """
    rows = []

    warns = [c for c in V.run_checks(t) if c["level"] == "warn"]
    for w in warns:
        content = f"{w['name']}: {w['msg']}" + (f" — {w['detail']}" if w["detail"] else "")
        rows.append({"출처": "검증 경고", "내용": content, "포함": True})

    f = M.funnel(t)
    bn = f[f.is_bottleneck].iloc[0]
    bi = max(int(f.index[f.label == bn.label][0]), 1)
    prev_step, gap_step = f.step.iloc[bi - 1], f.step.iloc[bi]
    for dim in M.DIM_SOURCE:
        g = M.funnel_by(t, dim, prev_step, gap_step)
        blocked = g[~g.믿음]
        if len(blocked):
            rows.append({
                "출처": "못 한 것",
                "내용": (f"{f.label.iloc[bi-1]} → {bn.label} 구간을 {dim}{_ro(dim)} "
                        f"쪼갠 칸 중 {len(blocked)}개가 최소 표본"
                        f"({C.DECOMPOSE_MIN_SAMPLE}건) 미달로 판정 보류"),
                "포함": True,
            })

    months = sorted(to_dt(t["leads"].inquiry_date).dropna()
                    .dt.strftime("%Y-%m").unique())
    ba = M.before_after(t, f"{months[len(months) // 2]}-01")
    if ba["판정"] == "판정 보류":
        rows.append({
            "출처": "못 한 것",
            "내용": f"전후 비교(기준월 {ba['split'][:7]}) — {ba['사유']}",
            "포함": True,
        })

    rows.append({
        "출처": "찾았는데 없음",
        "내용": ("채널별 실제 광고비를 기록하는 테이블 자체가 없다(leads·"
                "consultations·visits·contracts·rent_payments 외에 비용 테이블이 "
                "없음) — 획득 경로의 유효 비용(CAC)은 확인하지 못했다."),
        "포함": True,
    })
    rows.append({
        "출처": "찾았는데 없음",
        "내용": ("코호트(문의 접수월)별 상담 도달률 차이를 확인했으나, 최근 코호트"
                "(2025-12, 65.5%)가 다른 달(52.9~73.8%) 대비 낮지 않았다 — "
                "성과 문제도, 관측 기간 부족 문제도 아니었다."),
        "포함": True,
    })
    return rows


def _s7_limits(t: dict, rows: list[dict] | None = None) -> dict:
    """7. 한계 — 검증 경고에서 조립하고, 사람이 표에서 더한다

    ★ Day4 실습 D·G에서 채웁니다.

    **사람이 매번 쓰는 것이 아니라 경고를 그대로 옮긴다.**
    검증에서 경고가 났는데 한계에 안 적히면 **그 경고는 사라진 것과 같다.**

    한계는 세 곳에서 온다 — default_limit_rows() 가 앞 둘을 조립하고,
    세 번째(찾았는데 없던 것)는 사람이 찾아 적어야 한다. rows 는
    pages/3_리포트.py 의 st.data_editor 결과(포함 체크로 뺄 수 있음)다.
    `rows`가 None이면 default_limit_rows(t) 그대로 쓴다.

    그리고 **가정값이 들어간 문장에는 "가정값 기반"을 붙인다.**
    실측값과 가정값이 한 문단에 섞이면 읽는 사람은 둘 다 실측으로 읽는다.
    """
    rows = default_limit_rows(t) if rows is None else rows
    included = [r for r in rows if r.get("포함", True)]

    lines = []
    for source in ["검증 경고", "못 한 것", "찾았는데 없음"]:
        items = [r["내용"] for r in included if r["출처"] == source]
        lines.append(source)
        if items:
            for it in items:
                lines.append(f"  {it}")
        else:
            lines.append("  없음")
        lines.append("")

    # 항상 넣는 두 문장. 기간은 하드코딩하지 않고 config 에서 읽는다.
    lines.append("관측 데이터이므로 인과를 주장할 수 없다.")
    lines.append(
        f"기간이 {C.PERIOD[0]} ~ {C.PERIOD[1]}이므로 그보다 긴 주기의 변화는 "
        f"관측되지 않는다.")

    body = "\n".join(lines)
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "7. 한계", "kind": "auto", "body": body}


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
def _s2_background(human: dict) -> dict:
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
    }


def _s6_interpretation(human: dict) -> dict:
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다."),
    }


def _s8_proposal(human: dict) -> dict:
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None,
          limit_rows: list[dict] | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.
    limit_rows 는 7.한계 편집기(st.data_editor)의 결과 — None 이면
    default_limit_rows(t) 를 그대로 쓴다.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.
    """
    human = human or {}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 실험", _s5_experiments, t),
        _s6_interpretation(human),
        _safe("7. 한계", _s7_limits, t, limit_rows),
        _s8_proposal(human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[성장 리포트] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}
