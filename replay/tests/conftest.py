import os

import pytest


def pytest_sessionstart(session):
    os.environ["SENTRY_DSN"] = ""


@pytest.fixture(autouse=True)
def disable_live_sentry(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
