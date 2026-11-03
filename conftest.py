"""Root conftest: puts this folder on the import path for pytest.

Every test also runs with the developer's model settings removed and with no committed
seed database, so results do not depend on what is set in the shell or in the repo.
"""

import pytest

MODEL_VARS = ["ANTHROPIC_API_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_B64"]


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    for name in MODEL_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FINN_SEED", str(tmp_path / "no-seed.sqlite"))
