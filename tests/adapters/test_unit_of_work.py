from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from bayios.adapters.db.unit_of_work import SqlAlchemyUnitOfWork

_SampleBase = declarative_base()


class Sample(_SampleBase):
    __tablename__ = "samples"
    id = Column(Integer, primary_key=True)
    name = Column(String)


def test_sqlalchemy_uow_does_not_expire_loaded_objects_on_read() -> None:
    engine = create_engine("sqlite:///:memory:")
    _SampleBase.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)

    with sm() as s:
        s.add(Sample(id=1, name="Sample Item"))
        s.commit()

    uow = SqlAlchemyUnitOfWork(sm)
    with uow:
        item = uow.session.get(Sample, 1)
        assert item is not None
        assert item.name == "Sample Item"

    # Context manager has exited; item must remain readable outside of session!
    assert item.id == 1
    assert item.name == "Sample Item"


def test_sqlalchemy_uow_rolls_back_on_exception() -> None:
    engine = create_engine("sqlite:///:memory:")
    _SampleBase.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)

    uow = SqlAlchemyUnitOfWork(sm)
    with pytest.raises(RuntimeError), uow:
        uow.session.add(Sample(id=2, name="Should Rollback"))
        raise RuntimeError("Failure")

    with sm() as s:
        assert s.get(Sample, 2) is None


def test_sqlalchemy_uow_rolls_back_uncommitted_writes_on_exit() -> None:
    engine = create_engine("sqlite:///:memory:")
    _SampleBase.metadata.create_all(engine)
    sm = sessionmaker(bind=engine, expire_on_commit=False)

    uow = SqlAlchemyUnitOfWork(sm)
    with uow:
        uow.session.add(Sample(id=3, name="Uncommitted"))
        # uow.commit() is intentionally NOT called

    with sm() as s:
        assert s.get(Sample, 3) is None
