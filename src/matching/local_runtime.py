"""Processo llama.cpp privado, somente loopback, sem dependência de serviço prévio."""
import atexit
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


class LlamaCppAdapter:
    def __init__(self, model_path, executable):
        if not Path(model_path).is_file() or not Path(executable).is_file():
            raise ValueError('Prepare o runtime e GGUF com scripts.preparar_runtime_contextual')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.process = subprocess.Popen([str(executable), '-m', str(model_path),
            '--host', '127.0.0.1', '--port', str(port), '-c', '4096', '-t', '4',
            '-ngl', '0', '--parallel', '1'], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        atexit.register(self.close)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Runtime local encerrou antes de carregar o modelo')
            try:
                with self.http.open(self.url + '/health', timeout=2) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(.2)
        self.close()
        raise TimeoutError('Runtime não ficou pronto em 120 segundos')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def generate(self, payload):
        from src.matching.contextual import PROMPT, STATES
        ids = [e['id'] for e in payload['evidencias']]
        schema = dict(type='object', additionalProperties=False,
            required=['estado', 'evidence_ids', 'justificativa', 'limitacoes', 'base'],
            properties=dict(estado=dict(type='string', enum=sorted(STATES)),
                evidence_ids=dict(type='array', items=dict(type='string', enum=ids)),
                justificativa=dict(type='string', maxLength=180),
                limitacoes=dict(type='array', maxItems=2, items=dict(type='string', maxLength=100)),
                base=dict(type='string', enum=['evidencia', 'ausencia', 'contradicao', 'ambiguidade'])))
        body = dict(messages=[dict(role='system', content=PROMPT),
                              dict(role='user', content=json.dumps(payload, ensure_ascii=False))],
                    temperature=0, seed=0, max_tokens=384,
                    response_format=dict(type='json_schema', json_schema=dict(name='sustentacao', schema=schema)))
        request = urllib.request.Request(self.url + '/v1/chat/completions',
            data=json.dumps(body).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with self.http.open(request, timeout=120) as response:
            return json.load(response)['choices'][0]['message']['content']
