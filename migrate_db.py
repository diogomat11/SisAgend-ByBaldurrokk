import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
from dotenv import load_dotenv
import logging

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do PostgreSQL (Supabase via MCP)
PG_HOST = 'db.lmnboexmebxxwfowyjqe.supabase.co'
PG_DATABASE = 'postgres'
PG_USER = 'postgres'
PG_PASSWORD = 'ftwtThcqS4WE9PAR'
PG_PORT = '5432'
PG_SSL = True

# Tabelas principais e de junção
TABLES = [
    'unidades',
    'salas',
    'areas_atuacao',
    'pagamentos',
    'perfis_paciente',
    'terminologias',
    'profissionais',
    'disponibilidade',
    'disponibilidade_salas',
    'agenda_fixa',
    'agendamentos',
    'pacientes',
    'carteiras',
    'profissional_area_atuacao',
    'profissional_pagamento',
    'profissional_perfil_paciente'
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_sqlite_connection():
    """Conecta ao banco SQLite"""
    conn = sqlite3.connect('agendamento.db')
    conn.text_factory = lambda x: str(x, 'utf-8', 'ignore')
    return conn

def get_postgres_connection():
    """Conecta ao banco PostgreSQL (Supabase)"""
    return psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        port=PG_PORT,
        sslmode='require' if PG_SSL else 'disable'
    )

def map_sqlite_type_to_pg(sqlite_type):
    """Mapeia tipos SQLite para tipos PostgreSQL"""
    t = sqlite_type.lower()
    if 'int' in t:
        return 'INTEGER'
    if 'char' in t or 'clob' in t or 'text' in t:
        return 'TEXT'
    if 'bool' in t:
        return 'BOOLEAN'
    if 'real' in t or 'floa' in t or 'doub' in t:
        return 'FLOAT'
    if 'date' in t or 'time' in t:
        return 'TIMESTAMP'
    return 'TEXT'

def get_table_schema(sqlite_conn, table_name):
    """Obtém o schema da tabela no SQLite"""
    cursor = sqlite_conn.execute(f'PRAGMA table_info({table_name})')
    columns = []
    for col in cursor.fetchall():
        columns.append({
            'name': col[1],
            'type': map_sqlite_type_to_pg(col[2]),
            'notnull': col[3],
            'pk': col[5]
        })
    return columns

def migrate_table(sqlite_conn, pg_conn, table_name):
    logging.info(f'Migrando tabela: {table_name}')
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f'SELECT * FROM {table_name}')
    rows = sqlite_cursor.fetchall()
    columns = [description[0] for description in sqlite_cursor.description]
    schema = get_table_schema(sqlite_conn, table_name)
    pg_cursor = pg_conn.cursor()
    # Montar SQL de criação
    create_table_sql = f'CREATE TABLE IF NOT EXISTS {table_name} ('
    col_defs = []
    pk_cols = [col['name'] for col in schema if col['pk']]
    bool_cols = [col['name'] for col in schema if col['type'] == 'BOOLEAN']
    for col in schema:
        col_def = f"{col['name']} {col['type']}"
        # Não adicionar PRIMARY KEY individualmente em tabelas de junção
        if col['pk'] and not (len(pk_cols) > 1):
            col_def += ' PRIMARY KEY'
        if col['notnull']:
            col_def += ' NOT NULL'
        col_defs.append(col_def)
    create_table_sql += ', '.join(col_defs)
    # Adicionar PRIMARY KEY composta para tabelas de junção
    if len(pk_cols) > 1:
        create_table_sql += f", PRIMARY KEY ({', '.join(pk_cols)})"
    create_table_sql += ')'
    pg_cursor.execute(create_table_sql)
    # Truncar tabela antes de inserir
    try:
        pg_cursor.execute(f'TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE')
    except Exception as e:
        logging.warning(f'Não foi possível truncar a tabela {table_name}: {e}')
    # Converter inteiros para booleanos nas colunas booleanas
    if rows and bool_cols:
        new_rows = []
        for row in rows:
            row = list(row)
            for idx, col in enumerate(columns):
                if col in bool_cols and row[idx] is not None:
                    row[idx] = bool(row[idx])
            new_rows.append(tuple(row))
        rows = new_rows
    # Inserir dados
    if rows:
        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s"
        try:
            execute_values(pg_cursor, insert_sql, rows)
        except Exception as e:
            logging.error(f'Erro ao inserir dados na tabela {table_name}: {e}')
    pg_conn.commit()
    logging.info(f'Tabela {table_name} migrada com sucesso!')

def main():
    try:
        sqlite_conn = get_sqlite_connection()
        pg_conn = get_postgres_connection()
        for table in TABLES:
            migrate_table(sqlite_conn, pg_conn, table)
        logging.info('Migração concluída com sucesso!')
    except Exception as e:
        logging.error(f'Erro durante a migração: {e}')
    finally:
        if 'sqlite_conn' in locals():
            sqlite_conn.close()
        if 'pg_conn' in locals():
            pg_conn.close()

if __name__ == "__main__":
    main() 