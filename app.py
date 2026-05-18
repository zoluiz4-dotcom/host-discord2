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
import time
import psutil
import signal
import threading
from datetime import datetime
from pathlib import Path

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
        self.logs_cache = {}
    
    def encontrar_arquivo_principal(self, caminho):
        """Encontra automaticamente o arquivo principal do bot"""
        arquivos_principais = ['bot.py', 'main.py', 'app.py', 'run.py', 'index.py', 'client.py', 'discord_bot.py']
        
        for raiz, dirs, arquivos in os.walk(caminho):
            # Pular venv
            if 'venv' in dirs:
                dirs.remove('venv')
            
            for arquivo in arquivos:
                if arquivo in arquivos_principais:
                    return os.path.join(raiz, arquivo)
                
                if arquivo.endswith('.py') and arquivo != 'requirements.txt':
                    caminho_arquivo = os.path.join(raiz, arquivo)
                    try:
                        with open(caminho_arquivo, 'r', encoding='utf-8', errors='ignore') as f:
                            conteudo = f.read()
                            if 'discord' in conteudo and ('commands.Bot' in conteudo or 'discord.Client' in conteudo or 'Client' in conteudo):
                                return caminho_arquivo
                    except:
                        pass
        return None
    
    def instalar_dependencias(self, caminho_projeto, venv_path):
        """Instala dependências"""
        req_file = os.path.join(caminho_projeto, 'requirements.txt')
        if not os.path.exists(req_file):
            return True, "Sem dependências"
        
        try:
            if os.name == 'nt':
                pip_exe = os.path.join(venv_path, 'Scripts', 'pip.exe')
            else:
                pip_exe = os.path.join(venv_path, 'bin', 'pip')
            
            # Instalar pacotes básicos primeiro
            subprocess.run([pip_exe, 'install', '--upgrade', 'pip'], capture_output=True, timeout=60)
            subprocess.run([pip_exe, 'install', 'discord.py', 'asyncio'], capture_output=True, timeout=120)
            
            # Instalar requirements
            resultado = subprocess.run(
                [pip_exe, 'install', '-r', req_file],
                capture_output=True,
                timeout=300,
                text=True
            )
            
            if resultado.returncode == 0:
                return True, "Dependências instaladas"
            else:
                return False, resultado.stderr[:200]
                
        except Exception as e:
            return False, str(e)
    
    def iniciar_bot(self, projeto_id, projeto_nome, caminho):
        """Inicia um bot"""
        caminho_abs = os.path.abspath(caminho)
        
        # Encontrar arquivo principal
        arquivo_principal = self.encontrar_arquivo_principal(caminho_abs)
        if not arquivo_principal:
            return None, "❌ Arquivo principal não encontrado!\nCertifique-se de ter: bot.py, main.py ou app.py"
        
        try:
            # Criar ambiente virtual
            venv_path = os.path.join(caminho_abs, 'venv')
            if not os.path.exists(venv_path):
                processo = subprocess.run(
                    [sys.executable, '-m', 'venv', venv_path],
                    capture_output=True,
                    timeout=120
                )
                if processo.returncode != 0:
                    return None, f"Erro ao criar venv: {processo.stderr.decode()[:200]}"
            
            # Configurar executáveis
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
            else:
                python_exe = os.path.join(venv_path, 'bin', 'python')
            
            # Instalar dependências
            self.instalar_dependencias(caminho_abs, venv_path)
            
            # Criar arquivo de log
            log_path = os.path.join(caminho_abs, 'bot.log')
            log_file = open(log_path, 'a', encoding='utf-8')
            log_file.write(f'\n{"="*60}\n')
            log_file.write(f'🚀 BOT INICIADO: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n')
            log_file.write(f'📁 Projeto: {projeto_nome}\n')
            log_file.write(f'📄 Arquivo: {os.path.basename(arquivo_principal)}\n')
            log_file.write(f'{"="*60}\n\n')
            log_file.flush()
            
            # Iniciar processo
            if hasattr(os, 'setsid'):
                proc = subprocess.Popen(
                    [python_exe, arquivo_principal],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=caminho_abs,
                    preexec_fn=os.setsid,
                    text=True
                )
            else:
                proc = subprocess.Popen(
                    [python_exe, arquivo_principal],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=caminho_abs,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    text=True
                )
            
            self.processos[proc.pid] = {
                'pid': proc.pid,
                'projeto_id': projeto_id,
                'projeto_nome': projeto_nome,
                'processo': proc,
                'log_path': log_path,
                'log_file': log_file,
                'started_at': datetime.now().timestamp(),
                'caminho': caminho_abs,
                'arquivo_principal': arquivo_principal
            }
            
            return proc.pid, f"✅ Bot iniciado com sucesso! (PID: {proc.pid})"
            
        except Exception as e:
            return None, f"❌ Erro: {str(e)}"
    
    def parar_bot(self, pid):
        """Para um bot"""
        if pid not in self.processos:
            return False, "Processo não encontrado"
        
        try:
            info = self.processos[pid]
            proc = info['processo']
            
            # Tentar matar graciosamente
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except:
                    pass
            
            proc.terminate()
            
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            # Registrar log
            try:
                info['log_file'].write(f'\n🛑 BOT PARADO: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n')
                info['log_file'].close()
            except:
                pass
            
            del self.processos[pid]
            return True, "Bot parado com sucesso"
            
        except Exception as e:
            return False, f"Erro: {str(e)}"
    
    def status_bot(self, pid):
        if pid not in self.processos:
            return False
        try:
            return self.processos[pid]['processo'].poll() is None
        except:
            return False
    
    def obter_logs(self, pid, linhas=200):
        if pid not in self.processos:
            return None, "Processo não encontrado"
        
        try:
            log_path = self.processos[pid]['log_path']
            if not os.path.exists(log_path):
                return "⏳ Aguardando logs...", None
            
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                linhas_log = f.readlines()
                if len(linhas_log) > linhas:
                    linhas_log = linhas_log[-linhas:]
                return ''.join(linhas_log), None
        except Exception as e:
            return None, str(e)
    
    def obter_recursos(self, pid):
        if pid not in self.processos:
            return None
        
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=0.3)
            mem = proc.memory_info().rss / (1024 * 1024)
            
            try:
                filhos = proc.children(recursive=True)
                for filho in filhos:
                    cpu += filho.cpu_percent(interval=0.1)
                    mem += filho.memory_info().rss / (1024 * 1024)
            except:
                pass
            
            return {
                'cpu': round(min(cpu, 100), 1),
                'mem': round(mem, 1),
                'status': 'online'
            }
        except:
            return {'status': 'offline'}

# Inicializar
bot_manager = BotManager()
import sys

# Funções auxiliares
def carregar_dados():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'projetos': []}

def salvar_dados(dados):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def analisar_zip(zip_bytes):
    resultado = {'valido': False, 'tamanho_mb': 0, 'arquivos_py': 0, 'erros': []}
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            nomes = zf.namelist()
            resultado['tamanho_mb'] = sum(zf.getinfo(n).file_size for n in nomes) / (1024 * 1024)
            resultado['arquivos_py'] = len([n for n in nomes if n.endswith('.py')])
            
            if resultado['arquivos_py'] == 0:
                resultado['erros'].append("Nenhum arquivo .py encontrado")
                return resultado
            
            resultado['valido'] = True
    except Exception as e:
        resultado['erros'].append(str(e))
    
    return resultado

# Rotas API
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/projetos')
def api_projetos():
    dados = carregar_dados()
    projetos = []
    
    for projeto in dados.get('projetos', []):
        status = 'offline'
        recursos = None
        
        if projeto.get('pid') and bot_manager.status_bot(projeto['pid']):
            status = 'online'
            recursos = bot_manager.obter_recursos(projeto['pid'])
        
        projetos.append({
            'id': projeto['nome'],
            'nome': projeto['nome'],
            'status': status,
            'tamanho': round(projeto.get('tamanho', 0), 2),
            'cpu': recursos['cpu'] if recursos else 0,
            'mem': recursos['mem'] if recursos else 0,
            'pid': projeto.get('pid'),
            'criado': projeto.get('criado', ''),
            'caminho': projeto.get('caminho', '')
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
    
    nome_projeto = re.sub(r'[^a-zA-Z0-9_-]', '', nome_projeto)[:30]
    if not nome_projeto:
        return jsonify({'error': 'Nome inválido'}), 400
    
    # Verificar se já existe
    dados = carregar_dados()
    for p in dados['projetos']:
        if p['nome'] == nome_projeto:
            return jsonify({'error': f'Projeto "{nome_projeto}" já existe!'}), 400
    
    # Analisar ZIP
    zip_bytes = arquivo.read()
    analise = analisar_zip(zip_bytes)
    if not analise['valido']:
        return jsonify({'error': '\n'.join(analise['erros'])}), 400
    
    # Criar diretório
    caminho_projeto = os.path.join(PROJETOS_DIR, nome_projeto)
    
    if os.path.exists(caminho_projeto):
        shutil.rmtree(caminho_projeto)
    
    os.makedirs(caminho_projeto)
    
    # Extrair arquivos
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(caminho_projeto)
    
    # Salvar
    dados['projetos'].append({
        'nome': nome_projeto,
        'tamanho': analise['tamanho_mb'],
        'criado': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'pid': None,
        'caminho': caminho_projeto
    })
    
    salvar_dados(dados)
    
    return jsonify({
        'success': True,
        'projeto': nome_projeto,
        'tamanho': analise['tamanho_mb'],
        'arquivos_py': analise['arquivos_py']
    })

@app.route('/api/iniciar', methods=['POST'])
def api_iniciar():
    data = request.json
    projeto_nome = data.get('projeto_nome')
    
    if not projeto_nome:
        return jsonify({'error': 'Nome do projeto necessário'}), 400
    
    dados = carregar_dados()
    projeto = None
    
    for p in dados['projetos']:
        if p['nome'] == projeto_nome:
            projeto = p
            break
    
    if not projeto:
        return jsonify({'error': 'Projeto não encontrado'}), 404
    
    # Verificar se já está rodando
    if projeto.get('pid') and bot_manager.status_bot(projeto['pid']):
        return jsonify({'error': 'Bot já está rodando!'}), 400
    
    caminho = os.path.join(PROJETOS_DIR, projeto_nome)
    pid, msg = bot_manager.iniciar_bot(projeto_nome, projeto_nome, caminho)
    
    if pid:
        projeto['pid'] = pid
        salvar_dados(dados)
        socketio.emit('bot_iniciado', {'projeto': projeto_nome, 'pid': pid})
        return jsonify({'success': True, 'pid': pid, 'message': msg})
    
    return jsonify({'error': msg}), 500

@app.route('/api/parar', methods=['POST'])
def api_parar():
    data = request.json
    pid = data.get('pid')
    
    if not pid:
        return jsonify({'error': 'PID necessário'}), 400
    
    ok, msg = bot_manager.parar_bot(pid)
    
    if ok:
        dados = carregar_dados()
        for projeto in dados['projetos']:
            if projeto.get('pid') == pid:
                projeto['pid'] = None
                salvar_dados(dados)
                break
        
        socketio.emit('bot_parado', {'pid': pid})
        return jsonify({'success': True, 'message': msg})
    
    return jsonify({'error': msg}), 500

@app.route('/api/reiniciar', methods=['POST'])
def api_reiniciar():
    data = request.json
    projeto_nome = data.get('projeto_nome')
    pid = data.get('pid')
    
    if not projeto_nome:
        return jsonify({'error': 'Nome do projeto necessário'}), 400
    
    # Parar se estiver rodando
    if pid:
        bot_manager.parar_bot(pid)
        time.sleep(2)
    
    # Iniciar novamente
    dados = carregar_dados()
    projeto = None
    for p in dados['projetos']:
        if p['nome'] == projeto_nome:
            projeto = p
            break
    
    if not projeto:
        return jsonify({'error': 'Projeto não encontrado'}), 404
    
    caminho = os.path.join(PROJETOS_DIR, projeto_nome)
    novo_pid, msg = bot_manager.iniciar_bot(projeto_nome, projeto_nome, caminho)
    
    if novo_pid:
        projeto['pid'] = novo_pid
        salvar_dados(dados)
        socketio.emit('bot_reiniciado', {'projeto': projeto_nome, 'pid': novo_pid})
        return jsonify({'success': True, 'pid': novo_pid, 'message': msg})
    
    return jsonify({'error': msg}), 500

@app.route('/api/logs/<projeto_nome>')
def api_logs(projeto_nome):
    dados = carregar_dados()
    projeto = None
    
    for p in dados['projetos']:
        if p['nome'] == projeto_nome:
            projeto = p
            break
    
    if not projeto or not projeto.get('pid'):
        # Tenta ler log mesmo se não tiver PID
        log_path = os.path.join(PROJETOS_DIR, projeto_nome, 'bot.log')
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                logs = f.read()[-5000:]
                return jsonify({'logs': logs or "📝 Nenhum log disponível"})
        return jsonify({'logs': "⏳ Bot offline. Inicie o bot para ver os logs."})
    
    logs, erro = bot_manager.obter_logs(projeto['pid'])
    if erro:
        return jsonify({'error': erro}), 500
    
    return jsonify({'logs': logs or "📝 Nenhum log disponível"})

@app.route('/api/recursos/<projeto_nome>')
def api_recursos(projeto_nome):
    dados = carregar_dados()
    projeto = None
    
    for p in dados['projetos']:
        if p['nome'] == projeto_nome:
            projeto = p
            break
    
    if not projeto or not projeto.get('pid'):
        return jsonify({'status': 'offline', 'cpu': 0, 'mem': 0})
    
    recursos = bot_manager.obter_recursos(projeto['pid'])
    if recursos:
        return jsonify(recursos)
    
    return jsonify({'status': 'offline', 'cpu': 0, 'mem': 0})

@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Conectado'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)
