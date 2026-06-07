"""Per-parent sub-group tagging for account outcomes.

Pure, dependency-free helpers. An account always STAYS in its parent group and
gains a per-parent sub-group named ``"<parent> / <leaf>"``. The UI renders any
group containing ``" / "`` indented under its parent.

There are two INDEPENDENT dimensions, each mutually-exclusive within itself but
coexisting across:

  - login outcomes:  "Try to restore" (suspended) | "Password Changed"
  - review outcomes: "Posted"                      | "Not Posted"

Marking within one dimension replaces the other leaf of the SAME dimension but
never touches the other dimension. A successful login strips only the login
dimension (``strip_subgroups(..., leaves=LOGIN_LEAVES)``), leaving any review
tag intact.

These functions take/return plain lists of group-name strings so they can be
unit-tested in isolation from profile persistence.
"""

RESTORE_LEAF = 'Try to restore'
PASSWORD_CHANGED_LEAF = 'Password Changed'
POSTED_LEAF = 'Posted'
NOT_POSTED_LEAF = 'Not Posted'

LOGIN_LEAVES = (RESTORE_LEAF, PASSWORD_CHANGED_LEAF)
REVIEW_LEAVES = (POSTED_LEAF, NOT_POSTED_LEAF)
_ALL_LEAVES = LOGIN_LEAVES + REVIEW_LEAVES

SEP = ' / '


def subgroup_name(parent: str, leaf: str) -> str:
    """Compose the per-parent sub-group name, e.g. 'SD-152 / Try to restore'."""
    return f"{parent}{SEP}{leaf}"


def _leaf_of(name: str):
    """Return the auto-tag leaf for a group name, or None if it's a real group.

    Matches both per-parent sub-groups ('X / Posted') and legacy bare leaves
    ('Posted')."""
    if not name:
        return None
    if name in _ALL_LEAVES:
        return name
    for leaf in _ALL_LEAVES:
        if name.endswith(f"{SEP}{leaf}"):
            return leaf
    return None


def category_of(leaf: str) -> tuple:
    """The dimension (tuple of leaves) a leaf belongs to."""
    if leaf in LOGIN_LEAVES:
        return LOGIN_LEAVES
    if leaf in REVIEW_LEAVES:
        return REVIEW_LEAVES
    return ()


def is_special_group(name: str) -> bool:
    """True if a group name is an auto-tag (sub-group or legacy bare leaf)."""
    return _leaf_of(name) is not None


def has_special(groups, leaves=None) -> bool:
    """True if any group is an auto-tag. Restrict to a dimension via `leaves`."""
    target = set(leaves) if leaves is not None else set(_ALL_LEAVES)
    return any(_leaf_of(g) in target for g in (groups or []))


def real_groups(groups) -> list:
    """Drop ALL auto-tag groups, keeping real parent groups (order-preserved,
    de-duplicated)."""
    out = []
    for g in (groups or []):
        if g and _leaf_of(g) is None and g not in out:
            out.append(g)
    return out


def _base_parents(current, previous) -> list:
    """Real parent group(s): from `current`, then `previous`, then ['default']."""
    return real_groups(current) or real_groups(previous) or ['default']


def apply_subgroup(current, previous, leaf: str) -> list:
    """Return the new groups list after flagging with `leaf`.

    Keeps every real parent group, keeps sub-groups from the OTHER dimension,
    drops the SAME dimension's existing sub-groups (so switching within a
    dimension replaces), and appends '<primary parent> / <leaf>'. Idempotent.
    """
    cat = set(category_of(leaf))
    parents = _base_parents(current, previous)
    parent = parents[0]
    result = list(parents)
    for g in (current or []):
        lf = _leaf_of(g)
        if lf is not None and lf not in cat and g not in result:
            # keep the other dimension's tag untouched
            result.append(g)
    sub = subgroup_name(parent, leaf)
    if sub not in result:
        result.append(sub)
    return result


def strip_subgroups(current, previous, leaves=None) -> list:
    """Return the groups list with auto-tag sub-groups removed, keeping parents.

    `leaves` restricts removal to one dimension (e.g. LOGIN_LEAVES on a
    successful login keeps any review tag). Falls back to `previous` (then
    ['default']) only if nothing real remains (legacy bare-leaf data).
    """
    target = set(leaves) if leaves is not None else set(_ALL_LEAVES)
    result = []
    for g in (current or []):
        lf = _leaf_of(g)
        if lf is None:
            if g and g not in result:
                result.append(g)
        elif lf not in target:
            if g not in result:
                result.append(g)
    if not result:
        result = real_groups(previous) or ['default']
    return result
