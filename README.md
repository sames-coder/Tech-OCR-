# Tech OCR — BankXat

Bank xatlari, arxivlar va skaner hujjatlaridan karta ma'lumotlarini
lokal va audit qilinadigan tarzda ajratish tizimi.

Hozirgi versiya loyiha poydevorini taqdim etadi:

- lokal web boshqaruv paneli;
- kompyuterdan bir nechta fayl tanlash yoki drag-and-drop orqali lokal yuklash;
- konfiguratsiya va Pydantic ma'lumot modellari;
- SHA-256 asosidagi fayl inventarizatsiyasi va deduplikatsiya;
- PDF, DOCX, matn va rasmlardan lokal matn olish;
- skanerlar uchun kontrast, median-filter, Otsu binarizatsiyasi va 2x upscale;
- bir nechta Tesseract PSM natijasidan sifat bo'yicha eng yaxshisini tanlash;
- ixtiyoriy PP-OCRv5/PaddleOCR ikkinchi engine va OCR konsensusi;
- eski DOC fayllarni LibreOffice orqali DOCX'ga aylantirish;
- DOCX ichiga joylangan rasmlarni OCR qilish;
- ZIP, RAR va 7z arxivlarini xavfsiz, rekursiv ochish;
- barcha to'liq kartalarni Luhn orqali tekshirib, roli bilan `results.json`ga yozish;
- ixtiyoriy lokal AI yordamchi bilan xat mazmunidan jo'natuvchi va qabul qiluvchini aniqlash;
- SQLite holat bazasi;
- PII qiymatlarini maskalovchi logging;
- Luhn, maskalangan karta va PINFL format validatsiyasi;
- lokal vositalarni tekshiruvchi `selftest`;
- unit va API testlari.

## Ishga tushirish

Python 3.11 yoki yangiroq versiya kerak.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
bankxat selftest
bankxat web
```

Brauzerda `http://127.0.0.1:8765` manzilini oching. Server faqat localhost'ga
bog'lanadi; bank ma'lumotlari tashqi tarmoqqa yuborilmaydi.

Dashboarddagi yagona `Tanlash` tugmasi orqali PDF, Word, rasm, ZIP, RAR, 7z yoki
butun papkani qo'shish mumkin. Tanlovdan keyin `Skanerlashni boshlash` tugmasi
qayta ishlashni ishga tushiradi.
Yuklamalar alohida lokal batch papkasida saqlanadi; standart chegara har bir
fayl uchun 50 MB va bir batch uchun 500 fayl.

Luhn tekshiruvidan o'tgan barcha kartalar `output/results.json` fayliga atomik yoziladi.
To'liq qiymat himoyalangan (`0600`) JSON'da va faqat `127.0.0.1` lokal dashboardida
ko'rinadi. Javoblar cache qilinmaydi va tashqi resurslar CSP bilan bloklanadi.
Shubhali topilmalar `output/review_queue.json`ga
yoziladi.

Standart `card_role_strategy = "pair_order"` rejimida ham rol birinchi navbatda
xatdagi yo'nalish iboralari (`kartadan`, `kartaga`, `отправитель`, `получатель`,
`с карты`, `на карту` va boshqalar) hamda lokal AI dalili bilan aniqlanadi.
Karta tartibi faqat mazmun yetarli bo'lmaganida past ishonchli zaxira taxminidir;
bunday natija avtomatik ravishda tekshiruv navbatiga tushadi. Luhn tekshiruvidan
o'tgan barcha pozitsiyalar JSON'ga saqlanadi.
OCR orqali olingan karta ham saqlanadi, ammo konsensus yo'q bo'lsa tekshiruv talab
qiluvchi topilma sifatida belgilanadi. Dashboard natijalarni fayl bo'yicha guruhlaydi;
karta ustiga kursor olib borilganda tegishli manba matni va sahifa ko'rsatiladi.

## Lokal AI yordamchi

AI yordamchi asosiy pipeline'ni almashtirmaydi. OCR, karta qidirish, Luhn va matn
qoidalari doim mustaqil ishlaydi. Ollama o'rnatilmagan, model javob bermagan, vaqt
tugagan yoki javob schema tekshiruvidan o'tmagan holatda hujjat qayta ishlanishi
to'xtamaydi va odatiy natija saqlanadi.

Yordamchi faqat OCR avval topgan kartalar orasidan tanlashi mumkin. Qabul qiluvchi
va jo'natuvchi roli faqat AI keltirgan dalil parchasi asl xat matnida mavjud bo'lsa
qabul qilinadi. Matn qoidasi va AI qarama-qarshi xulosa bersa, tizim rolni taxmin
qilmaydi va kartani qo'lda tekshirishga yuboradi. Server faqat `127.0.0.1` dagi
Ollama manziliga ulanishga ruxsat beradi.

AI yordamchini ishga tushirish uchun Ollama'ni o'rnating va lokal modelni tayyorlang:

```bash
ollama pull qwen3:1.7b
ollama serve
bankxat selftest
```

Sozlamalar `config/default.toml` ichidagi `[ai]` bo'limida turadi. `enabled = false`
qilinganda yordamchi butunlay chetlab o'tiladi va loyiha avvalgi algoritm bilan ishlaydi.

Dashboard kartani to'liq ko'rsatadi, fayl/rol bo'yicha filterlaydi, raqamni nusxalash
va dalil oynasida manba matni, sahifa hamda foydalanuvchiga tushunarli tekshiruv
holatini ko'rish imkonini beradi. PINFL kabi boshqa identifikatorlar dalil matnida
yashiriladi.

## Kengaytirilgan OCR

Standart o'rnatishda tarmoqsiz Tesseract multi-pass pipeline ishlaydi. PaddleOCR 3.x
qo'llab-quvvatlanadigan muhitda ixtiyoriy ikkinchi engine sifatida o'rnatiladi:

```bash
python -m pip install -e '.[ocr]'
```

So'ng `config/default.toml` ichida `paddle_enabled = true` qilinadi. Modellar ish
vaqtida internetdan yuklanmasligi uchun ular o'rnatish bosqichida oldindan tayyorlanishi
kerak. PaddlePaddle'ning macOS/Apple Silicon mosligi rasmiy wheel mavjudligiga bog'liq;
u yo'q bo'lsa tizim Tesseract bilan ishlashda davom etadi.

Dashboarddagi `Barcha ma'lumotlarni tozalash` amali natijalar, review navbati,
skanerlash tarixi va platformaga yuklangan nusxalarni o'chiradi. Amal tasdiqlash
oynasi bilan himoyalangan va kompyuterdagi asl hujjatlarga tegmaydi.

## CLI

```bash
bankxat scan --input /xatlar/papkasi
bankxat web --host 127.0.0.1 --port 8765
bankxat selftest
```

`scan` hozircha xavfsiz inventarizatsiya bosqichini bajaradi. OCR va to'liq pipeline
keyingi qatlamlarda shu holat bazasi ustiga ulanadi.

## Xavfsizlik

- Haqiqiy bank ma'lumotlarini repozitoriyga joylamang.
- `data/`, `output/`, SQLite va natija fayllari Git'dan chiqarilgan.
- Loglarda to'liq karta va PINFL ko'rsatilmaydi.
- Web serverni `0.0.0.0` manzilida ishlatish tavsiya etilmaydi.
