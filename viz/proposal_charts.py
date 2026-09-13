# -*- coding: utf-8 -*-
"""제안서 전용 그래프. HTML 에 그대로 박을 수 있는 인라인 SVG 문자열을 만든다.

★ Day3 실습 C. 그림 하나에는 그 그림이 증명하는 문장 하나가 본문에 있어야 한다.
장식용 그래프는 넣지 않는다 — 파이 차트·3D·무지개색 없음. 색은 셋까지: 강조 1 ·
기본 1 · 회색 1(config.COLORS 에서 가져온다).

막대 길이·좌표는 전부 실제 값에서 계산한다. 값이 없는 계열은 그리지 않는다(0으로
그리지 않는다). 외부 CDN·이미지·폰트 링크를 쓰지 않는다 — 문자열 하나로 끝난다.
"""
from __future__ import annotations

import pandas as pd

from core import config as C

ACCENT = C.COLORS["block"]      # 강조 — 병목·최저
GOOD = C.COLORS["ok"]           # 대비용 — 최고
BASE = C.BRAND["primary"]       # 기본
GRAY = "#cbd5e1"                # 회색 — 나머지
INK = C.BRAND["ink"]
MUTED = C.BRAND["muted"]

_W = 640


def _bar_row(y: int, label: str, value: float, max_value: float, color: str,
             value_label: str) -> str:
    bar_w = 0 if max_value <= 0 else max(2, 300 * value / max_value)
    return (
        f'<text x="150" y="{y+15}" text-anchor="end" font-size="12" fill="{INK}">{label}</text>'
        f'<rect x="158" y="{y}" width="300" height="20" fill="#f1f5f9" rx="3"/>'
        f'<rect x="158" y="{y}" width="{bar_w:.1f}" height="20" fill="{color}" rx="3"/>'
        f'<text x="466" y="{y+15}" font-size="12" font-weight="700" fill="{INK}">{value_label}</text>'
    )


def funnel_svg(현황: pd.DataFrame) -> str:
    """단계별 도달 막대. 병목 구간 하나만 강조색, 나머지는 기본색."""
    rows = 현황.dropna(subset=["n"])
    if not len(rows):
        return ""
    max_n = rows.n.max()
    h = 30 * len(rows) + 20
    body = []
    for i, (_, row) in enumerate(rows.iterrows()):
        color = ACCENT if row.is_bottleneck else BASE
        body.append(_bar_row(10 + i * 30, row.label, row.n, max_n, color, f"{row.n:,}"))
    return (f'<svg viewBox="0 0 {_W} {h}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="sans-serif">{"".join(body)}</svg>')


def gap_svg(원인: pd.DataFrame, dim: str) -> str:
    """축별 전환율 가로 막대. 최고·최저만 색, 나머지는 회색. 표본 미달 칸은 안 그린다."""
    trusted = 원인[원인.믿음].sort_values("전환율", ascending=False)
    if not len(trusted):
        return ""
    max_v = trusted.전환율.max()
    hi_idx, lo_idx = trusted.전환율.idxmax(), trusted.전환율.idxmin()
    h = 30 * len(trusted) + 20
    body = []
    for i, (idx, row) in enumerate(trusted.iterrows()):
        color = GOOD if idx == hi_idx else ACCENT if idx == lo_idx else GRAY
        body.append(_bar_row(10 + i * 30, str(row[dim]), row.전환율, max_v, color,
                             f"{row.전환율*100:.1f}%"))
    return (f'<svg viewBox="0 0 {_W} {h}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="sans-serif">{"".join(body)}</svg>')


def trend_svg(추세: pd.DataFrame, col: str, threshold: float | None = None,
              higher_is_worse: bool = False) -> str:
    """최근 N개월 꺾은선. 임계선이 있으면 점선으로."""
    s = 추세[col].dropna()
    if len(s) < 2:
        return ""
    h, top, bottom = 200, 20, 170
    lo, hi = s.min(), s.max()
    if threshold is not None:
        lo, hi = min(lo, threshold), max(hi, threshold)
    span = (hi - lo) or 1
    n = len(s)
    step_x = (_W - 80) / max(1, n - 1)

    def y_of(v):
        return bottom - (v - lo) / span * (bottom - top)

    pts = [(40 + i * step_x, y_of(v)) for i, v in enumerate(s.values)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{BASE}"/>'
                   for x, y in pts)
    labels = "".join(
        f'<text x="{x:.1f}" y="{bottom+18}" font-size="10" fill="{MUTED}" '
        f'text-anchor="middle">{idx}</text>'
        for (x, _), idx in zip(pts, s.index))
    vals = "".join(
        f'<text x="{x:.1f}" y="{y-8:.1f}" font-size="10" font-weight="700" fill="{INK}" '
        f'text-anchor="middle">{v:.1f}</text>'
        for (x, y), v in zip(pts, s.values))
    th_line = ""
    if threshold is not None:
        ty = y_of(threshold)
        th_line = (f'<line x1="40" y1="{ty:.1f}" x2="{_W-40}" y2="{ty:.1f}" '
                   f'stroke="{ACCENT}" stroke-width="1.5" stroke-dasharray="5,4"/>'
                   f'<text x="{_W-40}" y="{ty-4:.1f}" font-size="10" fill="{ACCENT}" '
                   f'text-anchor="end">기준 {threshold}</text>')
    return (f'<svg viewBox="0 0 {_W} {h}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="sans-serif">'
            f'<path d="{path}" fill="none" stroke="{BASE}" stroke-width="2"/>'
            f'{dots}{vals}{labels}{th_line}</svg>')
