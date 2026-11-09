"""Load optional AI tools only when requested (OCR does not need the chat stack)."""
from importlib import import_module

_EXPORTS = {
    'load_documents': 'document_loader',
    'split_documents': 'document_loader',
    'get_llm': 'llm_client',
    'get_duckduckgo_search': 'search_tools',
    'get_memory_store': 'vector_store',
    'get_retriever': 'vector_store',
    'setup_vector_store': 'vector_store',
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f'.{_EXPORTS[name]}', __name__), name)
    globals()[name] = value
    return value
