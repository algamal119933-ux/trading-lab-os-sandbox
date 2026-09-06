# تشغيل Trading Lab OS على Windows — أسرع مسار

> هذه النسخة PAPER ONLY. لا تضف API keys حقيقية.

## 1) المتطلبات

- Windows 10/11 64-bit مدعوم لـ WSL 2.
- Docker Desktop يعمل باستخدام WSL 2 backend.

## 2) بعد فك الضغط

افتح مجلد `trading_lab_os_v1` ثم اضغط بزر الفأرة الأيمن داخل المجلد واختر **Open in Terminal** / PowerShell.

شغّل:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\START_WINDOWS.ps1
```

السكريبت يقوم تلقائيًا بـ:

- التحقق من Docker.
- إنشاء `.env` بكلمات مرور وأسرار عشوائية إذا لم يكن موجودًا.
- التأكد من أن `dry_run=true` وأن مفاتيح البورصة فارغة.
- سحب صور Docker.
- بناء metrics exporter.
- تشغيل الخدمات.

## 3) الواجهات

- Freqtrade / FreqUI: http://127.0.0.1:8080
- MLflow: http://127.0.0.1:5000
- Prometheus: http://127.0.0.1:9090
- Grafana: http://127.0.0.1:3000

بيانات Grafana تُنشأ أول مرة داخل `.env` ويطبع السكريبت كلمة المرور على الشاشة.

## 4) الإيقاف

```powershell
.\STOP_WINDOWS.ps1
```

## 5) لو التشغيل فشل

نفّذ وأرسل الناتج:

```powershell
docker version
docker compose version
docker compose ps
docker compose logs --tail=100
```
