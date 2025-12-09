import asyncio
import time
import os
import logging

import psycopg2
import redis
import docker
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
    CONTAINERS_TO_MONITOR,
    WHATSAPP_SERVICE_URL,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# definição das métricas prometheus
HEALTH_STATUS = Gauge("app_health_status", "Status do servico (1=UP, 0=DOWN)", ["service"])
HEALTH_LATENCY = Gauge("app_health_latency_seconds", "Tempo de resposta da checagem", ["service"])

# semáforo para controlar concorrência
CHECK_SEMAPHORE = asyncio.Semaphore(20)

# estado atual de todos os serviços
SERVICES_STATE = {}

# decorador genérico de monitoramento
async def monitor_service(service_name, check_func):
    async with CHECK_SEMAPHORE:
        start_time = time.time()
        try:
            await check_func()
            
            elapsed = time.time() - start_time
            HEALTH_LATENCY.labels(service=service_name).set(elapsed)
            HEALTH_STATUS.labels(service=service_name).set(1)
            logging.info(f"[*] [{service_name}] OK - {elapsed:.4f}s")
            
            return {
                "service": service_name,
                "is_healthy": True,
                "latency": elapsed,
                "error_message": "",
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            HEALTH_LATENCY.labels(service=service_name).set(elapsed)
            HEALTH_STATUS.labels(service=service_name).set(0)
            error_msg = str(e)
            logging.error(f"[x] [{service_name}] FALHA: {error_msg}")
            
            return {
                "service": service_name,
                "is_healthy": False,
                "latency": elapsed,
                "error_message": error_msg,
            }


# funções de checagem
async def check_postgresql():
    def _check():
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        cursor.fetchone()
        cursor.close()
        conn.close()
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)


async def check_redis():
    def _check():
        # socket_timeout evita que o monitoramento trave se o redis sumir
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


# apenas checagem de conexão simples
async def check_openai_conn():
    def _check():
        client = OpenAI()
        client.models.list()
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)


# checagem que gera custo - faz uma requisição de geração
async def check_openai_generation():
    def _check():
        client = OpenAI()
        client.chat.completions.create(
            model="gpt-4.1",  # modelo usado em produção, troque para um mais barato se quiser economizar
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)


async def check_whatsapp_flow():
    def _check():
        url = WHATSAPP_SERVICE_URL
        payload = {
            "content": "ping",  # mensagem simples para healthcheck
            "from_number": "HEALTHCHECK",
            "to_number": "HEALTHCHECK",
            "contact_name": "Monitor",
            "session_id": "health-check-session",
        }
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        response.raise_for_status()
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)


# checagem de container docker individual
async def check_container(container_name):
    def _check():
        client = docker.from_env()
        container = client.containers.get(container_name)
        
        # verifica se está "running"
        if container.status != "running":
            raise Exception(f"[x] Status is {container.status}")
        
        # se tiver healthcheck nativo do docker, verifica ele também
        health = container.attrs.get("State", {}).get("Health", {}).get("Status")
        if health and health != "healthy":
            raise Exception(f"[x] Docker Health is {health}")
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _check)

# executa todas as checagens em paralelo e atualiza o estado global
async def run_all_checks():
    logging.info("[i] Iniciando ciclo de verificação")
    
    tasks = []
    
    # checagens de infra/conectividade
    tasks.append(monitor_service("postgresql", check_postgresql))
    tasks.append(monitor_service("redis", check_redis))
    tasks.append(monitor_service("minio_s3", check_s3))
    tasks.append(monitor_service("openai_api_conn", check_openai_conn))
    
    # checagem de containers
    for container_name in CONTAINERS_TO_MONITOR:
        if container_name.strip():
            tasks.append(
                monitor_service(
                    f"container_{container_name}",
                    lambda name=container_name: check_container(name),
                )
            )
    
    # checagem de api local
    tasks.append(monitor_service("whatsapp_flow", check_whatsapp_flow))
    
    # checagem custosa (openai generation)
    tasks.append(monitor_service("openai_chat_gen", check_openai_generation))
    
    # executa tudo em paralelo
    results = await asyncio.gather(*tasks)
    
    # atualiza estado global
    global SERVICES_STATE
    SERVICES_STATE = {result["service"]: result for result in results}
    
    all_healthy = all(result["is_healthy"] for result in results)
    logging.info(f"[*/x] Ciclo concluido. Status: {'OK' if all_healthy else 'FALHA'}")
    
    return all_healthy

# endpoint /health retorna 200 se tudo ok, 503 se algum serviço está down
async def health_endpoint(request):
    if not SERVICES_STATE:
        return web.json_response(
            {"status": "unknown", "message": "Nenhuma checagem executada ainda"},
            status=503,
        )
    
    all_healthy = all(service["is_healthy"] for service in SERVICES_STATE.values())
    
    if all_healthy:
        return web.json_response(
            {
                "status": "healthy",
                "services": {
                    name: {
                        "status": "UP",
                        "latency": f"{data['latency']:.4f}s",
                    }
                    for name, data in SERVICES_STATE.items()
                },
            },
            status=200,
        )
    else:
        unhealthy_services = {
            name: {
                "status": "DOWN",
                "latency": f"{data['latency']:.4f}s",
                "error": data["error_message"],
            }
            for name, data in SERVICES_STATE.items()
            if not data["is_healthy"]
        }
        
        healthy_services = {
            name: {
                "status": "UP",
                "latency": f"{data['latency']:.4f}s",
            }
            for name, data in SERVICES_STATE.items()
            if data["is_healthy"]
        }
        
        return web.json_response(
            {
                "status": "unhealthy",
                "unhealthy_services": unhealthy_services,
                "healthy_services": healthy_services,
            },
            status=503,
        )

# inicia servidor /health
async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", health_endpoint)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    logging.info("[i] Servidor /health rodando na porta 8000")

# checagem periódica em loop
async def monitoring_loop():
    while True:
        await run_all_checks()
        logging.info("[i] Aguardando 30s...")
        await asyncio.sleep(30)


async def main():
    # inicializa servidor prometheus
    PROMETHEUS_PORT = 9090
    start_http_server(PROMETHEUS_PORT)
    logging.info(f"[i] Prometheus exporter rodando na porta {PROMETHEUS_PORT}")
    
    # inicia servidor /health
    await start_health_server()
    
    # inicia loop de monitoramento
    await monitoring_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[x] Monitoramento interrompido pelo usuario")