from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Inventory(StrictModel):
    A: Annotated[int, Field(strict=True, ge=0, le=1000)]
    B: Annotated[int, Field(strict=True, ge=0, le=1000)]

class Supply(StrictModel):
    id: str = Field(min_length=1,max_length=80)
    kit: Literal['A','B']
    quantity: Annotated[int, Field(strict=True,ge=0,le=1000)]
    eta: Annotated[int, Field(strict=True,ge=0,le=1440)]

class Order(StrictModel):
    id: str = Field(pattern=r'^VIN-\d{3}$')
    kit: Literal['A','B']
    model: str = Field(max_length=80)
    route: list[int] = Field(min_length=6,max_length=6)

class DataSet(StrictModel):
    version: str = Field(max_length=80)
    plan: Annotated[int, Field(strict=True,ge=0,le=80)]
    inventory: Inventory
    supply: Supply
    reorder_allowed: bool
    orders: list[Order] = Field(min_length=80,max_length=80)
    assumptions: list[str] = Field(min_length=1,max_length=20)

    @model_validator(mode='after')
    def validate_flow(self):
        if {o.id for o in self.orders} != {f'VIN-{i:03d}' for i in range(1,81)}:
            raise ValueError('Нужны 80 уникальных VIN-001…080')
        if any(o.route != list(range(6)) for o in self.orders):
            raise ValueError('MVP поддерживает маршрут 0…5')
        if any(len(a)>500 for a in self.assumptions):
            raise ValueError('Слишком длинное допущение')
        if self.reorder_allowed and any(o.kit != ('B' if 55<=int(o.id[-3:])<=60 else 'A') for o in self.orders):
            raise ValueError('Разрешённая перестановка требует эталонную комплектацию A/B')
        return self

class Event(StrictModel):
    id: str = Field(min_length=1,max_length=80)
    occurred_at: Annotated[int, Field(strict=True,ge=0,le=1440)]
    received_at: Annotated[int, Field(strict=True,ge=0,le=1440)]
    source: str = Field(min_length=1,max_length=100)
    kind: Literal['fact','assumption']
    event_type: Literal['eta_updated','batch_received','robot_down']
    payload: dict[str, Annotated[int, Field(strict=True)]] = Field(max_length=3)

    @model_validator(mode='after')
    def valid_payload(self):
        key = 'duration' if self.event_type == 'robot_down' else 'eta' if self.event_type == 'eta_updated' else None
        if key and (set(self.payload)!={key} or not 0<=self.payload[key]<=1440):
            raise ValueError('Некорректное событие')
        if self.received_at < self.occurred_at and self.kind == 'fact':
            raise ValueError('Факт не может быть получен раньше возникновения')
        if self.event_type == 'robot_down' and self.payload['duration'] > 180:
            raise ValueError('Сбой должен быть не более 180 мин.')
        if self.event_type == 'batch_received' and self.payload:
            raise ValueError('Поступление относится к существующей партии; payload должен быть пустым')
        return self

class SimulateRequest(StrictModel):
    basis_snapshot_id: str | None = Field(default=None,min_length=1,max_length=80)
    delay: Annotated[int, Field(strict=True,ge=0,le=400)] = 0
    robot_minutes: Annotated[int, Field(strict=True,ge=0,le=180)] = 0
    robot_start: Annotated[int, Field(strict=True,ge=0,le=480)] = 150
    eta_override: Annotated[int, Field(strict=True,ge=0,le=1840)] | None = None
    policy: Literal['none','delivery','reorder'] = 'none'
    decision_time: Annotated[int, Field(strict=True,ge=0,le=480)] = 120
    contribution: Annotated[int, Field(strict=True,ge=0,le=10000000)] = 650000
    data: DataSet | None = None
    events: list[Event] = Field(default_factory=list,max_length=32)
    received_until: Annotated[int, Field(strict=True,ge=0,le=480)] = 120

class SnapshotRequest(StrictModel):
    snapshot_id: str = Field(min_length=1,max_length=80)
    time: Annotated[int, Field(strict=True,ge=0,le=480)] = 120

class ChatRequest(SnapshotRequest):
    previous_snapshot_id: str | None = Field(default=None,min_length=1,max_length=80)
    question: str = Field(min_length=1,max_length=2000)
