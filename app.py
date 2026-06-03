import streamlit as st
import pandas as pd
import os
from sqlalchemy import create_engine, inspect
from datetime import datetime

st.set_page_config(page_title="Gestão de Estoque - Quermesse", layout="wide")

# Tentar buscar do st.secrets primeiro, depois do os.getenv, e fallback para SQLite local se não houver configuração
try:
    TURSO_URL = st.secrets.get("TURSO_DATABASE_URL") or os.getenv("TURSO_DATABASE_URL", "")
    TURSO_TOKEN = st.secrets.get("TURSO_AUTH_TOKEN") or os.getenv("TURSO_AUTH_TOKEN", "")
except (FileNotFoundError, KeyError):
    TURSO_URL = os.getenv("TURSO_DATABASE_URL", "")
    TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# Se estiver vazio ou contiver os templates de exemplo do Turso, usar SQLite local
if not TURSO_URL or "[SEU_BANCO]" in TURSO_URL or not TURSO_TOKEN or "[SEU_TOKEN_DE_AUTENTICACAO]" in TURSO_TOKEN:
    DB_URL = "sqlite:///estoque.db"
    engine = create_engine(DB_URL)
    is_sqlite = True
else:
    # O sqlalchemy-libsql exige o prefixo sqlite+libsql://
    if TURSO_URL.startswith("libsql://"):
        DB_URL = TURSO_URL.replace("libsql://", "sqlite+libsql://", 1)
    else:
        DB_URL = TURSO_URL
    
    try:
        # Tenta criar o engine com os argumentos de autenticação para o Turso
        engine = create_engine(
            DB_URL,
            connect_args={"auth_token": TURSO_TOKEN}
        )
        # Testar se o dialect/driver consegue ser carregado executando uma conexão simples
        with engine.connect() as conn:
            pass
        is_sqlite = False
    except Exception as e:
        # Se falhar (ex: módulo sqlalchemy-libsql não instalado), faz o fallback para o SQLite local
        DB_URL = "sqlite:///estoque.db"
        engine = create_engine(DB_URL)
        is_sqlite = True
        st.sidebar.warning("⚠️ O driver do Turso não está instalado ou o banco está inacessível. Usando banco de dados SQLite local temporariamente.")

# ==========================================
# SISTEMA DE AUTENTICAÇÃO VIA STREAMLIT SECRETS
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""

def check_credentials(username, password):
    if "credentials" in st.secrets and "usernames" in st.secrets["credentials"]:
        users = st.secrets["credentials"]["usernames"]
        if username in users:
            user_info = users[username]
            if str(user_info["password"]) == str(password):
                return user_info["name"]
    return None

if not st.session_state.logged_in:
    st.markdown(
        """
        <style>
        .login-box {
            background-color: #1e1e2e;
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            border: 1px solid #313244;
            max-width: 450px;
            margin: 2rem auto;
            text-align: center;
        }
        .login-title {
            color: #cdd6f4;
            font-size: 2.2rem;
            margin-bottom: 0.5rem;
            font-family: 'Outfit', sans-serif;
            font-weight: bold;
        }
        .login-subtitle {
            color: #a6adc8;
            font-size: 1rem;
            margin-bottom: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown(
            """
            <div class="login-box">
                <div class="login-title">🎪 Quermesse</div>
                <div class="login-subtitle">Controle de Inventário</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        with st.form("login_form"):
            username = st.text_input("Usuário", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            submit = st.form_submit_button("Entrar", use_container_width=True)
            
            if submit:
                name = check_credentials(username.strip(), password)
                if name:
                    st.session_state.logged_in = True
                    st.session_state.user_name = name
                    st.success(f"Bem-vindo, {name}! Entrando...")
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
                    
    st.stop()


import xml.etree.ElementTree as ET

def parse_nfe_xml(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # NF-e utiliza o namespace padrão da SEFAZ
        ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
        
        # Buscar número da nota fiscal
        nnf_elem = root.find('.//ns:ide/ns:nNF', ns)
        if nnf_elem is None:
            nnf_elem = root.find('.//ide/nNF')
            
        nNF = nnf_elem.text if nnf_elem is not None else "Desconhecida"
        
        items = []
        det_list = root.findall('.//ns:det', ns)
        if not det_list:
            det_list = root.findall('.//det')
            
        for det in det_list:
            prod = det.find('ns:prod', ns) if det.find('ns:prod', ns) is not None else det.find('prod')
            if prod is not None:
                xProd_elem = prod.find('ns:xProd', ns) if prod.find('ns:xProd', ns) is not None else prod.find('xProd')
                uCom_elem = prod.find('ns:uCom', ns) if prod.find('ns:uCom', ns) is not None else prod.find('uCom')
                qCom_elem = prod.find('ns:qCom', ns) if prod.find('ns:qCom', ns) is not None else prod.find('qCom')
                vUnCom_elem = prod.find('ns:vUnCom', ns) if prod.find('ns:vUnCom', ns) is not None else prod.find('vUnCom')
                
                xProd = xProd_elem.text if xProd_elem is not None else ""
                uCom = uCom_elem.text if uCom_elem is not None else ""
                qCom = float(qCom_elem.text) if qCom_elem is not None else 0.0
                vUnCom = float(vUnCom_elem.text) if vUnCom_elem is not None else 0.0
                
                # Conversão para quantidade inteira arredondada
                qCom_int = int(round(qCom))
                
                items.append({
                    'nome': xProd,
                    'unidade': uCom,
                    'quantidade': qCom_int,
                    'valor_unitario': vUnCom
                })
        return nNF, items
    except Exception as e:
        raise ValueError(f"Erro ao decodificar a Nota Fiscal XML: {e}")


def get_next_id(df, id_col):
    if df.empty:
        return 1
    numeric_ids = pd.to_numeric(df[id_col], errors='coerce').dropna()
    if numeric_ids.empty:
        return 1
    return int(numeric_ids.max()) + 1

def run_migrations():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    needs_remap = False
    
    # Verificar se as tabelas existem e se possuem IDs longos (UUIDs)
    if 'estoque' in tables:
        df_e = pd.read_sql("SELECT * FROM estoque", engine)
        if 'ID_Item' not in df_e.columns or df_e['ID_Item'].astype(str).str.len().max() > 10:
            needs_remap = True
            
    if 'barracas' in tables:
        df_b = pd.read_sql("SELECT * FROM barracas", engine)
        if 'ID_Barraca' not in df_b.columns or df_b['ID_Barraca'].astype(str).str.len().max() > 10:
            needs_remap = True
            
    if needs_remap:
        item_map = {}
        barraca_map = {}
        
        # Remapear Estoque
        if 'estoque' in tables:
            df_e = pd.read_sql("SELECT * FROM estoque", engine)
            if not df_e.empty:
                old_ids = df_e['ID_Item'].tolist() if 'ID_Item' in df_e.columns else df_e['Item'].tolist()
                new_ids = list(range(1, len(df_e) + 1))
                item_map.update(dict(zip(old_ids, new_ids)))
                item_map.update(dict(zip(df_e['Item'], new_ids)))
                
                df_e['ID_Item'] = new_ids
                df_e.to_sql('estoque', engine, if_exists='replace', index=False)
                
        # Remapear Barracas
        if 'barracas' in tables:
            df_b = pd.read_sql("SELECT * FROM barracas", engine)
            if not df_b.empty:
                old_ids = df_b['ID_Barraca'].tolist() if 'ID_Barraca' in df_b.columns else df_b['Nome'].tolist()
                new_ids = list(range(1, len(df_b) + 1))
                barraca_map.update(dict(zip(old_ids, new_ids)))
                barraca_map.update(dict(zip(df_b['Nome'], new_ids)))
                
                df_b['ID_Barraca'] = new_ids
                df_b.to_sql('barracas', engine, if_exists='replace', index=False)
                
        # Remapear Receitas
        if 'receitas' in tables:
            df_r = pd.read_sql("SELECT * FROM receitas", engine)
            if not df_r.empty:
                df_r['ID_Registro'] = list(range(1, len(df_r) + 1))
                
                if 'Receita' in df_r.columns:
                    df_r['Nome_Receita'] = df_r['Receita']
                    
                if 'ID_Item' in df_r.columns:
                    df_r['ID_Item'] = df_r['ID_Item'].map(lambda x: item_map.get(x, x))
                elif 'Ingrediente' in df_r.columns:
                    df_r['ID_Item'] = df_r['Ingrediente'].map(lambda x: item_map.get(x, x))
                    
                if 'ID_Barraca' in df_r.columns:
                    df_r['ID_Barraca'] = df_r['ID_Barraca'].map(lambda x: barraca_map.get(x, x))
                elif 'Barraca_Associada' in df_r.columns:
                    df_r['ID_Barraca'] = df_r['Barraca_Associada'].map(lambda x: barraca_map.get(x, x))
                    
                col_list = ['ID_Registro', 'Nome_Receita', 'ID_Item', 'Qtd_Necessaria', 'ID_Barraca']
                for col in col_list:
                    if col not in df_r.columns:
                        df_r[col] = None
                df_r = df_r[col_list].dropna(subset=['ID_Item', 'ID_Barraca'])
                df_r.to_sql('receitas', engine, if_exists='replace', index=False)
                
        # Remapear Histórico
        if 'historico' in tables:
            df_h = pd.read_sql("SELECT * FROM historico", engine)
            if not df_h.empty:
                df_h['ID_Historico'] = list(range(1, len(df_h) + 1))
                
                if 'ID_Item' in df_h.columns:
                    df_h['ID_Item'] = df_h['ID_Item'].map(lambda x: item_map.get(x, x))
                else:
                    df_h['ID_Item'] = df_h['Item'].map(lambda x: item_map.get(x, x))
                    
                if 'ID_Barraca' in df_h.columns:
                    df_h['ID_Barraca'] = df_h['ID_Barraca'].map(lambda x: barraca_map.get(x, x))
                else:
                    df_h['ID_Barraca'] = df_h['Barraca'].map(lambda x: barraca_map.get(x, x))
                    
                col_h = ['ID_Historico', 'Data/Hora', 'ID_Item', 'Movimento', 'Quantidade', 'ID_Barraca', 'Item', 'Barraca']
                for col in col_h:
                    if col not in df_h.columns:
                        df_h[col] = None
                df_h = df_h[col_h]
                df_h.to_sql('historico', engine, if_exists='replace', index=False)

if 'migrated' not in st.session_state:
    run_migrations()
    st.session_state.migrated = True

# Loaders
def load_data():
    try:
        inspector = inspect(engine)
        if 'estoque' in inspector.get_table_names():
            return pd.read_sql("SELECT * FROM estoque", engine)
        else:
            return pd.DataFrame(columns=['ID_Item', 'Item', 'Categoria', 'Quantidade', 'Estoque Mínimo'])
    except Exception as e:
        st.sidebar.error(f"⚠️ Erro ao conectar no banco de dados. Os dados não serão salvos! Detalhe: {e}")
        return pd.DataFrame(columns=['ID_Item', 'Item', 'Categoria', 'Quantidade', 'Estoque Mínimo'])

def get_barracas_df():
    try:
        inspector = inspect(engine)
        if 'barracas' in inspector.get_table_names():
            return pd.read_sql("SELECT * FROM barracas", engine)
        else:
            default_barracas = ["Barraca do Pastel", "Barraca do Cachorro Quente", "Barraca do Refrigerante", "Barraca das Brincadeiras", "Caixa Principal", "Outras"]
            df_b = pd.DataFrame({'ID_Barraca': range(1, len(default_barracas) + 1), 'Nome': default_barracas})
            df_b.to_sql('barracas', engine, index=False)
            return df_b
    except Exception:
        return pd.DataFrame(columns=['ID_Barraca', 'Nome'])

def get_receitas_df():
    cols = ['ID_Registro', 'Nome_Receita', 'ID_Item', 'Qtd_Necessaria', 'ID_Barraca']
    try:
        inspector = inspect(engine)
        if 'receitas' in inspector.get_table_names():
            return pd.read_sql("SELECT * FROM receitas", engine)
        else:
            df_r = pd.DataFrame(columns=cols)
            df_r.to_sql('receitas', engine, index=False)
            return df_r
    except Exception:
        return pd.DataFrame(columns=cols)

def save_data(df):
    df.to_sql('estoque', engine, if_exists='replace', index=False)

def save_barracas_df(df_b):
    df_b.to_sql('barracas', engine, if_exists='replace', index=False)

def save_receitas_df(df_r):
    df_r.to_sql('receitas', engine, if_exists='replace', index=False)

def log_movement(id_item, nome_item, tipo, quantidade, id_barraca, nome_barraca):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_suffix = f" (por {st.session_state.user_name})" if st.session_state.get('user_name') else ""
    tipo_com_usuario = f"{tipo}{user_suffix}"
    try:
        df_h = pd.read_sql('SELECT "ID_Historico" FROM historico', engine)
        prox_id = get_next_id(df_h, 'ID_Historico')
    except Exception:
        prox_id = 1
        
    novo_log = pd.DataFrame([{
        'ID_Historico': prox_id,
        'Data/Hora': agora,
        'ID_Item': id_item,
        'Item': nome_item,
        'Movimento': tipo_com_usuario,
        'Quantidade': quantidade,
        'ID_Barraca': id_barraca,
        'Barraca': nome_barraca
    }])
    novo_log.to_sql('historico', engine, if_exists='append', index=False)


# Session State Init
if 'df' not in st.session_state:
    st.session_state.df = load_data()
if 'barracas_df' not in st.session_state:
    st.session_state.barracas_df = get_barracas_df()
if 'receitas_df' not in st.session_state:
    st.session_state.receitas_df = get_receitas_df()

id_to_nome_item = dict(zip(st.session_state.df['ID_Item'], st.session_state.df['Item']))
nome_to_id_item = dict(zip(st.session_state.df['Item'], st.session_state.df['ID_Item']))

id_to_nome_barraca = dict(zip(st.session_state.barracas_df['ID_Barraca'], st.session_state.barracas_df['Nome']))
nome_to_id_barraca = dict(zip(st.session_state.barracas_df['Nome'], st.session_state.barracas_df['ID_Barraca']))

def highlight_low_stock(row):
    try:
        qtd = int(row['Quantidade'])
        min_estoque = int(row['Estoque Mínimo'])
        if qtd < min_estoque:
            return ['background-color: #ffcccc; color: black'] * len(row)
    except (ValueError, TypeError):
        pass
    return [''] * len(row)

st.title("🎪 Gestão de Inventário - Quermesse")

# Sidebar User Info & Logout
st.sidebar.markdown(f"👤 **Usuário:** {st.session_state.user_name}")

# Verificar status da conexão com o banco de dados
from sqlalchemy import text
db_online = False
db_err = None
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    db_online = True
except Exception as e:
    db_err = str(e)

if db_online:
    if is_sqlite:
        st.sidebar.success("🟢 Banco: SQLite Local (Online)")
    else:
        st.sidebar.success("🟢 Banco: Turso Cloud (Online)")
else:
    st.sidebar.error("🔴 Banco: Desconectado/Offline")
    if db_err:
        with st.sidebar.expander("Ver detalhes do erro"):
            st.code(db_err, language="text")

if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.rerun()
st.sidebar.divider()

st.sidebar.header("⚙️ Gestão de Cadastros")

tipo_cadastro = st.sidebar.radio("O que deseja gerenciar?", ["Itens de Estoque", "Barracas", "Receitas (Baixa Múltipla)"])

if tipo_cadastro == "Itens de Estoque":
    st.sidebar.subheader("Adicionar Novo Item")
    with st.sidebar.form("form_cadastro_item", clear_on_submit=True):
        novo_item = st.text_input("Nome do Item")
        nova_categoria = st.selectbox("Categoria", ["Comida", "Bebida", "Brincadeira", "Outros"])
        nova_qtd = st.number_input("Quantidade Inicial", min_value=0, step=1)
        novo_min = st.number_input("Estoque Mínimo", min_value=0, step=1)
        
        submit_button = st.form_submit_button("Adicionar Item")
        if submit_button:
            nome_limpo = novo_item.strip()
            item_ja_existe = False
            if not st.session_state.df.empty:
                item_ja_existe = nome_limpo.lower() in st.session_state.df['Item'].astype(str).str.strip().str.lower().values

            if nome_limpo == "":
                st.sidebar.error("O nome do item não pode estar vazio.")
            elif item_ja_existe:
                st.sidebar.error("Este item já está cadastrado.")
            else:
                novo_id = get_next_id(st.session_state.df, 'ID_Item')
                novo_registro = pd.DataFrame([{
                    'ID_Item': novo_id,
                    'Item': nome_limpo,
                    'Categoria': nova_categoria,
                    'Quantidade': nova_qtd,
                    'Estoque Mínimo': novo_min
                }])
                st.session_state.df = pd.concat([st.session_state.df, novo_registro], ignore_index=True) if not st.session_state.df.empty else novo_registro
                save_data(st.session_state.df)
                log_movement(novo_id, nome_limpo, "Entrada Inicial", nova_qtd, None, "-")
                st.sidebar.success(f"Item '{nome_limpo}' adicionado com sucesso!")
                st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Remover Item Existente")
    itens_disp = list(nome_to_id_item.keys()) if nome_to_id_item else ["Nenhum"]
    with st.sidebar.form("form_remover_item"):
        item_remover = st.selectbox("Selecione o Item", itens_disp)
        btn_rem_item = st.form_submit_button("Remover Item")
        if btn_rem_item and item_remover != "Nenhum":
            id_remover = nome_to_id_item[item_remover]
            st.session_state.df = st.session_state.df[st.session_state.df['ID_Item'] != id_remover]
            save_data(st.session_state.df)
            
            if not st.session_state.receitas_df.empty:
                st.session_state.receitas_df = st.session_state.receitas_df[st.session_state.receitas_df['ID_Item'] != id_remover]
                save_receitas_df(st.session_state.receitas_df)
                
            st.sidebar.success(f"Item '{item_remover}' removido!")
            st.rerun()

elif tipo_cadastro == "Barracas":
    st.sidebar.subheader("Adicionar Nova Barraca")
    with st.sidebar.form("form_cadastro_barraca", clear_on_submit=True):
        nova_b = st.text_input("Nome da nova barraca")
        btn_add_b = st.form_submit_button("Adicionar Barraca")
        if btn_add_b:
            b_limpa = nova_b.strip()
            b_ja_existe = False
            if not st.session_state.barracas_df.empty:
                b_ja_existe = b_limpa.lower() in st.session_state.barracas_df['Nome'].astype(str).str.strip().str.lower().values
                
            if b_limpa == "":
                st.sidebar.error("O nome da barraca não pode estar vazio.")
            elif b_ja_existe:
                st.sidebar.error("Esta barraca já existe.")
            else:
                novo_id = get_next_id(st.session_state.barracas_df, 'ID_Barraca')
                novo_registro = pd.DataFrame([{'ID_Barraca': novo_id, 'Nome': b_limpa}])
                st.session_state.barracas_df = pd.concat([st.session_state.barracas_df, novo_registro], ignore_index=True)
                save_barracas_df(st.session_state.barracas_df)
                st.sidebar.success(f"Barraca '{b_limpa}' adicionada!")
                st.rerun()
                
    st.sidebar.divider()
    st.sidebar.subheader("Remover Barraca Existente")
    barracas_disp = list(nome_to_id_barraca.keys()) if nome_to_id_barraca else ["Nenhuma"]
    with st.sidebar.form("form_remover_barraca"):
        b_remover = st.selectbox("Selecione a Barraca", barracas_disp)
        btn_rem_b = st.form_submit_button("Remover Barraca")
        if btn_rem_b and b_remover != "Nenhuma":
            id_rem_b = nome_to_id_barraca[b_remover]
            st.session_state.barracas_df = st.session_state.barracas_df[st.session_state.barracas_df['ID_Barraca'] != id_rem_b]
            save_barracas_df(st.session_state.barracas_df)
            
            if not st.session_state.receitas_df.empty:
                st.session_state.receitas_df = st.session_state.receitas_df[st.session_state.receitas_df['ID_Barraca'] != id_rem_b]
                save_receitas_df(st.session_state.receitas_df)
                
            st.sidebar.success(f"Barraca '{b_remover}' removida!")
            st.rerun()

elif tipo_cadastro == "Receitas (Baixa Múltipla)":
    st.sidebar.subheader("Montar Nova Receita")
    st.sidebar.write("Digite um nome, escolha a barraca e vá adicionando os ingredientes.")
    nome_receita = st.sidebar.text_input("Nome da Receita")
    
    barracas_disp_rec = list(nome_to_id_barraca.keys()) if nome_to_id_barraca else ["Nenhuma"]
    barraca_receita_nome = st.sidebar.selectbox("Barraca Associada", barracas_disp_rec)
    
    with st.sidebar.form("form_add_ingrediente", clear_on_submit=False):
        itens_disp = list(nome_to_id_item.keys()) if nome_to_id_item else []
        ingred_selecionado_nome = st.selectbox("Selecione o Ingrediente", itens_disp)
        qtd_ingred = st.number_input("Quantidade Necessária", min_value=1, step=1)
        btn_add_ingred = st.form_submit_button("Adicionar à Receita")
        
        if btn_add_ingred:
            nome_r = nome_receita.strip()
            if nome_r == "":
                st.sidebar.error("Preencha o Nome da Receita acima primeiro!")
            elif barraca_receita_nome == "Nenhuma":
                st.sidebar.error("Você precisa cadastrar uma barraca primeiro!")
            elif ingred_selecionado_nome:
                id_item_sel = nome_to_id_item[ingred_selecionado_nome]
                id_barraca_sel = nome_to_id_barraca[barraca_receita_nome]
                
                existe = False
                if not st.session_state.receitas_df.empty:
                    existe = not st.session_state.receitas_df[
                        (st.session_state.receitas_df['Nome_Receita'].str.lower() == nome_r.lower()) & 
                        (st.session_state.receitas_df['ID_Item'] == id_item_sel)
                    ].empty
                if existe:
                    st.sidebar.error("Este ingrediente já está nesta receita.")
                else:
                    novo_id_rec = get_next_id(st.session_state.receitas_df, 'ID_Registro')
                    novo_ing = pd.DataFrame([{
                        'ID_Registro': novo_id_rec,
                        'Nome_Receita': nome_r,
                        'ID_Item': id_item_sel,
                        'Qtd_Necessaria': qtd_ingred,
                        'ID_Barraca': id_barraca_sel
                    }])
                    st.session_state.receitas_df = pd.concat([st.session_state.receitas_df, novo_ing], ignore_index=True)
                    save_receitas_df(st.session_state.receitas_df)
                    st.sidebar.success(f"Ingrediente '{ingred_selecionado_nome}' adicionado à receita '{nome_r}'!")
                    st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Receitas Cadastradas")
    if not st.session_state.receitas_df.empty:
        receitas_nomes = st.session_state.receitas_df['Nome_Receita'].unique().tolist()
        for r in receitas_nomes:
            ingreds = st.session_state.receitas_df[st.session_state.receitas_df['Nome_Receita'] == r]
            if not ingreds.empty:
                id_barraca_rec = ingreds['ID_Barraca'].iloc[0]
                b_assoc = id_to_nome_barraca.get(id_barraca_rec, "Desconhecida")
                with st.sidebar.expander(f"Receita: {r} ({b_assoc})"):
                    for _, row_ing in ingreds.iterrows():
                        nome_i = id_to_nome_item.get(row_ing['ID_Item'], "Item Excluído")
                        st.write(f"- {row_ing['Qtd_Necessaria']}x {nome_i}")
                    if st.button(f"🗑️ Excluir", key=f"del_rec_{r}"):
                        st.session_state.receitas_df = st.session_state.receitas_df[st.session_state.receitas_df['Nome_Receita'] != r]
                        save_receitas_df(st.session_state.receitas_df)
                        st.rerun()
    else:
        st.sidebar.info("Nenhuma receita montada.")


tab_acoes, tab_xml, tab_estoque, tab_historico = st.tabs(["⚡ Ações Rápidas", "📥 Importar XML (NF-e)", "📦 Estoque (Gráficos)", "📜 Histórico de Movimentações"])

with tab_acoes:
    st.subheader("⚡ Ações Rápidas de Estoque")
    
    if st.session_state.df.empty:
        st.info("O estoque está vazio. Use a barra lateral para adicionar itens.")
    else:
        barracas_disponiveis = list(nome_to_id_barraca.keys())
        
        st.markdown("**Destino das Retiradas:**")
        barraca_atual_nome = st.selectbox("Selecione para qual barraca os itens estão indo:", barracas_disponiveis, label_visibility="collapsed")
        
        if not st.session_state.receitas_df.empty and barracas_disponiveis:
            id_barraca_atual = nome_to_id_barraca.get(barraca_atual_nome)
            receitas_da_barraca = st.session_state.receitas_df[st.session_state.receitas_df['ID_Barraca'] == id_barraca_atual]
            if not receitas_da_barraca.empty:
                with st.expander(f"🍳 Preparar Receita ({barraca_atual_nome})"):
                    receitas_unicas = receitas_da_barraca['Nome_Receita'].unique().tolist()
                    rec_selecionada = st.selectbox("Selecione a Receita", receitas_unicas)
                    multiplicador = st.number_input("Quantas vezes (porções) vai preparar?", min_value=1, step=1, value=1)
                    
                    if st.button("Preparar e Retirar Ingredientes", use_container_width=True):
                        ingreds = receitas_da_barraca[receitas_da_barraca['Nome_Receita'] == rec_selecionada]
                        pode_fazer = True
                        erros = []
                        
                        for _, row_ing in ingreds.iterrows():
                            id_ing = row_ing['ID_Item']
                            nome_ing = id_to_nome_item.get(id_ing, "Item Desconhecido")
                            qtd_necessaria_total = row_ing['Qtd_Necessaria'] * multiplicador
                            
                            item_idx = st.session_state.df[st.session_state.df['ID_Item'] == id_ing].index
                            if len(item_idx) > 0:
                                qtd_atual = st.session_state.df.at[item_idx[0], 'Quantidade']
                                if qtd_atual < qtd_necessaria_total:
                                    pode_fazer = False
                                    erros.append(f"Faltam {qtd_necessaria_total - qtd_atual}x de '{nome_ing}'.")
                            else:
                                pode_fazer = False
                                erros.append(f"Item '{nome_ing}' não encontrado no estoque atual.")
                        
                        if pode_fazer:
                            for _, row_ing in ingreds.iterrows():
                                id_ing = row_ing['ID_Item']
                                nome_ing = id_to_nome_item.get(id_ing, "Item")
                                qtd_necessaria_total = row_ing['Qtd_Necessaria'] * multiplicador
                                
                                item_idx = st.session_state.df[st.session_state.df['ID_Item'] == id_ing].index[0]
                                st.session_state.df.at[item_idx, 'Quantidade'] -= qtd_necessaria_total
                                log_movement(id_ing, nome_ing, f"Saída (Receita: {rec_selecionada} x{multiplicador})", qtd_necessaria_total, id_barraca_atual, barraca_atual_nome)
                            
                            save_data(st.session_state.df)
                            st.success(f"Baixa múltipla concluída! {multiplicador}x '{rec_selecionada}' enviado para '{barraca_atual_nome}'.")
                            st.rerun()
                        else:
                            st.error("Estoque insuficiente:\n\n" + "\n".join(erros))

        st.divider()
        st.markdown("**Movimentação Manual por Item:**")
        container = st.container(height=400)
        with container:
            for index, row in st.session_state.df.iterrows():
                col1, col2, col3, col4, col5 = st.columns([3, 2, 1.5, 1, 1])
                
                with col1:
                    st.write(f"**{row['Item']}** ({row['Categoria']})")
                with col2:
                    if row['Quantidade'] < row['Estoque Mínimo']:
                        st.error(f"Estq: {row['Quantidade']} / Min: {row['Estoque Mínimo']}", icon="⚠️")
                    else:
                        st.write(f"Estq: {row['Quantidade']} / Min: {row['Estoque Mínimo']}")
                
                with col3:
                    qtd_alterar = st.number_input("Qtd", min_value=1, step=1, value=1, key=f"qtd_{index}", label_visibility="collapsed")
                        
                with col4:
                    if st.button("➕", key=f"add_{index}", use_container_width=True, help="Adicionar quantidade"):
                        st.session_state.df.at[index, 'Quantidade'] += qtd_alterar
                        save_data(st.session_state.df)
                        log_movement(row['ID_Item'], row['Item'], "Entrada", qtd_alterar, None, "-")
                        st.rerun()
                with col5:
                    if st.button("➖", key=f"sub_{index}", use_container_width=True, help="Retirar quantidade"):
                        if barracas_disponiveis:
                            if st.session_state.df.at[index, 'Quantidade'] >= qtd_alterar:
                                st.session_state.df.at[index, 'Quantidade'] -= qtd_alterar
                                save_data(st.session_state.df)
                                id_bar_atual = nome_to_id_barraca.get(barraca_atual_nome)
                                log_movement(row['ID_Item'], row['Item'], "Saída", qtd_alterar, id_bar_atual, barraca_atual_nome)
                                st.rerun()
                            else:
                                st.toast(f"Não é possível retirar {qtd_alterar}. O estoque atual é {st.session_state.df.at[index, 'Quantidade']}.", icon="🚫")
                        else:
                            st.toast("Cadastre pelo menos uma barraca primeiro!", icon="🚫")

with tab_xml:
    st.subheader("📥 Importar Nota Fiscal (XML - NF-e)")
    
    xml_file = st.file_uploader("Selecione o arquivo XML da Nota Fiscal (NF-e)", type=["xml"], key="nfe_xml_uploader")
    
    if xml_file:
        try:
            # Para não fazer reparse desnecessário a cada interação do Streamlit
            if 'last_uploaded_xml' not in st.session_state or st.session_state.last_uploaded_xml != xml_file.name:
                st.session_state.nNF, st.session_state.xml_items = parse_nfe_xml(xml_file)
                st.session_state.last_uploaded_xml = xml_file.name
                # Resetar mapeamentos ao subir novo arquivo
                st.session_state.mappings = {}
                st.session_state.new_item_details = {}
                
            nNF = st.session_state.nNF
            xml_items = st.session_state.xml_items
            
            st.success(f"✅ Nota Fiscal nº **{nNF}** carregada com sucesso! Encontrados **{len(xml_items)}** itens.")
            
            st.markdown("### 🔍 Associação de Produtos ao Estoque")
            st.info("Mapeie os produtos da Nota Fiscal com itens já existentes do seu estoque ou cadastre novos itens se necessário.")
            
            all_items_stock = st.session_state.df['Item'].tolist() if not st.session_state.df.empty else []
            options = all_items_stock + ["➕ [ Cadastrar como Novo Item ]"]
            
            for i, item in enumerate(xml_items):
                st.markdown(f"**Item {i+1}:** {item['nome']}")
                col_info, col_map = st.columns([1.2, 1.8])
                
                with col_info:
                    st.markdown(f"📋 **Qtd na Nota:** `{item['quantidade']}` {item['unidade']}\n\n💵 **Valor Unit.:** `R$ {item['valor_unitario']:.2f}`")
                
                with col_map:
                    # Pré-seleção inteligente baseada em semelhança de nome
                    default_index = 0
                    if all_items_stock:
                        for idx, stock_item in enumerate(all_items_stock):
                            if stock_item.lower() in item['nome'].lower() or item['nome'].lower() in stock_item.lower():
                                default_index = idx
                                break
                    
                    if not all_items_stock:
                        selected = st.selectbox("Mapear para:", ["➕ [ Cadastrar como Novo Item ]"], key=f"map_{i}")
                    else:
                        selected = st.selectbox("Mapear para:", options, index=default_index, key=f"map_{i}")
                        
                    st.session_state.mappings[i] = selected
                    
                    if selected == "➕ [ Cadastrar como Novo Item ]":
                        col_cat, col_min = st.columns(2)
                        with col_cat:
                            new_cat = st.selectbox("Categoria", ["Comida", "Bebida", "Brincadeira", "Outros"], key=f"cat_{i}")
                        with col_min:
                            new_min = st.number_input("Estoque Mínimo", min_value=0, step=1, value=10, key=f"min_{i}")
                        st.session_state.new_item_details[i] = {
                            'categoria': new_cat,
                            'estoque_minimo': new_min
                        }
                st.divider()
                
            if st.button("Confirmar Importação de Itens", type="primary", use_container_width=True):
                novos_cadastrados = 0
                entradas_registradas = 0
                
                for i, item in enumerate(xml_items):
                    mapped_to = st.session_state.mappings[i]
                    qty = item['quantidade']
                    
                    if mapped_to == "➕ [ Cadastrar como Novo Item ]":
                        # Cadastrar novo item
                        details = st.session_state.new_item_details[i]
                        novo_id = get_next_id(st.session_state.df, 'ID_Item')
                        nome_limpo = item['nome'].strip().title()
                        
                        novo_registro = pd.DataFrame([{
                            'ID_Item': novo_id,
                            'Item': nome_limpo,
                            'Categoria': details['categoria'],
                            'Quantidade': qty,
                            'Estoque Mínimo': details['estoque_minimo']
                        }])
                        
                        st.session_state.df = pd.concat([st.session_state.df, novo_registro], ignore_index=True)
                        log_movement(novo_id, nome_limpo, f"Entrada via XML NF-e {nNF}", qty, None, "-")
                        novos_cadastrados += 1
                    else:
                        # Associar a um item existente
                        idx_list = st.session_state.df[st.session_state.df['Item'] == mapped_to].index
                        if len(idx_list) > 0:
                            idx = idx_list[0]
                            id_item = st.session_state.df.at[idx, 'ID_Item']
                            st.session_state.df.at[idx, 'Quantidade'] += qty
                            log_movement(id_item, mapped_to, f"Entrada via XML NF-e {nNF}", qty, None, "-")
                            entradas_registradas += 1
                
                save_data(st.session_state.df)
                st.toast(f"Importação concluída! {entradas_registradas} atualizados e {novos_cadastrados} criados.", icon="✅")
                
                # Limpar estados de importação
                if 'nNF' in st.session_state: del st.session_state.nNF
                if 'xml_items' in st.session_state: del st.session_state.xml_items
                if 'last_uploaded_xml' in st.session_state: del st.session_state.last_uploaded_xml
                if 'mappings' in st.session_state: del st.session_state.mappings
                if 'new_item_details' in st.session_state: del st.session_state.new_item_details
                
                st.rerun()
                
        except Exception as e:
            st.error(f"Erro ao processar arquivo XML: {e}")
    else:
        st.info("💡 Envie o arquivo XML da Nota Fiscal (NF-e) acima para mapear e carregar as mercadorias automaticamente.")


with tab_estoque:
    st.subheader("📦 Posição Atual do Estoque")
    if st.session_state.df.empty:
        st.info("O estoque está vazio.")
    else:
        df_view = st.session_state.df[['Item', 'Categoria', 'Quantidade', 'Estoque Mínimo']]
        styled_df = df_view.style.apply(highlight_low_stock, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("📊 Gráficos e Indicadores")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Distribuição por Categoria**")
            df_cat = st.session_state.df.groupby("Categoria")['Quantidade'].sum().reset_index()
            st.bar_chart(df_cat, x="Categoria", y="Quantidade")
            
        with col2:
            st.markdown("**Níveis de Estoque (Top 10 Maiores)**")
            df_top = st.session_state.df.nlargest(10, 'Quantidade')
            st.bar_chart(df_top, x="Item", y="Quantidade")

with tab_historico:
    st.subheader("Últimas Movimentações")
    try:
        df_hist = pd.read_sql('SELECT * FROM historico ORDER BY "Data/Hora" DESC', engine)
        if df_hist.empty:
            st.info("Nenhuma movimentação registrada ainda.")
        else:
            df_hist_view = df_hist[['Data/Hora', 'Item', 'Movimento', 'Quantidade', 'Barraca']]
            st.dataframe(df_hist_view, use_container_width=True, hide_index=True)
    except Exception:
        st.info("Nenhuma movimentação registrada ainda.")
