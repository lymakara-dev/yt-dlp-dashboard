"""Queue ordering: enqueue assigns positions, claim pops in position order."""
from __future__ import annotations

import asyncio

from app.db import engine
from app.models import Job, JobStatus
from app.queue import JobManager
from sqlmodel import Session


def _make_queued(*urls: str) -> list[int]:
    ids: list[int] = []
    with Session(engine) as s:
        jobs = [Job(url=u, status=JobStatus.queued) for u in urls]
        s.add_all(jobs)
        s.commit()
        for j in jobs:
            s.refresh(j)
            ids.append(j.id)
    return ids


def test_enqueue_assigns_sequential_positions():
    a, b, c = _make_queued("a", "b", "c")
    mgr = JobManager()

    async def _run():
        for jid in (a, b, c):
            await mgr.enqueue(jid)

    asyncio.run(_run())

    with Session(engine) as s:
        assert [s.get(Job, i).queue_position for i in (a, b, c)] == [1, 2, 3]


def test_claim_next_pops_in_position_order():
    a, b, c = _make_queued("a", "b", "c")
    mgr = JobManager()
    asyncio.run(_enqueue_all(mgr, [a, b, c]))

    # Give c the lowest position so it must be claimed first.
    with Session(engine) as s:
        s.get(Job, c).queue_position = 0
        s.commit()

    assert mgr._claim_next() == c
    assert mgr._claim_next() == a
    assert mgr._claim_next() == b
    assert mgr._claim_next() is None  # all claimed


def test_claim_next_marks_downloading():
    (a,) = (_make_queued("a")[0],)
    mgr = JobManager()
    asyncio.run(mgr.enqueue(a))
    assert mgr._claim_next() == a
    with Session(engine) as s:
        assert s.get(Job, a).status == JobStatus.downloading


async def _enqueue_all(mgr: JobManager, ids: list[int]) -> None:
    for jid in ids:
        await mgr.enqueue(jid)


def test_reorder_endpoint_rewrites_positions(client):
    a, b, c = _make_queued("a", "b", "c")
    # Seed positions 1,2,3 so there's a defined starting order.
    with Session(engine) as s:
        for pos, jid in enumerate((a, b, c), start=1):
            s.get(Job, jid).queue_position = pos
        s.commit()

    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [c, a, b]})
    assert resp.status_code == 200

    with Session(engine) as s:
        assert s.get(Job, c).queue_position == 1
        assert s.get(Job, a).queue_position == 2
        assert s.get(Job, b).queue_position == 3

    body = resp.json()
    assert [item["id"] for item in body["items"]] == [c, a, b]


def test_reorder_skips_unknown_and_nonqueued_ids(client):
    a, b = _make_queued("a", "b")
    # 999999 does not exist; it must be ignored, not error.
    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [b, 999999, a]})
    assert resp.status_code == 200
    with Session(engine) as s:
        assert s.get(Job, b).queue_position == 1
        assert s.get(Job, a).queue_position == 2


def test_reorder_omitted_queued_jobs_keep_relative_order(client):
    a, b, c, d = _make_queued("a", "b", "c", "d")
    with Session(engine) as s:
        for pos, jid in enumerate((a, b, c, d), start=1):
            s.get(Job, jid).queue_position = pos
        s.commit()

    # Only a subset is listed; omitted queued jobs (b, d) must keep their
    # original relative order and sort after the listed ones.
    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [c, a]})
    assert resp.status_code == 200

    with Session(engine) as s:
        assert s.get(Job, c).queue_position == 1
        assert s.get(Job, a).queue_position == 2
        assert s.get(Job, b).queue_position == 3
        assert s.get(Job, d).queue_position == 4

    body = resp.json()
    assert [item["id"] for item in body["items"]] == [c, a, b, d]


def test_reorder_skips_nonqueued_status_id(client):
    a, b = _make_queued("a", "b")
    # A downloading job must be skipped: not repositioned, not returned.
    with Session(engine) as s:
        d = Job(url="d", status=JobStatus.downloading)
        s.add(d)
        s.commit()
        s.refresh(d)
        d_id = d.id
        d_pos = d.queue_position

    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [b, d_id, a]})
    assert resp.status_code == 200

    with Session(engine) as s:
        assert s.get(Job, b).queue_position == 1
        assert s.get(Job, a).queue_position == 2
        # The downloading job is untouched by the reorder.
        assert s.get(Job, d_id).queue_position == d_pos
        assert s.get(Job, d_id).status == JobStatus.downloading

    body = resp.json()
    assert d_id not in [item["id"] for item in body["items"]]
    assert [item["id"] for item in body["items"]] == [b, a]


def test_bulk_cancel_cancels_queued_jobs(client):
    a, b, c = _make_queued("a", "b", "c")
    resp = client.post("/api/downloads/cancel", json={"ids": [a, b, 999999]})
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == 2  # 999999 skipped

    with Session(engine) as s:
        assert s.get(Job, a).status == JobStatus.cancelled
        assert s.get(Job, b).status == JobStatus.cancelled
        assert s.get(Job, c).status == JobStatus.queued  # untouched


def test_list_active_returns_non_terminal_in_queue_order(client):
    a, b, c = _make_queued("a", "b", "c")
    with Session(engine) as s:
        # queued positions: a=3, b=1, c=2
        s.get(Job, a).queue_position = 3
        s.get(Job, b).queue_position = 1
        s.get(Job, c).queue_position = 2

        downloading = Job(url="d", status=JobStatus.downloading, queue_position=5)
        scheduled = Job(url="e", status=JobStatus.scheduled, queue_position=0)
        completed = Job(url="f", status=JobStatus.completed, queue_position=4)
        s.add_all([downloading, scheduled, completed])
        s.commit()
        s.refresh(downloading)
        s.refresh(scheduled)
        s.refresh(completed)
        downloading_id = downloading.id
        scheduled_id = scheduled.id
        completed_id = completed.id

    resp = client.get("/api/downloads/active")
    assert resp.status_code == 200
    body = resp.json()

    ids = [item["id"] for item in body["items"]]
    assert completed_id not in ids
    # Ordered by queue_position: scheduled(0), b(1), c(2), a(3), downloading(5)
    assert ids == [scheduled_id, b, c, a, downloading_id]
    assert body["total"] == 5


def test_reorder_dedupes_repeated_ids(client):
    a, b = _make_queued("a", "b")
    with Session(engine) as s:
        s.get(Job, a).queue_position = 1
        s.get(Job, b).queue_position = 2
        s.commit()

    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [a, a, b]})
    assert resp.status_code == 200

    body = resp.json()
    assert [item["id"] for item in body["items"]] == [a, b]

    with Session(engine) as s:
        assert s.get(Job, a).queue_position == 1
        assert s.get(Job, b).queue_position == 2


def test_bulk_cancel_skips_already_terminal_jobs(client):
    a, b = _make_queued("a", "b")
    with Session(engine) as s:
        done = Job(url="done", status=JobStatus.completed)
        s.add(done)
        s.commit()
        s.refresh(done)
        done_id = done.id

    resp = client.post("/api/downloads/cancel", json={"ids": [a, done_id, b]})
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == 2  # terminal job not counted

    with Session(engine) as s:
        assert s.get(Job, a).status == JobStatus.cancelled
        assert s.get(Job, b).status == JobStatus.cancelled
        # The already-completed job is left untouched, not re-cancelled.
        assert s.get(Job, done_id).status == JobStatus.completed
