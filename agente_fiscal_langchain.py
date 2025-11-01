# Arquivo: agente_fiscal_langchain.py (Versão com Lógica de Auditoria Integrada)

import os
import json
import re
import fitz  # PyMuPDF
from lxml import etree
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate
from langchain.tools import tool
from decimal import Decimal, InvalidOperation

# Importa a ferramenta de consulta NCM
from tipi.consultartipi import consultar_ncm

# --- Configuração do Agente LangChain ---

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("A variável de ambiente OPENAI_API_KEY não foi encontrada.")

llm = ChatOpenAI(api_key=openai_api_key, model="gpt-4-turbo", temperature=0)

# --- LÓGICA DE AUDITORIA (MOVIMOS DE FERRAMENTAS_FISCAIS.PY) ---

def _to_decimal(value_str):
    """Converte uma string para Decimal, tratando formatos pt-BR e padrão."""
    if not value_str:
        return Decimal('0.0')
    value_str = str(value_str).strip()
    if ',' in value_str and '.' in value_str:
        value_str = value_str.replace('.', '')
    value_str = value_str.replace(',', '.')
    return Decimal(value_str)

def validar_cnpj(cnpj: str) -> bool:
    cnpj = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False
    try:
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(d) * p for d, p in zip(cnpj[:12], pesos))
        resto = soma % 11
        dv1 = 0 if resto < 2 else 11 - resto
        if dv1 != int(cnpj[12]): return False
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(d) * p for d, p in zip(cnpj[:13], pesos))
        resto = soma % 11
        dv2 = 0 if resto < 2 else 11 - resto
        if dv2 != int(cnpj[13]): return False
        return True
    except (ValueError, IndexError): return False

def validar_cpf(cpf: str) -> bool:
    cpf = ''.join(filter(str.isdigit, cpf))
    if len(cpf) != 11 or len(set(cpf)) == 1: return False
    try:
        soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
        resto = (soma * 10) % 11
        if resto == 10: resto = 0
        if resto != int(cpf[9]): return False
        soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
        resto = (soma * 10) % 11
        if resto == 10: resto = 0
        if resto != int(cpf[10]): return False
        return True
    except (ValueError, IndexError): return False

VALID_CFOP_CODES = {"6102", "1101", "1102", "1201", "1202", "1401", "1403", "1904", "1916", "2101", "2102", "2201", "2202", "2401", "2403", "2904", "2916", "3101", "3102", "3201", "3202", "5101", "5102", "5116", "5117", "5401", "5403", "5405", "5656", "5904", "5929", "6101", "6108", "6401", "6403", "6404", "6656", "6904", "6929", "7101", "7102", "7127"}

def _auditar_dados_nfs_ocr(dados: dict) -> tuple[list, list]:
    errors = []
    warnings = []
    if not dados.get('emitente_cnpj'): 
        errors.append("CNPJ do emitente não informado.")
    elif not validar_cnpj(dados['emitente_cnpj']): 
        errors.append(f"CNPJ do emitente '{dados['emitente_cnpj']}' é inválido.")
    dest_doc = dados.get('destinatario_cnpj_cpf')
    if not dest_doc: 
        warnings.append("CPF/CNPJ do destinatário (tomador) não informado.")
    elif len(''.join(filter(str.isdigit, dest_doc))) > 11 and not validar_cnpj(dest_doc):
        errors.append(f"CNPJ do destinatário '{dest_doc}' é inválido.")
    elif len(''.join(filter(str.isdigit, dest_doc))) <= 11 and not validar_cpf(dest_doc):
        errors.append(f"CPF do destinatário '{dest_doc}' é inválido.")
    if not dados.get('numero'): errors.append("Número da nota não informado.")
    if not dados.get('data_emissao'): warnings.append("Data de emissão não informada.")
    if not dados.get('valor_total_nota'): errors.append("Valor total da nota não informado.")
    if not dados.get('discriminacao_servicos'): warnings.append("Discriminação dos serviços não informada ou vazia.")
    return errors, warnings

@tool
def auditar_e_salvar_dados_fiscais(dados_json: str) -> str:
    """
    Recebe dados fiscais em JSON, executa uma auditoria, gera uma conclusão com IA, 
    salva o resultado no banco de dados e retorna a conclusão.
    """
    try:
        dados = json.loads(dados_json)
    except json.JSONDecodeError as e:
        return json.dumps({'status': 'ERRO', 'mensagem': f"JSON de entrada para auditoria é inválido. Erro: {e}. Entrada: {dados_json[:500]}"})

    # Adicionado para tratar erros da etapa de extração
    if 'erro' in dados:
        return json.dumps({'status': 'ERRO', 'mensagem': f"A extração de dados falhou. Causa raiz: {dados['erro']}"})

    issues = []
    warnings = []
    ncm_info = [] # Lista para armazenar informações dos NCMs encontrados
    
    if dados.get('formato') in ['ocr', 'ocr_ia']:
        issues, warnings = _auditar_dados_nfs_ocr(dados)
    else:
        calculated_sum = Decimal('0.00')
        if not dados.get('numero'): issues.append("Número do documento não informado.")
        if not dados.get('emitente_cnpj') or not validar_cnpj(dados.get('emitente_cnpj', '')):
            issues.append(f"CNPJ do emitente '{dados.get('emitente_cnpj', '')}' é inválido ou não informado.")
        
        items = dados.get('itens', [])
        if not items: warnings.append("O documento não contém itens.")
        
        for i, item in enumerate(items, 1):
            item_prefix = f"Item {i} ({item.get('codigo', 'S/C')}) - "
            ncm = item.get('ncm')
            if not ncm:
                issues.append(f"{item_prefix}NCM não informado.")
            else:
                resultado_ncm = consultar_ncm(ncm, db_file='tipi/tipi.db')
                if not resultado_ncm:
                    issues.append(f"{item_prefix}NCM '{ncm}' é inválido ou não foi encontrado na Tabela TIPI.")
                else:
                    # Adiciona informações do NCM para a conclusão
                    ncm_info.append(
                        f"Item {item.get('codigo', 'S/C')} (NCM {resultado_ncm['ncm_encontrado']}): "
                        f"Descrição: {resultado_ncm['descricao']}, "
                        f"Alíquota IPI: {resultado_ncm['aliquota']}%"
                    )
                    try:
                        pIPI_doc_str = item.get('imposto', {}).get('IPI', {}).get('IPITrib', {}).get('pIPI')
                        if pIPI_doc_str is not None:
                            pIPI_doc = _to_decimal(pIPI_doc_str)
                            pIPI_tipi = _to_decimal(resultado_ncm.get('aliquota', '0'))
                            if pIPI_doc != pIPI_tipi:
                                warnings.append(f"{item_prefix}Alíquota de IPI ({pIPI_doc}%) diverge da Tabela TIPI ({pIPI_tipi}%).")
                    except (InvalidOperation, TypeError):
                        warnings.append(f"{item_prefix}Não foi possível validar a alíquota de IPI. Valor inválido no documento.")

            if not item.get('cfop') or item.get('cfop') not in VALID_CFOP_CODES:
                warnings.append(f"{item_prefix}CFOP '{item.get('cfop', '')}' não consta na lista de códigos válidos.")
            
            try:
                calculated_sum += _to_decimal(item.get('valor_total', '0'))
            except (InvalidOperation, TypeError):
                issues.append(f"{item_prefix}Contém valor total inválido.")

        doc_total = _to_decimal(dados.get('valor_total_nota', '0'))
        if abs(calculated_sum - doc_total) > Decimal('0.01'):
            issues.append(f"A soma dos itens ({calculated_sum:.2f}) difere do valor total da nota ({doc_total:.2f}).")

    status = 'error' if issues else ('warning' if warnings else 'success')
    
    # --- GERAÇÃO DA CONCLUSÃO COM IA ---
    if issues or warnings or ncm_info:
        prompt_conclusao = ChatPromptTemplate.from_messages([
            ("system", "Você é um assistente fiscal especialista. Sua tarefa é gerar uma conclusão clara e útil com base nos resultados de uma auditoria de documento fiscal. Analise os erros, avisos e as informações de NCM para gerar a conclusão. Na sua conclusão, além de mencionar os erros e avisos, liste explicitamente a descrição e a alíquota da TIPI para cada NCM encontrado."),
            ("human", f"Por favor, gere uma conclusão para a seguinte auditoria:\n- Erros Encontrados: {json.dumps(issues)}\n- Avisos Emitidos: {json.dumps(warnings)}\n- Informações de NCM Encontradas: {json.dumps(ncm_info)}")
        ])
        chain_conclusao = prompt_conclusao | llm
        conclusao_analise = chain_conclusao.invoke({}).content
    else:
        conclusao_analise = "Auditoria concluída com sucesso. Nenhuma inconsistência fiscal foi encontrada e todos os dados parecem estar em conformidade."

    audit_result = {
        'status_auditoria': status,
        'erros_auditoria': issues,
        'avisos_auditoria': warnings,
        'conclusao_analise': conclusao_analise,
    }
    audit_result.update(dados)

    try:
        banco_de_dados = []
        if os.path.exists('db_documentos.json') and os.path.getsize('db_documentos.json') > 0:
            with open('db_documentos.json', 'r', encoding='utf-8') as f:
                banco_de_dados = json.load(f)
        banco_de_dados.append(audit_result)
        with open('db_documentos.json', 'w', encoding='utf-8') as f:
            json.dump(banco_de_dados, f, indent=4, ensure_ascii=False)
        
        return json.dumps({"status": "SUCESSO", "mensagem": conclusao_analise})

    except Exception as e:
        return json.dumps({"status": "ERRO", "mensagem": f"Falha ao salvar o resultado da auditoria: {e}"})

# --- Funções e Ferramentas do Agente ---

def element_to_dict(element):
    """Converte um elemento lxml e seus filhos em um dicionário, tratando namespaces."""
    if element is None: return None
    tag = etree.QName(element).localname
    d = {tag: {} if element.attrib else None}
    children = list(element)
    if children:
        dd = {}
        for child in children:
            child_dict = element_to_dict(child)
            child_tag = etree.QName(child).localname
            if child_tag in dd:
                if not isinstance(dd[child_tag], list):
                    dd[child_tag] = [dd[child_tag]]
                dd[child_tag].append(child_dict[child_tag])
            else:
                dd[child_tag] = child_dict[child_tag]
        d = {tag: dd}
    if element.attrib: d[tag].update(element.attrib)
    if element.text and element.text.strip():
        if d[tag] is None: d[tag] = element.text
        elif isinstance(d[tag], dict): d[tag]['text'] = element.text
    return d

@tool
def extrair_dados_xml(caminho_arquivo: str) -> str:
    """
    Extrai dados detalhados de um arquivo XML de documento fiscal (NFe/CTe).
    Recebe o caminho do arquivo e retorna uma string JSON com os dados extraídos.
    """
    try:
        with open(caminho_arquivo, 'rb') as f: doc = etree.parse(f)
        root = doc.getroot()
        ns = {'doc': root.nsmap.get(None)}
        def get_text(element, path): 
            node = element.find(path, ns) if element is not None else None
            return node.text if node is not None else None

        ide_node = doc.find('.//doc:ide', ns)
        emit_node = doc.find('.//doc:emit', ns)
        dest_node = doc.find('.//doc:dest', ns)
        total_node = doc.find('.//doc:ICMSTot', ns)

        dados = {
            "tipo_documento": etree.QName(root).localname.replace('Proc', '').upper(),
            "numero": get_text(ide_node, 'doc:nNF') or get_text(ide_node, 'doc:nCT'),
            "data_emissao": get_text(ide_node, 'doc:dhEmi'),
            "emitente_razao_social": get_text(emit_node, 'doc:xNome'),
            "emitente_cnpj": get_text(emit_node, 'doc:CNPJ'),
            "destinatario_razao_social": get_text(dest_node, 'doc:xNome'),
            "destinatario_cnpj_cpf": get_text(dest_node, 'doc:CNPJ') or get_text(dest_node, 'doc:CPF'),
            "valor_total_nota": get_text(total_node, 'doc:vNF'),
            "itens": []
        }

        for det in doc.findall('.//doc:det', ns):
            prod_node = det.find('doc:prod', ns)
            imposto_node = det.find('doc:imposto', ns)
            item = {
                "codigo": get_text(prod_node, 'doc:cProd'), "descricao": get_text(prod_node, 'doc:xProd'),
                "ncm": get_text(prod_node, 'doc:NCM'), "cfop": get_text(prod_node, 'doc:CFOP'),
                "valor_total": get_text(prod_node, 'doc:vProd'),
                "imposto": element_to_dict(imposto_node).get('imposto', {}) if imposto_node is not None else {}
            }
            dados["itens"].append(item)

        # Validação de dados essenciais extraídos
        if not dados.get("numero") or not dados.get("emitente_cnpj"):
            return json.dumps({"erro": "Falha ao extrair dados essenciais do XML. O arquivo pode não ser um documento fiscal válido ou ter uma estrutura não suportada."})

        return json.dumps({k: v for k, v in dados.items() if v is not None})
    except etree.XMLSyntaxError as e:
        return json.dumps({"erro": f"O arquivo XML fornecido está mal formatado e não pode ser lido. Erro de sintaxe: {e}"})
    except Exception as e:
        return json.dumps({"erro": f"Falha ao processar XML: {e}"})

def extrair_dados_com_ia(texto_cru: str, llm_instance) -> str:
    """Usa IA para extrair dados de texto e garante retorno de JSON."""
    prompt_extracao = ChatPromptTemplate.from_messages([
        ("system", "Você é um especialista em extrair dados de OCR de notas fiscais. Extraia os campos solicitados e retorne APENAS o JSON. Campos: `cnpj_emitente`, `destinatario_cpf` (ou `destinatario_cnpj`), `numero`, `data_emissao`, `valor_total_nota`, `discriminacao_servicos`."),
        ("human", "Extraia os dados do texto: \n\n{texto_documento}")
    ])
    chain_extracao = prompt_extracao | llm_instance
    raw_output = chain_extracao.invoke({"texto_documento": texto_cru}).content
    json_match = re.search(r"```json\n({.*?})\n```", raw_output, re.DOTALL)
    if json_match: return json_match.group(1)
    try:
        start = raw_output.find('{')
        end = raw_output.rfind('}') + 1
        if start != -1 and end != 0: return raw_output[start:end]
    except ValueError: pass
    return raw_output

@tool
def extrair_dados_pdf(caminho_arquivo: str) -> str:
    """Extrai dados de um PDF de documento fiscal usando IA."""
    try:
        with fitz.open(caminho_arquivo) as doc:
            texto_completo = "".join(page.get_text() for page in doc)
        json_extraido_str = extrair_dados_com_ia(texto_completo, llm)
        dados_extraidos = json.loads(json_extraido_str)
        dados_extraidos['emitente_cnpj'] = dados_extraidos.pop('cnpj_emitente', None)
        dados_extraidos['destinatario_cnpj_cpf'] = dados_extraidos.pop('destinatario_cnpj', dados_extraidos.pop('destinatario_cpf', None))
        dados_extraidos['formato'] = 'ocr_ia'
        dados_extraidos['tipo_documento'] = 'NFS-e'
        return json.dumps(dados_extraidos)
    except Exception as e:
        return json.dumps({"erro": f"Falha ao processar PDF: {e}"})

@tool
def consultar_ncm_tool(ncm_codigo: str) -> str:
    """Consulta a alíquota de IPI para um código NCM específico."""
    resultado = consultar_ncm(ncm_codigo, db_file='tipi/tipi.db')
    return json.dumps(resultado if resultado else {"erro": f"NCM '{ncm_codigo}' não encontrado."})

# --- Lista de Ferramentas e Prompt do Agente ---

tools = [
    extrair_dados_xml,
    extrair_dados_pdf,
    auditar_e_salvar_dados_fiscais,
    consultar_ncm_tool,
]

prompt_template = '''
Você é um assistente fiscal especialista. Sua função é processar, auditar, armazenar e consultar informações sobre documentos fiscais.

1.  **Processamento de Documentos (XML/PDF):**
    - Siga o fluxo de 2 passos: `extrair_dados_*` e depois `auditar_e_salvar_dados_fiscais`.
    - **REGRA DE OURO**: Passe o JSON da extração COMPLETO E SEM MODIFICAÇÕES para a ferramenta de auditoria.
    - A ferramenta `auditar_e_salvar_dados_fiscais` é a etapa final. Apresente o resultado dela de forma clara para o usuário.

2.  **Consulta de NCM (Tabela TIPI):**
    - Use `consultar_ncm_tool` para perguntas sobre IPI de NCM.
'''

prompt = ChatPromptTemplate.from_messages([
    ("system", prompt_template),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)