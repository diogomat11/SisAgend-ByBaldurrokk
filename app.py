# Imports e configurações iniciais
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, date, time, timedelta
import logging
import traceback
import re
import tempfile
from io import BytesIO
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, ForeignKey, 
    Date, DateTime, text, extract, Table, MetaData, inspect, and_
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, joinedload
import os
from unidecode import unidecode
import unicodedata
from dotenv import load_dotenv
import time as pytime  # Se precisar do time.sleep, use pytime.sleep()
from cachetools import cached, TTLCache

# Carregar variáveis de ambiente do arquivo .env
# load_dotenv(override=True)

# Obter a URL do banco de dados do arquivo .env
DATABASE_URL = os.getenv('DATABASE_URL')

print("DEBUG DATABASE_URL:", DATABASE_URL)

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Sistema de Agendamento",
    page_icon="📅",
    layout="wide"
)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# Função base para sessão do banco de dados
def get_session():
    """Retorna uma sessão do banco de dados"""
    try:
        session = Session()
        return session
    except Exception as e:
        logging.error(f"Erro ao criar sessão do banco de dados: {str(e)}")
        return None

# Configuração do banco de dados
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    echo=False
)
Session = sessionmaker(bind=engine)

# Constantes
DIAS_SEMANA_UTIL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira"]
DIAS_SEMANA_SABADO = ["Sábado"]
DIAS_SEMANA = {
    'SEGUNDA': 'Segunda-feira',
    'TERCA': 'Terça-feira',
    'QUARTA': 'Quarta-feira',
    'QUINTA': 'Quinta-feira',
    'SEXTA': 'Sexta-feira',
    'SABADO': 'Sábado'
}

HORARIOS_MANHA = [
    time(7, 0), time(8, 0), time(9, 0), time(10, 0), time(11, 0),
    time(12, 0)
]

HORARIOS_TARDE = [
    time(13, 0), time(14, 0), time(15, 0), time(16, 0),
    time(17, 0), time(18, 0)
]

HORARIOS_SABADO = [f"{h:02d}:00" for h in range(8, 12)]  # 08:00 a 11:00

HORARIOS_DISPONIVEIS = [
    time(7, 0), time(8, 0), time(9, 0), time(10, 0), time(11, 0),
    time(12, 0), time(13, 0), time(14, 0), time(15, 0), time(16, 0),
    time(17, 0), time(18, 0)
]

# Cache para resultados de consultas
cache = TTLCache(maxsize=100, ttl=300)
cache_unidades = TTLCache(maxsize=100, ttl=300)
cache_profissionais = TTLCache(maxsize=100, ttl=300)
cache_areas = TTLCache(maxsize=100, ttl=300)
cache_pagamentos = TTLCache(maxsize=100, ttl=300)
cache_perfis = TTLCache(maxsize=100, ttl=300)

@cached(cache_unidades)
def get_unidades_ativas(session):
    return session.query(Unidade).filter_by(ativo=True).all()

@cached(cache_profissionais)
def get_profissionais_ativos(session):
    return session.query(Profissional).filter_by(ativo=True).all()

@cached(cache_areas)
def get_areas_ativas(session):
    return session.query(AreaAtuacao).filter_by(ativo=True).all()

@cached(cache_pagamentos)
def get_pagamentos_ativos(session):
    return session.query(Pagamento).filter_by(ativo=True).all()

@cached(cache_perfis)
def get_perfis_ativos(session):
    return session.query(PerfilPaciente).filter_by(ativo=True).all()

# Funções auxiliares
def verificar_integridade_banco():
    """Verifica e cria o banco de dados se necessário"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Não foi possível conectar ao banco de dados")
            return False
            
        try:
            # Criar tabelas se não existirem
            Base.metadata.create_all(engine)
            
            # Carregar dados iniciais apenas se necessário
            carregar_dados_iniciais(session)
            
            session.commit()
            return True
            
        except Exception as e:
            logging.error(f"Erro ao verificar integridade do banco: {str(e)}")
            st.error(f"❌ Erro ao verificar integridade do banco: {str(e)}")
            return False

        finally:
            if session:
                session.close()
            
    except Exception as e:
        logging.error(f"Erro ao verificar integridade do banco: {str(e)}")
        st.error(f"❌ Erro ao verificar integridade do banco: {str(e)}")
        return False

def verificar_tabela_pacientes(session):
    """Verifica se as tabelas de pacientes existem e têm a estrutura correta"""
    try:
        # Verificar se as tabelas existem
        inspector = inspect(session.get_bind())
        
        # Verificar tabela de pacientes
        if 'pacientes' not in inspector.get_table_names():
            logging.info("Criando tabela de pacientes...")
            Base.metadata.tables['pacientes'].create(session.get_bind())
            st.info("ℹ️ Tabela de pacientes criada com sucesso!")
        else:
            # Verificar estrutura da tabela pacientes
            colunas_pacientes = [col['name'] for col in inspector.get_columns('pacientes')]
            colunas_necessarias = ['id', 'id_paciente_carteira', 'nome', 'created_at', 'updated_at']
            
            if not all(col in colunas_pacientes for col in colunas_necessarias):
                logging.warning("Estrutura da tabela pacientes incorreta. Recriando...")
                Base.metadata.tables['pacientes'].drop(session.get_bind())
                Base.metadata.tables['pacientes'].create(session.get_bind())
                st.warning("⚠️ Tabela de pacientes recriada com a estrutura correta")
        
        # Verificar tabela de carteiras
        if 'carteiras' not in inspector.get_table_names():
            logging.info("Criando tabela de carteiras...")
            Base.metadata.tables['carteiras'].create(session.get_bind())
            st.info("ℹ️ Tabela de carteiras criada com sucesso!")
        else:
            # Verificar estrutura da tabela carteiras
            colunas_carteiras = [col['name'] for col in inspector.get_columns('carteiras')]
            colunas_necessarias = ['id', 'numero_carteira', 'id_pagamento', 'status', 'paciente_id', 'created_at', 'updated_at']
            
            if not all(col in colunas_carteiras for col in colunas_necessarias):
                logging.warning("Estrutura da tabela carteiras incorreta. Recriando...")
                Base.metadata.tables['carteiras'].drop(session.get_bind())
                Base.metadata.tables['carteiras'].create(session.get_bind())
                st.warning("⚠️ Tabela de carteiras recriada com a estrutura correta")
        
        session.commit()
        return True
        
    except Exception as e:
        logging.error(f"Erro ao verificar tabelas de pacientes: {str(e)}")
        st.error(f"❌ Erro ao verificar tabelas de pacientes: {str(e)}")
        return False

# Tabelas de junção
profissional_area_atuacao = Table(
    'profissional_area_atuacao', Base.metadata,
    Column('profissional_id', Integer, ForeignKey('profissionais.id'), primary_key=True),
    Column('area_atuacao_id', Integer, ForeignKey('areas_atuacao.id'), primary_key=True)
)

profissional_pagamento = Table(
    'profissional_pagamento', Base.metadata,
    Column('profissional_id', Integer, ForeignKey('profissionais.id'), primary_key=True),
    Column('pagamento_id', Integer, ForeignKey('pagamentos.id'), primary_key=True)
)

profissional_perfil_paciente = Table(
    'profissional_perfil_paciente', Base.metadata,
    Column('profissional_id', Integer, ForeignKey('profissionais.id'), primary_key=True),
    Column('perfil_paciente_id', Integer, ForeignKey('perfis_paciente.id'), primary_key=True)
)

# Modelos
class Unidade(Base):
    """Modelo para unidades"""
    __tablename__ = 'unidades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    atende_sabado = Column(Boolean, default=False)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    salas = relationship("Sala", back_populates="unidade", cascade="all, delete-orphan")
    disponibilidades = relationship("Disponibilidade", back_populates="unidade", cascade="all, delete-orphan")

class Sala(Base):
    """Modelo para salas"""
    __tablename__ = 'salas'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(50), nullable=False)
    unidade_id = Column(Integer, ForeignKey('unidades.id'), nullable=False)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    unidade = relationship("Unidade", back_populates="salas")
    profissionais = relationship("Profissional", back_populates="sala", cascade="all, delete-orphan")
    disponibilidades_sala = relationship("DisponibilidadeSala", back_populates="sala", cascade="all, delete-orphan")

class AreaAtuacao(Base):
    """Modelo para áreas de atuação dos profissionais"""
    __tablename__ = 'areas_atuacao'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(String(200))
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    profissionais = relationship("Profissional", secondary="profissional_area_atuacao", back_populates="areas_atuacao")
    terminologias = relationship("Terminologia", back_populates="area_atuacao")

class Pagamento(Base):
    """Modelo para tipos de pagamento"""
    __tablename__ = 'pagamentos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    profissionais = relationship("Profissional", secondary="profissional_pagamento", back_populates="pagamentos")
    terminologias = relationship("Terminologia", back_populates="pagamento")

class PerfilPaciente(Base):
    """Modelo para perfis de pacientes"""
    __tablename__ = 'perfis_paciente'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(String(200))
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    profissionais = relationship("Profissional", secondary="profissional_perfil_paciente", back_populates="perfis_paciente")

class Disponibilidade(Base):
    """Modelo para disponibilidade de profissionais"""
    __tablename__ = 'disponibilidade'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    profissional_id = Column(Integer, ForeignKey('profissionais.id'), nullable=False)
    unidade_id = Column(Integer, ForeignKey('unidades.id'), nullable=True)
    dia_semana = Column(String(20), nullable=False)
    periodo = Column(String(20), nullable=False)  # 'Matutino' ou 'Vespertino'
    hora_inicio = Column(String(5), nullable=True)
    hora_fim = Column(String(5), nullable=True)
    status = Column(String(20), nullable=False, default='Disponível')
    
    # Relacionamentos
    profissional = relationship("Profissional", back_populates="disponibilidades")
    unidade = relationship("Unidade", back_populates="disponibilidades")

class DisponibilidadeSala(Base):
    """Modelo para disponibilidade de salas"""
    __tablename__ = 'disponibilidade_salas'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sala_id = Column(Integer, ForeignKey('salas.id'), nullable=False)
    dia_semana = Column(String(20), nullable=False)
    horario = Column(String(5), nullable=False)
    status = Column(String(20), nullable=False, default='Disponível')
    
    # Relacionamentos
    sala = relationship("Sala", back_populates="disponibilidades_sala")

class Terminologia(Base):
    """Modelo para terminologias"""
    __tablename__ = 'terminologias'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    descricao = Column(String(200), nullable=False)
    cod_faturamento = Column(String(50), nullable=False)
    tipo = Column(String(50), nullable=False)
    pagamento_id = Column(Integer, ForeignKey('pagamentos.id'), nullable=True)
    area_atuacao_id = Column(Integer, ForeignKey('areas_atuacao.id'), nullable=True)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    profissionais = relationship("Profissional", back_populates="terminologia")
    pagamento = relationship("Pagamento", back_populates="terminologias")
    area_atuacao = relationship("AreaAtuacao", back_populates="terminologias")

class Profissional(Base):
    """Modelo para profissionais"""
    __tablename__ = 'profissionais'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False, unique=True)
    cod_faturamento = Column(String(50), nullable=True)
    terminologia_id = Column(Integer, ForeignKey('terminologias.id'), nullable=True)
    sala_id = Column(Integer, ForeignKey('salas.id'), nullable=True)
    nome_conselho = Column(String(100), nullable=True)
    registro = Column(String(50), nullable=True)
    uf = Column(String(2), nullable=True)
    cbo = Column(String(10), nullable=True)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    terminologia = relationship("Terminologia", back_populates="profissionais")
    sala = relationship("Sala", back_populates="profissionais")
    disponibilidades = relationship("Disponibilidade", back_populates="profissional", cascade="all, delete-orphan")
    
    # Relacionamentos com as tabelas de junção
    areas_atuacao = relationship("AreaAtuacao", secondary=profissional_area_atuacao, back_populates="profissionais")
    pagamentos = relationship("Pagamento", secondary=profissional_pagamento, back_populates="profissionais")
    perfis_paciente = relationship("PerfilPaciente", secondary=profissional_perfil_paciente, back_populates="profissionais")

class AgendaFixa(Base):
    """Modelo para agenda fixa"""
    __tablename__ = 'agenda_fixa'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Date, nullable=False)
    dia_semana = Column(String(20), nullable=False)
    horario = Column(String(5), nullable=False)
    unidade = Column(String(100), nullable=False)
    sala = Column(String(50), nullable=True)
    profissional = Column(String(100), nullable=False)
    tipo_atend = Column(String(100), nullable=False)
    cod_faturamento = Column(String(50), nullable=True)
    qtd_sess = Column(Integer, nullable=True)
    pagamento = Column(String(50), nullable=True)
    paciente = Column(String(100), nullable=True)
    created_at = Column(Date, nullable=True, default=datetime.now().date())
    updated_at = Column(Date, nullable=True, default=datetime.now().date())

class Agendamento(Base):
    """Modelo para agendamentos"""
    __tablename__ = 'agendamentos'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    data_hora = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False)
    profissional_id = Column(Integer, ForeignKey('profissionais.id'), nullable=False)
    sala_id = Column(Integer, ForeignKey('salas.id'), nullable=False)
    paciente = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=True, default=datetime.now())
    updated_at = Column(DateTime, nullable=True, default=datetime.now())

class Paciente(Base):
    """Modelo para pacientes"""
    __tablename__ = 'pacientes'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_paciente_carteira = Column(Integer, nullable=False, unique=True)  # ID externo único
    nome = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=True, default=datetime.now())
    updated_at = Column(DateTime, nullable=True, default=datetime.now())
    
    # Relacionamentos
    carteiras = relationship("Carteira", back_populates="paciente", cascade="all, delete-orphan")

class Carteira(Base):
    """Modelo para carteiras dos pacientes"""
    __tablename__ = 'carteiras'
    __table_args__ = {'extend_existing': True}  # Permite recriar a tabela se necessário
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_carteira = Column(String(50), nullable=False)
    id_pagamento = Column(Integer, ForeignKey('pagamentos.id'), nullable=False)
    status = Column(String(20), nullable=False, default='Ativo')
    paciente_id = Column(Integer, ForeignKey('pacientes.id'), nullable=False)
    created_at = Column(DateTime, nullable=True, default=datetime.now())
    updated_at = Column(DateTime, nullable=True, default=datetime.now())
    
    # Relacionamentos
    paciente = relationship("Paciente", back_populates="carteiras")
    pagamento = relationship("Pagamento")

# Estilos CSS personalizados
st.markdown("""
<style>
/* Estilo geral */
.main {
    background-color: #f8f9fa;
    padding: 20px;
}

/* Botões */
.stButton>button {
    background-color: #6c5ce7;
    color: white;
    border-radius: 8px;
    padding: 12px 24px;
    border: none;
    font-weight: bold;
    transition: all 0.3s ease;
}
.stButton>button:hover {
    background-color: #5541d8;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

/* Campos de seleção */
.stSelectbox {
    background-color: white;
    border-radius: 8px;
    margin: 10px 0;
}

/* Upload de arquivos */
.stFileUploader {
    background-color: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    margin: 15px 0;
}

/* Mensagens */
.success-message {
    color: #00b894;
    font-weight: bold;
    padding: 10px;
    border-radius: 8px;
    background-color: rgba(0, 184, 148, 0.1);
    margin: 10px 0;
}
.error-message {
    color: #ff7675;
    font-weight: bold;
    padding: 10px;
    border-radius: 8px;
    background-color: rgba(255, 118, 117, 0.1);
    margin: 10px 0;
}

/* Cards */
.card {
    padding: 20px;
    border-radius: 12px;
    background-color: white;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    margin: 12px 0;
    transition: all 0.3s ease;
}
.card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 16px rgba(0,0,0,0.1);
}

/* Status de disponibilidade */
.disponivel {
    border-left: 5px solid #00b894;
}
.bloqueio {
    border-left: 5px solid #ff7675;
}
.em-atendimento {
    border-left: 5px solid #74b9ff;
}

/* Sidebar */
.sidebar .sidebar-content {
    background-color: #6c5ce7;
    color: white;
    padding: 20px;
}

/* Títulos */
h1, h2, h3 {
    color: #2d3436;
    font-weight: 700;
    margin: 20px 0;
}

/* Barra de progresso */
.stProgress > div > div {
    background-color: #6c5ce7;
}

/* Tabelas de dados */
.stDataFrame {
    border-radius: 8px;
    overflow: hidden;
    margin: 15px 0;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background-color: #f1f3f5;
    border-radius: 4px;
    color: #2d3436;
    padding: 8px 16px;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background-color: #6c5ce7;
    color: white;
}

/* Expander */
.streamlit-expanderHeader {
    font-weight: bold;
    color: #2d3436;
}
.streamlit-expanderContent {
    background-color: white;
    border-radius: 8px;
    padding: 15px;
    margin-top: 5px;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# 1. MODELOS DE DADOS
# =====================================================

# =====================================================
# 2. CONFIGURAÇÃO DO BANCO DE DADOS
# =====================================================

def fechar_conexoes():
    """Fecha todas as conexões ativas com o banco e remove o arquivo"""
    try:
        # Tentar fechar conexões SQLAlchemy
        try:
            if hasattr(get_session, 'engine'):
                get_session.engine.dispose()
                logging.info("Engine SQLAlchemy fechado")
        except Exception as e:
            logging.error(f"Erro ao fechar engine SQLAlchemy: {str(e)}")
        
        # Fechar conexões SQLite
        import sqlite3
        try:
            conn = sqlite3.connect('agendamento.db')
            conn.close()
            logging.info("Conexão SQLite fechada")
        except Exception as e:
            logging.error(f"Erro ao fechar conexão SQLite: {str(e)}")
        
        # Remover arquivo do banco
        if os.path.exists('agendamento.db'):
            try:
                os.remove('agendamento.db')
                logging.info("Arquivo do banco removido")
            except Exception as e:
                logging.error(f"Erro ao remover arquivo do banco: {str(e)}")
        
        logging.info("Fechamento de conexões concluído com sucesso")
        return True
    except Exception as e:
        logging.error(f"Erro no fechamento de conexões: {str(e)}")
        return False

def carregar_dados_iniciais_extras(session):
    """Carrega dados extras iniciais no banco de dados"""
    try:
        # Verificar e adicionar áreas de atuação
        areas_atuacao = [
            {"nome": "Psicologia", "descricao": "Atendimento psicológico"},
            {"nome": "Fonoaudiologia", "descricao": "Terapia fonoaudiológica"},
            {"nome": "Terapia Ocupacional", "descricao": "Terapia ocupacional"},
            {"nome": "Psicomotricidade", "descricao": "Terapia psicomotora"},
            {"nome": "Musicoterapia", "descricao": "Terapia através da música"},
            {"nome": "Fisioterapia", "descricao": "Terapia física"},
            {"nome": "Psicopedagogia", "descricao": "Acompanhamento psicopedagógico"}
        ]
        
        for area in areas_atuacao:
            if not session.query(AreaAtuacao).filter_by(nome=area["nome"]).first():
                nova_area = AreaAtuacao(**area)
                session.add(nova_area)
        
        # Verificar e adicionar perfis de paciente
        perfis = [
            {"nome": "Criança", "descricao": "Pacientes até 12 anos"},
            {"nome": "Adolescente", "descricao": "Pacientes de 13 a 18 anos"},
            {"nome": "Adulto", "descricao": "Pacientes acima de 18 anos"}
        ]
        
        for perfil in perfis:
            if not session.query(PerfilPaciente).filter_by(nome=perfil["nome"]).first():
                novo_perfil = PerfilPaciente(**perfil)
                session.add(novo_perfil)
        
        # Verificar e adicionar pagamentos
        pagamentos = ["Particular", "Convênio", "Plano de Saúde"]
        
        for nome_pagamento in pagamentos:
            if not session.query(Pagamento).filter_by(nome=nome_pagamento).first():
                novo_pagamento = Pagamento(nome=nome_pagamento, ativo=True)
                session.add(novo_pagamento)
        
        session.commit()
        return True
        
    except Exception as e:
        session.rollback()
        logging.error(f"Erro ao carregar dados iniciais extras: {str(e)}")
        st.error(f"❌ Erro ao carregar dados iniciais extras: {str(e)}")
        return False

# Atualizar a função carregar_dados_iniciais existente
def carregar_dados_iniciais(session):
    """Carrega dados iniciais no banco de dados"""
    try:
        # Verificar e carregar dados das tabelas existentes
        carregar_dados_iniciais_extras(session)
        
        # Verificar se as tabelas existem e recriar se necessário
        inspector = inspect(session.get_bind())
        
        # Recriar tabela de pacientes se necessário
        if 'pacientes' not in inspector.get_table_names():
            Base.metadata.tables['pacientes'].create(session.get_bind())
            logging.info("Tabela de pacientes criada")
            
        # Recriar tabela de carteiras se necessário
        if 'carteiras' in inspector.get_table_names():
            # Dropar tabela existente para recriar com a estrutura correta
            Base.metadata.tables['carteiras'].drop(session.get_bind())
            logging.info("Tabela de carteiras antiga removida")
            
        Base.metadata.tables['carteiras'].create(session.get_bind())
        logging.info("Tabela de carteiras recriada com a estrutura correta")
        
        return True
        
    except Exception as e:
        logging.error(f"Erro ao carregar dados iniciais: {str(e)}")
        return False

def verificar_tabela_unidades(session):
    """Verifica e recria a tabela unidades se necessário"""
    try:
        # Verifica se a tabela existe e tem a estrutura correta
        inspector = inspect(engine)
        if 'unidades' not in inspector.get_table_names():
            # Se a tabela não existe, cria
            Base.metadata.tables['unidades'].create(session.get_bind())
            session.commit()
            st.info("ℹ️ Tabela de unidades criada com sucesso!")
        else:
            # Verifica se tem todas as colunas necessárias
            colunas_existentes = [col['name'] for col in inspector.get_columns('unidades')]
            colunas_necessarias = ['id', 'nome', 'atende_sabado', 'ativo']
            
            if not all(col in colunas_existentes for col in colunas_necessarias):
                # Se faltam colunas, faz backup dos dados
                unidades_backup = []
                try:
                    unidades_backup = [(u.id, u.nome) for u in session.query(Unidade).all()]
                except:
                    pass
                
                # Recria a tabela
                Base.metadata.tables['unidades'].drop(session.get_bind())
                Base.metadata.tables['unidades'].create(session.get_bind())
                
                # Restaura os dados
                for id_unidade, nome in unidades_backup:
                    unidade = Unidade(id=id_unidade, nome=nome, atende_sabado=False, ativo=True)
                    session.add(unidade)
                
                session.commit()
                st.info("ℹ️ Tabela de unidades atualizada com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao verificar tabela de unidades: {str(e)}")
        logging.error(f"Erro ao verificar tabela de unidades: {str(e)}\n{traceback.format_exc()}")
        raise

def verificar_tabela_salas(session):
    """Verifica e recria a tabela salas se necessário"""
    try:
        # Verifica se a tabela existe e tem a estrutura correta
        inspector = inspect(engine)
        if 'salas' not in inspector.get_table_names():
            # Se a tabela não existe, cria
            Base.metadata.tables['salas'].create(session.get_bind())
            session.commit()
            st.info("ℹ️ Tabela de salas criada com sucesso!")
        else:
            # Verifica se tem todas as colunas necessárias
            colunas_existentes = [col['name'] for col in inspector.get_columns('salas')]
            colunas_necessarias = ['id', 'nome', 'unidade_id', 'ativo']
            
            if not all(col in colunas_existentes for col in colunas_necessarias):
                # Se faltam colunas, faz backup dos dados
                salas_backup = []
                try:
                    salas_backup = [(s.id, s.nome, s.unidade_id) for s in session.query(Sala).all()]
                except:
                    pass
                
                # Recria a tabela
                Base.metadata.tables['salas'].drop(session.get_bind())
                Base.metadata.tables['salas'].create(session.get_bind())
                
                # Restaura os dados
                for id_sala, nome, unidade_id in salas_backup:
                    sala = Sala(id=id_sala, nome=nome, unidade_id=unidade_id, ativo=True)
                    session.add(sala)
                
                session.commit()
                st.info("ℹ️ Tabela de salas atualizada com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao verificar tabela de salas: {str(e)}")
        logging.error(f"Erro ao verificar tabela de salas: {str(e)}\n{traceback.format_exc()}")
        raise

def verificar_tabela_profissionais(session):
    """Verifica se a tabela de profissionais existe"""
    try:
        # Verifica se a tabela existe
        if not inspect(engine).has_table("profissionais"):
            Base.metadata.create_all(engine)
            st.info("ℹ️ Tabela de profissionais criada com sucesso!")
        return True
    except Exception as e:
        logging.error(f"Erro ao verificar tabela de profissionais: {str(e)}")
        return False

def verificar_tabela_disponibilidade(session):
    """Verifica e recria a tabela disponibilidade se necessário"""
    try:
        # Verifica se a tabela existe e tem a estrutura correta
        inspector = inspect(engine)
        if 'disponibilidade' not in inspector.get_table_names():
            # Se a tabela não existe, cria
            Base.metadata.tables['disponibilidade'].create(session.get_bind())
            session.commit()
            st.info("ℹ️ Tabela de disponibilidade criada com sucesso!")
        else:
            # Verifica se tem todas as colunas necessárias
            colunas_existentes = [col['name'] for col in inspector.get_columns('disponibilidade')]
            colunas_necessarias = ['id', 'profissional_id', 'unidade_id', 'dia_semana', 'hora_inicio', 'status']
            
            if not all(col in colunas_existentes for col in colunas_necessarias):
                # Se faltam colunas, faz backup dos dados
                disponibilidades_backup = []
                try:
                    disponibilidades_backup = [
                        (d.id, d.profissional_id, d.unidade_id, d.dia_semana, d.hora_inicio, d.status) 
                        for d in session.query(Disponibilidade).all()
                    ]
                except:
                    pass
                
                # Recria a tabela
                Base.metadata.tables['disponibilidade'].drop(session.get_bind())
                Base.metadata.tables['disponibilidade'].create(session.get_bind())
                
                # Restaura os dados
                for id_disp, prof_id, unid_id, dia, hora, status in disponibilidades_backup:
                    disponibilidade = Disponibilidade(
                        id=id_disp,
                        profissional_id=prof_id,
                        unidade_id=unid_id,
                        dia_semana=dia,
                        hora_inicio=hora,
                        status=status
                    )
                    session.add(disponibilidade)
                
                session.commit()
                st.info("ℹ️ Tabela de disponibilidade atualizada com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao verificar tabela de disponibilidade: {str(e)}")
        logging.error(f"Erro ao verificar tabela de disponibilidade: {str(e)}")

# Inicializar banco de dados
if not verificar_integridade_banco():
    st.error("❌ Falha ao verificar/criar banco de dados")
    st.stop()

# =====================================================
# 3. FUNÇÕES DE PROCESSAMENTO
# =====================================================

def remover_acentos(texto: str) -> str:
    """Remove acentos de um texto"""
    if not isinstance(texto, str):
        return ''
    nfkd = unicodedata.normalize('NFKD', texto)
    return u"".join([c for c in nfkd if not unicodedata.combining(c)])

def normalizar_texto(texto):
    """Normaliza um texto removendo acentos, caracteres especiais e espaços extras"""
    try:
        if pd.isna(texto) or texto is None:
            return ""
        
        # Converter para string
        texto = str(texto)
        
        # Remover caracteres especiais e acentos
        texto = unidecode(texto)
        
        # Converter para minúsculo
        texto = texto.lower()
        
        # Remover caracteres especiais mantendo letras, números e espaços
        texto = re.sub(r'[^a-z0-9\s]', '', texto)
        
        # Remover espaços extras
        texto = ' '.join(texto.split())
        
        return texto
    except Exception as e:
        logging.error(f"Erro ao normalizar texto '{texto}': {str(e)}")
        return texto

def criar_ou_obter_unidade(session, nome_unidade):
    """Cria ou obtém uma unidade, tratando caracteres especiais"""
    try:
        if not nome_unidade or pd.isna(nome_unidade):
            st.error("❌ Nome da unidade não pode ser vazio")
            return None
        
        # Limpar e normalizar o nome
        nome_unidade = str(nome_unidade).strip()
        nome_normalizado = normalizar_texto(nome_unidade)
        
        # Buscar primeiro pelo nome original
        unidade = session.query(Unidade).filter(
            Unidade.nome == nome_unidade
                ).first()
                
        if not unidade:
            # Buscar pelo nome normalizado
            unidade = session.query(Unidade).filter(
                Unidade.nome.ilike(f"%{nome_normalizado}%")
            ).first()
        
        if not unidade:
            unidade = Unidade(
                nome=nome_unidade  # Mantém o nome original com acentos
            )
            session.add(unidade)
            session.flush()
            st.success(f"✅ Nova unidade criada: {nome_unidade}")
        
        return unidade
        
    except Exception as e:
        st.error(f"❌ Erro ao criar/obter unidade: {str(e)}")
        return None

def normalizar_dia_semana(dia: str) -> str:
    """Normaliza o nome do dia da semana para o formato simplificado"""
    if not dia or pd.isna(dia):
        return None
        
    dia = str(dia).strip().lower()
    dia = remover_acentos(dia)
    
    # Mapeamento para formato simplificado
    dias_simplificados = {
        'segunda': 'Segunda',
        'segunda-feira': 'Segunda',
        'segunda feira': 'Segunda',
        'terca': 'Terça',
        'terça': 'Terça',
        'terca-feira': 'Terça',
        'terça-feira': 'Terça',
        'terca feira': 'Terça',
        'terça feira': 'Terça',
        'quarta': 'Quarta',
        'quarta-feira': 'Quarta',
        'quarta feira': 'Quarta',
        'quinta': 'Quinta',
        'quinta-feira': 'Quinta',
        'quinta feira': 'Quinta',
        'sexta': 'Sexta',
        'sexta-feira': 'Sexta',
        'sexta feira': 'Sexta',
        'sabado': 'Sábado',
        'sábado': 'Sábado',
        'domingo': 'Domingo'
    }
    
    # Também mapear formatos com "feira" já normalizado
    formatos_normalizados = {
        'segunda-feira': 'Segunda',
        'terça-feira': 'Terça',
        'quarta-feira': 'Quarta',
        'quinta-feira': 'Quinta',
        'sexta-feira': 'Sexta'
    }
    
    # Tentar mapeamento direto
    resultado = dias_simplificados.get(dia)
    if resultado:
        return resultado
        
    # Tentar encontrar o dia na string
    for chave, valor in dias_simplificados.items():
        if chave.split()[0] in dia:
            return valor
            
    # Verificar formatos normalizados
    for chave, valor in formatos_normalizados.items():
        if chave in dia:
            return valor
            
    # Se nada encontrado, retornar None
    return None

def converter_periodo_para_hora(periodo):
    """Converte diferentes formatos de hora para o padrão HH:MM"""
    try:
        if pd.isna(periodo) or periodo is None:
            return None
            
        # Se for objeto datetime.time
        if hasattr(periodo, 'strftime'):
            return periodo.strftime('%H:%M')
            
        # Se já for string, limpar e padronizar
        if isinstance(periodo, str):
            # Remover espaços e converter para minúsculo
            periodo = periodo.strip().lower()
            
            # Remover caracteres especiais mantendo números e separadores
            periodo = periodo.replace('h', ':').replace('hs', ':').replace('.', ':').replace('hrs', ':')
            
            # Se terminar com ':', adicionar '00'
            if periodo.endswith(':'):
                periodo += '00'
            
            # Se for apenas número (ex: '7'), adicionar ':00'
            if periodo.isdigit():
                periodo = f'{int(periodo):02d}:00'
            
            # Tratar formato com um dígito na hora (ex: '7:00' -> '07:00')
            if re.match(r'^\d:\d{2}$', periodo):
                periodo = f'0{periodo}'
            
            # Se não tiver minutos, adicionar
            if ':' not in periodo and len(periodo) <= 2:
                periodo = f'{int(periodo):02d}:00'
            
            # Tratar formato HH:MM:SS
            partes = periodo.split(':')
            if len(partes) == 3:  # Formato HH:MM:SS
                try:
                    hora = int(partes[0])
                    minuto = int(partes[1])
                    if 0 <= hora <= 23 and 0 <= minuto <= 59:
                        return f'{hora:02d}:{minuto:02d}'
                    else:
                        logging.error(f"Valores de hora/minuto inválidos: {periodo}")
                        return None
                except ValueError:
                    logging.error(f"Erro ao converter valores de hora: {periodo}")
                    return None
            elif len(partes) == 2:  # Formato HH:MM
                try:
                    hora = int(partes[0])
                    minuto = int(partes[1])
                    if 0 <= hora <= 23 and 0 <= minuto <= 59:
                        return f'{hora:02d}:{minuto:02d}'
                    else:
                        logging.error(f"Valores de hora/minuto inválidos: {periodo}")
                        return None
                except ValueError:
                    logging.error(f"Erro ao converter valores de hora: {periodo}")
                    return None
            
            # Verificar se o formato está correto
            if not re.match(r'^\d{2}:\d{2}$', periodo):
                logging.error(f"Formato de hora inválido: {periodo}")
                return None
            
            return periodo
        
        # Se for número decimal do Excel
        if isinstance(periodo, (int, float)):
            try:
                horas = int(periodo)
                minutos = int((periodo - horas) * 60)
                return f'{horas:02d}:{minutos:02d}'
            except:
                logging.error(f"Erro ao converter número para hora: {periodo}")
                return None
        
        # Se chegou aqui, tentar extrair números
        numeros = re.findall(r'\d+', str(periodo))
        if len(numeros) >= 2:
            hora = int(numeros[0])
            minuto = int(numeros[1])
            if 0 <= hora <= 23 and 0 <= minuto <= 59:
                return f'{hora:02d}:{minuto:02d}'
        elif len(numeros) == 1:
            hora = int(numeros[0])
            if 0 <= hora <= 23:
                return f'{hora:02d}:00'
        
        logging.error(f"Não foi possível converter o valor para hora: {periodo}")
        return None
        
    except Exception as e:
        logging.error(f"Erro ao converter período {periodo}: {str(e)}")
        return None

def formatar_data(data_valor):
    """Formata uma data para o padrão dd/mm/aaaa"""
    try:
        if pd.isna(data_valor):
            return None
            
        if isinstance(data_valor, str):
            # Tentar converter string para data
            try:
                data_obj = pd.to_datetime(data_valor)
                return data_obj.strftime('%d/%m/%Y')
            except:
                return None
        elif isinstance(data_valor, (datetime, date)):
            return data_valor.strftime('%d/%m/%Y')
        elif isinstance(data_valor, pd.Timestamp):
            return data_valor.strftime('%d/%m/%Y')
        else:
            return None
    except:
        return None

def converter_para_inteiro(valor):
    """Converte um valor para inteiro"""
    try:
        if pd.isna(valor):
            return None
            
        if isinstance(valor, (int, float)):
            return int(valor)
        elif isinstance(valor, str) and valor.isdigit():
            return int(valor)
        else:
            try:
                # Tentar converter removendo casas decimais
                return int(float(valor))
            except:
                return None
    except:
        return None

def converter_para_texto(valor):
    """Converte um valor para texto, preservando zeros à esquerda"""
    try:
        if pd.isna(valor):
            return None
            
        # Remover formatação especial de fórmulas do Excel
        if isinstance(valor, str):
            # Remover formatação de fórmula
            if valor.startswith('='):
                valor = valor.lstrip('=')
            # Remover aspas
            valor = valor.replace('"', '').replace("'", "")
            return valor.strip()
        else:
            # Se for número, converter para string preservando zeros
            return str(valor).strip()
    except:
        if valor is not None:
            return str(valor)
        return None

def normalizar_hora(valor):
    """Normaliza o formato da hora para HH:MM"""
    try:
        if pd.isna(valor):
            return None
            
        # Se for objeto datetime.time ou datetime
        if hasattr(valor, 'strftime'):
            return valor.strftime('%H:%M')
            
        # Se for string
        if isinstance(valor, str):
            # Remover espaços
            valor = valor.strip()
            
            # Se for apenas número, adicionar :00
            if valor.isdigit():
                return f"{int(valor):02d}:00"
            
            # Tratar formato HH:MM:SS
            partes = valor.split(':')
            if len(partes) >= 2:  # Formato HH:MM ou HH:MM:SS
                try:
                    hora = int(partes[0])
                    minuto = int(partes[1])
                    if 0 <= hora <= 23 and 0 <= minuto <= 59:
                        return f"{hora:02d}:{minuto:02d}"
                except ValueError:
                    logging.error(f"Erro ao converter valores de hora: {valor}")
                    return None
            
        # Se for número
        if isinstance(valor, (int, float)):
            hora = int(valor)
            return f"{hora:02d}:00"
            
        return None
    except Exception as e:
        logging.error(f"Erro ao normalizar hora: {valor} - {str(e)}")
        return None

def processar_agenda_fixa(df):
    """Processa o arquivo de agenda fixa"""
    try:
        logging.info("=== INÍCIO DO PROCESSAMENTO DA AGENDA FIXA ===")
        logging.info(f"Tipo do DataFrame: {type(df)}")
        logging.info(f"Colunas do DataFrame: {df.columns.tolist()}")
        
        session = get_session()
        if not session:
            logging.error("❌ Erro ao conectar ao banco de dados")
            st.error("❌ Erro ao conectar ao banco de dados")
            return False
        
        try:
            # Inicializar conjuntos para controle
            grades_criadas = set()
            profissionais_incompletos = set()
            
            # Dicionário para rastrear a primeira ocorrência de unidade por profissional, dia e período
            unidades_por_profissional = {}  # formato: {(prof_id, dia, periodo): unidade_id}
            
            # Verificar se a coluna Id Profissional existe
            if 'Id Profissional' not in df.columns:
                logging.error("❌ Coluna 'Id Profissional' não encontrada no arquivo")
                st.error("❌ Coluna 'Id Profissional' não encontrada no arquivo")
                return False
            
            # Verificar se há valores nulos no ID
            if df['Id Profissional'].isnull().any():
                st.error("❌ Existem registros sem ID de profissional no arquivo")
                return False
            
            logging.info(f"Colunas do DataFrame: {df.columns.tolist()}")
            
            # 1. Limpar dados existentes
            logging.info("Limpando dados existentes")
            session.query(AgendaFixa).delete()
            session.query(Disponibilidade).delete()
            session.commit()

            # 2. Primeiro, criar ou atualizar todos os profissionais e gerar suas grades
            profissionais_unicos = df[['Id Profissional', 'Profissional']].drop_duplicates()
            logging.info(f"Total de profissionais únicos: {len(profissionais_unicos)}")

            for _, row in profissionais_unicos.iterrows():
                try:
                    profissional_id = int(float(row['Id Profissional']))
                    
                    # Verificar se o profissional existe
                    profissional = session.query(Profissional).get(profissional_id)
                    if not profissional:
                        # Criar novo profissional se não existir
                        profissional = Profissional(
                            id=profissional_id,
                            nome=row['Profissional']
                        )
                        session.add(profissional)
                        session.flush()
                    
                    # Gerar grade para o profissional
                    try:
                        gerar_grade_profissional(session, profissional_id)
                        grades_criadas.add(profissional_id)
                        logging.info(f"Grade gerada para profissional {profissional_id}")
                    except Exception as e:
                        logging.error(f"Erro ao gerar grade para profissional {profissional_id}: {str(e)}")
                        profissionais_incompletos.add(profissional_id)
                except Exception as e:
                    logging.error(f"Erro ao processar profissional {row['Id Profissional']}: {str(e)}")
                    continue
                
            session.commit()
            
            # 3. Processar cada linha do arquivo para criar agendamentos
            registros_processados = 0
            registros_ignorados = 0
            erros = []
        
            for idx, row in df.iterrows():
                try:
                    logging.info(f"Processando linha {idx+2}")
                    logging.info(f"Dados da linha: {row.to_dict()}")
                    
                    # Obter e converter ID do profissional para inteiro
                    profissional_id = int(float(row['Id Profissional']))
                    
                    # Converter data
                    data = pd.to_datetime(row['Data']).date()
                    dia_semana = obter_dia_semana(data)
                    if not dia_semana:
                        erros.append(f"Erro ao obter dia da semana na linha {idx+2}: {data}")
                        registros_ignorados += 1
                        continue
                        
                    # Converter dia da semana para o formato da grade (sem '-feira')
                    dia_grade = dia_semana.replace('-feira', '') if '-feira' in dia_semana else dia_semana
                    logging.info(f"Data: {data}, Dia da semana: {dia_semana}, Dia grade: {dia_grade}")
                    
                    # Normalizar horário
                    hora_inicial = normalizar_hora(row['Hora inicial'])
                    if not hora_inicial:
                        erros.append(f"Erro ao normalizar horário na linha {idx+2}: {row['Hora inicial']}")
                        registros_ignorados += 1
                        continue
                    
                    logging.info(f"Hora inicial normalizada: {hora_inicial}")
                    
                    # Verificar se o horário está dentro do intervalo permitido
                    hora = int(hora_inicial.split(':')[0])
                    if hora < 7 or hora > 18:
                        logging.warning(f"Horário fora do intervalo permitido: {hora_inicial}")
                        erros.append(f"Horário fora do intervalo permitido (07:00-18:00) na linha {idx+2}: {hora_inicial}")
                        registros_ignorados += 1
                        continue
                    
                    # Corrigir nome da unidade República do Líbano se necessário
                    nome_unidade = row['Unidade']
                    if nome_unidade and "Rep" in nome_unidade and "bano" in nome_unidade:
                        if nome_unidade.startswith("Rep") and "lica" in unidecode(nome_unidade).lower() and "bano" in unidecode(nome_unidade).lower():
                            nome_unidade = "República do Líbano"
                            logging.info(f"Nome da unidade corrigido para: {nome_unidade}")
                    
                    # Criar ou obter unidade
                    unidade = criar_ou_obter_unidade(session, nome_unidade)
                    if not unidade:
                        erros.append(f"Erro ao criar/obter unidade na linha {idx+2}: {nome_unidade}")
                        registros_ignorados += 1
                        continue
                    
                    # Criar registro na agenda fixa
                    agenda = AgendaFixa(
                        data=data,
                        dia_semana=dia_semana,
                        horario=hora_inicial,
                        unidade=nome_unidade,
                        sala=row['Sala'] if 'Sala' in row else None,
                        profissional=row['Profissional'],
                        tipo_atend=row['Tipo Atend'] if 'Tipo Atend' in row else None,
                        cod_faturamento=row['Codigo Faturamento'] if 'Codigo Faturamento' in row else None,
                        qtd_sess=row['Qtd Sess'] if 'Qtd Sess' in row else None,
                        pagamento=row['Pagamento'] if 'Pagamento' in row else None,
                        paciente=row['Paciente'] if 'Paciente' in row else None
                    )
                    session.add(agenda)
                    
                    # Determinar o período com base na hora
                    periodo = 'Matutino' if hora < 13 else 'Vespertino'
                    
                    # Salvar a unidade para este profissional, dia e período
                    chave = (profissional_id, dia_grade, periodo)
                    if chave not in unidades_por_profissional:
                        unidades_por_profissional[chave] = unidade.id
                        logging.info(f"Primeira ocorrência: Prof {profissional_id}, {dia_grade}, {periodo} - Unidade {unidade.id}")
                    
                    # Atualizar status na grade de disponibilidade
                    if row.get('Paciente'):
                        try:
                            disponibilidade = session.query(Disponibilidade).filter(
                                Disponibilidade.profissional_id == profissional_id,
                                Disponibilidade.dia_semana == dia_grade,
                                Disponibilidade.hora_inicio == hora_inicial
                            ).first()
                    
                            if disponibilidade:
                                logging.info(f"Atualizando status para Em atendimento: Prof {profissional_id}, {dia_grade}, {hora_inicial}")
                                disponibilidade.status = 'Em atendimento'
                                disponibilidade.unidade_id = unidade.id
                                session.flush()
                            else:
                                logging.warning(f"Disponibilidade não encontrada: Prof {profissional_id}, {dia_grade}, {hora_inicial}")
                                erros.append(f"Disponibilidade não encontrada na linha {idx+2}: Prof {profissional_id}, {dia_grade}, {hora_inicial}")
                        except Exception as e:
                            logging.error(f"Erro ao atualizar disponibilidade: {str(e)}")
                            erros.append(f"Erro ao atualizar disponibilidade na linha {idx+2}: {str(e)}")
                    
                    registros_processados += 1
                    
                except Exception as e:
                    erros.append(f"Erro ao processar linha {idx+2}: {str(e)}")
                    registros_ignorados += 1
                    continue
            
            # Depois de processar todas as linhas, atualizar as unidades na grade de disponibilidade
            for (prof_id, dia, periodo), unidade_id in unidades_por_profissional.items():
                try:
                    # Atualizar todas as disponibilidades deste profissional para este dia e período
                    disponibilidades = session.query(Disponibilidade).filter(
                        Disponibilidade.profissional_id == prof_id,
                        Disponibilidade.dia_semana == dia,
                        Disponibilidade.periodo == periodo
                    ).all()
                    
                    for disp in disponibilidades:
                        disp.unidade_id = unidade_id
                    
                    logging.info(f"Atribuída unidade {unidade_id} para todas as disponibilidades do profissional {prof_id} no dia {dia}, período {periodo}")
                    
                except Exception as e:
                    logging.error(f"Erro ao atribuir unidade para profissional {prof_id}, dia {dia}, período {periodo}: {str(e)}")
                    erros.append(f"Erro ao atribuir unidade para profissional {prof_id}, dia {dia}, período {periodo}: {str(e)}")
            
            # Commit das alterações
            session.commit()
                
            # Retornar estatísticas
            return {
                'processados': registros_processados,
                'ignorados': registros_ignorados,
                'erros': erros,
                'profissionais_incompletos': list(profissionais_incompletos)
            }
                
        except Exception as e:
            session.rollback()
            logging.error(f"Erro ao processar arquivo: {str(e)}")
            raise Exception(f"Erro ao processar arquivo: {str(e)}")
            
    except Exception as e:
        logging.error(f"Erro ao processar agenda fixa: {str(e)}")
        st.error(f"❌ Erro ao processar agenda fixa: {str(e)}")
        return False

def processar_bloqueios(df: pd.DataFrame) -> bool:
    """Processa o arquivo de bloqueios"""
    try:
        # Exibir status de processamento
        with st.spinner("Processando arquivo de bloqueios..."):
            # Verificar colunas obrigatórias
            colunas_esperadas = {
                'DIA DA SEMANA': 'dia_semana',
                'PERIODO': 'horario',
                'ID PROFISSIONAL': 'profissional_id'
            }
            
            colunas_faltantes = [col for col in colunas_esperadas.keys() if col not in df.columns]
            if colunas_faltantes:
                st.error(f"❌ Colunas obrigatórias faltando: {', '.join(colunas_faltantes)}")
                return False
            
            # Criar cópia do DataFrame para não modificar o original
            df_processado = df.copy()
            
            # Normalizar horário (PERIODO)
            def normalizar_horario(horario):
                if pd.isna(horario):
                    return None
                try:
                    # Remover possíveis segundos
                    horario = str(horario).strip()
                    if ':' in horario:
                        partes = horario.split(':')
                        # Se tiver segundos, pegar apenas hora e minuto
                        if len(partes) > 2:
                            hora = int(partes[0])
                            minuto = int(partes[1])
                        else:
                            hora = int(partes[0])
                            minuto = int(partes[1]) if len(partes) > 1 else 0
                    else:
                        # Se for apenas número, considerar como hora
                        hora = int(float(horario))
                        minuto = 0
                    
                    # Garantir formato HH:MM
                    return f"{hora:02d}:{minuto:02d}"
                except Exception as e:
                    logging.error(f"Erro ao normalizar horário '{horario}': {str(e)}")
                    return None

            # Aplicar normalizações
            df_processado['horario'] = df_processado['PERIODO'].apply(normalizar_horario)
            df_processado['dia_semana'] = df_processado['DIA DA SEMANA'].apply(lambda x: normalizar_dia_semana(str(x)))
            df_processado['profissional_id'] = df_processado['ID PROFISSIONAL'].apply(lambda x: int(float(x)) if pd.notna(x) else None)
            
            # Verificar se há valores inválidos após normalização
            registros_invalidos = df_processado[
                (df_processado['horario'].isna()) |
                (df_processado['dia_semana'].isna()) |
                (df_processado['profissional_id'].isna())
            ]
            
            if not registros_invalidos.empty:
                st.warning("⚠️ Alguns registros contêm valores inválidos:")
                for idx, row in registros_invalidos.iterrows():
                    st.write(f"Linha {idx+2}: Dia={row['DIA DA SEMANA']}, Período={row['PERIODO']}, ID={row['ID PROFISSIONAL']}")
                if not st.button("Continuar mesmo assim"):
                    return False
            
            # Obter sessão do banco
            session = get_session()
            if not session:
                st.error("❌ Erro ao conectar ao banco de dados")
                return False
                
            try:
                registros_processados = 0
                registros_ignorados = 0
                erros = []
                profissionais_afetados = set()
                
                # Processar cada linha
                for idx, row in df_processado.iterrows():
                    try:
                        if pd.isna(row['horario']) or pd.isna(row['dia_semana']) or pd.isna(row['profissional_id']):
                            erros.append(f"Dados inválidos na linha {idx+2}")
                            registros_ignorados += 1
                            continue
                        
                        # Buscar profissional
                        profissional = session.query(Profissional).get(row['profissional_id'])
                        if not profissional:
                            erros.append(f"Profissional não encontrado na linha {idx+2}: ID {row['profissional_id']}")
                            registros_ignorados += 1
                            continue
                        
                        # Buscar disponibilidade específica
                        disponibilidade = session.query(Disponibilidade).filter(
                            Disponibilidade.profissional_id == profissional.id,
                            Disponibilidade.dia_semana == row['dia_semana'],
                            Disponibilidade.hora_inicio == row['horario']
                        ).first()
                        
                        if disponibilidade:
                            disponibilidade.status = 'Bloqueio'
                            registros_processados += 1
                            profissionais_afetados.add(profissional.nome)
                            logging.info(f"Bloqueio aplicado para profissional {profissional.nome} no dia {row['dia_semana']} às {row['horario']}")
                        else:
                            erros.append(f"Disponibilidade não encontrada para profissional {profissional.nome} no dia {row['dia_semana']} às {row['horario']}")
                            registros_ignorados += 1
                            
                    except Exception as e:
                        erros.append(f"Erro ao processar linha {idx+2}: {str(e)}")
                        registros_ignorados += 1
                        continue
                
                # Commit das alterações
                session.commit()
        
                # Exibir resultados
                st.success("✅ Arquivo processado com sucesso!")
                
                # Métricas
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Registros Processados", registros_processados)
                with col2:
                    st.metric("Registros Ignorados", registros_ignorados)
                with col3:
                    st.metric("Profissionais Afetados", len(profissionais_afetados))
                
                # Detalhes dos profissionais afetados
                if profissionais_afetados:
                    with st.expander("Profissionais Afetados"):
                        for prof in sorted(profissionais_afetados):
                            st.write(f"- {prof}")
                
                # Detalhes dos erros
                if erros:
                    with st.expander("Ver detalhes dos erros"):
                        for erro in erros:
                            st.write(f"- {erro}")
                
                return True
    
            except Exception as e:
                session.rollback()
                st.error(f"❌ Erro ao processar bloqueios: {str(e)}")
                return False
                
    except Exception as e:
        st.error(f"❌ Erro ao processar arquivo: {str(e)}")
        return False

def gerenciar_unidades():
    """Interface para gerenciamento de unidades"""
    st.title("🏥 Gestão de Unidades")
    
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return
        
        # Listar unidades existentes
        unidades = session.query(Unidade).all()
        
        if unidades:
            for unidade in unidades:
                with st.expander(f"📍 {unidade.nome} - {'Ativo' if unidade.ativo else 'Inativo'}"):
                    novo_nome = st.text_input("Nome", value=unidade.nome, key=f"nome_{unidade.id}")
                    atende_sabado = st.selectbox(
                        "Atende Sábado",
                        ["Sim", "Não"],
                        index=0 if unidade.atende_sabado else 1,
                        key=f"sabado_{unidade.id}"
                    )
                    status = st.selectbox(
                        "Status",
                        ["Ativo", "Inativo"],
                        index=0 if unidade.ativo else 1,
                        key=f"status_{unidade.id}"
                    )
                    
                    if st.button("💾 Salvar", key=f"btn_salvar_{unidade.id}"):
                        try:
                            unidade.nome = novo_nome
                            unidade.atende_sabado = atende_sabado == "Sim"
                            unidade.ativo = status == "Ativo"
                            session.commit()
                            st.success("✅ Unidade atualizada com sucesso!")
                        except Exception as e:
                            session.rollback()
                            st.error(f"❌ Erro ao atualizar unidade: {str(e)}")
        else:
            st.info("ℹ️ Nenhuma unidade cadastrada")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerenciar unidades: {str(e)}")
    finally:
        session.close()

def verificar_banco_dados():
    """Verifica se o banco de dados existe e está acessível"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Não foi possível criar sessão do banco de dados")
            return False

        # Criar tabelas se não existirem
        Base.metadata.create_all(engine)
        
        # Carregar dados iniciais na ordem correta
        try:
            # 1. Carregar unidades iniciais
            if not session.query(Unidade).first():
                unidades = [
                    {"nome": "Unidade Oeste"},
                    {"nome": "República do Líbano"},
                    {"nome": "Unidade Externa"}
                ]
                for unid in unidades:
                    unidade = Unidade(**unid)
                    session.add(unidade)
                    session.flush()
                    
                    # Criar salas padrão para cada unidade
                    salas = [
                        Sala(nome="Sala 01", unidade_id=unidade.id),
                        Sala(nome="Sala 02", unidade_id=unidade.id)
                    ]
                    for sala in salas:
                        session.add(sala)
        
                session.commit()
                st.success("✅ Unidades e salas criadas com sucesso!")

            # 2. Carregar áreas de atuação
            if not session.query(AreaAtuacao).first():
                areas = [
                    {"nome": "Psicologia", "descricao": "Atendimento psicológico"},
                    {"nome": "Fonoaudiologia", "descricao": "Terapia fonoaudiológica"},
                    {"nome": "Terapia Ocupacional", "descricao": "Terapia ocupacional"},
                    {"nome": "Psicomotricidade", "descricao": "Terapia psicomotora"},
                    {"nome": "Musicoterapia", "descricao": "Terapia através da música"},
                    {"nome": "Fisioterapia", "descricao": "Terapia física"},
                    {"nome": "Psicopedagogia", "descricao": "Acompanhamento psicopedagógico"}
                ]
                for area in areas:
                    session.add(AreaAtuacao(**area))
                session.commit()
                st.success("✅ Áreas de atuação criadas com sucesso!")

            # 3. Carregar tipos de pagamento
            if not session.query(Pagamento).first():
                pagamentos = [
                    {"nome": "Particular", "descricao": "Pagamento particular"},
                    {"nome": "Convênio", "descricao": "Pagamento via convênio"},
                    {"nome": "Plano de Saúde", "descricao": "Pagamento via plano de saúde"}
                ]
                for pag in pagamentos:
                    session.add(Pagamento(**pag))
                session.commit()
                st.success("✅ Tipos de pagamento criados com sucesso!")

            # 4. Carregar perfis de paciente
            if not session.query(PerfilPaciente).first():
                perfis = [
                    {"nome": "Criança", "descricao": "Pacientes até 12 anos"},
                    {"nome": "Adolescente", "descricao": "Pacientes de 13 a 18 anos"},
                    {"nome": "Adulto", "descricao": "Pacientes acima de 18 anos"}
                ]
                for perfil in perfis:
                    session.add(PerfilPaciente(**perfil))
                session.commit()
                st.success("✅ Perfis de paciente criados com sucesso!")

            # 5. Carregar terminologias
            if not session.query(Terminologia).first():
                terminologias = [
                    {"cod_faturamento": "2250005189", "descricao": "Fonoaudiologia", "tipo": "FONO"},
                    {"cod_faturamento": "2250005103", "descricao": "Psicologia", "tipo": "PSI"},
                    {"cod_faturamento": "2250005170", "descricao": "Terapia Ocupacional", "tipo": "TO"},
                    {"cod_faturamento": "50000012", "descricao": "Psicomotricidade", "tipo": "MOTRIC"},
                    {"cod_faturamento": "50001213", "descricao": "Musicoterapia", "tipo": "MUSICO"},
                    {"cod_faturamento": "2250005111", "descricao": "Fisioterapia", "tipo": "FISIO"},
                    {"cod_faturamento": "2250005278", "descricao": "Psicopedagogia", "tipo": "PED"}
                ]
                for term in terminologias:
                    session.add(Terminologia(**term))
                session.commit()
                st.success("✅ Terminologias criadas com sucesso!")
        except Exception as e:
            session.rollback()
            logging.error(f"Erro ao carregar dados iniciais: {str(e)}")
            st.error(f"❌ Erro ao carregar dados iniciais: {str(e)}")
            return False

    except Exception as e:
        session.rollback()
        logging.error(f"Erro ao verificar banco de dados: {str(e)}")
        st.error(f"❌ Erro ao verificar banco de dados: {str(e)}")
        return False
    finally:
        if session:
            session.close()

# 2. FUNÇÕES AUXILIARES
# =====================================================

# --- Novas Funções Geradoras de Grade ---

def gerar_grade_profissional(session, profissional_id):
    """Gera grade de disponibilidade para um profissional"""
    try:
        profissional = session.query(Profissional).get(profissional_id)
        if not profissional:
            raise Exception(f"Profissional {profissional_id} não encontrado")
            
        # Dias da semana para geração da grade
        dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
        
        # Horários por período
        horarios_matutino = [f"{h:02d}:00" for h in range(7, 13)]  # 07:00 às 12:00 (6 slots)
        horarios_vespertino = [f"{h:02d}:00" for h in range(13, 19)]  # 13:00 às 18:00 (6 slots)
        horarios_sabado = [f"{h:02d}:00" for h in range(8, 12)]  # 08:00 às 11:00 (4 slots)
        
        # Gerar disponibilidade para cada dia
        for dia in dias_semana:
            if dia == 'Sábado':
                # Gerar horários para sábado (4 slots)
                for horario in horarios_sabado:
                    disponibilidade = Disponibilidade(
                        profissional_id=profissional_id,
                        dia_semana=dia,
                        periodo='Matutino',
                        hora_inicio=horario,
                        status='Disponível'
                    )
                    session.add(disponibilidade)
            else:
                # Gerar período matutino (6 slots por dia)
                for horario in horarios_matutino:
                    disponibilidade = Disponibilidade(
                        profissional_id=profissional_id,
                        dia_semana=dia,
                        periodo='Matutino',
                        hora_inicio=horario,
                        status='Disponível'
                    )
                    session.add(disponibilidade)
                
                # Gerar período vespertino (6 slots por dia)
                for horario in horarios_vespertino:
                    disponibilidade = Disponibilidade(
                        profissional_id=profissional_id,
                        dia_semana=dia,
                        periodo='Vespertino',
                        hora_inicio=horario,
                        status='Disponível'
                    )
                    session.add(disponibilidade)
        
        session.commit()
        logging.info(f"Grade gerada para profissional {profissional_id}: 60 slots (seg-sex) + 4 slots (sáb) = 64 slots")
        return True
        
    except Exception as e:
        session.rollback()
        raise Exception(f"Erro ao gerar grade para profissional {profissional_id}: {str(e)}")

def gerar_grade_sala(session, sala_id):
    """
    Gera a grade de disponibilidade para uma sala específica.
    
    Args:
        session: Sessão SQLAlchemy
        sala_id: ID da sala
        
    Returns:
        bool: True se a operação foi bem sucedida, False caso contrário
    """
    try:
        # Verifica se a sala existe
        sala = session.query(Sala).filter_by(id=sala_id).first()
        if not sala:
            logging.error(f"Sala com ID {sala_id} não encontrada")
            return False
            
        # Remove registros existentes de disponibilidade para esta sala
        session.query(DisponibilidadeSala).filter_by(sala_id=sala_id).delete()
        
        # Gera disponibilidade para dias úteis
        for dia in DIAS_SEMANA_UTIL:
            for horario in HORARIOS_DISPONIVEIS:
                disponibilidade = DisponibilidadeSala(
                    sala_id=sala_id,
                    dia_semana=dia,
                    horario=horario.strftime('%H:%M'),
                    status="Disponível"
                )
                session.add(disponibilidade)
                
        # Gera disponibilidade para sábado (apenas manhã)
        for dia in DIAS_SEMANA_SABADO:
            for horario in HORARIOS_DISPONIVEIS:
                if horario < time(12, 0):  # Apenas horários antes do meio-dia
                    disponibilidade = DisponibilidadeSala(
                        sala_id=sala_id,
                        dia_semana=dia,
                        horario=horario.strftime('%H:%M'),
                        status="Disponível"
                    )
                    session.add(disponibilidade)
        
        session.commit()
        logging.info(f"Grade de disponibilidade gerada com sucesso para sala {sala_id}")
        return True
        
    except Exception as e:
        session.rollback()
        logging.error(f"Erro ao gerar grade de disponibilidade para sala {sala_id}: {str(e)}")
        logging.error(traceback.format_exc())
        return False

# --- Fim Funções Geradoras de Grade ---

def mapear_dia_semana(data):
    """Mapeia uma data para o dia da semana em português."""
    dias = {
        0: "Segunda-feira",
        1: "Terça-feira",
        2: "Quarta-feira",
        3: "Quinta-feira",
        4: "Sexta-feira",
        5: "Sábado",
        6: "Domingo"
    }
    return dias.get(data.weekday())

def obter_dia_semana(data):
    """Obtém o dia da semana de uma data"""
    try:
        if isinstance(data, str):
            data = datetime.strptime(data, '%d/%m/%Y').date()
        elif isinstance(data, datetime):
            data = data.date()
            
        dias = {
            0: "Segunda-feira",
            1: "Terça-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sábado",
            6: "Domingo"
        }
        return dias.get(data.weekday())
    except Exception as e:
        logging.error(f"Erro ao obter dia da semana: {str(e)}")
        return None

# =====================================================
# 4. INTERFACE PRINCIPAL
# =====================================================

def salvar_arquivo_temporario(uploaded_file):
    """Salva o arquivo temporariamente e retorna o caminho"""
    try:
        # Criar diretório temporário se não existir
        temp_dir = "temp_uploads"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # Gerar nome único para o arquivo
        nome_arquivo = f"{temp_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
        
        # Salvar arquivo
        with open(nome_arquivo, "wb") as f:
            f.write(uploaded_file.getvalue())
            
        return nome_arquivo
    except Exception as e:
        st.error(f"❌ Erro ao salvar arquivo temporário: {str(e)}")
        return None

def processar_arquivo_excel(arquivo):
    """
    Processa o arquivo Excel enviado
    """
    try:
        # Salvar arquivo temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(arquivo.getvalue())
            tmp_path = tmp_file.name

        try:
            # Tentar ler com diferentes encodings
            df = pd.read_excel(tmp_path)
            
            # Normalizar nomes das colunas
            df.columns = [normalizar_texto(col) for col in df.columns]
            
            # Remover linhas vazias
            df = df.dropna(how='all')
            
            # Remover o arquivo temporário
            os.unlink(tmp_path)
            
            return df

        except Exception as e:
            st.error(f"❌ Erro ao ler arquivo Excel: {str(e)}")
            logging.error(f"Erro ao ler arquivo Excel: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None

    except Exception as e:
        st.error(f"❌ Erro ao processar arquivo: {str(e)}")
        logging.error(f"Erro ao processar arquivo: {str(e)}")
        return None

def consultar_disponibilidade():
    """Interface para consulta de disponibilidade (otimizada com paginação)"""
    try:
        st.title("🔍 Consulta de Disponibilidade")
        session = get_session()
        if not session:
            st.error("❌ Não foi possível conectar ao banco de dados")
            return
        start_time = pytime.time()
        # Carregar dados corretos para cada filtro
        unidades = get_unidades_ativas(session)  # Lista de unidades
        profissionais = get_profissionais_ativos(session)  # Lista de profissionais
        areas = get_areas_ativas(session)  # Lista de áreas de atuação
        pagamentos = get_pagamentos_ativos(session)  # Lista de tipos de pagamento
        perfis = get_perfis_ativos(session)  # Lista de perfis de paciente
        logging.info(f"Tempo para carregar dados iniciais: {pytime.time() - start_time:.2f} segundos")
        # Exibir estatísticas
        st.subheader("📊 Estatísticas")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            total_profissionais = len(profissionais)
            st.metric("Total de Profissionais", total_profissionais)
        with col_m2:
            total_disponiveis = session.query(Disponibilidade).filter_by(status="Disponível").count()
            st.metric("Horários Disponíveis", total_disponiveis)
        with col_m3:
            total_bloqueios = session.query(Disponibilidade).filter_by(status="Bloqueio").count()
            st.metric("Horários Bloqueados", total_bloqueios)
        with col_m4:
            total_atendimentos = session.query(Disponibilidade).filter_by(status="Em atendimento").count()
            st.metric("Horários em Atendimento", total_atendimentos)
        status_opcoes = ["Disponível", "Todos", "Em atendimento", "Bloqueio"]
        # Filtros reorganizados conforme solicitado
        col_f1, col_f2, col_f3, col_f4 = st.columns([1.2,1,1,1])
        with col_f1:
            status = st.selectbox(
                "📊 Status",
                status_opcoes,
                index=0,
                help="Selecione o status"
            )
            unidade_selecionada = st.selectbox(
                "🏥 Unidade",
                ["Todos"] + [u.nome for u in unidades],
                help="Selecione a unidade para filtrar"
            )
        with col_f2:
            area_selecionada = st.selectbox(
                "🎯 Área de Atuação",
                ["Todos"] + [a.nome for a in areas],
                help="Selecione a área de atuação"
            )
            dia_semana = st.selectbox(
                "📅 Dia da Semana",
                ["Todos", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"],
                help="Selecione o dia da semana"
            )
        with col_f3:
            periodo = st.selectbox(
                "⏰ Período",
                ["Todos", "Matutino", "Vespertino"],
                help="Selecione o período"
            )
            perfil = st.selectbox(
                "👥 Perfil",
                ["Todos"] + [p.nome for p in perfis],
                help="Selecione o perfil do paciente"
            )
        with col_f4:
            profissional_selecionado = st.selectbox(
                "👨‍⚕️ Profissional",
                ["Todos"] + [p.nome for p in profissionais],
                help="Selecione o profissional"
            )
            pagamento = st.selectbox(
                "💰 Pagamento",
                ["Todos"] + [p.nome for p in pagamentos],
                help="Selecione o tipo de pagamento"
            )
        # Linha de paginação
        st.markdown("---")
        col_pag1, _, col_pag2 = st.columns([1,6,1])
        with col_pag1:
            itens_por_pagina = st.selectbox("Resultados por página", [25, 50, 100], index=1, key="itens_pagina")
        with col_pag2:
            pagina = st.number_input("Página", min_value=1, value=1, step=1, key="pagina_num")
        # Consulta automática ao alterar qualquer filtro
        try:
            query = session.query(
                Disponibilidade.id,
                Disponibilidade.profissional_id,
                Disponibilidade.unidade_id,
                Disponibilidade.dia_semana,
                Disponibilidade.periodo,
                Disponibilidade.hora_inicio,
                Disponibilidade.hora_fim,
                Disponibilidade.status
            )
            # Filtros
            if unidade_selecionada != "Todos":
                unidade = session.query(Unidade).filter_by(nome=unidade_selecionada).first()
                if unidade:
                    query = query.filter(Disponibilidade.unidade_id == unidade.id)
            if area_selecionada != "Todos":
                area = session.query(AreaAtuacao).filter_by(nome=area_selecionada).first()
                if area:
                    profs_area = [p.id for p in area.profissionais]
                    query = query.filter(Disponibilidade.profissional_id.in_(profs_area))
            if dia_semana != "Todos":
                query = query.filter(Disponibilidade.dia_semana == dia_semana)
            if profissional_selecionado != "Todos":
                prof = session.query(Profissional).filter_by(nome=profissional_selecionado).first()
                if prof:
                    query = query.filter(Disponibilidade.profissional_id == prof.id)
            if periodo != "Todos":
                query = query.filter(Disponibilidade.periodo == periodo)
            if status != "Todos":
                query = query.filter(Disponibilidade.status == status)
            # Pagamento e perfil: filtrar IDs de profissionais
            if pagamento != "Todos":
                profs_pagamento = [p.id for p in profissionais if pagamento in [pag.nome for pag in p.pagamentos]]
                query = query.filter(Disponibilidade.profissional_id.in_(profs_pagamento))
            if perfil != "Todos":
                profs_perfil = [p.id for p in profissionais if perfil in [pf.nome for pf in p.perfis_paciente]]
                query = query.filter(Disponibilidade.profissional_id.in_(profs_perfil))
            # Paginação
            total_resultados = query.count()
            disponibilidades = query.offset((pagina-1)*itens_por_pagina).limit(itens_por_pagina).all()
            # Buscar dados extras em lote
            prof_ids = list(set([d.profissional_id for d in disponibilidades]))
            unid_ids = list(set([d.unidade_id for d in disponibilidades if d.unidade_id]))
            profs_dict = {p.id: p for p in session.query(Profissional).filter(Profissional.id.in_(prof_ids)).all()}
            unids_dict = {u.id: u for u in session.query(Unidade).filter(Unidade.id.in_(unid_ids)).all()}
            dados = []
            for disp in disponibilidades:
                profissional = profs_dict.get(disp.profissional_id)
                unidade = unids_dict.get(disp.unidade_id) if disp.unidade_id else None
                areas_prof = ", ".join([a.nome for a in profissional.areas_atuacao]) if profissional and profissional.areas_atuacao else ""
                pagamentos_prof = ", ".join([p.nome for p in profissional.pagamentos]) if profissional and profissional.pagamentos else ""
                perfis_prof = ", ".join([p.nome for p in profissional.perfis_paciente]) if profissional and profissional.perfis_paciente else ""
                status_exibicao = "Em atendimento" if disp.status == "Ocupado" else disp.status
                dados.append({
                    'Profissional': profissional.nome if profissional else '',
                    'Unidade': unidade.nome if unidade else '',
                    'Dia': disp.dia_semana,
                    'Período': disp.periodo,
                    'Hora Início': disp.hora_inicio,
                    'Hora Fim': disp.hora_fim,
                    'Status': status_exibicao,
                    'Áreas': areas_prof,
                    'Pagamentos': pagamentos_prof,
                    'Perfis': perfis_prof
                })
            df = pd.DataFrame(dados)
            st.write(f"Exibindo {len(df)} de {total_resultados} resultados.")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"❌ Erro ao buscar disponibilidades: {str(e)}")
    except Exception as e:
        st.error(f"❌ Erro ao consultar disponibilidade: {str(e)}")
    finally:
        if session:
            session.close()

def gerenciar_salas():
    """Gerenciamento de salas"""
    st.subheader("🚪 Gestão de Salas")
    
    session = get_session()
    try:
        # Debug: Mostrar todas as unidades no banco
        todas_unidades = session.query(Unidade).all()
        st.write("🔍 Unidades cadastradas no banco:")
        for u in todas_unidades:
            st.write(f"- ID: {u.id}, Nome: {u.nome}, Ativo: {u.ativo}")
        
        # Template para upload
        colunas_template = ["id_unidade", "id_sala", "nome", "ativo"]
        gerar_template_excel("template_salas.xlsx", colunas_template)
        
        # Upload de arquivo
        uploaded_file = st.file_uploader(
            "📤 Upload de Salas",
            type=["xlsx"],
            key="upload_salas"
        )
        
        if uploaded_file:
            try:
                # Ler arquivo
                df = pd.read_excel(uploaded_file)
                
                # Debug: Mostrar dados do arquivo
                st.write("📄 Dados do arquivo de upload:")
                st.write(df)
                
                # Verificar colunas
                colunas_esperadas = ["id_unidade", "id_sala", "nome", "ativo"]
                if not all(col in df.columns for col in colunas_esperadas):
                    st.error("❌ O arquivo deve conter as colunas: id_unidade, id_sala, nome e ativo")
                    st.write("Colunas encontradas:", df.columns.tolist())
                    return
                
                # Debug: Mostrar IDs de unidades do arquivo
                unidades_ids = df["id_unidade"].unique()
                st.write("🔢 IDs de unidades no arquivo:", unidades_ids)
                
                # Converter IDs para inteiros
                unidades_ids = [int(id) for id in unidades_ids]
                
                # Buscar unidades existentes
                unidades_existentes = session.query(Unidade).filter(Unidade.id.in_(unidades_ids)).all()
                unidades_existentes_ids = {u.id for u in unidades_existentes}
                
                # Debug: Mostrar IDs encontrados
                st.write("🔍 IDs de unidades encontrados no banco:", unidades_existentes_ids)
                
                unidades_faltantes = set(unidades_ids) - unidades_existentes_ids
                if unidades_faltantes:
                    st.error(f"❌ As seguintes unidades não foram encontradas: {unidades_faltantes}")
                    st.error("Por favor, cadastre as unidades primeiro antes de cadastrar as salas.")
                    return
                
                # Limpa tabela existente
                session.query(Sala).delete()
                session.commit()
                
                # Processar dados
                for _, row in df.iterrows():
                    # Converte o valor de ativo para boolean
                    ativo = str(row["ativo"]).upper() in ['ATIVO', 'A', 'TRUE', '1', 'T', 'Y', 'YES']
                    
                    # Garantir que id_unidade seja inteiro
                    id_unidade = int(row["id_unidade"])
                    
                    sala = Sala(
                        id=int(row["id_sala"]),
                        nome=row["nome"],
                        unidade_id=id_unidade,
                        ativo=ativo
                    )
                    session.add(sala)
                
                session.commit()
                st.success("✅ Salas atualizadas com sucesso!")
                
            except Exception as e:
                session.rollback()
                st.error(f"❌ Erro ao processar arquivo: {str(e)}")
                logging.error(f"Erro ao processar arquivo de salas: {str(e)}\n{traceback.format_exc()}")
        
        # Lista de salas existentes
        st.subheader("📋 Salas Cadastradas")
        salas = session.query(Sala).all()
        
        if salas:
            for sala in salas:
                with st.expander(f"🚪 {sala.nome}"):
                    # Formulário de edição
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.text_input("ID", value=sala.id, disabled=True, key=f"id_{sala.id}")
                        novo_nome = st.text_input("Nome", value=sala.nome, key=f"nome_{sala.id}")
                    
                    with col2:
                        unidade = session.query(Unidade).get(sala.unidade_id)
                        st.text_input("Unidade", value=f"{unidade.nome} (ID: {unidade.id})" if unidade else "Unidade não encontrada", disabled=True, key=f"unidade_{sala.id}")
                        status = st.selectbox(
                            "Status",
                            ["Ativo", "Inativo"],
                            index=0 if sala.ativo else 1,
                            key=f"status_{sala.id}"
                        )
                    
                    if st.button("💾 Salvar", key=f"btn_salvar_{sala.id}"):
                        try:
                            sala.nome = novo_nome
                            sala.ativo = status == "Ativo"
                            session.commit()
                            st.success("✅ Sala atualizada com sucesso!")
                        except Exception as e:
                            session.rollback()
                            st.error(f"❌ Erro ao atualizar sala: {str(e)}")
        else:
            st.info("ℹ️ Nenhuma sala cadastrada")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerenciar salas: {str(e)}")
        logging.error(f"Erro ao gerenciar salas: {str(e)}\n{traceback.format_exc()}")
    finally:
        session.close()

def verificar_tabela_profissionais(session):
    """Verifica se a tabela de profissionais existe"""
    try:
        # Verifica se a tabela existe
        if not inspect(engine).has_table("profissionais"):
            Base.metadata.create_all(engine)
        return True
    except Exception as e:
        logging.error(f"Erro ao verificar tabela de profissionais: {str(e)}")
        return False

def gerenciar_profissionais():
    """Interface para gerenciamento de profissionais"""
    try:
        st.title("👥 Gestão de Profissionais")
        
        session = get_session()
        if not session:
            st.error("❌ Não foi possível conectar ao banco de dados")
            return
            
        # Apenas verifica se a tabela existe, não recria
        if not verificar_tabela_profissionais(session):
            st.error("❌ Erro ao verificar tabela de profissionais")
            return
        
        # Botão para apagar todos os profissionais
        if st.button("🗑️ Apagar Todos os Profissionais", type="primary"):
            try:
                session.query(Profissional).delete()
                session.commit()
                st.success("✅ Todos os profissionais foram apagados com sucesso!")
                st.rerun()
            except Exception as e:
                session.rollback()
                st.error(f"❌ Erro ao apagar profissionais: {str(e)}")
                return
        
        # Template para download
        colunas = [
            "Id Profissional", "Nome Profissional", "NomeConselho", "Registro",
            "UF", "CBO", "Status", "Id Area", "Id Pagamento", "Perfil Paciente"
        ]
        
        # Botão para baixar template
        if st.button("📥 Baixar Template"):
            gerar_template_excel("template_profissionais.xlsx", colunas)
            st.success("✅ Template gerado com sucesso!")
        
        # Upload de arquivo
        st.subheader("📤 Upload de Arquivo")
        uploaded_file = st.file_uploader(
            "Selecione o arquivo Excel com os profissionais",
            type=["xlsx", "xls"],
            help="O arquivo deve conter as colunas: Id Profissional, Nome Profissional, NomeConselho, Registro, UF, CBO, Status, Id Area, Id Pagamento, Perfil Paciente"
        )
        
        if uploaded_file:
            try:
                # Desativa o autoflush durante o processamento
                session.autoflush = False
                
                # Processa o arquivo
                df = pd.read_excel(uploaded_file)
                
                # Verifica se todas as colunas necessárias estão presentes
                colunas_faltantes = [col for col in colunas if col not in df.columns]
                if colunas_faltantes:
                    st.error(f"❌ O arquivo deve conter todas as colunas necessárias. Faltando: {', '.join(colunas_faltantes)}")
                    return
                
                # Processa o upload
                resultado = processar_upload_profissionais(session, df)
                
                st.success("✅ Profissionais processados com sucesso!")
                
                # Exibe estatísticas
                st.write(f"📊 Registros processados: {resultado['processados']}")
                if resultado['ignorados'] > 0:
                    st.warning(f"⚠️ Registros ignorados: {resultado['ignorados']}")
                
                if resultado['erros']:
                    with st.expander("Ver detalhes dos erros"):
                        for erro in resultado['erros']:
                            st.write(f"- {erro}")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {str(e)}")
                logging.error(f"Erro ao processar arquivo: {str(e)}")
            finally:
                session.autoflush = True
        
        # Lista de profissionais
        st.subheader("📋 Lista de Profissionais")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            filtro_nome = st.text_input("🔍 Filtrar por nome")
        with col2:
            filtro_status = st.selectbox(
                "📊 Status",
                ["Todos", "Ativos", "Inativos"],
                index=0
            )
        
        # Consulta profissionais
        query = session.query(Profissional)
        if filtro_nome:
            query = query.filter(Profissional.nome.ilike(f"%{filtro_nome}%"))
        if filtro_status == "Ativos":
            query = query.filter(Profissional.ativo == True)
        elif filtro_status == "Inativos":
            query = query.filter(Profissional.ativo == False)
        
        profissionais = query.all()
        
        if not profissionais:
            st.info("ℹ️ Nenhum profissional encontrado")
            return
        
        # Carrega todas as áreas, pagamentos e perfis ativos
        areas = session.query(AreaAtuacao).filter_by(ativo=True).all()
        pagamentos = session.query(Pagamento).filter_by(ativo=True).all()
        perfis = session.query(PerfilPaciente).filter_by(ativo=True).all()
        
        # Exibe a lista de profissionais
        for prof in profissionais:
            with st.expander(f"{'✅' if prof.ativo else '❌'} {prof.nome}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**ID:** {prof.id}")
                    st.write(f"**Registro:** {prof.registro or 'Não informado'}")
                    st.write(f"**CBO:** {prof.cbo or 'Não informado'}")
                    st.write(f"**UF:** {prof.uf or 'Não informado'}")
                    st.write(f"**Conselho:** {prof.nome_conselho or 'Não informado'}")
                    st.write(f"**Sala:** {prof.sala.nome if prof.sala else 'Não atribuída'}")
                
                with col2:
                    # Seleção múltipla de áreas
                    areas_selecionadas = st.multiselect(
                        "Áreas de Atuação",
                        options=[(a.id, a.nome) for a in areas],
                        default=[(a.id, a.nome) for a in prof.areas_atuacao],
                        format_func=lambda x: x[1],
                        key=f"areas_{prof.id}"
                    )
                    
                    # Seleção múltipla de pagamentos
                    pagamentos_selecionados = st.multiselect(
                        "Pagamentos",
                        options=[(p.id, p.nome) for p in pagamentos],
                        default=[(p.id, p.nome) for p in prof.pagamentos],
                        format_func=lambda x: x[1],
                        key=f"pagamentos_{prof.id}"
                    )
                    
                    # Seleção múltipla de perfis
                    perfis_selecionados = st.multiselect(
                        "Perfis de Paciente",
                        options=[(p.id, p.nome) for p in perfis],
                        default=[(p.id, p.nome) for p in prof.perfis_paciente],
                        format_func=lambda x: x[1],
                        key=f"perfis_{prof.id}"
                    )
                    
                    # Botão para salvar alterações nas atribuições
                    if st.button("💾 Salvar Atribuições", key=f"save_attr_{prof.id}"):
                        try:
                            # Atualiza áreas
                            prof.areas_atuacao = [a for a in areas if (a.id, a.nome) in areas_selecionadas]
                            
                            # Atualiza pagamentos
                            prof.pagamentos = [p for p in pagamentos if (p.id, p.nome) in pagamentos_selecionados]
                            
                            # Atualiza perfis
                            prof.perfis_paciente = [p for p in perfis if (p.id, p.nome) in perfis_selecionados]
                            
                            session.commit()
                            st.success("✅ Atribuições atualizadas com sucesso!")
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"❌ Erro ao salvar atribuições: {str(e)}")
                
                # Botões de ação
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                
                with col_btn1:
                    if st.button("📅 Editar Grade", key=f"grade_{prof.id}"):
                        editar_grade_profissional(prof.id)
                
                with col_btn2:
                    if st.button("✏️ Editar", key=f"edit_{prof.id}"):
                        st.session_state.editando_profissional = prof.id
                
                with col_btn3:
                    if st.button("❌ Desativar" if prof.ativo else "✅ Ativar", key=f"toggle_{prof.id}"):
                        prof.ativo = not prof.ativo
                        session.commit()
                        st.rerun()
                    
    except Exception as e:
        st.error(f"❌ Erro ao gerenciar profissionais: {str(e)}")
        logging.error(f"Erro ao gerenciar profissionais: {str(e)}")
    finally:
        if session:
            session.close()

def gerenciar_areas_atuacao():
    """Interface para gerenciamento de áreas de atuação"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("🏥 Gestão de Áreas de Atuação")
        
        # Template para upload
        colunas_template = ["id", "nome", "ativo"]
        with st.expander("📥 Template para Upload", expanded=False):
            gerar_template_excel("template_areas_atuacao.xlsx", colunas_template)
        
        # Upload de arquivo
        uploaded_file = st.file_uploader("Escolha um arquivo Excel", type=["xlsx"], key="upload_areas")
        if uploaded_file:
            # Limpa a tabela antes do upload
            session.query(AreaAtuacao).delete()
            session.commit()
            
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                # Converte o valor de ativo para boolean
                ativo = True if str(row.get("ativo", "True")).lower() in ['true', '1', 't', 'y', 'yes', 'ativo', 'sim'] else False
                
                area = AreaAtuacao(
                    id=row["id"],
                    nome=row["nome"],
                    ativo=ativo
                )
                session.add(area)
            session.commit()
            st.success("✅ Áreas de atuação importadas com sucesso!")
            st.rerun()
        
        # Lista de áreas existentes
        areas = session.query(AreaAtuacao).order_by(AreaAtuacao.id).all()
        if areas:
            for area in areas:
                with st.expander(f"📝 {area.nome} (ID: {area.id})", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("ID", value=area.id, disabled=True, key=f"id_{area.id}")
                        novo_nome = st.text_input("Nome", value=area.nome, key=f"nome_{area.id}")
                        novo_status = st.checkbox("Ativo", value=area.ativo, key=f"ativo_{area.id}")
                    
                    if st.button("Salvar Alterações", key=f"save_{area.id}"):
                        area.nome = novo_nome
                        area.ativo = novo_status
                        session.commit()
                        st.success("✅ Alterações salvas com sucesso!")
                        st.rerun()
        else:
            st.info("ℹ️ Nenhuma área de atuação cadastrada")

    except Exception as e:
        st.error(f"❌ Erro ao gerenciar áreas de atuação: {str(e)}")
    finally:
        if session:
            session.close()

def gerenciar_pagamentos():
    """Interface para gerenciamento de tipos de pagamento"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("💰 Gestão de Tipos de Pagamento")
        
        # Template para upload
        colunas_template = ["id", "nome", "ativo"]
        with st.expander("📥 Template para Upload", expanded=False):
            gerar_template_excel("template_pagamentos.xlsx", colunas_template)
        
        # Upload de arquivo
        uploaded_file = st.file_uploader("Escolha um arquivo Excel", type=["xlsx"], key="upload_pagamentos")
        if uploaded_file:
            # Limpa a tabela antes do upload
            session.query(Pagamento).delete()
            session.commit()
            
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                # Converte o valor de ativo para boolean
                ativo = True if str(row.get("ativo", "True")).lower() in ['true', '1', 't', 'y', 'yes', 'ativo', 'sim'] else False
                
                pagamento = Pagamento(
                    id=row["id"],
                    nome=row["nome"],
                    ativo=ativo
                )
                session.add(pagamento)
            session.commit()
            st.success("✅ Tipos de pagamento importados com sucesso!")
            st.rerun()
        
        # Lista de pagamentos existentes
        pagamentos = session.query(Pagamento).order_by(Pagamento.id).all()
        if pagamentos:
            for pag in pagamentos:
                with st.expander(f"📝 {pag.nome} (ID: {pag.id})", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("ID", value=pag.id, disabled=True, key=f"pag_id_{pag.id}")
                        novo_nome = st.text_input("Nome", value=pag.nome, key=f"pag_nome_{pag.id}")
                        novo_status = st.checkbox("Ativo", value=pag.ativo, key=f"pag_ativo_{pag.id}")
                    
                    if st.button("Salvar Alterações", key=f"pag_save_{pag.id}"):
                        pag.nome = novo_nome
                        pag.ativo = novo_status
                        session.commit()
                        st.success("✅ Alterações salvas com sucesso!")
                        st.rerun()
        else:
            st.info("ℹ️ Nenhum tipo de pagamento cadastrado")

    except Exception as e:
        st.error(f"❌ Erro ao gerenciar tipos de pagamento: {str(e)}")
    finally:
        if session:
            session.close()

def gerar_template_excel(nome_arquivo: str, colunas: list):
    """Gera um template Excel vazio com as colunas especificadas"""
    try:
        # Criar DataFrame vazio com as colunas
        df = pd.DataFrame(columns=colunas)
        
        # Salvar como Excel no diretório atual
        df.to_excel(nome_arquivo, index=False)
        
        # Retorna sucesso
        return True
        
    except Exception as e:
        logging.error(f"Erro ao gerar template: {str(e)}\n{traceback.format_exc()}")
        return False

def gerenciar_perfis_paciente():
    """Gerenciamento de perfis de paciente"""
    st.subheader("👥 Gestão de Perfis de Paciente")
    
    session = get_session()
    try:
        # Template para upload
        colunas_template = ["Id", "Nome", "Descrição", "Status"]
        gerar_template_excel("template_perfis_paciente.xlsx", colunas_template)
        
        # Upload de arquivo
        uploaded_file = st.file_uploader(
            "📤 Upload de Perfis de Paciente",
            type=["xlsx"],
            key="upload_perfis"
        )
        
        if uploaded_file:
            try:
                # Ler arquivo
                df = pd.read_excel(uploaded_file)
                
                # Verificar colunas
                colunas_esperadas = ["Id", "Nome", "Descrição", "Status"]
                if not all(col in df.columns for col in colunas_esperadas):
                    st.error("❌ O arquivo deve conter as colunas: Id, Nome, Descrição e Status")
                    return
                
                # Processar dados
                for _, row in df.iterrows():
                    perfil_id = row["Id"]
                    perfil = session.query(PerfilPaciente).get(perfil_id)
                    
                    if perfil:
                        # Atualizar perfil existente
                        perfil.nome = row["Nome"]
                        perfil.descricao = row["Descrição"]
                        perfil.ativo = row["Status"] == "Ativo"
                    else:
                        # Criar novo perfil
                        perfil = PerfilPaciente(
                            id=perfil_id,
                            nome=row["Nome"],
                            descricao=row["Descrição"],
                            ativo=row["Status"] == "Ativo"
                        )
                        session.add(perfil)
                
                session.commit()
                st.success("✅ Perfis de paciente atualizados com sucesso!")
                
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {str(e)}")
                logging.error(f"Erro ao processar arquivo de perfis: {str(e)}\n{traceback.format_exc()}")
        
        # Lista de perfis existentes
        st.subheader("📋 Perfis Cadastrados")
        perfis = session.query(PerfilPaciente).all()
        
        if perfis:
            for perfil in perfis:
                with st.expander(f"👤 {perfil.nome}"):
                    # Formulário de edição
                    novo_nome = st.text_input("Nome", value=perfil.nome, key=f"nome_{perfil.id}")
                    nova_descricao = st.text_area("Descrição", value=perfil.descricao, key=f"desc_{perfil.id}")
                    novo_status = st.selectbox(
                        "Status",
                        ["Ativo", "Inativo"],
                        index=0 if perfil.ativo else 1,
                        key=f"status_{perfil.id}"
                    )
                    
                    if st.button("💾 Salvar", key=f"btn_salvar_{perfil.id}"):
                        perfil.nome = novo_nome
                        perfil.descricao = nova_descricao
                        perfil.ativo = novo_status == "Ativo"
                        session.commit()
                        st.success("✅ Perfil atualizado com sucesso!")
        else:
            st.info("ℹ️ Nenhum perfil cadastrado")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerenciar perfis: {str(e)}")
        logging.error(f"Erro ao gerenciar perfis: {str(e)}\n{traceback.format_exc()}")
    finally:
        session.close()

def gerenciar_terminologias():
    """Interface para gerenciamento de códigos de faturamento"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("📋 Gestão de Códigos de Faturamento")
        
        # Template para upload
        colunas_template = ["id_area", "id_pagamento", "id_codigo", "cod_faturamento", "descricao", "ativo"]
        with st.expander("📥 Template para Upload", expanded=False):
            gerar_template_excel("template_terminologias.xlsx", colunas_template)
        
        # Upload de arquivo
        uploaded_file = st.file_uploader("Escolha um arquivo Excel", type=["xlsx"], key="upload_terminologias")
        if uploaded_file:
            # Limpa a tabela antes do upload
            session.query(Terminologia).delete()
            session.commit()
            
            df = pd.read_excel(uploaded_file)
            for _, row in df.iterrows():
                # Converte o valor de ativo para boolean
                ativo = True if str(row.get("ativo", "True")).lower() in ['true', '1', 't', 'y', 'yes', 'ativo', 'sim'] else False
                
                # Garante que o código de faturamento seja tratado como texto
                cod_faturamento = str(row["cod_faturamento"]).zfill(8)  # Preenche com zeros à esquerda até ter 8 dígitos
                
                terminologia = Terminologia(
                    id=row["id_codigo"],
                    cod_faturamento=cod_faturamento,
                    descricao=row["descricao"],
                    tipo="Padrão",
                    area_atuacao_id=row["id_area"],
                    pagamento_id=row["id_pagamento"],
                    ativo=ativo
                )
                session.add(terminologia)
            session.commit()
            st.success("✅ Códigos de faturamento importados com sucesso!")
            st.rerun()
        
        # Lista de terminologias existentes
        terminologias = session.query(Terminologia).order_by(Terminologia.id).all()
        if terminologias:
            for term in terminologias:
                # Busca os nomes da área e do pagamento
                area = session.query(AreaAtuacao).get(term.area_atuacao_id)
                pagamento = session.query(Pagamento).get(term.pagamento_id)
                
                with st.expander(f"📝 {term.descricao} (ID: {term.id})", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("ID", value=term.id, disabled=True, key=f"term_id_{term.id}")
                        st.text_input("Código de Faturamento", value=term.cod_faturamento, key=f"term_cod_{term.id}")
                        st.text_input("Descrição", value=term.descricao, key=f"term_desc_{term.id}")
                        st.text_input("Área de Atuação", value=f"{area.nome if area else 'N/A'} (ID: {term.area_atuacao_id})", disabled=True, key=f"term_area_{term.id}")
                        st.text_input("Tipo de Pagamento", value=f"{pagamento.nome if pagamento else 'N/A'} (ID: {term.pagamento_id})", disabled=True, key=f"term_pag_{term.id}")
                        novo_status = st.checkbox("Ativo", value=term.ativo, key=f"term_ativo_{term.id}")
                    
                    if st.button("Salvar Alterações", key=f"term_save_{term.id}"):
                        term.cod_faturamento = st.session_state[f"term_cod_{term.id}"]
                        term.descricao = st.session_state[f"term_desc_{term.id}"]
                        term.ativo = novo_status
                        session.commit()
                        st.success("✅ Alterações salvas com sucesso!")
                        st.rerun()
        else:
            st.info("ℹ️ Nenhum código de faturamento cadastrado")

    except Exception as e:
        st.error(f"❌ Erro ao gerenciar códigos de faturamento: {str(e)}")
    finally:
        if session:
            session.close()

def dashboard_ocupacao():
    """Dashboard de ocupação por unidade"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("📊 Dashboard de Ocupação por Unidade")
        
        # Filtro de unidade
        unidades = session.query(Unidade).all()
        unidade_selecionada = st.selectbox(
            "Unidade",
            ["Todas as Unidades"] + [u.nome for u in unidades],
            index=0
        )
        
        # Query base
        query = session.query(
            Unidade.nome,
            func.count(DisponibilidadeSala.id).label('total_horarios'),
            func.sum(case((DisponibilidadeSala.status == 'Em atendimento', 1), else_=0)).label('horarios_alocados')
        ).join(Sala).join(DisponibilidadeSala).group_by(Unidade.id)
        
        if unidade_selecionada != "Todas as Unidades":
            query = query.filter(Unidade.nome == unidade_selecionada)
        
        resultados = query.all()
        
        # Exibição dos resultados
        for unidade, total, alocados in resultados:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Capacidade Total", total)
            with col2:
                percentual = (alocados / total * 100) if total > 0 else 0
                st.metric("Capacidade Alocada", f"{alocados} | {percentual:.1f}%")
            with col3:
                ociosidade = total - alocados
                percentual_ociosidade = (ociosidade / total * 100) if total > 0 else 0
                st.metric("Ociosidade", f"{ociosidade} | {percentual_ociosidade:.1f}%")
        
        # Análise de picos
        st.subheader("📈 Análise de Picos")
        col1, col2 = st.columns(2)
        
        with col1:
            # Picos de atendimento
            picos = session.query(
                DisponibilidadeSala.dia_semana,
                DisponibilidadeSala.horario,
                func.count(DisponibilidadeSala.id).label('quantidade')
            ).filter(DisponibilidadeSala.status == 'Em atendimento')
            
            if unidade_selecionada != "Todas as Unidades":
                picos = picos.join(Sala).join(Unidade).filter(Unidade.nome == unidade_selecionada)
            
            picos = picos.group_by(DisponibilidadeSala.dia_semana, DisponibilidadeSala.horario).order_by(func.count(DisponibilidadeSala.id).desc()).limit(5)
            
            st.write("**Top 5 Picos de Atendimento**")
            for dia, hora, qtd in picos:
                st.write(f"- {dia} {hora}: {qtd} atendimentos")
        
        with col2:
            # Picos de vacância
            vacancia = session.query(
                DisponibilidadeSala.dia_semana,
                DisponibilidadeSala.horario,
                func.count(DisponibilidadeSala.id).label('quantidade')
            ).filter(DisponibilidadeSala.status == 'Disponível')
            
            if unidade_selecionada != "Todas as Unidades":
                vacancia = vacancia.join(Sala).join(Unidade).filter(Unidade.nome == unidade_selecionada)
            
            vacancia = vacancia.group_by(DisponibilidadeSala.dia_semana, DisponibilidadeSala.horario).order_by(func.count(DisponibilidadeSala.id).desc()).limit(5)
            
            st.write("**Top 5 Horários de Vacância**")
            for dia, hora, qtd in vacancia:
                st.write(f"- {dia} {hora}: {qtd} vagas")
                
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de ocupação: {str(e)}")
    finally:
        if session:
            session.close()

def dashboard_area_atuacao():
    """Dashboard de área de atuação por unidade"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("📊 Dashboard de Área de Atuação")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            unidades = session.query(Unidade).all()
            unidade_selecionada = st.selectbox(
                "Unidade",
                ["Todas as Unidades"] + [u.nome for u in unidades],
                index=0
            )
        with col2:
            areas = session.query(AreaAtuacao).all()
            area_selecionada = st.selectbox(
                "Área de Atuação",
                ["Todas as Áreas"] + [a.nome for a in areas],
                index=0
            )
        
        # Query base
        query = session.query(
            Unidade.nome,
            AreaAtuacao.nome,
            func.count(Disponibilidade.id).label('total_horarios'),
            func.sum(case((Disponibilidade.status == 'Em atendimento', 1), else_=0)).label('horarios_alocados'),
            func.sum(case((Disponibilidade.status == 'Disponível', 1), else_=0)).label('horarios_vagos')
        ).join(Profissional).join(profissional_area_atuacao).join(AreaAtuacao).join(Unidade).group_by(Unidade.id, AreaAtuacao.id)
        
        if unidade_selecionada != "Todas as Unidades":
            query = query.filter(Unidade.nome == unidade_selecionada)
        if area_selecionada != "Todas as Áreas":
            query = query.filter(AreaAtuacao.nome == area_selecionada)
        
        resultados = query.all()
        
        # Exibição dos resultados
        for unidade, area, total, alocados, vagos in resultados:
            with st.expander(f"🏥 {unidade} - {area}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Capacidade Total", total)
                with col2:
                    percentual = (alocados / total * 100) if total > 0 else 0
                    st.metric("Horários Alocados", f"{alocados} | {percentual:.1f}%")
                with col3:
                    percentual = (vagos / total * 100) if total > 0 else 0
                    st.metric("Horários Vagos", f"{vagos} | {percentual:.1f}%")
                
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de área de atuação: {str(e)}")
    finally:
        if session:
            session.close()

def dashboard_disponibilidade():
    """Dashboard de disponibilidade de profissionais"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("📊 Dashboard de Disponibilidade de Profissionais")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            unidades = session.query(Unidade).all()
            unidade_selecionada = st.selectbox(
                "Unidade",
                ["Todas as Unidades"] + [u.nome for u in unidades],
                index=0
            )
        with col2:
            areas = session.query(AreaAtuacao).all()
            area_selecionada = st.selectbox(
                "Área de Atuação",
                ["Todas as Áreas"] + [a.nome for a in areas],
                index=0
            )
        
        # Query base
        query = session.query(
            Profissional.nome,
            AreaAtuacao.nome,
            func.count(Disponibilidade.id).label('total_horarios'),
            func.sum(case((Disponibilidade.status == 'Em atendimento', 1), else_=0)).label('horarios_alocados'),
            func.sum(case((Disponibilidade.status == 'Disponível', 1), else_=0)).label('horarios_vagos')
        ).join(Unidade).join(Disponibilidade).join(profissional_area_atuacao).join(AreaAtuacao).group_by(Profissional.id, AreaAtuacao.id)
        
        if unidade_selecionada != "Todas as Unidades":
            query = query.filter(Unidade.nome == unidade_selecionada)
        if area_selecionada != "Todas as Áreas":
            query = query.filter(AreaAtuacao.nome == area_selecionada)
        
        resultados = query.all()
        
        # Preparar dados para tabela
        dados = []
        for prof, area, total, alocados, vagos in resultados:
            percentual_vagos = (vagos / total * 100) if total > 0 else 0
            dados.append({
                'Profissional': prof,
                'Área de Atuação': area,
                'Capacidade Total': total,
                'Alocados': alocados,
                'Vagos': vagos,
                'Vacância %': f"{percentual_vagos:.1f}%"
            })
        
        # Ordenar por percentual de vacância
        dados = sorted(dados, key=lambda x: float(x['Vacância %'].replace('%', '')), reverse=True)
        
        # Exibir tabela
        st.dataframe(
            dados,
            column_config={
                "Profissional": st.column_config.TextColumn("Profissional"),
                "Área de Atuação": st.column_config.TextColumn("Área de Atuação"),
                "Capacidade Total": st.column_config.NumberColumn("Capacidade Total"),
                "Alocados": st.column_config.NumberColumn("Alocados"),
                "Vagos": st.column_config.NumberColumn("Vagos"),
                "Vacância %": st.column_config.TextColumn("Vacância %")
            },
            hide_index=True
        )
                
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de disponibilidade: {str(e)}")
    finally:
        if session:
            session.close()

def dashboard_profissionais():
    """Dashboard de métricas por profissional"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return

        st.subheader("👥 Dashboard por Profissional")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            unidades = session.query(Unidade).all()
            unidade_selecionada = st.selectbox(
                "Unidade",
                ["Todas as Unidades"] + [(u.id, u.nome) for u in unidades],
                format_func=lambda x: x[1] if isinstance(x, tuple) else x,
                key="select_unidade_prof"
            )
            unidade_id = unidade_selecionada[0] if isinstance(unidade_selecionada, tuple) else None
        
        with col2:
            areas = session.query(AreaAtuacao).all()
            area_selecionada = st.selectbox(
                "Área de Atuação",
                ["Todas as Áreas"] + [(a.id, a.nome) for a in areas],
                format_func=lambda x: x[1] if isinstance(x, tuple) else x,
                key="select_area_prof"
            )
            area_id = area_selecionada[0] if isinstance(area_selecionada, tuple) else None
        
        # Consulta profissionais com filtros
        query = session.query(Profissional)
        if unidade_id:
            query = query.filter(Profissional.unidade_id == unidade_id)
        if area_id:
            query = query.join(Profissional.areas_atuacao).filter(AreaAtuacao.id == area_id)
        
        profissionais = query.all()
        
        if profissionais:
            # Criar DataFrame para os dados
            dados = []
            
            for prof in profissionais:
                # Consulta grade de disponibilidade do profissional
                disponibilidades = session.query(Disponibilidade).filter(
                    Disponibilidade.profissional_id == prof.id
                ).all()
                
                # Calcula métricas
                total_horarios = len(disponibilidades)
                horarios_bloqueados = len([d for d in disponibilidades if d.status == 'Bloqueio'])
                horarios_disponiveis = len([d for d in disponibilidades if d.status == 'Disponível'])
                horarios_atendimento = len([d for d in disponibilidades if d.status == 'Em atendimento'])
                
                # Capacidade total descontando os bloqueios
                capacidade_total = total_horarios - horarios_bloqueados
                
                # Calcula taxa de ocupação
                taxa_ocupacao = (horarios_atendimento / capacidade_total * 100) if capacidade_total > 0 else 0
                
                dados.append({
                    'Profissional': prof.nome,
                    'Capacidade Total': capacidade_total,
                    'Horários Bloqueados': horarios_bloqueados,
                    'Horários Disponíveis': horarios_disponiveis,
                    'Em Atendimento': horarios_atendimento,
                    'Taxa de Ocupação (%)': round(taxa_ocupacao, 2)
                })
            
            # Criar DataFrame
            df = pd.DataFrame(dados)
            
            # Exibir métricas gerais
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total de Profissionais", len(profissionais))
            with col2:
                st.metric("Média de Capacidade", round(df['Capacidade Total'].mean(), 1))
            with col3:
                st.metric("Média de Ocupação", f"{round(df['Taxa de Ocupação (%)'].mean(), 1)}%")
            with col4:
                st.metric("Total em Atendimento", df['Em Atendimento'].sum())
            
            # Gráfico de barras para taxa de ocupação
            fig = px.bar(
                df,
                x='Profissional',
                y='Taxa de Ocupação (%)',
                title='Taxa de Ocupação por Profissional',
                color='Taxa de Ocupação (%)',
                color_continuous_scale='RdYlGn_r'
            )
            st.plotly_chart(fig)
            
            # Tabela detalhada
            st.dataframe(
                df,
                column_config={
                    'Profissional': st.column_config.TextColumn("Profissional"),
                    'Capacidade Total': st.column_config.NumberColumn("Capacidade Total"),
                    'Horários Bloqueados': st.column_config.NumberColumn("Horários Bloqueados"),
                    'Horários Disponíveis': st.column_config.NumberColumn("Horários Disponíveis"),
                    'Em Atendimento': st.column_config.NumberColumn("Em Atendimento"),
                    'Taxa de Ocupação (%)': st.column_config.NumberColumn(
                        "Taxa de Ocupação (%)",
                        format="%.2f%%"
                    )
                },
                hide_index=True
            )
        else:
            st.info("ℹ️ Nenhum profissional encontrado com os filtros selecionados")

    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de profissionais: {str(e)}")
    finally:
        if session:
            session.close()

def dashboard():
    """Exibe o dashboard com métricas e gráficos"""
    st.title("📊 Dashboard")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏥 Unidades",
        "🎯 Áreas de Atuação",
        "👥 Profissionais",
        "📅 Horários"
    ])
    
    with tab1:
        dashboard_unidades()
    with tab2:
        dashboard_areas_atuacao()
    with tab3:
        dashboard_profissionais()
    with tab4:
        dashboard_horarios()

def main():
    """Função principal da aplicação"""
    try:
        # Verifica a integridade do banco de dados
        if not verificar_integridade_banco():
            st.error("❌ Falha ao verificar/criar banco de dados")
            return

        # Menu lateral
        st.sidebar.title("📅 Sistema de Agendamento")
        menu = st.sidebar.radio(
            "Menu Principal",
            ["🏠 Início", "📅 Consultar Disponibilidade", "📊 Dashboard", "⚙️ Gestão"]
        )

        if menu == "🏠 Início":
            st.title("🏠 Início")
            st.write("Bem-vindo ao Sistema de Agendamento!")
            st.write("Selecione uma opção no menu lateral para começar.")

        elif menu == "📅 Consultar Disponibilidade":
            consultar_disponibilidade()

        elif menu == "📊 Dashboard":
            dashboard()

        elif menu == "⚙️ Gestão":
            st.sidebar.subheader("Menu de Gestão")
            submenu = st.sidebar.radio(
                "Opções",
                [
                    "🏢 Unidades",
                    "🚪 Salas",
                    "👨‍⚕️ Profissionais",
                    "🏥 Pacientes",
                    "📋 Áreas de Atuação",
                    "💰 Pagamentos",
                    "👥 Perfis de Paciente",
                    "📝 Terminologias",
                    "📅 Agenda Fixa",
                    "🔒 Bloqueios"
                ]
            )

            if submenu == "🏢 Unidades":
                gerenciar_unidades()
            elif submenu == "🚪 Salas":
                gerenciar_salas()
            elif submenu == "👨‍⚕️ Profissionais":
                gerenciar_profissionais()
            elif submenu == "🏥 Pacientes":
                gerenciar_pacientes()
            elif submenu == "📋 Áreas de Atuação":
                gerenciar_areas_atuacao()
            elif submenu == "💰 Pagamentos":
                gerenciar_pagamentos()
            elif submenu == "👥 Perfis de Paciente":
                gerenciar_perfis_paciente()
            elif submenu == "📝 Terminologias":
                gerenciar_terminologias()
            elif submenu == "📅 Agenda Fixa":
                gerenciar_agenda_fixa()
            elif submenu == "🔒 Bloqueios":
                gerenciar_bloqueios()

    except Exception as e:
        st.error(f"❌ Erro na aplicação: {str(e)}")
        logging.error(f"Erro na aplicação: {str(e)}\n{traceback.format_exc()}")

def gerenciar_agenda_fixa():
    """Gerenciamento da agenda fixa"""
    st.title("📅 Gestão da Agenda Fixa")
    
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return
            
        try:
            # Inicializar lista de erros
            erros = []
            
            # Exibe info sobre o status atual
            total_agenda_fixa = session.query(AgendaFixa).count()
            total_disponibilidade = session.query(Disponibilidade).count()
            
            st.info(f"""
                ℹ️ **Status Atual:**
                - Registros na Agenda Fixa: {total_agenda_fixa}
                - Registros na Grade de Disponibilidade: {total_disponibilidade}
            """)
            
            # Botão para apagar dados
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Apagar Dados da Agenda Fixa e Disponibilidade", type="primary"):
                    with st.spinner("⏳ Removendo dados existentes..."):
                        try:
                            # Apagar dados existentes
                            session.query(AgendaFixa).delete()
                            session.query(Disponibilidade).delete()
                            session.commit()
                            st.success("✅ Dados da agenda fixa e disponibilidade apagados com sucesso!")
                            
                            # Atualiza contadores
                            total_agenda_fixa = 0
                            total_disponibilidade = 0
                            st.rerun()
                        except Exception as e:
                            session.rollback()
                            st.error(f"❌ Erro ao apagar dados: {str(e)}")
                            return
            
            # Template para upload
            with col2:
                try:
                    colunas_template = [
                        "Id Profissional", "Data", "Hora inicial", "Unidade", "Sala", 
                        "Profissional", "Tipo Atend", "Codigo Faturamento", 
                        "Qtd Sess", "Pagamento", "Paciente"
                    ]
                    # Gera o template e verifica se foi criado com sucesso
                    template_filename = "template_agenda_fixa.xlsx"
                    gerar_template_excel(template_filename, colunas_template)
                    
                    # Verifica se o arquivo existe antes de tentar abri-lo
                    import os
                    if os.path.exists(template_filename):
                        with open(template_filename, "rb") as file:
                            st.download_button(
                                label="📥 Baixar Template",
                                data=file.read(),
                                file_name=template_filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.warning("Template não pôde ser gerado. Use um modelo existente.")
                except Exception as e:
                    st.error(f"❌ Erro ao gerar template: {str(e)}")
                    logging.error(f"Erro ao gerar template: {str(e)}")
            
            # Linha separadora
            st.markdown("---")
            
            # Upload de arquivo
            st.subheader("📤 Upload da Agenda Fixa")
            st.write("Selecione um arquivo Excel com os dados da agenda fixa.")
            
            # Mensagem de status do processamento
            status_container = st.empty()
            progress_bar = st.empty()
            stats_container = st.empty()
            
            uploaded_file = st.file_uploader(
                "Escolha o arquivo Excel",
                type=["xlsx"],
                key="upload_agenda_fixa"
            )
            
            if uploaded_file:
                # Exibe status inicial
                status_container.info("⏳ Iniciando processamento do arquivo...")
                progress_bar.progress(10, text="Lendo arquivo...")
                
                try:
                    # Ler arquivo
                    df = pd.read_excel(uploaded_file)
                    progress_bar.progress(30, text="Verificando dados...")
                    
                    # Mostrar número de linhas e colunas
                    stats_container.info(f"📊 Arquivo: {len(df)} linhas e {len(df.columns)} colunas")
                    
                    # Processar arquivo
                    status_container.info("⏳ Processando dados da agenda fixa...")
                    progress_bar.progress(50, text="Processando dados...")
                    
                    resultado = processar_agenda_fixa(df)
                    
                    if resultado:
                        # Atualiza barra de progresso
                        progress_bar.progress(100, text="Concluído!")
                        status_container.success("✅ Arquivo processado com sucesso!")
                        
                        # Limpa o container de estatísticas anterior
                        stats_container.empty()
                        
                        # Exibir estatísticas em cards
                        st.subheader("📊 Estatísticas do Processamento")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric(
                                "📋 Horários na Grade",
                                len(session.query(Disponibilidade).all()),
                                help="Total de horários criados na grade de disponibilidade"
                            )
                        
                        with col2:
                            st.metric(
                                "✅ Processados",
                                resultado['processados'],
                                help="Total de horários processados da agenda fixa"
                            )
                        
                        with col3:
                            st.metric(
                                "⚠️ Ignorados",
                                resultado['ignorados'],
                                help="Total de horários que não puderam ser processados"
                            )
                        
                        # Exibir erros se houver
                        if resultado['erros']:
                            with st.expander(f"⚠️ Ver detalhes dos {len(resultado['erros'])} horários ignorados", expanded=True if len(resultado['erros']) > 0 else False):
                                for erro in resultado['erros']:
                                    st.warning(erro)
                        
                        # Exibir profissionais com grades incompletas
                        if resultado['profissionais_incompletos']:
                            with st.expander("⚠️ Profissionais com grades incompletas", expanded=True):
                                for prof_id in resultado['profissionais_incompletos']:
                                    st.warning(f"Profissional ID {prof_id} - Grade não pôde ser gerada completamente")
                        
                        # Exibir resumo por profissional
                        st.subheader("👥 Resumo por Profissional")
                        profissionais = session.query(Profissional).all()
                        
                        # Preparar dados para a tabela
                        dados_profissionais = []
                        for prof in profissionais:
                            total_slots = session.query(Disponibilidade).filter(
                                Disponibilidade.profissional_id == prof.id
                            ).count()
                            
                            em_atendimento = session.query(Disponibilidade).filter(
                                Disponibilidade.profissional_id == prof.id,
                                Disponibilidade.status == 'Em atendimento'
                            ).count()
                            
                            dados_profissionais.append({
                                "ID": prof.id,
                                "Nome": prof.nome,
                                "Total de Slots": total_slots,
                                "Em Atendimento": em_atendimento,
                                "% Ocupação": f"{(em_atendimento/total_slots*100):.1f}%" if total_slots > 0 else "0%"
                            })
                        
                        if dados_profissionais:
                            st.dataframe(dados_profissionais)
                        else:
                            st.info("Nenhum profissional com dados disponíveis")
                    else:
                        progress_bar.progress(100, text="Falha no processamento")
                        status_container.error("❌ Falha ao processar o arquivo. Verifique os erros acima.")
                
                except Exception as e:
                    progress_bar.progress(100, text="Erro")
                    status_container.error(f"❌ Erro ao processar arquivo: {str(e)}")
                    logging.error(f"Erro ao processar arquivo: {str(e)}")
            
        except Exception as e:
            st.error(f"❌ Erro ao gerenciar agenda fixa: {str(e)}")
            logging.error(f"Erro ao gerenciar agenda fixa: {str(e)}")
            
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao banco de dados: {str(e)}")
    finally:
        if session:
            session.close()

def gerenciar_bloqueios():
    """Gerenciamento de bloqueios"""
    st.title("🔒 Gestão de Bloqueios")
    
    # Exibir amostra dos dados
    exibir_amostra_disponibilidade()
    
    # Template para upload
    colunas_template = ["DIA DA SEMANA", "PERIODO", "ID PROFISSIONAL"]
    gerar_template_excel("template_bloqueios.xlsx", colunas_template)
    
    # Upload de arquivo
    uploaded_file = st.file_uploader(
        "📤 Upload de Bloqueios",
        type=["xlsx"],
        key="upload_bloqueios"
    )
    
    if uploaded_file:
        try:
            # Ler arquivo
            df = pd.read_excel(uploaded_file)
            
            # Processar arquivo
            if processar_bloqueios(df):
                # Exibir amostra atualizada
                exibir_amostra_disponibilidade()
                
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)}")
            logging.error(f"Erro ao processar arquivo de bloqueios: {str(e)}\n{traceback.format_exc()}")

def dashboard_unidades():
    """Exibe o dashboard de unidades"""
    st.subheader("🏥 Dashboard de Unidades")
    
    session = get_session()
    if not session:
        st.error("❌ Erro ao conectar ao banco de dados")
        return
    
    try:
        # Filtros
        unidades = session.query(Unidade).all()
        unidade_selecionada = st.selectbox(
            "Unidade",
            ["Todas as Unidades"] + [u.nome for u in unidades]
        )
        
        # Métricas Gerais
        st.subheader("Métricas Gerais")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Total de Profissionais
            total_profissionais = session.query(Profissional).count()
            st.metric("Total de Profissionais", total_profissionais)
        
        with col2:
            # Total de Salas
            total_salas = session.query(Sala).count()
            st.metric("Total de Salas", total_salas)
        
        with col3:
            # Total de Agendamentos
            total_agendamentos = session.query(Agendamento).count()
            st.metric("Total de Agendamentos", total_agendamentos)
        
        # Ocupação por Unidade
        st.subheader("Ocupação por Unidade")
        ocupacao_data = []
        
        for unidade in unidades:
            if unidade_selecionada == "Todas as Unidades" or unidade.nome == unidade_selecionada:
                # Total de salas na unidade
                total_salas_unidade = session.query(Sala).filter_by(unidade_id=unidade.id).count()
                
                if total_salas_unidade > 0:
                    # Salas ocupadas
                    salas_ocupadas = session.query(Sala).join(Agendamento).filter(
                        Sala.unidade_id == unidade.id,
                        Agendamento.status != "Cancelado"
                    ).count()
                    
                    # Calcular taxa de ocupação
                    taxa_ocupacao = (salas_ocupadas / total_salas_unidade * 100) if total_salas_unidade > 0 else 0
                    
                    ocupacao_data.append({
                        "Unidade": unidade.nome,
                        "Total de Salas": total_salas_unidade,
                        "Salas Ocupadas": salas_ocupadas,
                        "Taxa de Ocupação": taxa_ocupacao
                    })
        
        if ocupacao_data:
            # Exibir tabela de ocupação
            st.dataframe(ocupacao_data)
            
            # Gráfico de Ocupação
            df_ocupacao = pd.DataFrame(ocupacao_data)
            fig = px.bar(
                df_ocupacao,
                x="Unidade",
                y="Taxa de Ocupação",
                title="Taxa de Ocupação por Unidade",
                color="Unidade"
            )
            st.plotly_chart(fig)
        else:
            st.info("ℹ️ Não há dados de ocupação para exibir")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de unidades: {str(e)}")
    finally:
        session.close()

def dashboard_areas_atuacao():
    """Exibe o dashboard de áreas de atuação"""
    st.subheader("🎯 Dashboard de Áreas de Atuação")
    
    session = get_session()
    if not session:
        st.error("❌ Erro ao conectar ao banco de dados")
        return
    
    try:
        # Ocupação por Área de Atuação
        areas_data = []
        
        areas = session.query(AreaAtuacao).all()
        for area in areas:
            # Profissionais na área
            profissionais_area = session.query(Profissional).join(
                profissional_area_atuacao
            ).filter(profissional_area_atuacao.c.area_atuacao_id == area.id).count()
            
            # Agendamentos na área
            agendamentos_area = session.query(Agendamento).join(
                Profissional
            ).join(
                profissional_area_atuacao
            ).filter(profissional_area_atuacao.c.area_atuacao_id == area.id).count()
            
            areas_data.append({
                "Área": area.nome,
                "Profissionais": profissionais_area,
                "Agendamentos": agendamentos_area
            })
        
        if areas_data:
            # Exibir tabela de áreas
            st.dataframe(areas_data)
            
            # Gráfico de Áreas
            df_areas = pd.DataFrame(areas_data)
            fig = px.bar(
                df_areas,
                x="Área",
                y=["Profissionais", "Agendamentos"],
                title="Distribuição por Área de Atuação",
                barmode="group"
            )
            st.plotly_chart(fig)
        else:
            st.info("ℹ️ Não há dados de áreas de atuação para exibir")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de áreas de atuação: {str(e)}")
    finally:
        session.close()

def dashboard_horarios():
    """Exibe o dashboard de horários"""
    st.subheader("📅 Dashboard de Horários")
    
    session = get_session()
    if not session:
        st.error("❌ Erro ao conectar ao banco de dados")
        return
    
    try:
        # Horários de Pico
        horarios_data = []
        
        for hora in range(8, 20):  # Das 8h às 20h
            agendamentos_hora = session.query(Agendamento).filter(
                extract('hour', Agendamento.data_hora) == hora
            ).count()
            
            horarios_data.append({
                "Hora": f"{hora:02d}:00",
                "Agendamentos": agendamentos_hora
            })
        
        if horarios_data:
            # Exibir tabela de horários
            st.dataframe(horarios_data)
            
            # Gráfico de Horários
            df_horarios = pd.DataFrame(horarios_data)
            fig = px.line(
                df_horarios,
                x="Hora",
                y="Agendamentos",
                title="Distribuição de Agendamentos por Horário"
            )
            st.plotly_chart(fig)
        else:
            st.info("ℹ️ Não há dados de horários para exibir")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerar dashboard de horários: {str(e)}")
    finally:
        session.close()

def editar_grade_profissional(profissional_id):
    """Interface para edição de grade do profissional"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Não foi possível conectar ao banco de dados")
            return
            
        # Buscar profissional
        profissional = session.query(Profissional).options(
            joinedload(Profissional.disponibilidades)
        ).get(profissional_id)
        
        if not profissional:
            st.error("❌ Profissional não encontrado")
            return
            
        st.title(f"📅 Grade de Disponibilidade - {profissional.nome}")
        
        # Buscar unidades
        unidades = session.query(Unidade).filter_by(ativo=True).all()
        if not unidades:
            st.error("❌ Nenhuma unidade cadastrada")
            return
            
        # Criar dicionário de disponibilidades por dia e período
        disponibilidades = {}
        for disp in profissional.disponibilidades:
            dia = disp.dia_semana
            periodo = disp.periodo
            if dia not in disponibilidades:
                disponibilidades[dia] = {}
            disponibilidades[dia][periodo] = disp
            
        # Dias da semana e períodos
        dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta']
        periodos = ['Matutino', 'Vespertino']
        
        # Criar formulário para cada dia e período
        for dia in dias_semana:
            st.subheader(dia)
            cols = st.columns(2)
            
            for idx, periodo in enumerate(periodos):
                with cols[idx]:
                    st.write(f"**{periodo}**")
                    
                    # Obter disponibilidade existente
                    disp = disponibilidades.get(dia, {}).get(periodo)
                    
                    # Campos do formulário
                    status = st.selectbox(
                        "Status",
                        ["Disponível", "Em atendimento", "Bloqueado"],
                        index=0 if not disp else (
                            1 if disp.status == "Ocupado" or disp.status == "Em atendimento" 
                            else 2 if disp.status == "Bloqueado" 
                            else 0
                        ),
                        key=f"status_{dia}_{periodo}"
                    )
                    
                    if status == "Disponível":
                        unidade_id = st.selectbox(
                            "Unidade",
                            [u.id for u in unidades],
                            format_func=lambda x: next((u.nome for u in unidades if u.id == x), ""),
                            index=next((idx for idx, u in enumerate(unidades) if disp and u.id == disp.unidade_id), 0) if disp and disp.unidade_id else 0,
                            key=f"unidade_{dia}_{periodo}"
                        )
                        
                        hora_inicio = st.time_input(
                            "Hora Início",
                            datetime.strptime(disp.hora_inicio, "%H:%M").time() if disp and disp.hora_inicio else datetime.strptime("08:00", "%H:%M").time() if periodo == "Matutino" else datetime.strptime("13:00", "%H:%M").time(),
                            key=f"inicio_{dia}_{periodo}"
                        )
                        
                        hora_fim = st.time_input(
                            "Hora Fim",
                            datetime.strptime(disp.hora_fim, "%H:%M").time() if disp and disp.hora_fim else datetime.strptime("12:00", "%H:%M").time() if periodo == "Matutino" else datetime.strptime("18:00", "%H:%M").time(),
                            key=f"fim_{dia}_{periodo}"
                        )
                        
                        # Validar horários
                        if hora_inicio >= hora_fim:
                            st.error("❌ Hora início deve ser menor que hora fim")
                            continue
                            
                        # Atualizar ou criar disponibilidade
                        if disp:
                            disp.status = status
                            disp.unidade_id = unidade_id
                            disp.hora_inicio = hora_inicio.strftime("%H:%M")
                            disp.hora_fim = hora_fim.strftime("%H:%M")
                        else:
                            nova_disp = Disponibilidade(
                                profissional_id=profissional_id,
                                dia_semana=dia,
                                periodo=periodo,
                                status=status,
                                unidade_id=unidade_id,
                                hora_inicio=hora_inicio.strftime("%H:%M"),
                                hora_fim=hora_fim.strftime("%H:%M")
                            )
                            session.add(nova_disp)
                    else:
                        # Se não disponível, atualizar apenas o status
                        if disp:
                            disp.status = "Em atendimento" if status == "Em atendimento" else status
                        else:
                            nova_disp = Disponibilidade(
                                profissional_id=profissional_id,
                                dia_semana=dia,
                                periodo=periodo,
                                status="Em atendimento" if status == "Em atendimento" else status
                            )
                            session.add(nova_disp)
                            
        # Botão para salvar alterações
        if st.button("💾 Salvar Alterações"):
            try:
                session.commit()
                st.success("✅ Grade atualizada com sucesso!")
            except Exception as e:
                session.rollback()
                st.error(f"❌ Erro ao salvar alterações: {str(e)}")
                
    except Exception as e:
        st.error(f"❌ Erro ao editar grade: {str(e)}")
    finally:
        if session:
            session.close()

def verificar_tabela_disponibilidade(session):
    """Verifica se a tabela de disponibilidade existe"""
    try:
        # Verifica se a tabela existe
        if not inspect(engine).has_table("disponibilidade"):
            Base.metadata.create_all(engine)
        return True
    except Exception as e:
        logging.error(f"Erro ao verificar tabela de disponibilidade: {str(e)}")
        return False
            
# Constantes para dias da semana
DIAS_SEMANA_UTIL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira"]
DIAS_SEMANA_SABADO = ["Sábado"]
DIAS_SEMANA = {
    'SEGUNDA': 'Segunda-feira',
    'TERCA': 'Terça-feira',
    'QUARTA': 'Quarta-feira',
    'QUINTA': 'Quinta-feira',
    'SEXTA': 'Sexta-feira',
    'SABADO': 'Sábado'
}

# Constantes para horários
HORARIOS_MANHA = [
    time(7, 0), time(8, 0), time(9, 0), time(10, 0), time(11, 0),
    time(12, 0)
]

HORARIOS_TARDE = [
    time(13, 0), time(14, 0), time(15, 0), time(16, 0),
    time(17, 0), time(18, 0)
]

HORARIOS_SABADO = [f"{h:02d}:00" for h in range(8, 12)]  # 08:00 a 11:00

# Constantes para geração de grade
HORARIOS_DISPONIVEIS = [
    time(7, 0), time(8, 0), time(9, 0), time(10, 0), time(11, 0),
    time(12, 0), time(13, 0), time(14, 0), time(15, 0), time(16, 0),
    time(17, 0), time(18, 0)
]

def get_session():
    """Retorna uma sessão do banco de dados"""
    try:
        session = Session()
        return session
    except Exception as e:
        logging.error(f"Erro ao criar sessão do banco de dados: {str(e)}")
        return None

def processar_upload_profissionais(session, df):
    """Processa o upload de profissionais"""
    try:
        # Normaliza nomes das colunas
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]
        
        # Converte colunas para os tipos corretos
        # Id Profissional - garantir que seja inteiro
        df['id_profissional'] = df['id_profissional'].apply(
            lambda x: int(float(x)) if pd.notna(x) and str(x).strip() != "" else None
        )
        
        # Id Area - converter para lista de inteiros, tratando diferentes formatos
        df['id_area'] = df['id_area'].apply(
            lambda x: [int(float(i.strip())) for i in str(x).replace(';', ',').split(',') 
                      if i.strip() and i.strip().replace('.', '', 1).isdigit()] 
            if pd.notna(x) else []
        )
        
        # Id Pagamento - converter para lista de inteiros, tratando diferentes formatos
        df['id_pagamento'] = df['id_pagamento'].apply(
            lambda x: [int(float(i.strip())) for i in str(x).replace(';', ',').split(',') 
                      if i.strip() and i.strip().replace('.', '', 1).isdigit()] 
            if pd.notna(x) else []
        )
        
        # Codigo Pagamento - garantir que seja string ou número inteiro
        if 'codigo_pagamento' in df.columns:
            df['codigo_pagamento'] = df['codigo_pagamento'].apply(
                lambda x: str(int(float(x))) if pd.notna(x) and str(x).strip() != "" else None
            )
        
        # Perfil Paciente - converter para lista de inteiros, tratando diferentes formatos
        df['perfil_paciente'] = df['perfil_paciente'].apply(
            lambda x: [int(float(i.strip())) for i in str(x).replace(';', ',').split(',') 
                      if i.strip() and i.strip().replace('.', '', 1).isdigit()] 
            if pd.notna(x) else []
        )
        
        # Outras conversões existentes
        df['registro'] = df['registro'].apply(lambda x: str(int(float(x))) if pd.notna(x) else None)
        df['cbo'] = df['cbo'].apply(lambda x: str(int(float(x))) if pd.notna(x) else None)
        df['status'] = df['status'].apply(lambda x: True if str(x).lower() == "ativo" else False)
        
        # Remove linhas com ID inválido
        df = df.dropna(subset=['id_profissional'])
        
        # Obtém lista de IDs existentes
        ids_existentes = {p.id for p in session.query(Profissional).all()}
        
        # Inicializa contadores
        processados = 0
        ignorados = 0
        erros = []
        
        # Processa cada linha
        for _, row in df.iterrows():
            try:
                id_prof = row['id_profissional']
                
                if id_prof in ids_existentes:
                    # Atualiza profissional existente
                    profissional = session.query(Profissional).filter_by(id=id_prof).first()
                    profissional.nome = row['nome_profissional']
                    profissional.nome_conselho = row['nomeconselho']
                    profissional.registro = row['registro']
                    profissional.uf = row['uf']
                    profissional.cbo = row['cbo']
                    profissional.ativo = row['status']
                else:
                    # Cria novo profissional
                    profissional = Profissional(
                        id=id_prof,
                        nome=row['nome_profissional'],
                        nome_conselho=row['nomeconselho'],
                        registro=row['registro'],
                        uf=row['uf'],
                        cbo=row['cbo'],
                        ativo=row['status']
                    )
                    session.add(profissional)
                    ids_existentes.add(id_prof)
                
                # Atualiza áreas de atuação
                areas = session.query(AreaAtuacao).filter(AreaAtuacao.id.in_(row['id_area'])).all()
                profissional.areas_atuacao = areas
                
                # Atualiza pagamentos
                pagamentos = session.query(Pagamento).filter(Pagamento.id.in_(row['id_pagamento'])).all()
                profissional.pagamentos = pagamentos
                
                # Atualiza perfis de paciente
                perfis = session.query(PerfilPaciente).filter(PerfilPaciente.id.in_(row['perfil_paciente'])).all()
                profissional.perfis_paciente = perfis
                
                processados += 1
                
            except Exception as e:
                ignorados += 1
                erros.append(f"Erro na linha {_ + 2}: {str(e)}")
                continue
        
        # Commit das alterações
        session.commit()
        
        return {
            'processados': processados,
            'ignorados': ignorados,
            'erros': erros
        }
        
    except Exception as e:
        session.rollback()
        raise e

def gerar_template_agenda_fixa(nome_arquivo):
    """Gera template para upload da agenda fixa"""
    colunas = [
        "Id Profissional", "Data", "Hora Inicial", "Unidade", "Sala", 
        "Profissional", "Tipo Atend", "Codigo Faturamento", 
        "Qtd Sess", "Pagamento", "Paciente"
    ]
    gerar_template_excel(nome_arquivo, colunas)

def exibir_amostra_disponibilidade():
    """Exibe uma amostra dos dados da tabela disponibilidade"""
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return
            
        # Buscar amostra de dados
        disponibilidades = session.query(
            Disponibilidade.profissional_id,
            Disponibilidade.dia_semana,
            Disponibilidade.hora_inicio,
            Disponibilidade.status,
            Profissional.nome
        ).join(Profissional).limit(10).all()
        
        if disponibilidades:
            st.subheader("📊 Amostra da Tabela Disponibilidade")
            
            # Exibir dados em formato de tabela
            dados = []
            for disp in disponibilidades:
                dados.append({
                    "ID Profissional": disp.profissional_id,
                    "Nome Profissional": disp.nome,
                    "Dia da Semana": disp.dia_semana,
                    "Horário": disp.hora_inicio,
                    "Status": disp.status
                })
            
            st.dataframe(dados)
            
            # Exibir estatísticas
            total_registros = session.query(Disponibilidade).count()
            total_bloqueios = session.query(Disponibilidade).filter_by(status="Bloqueio").count()
            
            st.write(f"Total de registros na tabela: {total_registros}")
            st.write(f"Total de bloqueios: {total_bloqueios}")
            
            # Exibir tipos de dados
            st.subheader("📝 Tipos de Dados")
            st.write("ID Profissional:", type(disponibilidades[0].profissional_id))
            st.write("Dia da Semana:", type(disponibilidades[0].dia_semana))
            st.write("Horário:", type(disponibilidades[0].hora_inicio))
            
        else:
            st.info("ℹ️ Nenhum registro encontrado na tabela disponibilidade")
            
    except Exception as e:
        st.error(f"❌ Erro ao exibir amostra: {str(e)}")
        logging.error(f"Erro ao exibir amostra: {str(e)}\n{traceback.format_exc()}")
    finally:
        session.close()

def gerar_template_pacientes(nome_arquivo: str):
    """Gera template Excel para cadastro de pacientes"""
    colunas = ['numeroCarteira', 'idPacienteCarteira', 'NomePaciente', 'IdPagamento', 'Status']
    return gerar_template_excel(nome_arquivo, colunas)

def processar_upload_pacientes(df: pd.DataFrame) -> dict:
    """Processa o arquivo de upload de pacientes"""
    try:
        session = get_session()
        if not session:
            raise Exception("Erro ao conectar ao banco de dados")
            
        registros_processados = 0
        registros_ignorados = 0
        erros = []
        
        # Limpar tabelas existentes
        try:
            session.query(Carteira).delete()
            session.query(Paciente).delete()
            session.commit()
            logging.info("Tabelas de pacientes e carteiras limpas com sucesso")
        except Exception as e:
            session.rollback()
            raise Exception(f"Erro ao limpar tabelas: {str(e)}")
        
        # Verificar colunas obrigatórias e normalizar nomes
        colunas_esperadas = {
            'numeroCarteira': 'numero_carteira',
            'idPacienteCarteira': 'id_paciente_carteira',
            'NomePaciente': 'nome_paciente',
            'IdPagamento': 'id_pagamento',
            'Status': 'status'
        }
        
        # Verificar colunas faltantes
        colunas_faltantes = [col for col in colunas_esperadas.keys() if col not in df.columns]
        if colunas_faltantes:
            raise Exception(f"Colunas obrigatórias faltando: {', '.join(colunas_faltantes)}")
        
        # Renomear colunas para o formato interno
        df = df.rename(columns=colunas_esperadas)
        
        # Processar cada linha
        for idx, row in df.iterrows():
            try:
                # Normalizar dados
                numero_carteira = str(row['numero_carteira']).strip()
                # Converter ID do paciente para inteiro, removendo decimais
                id_paciente = int(float(row['id_paciente_carteira']))
                nome_paciente = str(row['nome_paciente']).strip()
                id_pagamento = int(float(row['id_pagamento']))
                status = str(row['status']).strip()
                
                # Validar status
                status_normalizado = status.lower()
                if status_normalizado in ['ativo', 'sim']:
                    status = 'Ativo'
                elif status_normalizado in ['inativo', 'não', 'nao']:
                    status = 'Inativo'
                else:
                    status = 'Ativo'  # Default para status inválido
                
                # Verificar pagamento
                pagamento = session.query(Pagamento).get(id_pagamento)
                if not pagamento:
                    erros.append(f"Pagamento não encontrado na linha {idx+2}: ID {id_pagamento}")
                    registros_ignorados += 1
                    continue
                
                # Criar paciente
                paciente = Paciente(
                    id_paciente_carteira=id_paciente,
                    nome=nome_paciente
                )
                session.add(paciente)
                session.flush()  # Para obter o ID do paciente
                
                # Criar carteira
                nova_carteira = Carteira(
                    numero_carteira=numero_carteira,
                    id_pagamento=id_pagamento,
                    status=status,
                    paciente_id=paciente.id
                )
                session.add(nova_carteira)
                
                registros_processados += 1
                
            except Exception as e:
                erros.append(f"Erro ao processar linha {idx+2}: {str(e)}")
                registros_ignorados += 1
                continue
        
        session.commit()
        return {
            'processados': registros_processados,
            'ignorados': registros_ignorados,
            'erros': erros
        }
        
    except Exception as e:
        if session:
            session.rollback()
        raise Exception(f"Erro ao processar arquivo: {str(e)}")

def gerenciar_pacientes():
    """Interface para gerenciamento de pacientes"""
    st.title("🏥 Gestão de Pacientes")
    
    session = None
    try:
        session = get_session()
        if not session:
            st.error("❌ Erro ao conectar ao banco de dados")
            return
        
        # Verificar se as tabelas existem
        if not verificar_tabela_pacientes(session):
            st.error("❌ Erro ao verificar tabelas de pacientes")
            return
        
        # Criar abas
        tab_lista, tab_cadastro, tab_upload = st.tabs(["📋 Lista", "➕ Cadastro", "📤 Upload"])
        
        with tab_lista:
            # Lista de pacientes
            pacientes = session.query(Paciente).all()
            
            if not pacientes:
                st.info("ℹ️ Nenhum paciente cadastrado")
            else:
                # Exibir pacientes em uma tabela expansível
                for paciente in pacientes:
                    with st.expander(f"📋 {paciente.nome} (ID: {paciente.id_paciente_carteira})"):
                        # Informações do paciente
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write("**Nome:**", paciente.nome)
                            st.write("**ID Paciente:**", paciente.id_paciente_carteira)
                            
                            # Carteiras do paciente
                            st.write("**Carteiras:**")
                            for carteira in paciente.carteiras:
                                status_color = "🟢" if carteira.status == "Ativo" else "🔴"
                                pagamento = session.query(Pagamento).get(carteira.id_pagamento)
                                nome_pagamento = pagamento.nome if pagamento else "N/A"
                                st.write(f"{status_color} Carteira: {carteira.numero_carteira}")
                                st.write(f"   Pagamento: {nome_pagamento}")
                                st.write(f"   Status: {carteira.status}")
                        
                        with col2:
                            if st.button("🗑️ Excluir", key=f"del_{paciente.id}"):
                                try:
                                    session.delete(paciente)
                                    session.commit()
                                    st.success("✅ Paciente excluído com sucesso!")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"❌ Erro ao excluir paciente: {str(e)}")
        
        with tab_cadastro:
            # Formulário para cadastro/edição
            with st.form("cadastro_paciente", clear_on_submit=True):
                st.write("### Dados do Paciente")
                id_paciente = st.text_input("ID do Paciente", help="Identificador único do paciente")
                nome = st.text_input("Nome do Paciente")
                
                st.write("### Carteiras")
                # Múltiplos pagamentos
                pagamentos = session.query(Pagamento).all()
                pagamentos_selecionados = st.multiselect(
                    "Pagamentos",
                    options=[(p.id, p.nome) for p in pagamentos],
                    format_func=lambda x: x[1]
                )
                
                # Campos para cada pagamento selecionado
                carteiras_info = []
                for pag_id, pag_nome in pagamentos_selecionados:
                    st.write(f"**Carteira para {pag_nome}:**")
                    col1, col2 = st.columns(2)
                    with col1:
                        numero_carteira = st.text_input(f"Número da Carteira", key=f"carteira_{pag_id}")
                    with col2:
                        status = st.selectbox(f"Status", ["Ativo", "Inativo"], key=f"status_{pag_id}")
                    
                    if numero_carteira:  # Só adiciona se o número da carteira foi preenchido
                        carteiras_info.append({
                            'pagamento_id': pag_id,
                            'numero_carteira': numero_carteira,
                            'status': status
                        })
                
                if st.form_submit_button("💾 Salvar"):
                    try:
                        if not nome or not id_paciente or not carteiras_info:
                            st.error("❌ Preencha todos os campos obrigatórios")
                            return
                        
                        # Converter ID para inteiro
                        try:
                            id_paciente = int(id_paciente)
                        except ValueError:
                            st.error("❌ ID do paciente deve ser um número inteiro")
                            return
                        
                        # Criar/atualizar paciente
                        paciente = session.query(Paciente).filter_by(id_paciente_carteira=id_paciente).first()
                        if not paciente:
                            paciente = Paciente(
                                id_paciente_carteira=id_paciente,
                                nome=nome
                            )
                            session.add(paciente)
                            session.flush()
                        else:
                            paciente.nome = nome
                        
                        # Remover carteiras antigas
                        for carteira in paciente.carteiras:
                            session.delete(carteira)
                        
                        # Criar novas carteiras
                        for info in carteiras_info:
                            nova_carteira = Carteira(
                                numero_carteira=info['numero_carteira'],
                                id_pagamento=info['pagamento_id'],
                                status=info['status'],
                                paciente_id=paciente.id
                            )
                            session.add(nova_carteira)
                        
                        session.commit()
                        st.success("✅ Paciente salvo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"❌ Erro ao salvar paciente: {str(e)}")
        
        with tab_upload:
            st.write("### Upload de Pacientes")
            
            # Botão para download do template
            if st.button("📥 Download Template"):
                gerar_template_pacientes("template_pacientes.xlsx")
                st.success("✅ Template gerado com sucesso!")
            
            # Upload do arquivo
            uploaded_file = st.file_uploader("Escolha o arquivo Excel", type=['xlsx'])
            
            if uploaded_file is not None:
                try:
                    # Ler arquivo Excel
                    df = pd.read_excel(uploaded_file)
                    
                    # Exibir preview dos dados
                    st.write("Preview dos dados:")
                    st.dataframe(df.head())
                    
                    # Processar arquivo
                    if st.button("▶️ Processar Arquivo"):
                        with st.spinner("⏳ Processando arquivo..."):
                            resultado = processar_upload_pacientes(df)
                            
                            if resultado['processados'] > 0:
                                st.success("✅ Arquivo processado com sucesso!")
                                
                                # Exibir estatísticas
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Registros Processados", resultado['processados'])
                                with col2:
                                    st.metric("Registros Ignorados", resultado['ignorados'])
                                
                                if resultado['erros']:
                                    with st.expander("Ver detalhes dos erros"):
                                        for erro in resultado['erros']:
                                            st.write(f"- {erro}")
                            else:
                                st.warning("⚠️ Nenhum registro foi processado")
                                
                except Exception as e:
                    st.error(f"❌ Erro ao processar arquivo: {str(e)}")
                    logging.error(f"Erro ao processar arquivo: {str(e)}")
    
    except Exception as e:
        st.error(f"❌ Erro ao gerenciar pacientes: {str(e)}")
        logging.error(f"Erro ao gerenciar pacientes: {str(e)}")
    finally:
        if session:
            session.close()

if __name__ == "__main__":
    main()