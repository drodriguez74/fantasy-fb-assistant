"""
Shared, stateless grading helpers.

Extracted from `PostDraftAnalysisService._grade_from_score` so that both the
real post-draft analysis path and the mock-draft grading path
(`mock_draft_service.py`) use one implementation of the score -> letter grade
thresholds instead of two copies that could drift apart.
"""


def grade_from_score(score: float) -> str:
    """Convert a 0-100 numeric score into a letter grade.

    Thresholds: A >= 90, B >= 80, C >= 70, D >= 60, else F.
    """
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"
