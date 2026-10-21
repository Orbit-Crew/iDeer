import os
import subprocess
import sys

from app.device_control.identity import persistent_broker_key
from app.device_control.protocol import public_key_text


def test_broker_identity_is_stable_across_process_restart(tmp_path):
    path = tmp_path / "broker" / "signing.key"
    first = public_key_text(persistent_broker_key(path).public_key())
    code = "import sys;from app.device_control.identity import persistent_broker_key;from app.device_control.protocol import public_key_text;print(public_key_text(persistent_broker_key(sys.argv[1]).public_key()))"
    child = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True, check=True)
    assert child.stdout.strip() == first
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
