# Health Check Service
Esse serviço é responsável por monitorar a saúde de vários componentes do sistema, incluindo banco de dados, cache e armazenamento de arquivos. Ele fornece endpoints para verificar o status desses componentes e garantir que estejam funcionando corretamente.
## Endpoints
- `GET /health`: Verifica a saúde geral do sistema, porta 8000.
- `GET /metrics`: Exibe métricas do Prometheus, porta 9090.

## Variáveis de Ambiente
- `DATABASE_URL`: URL de conexão com o banco de dados PostgreSQL.
- `REDIS_URL`: URL de conexão com o Redis.
- `S3_ENDPOINT_URL`: endpoint S3 customizado. Em AWS S3 nativo pode ficar vazio; em MinIO/local use algo como `http://minio:9002`.
- `S3_ACCESS_KEY`/`S3_SECRET_KEY`: credenciais S3, servem tanto para AWS quanto para MinIO.
- `S3_BUCKET_NAME`: bucket usado no check. Quando configurado, o monitor usa `head_bucket`; sem bucket, usa `list_buckets`.
- `STREAMS_GROUPS`: pares `stream:consumer_group` monitorados no Redis.
- `QUEUE_STALE_THRESHOLD_MS`: idade máxima de mensagem pendente antes de alertar. Padrão: `30000`.
- `QUEUE_LAG_THRESHOLD`: quantidade máxima de mensagens ainda não entregues antes de alertar. Padrão: `10`.
- `QUEUE_PENDING_THRESHOLD`: quantidade máxima de mensagens entregues sem ACK antes de alertar. Padrão: `200`.
- `QUEUE_MAX_PENDING_INSPECT`: quantidade máxima de pendentes inspecionadas por grupo. Padrão: `200`.
- `ENABLE_COSTLY_CHECKS`: habilita o check sintético do WhatsApp a cada `CHECK_INTERVAL_COSTLY`. Padrão: `false`.
- `CHECK_INTERVAL_COSTLY`: intervalo do check sintético, em segundos. Padrão: `14400` (4 horas).

## Métricas de filas

O monitor não chama APIs pagas no ciclo padrão. As filas são avaliadas somente por
leituras no Redis Streams:

- `app_queue_group_lag`: mensagens acumuladas que ainda não foram entregues ao consumer group.
- `app_queue_group_pending`: mensagens entregues ao consumer e ainda sem ACK.
- `app_queue_group_stale_pending`: mensagens pendentes acima de `QUEUE_STALE_THRESHOLD_MS`.
- `app_queue_group_oldest_pending_seconds`: idade da pendente mais antiga inspecionada.
- `app_queue_group_health_status`: `1` quando o par `stream/group` está dentro dos limites, `0` quando está com lag alto, pending alto, mensagem velha, stream ausente ou grupo ausente.
- `app_queue_stream_length`: tamanho total do stream.

Regras de saúde:

- `lag > QUEUE_LAG_THRESHOLD`: existem mensagens acumuladas que ainda não chegaram ao consumer group.
- `pending > QUEUE_PENDING_THRESHOLD`: existem muitas mensagens entregues a consumers, mas ainda sem ACK.
- `stale_pending > 0`: existe pelo menos uma mensagem pendente há mais tempo que `QUEUE_STALE_THRESHOLD_MS`.

Passagem momentânea pela fila é normal. O sinal mais importante para alerta é
`app_queue_group_stale_pending`, porque indica mensagem parada durante
processamento.

## Como Executar
1. Clone o repositório:
   ```bash
   git clone https://github.com/Ilhe8l/prometheus-health-check.git
2. Navegue até o diretório do projeto:
   ```bash
   cd prometheus-health-check
3. Configure as variáveis de ambiente no arquivo `.env`.
4. Builde e execute o contêiner Docker:
   ```bash
   docker-compose up --build
5. Acesse os endpoints de saúde e métricas:
   - Saúde: `http://localhost:8000/health`
   - Métricas: `http://localhost:9090/metrics`
