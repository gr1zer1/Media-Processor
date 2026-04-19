from pydantic import BaseModel, ConfigDict, EmailStr,Field, model_validator


class UserSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    


class UserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


class ChangePasswordRequestSchema(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.old_password == self.new_password:
            raise ValueError("New password must be different from old password")
        return self