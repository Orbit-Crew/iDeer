from core.audit import AuditKind, LocalAuditLog


def test_local_audit_lists_recent_events_newest_first(tmp_path) -> None:
    log = LocalAuditLog(db_path=tmp_path / "audit.db")

    log.record(AuditKind.TASK, "received", capability="local.files.write")
    log.record(AuditKind.EXECUTION, "completed", capability="local.files.write")

    recent = log.recent(limit=10)

    assert [(entry.kind, entry.action) for entry in recent] == [
        (AuditKind.EXECUTION, "completed"),
        (AuditKind.TASK, "received"),
    ]


def test_local_audit_survives_restart_and_stays_append_only(tmp_path) -> None:
    path = tmp_path / "audit.db"
    LocalAuditLog(db_path=path).record(
        AuditKind.CONSENT, "approved", capability="local.python", digest="abc"
    )

    reopened = LocalAuditLog(db_path=path)
    entry = reopened.recent(limit=5)[0]

    assert entry.action == "approved"
    assert entry.capability == "local.python"
    assert entry.digest == "abc"
    assert reopened.verify().ok is True


def test_a_cleared_log_still_verifies_and_keeps_its_seal(tmp_path) -> None:
    """Clearing hides history; it must not make the remaining chain look forged."""
    path = tmp_path / "audit.db"
    log = LocalAuditLog(db_path=path)
    for index in range(3):
        log.record(AuditKind.TASK, f"received-{index}", capability="local.files.read")
    before_clear = log.recent(limit=0)[0].entry_hash

    log.clear(actor_id="alice")
    reopened = LocalAuditLog(db_path=path)

    assert reopened.verify().ok is True
    assert reopened.verify().entries == 1
    assert [entry.action for entry in reopened.recent(limit=5)] == ["cleared"]
    assert reopened.clearances()[0]["last_entry_hash"] == before_clear
    # The chain resumes from the seal: a later entry verifies against it.
    reopened.record(AuditKind.TASK, "received-after")
    assert LocalAuditLog(db_path=path).verify().ok is True


def test_rewriting_a_row_after_a_clear_is_still_detected(tmp_path) -> None:
    path = tmp_path / "audit.db"
    log = LocalAuditLog(db_path=path)
    log.record(AuditKind.TASK, "received")
    log.clear(actor_id="alice")
    log.record(AuditKind.TASK, "after-clear")

    import sqlite3

    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE audit_entries SET action = 'tampered' WHERE kind = 'task'"
            " AND action = 'after-clear'"
        )
        db.commit()

    result = LocalAuditLog(db_path=path).verify()

    assert result.ok is False
    assert "chain broken" in (result.problem or "")


def test_concurrent_record_keeps_every_entry_and_the_chain_intact(
    tmp_path, monkeypatch
) -> None:
    """05-M2: the runtime loop thread and the tray UI thread both call
    record(); racing writers used to compute the same MAX(seq)+1, so the
    loser escaped as sqlite3.IntegrityError (failing the caller's task or
    UI action). Writers must serialize and leave one intact chain."""
    import threading
    import time

    import core.audit as audit_module

    real_entry_hash = audit_module._entry_hash
    hash_calls = {"count": 0}

    def slowed_entry_hash(previous, seq, at, row):
        # Widen the SELECT->INSERT window so the first writers are all inside
        # it at once; without serialization they all compute the same seq.
        if hash_calls["count"] < 8:
            hash_calls["count"] += 1
            time.sleep(0.05)
        return real_entry_hash(previous, seq, at, row)

    monkeypatch.setattr(audit_module, "_entry_hash", slowed_entry_hash)

    log = LocalAuditLog(db_path=tmp_path / "audit.db")
    thread_count = 8
    per_thread = 25
    barrier = threading.Barrier(thread_count)
    failures: list[BaseException] = []

    def worker(worker_index: int) -> None:
        try:
            barrier.wait()
            for index in range(per_thread):
                log.record(
                    AuditKind.TASK,
                    f"received-{worker_index}-{index}",
                    capability="local.files.read",
                )
        except BaseException as exc:  # noqa: BLE001 - the assertion reports it
            failures.append(exc)

    threads = [
        threading.Thread(target=worker, args=(worker_index,))
        for worker_index in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    entries = log.recent(limit=0)
    assert len(entries) == thread_count * per_thread
    seqs = [entry.seq for entry in entries]
    assert len(set(seqs)) == len(seqs), "racing writers duplicated a seq"
    result = log.verify()
    assert result.ok is True, result.problem


def test_recent_pushes_kind_filter_and_limit_into_sql(
    tmp_path, monkeypatch
) -> None:
    """05-M7: the tray polls recent(limit=1) every second, so the poll must
    not load the whole audit table per call."""
    import sqlite3

    path = tmp_path / "audit.db"
    log = LocalAuditLog(db_path=path)
    log.record(AuditKind.TASK, "received", capability="local.files.write")
    log.record(AuditKind.EXECUTION, "completed", capability="local.files.write")
    log.record(AuditKind.EXECUTION, "failed", capability="local.python")

    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracing_connect)

    recent = log.recent(limit=1, kind=AuditKind.EXECUTION)

    assert [(entry.kind, entry.action) for entry in recent] == [
        (AuditKind.EXECUTION, "failed")
    ]
    polled = [sql for sql in statements if "audit_entries" in sql]
    assert polled, "the poll must hit the audit_entries table"
    assert any("LIMIT 1" in sql for sql in polled), polled
    assert any("kind" in sql.lower() and "where" in sql.lower() for sql in polled), polled
