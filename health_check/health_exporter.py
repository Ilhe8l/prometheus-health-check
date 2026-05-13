import asyncio
import time
import socket
import logging

import psycopg2
import redis
import requests
from boto3 import client as boto3_client
from prometheus_client import start_http_server, Gauge
from aiohttp import web

from config import (
    DATABASE_URL,
    REDIS_URL,
    S3_ENDPOINT_URL,
    S3_ACCESS_KEY,
    S3_SECRET_KEY,
    S3_BUCKET_NAME,
    WHATSAPP_LOGIC_URL,
    K8S_CONTROLPANEL_HOST,
    K8S_CONTROLPANEL_PORT,
    K8S_WHATSAPP_HOST,
    K8S_WHATSAPP_PORT,
    ENABLE_COSTLY_CHECKS,
    CHECK_INTERVAL_STANDARD,
    CHECK_INTERVAL_COSTLY,
    STREAMS_GROUPS,
    QUEUE_STALE_THRESHOLD_MS,
    QUEUE_LAG_THRESHOLD,
    QUEUE_PENDING_THRESHOLD,
    QUEUE_MAX_PENDING_INSPECT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# métricas Prometheus
HEALTH_STATUS = Gauge("app_health_status", "Status do servico (1=UP, 0=DOWN)", ["service"])
HEALTH_LATENCY = Gauge("app_health_latency_seconds", "Tempo de resposta da checagem", ["service"])
QUEUE_STREAM_LENGTH = Gauge("app_queue_stream_length", "Total de mensagens no Redis Stream", ["stream"])
QUEUE_GROUP_LAG = Gauge("app_queue_group_lag", "Mensagens ainda nao entregues ao consumer group", ["stream", "group"])
QUEUE_GROUP_PENDING = Gauge("app_queue_group_pending", "Mensagens entregues e ainda sem ACK", ["stream", "group"])
QUEUE_GROUP_STALE_PENDING = Gauge("app_queue_group_stale_pending", "Mensagens pendentes acima do limite de idade", ["stream", "group"])
QUEUE_GROUP_OLDEST_PENDING_SECONDS = Gauge("app_queue_group_oldest_pending_seconds", "Idade da mensagem pendente mais antiga inspecionada", ["stream", "group"])
QUEUE_GROUP_HEALTH_STATUS = Gauge("app_queue_group_health_status", "Saude do consumer group (1=OK, 0=FALHA)", ["stream", "group"])

CHECK_SEMAPHORE = asyncio.Semaphore(20)
SERVICES_STATE = {}

# variável global para controlar a última execução do check caro
LAST_COSTLY_RUN_TIME = 0

# monitoramento de um serviço genérico
async def monitor_service(service_name, check_func):
    async with CHECK_SEMAPHORE:
        start_time = time.time()
        try:
            await check_func()
            elapsed = time.time() - start_time
            HEALTH_LATENCY.labels(service=service_name).set(elapsed)
            HEALTH_STATUS.labels(service=service_name).set(1)
            logging.info(f"[*] [{service_name}] OK - {elapsed:.4f}s")
            return {"service": service_name, "is_healthy": True, "latency": elapsed, "error_message": ""}
        except Exception as e:
            elapsed = time.time() - start_time
            HEALTH_LATENCY.labels(service=service_name).set(elapsed)
            HEALTH_STATUS.labels(service=service_name).set(0)
            logging.error(f"[x] [{service_name}] FALHA: {e}")
            return {"service": service_name, "is_healthy": False, "latency": elapsed, "error_message": str(e)}

# testes de infraestrutura básica
async def check_postgresql():
    def _check():
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        conn.close()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

async def check_redis():
    def _check():
        r = redis.Redis.from_url(REDIS_URL, socket_timeout=3)
        r.ping()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

async def check_s3():
    def _check():
        kwargs = {}
        if S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = S3_ENDPOINT_URL
        if S3_ACCESS_KEY:
            kwargs["aws_access_key_id"] = S3_ACCESS_KEY
        if S3_SECRET_KEY:
            kwargs["aws_secret_access_key"] = S3_SECRET_KEY

        s3 = boto3_client("s3", **kwargs)
        if S3_BUCKET_NAME:
            s3.head_bucket(Bucket=S3_BUCKET_NAME)
        else:
            s3.list_buckets()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

# testes de infraestrutura interna K8s (porta TCP)
async def check_tcp_service(host, port):
    def _check():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        if result != 0:
            raise Exception(f"Porta {port} fechada ou inalcançavel em {host}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

# teste sintetico opcional. Em prod, deixa desabilitado se nao quiser gerar mensagem/custo.
async def check_whatsapp_logic():
    def _check():
        if not WHATSAPP_LOGIC_URL:
            raise Exception("WHATSAPP_LOGIC_URL nao configurado")

        payload = {
            "content": "quais editais disponiveis?",
            "from_number": "11988887777",
            "to_number": "11999999999",
            "contact_name": "Usuario Teste",
            "session_id": "health-check-monitor"
        }
        response = requests.post(
            WHATSAPP_LOGIC_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

async def check_redis_streams():
    def _reset_queue_metrics(stream, group):
        QUEUE_GROUP_LAG.labels(stream=stream, group=group).set(0)
        QUEUE_GROUP_PENDING.labels(stream=stream, group=group).set(0)
        QUEUE_GROUP_STALE_PENDING.labels(stream=stream, group=group).set(0)
        QUEUE_GROUP_OLDEST_PENDING_SECONDS.labels(stream=stream, group=group).set(0)
        QUEUE_GROUP_HEALTH_STATUS.labels(stream=stream, group=group).set(0)

    def _create_stream_group(client, stream, group, message):
        try:
            client.xgroup_create(stream, group, id="0", mkstream=True)
            logging.info(message)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _ensure_stream_group(client, stream, group):
        try:
            groups_info = client.xinfo_groups(stream)
        except redis.exceptions.ResponseError:
            _create_stream_group(
                client,
                stream,
                group,
                f"[+] [{stream}/{group}] stream/group criado para monitoramento",
            )
            return client.xinfo_groups(stream)

        if any(g.get("name") == group for g in groups_info):
            return groups_info

        _create_stream_group(
            client,
            stream,
            group,
            f"[+] [{stream}/{group}] consumer group criado para monitoramento",
        )
        return client.xinfo_groups(stream)

    def _check():
        client = redis.Redis.from_url(REDIS_URL, socket_timeout=3, decode_responses=True)
        violations = []

        for stream, group in STREAMS_GROUPS:
            try:
                groups_info = _ensure_stream_group(client, stream, group)
                stream_len = client.xlen(stream)
                QUEUE_STREAM_LENGTH.labels(stream=stream).set(stream_len)
            except redis.exceptions.ResponseError as exc:
                _reset_queue_metrics(stream, group)
                violations.append(f"{stream}/{group}: nao foi possivel preparar stream/group ({exc})")
                continue

            group_info = next((g for g in groups_info if g.get("name") == group), None)
            if group_info is None:
                _reset_queue_metrics(stream, group)
                violations.append(f"{stream}/{group}: grupo nao encontrado")
                continue

            lag = group_info.get("lag") or 0
            pending = group_info.get("pending") or 0
            stale_count = 0
            oldest_pending_seconds = 0

            if pending > 0:
                pending_entries = client.xpending_range(
                    stream,
                    group,
                    min="-",
                    max="+",
                    count=QUEUE_MAX_PENDING_INSPECT,
                )
                idle_times = [
                    entry.get("time_since_delivered", 0)
                    for entry in pending_entries
                ]
                if idle_times:
                    oldest_pending_seconds = max(idle_times) / 1000
                    stale_count = sum(
                        1
                        for idle_time in idle_times
                        if idle_time > QUEUE_STALE_THRESHOLD_MS
                    )

            QUEUE_GROUP_LAG.labels(stream=stream, group=group).set(lag)
            QUEUE_GROUP_PENDING.labels(stream=stream, group=group).set(pending)
            QUEUE_GROUP_STALE_PENDING.labels(stream=stream, group=group).set(stale_count)
            QUEUE_GROUP_OLDEST_PENDING_SECONDS.labels(stream=stream, group=group).set(oldest_pending_seconds)

            group_violations = []
            if lag > QUEUE_LAG_THRESHOLD:
                group_violations.append(f"lag={lag}")
            if pending > QUEUE_PENDING_THRESHOLD:
                group_violations.append(f"pending={pending}")
            if stale_count > 0:
                group_violations.append(
                    f"stale_pending={stale_count} oldest_pending={oldest_pending_seconds:.0f}s"
                )

            if group_violations:
                QUEUE_GROUP_HEALTH_STATUS.labels(stream=stream, group=group).set(0)
                violations.append(f"{stream}/{group}: {', '.join(group_violations)}")
            else:
                QUEUE_GROUP_HEALTH_STATUS.labels(stream=stream, group=group).set(1)

        if violations:
            raise Exception("; ".join(violations))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)


# lógica principal de verificação
async def run_all_checks():
    global LAST_COSTLY_RUN_TIME, SERVICES_STATE
    
    current_time = time.time()
    logging.info("[i] Iniciando ciclo de verificação Padrão")
    
    tasks = []
    
    # infra Básica (Sempre roda)
    tasks.append(monitor_service("postgresql", check_postgresql))
    tasks.append(monitor_service("redis", check_redis))
    tasks.append(monitor_service("s3_storage", check_s3))
    tasks.append(monitor_service("redis_streams", check_redis_streams))
    
    # infra Interna K8s (Sempre roda)
    tasks.append(monitor_service("k8s_svc_controlpanel", lambda: check_tcp_service(K8S_CONTROLPANEL_HOST, K8S_CONTROLPANEL_PORT)))
    tasks.append(monitor_service("k8s_svc_whatsapp", lambda: check_tcp_service(K8S_WHATSAPP_HOST, K8S_WHATSAPP_PORT)))

    # verifica se está habilitado E se já passou tempo suficiente desde a última execução
    should_run_costly = False
    
    if ENABLE_COSTLY_CHECKS:
        time_since_last = current_time - LAST_COSTLY_RUN_TIME
        if time_since_last >= CHECK_INTERVAL_COSTLY:
            should_run_costly = True
        else:
            logging.info(f"[i] Checks caros ignorados. Último: {int(time_since_last)}s atrás (Intervalo: {CHECK_INTERVAL_COSTLY}s)")
    
    if should_run_costly:
        logging.info("[i] Executando check sintetico do WhatsApp")
        tasks.append(monitor_service("app_logic_whatsapp", check_whatsapp_logic))
        # atualiza o timestamp apenas se enfileirou a task
        LAST_COSTLY_RUN_TIME = current_time

    # executa tudo o que foi agendado
    results = await asyncio.gather(*tasks)
    
    new_state = {result["service"]: result for result in results}
    SERVICES_STATE.update(new_state)
    
    # atualiza o estado geral para logging
    all_healthy = all(s["is_healthy"] for s in SERVICES_STATE.values())
    logging.info(f"[*/x] Ciclo concluido. Status Geral: {'OK' if all_healthy else 'FALHA'}")
    return all_healthy


# endpoint HTTP para health check
async def health_endpoint(request):
    if not SERVICES_STATE:
        return web.json_response({"status": "unknown"}, status=503)
    
    all_healthy = all(s["is_healthy"] for s in SERVICES_STATE.values())
    
    if all_healthy:
        return web.json_response({"status": "healthy", "services": SERVICES_STATE}, status=200)
    else:
        return web.json_response({"status": "unhealthy", "services": SERVICES_STATE}, status=503)

async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", health_endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

async def monitoring_loop():
    logging.info(f"--- Monitor Iniciado ---")
    logging.info(f"Intervalo Padrão: {CHECK_INTERVAL_STANDARD}s")
    logging.info(f"Intervalo Caro: {CHECK_INTERVAL_COSTLY}s | Habilitado: {ENABLE_COSTLY_CHECKS}")
    
    while True:
        await run_all_checks()
        # o sleep agora obedece apenas ao intervalo padrão.
        await asyncio.sleep(CHECK_INTERVAL_STANDARD)

async def main():
    start_http_server(9090) # Prometheus
    await start_health_server()
    await monitoring_loop()

if __name__ == "__main__":
    asyncio.run(main())
