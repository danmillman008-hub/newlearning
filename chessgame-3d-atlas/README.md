# ChessGame در Code Atlas — خروجی سه‌بعدی HTML

## دسترسی سریع

- 🔭 **اجرای زنده (بدون نصب):**
  https://raw.githack.com/danmillman008-hub/newlearning/arena/345fe9e3-newlearning/chessgame-3d-atlas/ChessGame-3D-Atlas.html
- 📦 **صفحهٔ فایل در گیت‌هاب:**
  https://github.com/danmillman008-hub/newlearning/blob/arena/345fe9e3-newlearning/chessgame-3d-atlas/ChessGame-3D-Atlas.html
- ⬇️ **دانلود مستقیم:** دکمهٔ *Download raw file* در همان صفحه، یا `git clone` و باز کردن `chessgame-3d-atlas/ChessGame-3D-Atlas.html`

> فایل کاملاً خودکفاست: هیچ asset نسبی، فونت، worker یا درخواست شبکه‌ای ندارد،
> پس هم از دیسک (دابل‌کلیک) و هم از روی CDN کار می‌کند.

## فایل تحویلی

**`ChessGame-3D-Atlas.html`** — یک فایل تک‌فایلی و کاملاً خودکفا (۴.۵ مگابایت).
روی سیستم‌عامل باز می‌شود (دابل‌کلیک)، **بدون اینترنت، بدون نصب، بدون سرور**.
تمام باندل رندرر سه‌بعدی، CSS، فونت لیبل‌ها، Worker چیدمان نیرو و دادهٔ تحلیل داخل همین یک فایل inline شده‌اند.

`ChessGame-3D-Atlas.snapshot.json` هم همان دادهٔ خام تحلیل است (برای بازتولید/بازرسی).

## چه چیزی داخلش هست

| | |
|---|---|
| مخزن | `pnpduy/ChessGame` (جاوا، Swing) |
| فایل‌ها | ۱۵ (۱۲ فایل `.java` + README + ۲ متادیتا) |
| خط کد | ۱٬۰۷۴ |
| سمبل‌ها | استخراج‌شده با tree-sitter-java برای ۱۲ فایل |
| یال‌های ایمپورت | ۲۲ (شامل ۷ یال از `import piece.*`) |
| کامیت‌ها | ۲ (تاریخ ۲۴ مارس ۲۰۲۴) |

سه ویو واقعی برنامه:

- **City** — هر فایل یک ساختمان؛ ارتفاع = LOC، رنگ = زبان، پنجره‌های روشن = churn گیت.
- **Galaxy** — فایل‌ها ستاره‌اند و گرانش از یال‌های ایمپورت می‌آید (چیدمان d3-force سه‌بعدی در Web Worker).
- **Molecule** — روی یک فایل دابل‌کلیک کنید: اتم‌ها = سمبل‌ها، پیوندها = فراخوانی‌ها (۹۵ سمبل، ۱۲۵ یال برای `GamePanel` + همسایه‌ها).

لنزها (Language / Complexity / Hotspot / Freshness / TODO / Ownership / Coverage)، پنل
**Health** (تشخیص چرخهٔ وابستگی با Tarjan-SCC: یک SCC هشت‌فایلی بین `GamePanel` و `piece/*`)،
تایم‌لاین گیت، `Ctrl+K` جست‌وجو، `Tab` حالت پرواز، `H` قاب‌بندی مجدد، `Esc` برگشت.

> در snapshot بالا: `0 cycles` قبل از پچ و `1 cycle / 8 files` بعد از آن — چرخه واقعی است، نه خطای تشخیص.

## نصب و پیش‌نیازها (همان‌طور که درخواست شد)

```bash
git clone https://github.com/mtecnic/code-atlas.git /home/user/code-atlas
cd /home/user/code-atlas
export NODE_EXTRA_CA_CERTS=/home/user/e2b-proxy-ca.pem   # در این sandbox برای TLS پروکسی
export ELECTRON_SKIP_BINARY_DOWNLOAD=1                   # باینری Electron از CDN قابل دریافت نبود
npm install --no-audit --no-fund       # ۷۳۸ پکیج + ۱۰ گرامر tree-sitter (wasm)
npx electron-vite build                # باندل production در out/
```

پیش‌نیازها: Node ≥ 20، npm، git، ۱۰ گرامر `web-tree-sitter`، و کتابخانه‌های سیستمی Electron
(GTK/NSS/…، اینجا نصب نشدند). در همین محیط Chromium واقعی + SwiftShader از خود npm نصب شد
(بستهٔ `@sparticuz/chromium`) تا بتوان خروجی WebGL را به‌طور واقعی رندر و تأیید کرد.

## چطور ساخته شد

هیچ‌کدام از این‌ها در این محیط قابل اجرا نبود: باینری Electron (CDN مسدود)، کتابخانه‌های
GTK/NSS/ALSA/GBM، و `xvfb`. بنابراین خودِ برنامه اجرا نشد، بلکه **کد خودش** اجرا شد:

1. `tools/headless-analyze.ts` خط لولهٔ واقعی تحلیل را بدون Electron در Node اجرا می‌کند:
   `scan` → `parse` (web-tree-sitter + ۱۰ گرامر) → `ImportResolver` → `readGitHistory` → `RepoSnapshot`.
   (به‌جای استخر Piscina، همان `parseFile` درون‌فرایندی اجرا می‌شود؛ خروجی یکسان.)
2. `tools/export-html.mjs` باندل production رندرر (`out/renderer/assets/index-*.js` + CSS +
   `force-worker-*.js`) را inline می‌کند، آدرس Worker را به Blob برمی‌گرداند، و یک
   `window.atlas` جعلی می‌سازد که جای IPC الکترون از snapshot درون فایل پاسخ می‌دهد.
   `getModuleGraph` هم پورت وفادار `symbol-graph.ts` است.
3. یک فرمان برای هر مخزنی:

```bash
cd /home/user/code-atlas
node tools/export-atlas.mjs <repoPath> <out.html> [snapshot.json]
```

## پچ‌های اعمال‌شده روی code-atlas

`code-atlas-headless.patch` (۱۶۸ خط، ۴ فایل) — همه با کامنت توضیح داده شده‌اند:

1. **`queries/index.ts`** — ایمپورت wildcard جاوا (`import piece.*;`) در درخت نحوی
   `(import_declaration (identifier) (asterisk))` است و قاعدهٔ `scoped_identifier` هرگز
   برایش فعال نمی‌شد؛ حالا گرفته می‌شود.
2. **`import-resolver.ts`** — `resolveJava` پکیج wildcard را مثل `resolveGo` روی پوشه حل
   می‌کند (با پرچم `weak` تا در تطبیق نامِ فراخوانی‌ها گمراه‌کننده نباشد).
3. **`WorldLayer.ts`** — در ویو Galaxy، فایل‌های بدون یال ایمپورت با شعاع ~۴۲۶ در لبهٔ
   شبیه‌سازی می‌ماندند و بقیهٔ خوشه (شعاع ۴۰–۸۰) به چند پیکسل تبدیل می‌شد؛ شعاع‌های بالاتر از
   صدک ۷۵ به همان حد کشیده می‌شوند.
4. **`SceneManager.ts`** — دوربین قبل از رسیدن فریم نهایی چیدمان، صفحه را قاب می‌گرفت؛ حالا
   مثل ویو Molecule، یک بار پس از settle دوباره قاب می‌بندد.

## اجرا / پیش‌نمایش

```bash
cd /home/user/atlas-export
python3 serve.py --port 8080 --bind 0.0.0.0     # http://<host>:8080/
```

`serve.py` همان فایل را از حافظه سرو می‌کند با `Content-Length` و `ETag`
(بار دوم فقط `304` می‌گیرد، نه ۴.۶ مگابایت)، هر درخواست در thread جدا، قطع
اتصال مرورگر را بی‌صدا رد می‌کند، و هدرهایی می‌گذارد که صفحه داخل iframe پیش‌نمایش
قابل embed باشد. `index.html` کپی همان `ChessGame-3D-Atlas.html` است تا مسیر ریشه
هم مستقیماً باز شود. (بدون سرور هم با دابل‌کلیک روی فایل HTML کار می‌کند.)

## اعتبارسنجی واقعی

فایل تحویلی با Chromium واقعی (SwiftShader / WebGL2، نصب‌شده از npm) بارگذاری و رندر شد:
۳ ویو، لنزها، تم روز/شب، پنل Health، تولتیپ هاور، درگ چرخش دوربین و مودال جست‌وجو —
**بدون هیچ خطای صفحه یا console**. اسکرین‌شات‌ها در پوشهٔ `screenshots/`.

همین بررسی روی نسخهٔ سرو‌شده (پورت ۸۰۸۰) هم تکرار شد: بارگذاری، reload (مسیر 304)،
حالت Galaxy، و اجرا داخل iframe — همه بدون خطا.

## محدودیت‌های نسخهٔ استاتیک

- ویرایش فایل، چت هوش مصنوعی و ایمپورت پوشش تست (lcov) غیرفعال‌اند (روی دکمه‌شان پیام می‌دهند).
- دکمهٔ `Open` مخزن دیگری را باز نمی‌کند (فقط همین snapshot داخل فایل است).
- تاریخ گیت فقط ۲ کامیت دارد، پس lens «Hotspot» و تایم‌لاین عملاً صاف‌اند — ویژگی خود مخزن است.
