from itertools import product
from numbers import Real


def generate_parameter_variations(
    center_params, variations, *, max_variations=100
):
    """Build unique parameter sets around an optimized center point.

    ``variations`` maps parameter names to additive numeric offsets. Zero is
    inserted automatically so the optimized center is always included.
    """
    if not isinstance(max_variations, int) or max_variations <= 0:
        raise ValueError("max_variations must be a positive integer")
    if not variations:
        return []
    unknown = set(variations) - set(center_params)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"parameter_variations contains unknown parameter(s): {names}")

    names = list(variations)
    offset_groups = []
    for name in names:
        center = center_params[name]
        if isinstance(center, bool) or not isinstance(center, Real):
            raise TypeError(
                f"parameter_variations requires a numeric center for {name!r}"
            )
        offsets = list(variations[name])
        if not offsets:
            raise ValueError(f"parameter_variations[{name!r}] must not be empty")
        if any(isinstance(item, bool) or not isinstance(item, Real) for item in offsets):
            raise TypeError(
                f"parameter_variations[{name!r}] offsets must be numeric"
            )
        offset_groups.append(list(dict.fromkeys([*offsets, 0])))

    combination_count = 1
    for offsets in offset_groups:
        combination_count *= len(offsets)
    if combination_count > max_variations:
        raise ValueError(
            "parameter variations produce "
            f"{combination_count} combinations; max_variations={max_variations}"
        )

    generated = []
    seen = set()
    for offsets in product(*offset_groups):
        params = dict(center_params)
        applied = {}
        for name, offset in zip(names, offsets):
            center = center_params[name]
            value = center + offset
            if isinstance(center, int):
                value = int(value)
            params[name] = value
            applied[name] = offset
        key = tuple((name, repr(value)) for name, value in sorted(params.items()))
        if key not in seen:
            seen.add(key)
            generated.append((params, applied, all(value == 0 for value in offsets)))
    return generated
