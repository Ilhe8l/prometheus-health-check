import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")
MINIO_URL = os.getenv("MINIO_URL") # Lembrar do https://
MINIO_ACESS_KEY = os.getenv("MINIO_ACESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# URL Pública para testar o fluxo (O curl)
WHATSAPP_LOGIC_URL = os.getenv("WHATSAPP_LOGIC_URL", "https://edite.aws.leds.dev.br/direct-message")

# Nomes dos services internos no Kubernetes para teste de TCP (Se estão de pé)
K8S_CONTROLPANEL_HOST = os.getenv("K8S_CONTROLPANEL_HOST", "controlpanel")
K8S_CONTROLPANEL_PORT = os.getenv("K8S_CONTROLPANEL_PORT", "8000")

K8S_WHATSAPP_HOST = os.getenv("K8S_WHATSAPP_HOST", "whatsapp-service")
K8S_WHATSAPP_PORT = os.getenv("K8S_WHATSAPP_PORT", "3000")