from langchain_core.documents import Document
from app.tools.lexical_store import LexicalStore


def test_lexical_retrieval_is_bounded_and_session_scoped():
    store = LexicalStore(memory=True)
    store.add_texts(['account salary income', 'account salary private'], [{'session_id': '1:one'}, {'session_id': '2:one'}])
    found = store.similarity_search('salary', filter={'session_id': '1:one'})
    assert len(found) == 1
    assert found[0].page_content == 'account salary income'
    found[0].page_content = 'modified copy'
    assert store.similarity_search('salary', filter={'session_id': '1:one'})[0].page_content == 'account salary income'
    store.add_texts(['deposit'] * 600, [{'session_id': '1:one'}] * 600)
    assert len(store.documents) == 500
