from flask import Flask, render_template, request, redirect
import os
import json
import zipfile

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
PROJETOS_FOLDER = "projetos"
DADOS_FILE = "dados.json"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROJETOS_FOLDER, exist_ok=True)

def carregar_dados():

    if not os.path.exists(DADOS_FILE):

        with open(DADOS_FILE, "w") as f:
            json.dump([], f)

    with open(DADOS_FILE, "r") as f:
        return json.load(f)

def salvar_dados(dados):

    with open(DADOS_FILE, "w") as f:
        json.dump(dados, f, indent=4)

@app.route("/")
def index():

    bots = carregar_dados()

    return render_template(
        "index.html",
        bots=bots
    )

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if request.method == "POST":

        arquivo = request.files.get("file")

        if arquivo:

            caminho_zip = os.path.join(
                UPLOAD_FOLDER,
                arquivo.filename
            )

            arquivo.save(caminho_zip)

            nome_bot = arquivo.filename.replace(".zip", "")

            pasta_bot = os.path.join(
                PROJETOS_FOLDER,
                nome_bot
            )

            os.makedirs(pasta_bot, exist_ok=True)

            with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
                zip_ref.extractall(pasta_bot)

            dados = carregar_dados()

            dados.append({
                "nome": nome_bot,
                "arquivo": arquivo.filename,
                "status": "OFFLINE"
            })

            salvar_dados(dados)

            return redirect("/")

    return render_template("upload.html")

@app.route("/start/<nome>")
def start(nome):

    dados = carregar_dados()

    for bot in dados:

        if bot["nome"] == nome:
            bot["status"] = "ONLINE"

    salvar_dados(dados)

    return redirect("/")

@app.route("/stop/<nome>")
def stop(nome):

    dados = carregar_dados()

    for bot in dados:

        if bot["nome"] == nome:
            bot["status"] = "OFFLINE"

    salvar_dados(dados)

    return redirect("/")

@app.route("/painel")
def painel():

    bots = carregar_dados()

    return render_template(
        "painel.html",
        bots=bots
    )

@app.route("/admin")
def admin():

    bots = carregar_dados()

    return render_template(
        "admin.html",
        bots=bots
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
