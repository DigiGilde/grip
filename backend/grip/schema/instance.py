from pydantic import BaseModel


class InstanceInfo(BaseModel):
    name: str
    base_uri: str
    # An instance that holds only fictional example data (INSTANCE_MODE).
    example: bool = False
