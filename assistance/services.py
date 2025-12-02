import math
import logging
from django.db import transaction
from django.utils import timezone
from .models import AssistanceRequest, Provider, ServiceAssignment
from .tasks import notify_insurance_company_task, log_event_to_clickhouse

logger = logging.getLogger('assistance')


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class AssistanceService:

    @classmethod
    def create_request(cls, data: dict) -> AssistanceRequest:
        req = AssistanceRequest.objects.create(**data)
        logger.info("Yeni talep oluşturuldu", extra={
            'request_id': req.id,
            'customer': req.customer_name,
            'policy': req.policy_number,
        })
        return req

    @classmethod
    def find_nearest_available_provider(cls, lat: float, lon: float) -> Provider:
        providers = Provider.objects.filter(is_available=True)
        if not providers.exists():
            logger.warning("Müsait provider bulunamadı", extra={'lat': lat, 'lon': lon})
            raise Exception("No available providers found!")
        nearest = min(providers, key=lambda p: haversine(lat, lon, p.lat, p.lon))
        logger.debug("En yakın provider bulundu", extra={
            'provider_id': nearest.id,
            'provider_name': nearest.name,
        })
        return nearest

    @classmethod
    @transaction.atomic
    def assign_provider_atomic(cls, request_id: int, provider_id: int = None):
        logger.info("Provider atama başladı", extra={
            'request_id': request_id,
            'provider_id': provider_id,
        })
        req = AssistanceRequest.objects.select_for_update().get(id=request_id)

        if provider_id:
            provider = Provider.objects.select_for_update().get(id=provider_id)
        else:
            provider = cls.find_nearest_available_provider(req.lat, req.lon)
            provider = Provider.objects.select_for_update().get(id=provider.id)

        if not provider.is_available:
            logger.warning("Provider meşgul", extra={
                'request_id': request_id,
                'provider_id': provider.id,
            })
            raise Exception("Provider is busy!")

        provider.is_available = False
        provider.save()

        ServiceAssignment.objects.create(request=req, provider=provider)
        req.status = 'DISPATCHED'
        req.save()

        logger.info("Provider atandı", extra={
            'request_id': req.id,
            'provider_id': provider.id,
            'provider_name': provider.name,
        })

        transaction.on_commit(
            lambda: notify_insurance_company_task.delay(req.id)
        )

    @classmethod
    @transaction.atomic
    def complete_request(cls, request_id: int):
        req = AssistanceRequest.objects.select_for_update().get(id=request_id)
        if req.status != 'DISPATCHED':
            logger.error("Geçersiz durum geçişi — complete", extra={
                'request_id': request_id,
                'current_status': req.status,
            })
            raise Exception(f"Cannot complete a request with status: {req.status}")

        req.status = 'COMPLETED'
        req.save()

        assignment = req.assignment
        assignment.provider.is_available = True
        assignment.provider.save()

        response_sec = (timezone.now() - req.created_at).total_seconds()
        logger.info("Talep tamamlandı", extra={
            'request_id': req.id,
            'provider_id': assignment.provider.id,
            'response_sec': response_sec,
        })

        transaction.on_commit(lambda: log_event_to_clickhouse.delay(
            request_id=req.id,
            city=getattr(req, 'city', 'unknown'),
            status='COMPLETED',
            response_sec=response_sec,
            provider_id=assignment.provider.id,
        ))

    @classmethod
    @transaction.atomic
    def cancel_request(cls, request_id: int):
        req = AssistanceRequest.objects.select_for_update().get(id=request_id)
        if req.status == 'COMPLETED':
            logger.error("Tamamlanmış talep iptal edilmeye çalışıldı", extra={
                'request_id': request_id,
            })
            raise Exception("Completed requests cannot be cancelled!")

        req.status = 'CANCELLED'
        req.save()

        if hasattr(req, 'assignment'):
            req.assignment.provider.is_available = True
            req.assignment.provider.save()

        logger.info("Talep iptal edildi", extra={
            'request_id': req.id,
            'previous_status': req.status,
        })