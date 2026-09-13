# -*- coding: utf-8 -*-
"""제안서 조립 — report/sections.py 와 다른 문서. 9주차 Day3에 다시 짰다.

────────────────────────────────────────────────────────────────────
리포트(sections.py)는 "무슨 일이 있었는가"를 적는 문서고, 제안서(이 파일)는
"그래서 무엇을 하자는가"를 적어 **결정을 요청하는** 문서다. 읽는 사람이 다르다 —
분석하는 사람이 아니라 결정 권한을 가진 사람이다. 그래서 계산 과정·함수 이름·
컬럼 이름은 어디에도 넣지 않는다. 궁금하면 앱을 열면 된다.

절은 이 프로젝트 데이터가 실제로 답할 수 있는 것만 만든다("채울 함수 이름을
지금 댈 수 있는가"). 최대 7개, 사람이 쓰는 절은 둘("이 판단이 틀릴 수 있는 지점" ·
"무엇을 결정해 주셔야 합니까")뿐이다.

    절 제목(질문형)                채우는 함수                  자동/사람
    ─────────────────────────────────────────────────────────────
    한 장 요약                     이 파일이 나머지를 압축       자동
    1. 지금 어디서 새고 있습니까    core.metrics.funnel()        자동
    2. 어느 지점에서 벌어집니까     core.metrics.topic_evidence  자동
    3. 얼마짜리 문제입니까         core.metrics.proposal_topics 자동
    4. 무엇을 하자는 것입니까      day2/제안카드.md (카드)       자동
    5. 이 판단이 틀릴 수 있는 지점  —                            **사람**
    6. 무엇을 결정해 주셔야 합니까  선택지 셋은 자동, 문장은 사람  **사람**

카드에 없는 값을 자동 절이 지어내지 않는다. 없으면 "확인 필요"를 그대로 옮긴다.
문장 검사(check_phrasing)는 새로 만들지 않고 report/sections.py 것을 그대로 쓴다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from pathlib import Path

from core import config as C, metrics as M
from report.sections import check_phrasing  # ★ 새로 만들지 않고 재사용한다
from viz import proposal_charts as PC

DEFAULT_CARDS_PATH = C.ROOT / "day2" / "제안카드.md"

_CLS_ORDER = ["하지 말 것", "다시 할 것", "할 것"]
_CLS_TAG = {"하지 말 것": "stop", "다시 할 것": "redo", "할 것": "go"}
_CLS_MARK = {"하지 말 것": "✕", "다시 할 것": "▲", "할 것": "●"}


# ── 카드 파일 파싱 (Day2에서 그대로 가져온다) ─────────────────────
def parse_cards(path: Path | str = DEFAULT_CARDS_PATH) -> list[dict]:
    """day2/제안카드.md 를 파싱한다. 파일이 없으면 빈 리스트 — 지어내지 않는다."""
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n##\s+제안\s+\d+\s*[—-]\s*", text)[1:]
    cards = []
    for block in blocks:
        title, _, rest = block.partition("\n")
        card = {"제목": title.strip()}
        for field in ["분류", "근거", "비용", "효과", "되돌림"]:
            m = re.search(rf"\|\s*\*\*{field}\*\*\s*\|\s*(.+?)\s*\|", rest)
            card[field] = m.group(1).strip() if m else "확인 필요"
        cards.append(card)
    return cards


def cards_summary(cards: list[dict]) -> dict[str, int]:
    out = {c: 0 for c in _CLS_ORDER}
    for card in cards:
        out[card.get("분류", "")] = out.get(card.get("분류", ""), 0) + 1
    return out


def cards_for_topic(cards: list[dict], topic: dict) -> list[dict]:
    """이 주제와 관련된 카드만 고른다. 근거축 이름이 카드 근거에 들어있으면 관련이다.

    관련 카드를 못 찾으면 빈 목록을 돌려준다 — 상관없는 카드를 대신 보여주지 않는다.
    "이 주제에 대한 카드가 아직 없다"고 그대로 적는 편이 더 정직하다.
    """
    dim = topic.get("근거축")
    if not dim:
        return []
    return [c for c in cards if dim in c.get("근거", "") or dim in c.get("제목", "")]


# ── 자동 절 ───────────────────────────────────────────────────────
def _s_summary(t: dict, topic: dict, cards: list[dict]) -> dict:
    lines = [f"발견 — {topic['한줄']}."]
    for cls in _CLS_ORDER:
        picks = [c for c in cards if c.get("분류") == cls]
        if picks:
            # ★ 되돌릴 수 있는지는 한 장 요약만 보고도 알 수 있어야 한다 — 카드 안에
            #   있다고 안심하면 안 된다(Day4 동료 지적: 위치 문제).
            titled = []
            for c in picks:
                revert = c.get("되돌림", "")
                tag = (" (되돌림 가능)" if revert.startswith("가능")
                      else " (되돌림 불가/제한)" if revert.startswith(("불가", "해당 없음"))
                      else "")
                titled.append(c["제목"] + tag)
            lines.append(f"제안 — {_CLS_MARK[cls]} {cls}: " + " · ".join(titled))
    lines.append(f"규모 — 연 {topic['규모_연간건수']:,.1f}건 수준으로 추정된다(가정 위의 계산).")
    lines.append(f"근거 — 기간 {C.PERIOD[0]}~{C.PERIOD[1]} · 검증 통과 · 상세는 부록")
    body = "\n".join(lines)
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "한 장 요약", "kind": "auto", "body": body}


def _s1_where(t: dict, evidence: dict) -> dict:
    f = evidence["현황"]
    bn = f[f.is_bottleneck].iloc[0]
    body = (f"전체 {f.n.iloc[0]:,}건 중 {bn.label} 단계까지 넘어가는 것은 "
           f"{bn.n:,}건이다. 6단계 중 이 구간의 전 단계 대비 전환율({bn.step_rate*100:.1f}%)이 "
           f"가장 낮다.")
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "1. 지금 어디서 새고 있습니까", "kind": "auto", "body": body,
            "svg": PC.funnel_svg(f)}


def _s2_where_exactly(evidence: dict, topic: dict) -> dict:
    원인, 사유 = evidence["원인"], evidence["원인_사유"]
    if 원인 is None:
        body = 사유
        return {"title": "2. 어느 지점에서 벌어집니까", "kind": "auto", "body": body, "svg": ""}
    dim = topic["근거축"]
    trusted = 원인[원인.믿음]
    blocked = len(원인) - len(trusted)
    body = (f"{dim}로 나누면 {topic['한줄']}다."
           + (f" 표본 미달로 판정을 보류한 칸 {blocked}개는 뺐다." if blocked else ""))
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "2. 어느 지점에서 벌어집니까", "kind": "auto", "body": body,
            "svg": PC.gap_svg(원인, dim)}


def _s3_how_big(t: dict, evidence: dict, topic: dict) -> dict:
    lines = [f"이 격차가 유지된다고 보면 연 {topic['규모_연간건수']:,.1f}건 규모다."]
    for g in evidence["규모_가정"]:
        lines.append(f"가정 — {g}")
    body = "\n".join(lines)
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"

    trend_col = None
    if topic["키"].startswith("threshold_"):
        trend_col = topic["키"].split("threshold_", 1)[1]
    elif topic["키"].startswith("trend_"):
        trend_col = topic["키"].split("trend_", 1)[1]
    svg = ""
    if trend_col and evidence["추세"] is not None and trend_col in evidence["추세"].columns:
        th = C.THRESHOLDS.get(trend_col, {}).get("경고") if trend_col in C.THRESHOLDS else None
        svg = PC.trend_svg(evidence["추세"], trend_col, threshold=th)
    return {"title": "3. 얼마짜리 문제입니까", "kind": "auto", "body": body, "svg": svg}


def _s4_proposal(cards: list[dict]) -> dict:
    if not cards:
        body = "이 주제에 대한 제안 카드가 아직 없다."
        return {"title": "4. 무엇을 하자는 것입니까", "kind": "auto", "body": body, "cards": []}
    lines = []
    for cls in _CLS_ORDER:
        picks = [c for c in cards if c.get("분류") == cls]
        if not picks:
            continue
        lines.append(f"{_CLS_MARK[cls]} {cls}")
        for c in picks:
            lines.append(f"  {c['제목']}")
            lines.append(f"    근거: {c['근거']}")
            lines.append(f"    비용: {c['비용']}")
            lines.append(f"    효과: {c['효과']}")
            lines.append(f"    되돌림: {c['되돌림']}")
        lines.append("")
    body = "\n".join(lines).rstrip()
    hit = check_phrasing(body)
    assert not hit, f"자동 생성 문장에 인과 단정 표현이 섞였다: {hit}"
    return {"title": "4. 무엇을 하자는 것입니까", "kind": "auto", "body": body, "cards": cards}


def _s5_if_wrong(human: dict) -> dict:
    return {
        "title": "5. 이 판단이 틀릴 수 있는 지점", "kind": "human",
        "body": human.get("5. 이 판단이 틀릴 수 있는 지점", ""),
        "placeholder": ("가장 큰 위험은 어느 제안인지, 무엇 때문에 틀릴 수 있는지, "
                        "철회 조건(무엇이 얼마가 되면 철회하는지)을 적으십시오."),
    }


def _s6_ask(topic: dict, human: dict) -> dict:
    auto_lines = [
        f"이 주제의 규모 — 연 {topic['규모_연간건수']:,.1f}건",
        "결정 선택지 — 승인(제안대로 즉시 진행) / 조건부 승인(추가 확인 후 진행) / 보류(다음 분기 재검토)",
        f"미루면 다음 분기까지 약 {topic['규모_연간건수']/4:,.1f}건 규모가 그대로 누적된다",
    ]
    return {
        "title": "6. 무엇을 결정해 주셔야 합니까", "kind": "human",
        "auto_lines": auto_lines,
        "body": human.get("6. 무엇을 결정해 주셔야 합니까", ""),
        "placeholder": "위 선택지 중 무엇을 요청하는지 결정을 요구하는 문장으로 적으십시오.",
    }


def build(t: dict, topic_key: str, cards: list[dict], human: dict | None = None) -> list[dict]:
    """주제 하나를 받아 절 전체를 조립한다. 순서를 바꾸지 않는다."""
    human = human or {}
    topics = {x["키"]: x for x in M.proposal_topics(t)}
    topic = topics[topic_key]
    evidence = M.topic_evidence(t, topic_key)
    topic_cards = cards_for_topic(cards, topic)
    return [
        _s_summary(t, topic, topic_cards),
        _s1_where(t, evidence),
        _s2_where_exactly(evidence, topic),
        _s3_how_big(t, evidence, topic),
        _s4_proposal(topic_cards),
        _s5_if_wrong(human),
        _s6_ask(topic, human),
    ]


# ── HTML 내보내기 ─────────────────────────────────────────────────
TEMPLATE_PATH = C.ROOT / "제안서_템플릿.html"


def _extract_style(template_path: Path = TEMPLATE_PATH) -> str:
    """템플릿의 <style> 블록(A4 인쇄 규칙 포함)을 그대로 읽어 재사용한다."""
    if not template_path.exists():
        return ""
    text = template_path.read_text(encoding="utf-8")
    m = re.search(r"<style>.*?</style>", text, re.S)
    return m.group(0) if m else ""


def to_html(secs: list[dict], meta: dict) -> str:
    """template 의 구조·클래스를 그대로 써서 단일 HTML 파일을 만든다. 빈 절은 그리지 않는다."""
    style = _extract_style()
    by_title = {s["title"]: s for s in secs}
    summary = by_title["한 장 요약"]["body"]
    s1, s2, s3 = (by_title[k] for k in
                  ["1. 지금 어디서 새고 있습니까", "2. 어느 지점에서 벌어집니까",
                   "3. 얼마짜리 문제입니까"])
    s4 = by_title["4. 무엇을 하자는 것입니까"]
    if_wrong = by_title["5. 이 판단이 틀릴 수 있는 지점"]["body"] or "확인 필요 — 아직 작성되지 않았다"
    ask = by_title["6. 무엇을 결정해 주셔야 합니까"]

    def fig(svg, caption):
        if not svg:
            return ""
        return f'<figure><div class="chart">{svg}</div><figcaption>{caption}</figcaption></figure>'

    prop_html = []
    for c in s4["cards"]:
        cls = c.get("분류", "할 것")
        tag = _CLS_TAG.get(cls, "go")
        mark = _CLS_MARK.get(cls, "●")
        prop_html.append(f'''
<div class="prop {tag}">
  <div class="cls">{mark} {cls}</div>
  <h4>{c["제목"]}</h4>
  <dl>
    <dt>근거</dt><dd>{c["근거"]}</dd>
    <dt>비용</dt><dd>{c["비용"]}</dd>
    <dt>효과</dt><dd>{c["효과"]}</dd>
    <dt>되돌림</dt><dd>{c["되돌림"]}</dd>
  </dl>
</div>''')

    ask_auto = "".join(f"<li>{ln}</li>" for ln in ask["auto_lines"])
    ask_body = ask["body"] or "확인 필요 — 아직 작성되지 않았다"

    sections_html = "".join([
        f'<h2 class="sec"><span class="no">1</span>{s1["title"][3:]}</h2>'
        f'<p>{s1["body"]}</p>{fig(s1["svg"], "막대 길이는 도달 건수에 비례한다. 그레인은 리드(lead_id) 1건이다.")}',
        f'<h2 class="sec"><span class="no">2</span>{s2["title"][3:]}</h2>'
        f'<p>{s2["body"]}</p>{fig(s2["svg"], "표본 미달 칸은 그리지 않았다.")}',
        f'<h2 class="sec"><span class="no">3</span>{s3["title"][3:]}</h2>'
        f'<p style="white-space:pre-line">{s3["body"]}</p>{fig(s3["svg"], "월별 실측값. 점선은 경고 기준선이다.")}',
        f'<h2 class="sec"><span class="no">4</span>{s4["title"][3:]}</h2>{"".join(prop_html) or "<p>확인 필요</p>"}',
        f'<h2 class="sec"><span class="no">5</span>{by_title["5. 이 판단이 틀릴 수 있는 지점"]["title"][3:]}</h2>'
        f'<p style="white-space:pre-line">{if_wrong}</p>',
        f'<h2 class="sec"><span class="no">6</span>{ask["title"][3:]}</h2>'
        f'<ul class="plist">{ask_auto}</ul>'
        f'<p style="white-space:pre-line"><b>{ask_body}</b></p>',
    ])

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{meta.get("title", "성과 개선 제안")}</title>
{style}
</head>
<body>
<div class="page">

<div class="cover">
  <div class="kicker">성과 개선 제안</div>
  <h1>{meta.get("title", "성과 개선 제안")}</h1>
  <div class="meta">
    <span>데이터셋 <b class="num">{meta.get("dataset", "")}</b></span>
    <span>기간 <b class="num">{meta.get("period", "")}</b></span>
    <span>작성 <b class="num">{meta.get("date", "")}</b></span>
    <span>검증 <b><span class="badge b-ok">● 통과</span></b></span>
  </div>
</div>

<div class="summary">
  <h2>한 장 요약</h2>
  <div class="srow"><div class="v" style="white-space:pre-line">{summary}</div></div>
</div>

{sections_html}

</div>
</body>
</html>'''
