import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://user:password@postgres:5432/mydatabase')
REDIS_URL= os.getenv('REDIS_URL', 'redis://redis:6379/0')
MINIO_URL = os.getenv('MINIO_URL', 'http://minio:9001')
MINIO_ACESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
CONTAINERS_TO_MONITOR = os.getenv('CONTAINERS_TO_MONITOR', "minio,postgres,redis,whatsapp_service,agents").split(",")