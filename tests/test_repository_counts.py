import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.repositories import get_job, list_jobs


class CountFailureTests(unittest.TestCase):
    def test_count_failures_are_reported_without_sensitive_details(self):
        for operation in (list_jobs, lambda client: get_job(client, 1)):
            with self.subTest(operation=operation):
                client = MagicMock()
                jobs = client.table.return_value.select.return_value
                jobs.order.return_value.range.return_value.execute.return_value = SimpleNamespace(data=[{
                    'id': 1, 'titulo': 'Vaga', 'descricao': 'Descricao', 'requisitos': '',
                }])
                jobs.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{
                    'id': 1, 'titulo': 'Vaga', 'descricao': 'Descricao', 'requisitos': '',
                }])
                def table(name):
                    if name == 'curriculos':
                        raise RuntimeError('sensitive database details')
                    return client.table.return_value
                client.table.side_effect = table
                with self.assertLogs('app.repositories', level='ERROR') as logs:
                    with self.assertRaisesRegex(RuntimeError, 'contagem') as caught:
                        operation(client)
                self.assertNotIn('sensitive', str(caught.exception))
                self.assertNotIn('sensitive', ' '.join(logs.output))


if __name__ == '__main__':
    unittest.main()
