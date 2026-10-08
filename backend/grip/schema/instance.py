from pydantic import BaseModel


class InstanceInfo(BaseModel):
    name: str
    base_uri: str
