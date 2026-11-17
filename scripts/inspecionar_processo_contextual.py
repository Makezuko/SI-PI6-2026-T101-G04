"""Windows x64: lê somente configuração contextual de PIDs indicados.

Não imprime linha de comando, ambiente completo, tokens ou dados do currículo.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json


def inspect(pid):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise OSError('Acesso ao processo indisponível')
    try:
        class Basic(c.Structure):
            _fields_ = [('reserved', c.c_void_p), ('peb', c.c_void_p),
                        ('reserved2', c.c_void_p * 2), ('pid', c.c_size_t), ('parent', c.c_void_p)]
        info = Basic()
        query = c.WinDLL('ntdll').NtQueryInformationProcess
        query.argtypes = [w.HANDLE, w.ULONG, c.c_void_p, w.ULONG, c.c_void_p]
        if query(handle, 0, c.byref(info), c.sizeof(info), None):
            raise OSError('Consulta ao processo indisponível')
        def read(address, size):
            buffer = c.create_string_buffer(size)
            count = c.c_size_t()
            kernel.ReadProcessMemory(handle, address, buffer, size, c.byref(count))
            if not count.value:
                raise OSError('Ambiente do processo indisponível')
            return buffer.raw[:count.value]
        params = int.from_bytes(read(info.peb + 0x20, 8), 'little')
        env_address = int.from_bytes(read(params + 0x80, 8), 'little')
        block = bytearray()
        for offset in range(0, 131072, 1024):
            block.extend(read(env_address + offset, 1024))
            if '\x00\x00' in block.decode('utf-16-le', errors='ignore'):
                break
        allow = {'CONTEXTUAL_EVALUATOR', 'CONTEXTUAL_BACKEND',
                 'CONTEXTUAL_MODEL_PATH', 'CONTEXTUAL_MODEL_REVISION', 'WERKZEUG_RUN_MAIN'}
        selected = {}
        for entry in block.decode('utf-16-le', errors='ignore').split('\x00'):
            key, separator, value = entry.partition('=')
            if separator and key in allow:
                selected[key] = value
        return dict(pid=pid, parent_pid=info.parent, contextual_environment=selected)
    finally:
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--pid', type=int, action='append', required=True)
    for pid in parser.parse_args().pid:
        print(json.dumps(inspect(pid), ensure_ascii=True))
