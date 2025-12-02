from celery import shared_task
import logging
import time
import random

from .analytics import insert_event

logger = logging.getLogger('assistance')


class InsuranceAPIError(Exception):
    pass


@shared_task(bind=True, max_retries=3)
def notify_insurance_company_task(self, request_id):
    logger.info("Sigorta bildirimi başladı", extra={
        'request_id': request_id,
        'attempt': self.request.retries + 1,
        'max_retries': self.max_retries,
    })

    try:
        time.sleep(1)

        if random.random() < 0.3:
            raise InsuranceAPIError("Connection timeout")

        logger.info("Sigorta bildirimi başarılı", extra={
            'request_id': request_id,
            'attempt': self.request.retries + 1,
        })
        return {"status": "success", "request_id": request_id}

    except InsuranceAPIError as exc:
        countdown = 2 ** self.request.retries
        logger.warning("Sigorta bildirimi başarısız, yeniden denenecek", extra={
            'request_id': request_id,
            'attempt': self.request.retries + 1,
            'max_retries': self.max_retries,
            'countdown_sec': countdown,
            'error': str(exc),
        })
        raise self.retry(exc=exc, countdown=countdown)


@shared_task
def log_event_to_clickhouse(request_id, city, status, response_sec, provider_id):
    logger.debug("ClickHouse event yazılıyor", extra={
        'request_id': request_id,
        'city': city,
        'status': status,
        'response_sec': response_sec,
        'provider_id': provider_id,
    })
    try:
        insert_event(request_id, city, status, response_sec, provider_id)
        logger.info("ClickHouse event yazıldı", extra={
            'request_id': request_id,
            'status': status,
        })
    except Exception as e:
        logger.warning("ClickHouse yazma hatası (kritik değil)", extra={
            'request_id': request_id,
            'error': str(e),
        })