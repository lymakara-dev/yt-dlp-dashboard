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
