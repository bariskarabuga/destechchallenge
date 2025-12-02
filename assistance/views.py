from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiExample
from .services import AssistanceService


class AssistanceRequestCreateView(APIView):

    @extend_schema(
        summary="Yeni yardım talebi oluştur",
        description="Müşterinin konumuna en yakın müsait provider'ı otomatik atar.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "example": "Barış Karabuğa"},
                    "policy_number": {"type": "string", "example": "POL-001"},
                    "lat": {"type": "number", "example": 41.01},
                    "lon": {"type": "number", "example": 28.98},
                    "issue_desc": {"type": "string", "example": "Lastiğim patladı"},
                },
                "required": ["customer_name", "policy_number", "lat", "lon", "issue_desc"],
            }
        },
        responses={
            201: {"description": "Talep oluşturuldu ve provider atandı"},
            400: {"description": "Hata — müsait provider yok veya geçersiz veri"},
        },
        examples=[
            OpenApiExample(
                "Başarılı yanıt",
                value={"status": "Created", "id": 1},
                response_only=True,
                status_codes=["201"],
            )
        ],
    )
    def post(self, request):
        data = request.data
        try:
            assistance_req = AssistanceService.create_request(data)
            AssistanceService.assign_provider_atomic(assistance_req.id)
            return Response(
                {"status": "Created", "id": assistance_req.id},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AssistanceRequestCompleteView(APIView):

    @extend_schema(
        summary="Talebi tamamla",
        description="Sadece DISPATCHED durumdaki talepler tamamlanabilir. Provider müsait hale gelir.",
        responses={
            200: {"description": "Talep tamamlandı"},
            400: {"description": "Geçersiz durum geçişi"},
            501: {"description": "Henüz implemente edilmedi"},
        },
    )
    def post(self, request, request_id):
        try:
            AssistanceService.complete_request(request_id)
            return Response({"status": "Completed"}, status=status.HTTP_200_OK)
        except NotImplementedError:
            return Response({"error": "Not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AssistanceRequestCancelView(APIView):

    @extend_schema(
        summary="Talebi iptal et",
        description="COMPLETED talepler iptal edilemez. Atanmış provider varsa serbest bırakılır.",
        responses={
            200: {"description": "Talep iptal edildi"},
            400: {"description": "Tamamlanmış talep iptal edilemez"},
        },
    )
    def post(self, request, request_id):
        try:
            AssistanceService.cancel_request(request_id)
            return Response({"status": "Cancelled"}, status=status.HTTP_200_OK)
        except NotImplementedError:
            return Response({"error": "Not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)