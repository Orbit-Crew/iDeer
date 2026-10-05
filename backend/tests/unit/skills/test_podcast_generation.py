"""Tests for skills/public/podcast-generation/scripts/generate.py.

The current script is Volcengine-only: it has no MiniMax provider, no
provider resolution, and no retry/backoff logic. The MiniMax + retry
coverage that existed until 2026-09 was written against a dual-provider
version of the script (commit cd5bedaa7) whose disappearance from the
script looks like a re-seed regression (2b532223b restored the
pre-MiniMax version while sibling skills kept MiniMax); that coverage is
recoverable from git history pending a diagnosis ticket.
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
    ]:
        monkeypatch.delenv(k, raising=False)


def test_text_to_speech_requires_credentials():
    with pytest.raises(ValueError):
        pod.text_to_speech("hello", "zh_male_yangguangqingnian_moon_bigtts")


def test_text_to_speech_decodes_base64(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    captured = {}

    def fake_post(url, headers=None, json=None, **kw):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp({"code": 3000, "data": base64.b64encode(b"volcbytes").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech("hi", "zh_male_yangguangqingnian_moon_bigtts")
    assert out == b"volcbytes"
    assert captured["url"].endswith("/api/v1/tts")
    assert captured["headers"]["Authorization"] == "Bearer;t"
    assert captured["json"]["app"]["appid"] == "a"
    assert captured["json"]["audio"]["voice_type"] == "zh_male_yangguangqingnian_moon_bigtts"
    assert captured["json"]["request"]["text"] == "hi"


def test_text_to_speech_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setattr(pod.requests, "post", lambda *a, **k: FakeResp({}, status_code=500))
    assert pod.text_to_speech("hi", "voice") is None


def test_text_to_speech_returns_none_on_error_code(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setattr(
        pod.requests,
        "post",
        lambda *a, **k: FakeResp({"code": 3001, "message": "bad request"}),
    )
    assert pod.text_to_speech("hi", "voice") is None


@pytest.mark.parametrize(
    ("speaker", "expected_voice"),
    [
        ("male", "zh_male_yangguangqingnian_moon_bigtts"),
        ("female", "zh_female_sajiaonvyou_moon_bigtts"),
    ],
)
def test_process_line_voice_mapping(monkeypatch, speaker, expected_voice):
    seen = {}

    def fake_tts(text, voice_type):
        seen["text"] = text
        seen["voice_type"] = voice_type
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech", fake_tts)
    line = pod.ScriptLine(speaker=speaker, paragraph="hi")

    idx, audio = pod._process_line((0, line, 1))
    assert idx == 0
    assert audio == b"x"
    assert seen["text"] == "hi"
    assert seen["voice_type"] == expected_voice


def test_process_line_returns_none_when_tts_fails(monkeypatch):
    monkeypatch.setattr(pod, "text_to_speech", lambda *_: None)
    line = pod.ScriptLine(speaker="male", paragraph="hi")

    idx, audio = pod._process_line((2, line, 3))
    assert idx == 2
    assert audio is None


def test_tts_node_requires_credentials():
    script = pod.Script(lines=[pod.ScriptLine("male", "a")])
    with pytest.raises(ValueError):
        pod.tts_node(script)


def test_tts_node_empty_script_raises():
    with pytest.raises(ValueError, match="no lines"):
        pod.tts_node(pod.Script())


def test_tts_node_returns_ordered_chunks(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_tts(text, voice_type):
        return text.encode()

    monkeypatch.setattr(pod, "text_to_speech", fake_tts)
    script = pod.Script(
        lines=[
            pod.ScriptLine("male", "a"),
            pod.ScriptLine("female", "b"),
            pod.ScriptLine("male", "c"),
        ]
    )

    assert pod.tts_node(script) == [b"a", b"b", b"c"]


def test_tts_node_skips_failed_lines(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_tts(text, voice_type):
        return None if text == "b" else text.encode()

    monkeypatch.setattr(pod, "text_to_speech", fake_tts)
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])

    assert pod.tts_node(script) == [b"a"]


def test_tts_node_raises_when_all_lines_fail(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setattr(pod, "text_to_speech", lambda *_: None)
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])

    with pytest.raises(ValueError, match="all 2 lines"):
        pod.tts_node(script)


def test_tts_node_default_workers(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    captured = {}
    real_executor = pod.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            captured["max_workers"] = kwargs.get("max_workers", args[0] if args else None)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(pod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(pod, "text_to_speech", lambda *_: b"x")
    script = pod.Script(lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")])

    assert pod.tts_node(script) == [b"x", b"x"]
    assert captured["max_workers"] == 4


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
