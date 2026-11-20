from app import app
import argparse
import logging
from pathlib import Path
from app.analysis import process_configuration


def main():
    parser = argparse.ArgumentParser(description='Servidor local com processo e porta explícitos.')
    parser.add_argument('--port', type=int, default=5002)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    from src.matching.telemetry import event
    trace_path = Path('reports/contextual-server.jsonl')
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    from src.matching.telemetry import logger
    trace_file = logging.FileHandler(trace_path, encoding='utf-8')
    trace_file.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(trace_file)
    from app.auth_diagnostics import logger as auth_logger
    auth_logger.addHandler(trace_file)
    # make_server faz bind exclusivo, sem SO_REUSEADDR que permite colisões no Windows.
    from socketserver import ThreadingMixIn
    from werkzeug.serving import BaseWSGIServer, WSGIRequestHandler
    class SafeHandler(WSGIRequestHandler):
        def log_request(self, code='-', size='-'):
            logging.getLogger('werkzeug').info('HTTP %s status=%s', self.command, code)
    class ExclusiveServer(ThreadingMixIn, BaseWSGIServer):
        allow_reuse_address = False
        daemon_threads = True
        def server_bind(self):
            import socket
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()
    app.debug = False
    server = ExclusiveServer('127.0.0.1', args.port, app, handler=SafeHandler)
    event('FLASK_PROCESS', **process_configuration())
    print(f'URL: http://127.0.0.1:{args.port}/login · debug=False · reloader=False', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
