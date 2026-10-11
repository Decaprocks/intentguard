from datetime import UTC, datetime, timedelta

import pytest

from intentguard.demo import DemoCloud
from intentguard.models import iso
from intentguard.service import Service
from intentguard.storage import SQLiteStore


@pytest.fixture
def now():
    return datetime(2026, 10, 11, 12, tzinfo=UTC)


@pytest.fixture
def service(tmp_path, now):
    return Service(SQLiteStore(tmp_path / "test.db"), DemoCloud(), clock=lambda: now)


@pytest.fixture
def payload(now):
    return {
        "resource_id": "i-00000000000000002",
        "owner": "Dhruv",
        "intent_type": "disposable_test",
        "reason": "Disposable review demonstration",
        "expires_at": iso(now + timedelta(days=7)),
        "cpu_max_percent": 10,
    }
