"""Tests for skills/public/podcast-generation/scripts/generate.py.

The script is dual-provider (Volcengine + MiniMax) with retry/backoff.
The MiniMax + retry coverage follows the #3437 lineage (cd5bedaa7 plus
69c160ba7 voice configuration); it was restored from git history after
the 2b532223b re-seed regression reverted the script to the pre-#3437
Volcengine-only version while sibling skills kept MiniMax. Tests that
the interim Volcengine-only suite (b0486a782) added for behavior that
still exists in the restored script are kept; tests asserting the
superseded partial-failure semantics were dropped (the restored script
fails loudly on any failed line, per #3437).
"""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_loader import FakeResp, load  # noqa: E402

pod = load("podcast-generation")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in [
        "VOLCENGINE_TTS_APPID",
        "VOLCENGINE_TTS_ACCESS_TOKEN",
        "VOLCENGINE_TTS_CLUSTER",
        "VOLCENGINE_TTS_VOICE_TYPE_MALE",
        "VOLCENGINE_TTS_VOICE_TYPE_FEMALE",
        "MINIMAX_API_KEY",
        "PODCAST_GENERATION_PROVIDER",
        "MINIMAX_API_HOST",
        "MINIMAX_TTS_MODEL",
        "MINIMAX_TTS_VOICE_MALE",
        "MINIMAX_TTS_VOICE_FEMALE",
        "MINIMAX_TTS_MAX_RETRIES",
    ]:
        monkeypatch.delenv(k, raising=False)
    # never actually sleep during backoff in tests
    monkeypatch.setattr(pod.time, "sleep", lambda *_: None)


# --- Provider resolution ---------------------------------------------------


def test_resolve_prefers_volcengine(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    assert pod._resolve_tts_provider() == "volcengine"


def test_resolve_falls_back_to_minimax(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    assert pod._resolve_tts_provider() == "minimax"


def test_resolve_override(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "minimax")
    assert pod._resolve_tts_provider() == "minimax"


def test_resolve_unknown_raises(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "openai")
    with pytest.raises(ValueError):
        pod._resolve_tts_provider()


def test_tts_node_requires_credentials():
    script = pod.Script(lines=[pod.ScriptLine("male", "a")])
    with pytest.raises(ValueError):
        pod.tts_node(script)


def test_volcengine_without_creds_raises(monkeypatch):
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "volcengine")
    script = pod.Script(lines=[pod.ScriptLine("male", "a")])
    with pytest.raises(ValueError):
        pod.tts_node(script)


# --- MiniMax TTS -------------------------------------------------------------


def test_minimax_tts_decodes_hex(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    captured = {}

    def fake_post(url, headers=None, json=None, **kw):
        captured["url"] = url
        captured["json"] = json
        return FakeResp({"data": {"audio": b"audiobytes".hex(), "status": 2}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hello", "male-qn-qingse")
    assert out == b"audiobytes"
    assert captured["url"].endswith("/v1/t2a_v2")
    assert captured["json"]["voice_setting"]["voice_id"] == "male-qn-qingse"
    assert captured["json"]["output_format"] == "hex"


def test_process_line_minimax_voice_mapping(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    seen = {}

    def fake_tts(text, voice_id):
        seen["voice_id"] = voice_id
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    line = pod.ScriptLine(speaker="female", paragraph="hi")
    idx, audio = pod._process_line((0, line, 1, "minimax"))
    assert audio == b"x"
    assert seen["voice_id"] == "female-tianmei"


def test_process_line_minimax_male_and_override(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    seen = []

    def fake_tts(text, voice_id):
        seen.append(voice_id)
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    male = pod.ScriptLine(speaker="male", paragraph="hi")
    pod._process_line((0, male, 1, "minimax"))
    assert seen[-1] == "male-qn-qingse"
    monkeypatch.setenv("MINIMAX_TTS_VOICE_MALE", "custom-male")
    pod._process_line((0, male, 1, "minimax"))
    assert seen[-1] == "custom-male"


def test_generate_podcast_minimax_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")

    def fake_post(url, headers=None, json=None, **kw):
        return FakeResp({"data": {"audio": b"chunk".hex(), "status": 2}, "base_resp": {"status_code": 0}})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    script = tmp_path / "s.json"
    script.write_text(
        '{"title":"T","locale":"en","lines":[{"speaker":"male","paragraph":"a"},{"speaker":"female","paragraph":"b"}]}',
        encoding="utf-8",
    )
    out = tmp_path / "o.mp3"
    msg = pod.generate_podcast(str(script), str(out), None)
    assert out.read_bytes() == b"chunkchunk"
    assert "Successfully generated podcast" in msg


def _seq_post(responses):
    """Return a fake requests.post that yields the given responses in order."""
    calls = {"n": 0}

    def fake_post(*a, **k):
        resp = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return resp

    return fake_post, calls


def test_minimax_retries_on_rate_limit_code(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1002, "status_msg": "rate limit"}}),
            FakeResp({"base_resp": {"status_code": 1039, "status_msg": "tpm limit"}}),
            FakeResp({"data": {"audio": b"ok".hex()}, "base_resp": {"status_code": 0}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out == b"ok"
    assert calls["n"] == 3  # two retries then success


def test_minimax_retries_on_http_429(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({}, status_code=429),
            FakeResp({"data": {"audio": b"ok".hex()}, "base_resp": {"status_code": 0}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out == b"ok"
    assert calls["n"] == 2


def test_minimax_no_retry_on_auth_error(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1004, "status_msg": "auth failed"}}),
            FakeResp({"data": {"audio": b"never".hex()}, "base_resp": {"status_code": 0}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out is None
    assert calls["n"] == 1  # permanent error: no retry


def test_minimax_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1002, "status_msg": "rate limit"}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=2)
    assert out is None
    assert calls["n"] == 3  # initial attempt + 2 retries


# --- Volcengine TTS ----------------------------------------------------------


def test_volcengine_tts_decodes_base64(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    captured = {}

    def fake_post(url, headers=None, json=None, **kw):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp({"code": 3000, "data": base64.b64encode(b"volcbytes").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_volcengine("hi", "zh_male_yangguangqingnian_moon_bigtts")
    assert out == b"volcbytes"
    assert captured["url"].endswith("/api/v1/tts")
    assert captured["headers"]["Authorization"] == "Bearer;t"
    assert captured["json"]["app"]["appid"] == "a"
    assert captured["json"]["audio"]["voice_type"] == "zh_male_yangguangqingnian_moon_bigtts"
    assert captured["json"]["request"]["text"] == "hi"


def test_volcengine_retries_on_http_5xx(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    fake_post, calls = _seq_post(
        [
            FakeResp({}, status_code=500),
            FakeResp({}, status_code=500),
            FakeResp({"code": 3000, "data": base64.b64encode(b"ok").decode()}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_volcengine("hi", "voice", max_retries=3)
    assert out == b"ok"
    assert calls["n"] == 3  # two transient failures then success


def test_volcengine_gives_up_after_max_retries_on_http_5xx(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    fake_post, calls = _seq_post([FakeResp({}, status_code=500)])
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_volcengine("hi", "voice", max_retries=2)
    assert out is None
    assert calls["n"] == 3  # initial attempt + 2 retries


def test_volcengine_returns_none_on_error_code(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    fake_post, calls = _seq_post([FakeResp({"code": 3001, "message": "bad request"})])
    monkeypatch.setattr(pod.requests, "post", fake_post)
    assert pod.text_to_speech_volcengine("hi", "voice") is None
    assert calls["n"] == 1  # permanent API error: no retry


@pytest.mark.parametrize(
    ("speaker", "env_name", "default_voice"),
    [
        (
            "male",
            "VOLCENGINE_TTS_VOICE_TYPE_MALE",
            "zh_male_yangguangqingnian_moon_bigtts",
        ),
        (
            "female",
            "VOLCENGINE_TTS_VOICE_TYPE_FEMALE",
            "zh_female_sajiaonvyou_moon_bigtts",
        ),
    ],
)
@pytest.mark.parametrize(
    ("configured_voice", "expected_voice"),
    [
        pytest.param(None, None, id="unset"),
        pytest.param("custom-voice", "custom-voice", id="custom"),
        pytest.param("", None, id="empty"),
        pytest.param("   ", None, id="whitespace"),
        pytest.param("  custom-voice  ", "custom-voice", id="padded-custom"),
    ],
)
def test_process_line_volcengine_voice_mapping(monkeypatch, speaker, env_name, default_voice, configured_voice, expected_voice):
    if configured_voice is not None:
        monkeypatch.setenv(env_name, configured_voice)

    seen = {}

    def fake_tts(text, voice_type):
        seen["voice_type"] = voice_type
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_volcengine", fake_tts)
    line = pod.ScriptLine(speaker=speaker, paragraph="hi")

    pod._process_line((0, line, 1, "volcengine"))
    assert seen["voice_type"] == (expected_voice or default_voice)


def test_process_line_returns_none_when_tts_fails(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setattr(pod, "text_to_speech_volcengine", lambda *_: None)
    line = pod.ScriptLine(speaker="male", paragraph="hi")

    idx, audio = pod._process_line((2, line, 3, "volcengine"))
    assert idx == 2
    assert audio is None


# --- tts_node ----------------------------------------------------------------


def test_tts_node_empty_script_raises():
    with pytest.raises(ValueError, match="no lines"):
        pod.tts_node(pod.Script())


def test_tts_node_returns_ordered_chunks(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_tts(text, voice_type):
        return text.encode()

    monkeypatch.setattr(pod, "text_to_speech_volcengine", fake_tts)
    script = pod.Script(
        lines=[
            pod.ScriptLine("male", "a"),
            pod.ScriptLine("female", "b"),
            pod.ScriptLine("male", "c"),
        ]
    )

    assert pod.tts_node(script) == [b"a", b"b", b"c"]


def test_tts_node_raises_on_partial_failure(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    calls = {"n": 0}

    def fake_tts(text, voice_id, **kw):
        calls["n"] += 1
        return b"x" if calls["n"] == 1 else None

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])
    with pytest.raises(ValueError) as e:
        pod.tts_node(script)
    assert "2" in str(e.value)  # mentions failed line number 2


def test_tts_node_defaults_to_one_worker_for_minimax(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    captured = {}
    real_executor = pod.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            captured["max_workers"] = kwargs.get("max_workers", args[0] if args else None)
            super().__init__(*args, **kwargs)

    def fake_tts(text, voice_id):
        return b"x"

    monkeypatch.setattr(pod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])

    assert pod.tts_node(script) == [b"x", b"x"]
    assert captured["max_workers"] == 1


def test_tts_node_keeps_four_worker_default_for_volcengine(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    captured = {}
    real_executor = pod.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            captured["max_workers"] = kwargs.get("max_workers", args[0] if args else None)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(pod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(pod, "text_to_speech_volcengine", lambda text, voice_type: b"x")
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])

    assert pod.tts_node(script) == [b"x", b"x"]
    assert captured["max_workers"] == 4


# --- Mix / markdown / generate_podcast ---------------------------------------


def test_mix_audio_joins_chunks():
    assert pod.mix_audio([b"a", b"b"]) == b"ab"


def test_mix_audio_empty_raises():
    with pytest.raises(ValueError):
        pod.mix_audio([])


def test_generate_markdown_formats_speakers():
    script = pod.Script(lines=[pod.ScriptLine("male", "hello"), pod.ScriptLine("female", "world")])

    md = pod.generate_markdown(script, title="My Show")
    assert md.startswith("# My Show")
    assert "**Host (Male)**: hello" in md
    assert "**Host (Female)**: world" in md


def _script_file(tmp_path):
    script = tmp_path / "s.json"
    script.write_text(
        '{"title":"T","locale":"en","lines":[{"speaker":"male","paragraph":"a"},{"speaker":"female","paragraph":"b"}]}',
        encoding="utf-8",
    )
    return script


def test_generate_podcast_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_post(url, headers=None, json=None, **kw):
        return FakeResp({"code": 3000, "data": base64.b64encode(b"chunk").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = tmp_path / "o.mp3"
    msg = pod.generate_podcast(str(_script_file(tmp_path)), str(out), None)
    assert out.read_bytes() == b"chunkchunk"
    assert "Successfully generated podcast" in msg


def test_generate_podcast_writes_transcript(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_post(url, headers=None, json=None, **kw):
        return FakeResp({"code": 3000, "data": base64.b64encode(b"chunk").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = tmp_path / "o.mp3"
    transcript = tmp_path / "transcript.md"
    msg = pod.generate_podcast(str(_script_file(tmp_path)), str(out), str(transcript))
    assert transcript.exists()
    assert "# T" in transcript.read_text(encoding="utf-8")
    assert "transcript" in msg


def test_generate_podcast_invalid_script_raises(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"title":"T"}', encoding="utf-8")

    with pytest.raises(ValueError, match="missing 'lines'"):
        pod.generate_podcast(str(bad), str(tmp_path / "o.mp3"), None)
