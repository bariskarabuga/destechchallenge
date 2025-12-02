from celery.exceptions import MaxRetriesExceededError
import pytest
from assistance.tasks import notify_insurance_company_task
class TestNotifyTask:

    def test_basarili_bildirim(self, mocker):
        mocker.patch("time.sleep")
        mocker.patch("random.random", return_value=0.9)

        result = notify_insurance_company_task.apply(args=[42]).get()

        assert result["status"] == "success"
        assert result["request_id"] == 42

    def test_retry(self):
        assert notify_insurance_company_task.max_retries == 3
        assert notify_insurance_company_task.default_retry_delay == 10