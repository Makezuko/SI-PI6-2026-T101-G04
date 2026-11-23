"""Eventos técnicos permitidos; nunca registrar textos, tokens ou exceções brutas."""
from contextvars import ContextVar
import json
import logging
import uuid

execution_id = ContextVar('analysis_execution_id', default='-')
logger = logging.getLogger('talentmatch.analysis')
logger.setLevel(logging.INFO)
ALLOWED = {'pid', 'python', 'enabled', 'backend', 'model', 'revision', 'pipeline',
           'requirement_id', 'seconds', 'error_code', 'analysis_id',
           'persisted_run_id', 'selected_count', 'found', 'method', 'stage', 'error_type', 'frames', 'count', 'windows', 'dimension'}


def new_execution():
    return execution_id.set(uuid.uuid4().hex)


def event(name, **fields):
    if fields.keys() - ALLOWED:
        raise ValueError('Campo não permitido no rastreamento técnico')
    logger.info(json.dumps(dict(event=name, run_id=execution_id.get(), **fields), ensure_ascii=True))


from contextlib import contextmanager
import traceback
from pathlib import Path


def failure(error, stage):
    frames = [dict(file=Path(f.filename).name, function=f.name, line=f.lineno)
              for f in traceback.extract_tb(error.__traceback__)]
    event('ANALYSIS_STAGE_ERROR', stage=stage, error_type=type(error).__name__, frames=frames)


@contextmanager
def stage(name):
    event('ANALYSIS_STAGE_START', stage=name)
    try:
        yield
    except Exception as error:
        failure(error, name)
        raise
    else:
        event('ANALYSIS_STAGE_END', stage=name)
