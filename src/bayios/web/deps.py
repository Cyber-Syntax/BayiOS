from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from bayios.application.ports.health import HealthProbe
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_health_probe(container: ContainerDep) -> HealthProbe:
    return container.health_probe()


def get_unit_of_work(container: ContainerDep) -> UnitOfWork:
    return container.unit_of_work()
