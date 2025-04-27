import os
import psycopg2
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Recarregar variáveis de ambiente do arquivo .env
load_dotenv(override=True)

# Atualizar a string de conexão com os novos parâmetros
DATABASE_URL = "postgresql://postgres.lmnboexmebxxwfowyjqe:2SPeycDHxmqb0wqp@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"

# Log para verificar a string de conexão
logging.debug(f"DATABASE_URL usada: {DATABASE_URL}")

try:
    # Tentar conectar ao banco de dados
    logging.info("Tentando conectar ao banco de dados...")
    connection = psycopg2.connect(DATABASE_URL)
    logging.info("Conexão bem-sucedida!")
except Exception as e:
    logging.error(f"Erro ao conectar ao banco de dados: {e}")
finally:
    if 'connection' in locals() and connection:
        connection.close()
        logging.info("Conexão fechada.") 