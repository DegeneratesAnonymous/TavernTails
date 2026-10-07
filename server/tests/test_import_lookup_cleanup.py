from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.agents.characters import _WidgetLookup
from server.agents.sessions import _require_session_member


@pytest.mark.parametrize(('fields', 'patterns', 'expected'), [
    ({'Species': 'Elf', 'Race': 'Human'}, [r'\brace\b', r'\bspecies\b'], 'Human'),
    ({'Race 2': 'Elf', 'Race 1': 'Human'}, [r'race'], 'Elf'),
    ({'Race': '', 'Species': 'Human'}, [r'race', r'species'], 'Human'),
    ({'Race': '   ', 'Species': 'Human'}, [r'race', r'species'], None),
    ({'LEVEL': '+12'}, [r'level'], '+12'),
    ({}, [r'race'], None),
])
def test_widget_lookup_preserves_pattern_priority_and_field_order(fields, patterns, expected):
    assert _WidgetLookup(fields).text(patterns) == expected


@pytest.mark.parametrize(('value', 'expected'), [('+3', 3), ('-2 bonus', -2), ('0', 0), ('unknown', None)])
def test_widget_integer_preserves_signed_and_zero_values(value, expected):
    assert _WidgetLookup({'Score': value}).integer(['score']) == expected


@pytest.mark.parametrize('meta', [
    {'owner': 'PLAYER@EXAMPLE.COM'},
    {'invites': ['player@example.com']},
    {'invites': [{'email': 'player@example.com', 'status': 'pending'}]},
    {'members': [{'email': 'PLAYER@EXAMPLE.COM'}]},
])
def test_membership_guard_preserves_owner_invite_and_member_access(meta):
    user = SimpleNamespace(email=' Player@Example.com ', username='player')
    assert _require_session_member(meta, user) == 'player@example.com'


def test_membership_guard_preserves_denial_status_and_message():
    user = SimpleNamespace(email='outsider@example.com', username='outsider')
    with pytest.raises(HTTPException) as error:
        _require_session_member({'owner': 'player@example.com'}, user)
    assert error.value.status_code == 403
    assert error.value.detail == 'Not a member of this session'
