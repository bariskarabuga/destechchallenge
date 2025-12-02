from clickhouse_driver import Client
from django.conf import settings


def get_client():
    cfg = settings.CLICKHOUSE
    return Client(
        host=cfg['host'],
        port=cfg['port'],
        database=cfg['database'],
        user=cfg['user'],
        password=cfg['password'],
    )


def create_events_table():
    """Tabloyu oluştur — uygulama başlangıcında bir kez çalıştır"""
    client = get_client()
    client.execute("""
        CREATE TABLE IF NOT EXISTS assistance_events (
            event_id      UUID,
            request_id    UInt32,
            city          String,
            status        String,
            response_sec  Float32,
            provider_id   UInt32,
            created_at    DateTime
        ) ENGINE = MergeTree()
        ORDER BY (created_at, city)
    """)


def insert_event(request_id, city, status, response_sec, provider_id):
    """Tek event yaz"""
    import uuid
    from datetime import datetime
    client = get_client()
    client.execute(
        "INSERT INTO assistance_events VALUES",
        [{
            'event_id': str(uuid.uuid4()),
            'request_id': request_id,
            'city': city,
            'status': status,
            'response_sec': response_sec,
            'provider_id': provider_id,
            'created_at': datetime.utcnow(),
        }]
    )


def get_avg_response_by_city():
    """İl bazlı ortalama yanıt süresi raporu"""
    client = get_client()
    rows = client.execute("""
        SELECT city, round(avg(response_sec), 1) as avg_sec, count() as total
        FROM assistance_events
        WHERE status = 'COMPLETED'
        GROUP BY city
        ORDER BY avg_sec DESC
    """)
    return [{'city': r[0], 'avg_sec': r[1], 'total': r[2]} for r in rows]