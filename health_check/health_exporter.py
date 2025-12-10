import asyncio
import time
import socket
import logging
import json

import psycopg2
import redis
import requests
from boto3 import client as boto3_client
from openai import OpenAI
from prometheus_client import start_http_server, Gauge
from aiohttp import web

from config import (
    DATABASE_URL,
    REDIS_URL,
    MINIO_URL,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    WHATSAPP_LOGIC_URL,
    K8S_CONTROLPANEL_HOST,
    K8S_CONTROLPANEL_PORT,
    K8S_WHATSAPP_HOST,
    K8S_WHATSAPP_PORT,
    ENABLE_COSTLY_CHECKS,
    CHECK_INTERVAL_STANDARD,
    CHECK_INTERVAL_COSTLY
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# métricas Prometheus
HEALTH_STATUS = Gauge("app_health_status", "Status do servico (1=UP, 0=DOWN)", ["service"])
HEALTH_LATENCY = Gauge("app_health_latency_seconds", "Tempo de resposta da checagem", ["service"])

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
        s3 = boto3_client(
            "s3",
            endpoint_url=MINIO_URL,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
        )
        s3.list_buckets()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

async def check_openai_conn():
    def _check():
        client = OpenAI()
        client.models.list()
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

# testes de lógica de negócio (Checks Caros/Pesados)
async def check_whatsapp_logic():
    def _check():
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

async def check_openai_generation():
    def _check():
        client = OpenAI()
        client.chat.completions.create(
            model="gpt-4.1-mini", 
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
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
    tasks.append(monitor_service("minio_s3", check_s3))
    tasks.append(monitor_service("openai_api_list", check_openai_conn))
    
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
        logging.info("[i] Executando checks caros (WhatsApp + OpenAI Gen)")
        tasks.append(monitor_service("app_logic_whatsapp", check_whatsapp_logic))
        tasks.append(monitor_service("openai_gen_gpt", check_openai_generation))
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