import json
import math

import pytest

from server.agents import references


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(references, '_storage_root', lambda: tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    references._tfidf_index.cache_clear()

    def add(name, texts, **metadata):
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        (folder / 'pages.json').write_text(json.dumps([
            {'page': i + 1, 'text': text, 'snippet': text} for i, text in enumerate(texts)
        ]))
        (folder / 'metadata.json').write_text(json.dumps(metadata))
        return folder

    yield add
    references._tfidf_index.cache_clear()


def test_tfidf_preserves_scores_and_stable_ties(corpus):
    corpus('guide', ['fire fire water', 'water', 'fire fire water', ''])
    hits = references.search_query('fire', top_k=10)
    fire_idf = math.log(5 / 3) + 1
    water_idf = math.log(5 / 4) + 1
    expected = 2 * fire_idf / math.sqrt((2 * fire_idf) ** 2 + water_idf ** 2)
    assert [hit['page'] for hit in hits] == [1, 3]
    assert [hit['score'] for hit in hits] == pytest.approx([expected, expected])
    assert references.search_query('unknown') == []
    assert references.search_query('') == []


def test_index_reused_for_other_queries_and_updated_after_content_changes(corpus):
    folder = corpus('guide', ['fire water'])
    assert references.search_query('fire')
    references.search_query('water')
    assert references._tfidf_index.cache_info().hits == 1
    (folder / 'pages.json').write_text(json.dumps([{'page': 1, 'text': 'ice', 'snippet': 'ice'}]))
    assert references.search_query('fire') == []
    assert references.search_query('ice')[0]['snippet'] == 'ice'
    assert references._tfidf_index.cache_info().misses == 2


def test_cache_does_not_reuse_visibility_or_system_metadata(corpus):
    folder = corpus('guide', ['fire water'], system_ref=False, game_system='D&D 5e')
    assert references.search_query('fire')[0]['snippet'] == 'fire water'
    (folder / 'metadata.json').write_text(json.dumps({'system_ref': True, 'game_system': 'D&D 5e'}))
    hit = references.search_query('fire')[0]
    assert hit['snippet'] is None
    assert hit['paraphrase_required'] is True
    assert references.search_query('fire', include_system=False) == []
    assert references.search_query('fire', game_system='Pathfinder 2e') == []
    assert references.search_query('fire', system_only=True)


def test_tokenless_query_keeps_substring_fallback(corpus):
    corpus('guide', ['A +1 sword', 'A shield'])
    hits = references.search_query('+1')
    assert [hit['page'] for hit in hits] == [1]
    assert hits[0]['score'] == 0.5


def test_index_cache_is_bounded():
    references._tfidf_index.cache_clear()
    for i in range(8):
        references._tfidf_index((f'word {i}',))
    assert references._tfidf_index.cache_info().currsize == 4
    references._tfidf_index.cache_clear()


def test_batch_reads_corpus_once_and_deduplicates_queries(corpus, monkeypatch):
    corpus('guide', ['fire water', 'ice'])
    expected = {q: references.search_query(q) for q in ['fire', 'ice']}
    loads = []
    load = references._load_search_corpus
    def counted(**kwargs):
        loads.append(kwargs)
        return load(**kwargs)
    monkeypatch.setattr(references, '_load_search_corpus', counted)
    assert references.search_queries(['fire', 'ice', 'fire', '']) == expected
    assert len(loads) == 1


def test_batch_continues_after_one_failed_lookup(corpus, monkeypatch):
    corpus('guide', ['fire water'])
    search = references._search_corpus
    def fail_one(q, *args):
        if q == 'ice':
            raise ValueError('bad query')
        return search(q, *args)
    monkeypatch.setattr(references, '_search_corpus', fail_one)
    hits = references.search_queries(['ice', 'fire'])
    assert hits['ice'] == []
    assert hits['fire']
    with pytest.raises(ValueError):
        references.search_query('ice')
