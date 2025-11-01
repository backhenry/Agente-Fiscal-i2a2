# Arquivo: app.py (Versão com Dashboard e Funções Internas)

import streamlit as st
import os
import pandas as pd
import json
from agente_fiscal_langchain import agent_executor
from tipi.atualizartipi import baixar_tipi_xlsx, processar_tipi_para_sqlite

# --- ATUALIZAÇÃO AUTOMÁTICA DA TABELA TIPI ---
print("Verificando e atualizando a tabela TIPI...")
tentativa_de_download = baixar_tipi_xlsx(output_filename="tipi/tipi_download.xlsx")
if tentativa_de_download and os.path.exists(tentativa_de_download):
    processar_tipi_para_sqlite(tentativa_de_download, db_file="tipi/tipi.db")
    print("Tabela TIPI atualizada com sucesso.")
else:
    print("Falha ao baixar a tabela TIPI. Usando a versão local, se existir.")

# --- Funções de Lógica do App ---

def ler_registros_do_banco() -> str:
    """
    Lê os registros do 'banco de dados' (atualmente um arquivo JSON)
    e retorna como uma string JSON.
    """
    db_file = 'db_documentos.json'
    if not os.path.exists(db_file):
        return json.dumps([])
    with open(db_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []
    return json.dumps(data)

# --- Configuração da Página ---
st.set_page_config(page_title="Agente Fiscal Inteligente", page_icon="🤖", layout="wide")

st.title("🤖 Agente Fiscal Inteligente")
st.caption("Uma solução de IA para automatizar a análise e o gerenciamento de documentos fiscais.")

# --- ABAS DA APLICAÇÃO ---
tab_processamento, tab_dashboard = st.tabs(["Processar Novo Documento", "Dashboard de Documentos"])


# --- ABA 1: PROCESSAMENTO DE DOCUMENTOS ---
with tab_processamento:
    st.header("Análise de Documento Individual")
    uploaded_file = st.file_uploader("Selecione o documento fiscal (XML ou PDF)", type=['xml', 'pdf'])

    if uploaded_file is not None:
        temp_dir = "temp_uploads"
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())

        if st.button("Analisar Documento", type="primary", use_container_width=True):
            tarefa = f"Extraia, audite e salve no banco de dados o documento fiscal '{file_path}'"
            
            with st.spinner('O Agente está trabalhando...'):
                try:
                    resultado = agent_executor.invoke({"input": tarefa})
                    st.subheader("✅ Análise Concluída")
                    st.markdown(resultado["output"])
                    st.cache_data.clear()
                    
                    with st.expander("Ver o raciocínio detalhado do Agente"):
                        st.json(resultado)

                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")

# --- ABA 2: DASHBOARD (LÓGICA CORRIGIDA) ---
with tab_dashboard:
    st.header("Documentos Fiscais Processados")
    
    if st.button("Atualizar Dados", use_container_width=True):
        st.cache_data.clear()

    @st.cache_data(ttl=60)
    def carregar_dados():
        dados_json = ler_registros_do_banco()
        return json.loads(dados_json)

    dados = carregar_dados()

    if isinstance(dados, list) and dados:
        dados_planos = []
        for doc_auditado in dados:
            # A estrutura de dados agora é plana. Acessamos os campos diretamente.
            if not doc_auditado: continue

            info_base = {
                'status_auditoria': doc_auditado.get('status_auditoria'),
                'numero_nota': doc_auditado.get('numero'),
                'conclusao_analise': doc_auditado.get('conclusao_analise'), # Nova coluna
                'data_emissao': doc_auditado.get('data_emissao'),
                'emitente': doc_auditado.get('emitente_razao_social'),
                'emitente_cnpj': doc_auditado.get('emitente_cnpj'),
                'destinatario': doc_auditado.get('destinatario_razao_social'),
                'destinatario_cnpj_cpf': doc_auditado.get('destinatario_cnpj_cpf'),
                'valor_total_nota': doc_auditado.get('valor_total_nota'),
                'tipo_documento': doc_auditado.get('tipo_documento'),
                'formato': doc_auditado.get('formato'),
                'discriminacao_servicos': doc_auditado.get('discriminacao_servicos'),
                'erros': ", ".join(doc_auditado.get('erros_auditoria', [])),
                'avisos': ", ".join(doc_auditado.get('avisos_auditoria', []))
            }
            
            itens = doc_auditado.get('itens', [])
            if itens and isinstance(itens, list):
                for item in itens:
                    linha = info_base.copy()
                    linha['item_codigo'] = item.get('codigo')
                    linha['item_descricao'] = item.get('descricao')
                    linha['item_ncm'] = item.get('ncm')
                    linha['item_cfop'] = item.get('cfop')
                    linha['item_valor_total'] = item.get('valor_total')
                    dados_planos.append(linha)
            else:
                # Para documentos sem itens (como NFS-e de OCR), usa o valor total da nota como o valor do item.
                info_base['item_valor_total'] = info_base.get('valor_total_nota')
                dados_planos.append(info_base)

        df = pd.DataFrame(dados_planos)

        # Reordenar colunas para colocar a conclusão em terceiro
        cols = df.columns.tolist()
        if 'conclusao_analise' in cols:
            cols.insert(2, cols.pop(cols.index('conclusao_analise')))
            df = df[cols]

        colunas_monetarias = ['valor_total_nota', 'item_valor_total']
        for col in colunas_monetarias:
            if col in df.columns:
                # Limpa e converte o formato de moeda (R$ 1.234,56 -> 1234.56)
                df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        st.dataframe(df, use_container_width=True)
        
        st.subheader("Análises Rápidas")
        col1, col2 = st.columns(2)
        with col1:
            if 'status_auditoria' in df.columns:
                st.write("Status das Auditorias")
                st.bar_chart(df['status_auditoria'].value_counts())
        with col2:
            if 'valor_total_nota' in df.columns:
                valor_por_nota = df.drop_duplicates(subset=['numero_nota']).set_index('numero_nota')
                st.bar_chart(valor_por_nota['valor_total_nota'])

    elif isinstance(dados, dict) and 'erro' in dados:
        st.error(f"Erro ao carregar dados do banco: {dados['erro']}")
    else:
        st.info("Nenhum documento processado ainda. Processe um documento na aba ao lado.")