"""Map an exchange announcement subject line to one of the reference categories.

Rules run first, in order. The first matching rule wins, so specific rules
sit above general ones. Haiku is called only when no rule matches.
"""

import re

CATEGORIES = {
    "results", "M&A", "fund_raise", "management_change", "litigation",
    "insider_trading", "earnings_call", "investor_meetings", "credit_rating",
    "dividend", "bonus_split", "capex", "press_release", "postal_ballot",
    "agm_egm", "pledging", "unclassified",
}

TIER = {
    "results": "high",
    "M&A": "high",
    "fund_raise": "high",
    "management_change": "high",
    "litigation": "high",
    "pledging": "high",
    "credit_rating": "medium",
    "insider_trading": "medium",
    "dividend": "medium",
    "bonus_split": "medium",
    "capex": "medium",
    "earnings_call": "low",
    "investor_meetings": "low",
    "press_release": "low",
    "postal_ballot": "low",
    "agm_egm": "low",
    "unclassified": "hidden",
}

# Order matters. Keep the most specific patterns first.
RULES = [
    (r"transcript|audio recording|call recording|earnings call|conference call", "earnings_call"),
    (r"financial results|quarterly results|annual results|results for the (quarter|year|half)|"
     r"(un)?audited (standalone|consolidated)", "results"),
    (r"credit rating|rating (assigned|upgrad|downgrad|reaffirm)|crisil|icra|care ratings|"
     r"india ratings|brickwork", "credit_rating"),
    (r"pledg|encumb", "pledging"),
    (r"insider|sast|regulation 7|\bpit\b", "insider_trading"),
    (r"postal ballot", "postal_ballot"),
    (r"\bagm\b|\begm\b|annual general meeting|extra[- ]?ordinary general meeting", "agm_egm"),
    (r"bonus|stock split|sub-?division", "bonus_split"),
    (r"dividend|record date", "dividend"),
    (r"analyst (meet|call)|investor (meet|conference)|meeting with (investors|analysts)", "investor_meetings"),
    (r"fund[- ]rais|\bqip\b|rights issue|preferential|institutional placement|buy[- ]?back|"
     r"non[- ]convertible|commercial paper|debentures", "fund_raise"),
    (r"esop|employee stock|allotment|compliance certificate|\besg\b|business responsibility|brsr|"
     r"shareholding pattern|reconciliation of share capital|auditor", "unclassified"),
    (r"acqui|merger|demerger|amalgamat|scheme of (arrangement|amalgamation)|joint venture|"
     r"divest|stake|investment in (a )?(wholly|subsidiar)", "M&A"),
    (r"litigation|lawsuit|penalt|show cause|sebi order|order (of|from|passed by) .*"
     r"(sebi|nclt|nclat|cci|tribunal|court|rbi)|nclt|insolven|restructuring proceeding|"
     r"winding|warning letter|regulatory action|fine(d| imposed)", "litigation"),
    (r"resign|appoint|cessation|retire|re-?designat|managing director|\bmd\b|chief executive|"
     r"\bceo\b|chief financial|\bcfo\b|company secretary|director|key managerial", "management_change"),
    (r"capex|capital expenditure|new (plant|facility|factory|capacity)|capacity expansion|"
     r"greenfield|brownfield|commission(ed|ing) of (plant|facility)", "capex"),
    (r"press release|news|order (win|received|book)|bagged|partnership|collaborat|launch|"
     r"\bmou\b|clarification|rumou?r|newspaper", "press_release"),
]

_COMPILED = [(re.compile(pattern, re.IGNORECASE), category) for pattern, category in RULES]


def classify_rules(subject):
    """Return the category for a subject line, or None if no rule matches."""
    for pattern, category in _COMPILED:
        if pattern.search(subject):
            return category
    return None


def tier_for(category, subject):
    """Tier for a classified announcement. Some categories depend on the wording."""
    s = subject.lower()
    if category == "results":
        # Board-meeting intimations and newspaper ads for results carry no numbers.
        return "low" if re.search(r"intimation|newspaper|advertis|publication", s) else "high"
    if category == "credit_rating":
        return "high" if "downgrad" in s else "medium"
    if category == "earnings_call":
        return "medium" if re.search(r"transcript|recording", s) else "low"
    return TIER[category]


def classify_with_llm(subject, client, model):
    """Ask Haiku for one label. Anything outside the category list becomes 'unclassified'."""
    prompt = (
        "Classify this Indian listed-company exchange announcement into exactly one of these "
        "labels: " + ", ".join(sorted(CATEGORIES)) + ".\n"
        "Reply with the label only.\n\nSubject: " + subject
    )
    message = client.messages.create(
        model=model,
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    label = message.content[0].text.strip()
    return label if label in CATEGORIES else "unclassified"
