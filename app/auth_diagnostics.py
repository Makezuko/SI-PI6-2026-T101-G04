"""Diagnóstico local por etapa, sem mensagens brutas, credenciais ou payloads."""
from contextvars import ContextVar
import logging
import json
import traceback
from pathlib import Path
from src.matching.telemetry import execution_id

logger = logging.getLogger('talentmatch.auth')
logger.setLevel(logging.INFO)
current_stage = ContextVar('auth_stage', default='NOT_STARTED')


def stage(name):
    current_stage.set(name)
    logger.info(json.dumps(dict(event='AUTH_STAGE', run_id=execution_id.get(), stage=name)))


def failure(error):
    chain, seen = [], set()
    original = error
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        item = dict(type=type(error).__name__)
        for key in ('errno', 'winerror'):
            value = getattr(error, key, None)
            if isinstance(value, int):
                item[key] = value
        chain.append(item)
        error = error.__cause__ or error.__context__
    frames = [dict(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
              for frame in traceback.extract_tb(original.__traceback__)[-6:]]
    logger.warning(json.dumps(dict(event='AUTH_ERROR', run_id=execution_id.get(),
        stage=current_stage.get(), exceptions=chain, frames=frames)))
