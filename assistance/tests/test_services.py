import pytest
from assistance.models import AssistanceRequest, Provider, ServiceAssignment
from assistance.services import AssistanceService


class TestFindNearestProvider:

    def test_en_yakin_provider_secilir(self, db, provider, far_provider):
        # İstanbul'a yakın nokta — provider (İstanbul) seçilmeli
        result = AssistanceService.find_nearest_available_provider(
            lat=41.0100, lon=28.9800
        )
        assert result.id == provider.id

    def test_musait_provider_yoksa_hata_firlatir(self, db):
        with pytest.raises(Exception, match="No available providers"):
            AssistanceService.find_nearest_available_provider(41.0, 28.9)

    def test_musait_olmayan_provider_secilmez(self, db, provider):
        provider.is_available = False
        provider.save()

        with pytest.raises(Exception, match="No available providers"):
            AssistanceService.find_nearest_available_provider(41.0, 28.9)


class TestAssignProvider:

    def test_provider_atanir(self, db, provider, assistance_request, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")

        AssistanceService.assign_provider_atomic(assistance_request.id)

        assistance_request.refresh_from_db()
        provider.refresh_from_db()

        assert assistance_request.status == "DISPATCHED"
        assert provider.is_available is False
        assert ServiceAssignment.objects.filter(request=assistance_request).exists()

    def test_mesgul_provider_atanamazr(self, db, provider, assistance_request, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")
        provider.is_available = False
        provider.save()

        with pytest.raises(Exception, match="Provider is busy"):
            AssistanceService.assign_provider_atomic(
                assistance_request.id, provider_id=provider.id
            )

    def test_celery_task_tetiklenir(self, db, provider, assistance_request, mocker):
        mock_task = mocker.patch("assistance.tasks.notify_insurance_company_task.delay")

        AssistanceService.assign_provider_atomic(assistance_request.id)

        mock_task.assert_called_once_with(assistance_request.id)


class TestCompleteRequest:

    def test_talep_tamamlanir(self, db, provider, assistance_request, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")
        AssistanceService.assign_provider_atomic(assistance_request.id)

        AssistanceService.complete_request(assistance_request.id)

        assistance_request.refresh_from_db()
        provider.refresh_from_db()

        assert assistance_request.status == "COMPLETED"
        assert provider.is_available is True  # provider serbest kaldı mı?

    def test_pending_talep_tamamlanamaz(self, db, assistance_request):
        with pytest.raises(Exception, match="Cannot complete"):
            AssistanceService.complete_request(assistance_request.id)

    def test_iptal_edilmis_talep_tamamlanamaz(self, db, assistance_request):
        assistance_request.status = "CANCELLED"
        assistance_request.save()

        with pytest.raises(Exception, match="Cannot complete"):
            AssistanceService.complete_request(assistance_request.id)


class TestCancelRequest:

    def test_pending_talep_iptal_edilir(self, db, assistance_request):
        AssistanceService.cancel_request(assistance_request.id)

        assistance_request.refresh_from_db()
        assert assistance_request.status == "CANCELLED"

    def test_dispatched_talep_iptal_edilince_provider_serbest_kalir(
        self, db, provider, assistance_request, mocker
    ):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")
        AssistanceService.assign_provider_atomic(assistance_request.id)

        AssistanceService.cancel_request(assistance_request.id)

        provider.refresh_from_db()
        assert provider.is_available is True

    def test_tamamlanmis_talep_iptal_edilemez(self, db, provider, assistance_request, mocker):
        mocker.patch("assistance.tasks.notify_insurance_company_task.delay")
        AssistanceService.assign_provider_atomic(assistance_request.id)
        AssistanceService.complete_request(assistance_request.id)

        with pytest.raises(Exception, match="cannot be cancelled"):
            AssistanceService.cancel_request(assistance_request.id)