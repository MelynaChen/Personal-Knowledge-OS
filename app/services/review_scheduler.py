from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class SchedulerConfig:
    interval_days: tuple[int, ...] = (0, 1, 7, 30, 90, 180)
    max_level: int = 5
    forget_level: int = 1
    forget_delay_days: int = 1
    uncertain_delay_days: int = 3

    def __post_init__(self):
        if self.max_level < 1 or len(self.interval_days) <= self.max_level or any(x < 0 for x in self.interval_days):
            raise ValueError("invalid scheduler configuration")


@dataclass(frozen=True)
class ScheduleResult:
    level: int
    next_review_date: date


def schedule_review(current_level: int, memory_score: int, completed_date: date,
                    config: SchedulerConfig = SchedulerConfig()) -> ScheduleResult:
    if not isinstance(current_level, int) or not 0 <= current_level <= config.max_level:
        raise ValueError("invalid review level")
    if type(memory_score) is not int or memory_score not in range(1, 6):
        raise ValueError("memory_score must be an integer from 1 to 5")
    if memory_score == 1:
        level, days = config.forget_level, config.forget_delay_days
    elif memory_score == 2:
        level, days = current_level, config.uncertain_delay_days
    else:
        level = min(current_level + (2 if memory_score == 5 else 1), config.max_level)
        days = config.interval_days[level]
    return ScheduleResult(level, completed_date + timedelta(days=days))
