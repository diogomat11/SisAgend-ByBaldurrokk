# Sistema de Agendamento

Sistema de agendamento desenvolvido com Streamlit para gerenciamento de profissionais, pacientes e agendamentos.

## Funcionalidades

- 🏢 Gestão de Unidades
- 🚪 Gestão de Salas
- 👨‍⚕️ Gestão de Profissionais
- 🏥 Gestão de Pacientes
- 📋 Gestão de Áreas de Atuação
- 💰 Gestão de Pagamentos
- 👥 Gestão de Perfis de Paciente
- 📝 Gestão de Terminologias
- 📅 Agenda Fixa
- 🔒 Gestão de Bloqueios
- 📊 Dashboards

## Requisitos

- Python 3.8+
- pip (gerenciador de pacotes Python)
- Conta no [Supabase](https://supabase.com/) para banco de dados PostgreSQL
- Conta no [Streamlit Cloud](https://streamlit.io/cloud) para deploy online (opcional)

## Instalação Local

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/agendamento-streamlit.git
cd agendamento-streamlit
```

2. Crie um ambiente virtual:
```bash
python -m venv venv
```

3. Ative o ambiente virtual:
- Windows:
```bash
venv\Scripts\activate
```
- Linux/Mac:
```bash
source venv/bin/activate
```

4. Instale as dependências:
```bash
pip install -r requirements.txt
```

5. Configure as variáveis de ambiente:
- Copie o arquivo `.env.example` para `.env` e preencha com sua URL do banco de dados PostgreSQL (Supabase):

```
DATABASE_URL=postgresql+psycopg2://postgres:SENHA_DO_SUPABASE@db.lmnboexmebxxwfowyjqe.supabase.co:5432/postgres
```

## Executando a Aplicação Localmente

1. Ative o ambiente virtual (se ainda não estiver ativo)
2. Execute o comando:
```bash
streamlit run app.py
```
3. Acesse a aplicação no navegador: http://localhost:8501

## Deploy no Streamlit Cloud

1. Faça push do seu código para o GitHub.
2. Acesse [streamlit.io/cloud](https://streamlit.io/cloud) e clique em "New app".
3. Selecione o repositório e branch.
4. Em "Advanced settings" > "Secrets", adicione a variável:
   ```toml
   DATABASE_URL = "postgresql+psycopg2://postgres:SENHA_DO_SUPABASE@db.lmnboexmebxxwfowyjqe.supabase.co:5432/postgres"
   ```
   Substitua `SENHA_DO_SUPABASE` pela senha do seu banco no Supabase.
5. Clique em "Deploy".

**Importante:**
- Nunca coloque a senha real no código ou no repositório.
- Use sempre variáveis de ambiente para dados sensíveis.
- O arquivo `.env` **NÃO** deve ser versionado (veja `.gitignore`).

## Estrutura do Projeto

- `app.py`: Arquivo principal da aplicação
- `requirements.txt`: Lista de dependências
- `.env.example`: Exemplo de variáveis de ambiente
- `README.md`: Documentação do projeto
- `migrate_db.py`: Script de migração do banco SQLite para Supabase/PostgreSQL

## Contribuição

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes. 