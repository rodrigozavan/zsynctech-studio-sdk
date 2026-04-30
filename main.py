"""
t.py — Testa a nova arquitetura WebSocket (versão Python)

Simula dois cenários:
  1. Robô: conecta no namespace /instances, autentica com API token e aguarda execuções
  2. Observador: conecta no namespace /dashboard (sem JWT, apenas observa os eventos raw)

Uso:
  python t.py

Variáveis de ambiente:
  API_TOKEN     — token zst_... de um robot cadastrado   (obrigatório)
  INSTANCE_ID   — UUID da instância do robô              (obrigatório)
  WS_URL        — URL base do backend                    (padrão: http://localhost:3000)
  DASHBOARD_JWT — JWT de um usuário admin para o dashboard (opcional)
"""

import asyncio
import os
import sys
import random

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import socketio

# ──────────────── Config ────────────────
WS_URL        = os.environ.get('WS_URL', 'http://localhost:3000')
API_TOKEN     = os.environ.get('API_TOKEN')
INSTANCE_ID   = os.environ.get('INSTANCE_ID')
DASHBOARD_JWT = os.environ.get('DASHBOARD_JWT')

if not API_TOKEN or not INSTANCE_ID:
    print('❌  Configure as variáveis de ambiente:')
    print('   API_TOKEN=zst_xxx  INSTANCE_ID=uuid-da-instancia  python t.py')
    sys.exit(1)

# ──────────────── Colors ────────────────
class c:
    reset  = '\x1b[0m'
    green  = '\x1b[32m'
    red    = '\x1b[31m'
    yellow = '\x1b[33m'
    cyan   = '\x1b[36m'
    gray   = '\x1b[90m'

def log(label, color, *args):
    msg = ' '.join(str(a) for a in args)
    print(f"{color}[{label}]{c.reset} {msg}", flush=True)

# ──────────────── Simulated tasks ────────────────
SIMULATED_TASKS = [
    {'name': 'Inicializar conexão',           'shouldFail': False},
    {'name': 'Autenticar na origem de dados', 'shouldFail': False},
    {'name': 'Extrair dados',                 'shouldFail': False},
    {'name': 'Transformar dados',             'shouldFail': False},
    {'name': 'Processar dados',               'shouldFail': False},
    {'name': 'Gravar resultados',             'shouldFail': False},
    {'name': 'Encerrar conexão',              'shouldFail': False},
]

# ──────────────── Socket clients ────────────────
robot_sio     = socketio.AsyncClient(reconnection=True, reconnection_delay=2, reconnection_attempts=5)
dashboard_sio = socketio.AsyncClient()

# ──────────────── WS Emit helper (with ack) ────────────────
async def ws_emit(event, data):
    """Sends an event with ack and raises on timeout or server error."""
    result = await robot_sio.call(event, data, namespace='/instances', timeout=10)
    if not result or not result.get('ok'):
        error = result.get('error', 'unknown') if result else 'timeout'
        raise Exception(f"{event} failed: {error}")
    return result

# ──────────────── Task simulation ────────────────
async def run_tasks(execution_id):
    log('ROBOT', c.cyan, f'   Iniciando {len(SIMULATED_TASKS)} tasks...')
    for i, task in enumerate(SIMULATED_TASKS):
        # 1. Register task
        try:
            reg = await ws_emit('task:register', {
                'executionId': execution_id,
                'name': task['name'],
                'order': i,
            })
            task_id = reg['taskId']
        except Exception as err:
            log('ROBOT', c.red, f'   ❌  Falha ao registrar task "{task["name"]}": {err}')
            continue

        log('ROBOT', c.cyan, f'   [{i+1}/{len(SIMULATED_TASKS)}] ▶  {task["name"]}')

        # 2. Mark as RUNNING
        try:
            await ws_emit('task:update', {'executionId': execution_id, 'taskId': task_id, 'status': 'RUNNING'})
        except Exception:
            pass

        # Simulate execution time
        await asyncio.sleep(0.5 + random.random() * 10)

        # 3. Mark as SUCCESS or ERROR
        final_status = 'ERROR' if task['shouldFail'] else 'SUCCESS'
        update_data = {'executionId': execution_id, 'taskId': task_id, 'status': final_status}
        if task['shouldFail']:
            update_data['observation'] = 'Erro simulado na task'
        try:
            await ws_emit('task:update', update_data)
        except Exception:
            pass

        icon  = '✅' if final_status == 'SUCCESS' else '❌'
        color = c.green if final_status == 'SUCCESS' else c.red
        log('ROBOT', color, f'   [{i+1}/{len(SIMULATED_TASKS)}] {icon}  {task["name"]} → {final_status}')

async def finish_execution(execution_id):
    has_failed = any(t['shouldFail'] for t in SIMULATED_TASKS)
    data = {'executionId': execution_id}
    if has_failed:
        data['observation'] = 'Uma ou mais tasks falharam durante a execução'
    try:
        res   = await ws_emit('execution:finish', data)
        icon  = '🏁' if res.get('status') == 'COMPLETED' else '💥'
        color = c.green if res.get('status') == 'COMPLETED' else c.red
        log('ROBOT', color, f'   {icon}  Execução encerrada com status: {res.get("status")}')
    except Exception as err:
        log('ROBOT', c.red, f'   ❌  Falha ao encerrar execução: {err}')

async def run_and_finish(execution_id):
    await run_tasks(execution_id)
    await finish_execution(execution_id)

# ──────────────── Robot socket handlers ────────────────
@robot_sio.event(namespace='/instances')
async def connect():
    log('ROBOT', c.green, f'Conectado (socketId: {robot_sio.get_sid("/instances")})')
    log('ROBOT', c.green, 'Enviando authenticate...')
    await robot_sio.emit('authenticate', {'token': API_TOKEN, 'instanceId': INSTANCE_ID}, namespace='/instances')

@robot_sio.on('authenticated', namespace='/instances')
async def on_authenticated(data):
    log('ROBOT', c.green, '✅  Autenticado!', data)
    if data.get('reconnected'):
        log('ROBOT', c.yellow, '↩️  Reconexão dentro do grace period — aguardando execution:resume...')
    else:
        log('ROBOT', c.cyan, '⏳  Aguardando execuções via WebSocket (event: execution:new)...')

@robot_sio.on('authenticate:error', namespace='/instances')
async def on_auth_error(data):
    log('ROBOT', c.red, '❌  Erro de autenticação:', data.get('message'))
    sys.exit(1)

@robot_sio.on('execution:new', namespace='/instances')
async def on_execution_new(data):
    log('ROBOT', c.cyan, '🚀  Nova execução recebida, aceitando via ack:', data)
    log('ROBOT', c.cyan, '   ✅  Ack enviado — aguardando execution:claimed...')
    return {'accepted': True}

@robot_sio.on('execution:claimed', namespace='/instances')
async def on_execution_claimed(data):
    execution_id = data.get('executionId')
    log('ROBOT', c.green, f'   🏃  Execução {execution_id} RUNNING — iniciando tasks...')
    asyncio.ensure_future(run_and_finish(execution_id))

@robot_sio.on('execution:resume', namespace='/instances')
async def on_execution_resume(data):
    execution_id = data.get('executionId')
    log('ROBOT', c.yellow, '▶️  Resume de execução em andamento:', data)
    log('ROBOT', c.yellow, '   (execução já RUNNING — simulando continuação das tasks)')
    asyncio.ensure_future(run_and_finish(execution_id))

@robot_sio.event(namespace='/instances')
async def disconnect():
    log('ROBOT', c.red, 'Desconectado')

@robot_sio.on('connect_error', namespace='/instances')
async def on_connect_error(data):
    log('ROBOT', c.red, 'Erro de conexão:', data)

# ──────────────── Dashboard socket handlers ────────────────
@dashboard_sio.event(namespace='/dashboard')
async def connect():
    log('DASH', c.green, f'Conectado ao dashboard (socketId: {dashboard_sio.get_sid("/dashboard")})')

@dashboard_sio.on('connect_error', namespace='/dashboard')
async def on_dash_connect_error(data):
    log('DASH', c.red, 'Erro de conexão (JWT inválido ou ausente):', data)

@dashboard_sio.on('instance:online', namespace='/dashboard')
async def on_instance_online(data):
    log('DASH', c.green, '🟢  instance:online', data)

@dashboard_sio.on('instance:disconnecting', namespace='/dashboard')
async def on_instance_disconnecting(data):
    log('DASH', c.yellow, '🟡  instance:disconnecting (grace period ativo)', data)

@dashboard_sio.on('instance:offline', namespace='/dashboard')
async def on_instance_offline(data):
    log('DASH', c.red, '🔴  instance:offline', data)

@dashboard_sio.on('execution:created', namespace='/dashboard')
async def on_execution_created(data):
    log('DASH', c.cyan, '📋  execution:created', data)

@dashboard_sio.on('execution:finished', namespace='/dashboard')
async def on_execution_finished(data):
    log('DASH', c.cyan, '✅  execution:finished', data)

# ──────────────── Interactive commands ────────────────
async def handle_input():
    log('INFO', c.gray, '')
    log('INFO', c.gray, '📌  Comandos disponíveis no terminal:')
    log('INFO', c.gray, '   d  — força disconnect do robô (testa grace period)')
    log('INFO', c.gray, '   r  — força reconnect do robô')
    log('INFO', c.gray, '   f  — simula task com falha na próxima execução')
    log('INFO', c.gray, '   q  — encerra o teste')
    log('INFO', c.gray, '')

    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        cmd  = line.strip().lower()

        if cmd == 'd':
            log('INFO', c.yellow, 'Desconectando robô (grace period deve iniciar no servidor)...')
            await robot_sio.disconnect()
        elif cmd == 'r':
            log('INFO', c.green, 'Reconectando robô...')
            await robot_sio.connect(WS_URL, namespaces=['/instances'])
        elif cmd == 'f':
            idx = next((i for i, t in enumerate(SIMULATED_TASKS) if not t['shouldFail']), None)
            if idx is not None:
                SIMULATED_TASKS[idx]['shouldFail'] = True
                log('INFO', c.yellow, f'Task "{SIMULATED_TASKS[idx]["name"]}" marcada para falhar na próxima execução')
            else:
                log('INFO', c.gray, 'Todas as tasks já estão marcadas para falhar')
        elif cmd == 'q':
            log('INFO', c.gray, 'Encerrando...')
            await robot_sio.disconnect()
            if DASHBOARD_JWT:
                await dashboard_sio.disconnect()
            sys.exit(0)
        else:
            log('INFO', c.gray, f'Comando desconhecido: "{cmd}". Use d, r, f ou q.')

# ──────────────── Main ────────────────
async def main():
    log('ROBOT', c.cyan, f'Conectando em {WS_URL}/instances ...')

    connect_tasks = [robot_sio.connect(WS_URL, namespaces=['/instances'])]

    if DASHBOARD_JWT:
        connect_tasks.append(
            dashboard_sio.connect(WS_URL, namespaces=['/dashboard'], auth={'token': DASHBOARD_JWT})
        )
    else:
        log('DASH', c.gray, 'DASHBOARD_JWT não configurado — dashboard desativado neste teste')

    await asyncio.gather(*connect_tasks)
    await handle_input()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log('INFO', c.gray, 'Interrompido.')
