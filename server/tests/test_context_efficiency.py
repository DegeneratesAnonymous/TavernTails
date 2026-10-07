import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from server import db
from server.agents import context_collector as collector
from server.agents import context_orchestrator as orchestrator
from server.agents.action_resolution import continuation_issues, resolution_issues


@pytest.fixture
def context_db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, 'engine', engine)
    yield engine
    engine.dispose()


def test_collector_reads_one_snapshot_for_scoring_and_output(context_db, monkeypatch):
    calls = []

    def story(*args, **kwargs):
        calls.append('story')
        return ['Ada waits.']

    def scene(*args):
        calls.append('scene')
        return 'The market is quiet.'

    monkeypatch.setattr(collector, '_load_session_story', story)
    monkeypatch.setattr(collector, '_load_session_scene', scene)
    ctx = collector.collect_context('campaign', session_id='session')
    assert calls == ['story', 'scene']
    assert ctx['recent_story'] == ['Ada waits.']
    assert ctx['current_scene'] == 'The market is quiet.'


def test_explicit_scene_problem_and_stakes_survive_without_threads(context_db):
    packet = orchestrator.orchestrate('campaign', scene_override={
        'problem': 'The bridge is breaking.', 'stakes': 'The wagon will fall.',
    })
    assert packet.scene.current_problem == 'The bridge is breaking.'
    assert packet.scene.immediate_stakes == 'The wagon will fall.'


def test_affiliation_lookup_keeps_duplicate_names_and_secrets_private(context_db):
    with db.Session(context_db) as session:
        session.add_all([
            db.CampaignEntity(id='npc', campaign_id='campaign', entity_type='npc', name='Ada',
                              data={'faction_affiliations': ['IRON GUILD'], 'secrets': ['hidden password']}),
            db.CampaignEntity(id='f1', campaign_id='campaign', entity_type='faction', name='Iron Guild'),
            db.CampaignEntity(id='f2', campaign_id='campaign', entity_type='faction', name='iron guild'),
            db.CampaignEntity(id='f3', campaign_id='campaign', entity_type='faction', name='Other'),
        ])
        session.commit()
    packet = orchestrator.orchestrate('campaign', use_cache=False)
    assert packet.entity_scores['Iron Guild (faction)'] == 30
    assert packet.entity_scores['iron guild (faction)'] == 30
    assert packet.entity_scores['Other (faction)'] == 0
    assert packet.active_npcs[0].secrets_count == 1
    assert 'hidden password' not in packet.for_narrative()


def test_budget_trim_finishes_and_reports_the_final_estimate():
    packet = orchestrator.ContextPacket(
        active_npcs=[orchestrator.NPCContext(name=f'NPC {i}') for i in range(12)],
        story_threads=[orchestrator.StoryThreadContext(title=f'Thread {i}') for i in range(12)],
    )
    orchestrator._trim_to_budget(packet, 0)
    assert packet.active_npcs == []
    assert packet.story_threads == []
    assert packet.token_estimate == orchestrator._estimate_tokens(packet.for_narrative())


def test_budget_keeps_ranked_entities_that_fit():
    packet = orchestrator.ContextPacket(active_npcs=[orchestrator.NPCContext(name='Ada')])
    budget = orchestrator._estimate_tokens(packet.for_narrative())
    orchestrator._trim_to_budget(packet, budget)
    assert [npc.name for npc in packet.active_npcs] == ['Ada']
    assert packet.token_estimate == budget


def test_question_index_keeps_first_resolution_and_ignores_invalid_indices():
    resolutions = [
        {'action_index': [], 'reply': 'Invalid index'},
        {'action_index': '0', 'reply': 'String index'},
        {'action_index': 0, 'status': 'answered', 'reply': 'At dawn.'},
        {'action_index': 0, 'status': 'answered', 'reply': 'At noon.'},
    ]
    actions = ['When did it stop?']
    assert not resolution_issues(actions, resolutions)
    assert not continuation_issues('At DAWN.', actions, resolutions, known_names=[], allow_new_names=True)
    assert continuation_issues('At noon.', actions, resolutions, known_names=[], allow_new_names=True)


def test_question_checks_keep_validation_errors_before_missing_dialogue():
    actions = ['Why?', 'When?']
    resolutions = [{'action_index': i, 'status': 'cannot_answer', 'reply': 'Unknown.'} for i in range(2)]
    issues = continuation_issues('', actions, resolutions, known_names=[], allow_new_names=True)
    assert issues == [
        'Question 0 requires an explicit reason the NPC cannot answer.',
        'Question 1 requires an explicit reason the NPC cannot answer.',
        'Question 0: include the planned reply in the narration.',
        'Question 1: include the planned reply in the narration.',
    ]


def test_relevance_ranking_keeps_recent_order_for_ties(context_db):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    with db.Session(context_db) as session:
        for index, name in enumerate(['Ada', 'Bea', 'Cal']):
            session.add(db.CampaignEntity(
                id=name, campaign_id='campaign', entity_type='npc', name=name,
                data={'primary_goal': 'Find shelter'}, updated_at=now + timedelta(seconds=index),
            ))
        for priority in [1, 10]:
            session.add(db.CampaignEntity(
                id=f't{priority}', campaign_id='campaign', entity_type='story_thread', name=f'Thread {priority}',
                data={'current_priority': priority, 'current_situation': f'Problem {priority}'},
            ))
        session.commit()
    packet = orchestrator.orchestrate('campaign', player_actions=['I ask Ada for directions.'], use_cache=False)
    assert [npc.name for npc in packet.active_npcs] == ['Ada', 'Cal', 'Bea']
    assert [thread.title for thread in packet.story_threads] == ['Thread 10', 'Thread 1']
    assert packet.scene.current_problem == 'Problem 10'


def test_compact_memory_reads_preserve_full_payload_ranking_and_constraints(context_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import event
    from sqlmodel import select

    now = datetime.now(timezone.utc)
    with db.Session(context_db) as session:
        for kind, count in [('npc', 40), ('location', 6), ('story_thread', 6), ('faction', 3), ('world_event', 20)]:
            for i in range(count):
                session.add(db.CampaignEntity(
                    id=f'{kind}{i}', campaign_id='campaign', entity_type=kind, name=f'{kind.title()} {i}',
                    updated_at=now + timedelta(seconds=i),
                    data={'biography': 'large irrelevant history ' * 1000,
                          'primary_goal': 'Find shelter', 'next_likely_action': 'Ask for help',
                          'story_engine': {'goal': 'Protect the bridge', 'deadline': 'dawn'},
                          'faction_affiliations': ['Faction 0'], 'secrets': ['secret password'],
                          'current_priority': 10 if i == 0 else 1,
                          'current_situation': f'The bridge {i} is breaking.', 'stakes': 'The wagon will fall.',
                          'gm_notes': f'Hidden thread {i}', 'opportunities': [f'Clue {i}'],
                          'hidden_elements': [f'Hidden location {i}']},
                ))
        session.add(db.CampaignEntity(id='inactive', campaign_id='campaign', entity_type='npc', name='Inactive', status='inactive'))
        session.add(db.CampaignEntity(id='other', campaign_id='other', entity_type='npc', name='Other'))
        session.commit()
        candidates = orchestrator._load_rankable_entities(session, 'campaign')
    assert len(candidates) == 55
    assert all('biography' not in e.data and 'secrets' not in e.data for e in candidates)
    queries = []
    def record(connection, cursor, statement, parameters, context, executemany):
        queries.append((statement, parameters))
    event.listen(context_db, 'before_cursor_execute', record)
    args = {'campaign_id': 'campaign', 'player_actions': ['I ask Npc 0 about the bridge.'],
            'scene_override': {'location_name': 'Location 0'}, 'use_cache': False}
    compact = orchestrator.orchestrate(**args)
    event.remove(context_db, 'before_cursor_execute', record)
    hydration = [(sql, params) for sql, params in queries if 'campaignentity.id IN' in sql]
    assert len(hydration) == 1
    assert len(hydration[0][1]) <= 18  # campaign ID plus at most 17 full memories
    def full_rows(session, campaign_id):
        return session.exec(select(db.CampaignEntity).where(
            db.CampaignEntity.campaign_id == campaign_id, db.CampaignEntity.status == 'active',
        ).order_by(db.CampaignEntity.updated_at.desc())).all()
    monkeypatch.setattr(orchestrator, '_load_rankable_entities', full_rows)
    baseline = orchestrator.orchestrate(**args)
    assert compact.model_dump(exclude={'generated_at'}) == baseline.model_dump(exclude={'generated_at'})
    assert compact.location.name == 'Location 0'
    assert compact.active_npcs[0].name == 'Npc 0'
    assert compact.story_threads[0].title == 'Story_Thread 0'
    assert 'secret password' not in compact.for_narrative()
