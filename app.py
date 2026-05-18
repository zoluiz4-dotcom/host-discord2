from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
import os
import json
import subprocess
import psutil
import signal
import threading
import time
from datetime import datetime
import zipfile
import io
import shutil
import re
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configurações
PROJETOS_DIR = 'projetos'
DATA_FILE = 'hospedagens.json'
os.makedirs(PROJETOS_DIR, exist_ok=True)

# Gerenciador de processos
class BotManager:
    def __init__(self):
        self.processos = {}
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_loop(self):
        while True:
            for pid, info in list(self.processos.items()):
                if info['processo'].poll() is not None:
                    # Bot caiu, tentar reiniciar
                    socketio.emit('bot_status', {
                        'nome': info['projeto'],
                        'status': 'offline',
                        'pid': pid
                    })
            time.sleep(5)
    
    def encontrar_arquivo_principal(self, caminho):
        """Encontra automaticamente o arquivo principal do bot"""
        arquivos_principais = ['bot.py', 'main.py', 'app.py', 'run.py', 'index.py', 'client.py']
        
        for raiz, dirs, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                if arquivo in arquivos_principais:
                    return os.path.join(raiz, arquivo)
                
                # Verificar se o arquivo tem código Discord
                if arquivo.endswith('.py'):
                    caminho_arquivo = os.path.join(raiz, arquivo)
                    try:
                        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                            conteudo = f.read()
                            if 'discord' in conteudo and ('commands.Bot' in conteudo or 'discord.Client' in conteudo):
                                return caminho_arquivo
                    except:
                        pass
        return None
    
    def instalar_dependencias(self, caminho_projeto):
        """Instala dependências do arquivo requirements.txt"""
        req_file = os.path.join(caminho_projeto, 'requirements.txt')
        if os.path.exists(req_file):
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req_file], 
                             capture_output=True, timeout=120)
                return True, "Dependências instaladas"
            except Exception as e:
                return False, str(e)
        return True, "Sem dependências"
    
    def iniciar_bot(self, usuario_id, projeto_nome, caminho):
        caminho_abs = os.path.abspath(caminho)
        
        # Encontrar arquivo principal
        arquivo_principal = self.encontrar_arquivo_principal(caminho_abs)
        if not arquivo_principal:
            return None, "Arquivo principal não encontrado (bot.py, main.py, etc)"
        
        try:
            # Criar ambiente virtual
            venv_path = os.path.join(caminho_abs, 'venv')
            if not os.path.exists(venv_path):
                subprocess.run([sys.executable, '-m', 'venv', venv_path], 
                             capture_output=True, timeout=60)
            
            # Setup do ambiente
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
                pip_exe = os.path.join(venv_path, 'Scripts', 'pip.exe')
            else:
                python_exe = os.path.join(venv_path, 'bin', 'python')
                pip_exe = os.path.join(venv_path, 'bin', 'pip')
            
            # Instalar discord.py
            subprocess.run([pip_exe, 'install', 'discord.py', '--quiet'], 
                         capture_output=True, timeout=60)
            
            # Instalar outras dependências
            req_file = os.path.join(caminho_abs, 'requirements.txt')
            if os.path.exists(req_file):
                subprocess.run([pip_exe, 'install', '-r', req_file, '--quiet'],
                             capture_output=True, timeout=180)
            
            # Arquivo de log
            log_path = os.path.join(caminho_abs, 'bot.log')
            log_file = open(log_path, 'a', encoding='utf-8')
            log_file.write(f'\n--- Iniciado em {datetime.now()} ---\n')
            log_file.flush()
            
            # Iniciar processo
            proc = subprocess.Popen(
                [python_exe, arquivo_principal],
                stdout=log_file,
                stderr=log_file,
                cwd=caminho_abs,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            self.processos[proc.pid] = {
                'pid': proc.pid,
                'usuario_id': usuario_id,
                'projeto': projeto_nome,
                'processo': proc,
                'log_path': log_path,
                'log_file': log_file,
                'started_at': datetime.now().timestamp(),
                'caminho': caminho_abs
            }
            
            return proc.pid, "Bot iniciado com sucesso"
            
        except Exception as e:
            return None, str(e)
    
    def parar_bot(self, pid):
        if pid not in self.processos:
            return False, "Processo não encontrado"
        
        try:
            info = self.processos[pid]
            proc = info['processo']
            
            # Tentar matar o processo e seus filhos
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except:
                    pass
            
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()
            
            try:
                info['log_file'].close()
            except:
                pass
            
            del self.processos[pid]
            return True, "Bot parado"
            
        except Exception as e:
            return False, str(e)
    
    def reiniciar_bot(self, pid):
        if pid not in self.processos:
            return False, "Processo não encontrado"
        
        info = self.processos[pid]
        nome_projeto = info['projeto']
        usuario_id = info['usuario_id']
        caminho = info['caminho']
        
        # Parar
        self.parar_bot(pid)
        time.sleep(2)
        
        # Iniciar novamente
        novo_pid, msg = self.iniciar_bot(usuario_id, nome_projeto, caminho)
        return novo_pid is not None, msg
    
    def status_bot(self, pid):
        if pid not in self.processos:
            return False
        proc = self.processos[pid]['processo']
        return proc.poll() is None
    
    def obter_logs(self, pid, linhas=100):
        if pid not in self.processos:
            return None, "Processo não encontrado"
        
        try:
            log_path = self.processos[pid]['log_path']
            if not os.path.exists(log_path):
                return "Sem logs ainda", None
            
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                linhas_log = f.readlines()
                ultimas_linhas = linhas_log[-linhas:]
                return ''.join(ultimas_linhas), None
                
        except Exception as e:
            return None, str(e)
    
    def obter_uso_recursos(self, pid):
        if pid not in self.processos:
            return None
        
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=0.5)
            mem = proc.memory_info().rss / (1024 * 1024)
            
            # Pega filhos também
            filhos = proc.children(recursive=True)
            for filho in filhos:
                cpu += filho.cpu_percent(interval=0.1)
                mem += filho.memory_info().rss / (1024 * 1024)
            
            return {
                'cpu': round(min(cpu, 100), 1),
                'mem': round(mem, 1),
                'status': 'online' if proc.is_running() else 'offline'
            }
        except:
            return None

bot_manager = BotManager()

# Utilitários
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
        'arquivo_principal': None,
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
                resultado['erros'].append("Nenhum arquivo .py encontrado")
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
    
    # Limpar nome do projeto
    nome_projeto = re.sub(r'[^a-zA-Z0-9_-]', '', nome_projeto)
    if not nome_projeto:
        return jsonify({'error': 'Nome inválido'}), 400
    
    # Salvar arquivo temporário
    zip_bytes = arquivo.read()
    
    # Analisar ZIP
    analise = analisar_zip(zip_bytes)
    if not analise['valido']:
        return jsonify({'error': '\n'.join(analise['erros'])}), 400
    
    # Criar diretório do projeto
    usuario_id = "anonimo"
    caminho_projeto = os.path.join(PROJETOS_DIR, usuario_id, nome_projeto)
    
    if os.path.exists(caminho_projeto):
        shutil.rmtree(caminho_projeto)
    
    os.makedirs(caminho_projeto)
    
    # Extrair arquivos
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
    import sys
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)
