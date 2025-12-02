import django
import pytest
from django.conf import settings


def pytest_configure():
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'ATOMIC_REQUESTS': False,
    }


@pytest.fixture
def provider(db):
    from assistance.models import Provider
    return Provider.objects.create(
        name="Barış Karabuğa",
        phone="05469089889",
        lat=41.0082,
        lon=28.9784,
        is_available=True,
    )


@pytest.fixture
def far_provider(db):
    from assistance.models import Provider
    return Provider.objects.create(
        name="Uzak Çekici",
        phone="05009999999",
        lat=37.8746,
        lon=32.4932,
        is_available=True,
    )


@pytest.fixture
def assistance_request(db):
    from assistance.models import AssistanceRequest
    return AssistanceRequest.objects.create(
        customer_name="Test Müşteri",
        policy_number="POL-001",
        lat=41.0100,
        lon=28.9800,
        issue_desc="Lastiğim patladı",
    )