"""Unit tests for shared/group_tagging.py — per-parent sub-group logic.

When a batch login marks an account as "Try to restore" (suspended) or
"Password Changed", the account must STAY in its parent group and ALSO gain a
sub-group named "<parent> / Try to restore" (or "<parent> / Password Changed").
On a later successful login the sub-group tags are stripped, parent preserved.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import group_tagging as gt


# ── marking ──────────────────────────────────────────────────────────────────

def test_mark_restore_keeps_parent_and_adds_subgroup():
    assert gt.apply_subgroup(['SD-152'], [], gt.RESTORE_LEAF) == [
        'SD-152', 'SD-152 / Try to restore'
    ]


def test_mark_password_changed_keeps_parent_and_adds_subgroup():
    assert gt.apply_subgroup(['SD-152'], [], gt.PASSWORD_CHANGED_LEAF) == [
        'SD-152', 'SD-152 / Password Changed'
    ]


def test_mark_is_idempotent_no_duplicate():
    once = gt.apply_subgroup(['SD-152'], [], gt.RESTORE_LEAF)
    twice = gt.apply_subgroup(once, [], gt.RESTORE_LEAF)
    assert twice == ['SD-152', 'SD-152 / Try to restore']


def test_switching_diagnosis_replaces_other_subgroup():
    # was password-changed, now suspended -> drop pw sub, keep parent, add restore sub
    current = ['SD-152', 'SD-152 / Password Changed']
    assert gt.apply_subgroup(current, [], gt.RESTORE_LEAF) == [
        'SD-152', 'SD-152 / Try to restore'
    ]


def test_multi_parent_attaches_to_primary_keeps_others():
    current = ['SD-152', 'VIP']
    assert gt.apply_subgroup(current, [], gt.RESTORE_LEAF) == [
        'SD-152', 'VIP', 'SD-152 / Try to restore'
    ]


def test_legacy_standalone_recovers_parent_from_previous():
    # old data: account was moved to bare "Try to restore", parent saved in previous_groups
    current = ['Try to restore']
    previous = ['SD-152']
    assert gt.apply_subgroup(current, previous, gt.RESTORE_LEAF) == [
        'SD-152', 'SD-152 / Try to restore'
    ]


def test_mark_empty_falls_back_to_default():
    assert gt.apply_subgroup([], [], gt.RESTORE_LEAF) == [
        'default', 'default / Try to restore'
    ]


# ── unmarking (on successful login) ──────────────────────────────────────────

def test_strip_removes_subgroup_keeps_parent():
    current = ['SD-152', 'SD-152 / Try to restore']
    assert gt.strip_subgroups(current, []) == ['SD-152']


def test_strip_removes_both_kinds():
    current = ['SD-152', 'SD-152 / Try to restore', 'SD-152 / Password Changed']
    assert gt.strip_subgroups(current, []) == ['SD-152']


def test_strip_legacy_standalone_uses_previous():
    assert gt.strip_subgroups(['Try to restore'], ['SD-152']) == ['SD-152']


def test_strip_noop_when_no_special_returns_base():
    assert gt.strip_subgroups(['SD-152'], []) == ['SD-152']


# ── helpers ──────────────────────────────────────────────────────────────────

def test_has_special_detects_subgroups_and_standalone():
    assert gt.has_special(['SD-152', 'SD-152 / Try to restore']) is True
    assert gt.has_special(['Password Changed']) is True
    assert gt.has_special(['SD-152', 'VIP']) is False


def test_real_groups_filters_specials():
    groups = ['SD-152', 'SD-152 / Try to restore', 'Password Changed', 'VIP']
    assert gt.real_groups(groups) == ['SD-152', 'VIP']
