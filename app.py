from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import os
import json
import subprocess
import zipfile
import io
import re
import shutil
import secrets
from datetime import datetime
from bot_manager import BotManager

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configurações
PROJETOS_DIR = 'projetos'
DATA_FILE = 'hospedagens.json'
os.makedirs(PROJETOS_DIR, exist_ok=True)

# Inicializar gerenciador
bot_manager = BotManager()

# Funções auxiliares
def carregar_dados():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def salvar_dados(dados):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def analisar_zip(zip_bytes):
    resultado = {
        'valido': False,
        'tamanho_mb': 0,
        'total_arquivos': 0,
        'erros': []
    }
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            nomes = zf.namelist()
            resultado['total_arquivos'] = len(nomes)
            resultado['tamanho_mb'] = sum(zf.getinfo(n).file_size for n in nomes) / (1024 * 1024)
            
            # Verificar se tem arquivo Python
            tem_py = any(n.endswith('.py') for n in nomes)
            if not tem_py:
                resultado['erros'].append("Nenhum arquivo .py encontrado no ZIP")
                return resultado
            
            resultado['valido'] = True
            
    except Exception as e:
        resultado['erros'].append(str(e))
    
    return resultado

# Rotas
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/projetos')
def api_projetos():
    dados = carregar_dados()
    projetos = []
    
    for usuario_id, info in dados.items():
        for projeto in info.get('projetos', []):
            status = 'offline'
            recursos = None
            
            if projeto.get('pid') and bot_manager.status_bot(projeto['pid']):
                status = 'online'
                recursos = bot_manager.obter_uso_recursos(projeto['pid'])
            
            projetos.append({
                'id': f"{usuario_id}_{projeto['nome']}",
                'usuario_id': usuario_id,
                'nome': projeto['nome'],
                'status': status,
                'tamanho': projeto.get('tamanho', 0),
                'cpu': recursos['cpu'] if recursos else 0,
                'mem': recursos['mem'] if recursos else 0,
                'pid': projeto.get('pid'),
                'criado': projeto.get('criado', '')
            })
    
    return jsonify({'projetos': projetos})

@app.route('/api/deploy', methods=['POST'])
def api_deploy():
    if 'arquivo' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    arquivo = request.files['arquivo']
    if not arquivo.filename.endswith('.zip'):
        return jsonify({'error': 'Envie apenas arquivos ZIP'}), 400
    
    nome_projeto = request.form.get('nome')
    if not nome_projeto:
        return jsonify({'error': 'Nome do projeto é obrigatório'}), 400
    
    # Limpar nome
    nome_projeto = re.sub(r'[^a-zA-Z0-9_-]', '', nome_projeto)[:50]
    if not nome_projeto:
        return jsonify({'error': 'Nome inválido'}), 400
    
    # Analisar ZIP
    zip_bytes = arquivo.read()
    analise = analisar_zip(zip_bytes)
    if not analise['valido']:
        return jsonify({'error': '\n'.join(analise['erros'])}), 400
    
    # Criar diretório
    usuario_id = "anonimo"
    caminho_projeto = os.path.join(PROJETOS_DIR, usuario_id, nome_projeto)
    
    if os.path.exists(caminho_projeto):
        shutil.rmtree(caminho_projeto)
    
    os.makedirs(caminho_projeto)
    
    # Extrair
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(caminho_projeto)
    
    # Salvar dados
    dados = carregar_dados()
    if usuario_id not in dados:
        dados[usuario_id] = {
            'usado_mb': 0,
            'projetos': []
        }
    
    dados[usuario_id]['projetos'].append({
        'nome': nome_projeto,
        'tamanho': analise['tamanho_mb'],
        'criado': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'pid': None,
        'caminho': caminho_projeto
    })
    
    dados[usuario_id]['usado_mb'] += analise['tamanho_mb']
    salvar_dados(dados)
    
    return jsonify({
        'success': True,
        'projeto': nome_projeto,
        'tamanho': analise['tamanho_mb']
    })

@app.route('/api/iniciar', methods=['POST'])
def api_iniciar():
    data = request.json
    projeto_id = data.get('projeto_id')
    
    if not projeto_id:
        return jsonify({'error': 'ID do projeto necessário'}), 400
    
    # Buscar projeto
    dados = carregar_dados()
    projeto_encontrado = None
    usuario_id_encontrado = None
    
    for usuario_id, info in dados.items():
        for projeto in info['projetos']:
            if f"{usuario_id}_{projeto['nome']}" == projeto_id:
                projeto_encontrado = projeto
                usuario_id_encontrado = usuario_id
                break
        if projeto_encontrado:
            break
    
    if not projeto_encontrado:
        return jsonify({'error': 'Projeto não encontrado'}), 404
    
    caminho = os.path.join(PROJETOS_DIR, usuario_id_encontrado, projeto_encontrado['nome'])
    pid, msg = bot_manager.iniciar_bot(usuario_id_encontrado, projeto_encontrado['nome'], caminho)
    
    if pid:
        projeto_encontrado['pid'] = pid
        salvar_dados(dados)
        
        socketio.emit('bot_iniciado', {
            'projeto_id': projeto_id,
            'pid': pid
        })
        
        return jsonify({'success': True, 'pid': pid})
    
    return jsonify({'error': msg}), 500

@app.route('/api/parar', methods=['POST'])
def api_parar():
    data = request.json
    pid = data.get('pid')
    
    if not pid:
        return jsonify({'error': 'PID necessário'}), 400
    
    ok, msg = bot_manager.parar_bot(pid)
    
    if ok:
        # Atualizar dados
        dados = carregar_dados()
        for usuario_id, info in dados.items():
            for projeto in info['projetos']:
                if projeto.get('pid') == pid:
                    projeto['pid'] = None
                    salvar_dados(dados)
                    break
        
        socketio.emit('bot_parado', {'pid': pid})
        return jsonify({'success': True})
    
    return jsonify({'error': msg}), 500

@app.route('/api/reiniciar', methods=['POST'])
def api_reiniciar():
    data = request.json
    pid = data.get('pid')
    
    if not pid:
        return jsonify({'error': 'PID necessário'}), 400
    
    ok, msg = bot_manager.reiniciar_bot(pid)
    
    if ok:
        return jsonify({'success': True})
    
    return jsonify({'error': msg}), 500

@app.route('/api/logs/<int:pid>')
def api_logs(pid):
    logs, erro = bot_manager.obter_logs(pid)
    
    if erro:
        return jsonify({'error': erro}), 500
    
    return jsonify({'logs': logs})

@app.route('/api/recursos/<int:pid>')
def api_recursos(pid):
    recursos = bot_manager.obter_uso_recursos(pid)
    
    if recursos:
        return jsonify(recursos)
    
    return jsonify({'status': 'offline'})

@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Conectado ao servidor'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)
