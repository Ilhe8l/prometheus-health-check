import asyncio
import time
import socket
import logging
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
    MINIO_ACESS_KEY,
    MINIO_SECRET_KEY,
    WHATSAPP_LOGIC_URL, # A URL: https://edite.aws.leds.dev.br/direct-message
    K8S_CONTROLPANEL_HOST, # Nome do service: controlpanel
    K8S_CONTROLPANEL_PORT, # Porta: 8000
    K8S_WHATSAPP_HOST,     # Nome do service: whatsapp-service
    K8S_WHATSAPP_PORT      # Porta: 3000
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

HEALTH_STATUS = Gauge("app_health_status", "Status do servico (1=UP, 0=DOWN)", ["service"])
HEALTH_LATENCY = Gauge("app_health_latency_seconds", "Tempo de resposta da checagem", ["service"])
CHECK_SEMAPHORE = asyncio.Semaphore(20)
SERVICES_STATE = {}

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
            aws_access_key_id=MINIO_ACESS_KEY,
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

# Checagem TCP (Socket) para ver se o Pod/Service Kubernetes está aceitando conexão
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

# Checagem Lógica do WhatsApp (O CURL que você mandou)
async def check_whatsapp_logic():
    def _check():
        payload = {
            "content": "quais editais disponiveis?",
            "from_number": "11988887777",
            "to_number": "11999999999",
            "contact_name": "Usuario Teste",
            "session_id": "health-check-monitor" 
        }
        # Bate na URL publica/ingress
        response = requests.post(
            WHATSAPP_LOGIC_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

async def run_all_checks():
    logging.info("[i] Iniciando ciclo de verificação")
    tasks = []
    
    # 1. Infra Externa
    tasks.append(monitor_service("postgresql", check_postgresql))
    tasks.append(monitor_service("redis", check_redis))
    tasks.append(monitor_service("minio_s3", check_s3))
    tasks.append(monitor_service("openai_api", check_openai_conn))
    
    # 2. Infra Interna Kubernetes (Teste de Porta TCP)
    # Verifica se o container está rodando e escutando
    tasks.append(monitor_service(f"k8s_svc_controlpanel", lambda: check_tcp_service(K8S_CONTROLPANEL_HOST, K8S_CONTROLPANEL_PORT)))
    tasks.append(monitor_service(f"k8s_svc_whatsapp", lambda: check_tcp_service(K8S_WHATSAPP_HOST, K8S_WHATSAPP_PORT)))

    # 3. Teste de Lógica (Curl do WhatsApp)
    tasks.append(monitor_service("app_logic_whatsapp", check_whatsapp_logic))
    
    results = await asyncio.gather(*tasks)
    
    global SERVICES_STATE
    SERVICES_STATE = {result["service"]: result for result in results}
    
    all_healthy = all(result["is_healthy"] for result in results)
    logging.info(f"[*/x] Ciclo concluido. Status: {'OK' if all_healthy else 'FALHA'}")
    return all_healthy

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
    while True:
        await run_all_checks()
        logging.info("[i] Aguardando 30s...")
        await asyncio.sleep(30)

async def main():
    start_http_server(9090)
    await start_health_server()
    await monitoring_loop()

if __name__ == "__main__":
    asyncio.run(main())