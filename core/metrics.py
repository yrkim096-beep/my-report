# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
★ 이 파일에는 통신사 컬럼명이 박혀 있다.

  billing_amount · is_churned · acquisition_channel · visitor_id ...

config.py 를 다 바꿔도 여기서 깨진다. **깨지는 것이 정상이다.**
컬럼명을 하나씩 내 것으로 맞추는 것이 이식 작업의 절반이다. → DESIGN.md §4-6
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core import config as C
from core.load import to_dt
from core.todo import todo


# ── 퍼널 ──────────────────────────────────────────────────────────
def _stage_leads(t: dict) -> dict[str, set]:
    """단계별 "도달한 lead_id 집합". funnel() 과 funnel_by() 가 함께 쓴다."""
    leads, consultations = t["leads"], t["consultations"]
    visits, contracts, payments = t["visits"], t["contracts"], t["rent_payments"]

    contract_lead = contracts.set_index("contract_id")["lead_id"]
    paid_contract_ids = set(payments.loc[payments.paid.astype(bool), "contract_id"])
    paid_leads = set(contract_lead.reindex(list(paid_contract_ids)).dropna())

    return {
        "문의접수": set(leads.lead_id),
        "상담진행": set(consultations.lead_id),
        "방문예약진행": set(visits.lead_id),
        "계약체결": set(contracts.lead_id),
        "입주": set(contracts.lead_id),  # contract_start_date = 입주일(알려진 한계, 위 참고)
        "첫월세납부": paid_leads,
    }


@st.cache_data(show_spinner=False)
def funnel(t: dict) -> pd.DataFrame:
    """단계별 도달 인원과 전환율.

    그레인: **리드(lead_id) 1건.** 한 리드가 같은 단계를 두 번 밟지 않으므로
    (leads.csv 그레인 노트: 재문의는 별도 lead_id로 새 행) 고유값(nunique)이나
    len이나 결과는 같지만, 안전하게 고유값으로 센다.

    단계는 획득 퍼널(leads→consultations→visits→contracts)에 rent_payments를
    더해 여섯 단계로 잇는다. 각 단계에 "도달한 lead_id 집합"을 먼저 만들고
    집합 크기를 센다 — 그래야 팬아웃(한 리드에 여러 상담·방문 로그)이 있어도
    중복으로 안 세인다.

    ★ 알려진 한계: "계약체결"과 "입주"는 이 데이터에서 같은 사건이다.
    contracts.contract_start_date 하나만 있고 별도 입주일 컬럼이 없어서,
    두 단계의 lead_id 집합이 동일하다 — 전환율 100%가 뜨는 게 정상이다.
    실제 데이터를 반입하면 입주일이 따로 있는지 다시 확인해야 한다.

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              그 단계에 도달한 리드 수
        step_rate      전 단계 대비 비율 (첫 단계는 NaN)
        cum_rate       첫 단계 대비 비율
        drop           전 단계에서 빠진 수
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True
    """
    stage_leads = _stage_leads(t)

    rows = []
    prev_n = first_n = None
    for step in C.FUNNEL_STEPS:
        n = len(stage_leads.get(step, set()))
        first_n = n if first_n is None else first_n
        rows.append({
            "step": step, "label": C.FUNNEL_LABELS.get(step, step), "n": n,
            "step_rate": (n / prev_n) if prev_n else np.nan,
            "cum_rate": (n / first_n) if first_n else np.nan,
            "drop": (prev_n - n) if prev_n is not None else np.nan,
        })
        prev_n = n

    df = pd.DataFrame(rows)
    df["is_bottleneck"] = False
    rates = df["step_rate"].iloc[1:]
    if rates.notna().any():
        df.loc[rates.idxmin(), "is_bottleneck"] = True
    return df


# ★ 분해 축. 어느 테이블의 어느 컬럼인지. 담당자·유입채널 둘 다 손을 쓸 수 있는
#   축으로 골랐다(Day3 실습 A) — 매물유형은 격차가 2.2%p뿐이라 뺐다.
DIM_SOURCE = {
    "담당자": ("consultations", "counselor_id"),
    "유입채널": ("leads", "channel"),
}


def sample_band(n: int) -> str:
    """건수 구간. 「적은 표본으로 판단하기」의 표를 그대로 코드로 옮긴다.

    한 칸을 감출지 말지를 임계값 하나로 이분하지 않는다 — 건수 구간마다
    "무엇을 보여줄 수 있는가"가 다르다(전수만 · 경향만 · 정수 비율만 · 소수점
    비율 · 전부). 평균이 아니라 **그 칸 자체의 건수**로 판정한다.
    """
    if n < 10:
        return "전수"
    if n < 30:
        return "경향"
    if n < 100:
        return "정수율"
    if n < 500:
        return "비율"
    return "충분"


def format_cell(n: int, m: int) -> str:
    """건수 구간에 맞는 표시 문자열. 분모(n)를 반드시 같이 적는다.

        전수    비율을 아예 안 쓴다 — "3건 중 1건"
        경향    비율은 10% 단위까지만 — 소수점을 쓰면 없는 정밀도를 지어낸 것
        정수율  비율은 정수 자리까지만
        비율    소수점 한 자리까지
        충분    소수점 한 자리, 천단위 구분
    """
    band = sample_band(n)
    if band == "전수":
        return f"{n}건 중 {m}건"
    if band == "경향":
        return f"{n}건 중 {m}건 (약 {round(m / n * 100 / 10) * 10}%)"
    if band == "정수율":
        return f"{m / n * 100:.0f}% ({n}건 중 {m}건)"
    if band == "비율":
        return f"{m / n * 100:.1f}% ({n}건 중 {m}건)"
    return f"{m / n * 100:.1f}% ({n:,}건 중 {m:,}건)"


@st.cache_data(show_spinner=False)
def funnel_by(t: dict, dim: str, step_from: str, step_to: str) -> pd.DataFrame:
    """차원별 특정 구간 전환율. 평균 하나로는 어디를 고칠지 모른다.

    dim 은 분해 축이다. DIM_SOURCE 에 등록된 이름만 받는다.
    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중, band, 표시, 믿음, 가림사유]

        도달     step_from 에 도달한 lead 수 (그 칸)
        전환     그중 step_to 까지 넘어간 lead 수
        전환율   전환 / 도달 (0~1). **믿음이 False 인 칸은 NaN 이다** —
                 계산해 놓고 안 보여주는 게 아니라, 표시할 값 자체가 없다
        비중     도달 / step_from 전체 도달 수 (0~1)
        band     sample_band(도달) — 참고용 세부 구간
        믿음     도달 >= config.DECOMPOSE_MIN_SAMPLE (못 믿을 조건 분기)
        가림사유  믿음이 False 일 때만 채워진다. 실제 숫자를 담는다
        표시     믿음이면 format_cell(도달, 전환), 아니면 가림사유
    """
    stage = _stage_leads(t)
    reach_from, reach_to = stage[step_from], stage[step_to]
    table_name, col = DIM_SOURCE[dim]

    src = t[table_name][["lead_id", col]].drop_duplicates("lead_id")
    df = pd.DataFrame({"lead_id": list(reach_from)}).merge(src, on="lead_id", how="left")
    df[col] = df[col].astype(object).fillna("결측")
    df["전환됨"] = df.lead_id.isin(reach_to)

    g = df.groupby(col, dropna=False)["전환됨"].agg(전환="sum", 도달="count").reset_index()
    g["비중"] = g["도달"] / g["도달"].sum()
    g["band"] = g["도달"].apply(sample_band)

    # ★ 못 믿을 조건 분기 — 표본이 config.DECOMPOSE_MIN_SAMPLE 미만이면
    # 전환율 자체를 계산하지 않는다(NaN). 사유에는 실제 숫자를 넣는다.
    g["믿음"] = g["도달"] >= C.DECOMPOSE_MIN_SAMPLE
    g["가림사유"] = g["도달"].apply(
        lambda n: None if n >= C.DECOMPOSE_MIN_SAMPLE
        else f"표본 {n}건 (최소 {C.DECOMPOSE_MIN_SAMPLE}건)")
    g["전환율"] = np.where(g["믿음"], g["전환"] / g["도달"], np.nan)
    g["표시"] = [
        format_cell(n, m) if 믿음 else 사유
        for 믿음, 사유, n, m in zip(g["믿음"], g["가림사유"], g["도달"], g["전환"])
    ]
    return g.rename(columns={col: dim})[
        [dim, "도달", "전환", "전환율", "비중", "band", "믿음", "가림사유", "표시"]]


# ── 유지 퍼널 ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다.

    ★ Day2 실습 D에서 채웁니다.

    획득 퍼널과 다른 점 셋:

        단계    주어지지 않는다. **내가 정의한다**
        방향    한 방향이 아니다. 오갈 수 있다
        시간    며칠이 아니라 몇 달~몇 년

    그래서 그레인이 다르다. 획득은 **대상 하나**지만 유지는 흔히 **대상 × 기간**이다.
    같은 오류의 두 얼굴이다 — 그레인을 잘못 잡으면 둘 다 틀린다.

    **퍼널이 아니면 퍼널이라고 부르지 않는다.** 세 가지를 물어라.

        이 단계는 앞 단계를 반드시 거치는가?  아니면 그냥 분류다
        그레인이 무엇인가?
        기간을 어떻게 자르는가?

    그리고 **관측 기간이 다른 대상을 누적값으로 비교하지 않는다.**
    비교하려면 비율(단위 기간당)로 바꾸거나, 같은 시점에 시작한 것끼리 묶는다.
    7주차 토요일에 겪은 생존 편향이 여기서 다시 나온다.

    반환: DataFrame[step, label, n, step_rate, cum_rate]

    ────────────────────────────────────────────────────────────────
    ★ 이 프로젝트 데이터에는 "과제"·"집행" 테이블이 따로 없다. 과제는
    계약(contracts, contract_id 1건)으로, 집행은 그 계약의 월세 납부
    (rent_payments 에서 paid == True) 로 놓았다. 다르게 정의했다면
    아래 stage_contracts 부터 다시 봐야 한다.

    그레인: 과제(계약) 1건. "지속" 판정만 예외적으로 대상×시간(첫 집행과
    두 번째 집행 사이 간격)을 본다 — 착수·완주는 시점 하나의 상태다.
    ────────────────────────────────────────────────────────────────
    """
    contracts, payments = t["contracts"], t["rent_payments"]
    paid = payments[payments.paid.astype(bool)].copy()
    paid["pm"] = to_dt(paid.payment_month)

    paid_dates = (paid.sort_values("pm").groupby("contract_id")["pm"]
                  .apply(lambda s: s.tolist()))

    started = set(paid_dates.index)
    continued = {cid for cid, dates in paid_dates.items()
                 if len(dates) >= 2 and (dates[1] - dates[0]).days <= 90}
    completed = set(contracts.loc[contracts.status != "계약중", "contract_id"])

    stage_contracts = {"착수": started, "지속": continued, "완주": completed}

    rows = []
    prev_n = first_n = None
    for step, _ in C.RETENTION_STEPS:
        n = len(stage_contracts.get(step, set()))
        first_n = n if first_n is None else first_n
        rows.append({
            "step": step, "label": step, "n": n,
            "step_rate": (n / prev_n) if prev_n else np.nan,
            "cum_rate": (n / first_n) if first_n else np.nan,
        })
        prev_n = n
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def churn(t: dict) -> dict:
    """이탈 판정. 계약 기간이 끝난 뒤 재계약했는지로 본다.

        유지  status == "재계약"
        이탈  status in {"만료_미갱신", "중도해지"}

    "계약중"(아직 기간이 안 끝난 계약)은 재계약 여부 자체가 아직 정해지지
    않았으므로 분모에서 뺀다 — 유지도 이탈도 아니라 "아직 판정 불가"다.

    다만 계약중인 것 중 마지막 집행(납부) 후 config.CHURN_INACTIVITY_DAYS
    이상 무활동인 것은 위험 표시(at_risk)만 남긴다. 이탈로 세지는 않는다 —
    계약 기간이 끝나 재계약을 안 한 것 같은 확정된 사건이 아니라 조짐일
    뿐이라서다. 기준 시점(anchor)은 config.PERIOD 종료일이다.

    반환: {"n_retained": int, "n_churned": int, "n_decided": int, "rate": float,
           "retained_ids": set[str], "churned_ids": set[str],
           "at_risk_ids": set[str]}
    """
    contracts, payments = t["contracts"], t["rent_payments"]

    retained_ids = set(contracts.loc[contracts.status == "재계약", "contract_id"])
    churned_ids = set(contracts.loc[
        contracts.status.isin(["만료_미갱신", "중도해지"]), "contract_id"])
    n_retained, n_churned = len(retained_ids), len(churned_ids)
    n_decided = n_retained + n_churned

    ongoing_ids = set(contracts.loc[contracts.status == "계약중", "contract_id"])
    paid = payments[payments.paid.astype(bool)].copy()
    paid["pm"] = to_dt(paid.payment_month)
    last_paid = paid.groupby("contract_id")["pm"].max()
    anchor = pd.Timestamp(C.PERIOD[1])
    inactive_days = (anchor - last_paid).dt.days
    at_risk_ids = {cid for cid in ongoing_ids
                   if inactive_days.get(cid, 0) >= C.CHURN_INACTIVITY_DAYS}

    return {
        "n_retained": n_retained,
        "n_churned": n_churned,
        "n_decided": n_decided,
        "rate": (n_churned / n_decided) if n_decided else np.nan,
        "retained_ids": retained_ids,
        "churned_ids": churned_ids,
        "at_risk_ids": at_risk_ids,
    }


# ── KPI ───────────────────────────────────────────────────────────
# ★ kpis() 각 지표의 계산식을 사람이 읽는 문장으로도 남긴다. 화면의
#   st.popover("정의")가 여기서 읽어 보여준다. 임계값 근거는 config.THRESHOLD_REASONS.
KPI_DEFS: dict[str, str] = {
    "리드 수": "leads 테이블 전체 행 수 (lead_id 고유값 개수)",
    "전환율": "계약까지 간 리드 수 ÷ 전체 리드 수 × 100",
    "체결소요일": "문의 접수일 ~ 계약 체결일 사이 일수의 중앙값",
    "납부이행률": "정상 납부(rent_payments.paid == True) 건수 ÷ 전체 납부 건수 × 100",
}


@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드. 규모·전환·속도·품질 네 축에서 하나씩 뽑았다.

        리드 수      규모  leads 전체 건수
        전환율       전환  계약까지 간 리드 비율 (lead_id 기준)
        체결소요일    속도  문의 접수 ~ 계약 체결까지 걸린 일수 (중앙값)
        납부이행률    품질  rent_payments 중 정상 납부(paid=True) 비율

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str}}
    """
    leads, contracts, payments = t["leads"], t["contracts"], t["rent_payments"]

    n_leads = leads.lead_id.nunique()
    n_contracted = contracts.lead_id.nunique()

    lead_dates = to_dt(leads.set_index("lead_id")["inquiry_date"])
    contract_dates = to_dt(contracts.set_index("lead_id")["contract_start_date"])
    lead_to_contract_days = (
        contract_dates - lead_dates.reindex(contract_dates.index)
    ).dt.days

    return {
        "리드 수": {"value": float(n_leads), "unit": "건", "fmt": "{:,.0f}건"},
        "전환율": {"value": (n_contracted / n_leads * 100) if n_leads else float("nan"),
                  "unit": "%", "fmt": "{:.2f}%"},
        "체결소요일": {"value": float(lead_to_contract_days.median()),
                    "unit": "일", "fmt": "{:.1f}일"},
        "납부이행률": {"value": float(payments.paid.astype(bool).mean() * 100),
                    "unit": "%", "fmt": "{:.2f}%"},
    }


# ★ 전후 비교의 주지표·가드레일과 판정 기준. 실험이 없어 이 표로 대신한다.
#   근거 — 여러 시점으로 실제 전후 비교를 반복해 본 결과(과거 데이터 안에서
#   기준월을 이동시켜 가며 관측), 관측 편향이 없는 구간에서도 두 값 다
#   최대 ±2.8%p 안에서 자연스럽게 흔들렸다. 그 흔들림보다 뚜렷이 크도록
#   3%p를 기준으로 잡았다.
BEFORE_AFTER_PRIMARY = "전환율"       # 주지표 — 이 퍼널의 핵심 전환 지표
BEFORE_AFTER_MOVE = 3.0              # %p. 이보다 작으면 "효과 없음"
BEFORE_AFTER_GUARD = "납부이행률"     # 가드레일 — 계약을 서둘러 늘리면 질이 떨어질 수 있다
BEFORE_AFTER_GUARD_WORSEN = 3.0      # %p. 이보다 나빠지면 "주의 필요"


@st.cache_data(show_spinner=False)
def before_after(t: dict, split: str) -> dict:
    """전후 비교. split(YYYY-MM-DD) 이전/이후로 나눠 kpis() 를 각각 낸다.

    ★ 이 도메인엔 실험(A/B)이 없다. 무작위 배정 없이 시간으로만 가른
    비교라 **인과를 주장할 수 없다** — 이건 계산이 아니라 화면 카드에
    적어야 하는 문장이다(Day3 실습 C, "내 도메인이라면").

    그레인은 문의(lead) 기준이다 — inquiry_date 가 split 이전/이후인
    리드로 나누고, 그 리드에 딸린 하위 테이블만 같이 잘라 kpis() 에 넣는다.

    판정 순서(★ 순서가 중요하다 — 못 믿을 조건이 먼저다. 1번을 통과했다고
    바로 성공으로 가지 않는다):

        0. 이전·이후 중 표본이 config.DECOMPOSE_MIN_SAMPLE 미만인 쪽이
           있는가 — 있으면 "판정 보류"(계산은 했지만 결론은 안 낸다)
        1. 주지표(BEFORE_AFTER_PRIMARY)가 BEFORE_AFTER_MOVE 이상 움직였는가
           — 아니면 "효과 없음"
        2. 가드레일(BEFORE_AFTER_GUARD)이 BEFORE_AFTER_GUARD_WORSEN 이상
           나빠졌는가 — 그러면 "주의 필요"
        3. 둘 다 통과 — "성공"

    반환: {"split": str, "이전": kpis dict, "이후": kpis dict,
           "n_이전": int, "n_이후": int,
           "주지표_변화": float, "가드레일_변화": float,
           "판정": str, "color": str, "사유": str | None}
    """
    leads = t["leads"]
    lead_date = to_dt(leads.inquiry_date)
    split_ts = pd.Timestamp(split)

    def _subset(mask: pd.Series) -> dict:
        sel_leads = leads[mask]
        lead_ids = set(sel_leads.lead_id)
        sel_contracts = t["contracts"][t["contracts"].lead_id.isin(lead_ids)]
        return {
            "leads": sel_leads,
            "consultations": t["consultations"][
                t["consultations"].lead_id.isin(lead_ids)],
            "visits": t["visits"][t["visits"].lead_id.isin(lead_ids)],
            "contracts": sel_contracts,
            "rent_payments": t["rent_payments"][
                t["rent_payments"].contract_id.isin(set(sel_contracts.contract_id))],
        }

    before, after = _subset(lead_date < split_ts), _subset(lead_date >= split_ts)
    n_before, n_after = len(before["leads"]), len(after["leads"])
    kb, ka = kpis(before), kpis(after)

    primary_move = ka[BEFORE_AFTER_PRIMARY]["value"] - kb[BEFORE_AFTER_PRIMARY]["value"]
    guard_move = ka[BEFORE_AFTER_GUARD]["value"] - kb[BEFORE_AFTER_GUARD]["value"]

    # 0) 못 믿을 조건이 먼저다 — 표본이 모자라면 움직임 크기와 무관하게 보류.
    if n_before < C.DECOMPOSE_MIN_SAMPLE or n_after < C.DECOMPOSE_MIN_SAMPLE:
        small = "이전" if n_before < n_after else "이후"
        n_small = min(n_before, n_after)
        verdict, color = "판정 보류", "block"
        reason = f"{small} 표본 {n_small}건 (최소 {C.DECOMPOSE_MIN_SAMPLE}건)"
    # 1) 주지표가 안 움직였으면 여기서 끝 — 가드레일은 볼 필요도 없다.
    elif abs(primary_move) < BEFORE_AFTER_MOVE:
        verdict, color, reason = "효과 없음", "none", None
    # 2) 움직였다. 그런데 가드레일이 나빠졌으면 "주의 필요" — 성공이 아니다.
    elif guard_move <= -BEFORE_AFTER_GUARD_WORSEN:
        verdict, color, reason = "주의 필요", "warn", None
    # 3) 둘 다 통과.
    else:
        verdict, color, reason = "성공", "ok", None

    return {
        "split": split,
        "이전": kb, "이후": ka,
        "n_이전": n_before, "n_이후": n_after,
        "주지표_변화": primary_move, "가드레일_변화": guard_move,
        "판정": verdict, "color": color, "사유": reason,
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """기간별 추이. 지표 카드의 스파크라인과 아카이브 비교에 쓴다.

    열 이름은 kpis() 의 지표 이름과 같다 — 이름으로 짝을 맞춰 스파크라인을 그린다.

        리드 수      그 달 접수된 리드 수
        전환율       그 달 리드 중 (지금까지) 계약으로 이어진 비율
                    ★ 최근 달일수록 아직 계약이 안 된 리드가 섞여 있어 낮게 보일 수 있다
                    (관측 기간이 짧은 대상을 그대로 비교하는 문제 — retention_funnel과 동일)
        체결소요일    그 달 체결된 계약의 문의~체결 소요일수 중앙값
        납부이행률    그 달 납부 대상 중 정상 납부(paid=True) 비율

    반환: 인덱스가 기간("2025-01"), 열이 지표인 DataFrame
    """
    leads, contracts, payments = t["leads"], t["contracts"], t["rent_payments"]

    lead_month = to_dt(leads.inquiry_date).dt.strftime("%Y-%m")
    n_leads = leads.groupby(lead_month).lead_id.nunique().rename("리드 수")

    contracted_leads = set(contracts.lead_id)
    conv = (leads.assign(월=lead_month, 계약여부=leads.lead_id.isin(contracted_leads))
                 .groupby("월")["계약여부"].mean() * 100).rename("전환율")

    lead_dates = to_dt(leads.set_index("lead_id")["inquiry_date"])
    c = contracts.copy()
    c["체결월"] = to_dt(c.contract_start_date).dt.strftime("%Y-%m")
    c["소요일"] = (to_dt(c.contract_start_date)
                  - lead_dates.reindex(c.lead_id).values).dt.days
    speed = c.groupby("체결월")["소요일"].median().rename("체결소요일")

    pay_month = payments.payment_month.astype(str)
    quality = (payments.assign(월=pay_month).groupby("월")["paid"]
               .apply(lambda s: s.astype(bool).mean() * 100)).rename("납부이행률")

    return pd.concat([n_leads, conv, speed, quality], axis=1).sort_index()


@st.cache_data(show_spinner=False)
def kpi_deltas(t: dict) -> dict[str, float | None]:
    """kpis() 각 지표의 "직전 달 대비" 변화량.

    monthly() 열에서 결측을 뺀 마지막 두 값의 차이다 — 대시보드 카드와
    리포트 요약이 서로 다른 계산을 쓰면 숫자가 어긋난다. 이 함수 하나로
    통일해서 둘 다 여기서 값을 가져오게 한다.

    ★ config.PERIOD 종료월 이후는 자른다. rent_payments 는 계약 기간(최대
    12개월)만큼 리드 관측 기간보다 더 뒤까지 남아 있어서, 자르지 않으면
    납부이행률만 다른(더 늦은) 달을 "직전 달"로 잡아 다른 지표와 다른
    시점을 비교하게 된다 — 실제로 표본 1건짜리 꼬리 달과 비교돼 변화량이
    +100%p 처럼 튄 적이 있다. 네 지표를 같은 마지막 달(PERIOD 종료월)에
    맞춰야 서로 비교가 된다.

    반환: {"지표이름": 변화량} — 추이가 2개월 미만이면 None.
    """
    m = monthly(t).loc[:C.PERIOD[1][:7]]
    out: dict[str, float | None] = {}
    for name in kpis(t):
        if name not in m.columns:
            out[name] = None
            continue
        s = m[name].dropna()
        out[name] = float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None
    return out


# ★ 높을수록 나쁜 지표. 내 지표 이름을 넣는다.
HIGHER_IS_WORSE = {"이탈률", "이탈율", "해지율", "불량률", "반품률", "체결소요일"}


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    THRESHOLDS 가 비어 있으면 전부 "ok"로 나온다 — 채우면 색이 갈린다.
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "ok"
    if name in HIGHER_IS_WORSE:
        return ("block" if value > th["위험"]
                else "warn" if value > th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 어느 구간을 보는지. 도메인이 바뀌면 이 표를 갈아끼운다.
#   실험이 없는 도메인이면 비워 둔다.
EXP_STEPS: dict[str, tuple[str, str]] = {
    "EXP-001": ("랜딩방문", "요금제조회"),
    "EXP-002": ("요금제조회", "신청시작"),
    "EXP-003": ("신청시작", "신청완료"),
    "EXP-004": ("요금제조회", "신청시작"),
    "EXP-005": ("요금제조회", "신청시작"),
}


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(srm: dict, n_total: int, days: int | None = None) -> str | None:
    """이 실험을 믿을 수 있는가. **계산하기 전에** 묻는다.

    못 믿을 조건은 하나다 — **표본이 config.DECOMPOSE_MIN_SAMPLE 미만.**
    이 도메인엔 실험(A/B)이 없어 배정 공정성(srm)·최소 기간(days)은
    해당 없음으로 둔다 — 조건이 하나뿐이어도 된다, 억지로 셋을 채우지 않는다.
    (funnel_by() 의 분해 칸을 가리는 기준과 같은 값을 쓴다 — 근거를 하나로 유지)

    하나라도 걸리면 **사유 문자열**을 돌려준다. 돌려주면
    experiment_results() 가 거기서 멈추고 **지표를 계산하지 않는다.**
    다 통과하면 None 을 돌려준다.

    "그래도 회색으로라도 보여주면 안 되나요?"

        안 됩니다. **사람은 본 숫자를 기억합니다.**
        옆에 아무리 경고를 붙여도 회의실에서 인용되는 것은 숫자입니다.

    ★ 사유에는 실제 숫자를 넣는다. "표본 부족"이 아니라
      "표본 12건 (최소 50건)"처럼 — 두루뭉술하면 사람이 판단할 수 없다.

    반환: 못 믿을 이유(str) 또는 None
    """
    if n_total < C.DECOMPOSE_MIN_SAMPLE:
        return f"표본 {n_total}건 (최소 {C.DECOMPOSE_MIN_SAMPLE}건)"
    return None


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    실험이 없는 도메인이면 이 함수는 빈 목록을 돌려준다. 대신 전후 비교
    카드를 만들되 **"인과 주장 불가"를 카드에 박아 둔다.** → DESIGN.md §4-4
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg, fe = t["experiments"], t["experiment_assignments"], t["funnel_events"]
    reach = {s: set(fe.loc[fe.funnel_step == s, "visitor_id"]) for s in C.FUNNEL_STEPS}
    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        n_total = int((asg.experiment_id == eid).sum())
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
        }

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        reason = trust_check(srm, n_total)
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        if eid not in EXP_STEPS:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_STEPS 에 이 실험의 구간이 없습니다.")
            out.append(row)
            continue
        sf, stp = EXP_STEPS[eid]
        a = asg[asg.experiment_id == eid][["visitor_id", "variant", "assigned_at"]]
        a = a[a.visitor_id.isin(reach[sf])]
        a = a.assign(conv=a.visitor_id.isin(reach[stp]).astype(int))
        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2:
            row.update(verdict="데이터 없음", color="none")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, step_from=sf, step_to=stp, assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것
        # ★ 아래는 통신사 컬럼(is_churned)이다. 내 가드레일 지표로 바꾼다.
        row["guard"] = None
        if "유지율" in str(e.guardrail_metric) and "customers" in t:
            cu = t["customers"]
            m = cu.merge(a[["visitor_id", "variant"]], on="visitor_id", how="inner")
            if len(m) and m.variant.nunique() == 2:
                ret = m.groupby("variant", observed=True).is_churned.mean()
                row["guard"] = {
                    "name": e.guardrail_metric,
                    "control": float(1 - ret["control"]),
                    "treatment": float(1 - ret["treatment"]),
                    "delta": float((1 - ret["treatment"]) - (1 - ret["control"])),
                }

        # 판정 — ★ 3%p 는 예시다. 내 가드레일 기준으로 바꾼다.
        sig = r["p"] < 0.05
        guard_bad = row["guard"] is not None and row["guard"]["delta"] < -0.03
        if guard_bad:
            # 주지표가 좋아져도 가드레일이 무너지면 성공이 아니다
            row.update(verdict="주의 필요", color="warn",
                       reason="주지표는 개선됐으나 가드레일이 악화됐습니다.")
        elif sig and r["lift"] > 0:
            row.update(verdict="성공", color="ok", reason="")
        elif sig:
            row.update(verdict="악화", color="block", reason="")
        else:
            row.update(verdict="효과 없음", color="none",
                       reason="통계적으로 유의한 차이가 없습니다.")
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def channel_efficiency(t: dict) -> pd.DataFrame:
    """비용만 보면 순위가 뒤집힌다. 유지율까지 반영한 유효 비용을 함께 낸다.

    ★ Day3 선택 과제입니다. 안 만들어도 나머지가 돕니다.

    획득 비용이 싼 경로가 실제로 싼 것이 아니다 —
    데려온 대상이 남지 않으면 같은 자리를 다시 채워야 한다.

        유효 비용 = 획득 비용 / 유지율

    비용 개념이 없으면 **투입 공수(인시)**로 해도 된다.
    획득 경로 구분이 없으면 이 함수를 지운다.

    ★ 여기 쓰이는 CHANNEL_CAC 는 **가정값**이다. 광고비 실측 테이블에서
      유도하지 않는다 — 광고비는 개인 단위로 추적되지 않아 가입과 이을 수 없다.
      리포트에 이 값이 들어가면 "가정값 기반"을 문장에 남긴다. → DESIGN.md §4-3

    반환: DataFrame[채널, 방문, 가입, 전환율, CAC, 유지율, 유효CAC, 역전]
    """
    todo("Day3 선택 과제", "채널 효율",
         "내 도메인에 획득 경로 구분이 있습니까? 비용이 없으면 투입 공수로 바꾸십시오.",
         "core/metrics.py  channel_efficiency()")


# ── 제안서 주제 후보 (9주차 Day3) ──────────────────────────────────
def _annual(n: float) -> float:
    """관측 기간(config.PERIOD) 동안의 건수를 연간으로 환산한다."""
    days = (pd.Timestamp(C.PERIOD[1]) - pd.Timestamp(C.PERIOD[0])).days
    months = days / 30.44
    return n / months * 12


@st.cache_data(show_spinner=False)
def proposal_topics(t: dict) -> list[dict]:
    """제안서 주제 후보를 가능한 만큼 뽑는다. 하나만 고르지 않는다.

    ★ Day3 실습 A. 후보를 만드는 곳 넷:

        ① 퍼널 구간   단계 전환율이 가장 낮은 구간과 그다음으로 낮은 구간의 격차
        ② 분해 축     DIM_SOURCE 각 축에서 최고 칸과 최저 칸의 전환율 격차(병목 구간)
        ③ 임계값      config.THRESHOLDS 를 벗어난 지표
        ④ 추세        최근 3개월 평균이 직전 3개월보다 나쁜 지표

    **격차가 작아 기각된 후보도 목록에 남긴다.** 지우지 않고 기각사유만 채운다.
    **못 믿을 조건(표본 미달)에 걸린 칸은 애초에 후보로 만들지 않는다** — 그건
    "차이가 작다"가 아니라 "비교 자체가 안 된다"라서 기각과 다르다.

    반환: [{"키","제목","한줄","규모_연간건수","근거축","구간","기각사유"}]
    규모가 큰 채택 후보가 먼저, 기각된 것은 맨 뒤로 간다.
    """
    f = funnel(t)
    rates = f[f.step_rate.notna()].sort_values("step_rate")
    topics: list[dict] = []

    # ① 퍼널 구간 — 가장 낮은 구간과 그다음으로 낮은 구간의 격차.
    #   이 격차 자체는 "어느 축을 손봐야 할지"를 알려주지 않으므로 기각한다 —
    #   ②(분해 축)가 그 답을 갖고 있다.
    if len(rates) >= 2:
        worst, second = rates.iloc[0], rates.iloc[1]
        bi = int(f.index[f.step == worst.step][0])
        topics.append({
            "키": "funnel_gap", "제목": "퍼널 병목 구간 정체",
            "한줄": (f"{worst.label}({worst.step_rate*100:.1f}%)이 그다음으로 낮은 "
                    f"{second.label}({second.step_rate*100:.1f}%)보다 "
                    f"{(second.step_rate-worst.step_rate)*100:.1f}%p 낮다"),
            "규모_연간건수": round(_annual(f.n.iloc[bi]), 1),
            "근거축": None, "구간": (f.step.iloc[bi-1], worst.step) if bi > 0 else None,
            "기각사유": "구간 자체만으로는 무엇을 손볼지 특정할 수 없다 — 분해 축으로 좁혀야 한다",
        })

    # ② 분해 축 — 병목 구간을 축별로 쪼갠 최고-최저 격차.
    bn = f[f.is_bottleneck].iloc[0]
    bi = max(int(f.index[f.label == bn.label][0]), 1)
    prev_step, gap_step = f.step.iloc[bi - 1], f.step.iloc[bi]
    for dim in DIM_SOURCE:
        g = funnel_by(t, dim, prev_step, gap_step)
        trusted = g[g.믿음]
        if len(trusted) < 2:
            continue
        top = trusted.loc[trusted.전환율.idxmax()]
        bot = trusted.loc[trusted.전환율.idxmin()]
        gap = top.전환율 - bot.전환율
        # ★ 규모는 "최저 칸 하나"가 아니라 "최고 칸보다 낮은 칸 전부"가 최고 칸
        # 수준으로 개선된다고 볼 때의 합계다 — 최저 칸 하나만 보면 개선 규모를
        # 실제보다 작게 잡아 "사업적 임팩트가 안 보인다"는 지적을 받는다
        # (9주차 Day5, 외부 검토에서 지적된 것을 반영해 넓혔다).
        below = trusted[trusted.전환율 < top.전환율]
        extra = (below.도달 * (top.전환율 - below.전환율)).sum()
        topics.append({
            "키": f"dim_{dim}", "제목": f"{dim}별 전환율 격차",
            "한줄": (f"{dim} {bot[dim]}({bot.전환율*100:.1f}%) vs "
                    f"{top[dim]}({top.전환율*100:.1f}%), 격차 {gap*100:.1f}%p"),
            "규모_연간건수": round(_annual(extra), 1),
            "근거축": dim, "구간": (prev_step, gap_step), "기각사유": None,
        })

    # ③ 임계값 — config.THRESHOLDS 를 벗어난 지표.
    k = kpis(t)
    for name, v in k.items():
        if status_of(name, v["value"]) in ("warn", "block"):
            th = C.THRESHOLDS[name]
            topics.append({
                "키": f"threshold_{name}", "제목": f"{name} 임계값 초과",
                "한줄": (f"{name} {v['fmt'].format(v['value'])} — 경고 기준"
                        f"({th['경고']}) 초과"
                        + (f", 위험 기준({th['위험']}) 근접" if name in HIGHER_IS_WORSE
                           and v["value"] > th["위험"] * 0.9 else "")),
                "규모_연간건수": round(_annual(t["contracts"].contract_id.nunique()), 1),
                "근거축": None, "구간": None, "기각사유": None,
            })

    # ④ 추세 — 최근 3개월 평균이 직전 3개월 평균보다 나쁜 지표.
    m = monthly(t).loc[:C.PERIOD[1][:7]]
    if len(m) >= 6:
        recent, prior = m.tail(3), m.iloc[-6:-3]
        for col in m.columns:
            r, p = recent[col].mean(), prior[col].mean()
            worse = (r > p) if col in HIGHER_IS_WORSE else (r < p)
            if not worse:
                continue
            reject = None
            if col == "전환율":
                reject = ("최근월 리드는 아직 계약까지 이어질 시간이 다 지나지 않았다 — "
                          "성과 악화가 아니라 관측 기간 미달일 수 있다")
            elif abs(r - p) < (0.1 * abs(p) if p else 0):
                reject = "월별 표본이 작아(70~100건대) 이 정도 차이는 우연 범위일 수 있다"

            # 규모 — 지표 성격에 따라 "건수"로 환산하는 방식이 다르다.
            if col == "리드 수":
                # 이미 월별 건수다. 그대로 연환산한다.
                scale = _annual(abs(p - r))
            elif col in ("전환율", "납부이행률"):
                # %p 차이를 그 지표의 모집단(월평균 리드 수)에 곱해 건수로 바꾼다.
                scale = _annual(abs(p - r) / 100 * m["리드 수"].tail(3).mean())
            else:
                # 일(day) 단위 등 건수로 직접 못 바꾸는 지표 — 영향받는 계약 건수로 대신한다.
                scale = _annual(t["contracts"].contract_id.nunique())

            topics.append({
                "키": f"trend_{col}", "제목": f"{col} 최근 3개월 하락",
                "한줄": f"최근 3개월 평균 {r:.2f} vs 직전 3개월 평균 {p:.2f}",
                "규모_연간건수": round(scale, 1),
                "근거축": None, "구간": None, "기각사유": reject,
            })

    accepted = sorted([x for x in topics if not x["기각사유"]],
                      key=lambda x: x["규모_연간건수"], reverse=True)
    rejected = sorted([x for x in topics if x["기각사유"]],
                      key=lambda x: x["규모_연간건수"], reverse=True)
    return accepted + rejected


@st.cache_data(show_spinner=False)
def topic_evidence(t: dict, topic_key: str) -> dict:
    """주제 하나에 딸린 근거를 한 번에 모아 돌려준다. ★ Day3 실습 A.

    조회만 한다 — 문장을 만들지 않는다. 없는 것은 None + 사유.

    반환: {"현황": DataFrame, "원인": DataFrame|None, "원인_사유": str|None,
           "규모_연간건수": float, "규모_가정": list[str], "추세": DataFrame}
    """
    topics = {x["키"]: x for x in proposal_topics(t)}
    topic = topics.get(topic_key)
    if topic is None:
        return {"현황": None, "원인": None, "원인_사유": "알 수 없는 주제 키입니다.",
                "규모_연간건수": None, "규모_가정": [], "추세": None}

    현황 = funnel(t)
    원인, 원인_사유 = None, None
    if topic["근거축"]:
        step_from, step_to = topic["구간"]
        원인 = funnel_by(t, topic["근거축"], step_from, step_to)
    else:
        원인_사유 = "이 주제는 축으로 쪼개지 않았다 — 근거축이 정해지지 않았다."

    가정 = []
    if topic["키"].startswith("dim_") or topic["키"] == "funnel_gap":
        가정.append("하위 칸이 상위 칸과 같은 전환율을 보였다면 늘었을 건수로 계산했다"
                    "(가정: 배정 구조는 그대로 두고 전환율만 개선된다고 봄)")
    elif topic["키"].startswith("threshold_"):
        가정.append("영향받는 모집단을 전체 계약 건수로 잡았다"
                    "(가정: 이 지표 초과가 전체 계약에 고르게 영향을 준다고 봄)")

    m = monthly(t).loc[:C.PERIOD[1][:7]]
    return {
        "현황": 현황, "원인": 원인, "원인_사유": 원인_사유,
        "규모_연간건수": topic["규모_연간건수"], "규모_가정": 가정,
        "추세": m.tail(12),
    }
