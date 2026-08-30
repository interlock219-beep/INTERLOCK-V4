from datetime import datetime

from pydantic import BaseModel


class GraphNode(BaseModel):
    action_id: str
    agent_id: str
    tool: str
    resource: str
    action_type: str
    status: str
    parent_action_id: str | None
    created_at: datetime


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class IncidentGraphResponse(BaseModel):
    root_action_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class UpstreamResponse(BaseModel):
    action_id: str
    upstream: list[dict[str, object]]
    total: int


class DownstreamResponse(BaseModel):
    action_id: str
    downstream: list[dict[str, object]]
    total: int
