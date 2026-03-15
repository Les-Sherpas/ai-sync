"""Plan action model."""

from pydantic import BaseModel


class PlanAction(BaseModel):
    action: str
    source_alias: str
    kind: str
    resource: str
    target: str
    target_key: str
    secret_backed: bool = False
    composable: bool = False
