# Agente Fiscal Inteligente 🤖

## 1. Visão Geral

O **Agente Fiscal Inteligente** é uma aplicação de Inteligência Artificial projetada para automatizar a análise, auditoria e gerenciamento de documentos fiscais eletrônicos. Utilizando o poder de Grandes Modelos de Linguagem (LLMs) através do framework LangChain, este agente é capaz de processar arquivos XML (NF-e, CT-e) e PDF (NFS-e), extrair dados, realizar uma auditoria detalhada e apresentar os resultados em um dashboard interativo.

O objetivo principal é reduzir o trabalho manual, minimizar erros e fornecer insights claros sobre a conformidade fiscal dos documentos.

---

## 2. Funcionalidades Principais

- **Processamento Multiformato:** Extrai dados de arquivos `XML` e `PDF`.
- **Atualização Automática da Tabela TIPI:** Ao iniciar, a aplicação verifica e baixa a versão mais recente da Tabela TIPI (webscrapping) diretamente do site do Governo Federal, garantindo que as validações sejam sempre feitas com dados atualizados.
- **Auditoria Fiscal Abrangente:**
  - **Validação de Documentos:** Verifica a validade de CNPJ e CPF do emitente e destinatário.
  - **Conformidade de Itens:** Valida os códigos NCM de cada item contra a Tabela TIPI (Tabela de Incidência do Imposto sobre Produtos Industrializados).
  - **Análise de Alíquotas:** Compara a alíquota de IPI declarada no documento com a alíquota oficial da Tabela TIPI.
  - **Consistência de Valores:** Verifica se a soma dos valores dos itens corresponde ao valor total da nota.
  - **Validação de CFOP:** Checa se os códigos CFOP estão em uma lista de códigos válidos.
- **Conclusão com IA:** Gera um resumo em linguagem natural, destacando os principais erros, avisos e informações relevantes encontradas na auditoria.
- **Dashboard Interativo:** Uma interface web construída com Streamlit para visualizar, filtrar e analisar todos os documentos processados.


---

## 3. Arquitetura e Tecnologias

- **Interface (Frontend):** [Streamlit](https://streamlit.io/)
- **Orquestração de IA:** [LangChain](https://www.langchain.com/)
- **Modelo de Linguagem:** OpenAI GPT-4-Turbo
- **Processamento de Dados:** [Pandas](https://pandas.pydata.org/)
- **Banco de Dados (TIPI):** SQLite
- **Armazenamento de Auditorias:** Arquivo JSON (`db_documentos.json`)

---

## 4. Instalação e Configuração

Siga os passos abaixo para configurar e executar o projeto em seu ambiente local.

**Pré-requisitos:**
- Python 3.8 ou superior
- Git

**Passo 1: Clonar o Repositório**
```bash
git clone C:\Users\henri\Documents\GitHub\Agente-Fiscal.git
cd Agente-Fiscal
```

**Passo 2: Criar um Ambiente Virtual**
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

**Passo 3: Instalar as Dependências**
```bash
pip install -r requirements.txt
```

**Passo 4: Configurar a Chave da API OpenAI**
Crie um arquivo chamado `.env` na raiz do projeto e adicione sua chave da API OpenAI:
```
OPENAI_API_KEY="sua-chave-secreta-aqui"
```

---

## 5. Como Usar

Com o ambiente configurado, inicie a aplicação com o seguinte comando:

```bash
streamlit run app.py
```

Ao iniciar pela primeira vez, o terminal exibirá mensagens indicando que a Tabela TIPI está sendo baixada e processada. Este processo pode levar alguns instantes.

Após a inicialização, a interface será aberta em seu navegador. 

1.  **Para analisar um documento:**
    - Na aba **"Processar Novo Documento"**, clique em **"Browse files"**.
    - Selecione um ou mais arquivos XML ou PDF.
    - Clique no botão **"Analisar Documento"**.
    - Aguarde o processamento e veja a conclusão do agente.

2.  **Para ver o dashboard:**
    - Clique na aba **"Dashboard de Documentos"** para ver uma tabela com todos os documentos já processados e análises rápidas sobre os dados.

---

## 6. Estrutura do Projeto

```
Agente-Fiscal/
├─── app.py                     # Aplicação principal Streamlit (Frontend)
├─── agente_fiscal_langchain.py # Lógica central do agente, ferramentas e auditoria
├─── requirements.txt           # Lista de dependências Python
├─── db_documentos.json         # Armazena os resultados das auditorias
├─── .env                       # Arquivo para chaves de API (não versionado)
├─── .gitignore
├─── README.md                  # Este arquivo
└─── tipi/                      # Módulo de gerenciamento da Tabela TIPI
    ├─── atualizartipi.py       # Script que baixa e processa a tabela
    ├─── consultartipi.py       # Script que realiza a consulta no banco de dados
    └─── tipi.db                # Banco de dados SQLite gerado
```
