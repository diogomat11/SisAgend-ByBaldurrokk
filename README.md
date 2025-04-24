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

## Instalação

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

## Executando a Aplicação

1. Ative o ambiente virtual (se ainda não estiver ativo)
2. Execute o comando:
```bash
streamlit run app.py
```

3. Acesse a aplicação no navegador: http://localhost:8501

## Estrutura do Projeto

- `app.py`: Arquivo principal da aplicação
- `requirements.txt`: Lista de dependências
- `.gitignore`: Arquivos e diretórios ignorados pelo Git
- `README.md`: Documentação do projeto

## Contribuição

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes. 