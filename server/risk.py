"""Growth, promise grading, unusual-move statistics, profit comparison and a credit scorecard.

Pure functions with no database, so each one can be tested on its own. Every threshold is
written out here so it can be read and changed. Money is in Rs crore unless stated.
"""

import math

# ---------------------------------------------------------------- growth

def pct_change(old, new):
    """Percent change from `old` to `new`, divided by the size of the base: (new - old) / |old| x 100.

    The base can be negative (a loss). Dividing by |old| keeps the sign meaningful: a move from -100
    to +50 is +150%, an improvement, and a widening loss is negative. None if the base is zero or missing.
    """
    if old is None or new is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


# ---------------------------------------------------------------- promises

# Share of the promised growth that was delivered, and the label for each band.
GRADE_BANDS = ((100.0, "met"), (90.0, "nearly met"), (50.0, "partly met"))


def achievement_pct(target, actual):
    """How much of the promise was delivered, as a percent of the target.

    14.95 against a target of 15 gives 99.7. A promised decline is compared with its sign kept,
    so -5 promised and -6 delivered gives 120. None if the target is zero or a value is missing.
    """
    if target is None or actual is None or target == 0:
        return None
    return actual / target * 100


def grade(achievement):
    """The verdict label for an achievement percentage. None if there is no achievement."""
    if achievement is None:
        return None
    for floor, label in GRADE_BANDS:
        if achievement >= floor:
            return label
    return "missed"


# ---------------------------------------------------------------- unusual moves

Z_MIN_POINTS = 10   # fewer past observations than this gives no reliable spread, so no alert


def z_score(history, current, threshold=2.0, min_points=Z_MIN_POINTS):
    """(z, is_outlier) for `current` against `history`.

    z = (current - mean) / sample standard deviation of history. The standard deviation is
    never negative, so dividing by it is always safe. Returns (0.0, False) when there are fewer
    than `min_points` observations or when the history has no spread.
    """
    n = len(history)
    if n < min_points or n < 2:
        return 0.0, False
    mean = sum(history) / n
    variance = sum((x - mean) ** 2 for x in history) / (n - 1)
    spread = math.sqrt(variance)
    if spread == 0:
        return 0.0, False
    z = (current - mean) / spread
    return round(z, 2), abs(z) >= threshold


# ---------------------------------------------------------------- operating profit versus PBT

GAP_FLAG_POINTS = 10.0   # growth rates this many points apart are flagged


def profit_view(ebitda_yoy, pbt_yoy, pbt=None, ebitda=None, weight=0.5):
    """Compares operating profit (screener's EBITDA) with PBT, which also includes other income and finance costs.

    blended = weight x EBITDA growth + (1 - weight) x PBT growth. The weight is shown with the result,
    so the reader can change it. The gap is flagged when the two rates differ by GAP_FLAG_POINTS or more.
    pbt_above_operating_profit_pct is approximate: PBT minus operating profit, as a share of PBT.
    """
    gap = None if ebitda_yoy is None or pbt_yoy is None else round(pbt_yoy - ebitda_yoy, 1)
    blended = None if gap is None else round(weight * ebitda_yoy + (1 - weight) * pbt_yoy, 1)
    share = None
    if pbt and pbt > 0 and ebitda is not None:
        share = round((pbt - ebitda) / pbt * 100, 1)
    if gap is None:
        note = "Not enough data to compare."
    elif abs(gap) >= GAP_FLAG_POINTS:
        note = ("Profit and operating profit are moving apart. Check other income, finance costs "
                "and one-off items in the filing.")
    else:
        note = "Profit and operating profit are moving together."
    return {
        "ebitda_yoy_pct": ebitda_yoy,
        "pbt_yoy_pct": pbt_yoy,
        "gap_pts": gap,
        "blended_yoy_pct": blended,
        "weight_on_ebitda": weight,
        "pbt_above_operating_profit_pct": share,
        "formula": f"blended = {weight:.1f} x EBITDA growth + {1 - weight:.1f} x PBT growth",
        "note": note,
    }


# ---------------------------------------------------------------- credit scorecard

# Each measure scores 0 to 3 points. The weights below turn points into a score out of 100.
CREDIT_WEIGHTS = {"interest_cover": 30, "leverage": 30, "pat_margin": 20, "ebitda_trend": 20}

# Score floor, rating, and the underwriting view for that rating. Checked from the top down.
RATINGS = (
    (75, "Strong", "Lend on standard terms"),
    (55, "Adequate", "Lend with covenants"),
    (35, "Weak", "Refer for review"),
    (float("-inf"), "Stressed", "Decline"),
)


def ttm_from_quarters(quarters):
    """Trailing four quarters summed (revenue, EBITDA, PAT), and the four before them for the EBITDA trend.

    Oldest first, as stored. None if there are fewer than four quarters. The trend is None
    if there are fewer than eight. A missing quarter value makes that total None.
    """
    if len(quarters) < 4:
        return None

    def total(rows, key):
        values = [r.get(key) for r in rows]
        return None if any(v is None for v in values) else sum(values)

    last = quarters[-4:]
    prior = quarters[-8:-4] if len(quarters) >= 8 else None
    return {
        "revenue": total(last, "revenue"),
        "ebitda": total(last, "ebitda"),
        "pat": total(last, "pat"),
        "ebitda_prior": total(prior, "ebitda") if prior else None,
    }


def _interest_points(cover, interest):
    if interest <= 0:
        return 3                      # no interest expense
    if cover is None:
        return 0
    return 3 if cover >= 6 else 2 if cover >= 3 else 1 if cover >= 1.5 else 0


def _leverage_points(leverage):
    if leverage is None:
        return 0                      # operating profit is zero or negative
    return 3 if leverage <= 0.5 else 2 if leverage <= 1.5 else 1 if leverage <= 3 else 0


def _margin_points(margin):
    if margin is None:
        return 0
    return 3 if margin >= 10 else 2 if margin >= 5 else 1 if margin >= 0 else 0


def _trend_points(trend):
    if trend is None:
        return 0
    return 3 if trend >= 5 else 2 if trend >= 0 else 1 if trend >= -10 else 0


ASSUMPTIONS = [
    "Debt, cash and interest are entered by you. They are not in the stored data.",
    "Operating profit is screener.in's EBITDA. It is an approximation, not the filing's figure.",
    "Trailing figures are the last four reported quarters. The trend compares them with the four before.",
    "Thresholds are illustrative assumptions for a teaching scorecard, not a bank's approved model.",
]


def credit_model(ttm, debt, cash, interest):
    """A transparent credit scorecard. Returns the metrics, points, score out of 100, rating and view."""
    revenue, ebitda, pat = ttm.get("revenue"), ttm.get("ebitda"), ttm.get("pat")
    cover = ebitda / interest if interest > 0 and ebitda is not None else None
    leverage = (debt - cash) / ebitda if ebitda is not None and ebitda > 0 else None
    margin = pat / revenue * 100 if pat is not None and revenue else None
    trend = pct_change(ttm.get("ebitda_prior"), ebitda)

    points = {
        "interest_cover": _interest_points(cover, interest),
        "leverage": _leverage_points(leverage),
        "pat_margin": _margin_points(margin),
        "ebitda_trend": _trend_points(trend),
    }
    score = round(sum(points[k] * CREDIT_WEIGHTS[k] / 3 for k in CREDIT_WEIGHTS), 1)
    rating, view = next((label, action) for floor, label, action in RATINGS if score >= floor)
    return {
        "metrics": {
            "interest_cover_x": None if cover is None else round(cover, 2),
            "net_debt": round(debt - cash, 1),
            "net_debt_to_ebitda_x": None if leverage is None else round(leverage, 2),
            "pat_margin_pct": None if margin is None else round(margin, 1),
            "ebitda_trend_pct": None if trend is None else round(trend, 1),
        },
        "points": points,
        "score": score,
        "rating": rating,
        "view": view,
        "assumptions": ASSUMPTIONS,
    }


SHOCKS_PCT = list(range(-60, 21, 10))   # EBITDA change applied to the trailing figure
DEBT_SCALES = (0.75, 1.0, 1.25)         # the entered debt, scaled down and up


def sensitivity(ttm, debt, cash, interest, shocks=SHOCKS_PCT, debt_scales=DEBT_SCALES):
    """Score across EBITDA shocks, one line per debt level. Interest is held constant, so a fall in
    EBITDA shows up in interest cover, leverage and trend."""
    ebitda = ttm.get("ebitda")
    series = []
    for scale in debt_scales:
        scores = []
        for shock in shocks:
            shocked = {**ttm, "ebitda": None if ebitda is None else ebitda * (1 + shock / 100)}
            scores.append(credit_model(shocked, debt * scale, cash, interest)["score"])
        series.append({"debt_scale": scale, "debt": round(debt * scale, 1), "scores": scores})
    return {"shocks_pct": list(shocks), "series": series}
