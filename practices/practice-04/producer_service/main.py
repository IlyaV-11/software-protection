"""Producer: HTTP → Kafka через HAProxy или RabbitMQ."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
import time
from typing import Annotated
from uuid import uuid4

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import aio_pika
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9093")


class Order(BaseModel):
    order_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    product: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class Notification(BaseModel):
    user_id: int = Field(gt=0)
    message: str = Field(min_length=1)


class ErrorMessage(BaseModel):
    service: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: str = "error"


@asynccontextmanager
async def lifespan(app):
    producer = AIOKafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode(),
        enable_idempotence=True,
        acks="all",
        request_timeout_ms=5000,
    )
    rabbit = None
    await producer.start()
    try:
        rabbit = await aio_pika.connect_robust(os.environ["RABBITMQ_URL"])
        channel = await rabbit.channel(publisher_confirms=True)
        for topic in ["orders", "notifications", "errors"]:
            await channel.declare_queue(topic, durable=True)
        app.state.kafka = producer
        app.state.rabbit = rabbit
        app.state.channel = channel
        yield
    finally:
        if rabbit is not None:
            await rabbit.close()
        await producer.stop()


app = FastAPI(title="Producer Service", version="1.0.0", lifespan=lifespan)
RunId = Annotated[str, Query(max_length=100)]


async def publish(topic: str, data: BaseModel, transport: str, run_id: str):
    event_id = str(uuid4())
    start_ns = time.perf_counter_ns()
    try:
        if transport == "kafka":
            metadata = await asyncio.wait_for(app.state.kafka.send_and_wait(
                topic, value=data.model_dump(),
                headers=[("event_id", event_id.encode()),
                         ("published_ns", str(start_ns).encode()),
                         ("run_id", run_id.encode())],
            ), timeout=5)
            location = {"partition": metadata.partition, "offset": metadata.offset}
        else:
            message = aio_pika.Message(
                body=json.dumps(data.model_dump(), ensure_ascii=False).encode(),
                message_id=event_id,
                headers={"published_ns": str(start_ns), "run_id": run_id},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await app.state.channel.default_exchange.publish(message, routing_key=topic)
            location = {"queue": topic}
    except (KafkaError, aio_pika.exceptions.AMQPException, TimeoutError, ConnectionError) as error:
        raise HTTPException(503, f"{transport} broker unavailable") from error
    return {
        "status": "success", "transport": transport, "topic": topic,
        "event_id": event_id, "run_id": run_id,
        "publish_ms": round((time.perf_counter_ns() - start_ns) / 1_000_000, 3),
        **location,
    }


@app.post("/orders/")
async def create_order(order: Order, run_id: RunId = "manual"):
    return await publish("orders", order, "kafka", run_id)


@app.post("/notify/")
async def send_notification(notification: Notification, run_id: RunId = "manual"):
    return await publish("notifications", notification, "kafka", run_id)


@app.post("/errors/")
async def send_error(error: ErrorMessage, run_id: RunId = "manual"):
    return await publish("errors", error, "kafka", run_id)


@app.post("/rabbit/orders/")
async def rabbit_order(order: Order, run_id: RunId = "manual"):
    return await publish("orders", order, "rabbitmq", run_id)


@app.post("/rabbit/notify/")
async def rabbit_notification(notification: Notification, run_id: RunId = "manual"):
    return await publish("notifications", notification, "rabbitmq", run_id)


@app.post("/rabbit/errors/")
async def rabbit_error(error: ErrorMessage, run_id: RunId = "manual"):
    return await publish("errors", error, "rabbitmq", run_id)


@app.get("/health")
async def health():
    return {"status": "healthy", "kafka_bootstrap_servers": BOOTSTRAP,
            "rabbitmq_connected": not app.state.rabbit.is_closed}
