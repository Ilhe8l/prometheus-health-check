import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

# s3 / minio
MINIO_URL = os.getenv("MINIO_URL")
if MINIO_URL and not MINIO_URL.startswith("http"):
    MINIO_URL = "https://" + MINIO_URL
    
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY") 
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

WHATSAPP_LOGIC_URL = os.getenv("WHATSAPP_LOGIC_URL")

# K8s interno
K8S_CONTROLPANEL_HOST = os.getenv("K8S_CONTROLPANEL_HOST", "controlpanel")
K8S_CONTROLPANEL_PORT = os.getenv("K8S_CONTROLPANEL_PORT", "8000")
K8S_WHATSAPP_HOST = os.getenv("K8S_WHATSAPP_HOST", "whatsapp-service")
K8S_WHATSAPP_PORT = os.getenv("K8S_WHATSAPP_PORT", "8001")


# Define se checks que geram custo devem rodar (True/False)
_costly_env = os.getenv("ENABLE_COSTLY_CHECKS", "true").lower()
ENABLE_COSTLY_CHECKS = _costly_env in ["true", "1", "yes"]

# intervalo para checks padrão em segundos
CHECK_INTERVAL_STANDARD = int(os.getenv("CHECK_INTERVAL_STANDARD", "30")) # 30 segundos

# intervalo para checks caros (WhatsApp Logic) em segundos
CHECK_INTERVAL_COSTLY = int(os.getenv("CHECK_INTERVAL_COSTLY", "14400")) # 4 horas