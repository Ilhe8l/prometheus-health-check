import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
# adiciona https na frente se não tiver
MINIO_URL = os.getenv("MINIO_URL")
if MINIO_URL and not MINIO_URL.startswith("http"):
    MINIO_URL = "https://" + MINIO_URL
    
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY") 
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
WHATSAPP_LOGIC_URL = os.getenv("WHATSAPP_LOGIC_URL")

K8S_CONTROLPANEL_HOST = os.getenv("K8S_CONTROLPANEL_HOST", "controlpanel")
K8S_CONTROLPANEL_PORT = os.getenv("K8S_CONTROLPANEL_PORT", "8000")

K8S_WHATSAPP_HOST = os.getenv("K8S_WHATSAPP_HOST", "whatsapp-service")
K8S_WHATSAPP_PORT = os.getenv("K8S_WHATSAPP_PORT", "8001")