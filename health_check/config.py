import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@postgres:5432/mydatabase')
REDIS_URL= os.getenv('REDIS_URL', 'redis://redis:6379/0')
MINIO_URL = os.getenv('MINIO_URL', 'http://minio:9001')
MINIO_ACESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
CONTAINERS_TO_MONITOR = os.getenv('CONTAINERS_TO_MONITOR', "minio,postgres,redis,whatsapp_service,agents").split(",")
WHATSAPP_SERVICE_URL = os.getenv('WHATSAPP_SERVICE_URL', 'http://whatsapp_service:8000/direct-message')
K8S_DEPLOYMENTS_TO_MONITOR = os.getenv('K8S_DEPLOYMENTS_TO_MONITOR', "my-deployment-1,my-deployment-2").split(",")  # Lista de Deployments no K8s para monitorar
K8S_NAMESPACE = os.getenv('K8S_NAMESPACE', 'default')  