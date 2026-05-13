import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

# s3 / minio / aws
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
if S3_ENDPOINT_URL and not S3_ENDPOINT_URL.startswith("http"):
    S3_ENDPOINT_URL = "https://" + S3_ENDPOINT_URL
    
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

WHATSAPP_LOGIC_URL = os.getenv("WHATSAPP_LOGIC_URL")

# K8s interno
K8S_CONTROLPANEL_HOST = os.getenv("K8S_CONTROLPANEL_HOST", "controlpanel")
K8S_CONTROLPANEL_PORT = os.getenv("K8S_CONTROLPANEL_PORT", "8000")
K8S_WHATSAPP_HOST = os.getenv("K8S_WHATSAPP_HOST", "whatsapp-service")
K8S_WHATSAPP_PORT = os.getenv("K8S_WHATSAPP_PORT", "8001")


# Define se checks que geram custo devem rodar (True/False)
_costly_env = os.getenv("ENABLE_COSTLY_CHECKS", "false").lower()
ENABLE_COSTLY_CHECKS = _costly_env in ["true", "1", "yes"]

# intervalo para checks padrão em segundos
CHECK_INTERVAL_STANDARD = int(os.getenv("CHECK_INTERVAL_STANDARD", "30")) # 30 segundos

# intervalo para checks caros (WhatsApp Logic) em segundos
CHECK_INTERVAL_COSTLY = int(os.getenv("CHECK_INTERVAL_COSTLY", "14400")) # 4 horas

# Redis Streams / filas
_raw_streams_groups = os.getenv(
    "STREAMS_GROUPS",
    "queue_questions:agents_group,"
    "queue_questions:db_group,"
    "queue_responses:whatsapp_group,"
    "queue_responses:db_responses_group,"
    "queue_responses_dlq:ops_group,"
    "queue_consent:db_consent_group",
)
STREAMS_GROUPS = [
    (item.strip().split(":", 1)[0], item.strip().split(":", 1)[1])
    for item in _raw_streams_groups.split(",")
    if ":" in item and item.strip()
]

# tempo para considerar uma mensagem parada/travada
QUEUE_STALE_THRESHOLD_MS = int(os.getenv("QUEUE_STALE_THRESHOLD_MS", os.getenv("STALE_THRESHOLD_MS", "30000")))

# limites para derrubar a saude. A idade e mais importante que volume momentaneo.
QUEUE_LAG_THRESHOLD = int(os.getenv("QUEUE_LAG_THRESHOLD", "10"))
QUEUE_PENDING_THRESHOLD = int(os.getenv("QUEUE_PENDING_THRESHOLD", "200"))
QUEUE_MAX_PENDING_INSPECT = int(os.getenv("QUEUE_MAX_PENDING_INSPECT", os.getenv("MAX_PENDING", "200")))
