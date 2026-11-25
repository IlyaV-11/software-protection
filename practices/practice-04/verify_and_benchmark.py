"""Проверка всей цепочки и измерения из ответов реального Consumer."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import statistics
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent
PRODUCER = "http://127.0.0.1:8020"
CONSUMER = "http://127.0.0.1:8021"


async def wait_events(client, run_id, count, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(CONSUMER + "/events/", params={"run_id": run_id})
        response.raise_for_status()
        events = response.json()["events"]
        if len(events) >= count:
            return events
        await asyncio.sleep(0.05)
    raise AssertionError(f"Не получены {count} сообщений для {run_id}")


async def send(client, transport, path, data, run_id):
    prefix = "/rabbit" if transport == "rabbitmq" else ""
    response = await client.post(PRODUCER + prefix + path, params={"run_id": run_id}, json=data)
    assert response.status_code == 200, (response.status_code, response.text)
    assert response.json()["status"] == "success"
    return response.json()


def describe(values):
    ordered = sorted(values)
    return {"n": len(values), "mean_ms": round(statistics.mean(values), 3),
            "median_ms": round(statistics.median(values), 3),
            "min_ms": round(min(values), 3), "max_ms": round(max(values), 3),
            "p95_ms": ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)]}


async def main():
    ROOT.joinpath("evidence").mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=15) as client:
        for url in [PRODUCER, CONSUMER]:
            health = await client.get(url + "/health")
            assert health.status_code == 200 and health.json()["status"] == "healthy", health.text
        run_id = "functional-" + uuid4().hex[:8]
        payloads = [
            ("/orders/", "orders", {"order_id": 1, "user_id": 100, "product": "Laptop", "quantity": 1}),
            ("/notify/", "notifications", {"user_id": 100, "message": "Your order has been processed"}),
            ("/errors/", "errors", {"service": "payment", "message": "Payment timeout", "severity": "error"}),
        ]
        sent = []
        for transport in ["kafka", "rabbitmq"]:
            for path, topic, payload in payloads:
                sent.append(await send(client, transport, path, payload, run_id))
        events = await wait_events(client, run_id, 6)
        for transport in ["kafka", "rabbitmq"]:
            for path, topic, payload in payloads:
                assert any(e["transport"] == transport and e["topic"] == topic and e["data"] == payload for e in events)
        bad = await client.post(PRODUCER + "/orders/", json={"order_id": 0, "quantity": -1})
        assert bad.status_code == 422
        functional = {"run_id": run_id, "published": sent, "received": events, "validation_status": bad.status_code}
        (ROOT / "evidence/functional.json").write_text(json.dumps(functional, ensure_ascii=False, indent=2))
        print("Функциональная проверка: 6 из 6 сообщений получены; неверные данные → 422", flush=True)

        # Отдельная серия доказывает перекрытие обработки пяти сообщений по 1 секунде.
        run_id = "parallel-" + uuid4().hex[:8]
        start = time.perf_counter()
        published = await asyncio.gather(*[
            send(client, "kafka", "/orders/", {"order_id": 100 + i, "user_id": 100, "product": "Parallel", "quantity": 1}, run_id)
            for i in range(5)
        ])
        events = await wait_events(client, run_id, 5)
        elapsed = time.perf_counter() - start
        health = (await client.get(CONSUMER + "/health")).json()
        parallel = {"run_id": run_id, "messages": 5, "processing_delay_s": 1,
                    "elapsed_s": round(elapsed, 3), "global_peak_parallel_tasks": health["peak_parallel_tasks"],
                    "events": events}
        bounds = []
        for event in events:
            end = datetime.fromisoformat(event["completed_at"]).timestamp()
            bounds.extend([(end - event["processing_ms"] / 1000, 1), (end, -1)])
        active = peak = 0
        for _, change in sorted(bounds):
            active += change
            peak = max(peak, active)
        parallel["peak_parallel_in_this_run"] = peak
        assert peak >= 2
        assert elapsed < 4.5, f"Нет ожидаемого перекрытия задач: {elapsed}"
        (ROOT / "evidence/parallel.json").write_text(json.dumps(parallel, ensure_ascii=False, indent=2))
        print(f"Параллельная обработка: 5 сообщений за {elapsed:.3f} с", flush=True)

        # Прогрев 3 пары; затем 20 пар без накопления необработанных сообщений.
        rows = []
        for iteration in range(23):
            run_id = f"benchmark-{uuid4().hex[:8]}"
            order = {"order_id": 1000 + iteration, "user_id": 100, "product": "Benchmark", "quantity": 1}
            # Чередование порядка уменьшает влияние систематического первого места.
            transports = ["kafka", "rabbitmq"] if iteration % 2 == 0 else ["rabbitmq", "kafka"]
            published = {t: await send(client, t, "/orders/", order, run_id) for t in transports}
            events = await wait_events(client, run_id, 2)
            if iteration >= 3:
                for event in events:
                    rows.append({"sample": iteration - 2, "transport": event["transport"],
                                 "delivery_ms": event["delivery_ms"], "processing_ms": event["processing_ms"],
                                 "total_ms": event["total_ms"],
                                 "publish_ms": published[event["transport"]]["publish_ms"]})
        summary = {t: {metric: describe([r[metric] for r in rows if r["transport"] == t])
                       for metric in ["delivery_ms", "publish_ms", "processing_ms", "total_ms"]}
                   for t in ["kafka", "rabbitmq"]}
        result = {"warmup_pairs": 3, "measured_pairs": 20, "processing_delay_s": 1,
                  "delivery_definition": "Время от начала публикации в Producer до начала обработки в Consumer; общий монотонный таймер ядра ВМ.",
                  "conditions": "Одна ВМ, один Kafka broker через HAProxy, одна RabbitMQ; постоянные сообщения RabbitMQ с publisher confirms; Kafka idempotence и acks=all; по одной паре в обработке.",
                  "summary": summary, "samples": rows}
        (ROOT / "evidence/benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        for transport in summary:
            print(transport, json.dumps(summary[transport]["delivery_ms"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
