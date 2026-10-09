"""Keep Feishu SDK failure simulations isolated from pytest's error handling."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.parametrize("case", ["test_run_ws_exception", "test_run_ws_exception_when_not_running"])
def test_websocket_failure_test_preserves_exception_processing(case):
    # Exercise the existing test through pytest, with collection occurring while
    # its SDK failure simulation is active, as it can in a large suite.
    script = dedent("""
        import gc
        import sys
        import pytest

        collected = False
        triggered = False

        class PendingFinalizer:
            def __init__(self):
                self.cycle = self

            def __del__(self):
                global collected
                collected = True
                raise ValueError("pending finalizer")

        def profile(frame, event, arg):
            global triggered
            if event == "call" and frame.f_code.co_name == "_run_ws" and not triggered:
                triggered = True
                PendingFinalizer()
                gc.collect()

        class CollectionPlugin:
            @pytest.hookimpl(hookwrapper=True)
            def pytest_runtest_call(self, item):
                previous = sys.getprofile()
                sys.setprofile(profile)
                try:
                    yield
                finally:
                    sys.setprofile(previous)

        result = pytest.main([sys.argv[1], "-q"], plugins=[CollectionPlugin()])
        print(f"COLLECTION_PROBE triggered={triggered} collected={collected}")
        raise SystemExit(result)
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, f"tests/unit/channels/test_feishu_channel.py::TestRunWs::{case}"],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert "COLLECTION_PROBE triggered=True collected=True" in output
    assert result.returncode == 0, output[-4000:]
