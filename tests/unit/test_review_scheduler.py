from datetime import date

import pytest

from app.services.review_scheduler import schedule_review


DAY = date(2026, 9, 29)


@pytest.mark.parametrize("score,level,expected_date", [
    (1, 1, date(2026, 9, 30)),
    (2, 2, date(2026, 10, 2)),
    (3, 3, date(2026, 10, 29)),
    (4, 3, date(2026, 10, 29)),
    (5, 4, date(2026, 12, 28)),
])
def test_review_scores(score, level, expected_date):
    result = schedule_review(2, score, DAY)
    assert (result.level, result.next_review_date) == (level, expected_date)


def test_review_level_5():
    result = schedule_review(5, 5, DAY)
    assert result.level == 5 and result.next_review_date == date(2027, 3, 28)
