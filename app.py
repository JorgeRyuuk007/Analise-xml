# app.py - Versão Web do Analisador NFe para Render/Streamlit
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import os
import tempfile
import zipfile
from datetime import datetime
from io import BytesIO
import base64

# Configuração da página
st.set_page_config(
    page_title="Analisador NFe SEFAZ",
    page_icon="📊",
    layout="wide"
)

class NFeAnalyzer:
    def __init__(self):
        self.ncm_database = {}
        self.sefaz_autorizadas = {}
        self.sefaz_canceladas = {}
        self.sefaz_denegadas = {}
        self.sefaz_entrada = {}
        self.xmls_database = {}
        self.processed_data = []
        self.excluded_data = []
        self.xmls_nao_encontrados = []
        
    def load_ncm_database(self, excel_file):
        """Carrega a base de dados de NCMs do arquivo Excel"""
        try:
            df = pd.read_excel(excel_file, sheet_name=0, header=1)
            if len(df) < 10:  # Tentar header=0 se poucos dados
                df = pd.read_excel(excel_file, sheet_name=0, header=0)
            
            # Identificar colunas
            ncm_col = None
            class_col = None
            
            for col in df.columns:
                if 'NCM' in str(col).upper():
                    ncm_col = col
                    break
            
            for col in df.columns:
                if any(term in str(col).upper() for term in ['MONOFASICO', 'MONOFÁSICO', 'PIS', 'COFINS']):
                    class_col = col
                    break
            
            if not ncm_col or not class_col:
                ncm_col = 0
                class_col = 4
            
            count_monofasico = 0
            count_tributado = 0
            
            for index, row in df.iterrows():
                try:
                    if isinstance(ncm_col, int):
                        ncm_value = row.iloc[ncm_col] if len(row) > ncm_col else None
                        class_value = row.iloc[class_col] if len(row) > class_col else None
                    else:
                        ncm_value = row[ncm_col] if ncm_col in row else None
                        class_value = row[class_col] if class_col in row else None
                    
                    if pd.notna(ncm_value) and pd.notna(class_value):
                        if isinstance(ncm_value, (int, float)):
                            ncm = str(int(ncm_value)).zfill(8)
                        else:
                            ncm = str(ncm_value).replace('.', '').replace('-', '').strip().zfill(8)
                        
                        classificacao = str(class_value).strip()
                        self.ncm_database[ncm] = classificacao
                        
                        if 'monofasico' in classificacao.lower() or 'monofásico' in classificacao.lower():
                            count_monofasico += 1
                        elif 'tributado' in classificacao.lower():
                            count_tributado += 1
                        
                except:
                    continue
            
            return True, len(self.ncm_database), count_monofasico, count_tributado
            
        except Exception as e:
            return False, str(e), 0, 0
    
    def load_sefaz_database(self, csv_file):
        """Carrega e categoriza todas as notas da SEFAZ"""
        try:
            # Tentar diferentes separadores
            df = None
            for sep in [',', ';', '\t']:
                try:
                    df = pd.read_csv(csv_file, sep=sep)
                    if len(df.columns) > 5:
                        break
                except:
                    csv_file.seek(0)  # Reset file pointer
                    continue
            
            if df is None or len(df.columns) < 2:
                # Tentar com encoding diferente
                csv_file.seek(0)
                df = pd.read_csv(csv_file, encoding='latin-1')
            
            # Identificar colunas
            chave_col = None
            situacao_col = None
            tipo_op_col = None
            valor_col = None
            
            for col in df.columns:
                col_clean = str(col).upper().replace(' ', '')
                if 'CHAVE' in col_clean and 'ACESSO' in col_clean:
                    chave_col = col
                elif 'SITUACAO' in col_clean or 'SITUAÇÃO' in col_clean:
                    situacao_col = col
                elif 'TIPO' in col_clean and 'OPERACAO' in col_clean:
                    tipo_op_col = col
                elif 'VALOR' in col_clean:
                    valor_col = col
            
            if not chave_col or not situacao_col:
                return False, "Colunas essenciais não encontradas!", 0, 0, 0, 0
            
            # Contadores
            count_autorizadas_saida = 0
            count_canceladas = 0
            count_denegadas = 0
            count_entrada = 0
            
            valor_autorizadas = 0
            valor_canceladas = 0
            valor_denegadas = 0
            valor_entrada = 0
            
            # Processar cada linha
            for index, row in df.iterrows():
                try:
                    chave = str(row[chave_col]).strip() if pd.notna(row[chave_col]) else ''
                    situacao = str(row[situacao_col]).strip() if pd.notna(row[situacao_col]) else ''
                    tipo_op = str(row[tipo_op_col]).strip() if tipo_op_col and pd.notna(row[tipo_op_col]) else 'Saida'
                    
                    # Extrair valor
                    valor = 0
                    if valor_col and pd.notna(row[valor_col]):
                        try:
                            valor_str = str(row[valor_col]).replace('R$', '').replace('.', '').replace(',', '.').strip()
                            valor = float(valor_str)
                        except:
                            valor = 0
                    
                    # Limpar chave
                    chave_limpa = ''.join(c for c in chave if c.isdigit())
                    
                    if len(chave_limpa) == 44:
                        dados = {
                            'chave': chave_limpa,
                            'situacao': situacao,
                            'tipo_operacao': tipo_op,
                            'valor': valor
                        }
                        
                        situacao_upper = situacao.upper()
                        tipo_upper = tipo_op.upper()
                        
                        if 'AUTORIZADA' in situacao_upper:
                            if 'SAIDA' in tipo_upper or 'SAÍDA' in tipo_upper:
                                self.sefaz_autorizadas[chave_limpa] = dados
                                count_autorizadas_saida += 1
                                valor_autorizadas += valor
                            else:
                                self.sefaz_entrada[chave_limpa] = dados
                                count_entrada += 1
                                valor_entrada += valor
                        elif 'CANCELADA' in situacao_upper:
                            self.sefaz_canceladas[chave_limpa] = dados
                            count_canceladas += 1
                            valor_canceladas += valor
                        elif 'DENEGADA' in situacao_upper:
                            self.sefaz_denegadas[chave_limpa] = dados
                            count_denegadas += 1
                            valor_denegadas += valor
                            
                except:
                    continue
            
            return True, count_autorizadas_saida, valor_autorizadas, count_canceladas, valor_canceladas, count_entrada, valor_entrada
            
        except Exception as e:
            return False, str(e), 0, 0, 0, 0
    
    def process_xml_files(self, xml_files):
        """Processa lista de arquivos XML"""
        xmls_processados = 0
        
        for xml_file in xml_files:
            try:
                content = xml_file.read()
                chave = self.extract_chave_from_xml_content(content)
                
                if chave and len(chave) == 44:
                    self.xmls_database[chave] = content
                    xmls_processados += 1
            except:
                continue
        
        return xmls_processados
    
    def extract_chave_from_xml_content(self, xml_content):
        """Extrai chave de conteúdo XML"""
        try:
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8', errors='ignore')
            
            root = ET.fromstring(xml_content)
            
            # Procurar chave
            for elem in root.iter():
                if elem.tag.endswith('}infNFe') or elem.tag == 'infNFe':
                    id_attr = elem.get('Id', '')
                    if id_attr.startswith('NFe'):
                        chave = id_attr[3:]
                        return ''.join(c for c in chave if c.isdigit())
                    elif len(id_attr) == 44:
                        return ''.join(c for c in id_attr if c.isdigit())
            
            # Procurar por chNFe
            for elem in root.iter():
                if elem.tag.endswith('}chNFe') or elem.tag == 'chNFe':
                    chave = elem.text.strip() if elem.text else ''
                    return ''.join(c for c in chave if c.isdigit())
            
            return None
            
        except:
            return None
    
    def classify_product(self, ncm):
        """Classifica produto por NCM"""
        if not ncm:
            return 'Indefinido'
        
        clean_ncm = str(ncm).replace('.', '').replace('-', '').strip().zfill(8)
        
        if clean_ncm in self.ncm_database:
            classificacao = self.ncm_database[clean_ncm]
            
            if 'monofasico' in classificacao.lower() or 'monofásico' in classificacao.lower():
                return 'Monofásico'
            elif 'tributado' in classificacao.lower():
                return 'Tributado'
            else:
                return classificacao
        
        return 'Indefinido'
    
    def extract_products_from_xml(self, xml_content):
        """Extrai produtos de XML"""
        try:
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8', errors='ignore')
            
            root = ET.fromstring(xml_content)
            
            def remove_namespace(tag):
                return tag.split('}')[-1] if '}' in tag else tag
            
            def find_element_text(parent, tag_name):
                for elem in parent.iter():
                    if remove_namespace(elem.tag) == tag_name:
                        return elem.text.strip() if elem.text else ''
                return ''
            
            def find_element_float(parent, tag_name):
                text = find_element_text(parent, tag_name)
                try:
                    return float(text) if text else 0.0
                except:
                    return 0.0
            
            produtos = []
            for elem in root.iter():
                if remove_namespace(elem.tag) == 'det':
                    prod_element = None
                    
                    for sub_elem in elem.iter():
                        if remove_namespace(sub_elem.tag) == 'prod':
                            prod_element = sub_elem
                            break
                    
                    if prod_element is not None:
                        ncm = find_element_text(prod_element, 'NCM')
                        descricao = find_element_text(prod_element, 'xProd')
                        quantidade = find_element_float(prod_element, 'qCom')
                        valor_unitario = find_element_float(prod_element, 'vUnCom')
                        valor_produto = find_element_float(prod_element, 'vProd')
                        unidade = find_element_text(prod_element, 'uCom')
                        cfop = find_element_text(prod_element, 'CFOP')
                        
                        if ncm and valor_produto > 0:
                            classificacao = self.classify_product(ncm)
                            
                            produtos.append({
                                'ncm': ncm,
                                'descricao': descricao or 'Produto sem descrição',
                                'classificacao': classificacao,
                                'quantidade': quantidade,
                                'valor_unitario': valor_unitario,
                                'valor_produto_xml': valor_produto,
                                'unidade': unidade or 'UN',
                                'cfop': cfop or ''
                            })
            
            return produtos
            
        except:
            return []
    
    def process_analysis(self):
        """Processa análise baseada na SEFAZ"""
        self.processed_data = []
        self.xmls_nao_encontrados = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_items = len(self.sefaz_autorizadas)
        processed = 0
        
        for chave, dados_sefaz in self.sefaz_autorizadas.items():
            if chave in self.xmls_database:
                xml_content = self.xmls_database[chave]
                produtos = self.extract_products_from_xml(xml_content)
                
                if produtos:
                    valor_nota_sefaz = dados_sefaz['valor']
                    num_produtos = len(produtos)
                    valor_por_produto = valor_nota_sefaz / num_produtos if num_produtos > 0 else 0
                    
                    for produto in produtos:
                        produto.update({
                            'chave_nfe': chave,
                            'valor_nota_sefaz': valor_nota_sefaz,
                            'valor_produto_proporcional': valor_por_produto,
                            'status': 'Autorizada + Saída'
                        })
                        self.processed_data.append(produto)
            else:
                self.xmls_nao_encontrados.append({
                    'chave': chave,
                    'valor': dados_sefaz['valor'],
                    'situacao': dados_sefaz['situacao'],
                    'motivo': 'XML não encontrado'
                })
            
            processed += 1
            progress_bar.progress(processed / total_items)
            status_text.text(f"Processando... {processed}/{total_items}")
        
        progress_bar.empty()
        status_text.empty()
        
        return len(self.processed_data), len(self.xmls_nao_encontrados)
    
    def generate_detailed_excel(self):
        """Gera Excel detalhado com formatação"""
        if not self.processed_data:
            return None
        
        # Preparar dados
        export_data = []
        for item in self.processed_data:
            export_data.append({
                'Nome do Produto': item['descricao'],
                'Valor Total': item['valor_produto_proporcional'],
                'NCM': item['ncm'],
                'Classificação': item['classificacao'],
                'Quantidade': item['quantidade'],
                'Valor Unitário': item['valor_unitario'],
                'Nota Fiscal': f"NFe_{item['chave_nfe']}",
                'CFOP': item.get('cfop', ''),
                'Unidade': item.get('unidade', 'UN'),
                'Observações': f"Encontrado na base oficial - {item['status']}"
            })
        
        # Criar Excel em memória
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df = pd.DataFrame(export_data)
            df.to_excel(writer, sheet_name='Análise Detalhada', index=False)
            
            # Formatação
            workbook = writer.book
            worksheet = writer.sheets['Análise Detalhada']
            
            # Formatos
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'center',
                'align': 'center',
                'bg_color': '#366092',
                'font_color': 'white',
                'border': 1
            })
            
            money_format = workbook.add_format({
                'num_format': 'R$ #,##0.00',
                'border': 1
            })
            
            # Aplicar formatação
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Largura das colunas
            worksheet.set_column('A:A', 50)
            worksheet.set_column('B:B', 15)
            worksheet.set_column('C:C', 10)
            worksheet.set_column('D:D', 15)
            worksheet.set_column('E:E', 12)
            worksheet.set_column('F:F', 15)
            worksheet.set_column('G:G', 45)
            worksheet.set_column('H:H', 8)
            worksheet.set_column('I:I', 10)
            worksheet.set_column('J:J', 40)
            
            # Adicionar resumo
            self.add_summary_sheet(writer)
        
        output.seek(0)
        return output
    
    def add_summary_sheet(self, writer):
        """Adiciona planilha de resumo"""
        summary_data = {
            'Categoria': [],
            'Quantidade': [],
            'Valor Total': [],
            'Percentual': []
        }
        
        valor_total = sum(item['valor_produto_proporcional'] for item in self.processed_data)
        
        for classificacao in ['Monofásico', 'Tributado', 'Indefinido']:
            itens = [item for item in self.processed_data if item['classificacao'] == classificacao]
            if itens:
                valor = sum(item['valor_produto_proporcional'] for item in itens)
                summary_data['Categoria'].append(classificacao)
                summary_data['Quantidade'].append(len(itens))
                summary_data['Valor Total'].append(valor)
                summary_data['Percentual'].append((valor / valor_total * 100) if valor_total > 0 else 0)
        
        summary_data['Categoria'].append('TOTAL GERAL')
        summary_data['Quantidade'].append(len(self.processed_data))
        summary_data['Valor Total'].append(valor_total)
        summary_data['Percentual'].append(100.0)
        
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Resumo', index=False)

# Interface Streamlit
def main():
    st.title("🐍 Sistema de Análise NFe - SEFAZ")
    st.markdown("### 🎯 Análise baseada em valores SEFAZ + produtos dos XMLs")
    
    # Sidebar para instruções
    with st.sidebar:
        st.header("📋 Instruções")
        st.markdown("""
        1. **Base NCM**: Excel com NCMs e classificação tributária
        2. **SEFAZ**: CSV com dados das notas fiscais
        3. **XMLs**: Arquivos XML das notas (múltiplos)
        
        O sistema irá:
        - ✅ Usar valores da SEFAZ
        - 📊 Classificar por NCM (Monofásico/Tributado)
        - 📥 Gerar relatório detalhado
        """)
    
    # Inicializar analyzer
    if 'analyzer' not in st.session_state:
        st.session_state.analyzer = NFeAnalyzer()
    
    analyzer = st.session_state.analyzer
    
    # Upload de arquivos
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 Base NCM")
        ncm_file = st.file_uploader("Selecione o Excel", type=['xlsx', 'xls'], key='ncm')
        
        if ncm_file:
            result = analyzer.load_ncm_database(ncm_file)
            if result[0]:
                st.success(f"✅ {result[1]} NCMs carregados")
                st.info(f"Monofásicos: {result[2]} | Tributados: {result[3]}")
            else:
                st.error(f"❌ Erro: {result[1]}")
    
    with col2:
        st.markdown("### 📋 Base SEFAZ")
        sefaz_file = st.file_uploader("Selecione o CSV", type=['csv'], key='sefaz')
        
        if sefaz_file:
            result = analyzer.load_sefaz_database(sefaz_file)
            if result[0]:
                st.success(f"✅ {result[1]} notas autorizadas")
                st.info(f"Valor total: R$ {result[2]:,.2f}")
            else:
                st.error(f"❌ Erro: {result[1]}")
    
    with col3:
        st.markdown("### 📁 XMLs NFe")
        xml_files = st.file_uploader("Selecione os XMLs", type=['xml'], accept_multiple_files=True, key='xmls')
        
        if xml_files:
            xmls_count = analyzer.process_xml_files(xml_files)
            st.success(f"✅ {xmls_count} XMLs processados")
    
    # Botão processar
    if st.button("🎯 Processar Análise", type="primary", use_container_width=True):
        if not analyzer.ncm_database:
            st.error("❌ Carregue a base NCM primeiro!")
        elif not analyzer.sefaz_autorizadas:
            st.error("❌ Carregue a base SEFAZ primeiro!")
        elif not analyzer.xmls_database:
            st.error("❌ Carregue os XMLs primeiro!")
        else:
            with st.spinner("Processando..."):
                produtos_count, xmls_nao_encontrados = analyzer.process_analysis()
                
            st.success(f"✅ Análise concluída! {produtos_count} produtos processados")
            
            if xmls_nao_encontrados > 0:
                st.warning(f"⚠️ {xmls_nao_encontrados} XMLs não encontrados")
            
            # Resultados
            if analyzer.processed_data:
                st.markdown("---")
                st.markdown("## 📊 Resultados")
                
                # Métricas principais
                valor_total = sum(item['valor_produto_proporcional'] for item in analyzer.processed_data)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("💰 Valor Total", f"R$ {valor_total:,.2f}")
                with col2:
                    st.metric("📦 Total Produtos", len(analyzer.processed_data))
                
                # Separar por classificação
                monofasicos = [p for p in analyzer.processed_data if p['classificacao'] == 'Monofásico']
                tributados = [p for p in analyzer.processed_data if p['classificacao'] == 'Tributado']
                indefinidos = [p for p in analyzer.processed_data if p['classificacao'] == 'Indefinido']
                
                valor_monofasico = sum(p['valor_produto_proporcional'] for p in monofasicos)
                valor_tributado = sum(p['valor_produto_proporcional'] for p in tributados)
                valor_indefinido = sum(p['valor_produto_proporcional'] for p in indefinidos)
                
                with col3:
                    st.metric("💚 Monofásico", 
                             f"R$ {valor_monofasico:,.2f}", 
                             f"{len(monofasicos)} itens")
                with col4:
                    st.metric("🔴 Tributado", 
                             f"R$ {valor_tributado:,.2f}",
                             f"{len(tributados)} itens")
                
                # Gráfico de pizza
                st.markdown("### 📊 Distribuição por Classificação")
                
                import plotly.express as px
                
                df_pie = pd.DataFrame({
                    'Classificação': ['Monofásico', 'Tributado', 'Indefinido'],
                    'Valor': [valor_monofasico, valor_tributado, valor_indefinido]
                })
                df_pie = df_pie[df_pie['Valor'] > 0]
                
                fig = px.pie(df_pie, values='Valor', names='Classificação', 
                           color_discrete_map={'Monofásico': '#00CC00', 
                                             'Tributado': '#FF4444',
                                             'Indefinido': '#CCCCCC'})
                st.plotly_chart(fig)
                
                # Preview dos dados
                st.markdown("### 📋 Preview dos Dados")
                df_preview = pd.DataFrame(analyzer.processed_data[:10])
                st.dataframe(df_preview[['descricao', 'ncm', 'classificacao', 'valor_produto_proporcional']])
                
                # Download
                st.markdown("### 📥 Exportar Resultados")
                
                excel_file = analyzer.generate_detailed_excel()
                if excel_file:
                    st.download_button(
                        label="📥 Baixar Análise Detalhada (Excel)",
                        data=excel_file,
                        file_name=f"analise_detalhada_nfe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

if __name__ == "__main__":
    main()
