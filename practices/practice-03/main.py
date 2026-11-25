"""Практическая 3: User Service, CRUD, JWT и HTTP-интеграции."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging
import os
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("uvicorn.error")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://127.0.0.1:8011/notify/")
POSTS_URL = "https://jsonplaceholder.typicode.com/posts"
# Локальный ключ живёт в памяти процесса. После перезапуска нужно войти заново.
SECRET_KEY = os.getenv("JWT_SECRET") or secrets.token_hex(32)
ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=5.0) as client:
        app.state.http = client
        yield


app = FastAPI(title="User Service", version="1.0.0", lifespan=lifespan)


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    age: int | None = Field(default=None, ge=0, le=150)


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    created_at: datetime
    is_active: bool = True


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class Notification(BaseModel):
    user_id: int
    email: EmailStr
    message: str


# Отдельные хранилища: пользователи сервиса и учётные записи для входа.
users_db: dict[int, User] = {}
accounts_db: dict[str, str] = {}
next_user_id = 1


def email_key(email: str) -> str:
    return email.casefold()


def check_unique_email(email: str, exclude_id: int | None = None):
    for existing in users_db.values():
        if existing.id != exclude_id and email_key(existing.email) == email_key(email):
            raise HTTPException(400, "Email already registered")


def find_user(user_id: int) -> User:
    if user_id not in users_db:
        raise HTTPException(404, "User not found")
    return users_db[user_id]


def current_account(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    unauthorized = HTTPException(
        401, "Invalid or missing token", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        email = payload["sub"]
        if not isinstance(email, str) or email not in accounts_db:
            raise unauthorized
    except InvalidTokenError:
        raise unauthorized
    return email


@app.get("/")
async def root():
    return {"message": "User Service is running!", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/signup", status_code=201)
def signup(credentials: Credentials):
    email = email_key(credentials.email)
    if email in accounts_db:
        raise HTTPException(400, "Account already registered")
    accounts_db[email] = password_hash.hash(credentials.password)
    return {"email": email, "message": "Account created"}


@app.post("/login", response_model=Token)
def login(credentials: Credentials):
    email = email_key(credentials.email)
    stored_hash = accounts_db.get(email)
    if stored_hash is None or not password_hash.verify(credentials.password, stored_hash):
        raise HTTPException(401, "Incorrect email or password")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(minutes=30)},
        SECRET_KEY, algorithm=ALGORITHM,
    )
    return Token(access_token=token)


@app.post("/users/", response_model=User, status_code=201)
async def create_user(user: UserCreate):
    global next_user_id
    check_unique_email(user.email)
    new_user = User(
        **user.model_dump(), id=next_user_id, created_at=datetime.now(timezone.utc)
    )
    users_db[new_user.id] = new_user
    next_user_id += 1
    notification = Notification(
        user_id=new_user.id, email=new_user.email, message=f"Welcome, {new_user.name}!"
    )
    try:
        response = await app.state.http.post(NOTIFICATION_URL, json=notification.model_dump())
        response.raise_for_status()
        logger.info("Notification sent for user %s", new_user.id)
    except (httpx.RequestError, httpx.HTTPStatusError) as error:
        logger.warning("Notification failed for user %s: %s", new_user.id, type(error).__name__)
    return new_user


@app.get("/users/", response_model=list[User])
async def get_users(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    min_age: Annotated[int | None, Query(ge=0, le=150)] = None,
):
    users = list(users_db.values())
    if min_age is not None:
        users = [user for user in users if user.age is not None and user.age > min_age]
    return users[skip:skip + limit]


@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    return find_user(user_id)


@app.put("/users/{user_id}", response_model=User)
async def update_user(
    user_id: int, user: UserCreate, account: Annotated[str, Depends(current_account)],
):
    existing = find_user(user_id)
    check_unique_email(user.email, exclude_id=user_id)
    updated = existing.model_copy(update=user.model_dump())
    users_db[user_id] = updated
    return updated


@app.delete("/users/{user_id}")
async def delete_user(user_id: int, account: Annotated[str, Depends(current_account)]):
    find_user(user_id)
    del users_db[user_id]
    return {"message": f"User {user_id} deleted successfully"}


@app.get("/users/{user_id}/posts")
async def get_posts(user_id: int):
    find_user(user_id)
    try:
        response = await app.state.http.get(POSTS_URL, params={"userId": user_id})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        raise HTTPException(502, "External posts API returned an error") from error
    except httpx.TimeoutException as error:
        raise HTTPException(504, "External posts API timeout") from error
    except (httpx.RequestError, ValueError) as error:
        raise HTTPException(502, "External posts API unavailable or invalid response") from error
