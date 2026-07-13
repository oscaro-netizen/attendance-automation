from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr

class EmployeeBase(BaseModel):
    slack_user_id: str
    slack_username: str
    marsos_email: EmailStr
    marsos_employee_id: str

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    slack_username: Optional[str] = None
    marsos_email: Optional[EmailStr] = None
    marsos_employee_id: Optional[str] = None

class Employee(EmployeeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AttendanceLogBase(BaseModel):
    employee_id: int
    date: datetime
    started: bool
    status: str
    failure_reason: Optional[str] = None
    response_time: Optional[float] = None

class AttendanceLogCreate(AttendanceLogBase):
    started_at: Optional[datetime] = None

class AttendanceLog(AttendanceLogBase):
    id: int
    started_at: Optional[datetime]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
