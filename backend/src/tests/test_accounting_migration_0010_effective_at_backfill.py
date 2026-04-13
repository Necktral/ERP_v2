from __future__ import annotations

import importlib
from datetime import date
from types import SimpleNamespace

import pytest
from django.utils import timezone


@pytest.mark.django_db
def test_backfill_effective_at_uses_chunked_source_lookup(monkeypatch):
    migration = importlib.import_module("apps.kernels.accounting.migrations.0010_intercompany_effective_at")
    monkeypatch.setattr(migration, "BATCH_SIZE", 2)

    now = timezone.now()
    tx_rows = [
        SimpleNamespace(id=1, created_at=now, source_journal_entry_id=11, effective_at=None),
        SimpleNamespace(id=2, created_at=now, source_journal_entry_id=12, effective_at=None),
        SimpleNamespace(id=3, created_at=now, source_journal_entry_id=13, effective_at=None),
        SimpleNamespace(id=4, created_at=now, source_journal_entry_id=None, effective_at=None),
        SimpleNamespace(id=5, created_at=now, source_journal_entry_id=14, effective_at=None),
    ]
    entry_dates = {
        11: date(2026, 3, 1),
        12: date(2026, 3, 2),
        13: date(2026, 3, 3),
        14: date(2026, 3, 4),
    }

    class IntercompanyManager:
        def __init__(self, rows):
            self._rows = rows
            self.bulk_batches: list[list[int]] = []

        def using(self, alias):
            return self

        def all(self):
            return self

        def only(self, *args):
            return self

        def iterator(self, chunk_size):
            assert chunk_size == 2
            return iter(self._rows)

        def bulk_update(self, pending, fields, batch_size):
            assert fields == ["effective_at"]
            assert batch_size == 2
            self.bulk_batches.append([int(row.id) for row in pending])

    class JournalManager:
        def __init__(self, rows):
            self._rows = rows
            self.filter_calls: list[tuple[int, ...]] = []
            self._selected_ids: tuple[int, ...] = ()

        def using(self, alias):
            return self

        def filter(self, **kwargs):
            selected = tuple(int(v) for v in kwargs.get("id__in", []))
            self.filter_calls.append(selected)
            self._selected_ids = selected
            return self

        def values(self, *args):
            return [
                {"id": int(row_id), "entry_date": self._rows[int(row_id)]}
                for row_id in self._selected_ids
                if int(row_id) in self._rows
            ]

    intercompany_manager = IntercompanyManager(tx_rows)
    journal_manager = JournalManager(entry_dates)

    class FakeApps:
        @staticmethod
        def get_model(app_label: str, model_name: str):
            if app_label == "accounting" and model_name == "IntercompanyTransaction":
                return SimpleNamespace(objects=intercompany_manager)
            if app_label == "accounting" and model_name == "JournalEntry":
                return SimpleNamespace(objects=journal_manager)
            raise AssertionError(f"unexpected model lookup: {app_label}.{model_name}")

    schema_editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    migration.backfill_effective_at(FakeApps(), schema_editor)

    assert intercompany_manager.bulk_batches == [[1, 2], [3, 4], [5]]
    assert len(journal_manager.filter_calls) == 3
    assert all(len(batch_ids) <= 2 for batch_ids in journal_manager.filter_calls)

    assert tx_rows[0].effective_at.date() == date(2026, 3, 1)
    assert tx_rows[1].effective_at.date() == date(2026, 3, 2)
    assert tx_rows[2].effective_at.date() == date(2026, 3, 3)
    assert tx_rows[3].effective_at == now
    assert tx_rows[4].effective_at.date() == date(2026, 3, 4)
