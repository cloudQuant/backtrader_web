"""Iteration 129 import API tests."""

from httpx import AsyncClient


class TestIteration129ImportAPI:
    """ReqDocs migration import tests."""

    async def test_import_reqdocs_payload_creates_knowledge_base_and_documents(
        self, client: AsyncClient, auth_headers: dict
    ):
        payload = {
            "name": "迁移知识库",
            "description": "来自 ReqDocs 的迁移数据",
            "documents": [
                {
                    "title": "双均线策略",
                    "content": "双均线策略在上穿时开仓。",
                    "content_type": "markdown",
                    "is_folder": False,
                },
                {
                    "title": "策略手册",
                    "content": "使用说明。",
                    "content_type": "markdown",
                    "is_folder": False,
                },
            ],
        }

        resp = await client.post(
            "/api/v1/knowledge-base/import/reqdocs",
            headers=auth_headers,
            json=payload,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["knowledge_base"]["name"] == "迁移知识库"
        assert body["imported_documents"] == 2
