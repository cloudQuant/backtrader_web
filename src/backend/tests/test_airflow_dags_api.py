from httpx import AsyncClient


class TestAirflowDagsAPI:
    async def test_list_dags_requires_authentication(self, client: AsyncClient):
        response = await client.get("/api/v1/data/airflow/dags")

        assert response.status_code == 401

    async def test_orchestration_status_requires_authentication(self, client: AsyncClient):
        response = await client.get("/api/v1/data/airflow/orchestration/status")

        assert response.status_code == 401
