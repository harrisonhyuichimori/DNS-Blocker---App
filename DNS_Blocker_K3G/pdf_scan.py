import pdfplumber
import os


def extrair_terceiro_item_pdf(pdf_path):
    try:
        terceiro_item_extraido = []
        with pdfplumber.open(pdf_path) as pdf:
            for pagina in pdf.pages:
                tabelas = pagina.extract_tables()
                if tabelas:
                    for tabela in tabelas:
                        for linha in tabela:
                            if len(linha) >= 3:  # Verifica se há pelo menos 3 colunas
                                terceiro_item_extraido.append(
                                    linha[2])  # Adiciona o terceiro item
        return terceiro_item_extraido
    except Exception as e:
        print(f"Erro ao processar o PDF: {e}")
        return []


def adicionar_resultado_em_txt(resultado, caminho_txt):
    try:
        # Verifica se o arquivo já existe e não está vazio
        precisa_pular_linha = os.path.exists(
            caminho_txt) and os.path.getsize(caminho_txt) > 0

        with open(caminho_txt, "a", encoding="utf-8") as arquivo:
            if precisa_pular_linha:
                # Adiciona uma quebra de linha antes do primeiro item
                arquivo.write("\n")
            # Ignora o primeiro item (índice 0)
            for i, item in enumerate(resultado[1:]):
                if item.strip():  # Verifica se o item não está vazio ou em branco
                    arquivo.write(f"{item}\n")
        print(f"Resultado adicionado ao arquivo: {caminho_txt}")
    except Exception as e:
        print(f"Erro ao salvar o arquivo: {e}")
