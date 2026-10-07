import asyncio
from threading import Event, Lock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from server.generation_workers import run_generation


@pytest.mark.asyncio
@pytest.mark.parametrize("requests", [1, 5])
async def test_blocked_generation_leaves_api_and_sync_workers_responsive(requests):
    app = FastAPI()
    started = Event()
    release = Event()
    lock = Lock()
    running = 0
    peak = 0

    def generate():
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
            if running == min(requests, 4):
                started.set()
        try:
            assert release.wait(3)
            return {'scene': 'done'}
        finally:
            with lock:
                running -= 1

    @app.get('/generate')
    async def generation():
        return await run_generation(generate)

    @app.get('/status')
    def status():
        return {'ok': True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        tasks = [asyncio.create_task(client.get('/generate')) for _ in range(requests)]
        try:
            assert await asyncio.to_thread(started.wait, 1)
            response = await asyncio.wait_for(client.get('/status'), 0.5)
            assert response.json() == {'ok': True}
        finally:
            release.set()
            results = await asyncio.gather(*tasks)
        assert all(result.json() == {'scene': 'done'} for result in results)
        assert peak <= 4


@pytest.mark.asyncio
async def test_worker_exceptions_reach_existing_route_error_handling():
    def generate():
        raise ValueError('provider failed')

    with pytest.raises(ValueError, match='provider failed'):
        await run_generation(generate)


@pytest.mark.asyncio
async def test_scene_retry_preserves_approved_inputs(monkeypatch):
    from server.agents import sessions

    narrative = sessions.narrative_agent

    seen = []
    def generate(request):
        seen.append(request.model_dump())
        return narrative.NarrativeResponse(narrative='The bridge shakes.', prompt='What do you do?', tone='balanced')
    monkeypatch.setattr(narrative, 'generate_narrative', generate)
    request = narrative.NarrativeRequest(
        scene='Approved opening seed', player='Ada', is_opening_scene=True,
        scene_director_data={'approved_object': 'sealed letter'},
        composer_data={'vivid_image': 'A broken bridge'},
        character_context={'backstory': 'Authored history'},
        campaign_contract={'tone': 'heroic'}, approved_object='sealed letter',
    )
    await sessions._write_scene(request)
    await sessions._write_scene(request, validator_feedback='Keep the stakes concrete.')
    assert seen[1] == {**seen[0], 'validator_feedback': 'Keep the stakes concrete.'}
    assert request.validator_feedback is None
