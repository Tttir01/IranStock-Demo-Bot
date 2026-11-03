# طراحی اتصال به معامله واقعی — IranStock-Demo-Bot

> **وضعیت:** فقط طراحی · **حالت اجرا همچنان:** `DRY_RUN` / `PAPER` · **تاریخ:** ۲۰۲۶-۱۱-۰۳  
> این سند هیچ کلیدی را فعال نمی‌کند، هیچ endpoint حدسی را مستند نمی‌کند و هیچ سفارشی ارسال نمی‌کند. اجرای زنده منوط به دریافت مستندات رسمی و sandbox از کارگزاری و امضای انسانی خارج از کد است.

---

## ۱) چکیده

ربات امروز فقط داده می‌خواند و سیگنال می‌سازد؛ `AgahBroker` هر سفارش غیر `DRY_RUN` را با `BLOCKED` برمی‌گرداند. ریشه مشکل فعلی کیفیت سیگنال است نه اتصال: با مسیر `Tindex` سه مؤلفه امتیاز صفر می‌مانند و آستانه ۸۰ عملاً دست‌نیافتنی است [جدول امتیاز در `docs/review.md`]. بنابراین مسیر درست دوگانه است:

| فاز | ارزش | ریسک |
|---|---|---|
| **الف) این سند (طراحی)** | بالا — از بدفهمی و حدسِ پرخطر جلوگیری می‌کند | صفر |
| **ج) Shadow Mode + کالیبراسیون آستانه** | بالاترین — تنها انسداد واقعی را با داده برطرف می‌کند | صفر (فقط لاگ) |
| (ب) اسکلت LiveGateway | فعلاً پایین — بدون مستندات رسمی اعتماد کاذب می‌دهد | بالا |

**جمع‌بندی توصیه:** پیاده‌سازی اتصال زنده تا پیش از کامل شدن (ج) و دریافت مستندات رسمی، **عمداً به تعویق می‌افتد.**

---

## ۲) اهداف و غیراهداف

### اهداف
- قرارداد یکسان برای هر کارگزاری آینده (`BrokerGateway`)
- فهرست گیت‌های ایمنی قبل از هر ارسال
- نگهداری سوابق قابل‌حسابرسی و قابلیت توقف اضطراری
- مسیری قابل‌اثبات از `PAPER → SHADOW → CANARY (سرمایه خرد) → SCALE`

### غیراهداف (صریحاً انجام **نمی‌شود**)
1. حدس یا ابداع endpoint کارگزاری (مثلاً `api.agah.com/order/place` تخیلی).
2. دور زدن MFA، کپچا، ضدربات، یا برداشت توکن از حافظه مرورگر/اپلیکیشن.
3. نگه‌داری کلید/توکن در کد، `data.json`، لاگ، یا داشبورد.
4. تغییر `TRADING_MODE` به `LIVE` از داخل کد یا workflow.
5. سفارش Market بی‌حد، سفارش بدون `clientOrderId` یکتا، یا سفارش بدون سقف ریالی روزانه.
6. اجرای زنده روی GitHub Actions (جای آن VPS اختصاصی با IP ثابت).

> هر درخواست برای موارد بالا رد می‌شود و به این بند ارجاع داده خواهد شد.

---

## ۳) معماری فعلی و پیشنهادی

### امروز
```
TSETMC ─┬─► scanner.analyze_symbol ─► signal_engine.score_signal ─► main._paper_actions
Tindex ─┤                                                      ├─► PaperAccount (مجازی)
BrsApi ─┘                                                      ├─► AgahBroker (DRY_RUN فقط)
                                                              └─► dashboard + Telegram
```

### پیشنهادی (با Gateway)
```
scanner/signal ─► RiskManager ─► BrokerGateway (interface)
                       │                ├─► PaperGateway   (امروز، تست‌ها)
                       │                └─► LiveGateway    (آینده، پس از تأیید)
                       └─► ShadowLogger (همیشه، بدون ریسک)
                              └─► Evaluator (بازده 5/10/20 روزه، تحلیل آستانه)
```

انتخاب کارگزاری در زمان اجرا فقط از روی پیکربندی امن:
```
BROKER_GATEWAY = PAPER | LIVE   (پیش‌فرض PAPER)
BROKER_NAME    = AGAH | MOFID | ... (فقط برای انتخاب پیاده‌سازی)
TRADING_MODE   = DRY_RUN | LIVE (باید هر دو LIVE باشند تا ارسال مجاز شود)
```

---

## ۴) قرارداد `BrokerGateway`

قرارداد به‌صورت کلاس انتزاعی تعریف می‌شود؛ هر کارگزاری آن را پیاده می‌کند. امضاها عمداً حداقلی و کارگزاری-ناآگاه هستند تا از نشت جزئیات احراز هویت به منطق سیگنال جلوگیری شود.

```python
class BrokerGateway(ABC):
    name: str                          # "AGAH" | "MOFID" | ...

    def submit_order(self, req: OrderRequest) -> OrderResult: ...
    def cancel_order(self, client_order_id: str) -> CancelResult: ...
    def order_status(self, client_order_id: str) -> OrderStatus: ...
    def positions(self) -> list[Position]: ...
    def account(self) -> AccountStatus: ...
    def health(self) -> HealthStatus: ...
```

### ۴.۱ `OrderRequest`
```python
@dataclass(frozen=True)
class OrderRequest:
    symbol: str              # نماد بورسی، مثلاً "فولاد"
    side: str                # "BUY" | "SELL"
    quantity: int            # تعداد سهم، >0 و مضرب lot کارگزاری
    price: float             # تومان، سفارش فقط Limit (بدون Market)
    client_order_id: str     # یکتای سراسری: {YYYYMMDD}-{SYMBOL}-{SIDE}-{ULID}
    tif: str = "DAY"         # Time-in-force
    tag: str = "IS-Demo-v2"  # برای حسابرسی
```

### ۴.۲ `OrderResult` / `OrderStatus`
```python
@dataclass
class OrderResult:
    ok: bool
    status: str              # "ACKED" | "REJECTED" | "BLOCKED" | "DRY_RUN"
    broker_order_id: str | None
    client_order_id: str
    message: str              # فارسی، قابل‌نمایش در داشبورد/تلگرام

@dataclass
class OrderStatus:
    status: str              # "PENDING" | "FILLED" | "PARTIAL" | "CANCELLED" | "REJECTED"
    filled_qty: int
    avg_price: float | None
    last_update: str         # ISO-8601
```

### ۴.۳ `PaperGateway` (امروز)

- سفارش را در `PaperAccount` ثبت می‌کند (`buy`/`sell` موجود).
- همیشه `status=DRY_RUN` برمی‌گرداند و لاگ `AGAH DRY_RUN | ...` می‌نویسد.
- تست‌ها فقط با همین پیاده‌سازی اجرا می‌شوند؛ هیچ شبکه‌ای لازم نیست.

### ۴.۴ `LiveGateway` (آینده، **هنوز پیاده نمی‌شود**)

شرط ورود به پیاده‌سازی:
1. **مستندات رسمی** کارگزاری با آدرس پایه، مسیر احراز هویت، و نمونه cURL/Postman رسمی.
2. **حساب sandbox** یا محیط تست با داده واقعی/شبیه‌سازی‌شده.
3. تأیید کتبی واحد فنی کارگزاری که کلید ارائه‌شده برای API سفارش مجاز است.
4. `AGAH_API_BASE`, `AGAH_AUTH_URL` فقط از Secret محیط خوانده شوند؛ هرگز hardcode نشوند.

رفتار الزامی:
- هر `submit_order` باید پیش از خروج از فرآیند، از ۷ گیت جدول بخش ۶ عبور کند.
- هر پاسخ کارگزاری با `broker_order_id` ذخیره و با `client_order_id` تطبیق داده شود.
- خطای شبکه → `REJECTED` با دلیل، نه تکرار بی‌نهایت (حداکثر ۱ retry با idempotency).

---

## ۵) چک‌لیست دسترسی per-broker

برای هر کارگزاری (آگاه، مفید، فارابی، ...) همین چک‌لیست جداگانه پر می‌شود:

| ردیف | مدرک | وضعیت | توضیح |
|---|---|---|---|
| ۱ | مستندات رسمی API سفارش (PDF/پورتال توسعه‌دهندگان) | ☐ | آدرس، نسخه، تاریخ اعتبار |
| ۲ | آدرس پایه رسمی (`https://...`) | ☐ | هرگز IP/دامنه حدسی |
| ۳ | روش احراز هویت (OAuth2 / API-Key + Secret / ...) | ☐ | شامل چرخه refresh و انقضا |
| ۴ | محدودیت نرخ (rate limit) | ☐ | درخواست/ثانیه، رفتار 429 |
| ۵ | محیط sandbox / تست | ☐ | حساب تست + نماد تست |
| ۶ | لیست خطاهای استاندارد کارگزاری | ☐ | کد → ترجمه فارسی |
| ۷ | تأیید کتبی دسترسی سفارش | ☐ | ایمیل/نامه رسمی |
| ۸ | تماس فنی اضطراری | ☐ | تلفن/ایمیل on-call |

> بدون تیک ردیف‌های ۱–۳ و ۷، حتی اسکلت `LiveGateway` نوشته نمی‌شود.

---

## ۶) گیت‌های ایمنی (Safety Gates)

هیچ سفارشی بدون عبور از **همه** گیت‌ها ارسال نمی‌شود. ترتیب اجرا ثابت است:

| # | گیت | شرط عبور | در صورت رد |
|---|---|---|---|
| G1 | `TRADING_MODE == LIVE` **و** `BROKER_GATEWAY == LIVE` | هر دو از env، با مقدار پیش‌فرض `DRY_RUN`/`PAPER` | `BLOCKED` + لاگ هشدار |
| G2 | تأیید انسانی خارج از کد | فایل `data/live-ack.json` با امضای `I-ACCEPT-REAL-MONEY-RISK` + تاریخ + شناسه تأییدکننده | `BLOCKED` |
| G3 | Kill Switch خاموش | `data/kill-switch` وجود **ندارد** | `BLOCKED` |
| G4 | نماد در `ALLOWLIST` | `ALLOWED_SYMBOLS` (مثلاً ۱۰ نماد فعلی) | `REJECTED` |
| G5 | سقف ریالی روزانه | مجموع سفارش‌های امروز < `DAILY_RIAL_CAP` | `REJECTED` |
| G6 | سقف تعداد سفارش | `orders_today < MAX_ORDERS_PER_DAY` (مثلاً ۱۰) | `REJECTED` |
| G7 | فقط سفارش Limit با قیمت معتبر | `price>0` و `price` در بازه مجاز تابلو (±۵٪) | `REJECTED` |
| G8 | Idempotency | `client_order_id` یکتاست و قبلاً ارسال نشده | `REJECTED` (تکراری) |

گیت‌ها در `RiskManager` متمرکز می‌شوند تا `LiveGateway` نتواند آن‌ها را دور بزند.

---

## ۷) سناریوهای شکست

| سناریو | تشخیص | واکنش | ثبت |
|---|---|---|---|
| TSETMC/Tindex قطع است | `analyze_symbol → UNAVAILABLE` | هیچ سفارش جدید؛ موقعیت‌های باز نگه‌داشته شوند | `scan_results.provider=UNAVAILABLE` |
| سفارش نیمه‌پر (Partial Fill) | `order_status.filled_qty < quantity` | نگه‌داری `filled_qty`؛ تصمیم بعدی فقط با `filled_qty` | `data/broker-audit.jsonl` |
| ۴۲۹ Rate Limit | HTTP 429 | توقف ۶۰ ثانیه، سپس ۱ retry با همان `client_order_id` | لاگ هشدار |
| انقضای توکن | 401 | تلاش ۱باره refresh؛ در شکست، توقف سفارش‌گذاری و آلارم تلگرام | لاگ خطا |
| اختلاف موجودی کارگزاری و Paper | مغایرت `account()` vs `positions()` | آلارم + `kill-switch` پیشنهادی | گزارش تطبیق روزانه |
| انتشار اشتباه روی GitHub Actions | `GITHUB_ACTIONS==true` | هر `LiveGateway` در CI خودکار `BLOCKED` می‌شود | لاگ `BLOCKED: CI is not a trading host` |
| دستور `kill-switch` | فایل `data/kill-switch` ساخته شد | همه ارسال‌ها `BLOCKED` تا حذف دستی | بنر قرمز در داشبورد |

---

## ۸) نگهداری سوابق و تطبیق

- **Append-only audit:** `data/broker-audit.jsonl` — هر `submit/cancel/status` با `time, client_order_id, broker_order_id, symbol, side, qty, price, result`.
- **Shadow log:** `data/shadow-signals.jsonl` — هر اجرا، هر نماد، حتی وقتی `action=NO_TRADE` (برای تحلیل آستانه).
- **تطبیق روزانه:** اسکریپت `scripts/reconcile.py` (آینده) موجودی `account()` را با جمع `positions()` مقایسه می‌کند؛ مغایرت >۱٪ آلارم می‌دهد.
- **نگهداری:** لاگ‌ها ۹۰ روز نگه‌داری، سپس آرشیو فشرده؛ هرگز روی `main` کامیتِ دستیِ سفارش زنده انجام نمی‌شود.

---

## ۹) استقرار

| محیط | مجاز برای LIVE | توضیح |
|---|---|---|
| لپ‌تاپ/سرور شخصی | خیر (فقط Paper) | IP متغیر، ریسک گم‌شدن کلید |
| GitHub Actions | **هرگز** | لاگ عمومی، Secret در معرض نشت، زمان‌بندی غیرقطعی |
| VPS اختصاصی (Ubuntu, IP ثابت) | بله | فایروال خروجی فقط به دامنه رسمی کارگزاری، دیسک رمزگذاری‌شده |
| Systemd service + logrotate | بله | `Restart=on-failure`, `EnvironmentFile=/etc/is-demo/secrets.env` با دسترسی 600 |

کلیدها فقط از `EnvironmentFile` یا Secret Manager ابری خوانده می‌شوند؛ هرگز در `.env` کامیت‌شده یا `dashboard/data.json`.

---

## ۱۰) نقشه راه فازی

```
فاز 0 (امروز): PAPER + Shadow Logger ──────────────────────────►
  └─► هر اجرا: scan → PaperAccount → shadow-signals.jsonl → dashboard
فاز 1 (۲–۴ هفته): کالیبراسیون آستانه با Evaluator
  └─► تحلیل بازده 5/10/20 روزه برای آستانه‌های 55..80
  └─► تصمیم: آستانه جدید یا تکمیل داده حجم/جریان Tindex
فاز 2 (پس از مستندات): LiveGateway اسکلت + sandbox
  └─► فقط submit/cancel/status با گیت‌های G1..G8
فاز 3: Canary (۱ نماد، سرمایه خرد، ۲ هفته)
فاز 4: گسترش تدریجی با سقف ریالی و مانیتورینگ تطبیق
```

عبور از هر فاز نیاز به تأیید انسانی و ثبت در `docs/live-integration-design.md` (بخش تاریخچه تصمیم) دارد.

---

## ۱۱) تاریخچه تصمیم

| تاریخ | تصمیم | دلیل |
|---|---|---|
| ۲۰۲۶-۱۱-۰۳ | اتصال زنده به تعویق افتاد | نبود مستندات رسمی + آستانه ۸۰ غیرقابل‌دسترس (بیشینه ۵۵ در داده واقعی) |
| ۲۰۲۶-۱۱-۰۳ | Shadow Mode تصویب شد | تنها راه اثبات سودآوری بدون ریسک مالی |

---

## ۱۲) پیوست — نمونه `client_order_id`

```
20261103-فولاد-BUY-01JCE3X5K9Q2H7M4N8P6
│         │     │   └─ ULID یکتا
│         │     └───── جهت
│         └─────────── نماد
└───────────────────── تاریخ شمسی/میلادی اجرا
```

این شناسه در هر دو سوی کارگزاری و حسابرسی کلید اصلی است؛ تکرار آن به معنی سفارش تکراری و مردود است.
