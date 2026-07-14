"""LiveQwen — the Qwen Cloud transport, exercised fully offline.

No real network call is ever made: the OpenAI client's `.embeddings.create`
/ `.chat.completions.create` and the module-level `httpx.post`/`httpx.get`
are monkeypatched with small fakes that mimic the real response shapes
(verified against the DashScope/OpenAI-compatible docs referenced in
live.py's own docstring). This exercises LiveQwen's real batching,
normalization, JSON-schema parsing, and error-handling logic — the same
code that would run against the real endpoint — without DASHSCOPE_API_KEY
or a socket.
"""

from __future__ import annotations

import json

import pytest

from lamplight_memory.transport.live import BASE_URL, LiveQwen

# --------------------------------------------------------------------------- #
# __init__ — key resolution
# --------------------------------------------------------------------------- #


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        LiveQwen()


def test_explicit_api_key_used():
    tr = LiveQwen(api_key="explicit-key")
    assert tr.api_key == "explicit-key"
    assert tr.name == "live"
    assert tr.dim == 256
    assert tr.client.base_url is not None
    assert str(tr.client.base_url).rstrip("/") == BASE_URL.rstrip("/")


def test_env_api_key_used(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
    tr = LiveQwen()
    assert tr.api_key == "env-key"


def test_custom_dim_propagates():
    tr = LiveQwen(api_key="k", dim=64)
    assert tr.dim == 64


# --------------------------------------------------------------------------- #
# fakes for the OpenAI-compatible client surface
# --------------------------------------------------------------------------- #


class _FakeEmbeddingItem:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddings:
    def __init__(self, responder):
        self._responder = responder
        self.calls: list[dict] = []

    def create(self, model, input, dimensions):  # noqa: A002
        self.calls.append({"model": model, "input": list(input), "dimensions": dimensions})
        return self._responder(model, input, dimensions)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeChatResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responder):
        self._responder = responder
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responder(**kwargs)


class _FakeChat:
    def __init__(self, responder):
        self.completions = _FakeCompletions(responder)


class _FakeClient:
    def __init__(self, embed_responder=None, chat_responder=None):
        self.embeddings = _FakeEmbeddings(embed_responder)
        self.chat = _FakeChat(chat_responder)


# --------------------------------------------------------------------------- #
# embed() — batching (chunks of 10) + L2 normalization + zero-vector guard
# --------------------------------------------------------------------------- #


def test_embed_batches_and_normalizes():
    def responder(model, input, dimensions):
        assert model == "text-embedding-v4"
        assert dimensions == 8
        # index in reverse to prove the sort-by-index step matters
        data = [
            _FakeEmbeddingItem(i, [3.0, 4.0] + [0.0] * (dimensions - 2))
            for i in range(len(input))
        ][::-1]
        return _FakeEmbeddingResponse(data)

    tr = LiveQwen(api_key="k", dim=8)
    tr.client = _FakeClient(embed_responder=responder)
    texts = [f"note {i}" for i in range(15)]  # forces 2 batches (10 + 5)
    out = tr.embed(texts)
    assert len(out) == 15
    for vec in out:
        norm = sum(x * x for x in vec) ** 0.5
        assert norm == pytest.approx(1.0)
    assert len(tr.client.embeddings.calls) == 2
    assert len(tr.client.embeddings.calls[0]["input"]) == 10
    assert len(tr.client.embeddings.calls[1]["input"]) == 5


def test_embed_zero_vector_not_divided():
    def responder(model, input, dimensions):
        return _FakeEmbeddingResponse(
            [_FakeEmbeddingItem(0, [0.0] * dimensions)]
        )

    tr = LiveQwen(api_key="k", dim=4)
    tr.client = _FakeClient(embed_responder=responder)
    out = tr.embed(["anything"])
    assert out == [[0.0, 0.0, 0.0, 0.0]]


# --------------------------------------------------------------------------- #
# rerank() — DashScope-native endpoint via httpx
# --------------------------------------------------------------------------- #


class _FakeHttpResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("boom")

    def json(self):
        return self._payload


def test_rerank_scores_aligned_by_index(monkeypatch):
    import httpx

    def fake_post(url, headers=None, json=None, timeout=None):
        assert "rerank" in url
        assert json["model"] == "qwen3-rerank"
        n = len(json["input"]["documents"])
        # deliberately out of order, string indices (DashScope returns strings)
        results = [
            {"index": str(n - 1 - i), "relevance_score": str(round(0.1 * i, 2))}
            for i in range(n)
        ]
        return _FakeHttpResponse({"output": {"results": results}})

    monkeypatch.setattr(httpx, "post", fake_post)
    tr = LiveQwen(api_key="k")
    scores = tr.rerank("falls risk", ["doc a", "doc b", "doc c"])
    assert len(scores) == 3
    # index 2 got relevance_score "0.0" (i=0), index 1 got "0.1", index 0 got "0.2"
    assert scores == [0.2, 0.1, 0.0]


# --------------------------------------------------------------------------- #
# extract() — structured JSON -> Episode list, default fields
# --------------------------------------------------------------------------- #


def test_extract_builds_episodes_with_defaults_and_overrides():
    payload = {
        "episodes": [
            {
                "type": "observation",
                "text": "erythema on forearm",
                "entities": ["cefazolin", "skin_reaction"],
                "polarity": "neg",
                "decay_class": "critical",
                "resolves": None,
                "why_hint": "verify before next dose",
            },
            {
                # minimal record: entities/polarity/resolves/why_hint all
                # rely on extract()'s raw.get(...) defaults
                "type": "action",
                "text": "gave lunch",
                "decay_class": "routine",
            },
        ]
    }

    def chat_responder(**kwargs):
        assert kwargs["model"] == "qwen3.7-plus"
        assert kwargs["response_format"]["type"] == "json_schema"
        return _FakeChatResponse(json.dumps(payload))

    tr = LiveQwen(api_key="k")
    tr.client = _FakeClient(chat_responder=chat_responder)
    episodes = tr.extract("Bed 9 shift note text", bed=9, shift=6)

    assert len(episodes) == 2
    e1, e2 = episodes
    assert e1.id == "ep-09-06-1"
    assert e1.bed == 9 and e1.shift == 6
    assert e1.ts == ""  # engine assigns the ward-clock ts
    assert set(e1.entities) == {"cefazolin", "skin_reaction"}
    assert e1.polarity == "neg"
    assert e1.decay_class.value == "critical"

    assert e2.id == "ep-09-06-2"
    assert e2.entities == []  # defaulted
    assert e2.polarity == "neutral"  # defaulted
    assert e2.resolves is None
    assert e2.why_hint is None


# --------------------------------------------------------------------------- #
# brief_prose() — valid JSON vs malformed JSON fallback
# --------------------------------------------------------------------------- #


def test_brief_prose_returns_parsed_dict():
    def chat_responder(**kwargs):
        assert kwargs["response_format"] == {"type": "json_object"}
        return _FakeChatResponse(json.dumps({"sbar": "S: ...", "why_tonight": "..."}))

    tr = LiveQwen(api_key="k")
    tr.client = _FakeClient(chat_responder=chat_responder)
    out = tr.brief_prose({"facts": "x", "why": "y", "bed": 9})
    assert out == {"sbar": "S: ...", "why_tonight": "..."}


def test_brief_prose_malformed_json_returns_none():
    def chat_responder(**kwargs):
        return _FakeChatResponse("not valid json {{{")

    tr = LiveQwen(api_key="k")
    tr.client = _FakeClient(chat_responder=chat_responder)
    assert tr.brief_prose({"facts": "x"}) is None


# --------------------------------------------------------------------------- #
# transcribe() — fun-asr async task submit + poll loop
# --------------------------------------------------------------------------- #


def test_transcribe_succeeds_on_first_poll(monkeypatch):
    import httpx

    calls = {"submit": 0, "poll": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["submit"] += 1
        assert "X-DashScope-Async" in headers
        return _FakeHttpResponse({"output": {"task_id": "task-1"}})

    def fake_get(url, headers=None, timeout=None):
        calls["poll"] += 1
        return _FakeHttpResponse(
            {"output": {"task_status": "SUCCEEDED", "results": {"text": "hello"}}}
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    tr = LiveQwen(api_key="k")
    out = tr.transcribe("s3://bucket/audio.wav")
    assert json.loads(out) == {"text": "hello"}
    assert calls["submit"] == 1
    assert calls["poll"] == 1


def test_transcribe_defaults_to_raw_output_when_no_results_key(monkeypatch):
    import httpx

    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_id": "t"}}),
    )
    monkeypatch.setattr(
        httpx, "get",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_status": "SUCCEEDED"}}),
    )
    tr = LiveQwen(api_key="k")
    out = tr.transcribe("audio.wav")
    assert json.loads(out) == {"task_status": "SUCCEEDED"}


@pytest.mark.parametrize("status", ["FAILED", "CANCELED"])
def test_transcribe_failed_or_canceled_raises(monkeypatch, status):
    import httpx

    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_id": "t"}}),
    )
    monkeypatch.setattr(
        httpx, "get",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_status": status}}),
    )
    tr = LiveQwen(api_key="k")
    with pytest.raises(RuntimeError):
        tr.transcribe("audio.wav")


def test_transcribe_times_out(monkeypatch):
    import time

    import httpx

    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_id": "t"}}),
    )
    monkeypatch.setattr(
        httpx, "get",
        lambda *a, **k: _FakeHttpResponse({"output": {"task_status": "RUNNING"}}),
    )
    monkeypatch.setattr(time, "sleep", lambda seconds: None)  # skip the real 2s waits
    tr = LiveQwen(api_key="k")
    with pytest.raises(TimeoutError):
        tr.transcribe("audio.wav")
