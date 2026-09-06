# Trading Lab OS v1.0.1 — Paper-Only

حزمة بداية عملية لبناء معمل تداول مفتوح المصدر قابل للتحقق، **وليس بوت أرباح جاهزًا**.


## Windows: أسرع تشغيل

بعد تثبيت وتشغيل Docker Desktop، افتح PowerShell داخل مجلد المشروع ونفّذ:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\START_WINDOWS.ps1
```

راجع `RUN_WINDOWS_AR.md` للتفاصيل.

## الهدف

فصل البحث عن التنفيذ، ومنع أي استراتيجية أو نموذج AI من الوصول المباشر إلى أموال حقيقية.
الإصدار v1 يعمل في `dry_run` فقط ويعطيك:

- Freqtrade للتشغيل التجريبي والـ backtesting.
- FreqUI عبر API محلي فقط.
- MLflow لتسجيل التجارب والنماذج.
- Prometheus + Grafana للمراقبة.
- Exporter قراءة فقط من Freqtrade API.
- Paper Guard يمنع التشغيل لو تم تعطيل `dry_run` أو تفعيل force-entry.
- استراتيجية `PlumbingSmokeStrategy` لاختبار البنية فقط؛ **ليست توصية ولا Strategy متوقع منها الربح**.

## لماذا Paper-Only؟

قبل أي أموال حقيقية يجب أن تمر الاستراتيجية على الأقل عبر:

1. Backtest
2. Lookahead analysis
3. Recursive analysis
4. Out-of-sample / Walk-forward
5. رسوم + spread + slippage assumptions
6. Paper trading لفترة كافية
7. مراجعة المخاطر والـ kill-switches

## المتطلبات

- Ubuntu / Linux أو Windows مع WSL2
- Docker Engine + Docker Compose v2
- Git اختياري

## تشغيل سريع

```bash
cp .env.example .env
cp freqtrade/user_data/config.paper.json.example freqtrade/user_data/config.json
python3 scripts/paper_guard.py

docker compose up -d
```

بعد التشغيل:

- Freqtrade / FreqUI: `http://127.0.0.1:8080`
- MLflow: `http://127.0.0.1:5000`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`

كلمة مرور Grafana وبيانات Freqtrade API تؤخذ من `.env`.

## تنزيل بيانات اختبار

```bash
./scripts/download_data.sh 20250101-
```

## Backtest

```bash
./scripts/backtest.sh 20250101-
```

## فحص lookahead

```bash
./scripts/lookahead.sh 20250101-
```

## فحص recursive indicators

```bash
./scripts/recursive.sh 20250101-
```

## تشغيل Paper Bot

```bash
./scripts/start_paper.sh
```

## إيقاف كل الخدمات

```bash
./scripts/stop.sh
```

## ملاحظة مهمة عن FreqAI

الـCompose افتراضيًا مثبت على Freqtrade `2026.7`. لتجارب FreqAI غيّر في `.env`:

```text
FREQTRADE_IMAGE=freqtradeorg/freqtrade:2026.7_freqai
```

ثم أضف Config/Strategy خاصين بـFreqAI بعد نجاح الـbaseline. لا تجعل أول تجربة في المشروع تعتمد على AI؛ أولًا نثبت أن pipeline نفسه صحيح.

## ما لم يتم عمله عمدًا في v1

- لا API keys لبورصة حقيقية.
- لا Futures أو leverage.
- لا Shorts.
- لا LLM يرسل أوامر تداول.
- لا Hummingbot / Condor.
- لا NautilusTrader.
- لا RD-Agent/Qlib.

هذه تُضاف فقط بعد اجتياز Gate v1 الموضح في `docs/ROADMAP.md`.

## حالة التحقق لهذه الحزمة

تم التحقق محليًا من:

- صحة JSON/YAML.
- Python syntax.
- Bash syntax.
- Paper Guard behavior على ملفات config.

**لم يتم تشغيل Docker داخل بيئة إنشاء الحزمة لأن Docker غير متاح هناك.** لذلك أول تشغيل فعلي يجب أن يسجل الإصدارات، logs، ونتيجة الـhealth check قبل اعتبار المرحلة PASS.
