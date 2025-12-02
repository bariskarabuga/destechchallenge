import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


class TestAssistanceRequestCreateView:

    def test_talep_olusturulur(self, db, provider, api_client, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")

        response = api_client.post("/api/requests/", {
            "customer_name": "Barış Karabuğa",
            "policy_number": "POL-999",
            "lat": 41.01,
            "lon": 28.98,
            "issue_desc": "Araba çalışmıyor",
        }, format="json")

        assert response.status_code == 201
        assert response.data["status"] == "Created"
        assert "id" in response.data

    def test_provider_yoksa_400_doner(self, db, api_client):
        response = api_client.post("/api/requests/", {
            "customer_name": "Barış Karabuğa",
            "policy_number": "POL-999",
            "lat": 41.01,
            "lon": 28.98,
            "issue_desc": "Araba çalışmıyor",
        }, format="json")

        assert response.status_code == 400


class TestCompleteView:

    def test_talep_tamamlanir(self, db, provider, assistance_request, api_client, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")
        from assistance.services import AssistanceService
        AssistanceService.assign_provider_atomic(assistance_request.id)

        response = api_client.post(f"/api/requests/{assistance_request.id}/complete/")

        assert response.status_code == 200
        assert response.data["status"] == "Completed"


class TestCancelView:

    def test_talep_iptal_edilir(self, db, assistance_request, api_client):
        response = api_client.post(f"/api/requests/{assistance_request.id}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "Cancelled"