"""Consumer: отдельные задачи, задержка 1 с, подтверждение после обработки."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import json
import logging
import os
import time

from aiokafka import AIOKafkaConsumer
import aio_pika
from fastapi import FastAPI, Query

logger = logging.getLogger("uvicorn.error")
TOPICS = ["orders", "notifications", "errors"]
DELAY = float(os.getenv("PROCESSING_DELAY", "1"))
events: list[dict] = []
active = 0
peak_active = 0


async def process_message(transport, topic, data, event_id, published_ns, run_id, **metadata):
    global active, peak_active
    received_ns = time.perf_counter_ns()
    active += 1
    peak_active = max(peak_active, active)
    try:
        await asyncio.sleep(DELAY)
        finished_ns = time.perf_counter_ns()
        event = {
            "event_id": event_id, "run_id": run_id, "transport": transport,
            "topic": topic, "data": data,
            "delivery_ms": round((received_ns - published_ns) / 1_000_000, 3),
            "processing_ms": round((finished_ns - received_ns) / 1_000_000, 3),
            "total_ms": round((finished_ns - published_ns) / 1_000_000, 3),
            "completed_at": datetime.now(timezone.utc).isoformat(), **metadata,
        }
        events.append(event)
        logger.info("%s %s processed: %s", transport, topic, json.dumps(data, ensure_ascii=False))
    finally:
        active -= 1


async def consume_kafka(consumer, topic):
    while True:
        batch = await consumer.getmany(timeout_ms=250, max_records=100)
        jobs = []
        for partition, messages in batch.items():
            for message in messages:
                headers = {key: value.decode() for key, value in message.headers}
                jobs.append(asyncio.create_task(process_message(
                    "kafka", topic, message.value,
                    headers.get("event_id", f"{partition.partition}:{message.offset}"),
                    int(headers.get("published_ns", time.perf_counter_ns())),
                    headers.get("run_id", "external"),
                    partition=message.partition, offset=message.offset,
                )))
        if jobs:
            # Offset подтверждается только после обработки всей полученной порции.
            await asyncio.gather(*jobs)
            await consumer.commit()


def rabbit_callback(topic):
    async def consume(message):
        async with message.process(requeue=True):
            task = asyncio.create_task(process_message(
                "rabbitmq", topic, json.loads(message.body), message.message_id,
                int(message.headers.get("published_ns", time.perf_counter_ns())),
                message.headers.get("run_id", "external"),
            ))
            await task
    return consume


@asynccontextmanager
async def lifespan(app):
    consumers = []
    tasks = []
    rabbit = None
    try:
        for topic in TOPICS:
            consumer = AIOKafkaConsumer(
                topic, bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9093"),
                group_id=f"{topic}-group", auto_offset_reset="earliest", enable_auto_commit=False,
                value_deserializer=lambda value: json.loads(value.decode()),
            )
            await consumer.start()
            consumers.append(consumer)
            tasks.append(asyncio.create_task(consume_kafka(consumer, topic)))
        rabbit = await aio_pika.connect_robust(os.environ["RABBITMQ_URL"])
        channel = await rabbit.channel()
        await channel.set_qos(prefetch_count=100)
        for topic in TOPICS:
            queue = await channel.declare_queue(topic, durable=True)
            await queue.consume(rabbit_callback(topic))
        app.state.tasks = tasks
        app.state.rabbit = rabbit
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        if rabbit is not None:
            await rabbit.close()
        for consumer in consumers:
            await consumer.stop()


app = FastAPI(title="Consumer Service", version="1.0.0", lifespan=lifespan)


def received(transport, topic):
    data = [e["data"] for e in events if e["transport"] == transport and e["topic"] == topic]
    return {topic: data, "count": len(data)}


@app.get("/orders/")
async def get_orders():
    return received("kafka", "orders")


@app.get("/notifications/")
async def get_notifications():
    return received("kafka", "notifications")


@app.get("/errors/")
async def get_errors():
    return received("kafka", "errors")


@app.get("/rabbit/orders/")
async def rabbit_orders():
    return received("rabbitmq", "orders")


@app.get("/rabbit/notifications/")
async def rabbit_notifications():
    return received("rabbitmq", "notifications")


@app.get("/rabbit/errors/")
async def rabbit_errors():
    return received("rabbitmq", "errors")


@app.get("/events/")
async def get_events(run_id: str | None = None, transport: str | None = None):
    selected = [e for e in events if (run_id is None or e["run_id"] == run_id)
                and (transport is None or e["transport"] == transport)]
    return {"events": selected, "count": len(selected)}


@app.get("/health")
async def health():
    healthy = all(not task.done() for task in app.state.tasks) and not app.state.rabbit.is_closed
    return {"status": "healthy" if healthy else "degraded",
            "active_tasks": active, "peak_parallel_tasks": peak_active,
            "processed": len(events), "processing_delay_s": DELAY}
