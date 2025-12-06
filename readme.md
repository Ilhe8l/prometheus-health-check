# Health Check Service
Esse serviço é responsável por monitorar a saúde de vários componentes do sistema, incluindo banco de dados, cache e armazenamento de arquivos. Ele fornece endpoints para verificar o status desses componentes e garantir que estejam funcionando corretamente.
## Endpoints
- `GET /health`: Verifica a saúde geral do sistema, porta 8000.
- `GET /metrics`: Exibe métricas do Prometheus, porta 9090.

## Variáveis de Ambiente
- `DATABASE_URL`: URL de conexão com o banco de dados PostgreSQL.
- `REDIS_URL`: URL de conexão com o Redis.
- `MINIO_URL`: URL de conexão com o MinIO.
- `MINIO_ACCESS_KEY`: Chave de acesso do MinIO.
- `MINIO_SECRET_KEY`: Chave secreta do MinIO.
- `OPENAI_API_KEY`: Chave da API do OpenAI.

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