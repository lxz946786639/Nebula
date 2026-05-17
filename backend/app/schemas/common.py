from pydantic import BaseModel


class Message(BaseModel):
    message: str


class HealthStatus(BaseModel):
    status: str
    redis: str
    subconverter: str
