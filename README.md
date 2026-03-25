# TurAssist — Yol Yardım Backend Sistemi

Günde 10.000+ yardım talebini karşılayan, 81 ilde hizmet veren çekici çağırma ve sigorta entegrasyon platformu. Django REST Framework üzerine inşa edilmiş, Celery ile asenkron görev yönetimi, ClickHouse ile analitik altyapısı ve ELK Stack ile merkezi log takibi sunan ölçeklenebilir bir backend sistemi.

---

## Mimari Genel Bakış

```
Clients (Mobile / Admin / B2B)
        │
   [Nginx - Load Balancer]
        │
   ┌────┴────────────────┐
   │                     │
Django REST API      WebSocket Server
(3x replica)         (Django Channels)
   │                     │
   └────────┬────────────┘
            │
      Redis Broker
            │
      Celery Workers ──── Sigorta API (retry/fallback)
            │
   ┌────────┴────────────────┐
   │            │            │
PostgreSQL  Redis Cache  ClickHouse
(OLTP)      (TTL)        (OLAP/Analitik)
            │
   ┌────────┴────────────────┐
   │            │            │
Logstash  Elasticsearch  Kibana
(UDP 5959)  (indeks)     (dashboard)
```

**Teknoloji Seçim Gerekçeleri:**

| Bileşen | Teknoloji | Neden |
|---|---|---|
| API | Django REST Framework | Hızlı geliştirme, güçlü ORM, admin panel |
| Async görev | Celery + Redis | Sigorta bildirimlerini ana akıştan izole eder |
| Load balancer | Nginx `least_conn` | En az bağlantılı instance'a yönlendirir |
| Operasyonel DB | PostgreSQL | ACID garantisi, `SELECT FOR UPDATE` desteği |
| Analitik DB | ClickHouse | Kolon bazlı depolama, 50M satırı saniyeler içinde tarar |
| Cache | Redis | Provider listesi TTL cache, Celery broker |
| Log takibi | ELK Stack | Merkezi log yönetimi, Kibana ile filtreleme ve analiz |
| Container | Docker Compose | Tekrarlanabilir ortam, servis izolasyonu |

---

## Ön Gereksinimler

- Docker >= 24.0
- Docker Compose V2 (`docker compose` — tire olmadan)
- 4GB+ RAM (ClickHouse + Elasticsearch için)

```bash
docker --version          # Docker version 24+
docker compose version    # Docker Compose version v2+
```

---

## Kurulum

### 1. Repoyu klonla

```bash
git clone <repo-url>
cd destechchallenge
```

### 2. Ortam değişkenlerini ayarla

```bash
cp .env.example .env
```

`.env` içeriği:

```env
SECRET_KEY=django-insecure-challenge
DEBUG=True
ALLOWED_HOSTS=*

# Database
DATABASE_URL=postgresql://appuser:apppassword@db:5432/appdb

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# ClickHouse
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
CLICKHOUSE_DB=turassist
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# Logstash
LOGSTASH_HOST=logstash
LOGSTASH_PORT=5959
```

### 3. Servisleri ayağa kaldır

```bash
docker compose up --build
```

İlk çalıştırmada şu servisler ayağa kalkar:

| Servis | Port | Açıklama |
|---|---|---|
| nginx | 80 | Load balancer — dışarıya açık tek port |
| web1, web2, web3 | 8000 (iç) | Django REST API replicalari |
| db | 5432 (iç) | PostgreSQL |
| redis | 6379 (iç) | Broker + cache |
| celery | — | Async worker |
| clickhouse | 9000 (iç) | Analitik DB |
| elasticsearch | 9200 (iç) | Log indeksleme |
| logstash | 5959/udp (iç) | Log pipeline |
| kibana | 5601 | Log dashboard |

### 4. Veritabanını hazırla

```bash
# Migrasyonları çalıştır
docker compose exec web1 python manage.py migrate

# Superuser oluştur
docker compose exec web1 python manage.py createsuperuser

# ClickHouse tablosunu oluştur
docker compose exec web1 python -c "
from assistance.analytics import create_events_table
create_events_table()
print('ClickHouse tablosu hazır')
"
```

### 5. Kibana index pattern oluştur

```
http://localhost:5601 → Management → Index Patterns → Create → turassist-logs-*
```

### 6. Test verisi ekle

```bash
docker compose exec web1 python manage.py shell -c "
from assistance.models import Provider
Provider.objects.create(name='Barış Karabuğa', phone='05469089889', lat=41.01, lon=28.98, is_available=True)
Provider.objects.create(name='Barış Karabuğa 1', phone='05469089889', lat=41.05, lon=29.01, is_available=True)
print('Providerlar eklendi:', Provider.objects.count())
"
```

---

## API Referansı

Swagger UI: `http://localhost/api/docs/`
ReDoc: `http://localhost/api/redoc/`

### Endpoint'ler

#### `POST /api/requests/` — Yeni yardım talebi

```bash
curl -X POST http://localhost/api/requests/ \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Barış Karabuğa",
    "policy_number": "POL-001",
    "lat": 41.01,
    "lon": 28.98,
    "issue_desc": "Lastiğim patladı"
  }'
```

**Başarılı yanıt (201):**
```json
{ "status": "Created", "id": 1 }
```

**İş mantığı:** Haversine formülü ile en yakın müsait provider bulunur → `SELECT FOR UPDATE` ile kilitlenir → atomic transaction içinde atanır → Celery kuyruğuna sigorta bildirimi düşer.

---

#### `POST /api/requests/{id}/complete/` — Talebi tamamla

```bash
curl -X POST http://localhost/api/requests/1/complete/
```

Sadece `DISPATCHED` durumundaki talepler tamamlanabilir. Provider `is_available=True` yapılır, ClickHouse'a analitik event yazılır.

---

#### `POST /api/requests/{id}/cancel/` — Talebi iptal et

```bash
curl -X POST http://localhost/api/requests/1/cancel/
```

`COMPLETED` talepler iptal edilemez. Atanmış provider varsa serbest bırakılır.

---

### Durum Makinesi

```
PENDING ──→ DISPATCHED ──→ COMPLETED
   │              │
   └──────────────┴──→ CANCELLED
```

---

## Race Condition Koruması

Aynı anda iki farklı talep aynı provider'ı kapmaya çalıştığında sistem tutarlı kalır:

```python
@transaction.atomic
def assign_provider_atomic(cls, request_id, provider_id=None):
    req = AssistanceRequest.objects.select_for_update().get(id=request_id)
    provider = Provider.objects.select_for_update().get(id=provider.id)
    # Veritabanı kilidi — ikinci istek burada bekler
    ...
```

`SELECT FOR UPDATE` PostgreSQL satır kilidi kullanır. Transaction başarıyla kapanana kadar başka bir işlem aynı provider'a erişemez.

---

## Celery & Retry Mekanizması

Sigorta API'si hata verirse **Exponential Backoff** stratejisi ile tekrar denenir:

| Deneme | Bekleme |
|---|---|
| 1. retry | 2 sn |
| 2. retry | 4 sn |
| 3. retry | 8 sn |
| Sonrası | `MaxRetriesExceededError` |

Celery loglarını izlemek için:

```bash
docker compose logs -f celery
```

---

## Log Takibi — ELK Stack

Tüm uygulama logları merkezi olarak ELK Stack üzerinden yönetilir. Django, `python-logstash` kütüphanesi ile logları UDP üzerinden Logstash'e gönderir. Logstash bunları Elasticsearch'e indeksler, Kibana üzerinden görselleştirilir.

```bash
# Kibana dashboard
http://localhost:5601

# Logstash durumu
docker compose logs -f logstash

# Elasticsearch sağlık kontrolü
curl http://localhost:9200/_cluster/health
```

Kibana'da yapılabilecekler:

- `request_id` ile bir talebin baştan sona tüm log akışını takip etmek
- Son 1 saatteki `ERROR` loglarını listelemek
- Sigorta bildirimi retry sayısını grafik olarak izlemek
- Provider atama sürelerini histogram olarak görmek

---

## Yük Dengeleme

Nginx `least_conn` algoritması ile 3 Django instance'ına dağıtım:

```bash
# 6 istek gönder, logda 3 farklı instance gözükecektir.
for i in {1..6}; do
  curl -s -X POST http://localhost/api/requests/ \
    -H "Content-Type: application/json" \
    -d '{"customer_name":"Test","policy_number":"POL-001","lat":41.01,"lon":28.98,"issue_desc":"test"}'
  echo
done

# Instance loglarını izle
docker compose logs -f web1 web2 web3
```

---

## Testler

```bash
# Tüm testleri çalıştır
docker compose exec web1 pytest -v

# Coverage raporu
docker compose exec web1 pytest --cov=assistance --cov-report=term-missing

# Sadece belirli modül
docker compose exec web1 pytest assistance/tests/test_services.py -v
```

**Test kapsamı:**

| Modül | Test Sayısı | Kapsam |
|---|---|---|
| `test_services.py` | 10 | Provider bulma, atama, tamamlama, iptal |
| `test_views.py` | 4 | API endpoint'leri, HTTP durum kodları |
| `test_tasks.py` | 2 | Celery task başarı ve retry konfigürasyonu |

---

## Operasyonel Komutlar

```bash
# Tüm servisleri başlat
docker compose up -d

# Servisleri durdur (veriyi koru)
docker compose stop

# Servisleri durdur ve sil (veriyi koru)
docker compose down

# Veriyle birlikte tamamen sil
docker compose down -v

# Belirli servisi yeniden başlat
docker compose restart celery

# Servis durumlarını gör
docker compose ps

# Canlı log izle
docker compose logs -f

# Django shell
docker compose exec web1 python manage.py shell

# ClickHouse bağlantı testi
docker compose exec clickhouse clickhouse-client --query "SELECT 1"

# Elasticsearch sağlık kontrolü
curl http://localhost:9200/_cluster/health
```

---

## Proje Yapısı

```
destechchallenge/
├── config/
│   ├── settings.py       # Django ayarları
│   ├── urls.py           # Ana URL routing
│   └── wsgi.py
├── assistance/
│   ├── models.py         # Provider, AssistanceRequest, ServiceAssignment
│   ├── services.py       # İş mantığı — find_nearest, assign, complete, cancel
│   ├── tasks.py          # Celery görevleri — sigorta bildirimi, ClickHouse
│   ├── analytics.py      # ClickHouse client ve sorgular
│   ├── views.py          # DRF API view'ları
│   ├── urls.py           # Endpoint tanımları
│   ├── admin.py          # Django admin kayıtları
│   └── tests/
│       ├── test_services.py
│       ├── test_views.py
│       └── test_tasks.py
├── nginx.conf            # Load balancer konfigürasyonu
├── logstash.conf         # Logstash pipeline konfigürasyonu
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── conftest.py
└── .env
```