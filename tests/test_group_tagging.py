"""Unit tests for shared/group_tagging.py — per-parent sub-group logic.

Two INDEPENDENT dimensions of per-parent sub-groups, each mutually-exclusive
within itself but coexisting across:
  - login outcomes:  "<parent> / Try to restore" | "<parent> / Password Changed"
  - review outcomes: "<parent> / Posted"          | "<parent> / Not Posted"

An account always STAYS in its parent group. Marking one dimension never
disturbs the other (a Posted account that later fails login keeps BOTH tags;
a successful login clears only the login tag, never the Posted tag).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import group_tagging as gt


# ── marking: login dimension ─────────────────────────────────────────────────

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


def test_switching_login_diagnosis_replaces_within_dimension():
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
    assert gt.apply_subgroup(['Try to restore'], ['SD-152'], gt.RESTORE_LEAF) == [
        'SD-152', 'SD-152 / Try to restore'
    ]


def test_mark_empty_falls_back_to_default():
    assert gt.apply_subgroup([], [], gt.RESTORE_LEAF) == [
        'default', 'default / Try to restore'
    ]


# ── marking: review dimension ────────────────────────────────────────────────

def test_mark_posted_keeps_parent():
    assert gt.apply_subgroup(['SD-152'], [], gt.POSTED_LEAF) == [
        'SD-152', 'SD-152 / Posted'
    ]


def test_mark_not_posted_keeps_parent():
    assert gt.apply_subgroup(['SD-152'], [], gt.NOT_POSTED_LEAF) == [
        'SD-152', 'SD-152 / Not Posted'
    ]


def test_posted_to_not_posted_replaces_within_dimension():
    current = ['SD-152', 'SD-152 / Posted']
    assert gt.apply_subgroup(current, [], gt.NOT_POSTED_LEAF) == [
        'SD-152', 'SD-152 / Not Posted'
    ]


# ── cross-dimension independence ─────────────────────────────────────────────

def test_review_tag_coexists_with_login_tag():
    # account flagged "Try to restore" then posted -> keeps BOTH
    current = ['SD-152', 'SD-152 / Try to restore']
    assert gt.apply_subgroup(current, [], gt.POSTED_LEAF) == [
        'SD-152', 'SD-152 / Try to restore', 'SD-152 / Posted'
    ]


def test_login_tag_coexists_with_review_tag():
    current = ['SD-152', 'SD-152 / Posted']
    assert gt.apply_subgroup(current, [], gt.RESTORE_LEAF) == [
        'SD-152', 'SD-152 / Posted', 'SD-152 / Try to restore'
    ]


# ── unmarking (login success) — only clears the login dimension ──────────────

def test_login_success_strips_login_keeps_posted():
    current = ['SD-152', 'SD-152 / Posted', 'SD-152 / Try to restore']
    assert gt.strip_subgroups(current, [], leaves=gt.LOGIN_LEAVES) == [
        'SD-152', 'SD-152 / Posted'
    ]


def test_strip_login_noop_leaves_posted_intact():
    # has_special must report False for the login dimension when only Posted is set
    assert gt.has_special(['SD-152', 'SD-152 / Posted'], leaves=gt.LOGIN_LEAVES) is False
    assert gt.has_special(['SD-152', 'SD-152 / Try to restore'], leaves=gt.LOGIN_LEAVES) is True


def test_strip_default_removes_all_specials():
    current = ['SD-152', 'SD-152 / Try to restore', 'SD-152 / Posted']
    assert gt.strip_subgroups(current, []) == ['SD-152']


def test_strip_legacy_standalone_uses_previous():
    assert gt.strip_subgroups(['Try to restore'], ['SD-152'], leaves=gt.LOGIN_LEAVES) == ['SD-152']


# ── helpers ──────────────────────────────────────────────────────────────────

def test_real_groups_filters_all_specials():
    groups = ['SD-152', 'SD-152 / Try to restore', 'Password Changed',
              'SD-152 / Posted', 'Not Posted', 'VIP']
    assert gt.real_groups(groups) == ['SD-152', 'VIP']
