# -*- coding: utf-8 -*-
"""화면용 차트 (Plotly).

PDF용 차트는 viz/pdf_charts.py 에 matplotlib으로 따로 있다.
Plotly를 이미지로 내보내려면 kaleido가 필요한데 환경을 심하게 탄다.
**화면은 Plotly, 인쇄는 matplotlib** — 이 분리를 지킨다.
"""
from __future__ import annotations

import plotly.graph_objects as go

from core import config as C

FONT = "Pretendard, -apple-system, 'Malgun Gothic', sans-serif"


def _base(fig, height=360, margin=None):
    fig.update_layout(
        height=height,
        margin=margin or dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=C.BRAND["ink"]),
        hoverlabel=dict(font_family=FONT, font_size=13),
        showlegend=False,
    )
    return fig


def funnel_bars(f):
    """퍼널. 단계별 폭이 인원에 비례하고 병목 구간을 색으로 표시한다."""
    top = f.n.iloc[0]
    colors = [C.COLORS["block"] if b else C.BRAND["primary"]
              for b in f.is_bottleneck]
    text = []
    for _, r in f.iterrows():
        if r.step_rate == r.step_rate:
            text.append(f"{r.n:,}명 · 전 단계의 {r.step_rate*100:.1f}%")
        else:
            text.append(f"{r.n:,}명")
    fig = go.Figure(go.Bar(
        x=f.n, y=f.label, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=text, textposition="outside",
        textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>%{x:,}명<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False,
                     tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, top * 1.32])
    return _base(fig, height=300, margin=dict(l=8, r=8, t=4, b=4))


def device_compare(g):
    """분해 축별 전환율 비교. 격차가 보이는 것이 목적이다.

    g.믿음 이 False 인 칸(표본이 config.DECOMPOSE_MIN_SAMPLE 미만)은 전환율
    자체가 NaN이다 — 계산해 놓고 숨기는 게 아니라 값이 없다. 그런 칸은 막대
    길이를 0으로 두고 **block(빨강)** 으로 표시한다 — 판단기준 ⑤: "못 믿을
    조건에 걸린 카드는 block. 표본 부족이든 뭐든 결론이 '이 값을 쓰면 안 됨'
    으로 같기 때문". 믿을 수 있는 칸 중 가장 낮은 것은 warn(주황) — 이건
    "못 믿음"이 아니라 "실제로 낮으니 사람이 봐야 함"이라 다른 색을 쓴다.
    라벨은 항상 g.표시(믿을 수 있으면 비율, 아니면 가림사유)를 쓴다.
    """
    g = g.sort_values("전환율")
    min_reliable = g.loc[g.믿음, "전환율"].min() if g.믿음.any() else None
    colors = [
        C.COLORS["block"] if not rel else
        (C.COLORS["warn"] if rate == min_reliable else C.BRAND["primary"])
        for rel, rate in zip(g.믿음, g.전환율)
    ]
    fig = go.Figure(go.Bar(
        x=g.전환율.fillna(0) * 100, y=g[g.columns[0]], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=g["표시"],
        textposition="outside", textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>%{text}<extra></extra>",
    ))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, g.전환율.max(skipna=True) * 175])
    return _base(fig, height=52 * len(g) + 40,
                 margin=dict(l=8, r=8, t=4, b=4))


def forest(res):
    """실험 효과의 신뢰구간. 0을 지나면 유의하지 않다는 뜻이다.

    p값 하나만 보면 '얼마나' 좋아졌는지 모른다. 구간을 그려야 크기가 보인다.
    """
    lo, hi, d = res["lo"] * 100, res["hi"] * 100, res["diff"] * 100
    color = C.COLORS[res["color"]] if res["color"] in C.COLORS else C.BRAND["primary"]
    span = max(abs(lo), abs(hi)) * 1.5 or 1
    fig = go.Figure()
    fig.add_vline(x=0, line=dict(color=C.BRAND["line"], width=1.5))
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[0, 0], mode="lines",
        line=dict(color=color, width=4), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=[d], y=[0], mode="markers",
        marker=dict(color=color, size=13,
                    line=dict(color="white", width=2)),
        hovertemplate=f"차이 {d:+.2f}%p<br>95%% CI [{lo:+.2f}, {hi:+.2f}]<extra></extra>"))
    fig.update_xaxes(range=[-span, span], zeroline=False,
                     showgrid=False, ticksuffix="%p",
                     tickfont=dict(size=11, color=C.BRAND["muted"]))
    fig.update_yaxes(visible=False, range=[-1, 1])
    return _base(fig, height=86, margin=dict(l=8, r=8, t=6, b=22))


def spark(series, color=None):
    """지표 카드의 소형 추이선. 축도 눈금도 없다 — 모양만 본다."""
    fig = go.Figure(go.Scatter(
        y=list(series), mode="lines",
        line=dict(color=color or C.BRAND["primary"], width=2, shape="spline"),
        fill="tozeroy", fillcolor="rgba(79,70,229,0.08)",
        hoverinfo="skip"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False,
                     range=[min(series) * 0.97, max(series) * 1.03])
    return _base(fig, height=44, margin=dict(l=0, r=0, t=0, b=0))


def peeking(df, final_lift):
    """관측 시점별 효과. 초반에 멈췄으면 무엇을 봤을지 보여준다."""
    colors = [C.COLORS["warn"] if s else C.COLORS["none"] for s in df.sig]
    fig = go.Figure()
    fig.add_hline(y=final_lift * 100, line=dict(
        color=C.BRAND["muted"], width=1, dash="dot"))
    fig.add_trace(go.Bar(
        x=[f"{int(c)}일" for c in df.cut], y=df.lift * 100,
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v*100:+.1f}%" for v in df.lift],
        textposition="outside", textfont=dict(size=12),
        hovertemplate="%{x}<br>상대효과 %{y:.1f}%<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     ticksuffix="%", tickfont=dict(size=11,
                                                   color=C.BRAND["muted"]))
    return _base(fig, height=240, margin=dict(l=8, r=8, t=20, b=8))


def effect_decay(w):
    """기간별 효과 추이. 신규성 효과는 여기서만 드러난다."""
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=C.BRAND["line"], width=1))
    fig.add_trace(go.Scatter(
        x=w.label, y=w.lift * 100, mode="lines+markers",
        line=dict(color=C.COLORS["warn"], width=3, shape="spline"),
        marker=dict(size=9, color=C.COLORS["warn"],
                    line=dict(color="white", width=2)),
        hovertemplate="%{x}<br>상대효과 %{y:.1f}%<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     ticksuffix="%", tickfont=dict(size=11,
                                                   color=C.BRAND["muted"]))
    return _base(fig, height=240, margin=dict(l=8, r=8, t=12, b=8))


def cac_compare(g):
    """CAC와 유효 CAC를 나란히. 순위가 뒤집히는 것을 보이는 것이 목적이다."""
    g = g.sort_values("CAC")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="CAC", y=g.channel, x=g.CAC, orientation="h",
        marker=dict(color=C.BRAND["line"], line=dict(width=0)),
        text=[f"{v:,.0f}" for v in g.CAC], textposition="inside",
        textfont=dict(size=11, color=C.BRAND["ink"]),
        hovertemplate="%{y} CAC %{x:,.0f}원<extra></extra>"))
    fig.add_trace(go.Bar(
        name="유효 CAC", y=g.channel, x=g.유효CAC, orientation="h",
        marker=dict(color=[C.COLORS["block"] if r else C.BRAND["primary"]
                           for r in g.역전], line=dict(width=0)),
        text=[f"{v:,.0f}" for v in g.유효CAC], textposition="outside",
        textfont=dict(size=11, color=C.BRAND["muted"]),
        hovertemplate="%{y} 유효 CAC %{x:,.0f}원<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.05)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, g.유효CAC.max() * 1.28])
    return _base(fig, height=64 * len(g) + 30,
                 margin=dict(l=8, r=8, t=4, b=4))


def trend(m, col, suffix=""):
    fig = go.Figure(go.Scatter(
        x=list(m.index), y=m[col], mode="lines+markers",
        line=dict(color=C.BRAND["primary"], width=2.5, shape="spline"),
        marker=dict(size=6),
        hovertemplate="%{x}<br>%{y:,.2f}" + suffix + "<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     tickfont=dict(size=11, color=C.BRAND["muted"]))
    return _base(fig, height=260, margin=dict(l=8, r=8, t=8, b=8))
