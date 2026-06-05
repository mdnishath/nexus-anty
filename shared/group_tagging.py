"""Per-parent sub-group tagging for login outcomes.

Pure, dependency-free helpers used by the login flow to tag a profile as
"Try to restore" (account suspended/rejected) or "Password Changed" WITHOUT
removing it from its parent group.

Policy: a flagged account stays in its parent group AND gains a sub-group named
``"<parent> / Try to restore"`` (or ``"<parent> / Password Changed"``). The
sub-group is a sibling entry in the profile's ``groups`` array; the UI renders
any group containing ``" / "`` indented under its parent. On a later successful
login the sub-group tags are stripped and the parent is preserved.

These functions take/return plain lists of group-name strings so they can be
unit-tested in isolation from profile persistence.
"""

RESTORE_LEAF = 'Try to restore'
PASSWORD_CHANGED_LEAF = 'Password Changed'
SEP = ' / '

_LEAVES = (RESTORE_LEAF, PASSWORD_CHANGED_LEAF)


def subgroup_name(parent: str, leaf: str) -> str:
    """Compose the per-parent sub-group name, e.g. 'SD-152 / Try to restore'."""
    return f"{parent}{SEP}{leaf}"


def is_special_group(name: str) -> bool:
    """True if a group name is an auto-tag — either a per-parent sub-group
    ('X / Try to restore') or a legacy bare leaf ('Try to restore')."""
    if not name:
        return False
    if name in _LEAVES:
        return True
    return any(name.endswith(f"{SEP}{leaf}") for leaf in _LEAVES)


def has_special(groups) -> bool:
    """True if any group in the list is an auto-tag sub-group/leaf."""
    return any(is_special_group(g) for g in (groups or []))


def real_groups(groups) -> list:
    """Drop auto-tag groups, keeping real parent groups in their original order
    (de-duplicated)."""
    out = []
    for g in (groups or []):
        if g and not is_special_group(g) and g not in out:
            out.append(g)
    return out


def _base_parents(current, previous) -> list:
    """The real parent group(s): from `current`, falling back to `previous`,
    finally to ['default']."""
    return real_groups(current) or real_groups(previous) or ['default']


def apply_subgroup(current, previous, leaf: str) -> list:
    """Return the new groups list after flagging with `leaf`.

    Keeps every real parent group, drops any pre-existing auto-tag sub-groups
    (so switching diagnosis replaces the old tag), and appends
    '<primary parent> / <leaf>'. Idempotent.
    """
    base = _base_parents(current, previous)
    parent = base[0]
    sub = subgroup_name(parent, leaf)
    result = list(base)
    if sub not in result:
        result.append(sub)
    return result


def strip_subgroups(current, previous) -> list:
    """Return the groups list with all auto-tag sub-groups removed, keeping the
    parent(s). Falls back to `previous` (then ['default']) only if `current`
    held no real groups (legacy bare-leaf data)."""
    return _base_parents(current, previous)
