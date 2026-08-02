from dataclasses import dataclass
from typing import Callable, Iterable, Tuple


@dataclass(frozen=True)
class ConstraintResult:
    feasible: bool
    violations: Tuple[str, ...] = ()

    @classmethod
    def accepted(cls):
        return cls(feasible=True)

    @classmethod
    def rejected(cls, *violations):
        messages = tuple(str(message) for message in violations if str(message))
        return cls(feasible=False, violations=messages or ("constraint failed",))


def evaluate_constraints(
    constraints: Iterable[Callable], value
) -> ConstraintResult:
    violations = []
    for index, constraint in enumerate(constraints):
        outcome = constraint(value)
        name = getattr(constraint, "__name__", f"constraint_{index}")
        if isinstance(outcome, ConstraintResult):
            if not outcome.feasible:
                violations.extend(outcome.violations or (f"{name} failed",))
        elif outcome is None or outcome is True:
            continue
        elif outcome is False:
            violations.append(f"{name} failed")
        elif isinstance(outcome, str):
            if outcome:
                violations.append(outcome)
        else:
            raise TypeError(
                "constraint must return bool, str, None, or ConstraintResult"
            )
    return (
        ConstraintResult.rejected(*violations)
        if violations
        else ConstraintResult.accepted()
    )

