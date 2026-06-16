from typing import Optional, TypedDict


class CompanyContext(TypedDict, total=False):
    name: str
    industry: str
    product: str
    audience: str
    tone: str
    mission: str
    uvp: str


class CreativeOutput(TypedDict):
    type: str
    title: str
    content: str
    variations: Optional[list[str]]
