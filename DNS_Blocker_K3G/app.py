from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pdf_scan import extrair_terceiro_item_pdf, adicionar_resultado_em_txt
import os
from netmiko import ConnectHandler
from netmiko import file_transfer


def get_client_data(client_id):
    conn = sqlite3.connect('clientes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE id = ?", (client_id,))
    row = cursor.fetchone()
    colunas = [description[0] for description in cursor.description]
    conn.close()
    if row:
        data = dict(zip(colunas, row))
        # Ajuste o device_type conforme seu equipamento, exemplo: 'linux'
        data["device_type"] = "linux"
        data["global_delay_factor"] = 2
        return data
    return None


app = Flask(__name__)


@app.route('/')
def home():
    conn = sqlite3.connect('clientes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()
    colunas = [description[0] for description in cursor.description]
    conn.close()
    return render_template('home.html', clientes=clientes, colunas=colunas)


@app.route('/consultar-clientes')
def consultar_clientes():
    conn = sqlite3.connect('clientes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()
    colunas = [description[0] for description in cursor.description]
    conn.close()
    return render_template('consultar_clientes.html', clientes=clientes, colunas=colunas)


@app.route('/cadastrar-cliente', methods=['GET', 'POST'])
def cadastrar_cliente():
    msg = None
    if request.method == 'POST':
        cliente = request.form['cliente']
        host = request.form['host']
        username = request.form['username']
        password = request.form['password']
        port = request.form['port']
        senha_root = request.form['senha_root']
        conn = sqlite3.connect('clientes.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO clientes (cliente, host, username, password, port, senha_root) VALUES (?, ?, ?, ?, ?, ?)",
                       (cliente, host, username, password, port, senha_root))
        conn.commit()
        conn.close()
        msg = "Cliente cadastrado com sucesso!"
    return render_template('cadastrar_cliente.html', msg=msg)


@app.route('/excluir-cliente', methods=['GET', 'POST'])
def excluir_cliente():
    msg = None
    if request.method == 'POST':
        id_cliente = request.form['id']
        conn = sqlite3.connect('clientes.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clientes WHERE id = ?", (id_cliente,))
        if cursor.rowcount > 0:
            msg = f"Cliente com ID {id_cliente} excluído com sucesso!"
        else:
            msg = f"Nenhum cliente encontrado com ID {id_cliente}."
        conn.commit()
        conn.close()
    return render_template('excluir_cliente.html', msg=msg)


@app.route('/escanear-pdf', methods=['GET', 'POST'])
def escanear_pdf():
    msg = None
    if request.method == 'POST':
        if 'apagar_lista' in request.form:
            # Botão de apagar lista foi pressionado
            try:
                open('lista.txt', 'w', encoding='utf-8').close()
                msg = "A lista.txt foi apagada com sucesso!"
            except Exception as e:
                msg = f"Erro ao apagar lista.txt: {e}"
        else:
            if 'pdf_file' not in request.files:
                msg = "Nenhum arquivo enviado."
            else:
                pdf_file = request.files['pdf_file']
                if pdf_file.filename == '':
                    msg = "Nenhum arquivo selecionado."
                else:
                    caminho_pdf = os.path.join('uploads', pdf_file.filename)
                    os.makedirs('uploads', exist_ok=True)
                    pdf_file.save(caminho_pdf)
                    resultado = extrair_terceiro_item_pdf(caminho_pdf)
                    if resultado:
                        adicionar_resultado_em_txt(resultado, 'lista.txt')
                        msg = "PDF escaneado e dados adicionados à lista.txt com sucesso!"
                    else:
                        msg = "Nenhum dado extraído do PDF."
    # Lê o conteúdo da lista.txt para exibir na página
    conteudo_lista = ""
    try:
        with open('lista.txt', 'r', encoding='utf-8') as f:
            conteudo_lista = f.read()
    except Exception as e:
        conteudo_lista = f"Erro ao ler lista.txt: {e}"
    return render_template('escanear_pdf.html', msg=msg, conteudo_lista=conteudo_lista)


def adicionar_sites_bloqueados(local_file, lista_txt="lista.txt"):
    import os

    os.makedirs(os.path.dirname(local_file), exist_ok=True)

    if not os.path.exists(lista_txt):
        return "Arquivo lista.txt não encontrado."

    with open(lista_txt, "r", encoding="utf-8") as f:
        sites = [site.strip() for site in f if site.strip()]

    if not sites:
        return "Nenhum site para adicionar."

    # Carrega linhas já existentes para evitar duplicatas
    if os.path.exists(local_file):
        with open(local_file, "r", encoding="utf-8") as f:
            linhas_existentes = set(f.readlines())
    else:
        linhas_existentes = set()

    novas_linhas = []
    for site in sites:
        linha1 = f'local-zone: "{site}" static\n'
        linha2 = f'local-data: "{site} A 127.0.0.1"\n'
        if linha1 not in linhas_existentes:
            novas_linhas.append(linha1)
        if linha2 not in linhas_existentes:
            novas_linhas.append(linha2)

    if novas_linhas:
        with open(local_file, "a", encoding="utf-8") as f:
            f.writelines(novas_linhas)
        return "Sites adicionados ao arquivo sitesblock.conf com sucesso!"
    else:
        return "Nenhum site novo para adicionar."


@app.route('/conectar-cliente', methods=['GET', 'POST'])
def conectar_cliente():
    msg = None
    erro = None
    log = None
    bloqueio_realizado = None
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        acao = request.form.get('acao')
        sites_manuais = request.form.get('sites_manuais')
        try:
            client_id = int(client_id)
            device = get_client_data(client_id)
            if not device:
                erro = f"Cliente com ID {client_id} não encontrado."
            else:
                connection = ConnectHandler(
                    device_type=device["device_type"],
                    host=device["host"],
                    username=device["username"],
                    password=device["password"],
                    port=device["port"],
                    global_delay_factor=device["global_delay_factor"],
                    session_log="netmiko_session.log",
                )
                # Obter acesso root
                if client_id in [8, 9, 12]:
                    root = connection.send_command_timing("sudo -i")
                else:
                    root = connection.send_command_timing("su")
                    if "Password" in root:
                        root = connection.send_command_timing(
                            device["senha_root"])
                    else:
                        root = connection.send_command_timing(
                            device["senha_root"])
                output = connection.send_command("export LANG=C")
                msg = f"Conexão SSH realizada com sucesso para o cliente {device['cliente']}!"

                # Caminhos dos arquivos
                local_file = "sites_bloqueados/cliente/sitesblock.conf"
                remote_file = "/etc/unbound/unbound.conf.d/sitesblock.conf"
                tmp_remote_file = "/tmp/sitesblock.conf"

                # Baixar o arquivo remoto para o local antes de editar
                file_transfer(
                    connection,
                    source_file=remote_file,
                    dest_file=local_file,
                    file_system="/",
                    direction="get",
                    overwrite_file=True,
                )

                # Se o usuário escolheu bloquear manualmente
                if acao == "bloquear_manual" and sites_manuais:
                    # Salva os sites digitados no lista.txt
                    with open("lista.txt", "w", encoding="utf-8") as f:
                        for site in sites_manuais.splitlines():
                            if site.strip():
                                f.write(site.strip() + "\n")
                    bloqueio_realizado = adicionar_sites_bloqueados(local_file)
                # Se o usuário escolheu bloquear do lista.txt
                elif acao == "bloquear_lista":
                    bloqueio_realizado = adicionar_sites_bloqueados(local_file)

                # Se algum bloqueio foi realizado, transfere e aplica no host
                if bloqueio_realizado and "sucesso" in bloqueio_realizado.lower():
                    connection.send_command("export LANG=C")
                    transfer_result = file_transfer(
                        connection,
                        source_file=local_file,
                        dest_file=tmp_remote_file,
                        file_system="/",
                        direction="put",
                        disable_md5=False,
                        overwrite_file=True,
                    )
                    # Usando essa função para corrigir compatibilidade com o cliente SpeedNetworks (ou ambientes CentOS 7)
                    if client_id in [3]:
                        connection.send_command_timing("unalias cp")
                    # Comandos padrão em ambientes linux, haverá algumas exeções de outros hosts

                    connection.send_command_timing("clear")
                    connection.send_command_timing(
                        "cp /etc/unbound/unbound.conf.d/sitesblock.conf /etc/unbound/unbound.conf.d/sitesblock.conf.old")
                    connection.send_command_timing(
                        "cp /tmp/sitesblock.conf /etc/unbound/unbound.conf.d/")
                    connection.send_command_timing(
                        "sudo unbound-checkconf")
                    connection.send_command_timing(
                        "systemctl restart unbound")
                with open("netmiko_session.log", "r", encoding="utf-8") as f:
                    log = f.read()
                connection.disconnect()
        except Exception as e:
            erro = f"Erro: {e}"
    return render_template('conectar_cliente.html', msg=msg, erro=erro, log=log, bloqueio_realizado=bloqueio_realizado)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
