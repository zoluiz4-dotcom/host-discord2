import os
import subprocess
import signal
import time
import psutil
import sys
from datetime import datetime
import threading

class BotManager:
    def __init__(self):
        self.processos = {}
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _monitor_loop(self):
        """Monitora os bots e emite eventos de status"""
        while True:
            for pid, info in list(self.processos.items()):
                try:
                    if info['processo'].poll() is not None:
                        # Bot caiu, tentar reiniciar se configurado
                        from flask_socketio import SocketIO
                        try:
                            socketio = SocketIO(message_queue='epc://')
                            socketio.emit('bot_status', {
                                'nome': info['projeto'],
                                'status': 'offline',
                                'pid': pid
                            })
                        except:
                            pass
                except:
                    pass
            time.sleep(5)
    
    def encontrar_arquivo_principal(self, caminho):
        """Encontra automaticamente o arquivo principal do bot"""
        arquivos_principais = [
            'bot.py', 'main.py', 'app.py', 'run.py', 
            'index.py', 'client.py', 'discord_bot.py'
        ]
        
        # Primeiro, procurar arquivos conhecidos
        for raiz, dirs, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                if arquivo in arquivos_principais:
                    return os.path.join(raiz, arquivo)
        
        # Segundo, procurar qualquer arquivo .py que contenha código Discord
        for raiz, dirs, arquivos in os.walk(caminho):
            for arquivo in arquivos:
                if arquivo.endswith('.py') and arquivo != 'requirements.py':
                    caminho_arquivo = os.path.join(raiz, arquivo)
                    try:
                        with open(caminho_arquivo, 'r', encoding='utf-8', errors='ignore') as f:
                            conteudo = f.read()
                            if 'discord' in conteudo and ('commands.Bot' in conteudo or 'discord.Client' in conteudo):
                                return caminho_arquivo
                    except:
                        pass
        return None
    
    def instalar_dependencias(self, caminho_projeto, venv_path):
        """Instala dependências do arquivo requirements.txt"""
        req_file = os.path.join(caminho_projeto, 'requirements.txt')
        if not os.path.exists(req_file):
            return True, "Sem dependências para instalar"
        
        try:
            if os.name == 'nt':
                pip_exe = os.path.join(venv_path, 'Scripts', 'pip.exe')
            else:
                pip_exe = os.path.join(venv_path, 'bin', 'pip')
            
            # Instalar dependências
            resultado = subprocess.run(
                [pip_exe, 'install', '-r', req_file],
                capture_output=True,
                timeout=180,
                text=True
            )
            
            if resultado.returncode == 0:
                return True, "Dependências instaladas com sucesso"
            else:
                return False, f"Erro ao instalar: {resultado.stderr[:200]}"
                
        except subprocess.TimeoutExpired:
            return False, "Timeout ao instalar dependências"
        except Exception as e:
            return False, str(e)
    
    def iniciar_bot(self, usuario_id, projeto_nome, caminho):
        """Inicia um bot em um diretório"""
        caminho_abs = os.path.abspath(caminho)
        
        # Verificar se já está rodando
        for pid, info in self.processos.items():
            if info['projeto'] == projeto_nome and info['usuario_id'] == usuario_id:
                if info['processo'].poll() is None:
                    return None, "Bot já está rodando"
        
        # Encontrar arquivo principal
        arquivo_principal = self.encontrar_arquivo_principal(caminho_abs)
        if not arquivo_principal:
            return None, "Arquivo principal não encontrado (bot.py, main.py, app.py, etc)"
        
        try:
            # Criar ambiente virtual
            venv_path = os.path.join(caminho_abs, 'venv')
            if not os.path.exists(venv_path):
                subprocess.run(
                    [sys.executable, '-m', 'venv', venv_path],
                    capture_output=True,
                    timeout=60
                )
            
            # Configurar executáveis
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, 'Scripts', 'python.exe')
                pip_exe = os.path.join(venv_path, 'Scripts', 'pip.exe')
            else:
                python_exe = os.path.join(venv_path, 'bin', 'python')
                pip_exe = os.path.join(venv_path, 'bin', 'pip')
            
            # Instalar discord.py
            subprocess.run(
                [pip_exe, 'install', 'discord.py', '--quiet'],
                capture_output=True,
                timeout=60
            )
            
            # Instalar outras dependências
            self.instalar_dependencias(caminho_abs, venv_path)
            
            # Criar arquivo de log
            log_path = os.path.join(caminho_abs, 'bot.log')
            log_file = open(log_path, 'a', encoding='utf-8')
            log_file.write(f'\n{"="*50}\n')
            log_file.write(f'Bot iniciado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n')
            log_file.write(f'Arquivo principal: {arquivo_principal}\n')
            log_file.write(f'{"="*50}\n\n')
            log_file.flush()
            
            # Iniciar processo
            if hasattr(os, 'setsid'):
                # Linux/Unix
                proc = subprocess.Popen(
                    [python_exe, arquivo_principal],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=caminho_abs,
                    preexec_fn=os.setsid
                )
            else:
                # Windows
                proc = subprocess.Popen(
                    [python_exe, arquivo_principal],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=caminho_abs,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            
            # Armazenar informações
            self.processos[proc.pid] = {
                'pid': proc.pid,
                'usuario_id': usuario_id,
                'projeto': projeto_nome,
                'processo': proc,
                'log_path': log_path,
                'log_file': log_file,
                'started_at': datetime.now().timestamp(),
                'caminho': caminho_abs,
                'arquivo_principal': arquivo_principal
            }
            
            return proc.pid, f"Bot iniciado com sucesso (PID: {proc.pid})"
            
        except Exception as e:
            return None, f"Erro ao iniciar bot: {str(e)}"
    
    def parar_bot(self, pid):
        """Para um bot pelo PID"""
        if pid not in self.processos:
            return False, "Processo não encontrado"
        
        try:
            info = self.processos[pid]
            proc = info['processo']
            
            # Tentar matar o processo graciosamente
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except:
                    pass
            
            proc.terminate()
            
            # Esperar o processo terminar
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            # Registrar no log
            try:
                info['log_file'].write(f'\nBot parado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n')
                info['log_file'].close()
            except:
                pass
            
            # Remover do dicionário
            del self.processos[pid]
            
            return True, "Bot parado com sucesso"
            
        except Exception as e:
            return False, f"Erro ao parar bot: {str(e)}"
    
    def reiniciar_bot(self, pid):
        """Reinicia um bot"""
        if pid not in self.processos:
            return False, "Processo não encontrado"
        
        info = self.processos[pid]
        nome_projeto = info['projeto']
        usuario_id = info['usuario_id']
        caminho = info['caminho']
        
        # Parar o bot
        self.parar_bot(pid)
        time.sleep(2)  # Aguardar para garantir que parou
        
        # Iniciar novamente
        novo_pid, msg = self.iniciar_bot(usuario_id, nome_projeto, caminho)
        
        if novo_pid:
            return True, "Bot reiniciado com sucesso"
        else:
            return False, msg
    
    def status_bot(self, pid):
        """Verifica se o bot está rodando"""
        if pid not in self.processos:
            return False
        
        try:
            proc = self.processos[pid]['processo']
            return proc.poll() is None
        except:
            return False
    
    def obter_logs(self, pid, linhas=200):
        """Obtém os logs do bot"""
        if pid not in self.processos:
            return None, "Processo não encontrado"
        
        try:
            log_path = self.processos[pid]['log_path']
            if not os.path.exists(log_path):
                return "Sem logs ainda...", None
            
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                linhas_log = f.readlines()
                
                if len(linhas_log) > linhas:
                    linhas_log = linhas_log[-linhas:]
                
                return ''.join(linhas_log), None
                
        except Exception as e:
            return None, f"Erro ao ler logs: {str(e)}"
    
    def obter_uso_recursos(self, pid):
        """Obtém uso de CPU e RAM do bot"""
        if pid not in self.processos:
            return None
        
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=0.5)
            mem = proc.memory_info().rss / (1024 * 1024)
            
            # Incluir processos filhos
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
                'status': 'online' if proc.is_running() else 'offline'
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        except Exception:
            return None
    
    def listar_bots_ativos(self):
        """Lista todos os bots ativos"""
        bots = []
        for pid, info in self.processos.items():
            if self.status_bot(pid):
                bots.append({
                    'pid': pid,
                    'projeto': info['projeto'],
                    'usuario_id': info['usuario_id'],
                    'started_at': info['started_at']
                })
        return bots
    
    def limpar_processos_mortos(self):
        """Limpa processos que já morreram do dicionário"""
        for pid, info in list(self.processos.items()):
            if info['processo'].poll() is not None:
                try:
                    info['log_file'].close()
                except:
                    pass
                del self.processos[pid]
