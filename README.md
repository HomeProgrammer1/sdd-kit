# SDD Kit: маркетплейс плагінів для Claude Code

*Spec-driven development for any software project (web, mobile, backend): spec → diagrams → plan → prototype → code → PR, behind human gates.*

Чотири плагіни, які працюють разом або окремо. Кожна фіча проходить шлях від ідеї до draft pull request. Спершу пишеться специфікація з діаграмою «як це працює», потім план і, за бажанням, клікабельний прототип на вашій дизайн-системі з розкладкою у Figma. Після цього йде код за TDD з рев'ю. Специфікацію і план погоджує людина, і merge теж робить тільки людина.

| Плагін | Що робить | Команди |
|---|---|---|
| **sdd-kit** | Оркестратор і агенти: discovery, analyst, architect, implementer, reviewer, branch-reviewer, verifier, security-auditor, debugger | `/sdd-kit:sdd`, `/sdd-kit:sdd-status`, `/sdd-kit:init-project` |
| **sdd-diagrams** | Перевіряє Mermaid у специфікації. Рендерить редакційні SVG, багатосторінковий `.drawio` і галерею для рев'ю | `/sdd-diagrams:feature-diagrams` |
| **sdd-design** | Агент ux-designer, `screens.json`, клікабельний HTML-прототип і стартер дизайн-системи | `/sdd-design:prototype`, `/sdd-design:design-system-init` |
| **sdd-figma** | Розкладає діаграми й екрани у Figma: через MCP-конектор або через власний Figma-плагін без конектора | `/sdd-figma:figma-export` |

## Встановлення

```text
/plugin marketplace add HomeProgrammer1/sdd-kit
/plugin install sdd-kit@sdd-marketplace
/plugin install sdd-diagrams@sdd-marketplace     # рекомендовано
/plugin install sdd-design@sdd-marketplace       # якщо потрібні прототипи
/plugin install sdd-figma@sdd-marketplace        # якщо потрібна Figma
```

Те саме з терміналу: `claude plugin marketplace add HomeProgrammer1/sdd-kit`, потім `claude plugin install <name>@sdd-marketplace`. Плагіни не залежать один від одного. `sdd-kit` сам знаходить компаньйонів, якщо вони встановлені. Якщо репозиторій приватний, встановити плагіни зможуть лише ті, хто має до нього доступ у git.

Після встановлення `sdd-kit` Claude Code може показати «userConfig options not yet set». Це нормально. Без налаштування діють значення за замовчуванням: `guard_mode = sdd` і `format_on_edit = true`. Без меню їх можна перевизначити змінними середовища: `SDD_GUARD=strict|hard-only|off` і `SDD_FORMAT=off`.

Далі в репозиторії проєкту:

```text
/sdd-kit:init-project                     # шаблон CLAUDE.md, правила, settings, specs/
/sdd-kit:sdd "Скидання пароля через email" # зупиниться після специфікації (Gate 1)
/sdd-kit:sdd F-001 --level=plan --design --figma
```

## Як це працює

```
/sdd-kit:sdd "опис" [--level=spec|plan|implement|push] [--design] [--figma]
   0. discovery         коротке інтерв'ю, одне питання за раз → discovery.md
   1. analyst           spec.md: EARS-вимоги, AC-1..n (Given/When/Then), розділ «How it works» з Mermaid
      sdd-diagrams      перевірка і рендер діаграм → specs/F-001/diagrams/
   ═══ GATE 1: людина погоджує специфікацію ═══
   2. architect         plan.md, tasks.md (задачі з кроками), ADR
      sdd-design        ux-designer → design/screens.json → клікабельний прототип   (--design)
      sdd-figma         діаграми й екрани у Figma                                    (--figma)
   ═══ GATE 2: людина погоджує план (і прототип) ═══
   3. worktree + зелений baseline, pre-flight скан задач
   4. для кожної задачі: implementer (TDD) → reviewer (SPEC: PASS|FAIL, QUALITY: APPROVE|REQUEST_CHANGES)
      → до 5 раундів виправлень → коміт
   5. branch-reviewer → verifier (e2e проти AC) → security-auditor
   6. handover: push гілки і DRAFT PR
   ═══ GATE 3: review і merge робить ТІЛЬКИ людина ═══
```

Агенти передають одне одному **файли**, а не розмову. Кожен повертає фіксований блок (`STATUS`, `SPEC`, `QUALITY`, `VERDICT`), і оркестратор маршрутизує за ним. Стан прогону лежить у `specs/<ID>/state.json` і `ledger.md` (рішення у форматі «Ruling: що — чому — ціна помилки»). Тому роботу можна продовжити в новій сесії або після стиснення контексту.

## Діаграми: у кожної фічі є схема роботи

Аналітик пише діаграми в `spec.md` на **Mermaid**. Обов'язковий Flow. Sequence потрібен, якщо взаємодіють дві чи більше систем, State потрібен, якщо сутність має життєвий цикл. Mermaid є єдиним джерелом: GitHub показує його в PR, а диф читається як текст. `sdd-diagrams` перевіряє бюджети і правила:

- не більше 12 вузлів, комфортно до 9;
- у кожного рішення підписані всі виходи;
- не більше двох акцентів;
- немає перекриттів і підписів на лініях.

Після перевірки він генерує файли:
- SVG у редакційному стилі: ортогональні лінії із заокругленням, підписи поруч із сегментом, AC-теги на вузлах, доступний `<title>/<desc>`, хеш джерела;
- `.drawio` з окремою сторінкою на кожну діаграму;
- `index.html`, галерею для рев'ю.

Кольори беруться з токенів вашої дизайн-системи (`--tokens`), з перевіркою контрасту WCAG AA. Рушій написаний на чистому Python, без мережі та залежностей.

<p align="center"><img src="docs/img/example-flow.svg" alt="Flow diagram of the example password-reset feature" width="440"></p>

## Дизайн: спершу власна дизайн-система

> **Важливо.** Щоб будувати дизайн і прототипи, спочатку **створіть власну дизайн-систему**. `sdd-design` не вигадує компонентів і кольорів. Він збирає екрани лише з того, що оголошено у вашій системі, тому прототип збігається з тим, що ви реально випустите. Без дизайн-системи команда зупиняється і пояснює, що робити. Прапорець `--sketch` дає лише сірий одноразовий ескіз.

**Окреме репо чи все в одному?** Рекомендація: **один окремий репозиторій дизайн-системи** (монорепо), відокремлений і від продуктів, і від цього плагіна. Усередині лежать:
- спільні семантичні токени (DTCG), які є контрактом для коду, прототипів і Figma;
- **теми** (бренди, dark mode), які лише перенаправляють аліаси;
- **кіти**: `saas-dashboard`, `marketing-site`, `mobile-app`. Це підмножини компонентів, а не форки.

Розділяти на кілька репозиторіїв варто лише тоді, коли бренд веде інша команда з власним циклом релізів. Навіть тоді імена семантичних токенів мають бути спільними.

1. У новій порожній папці: `/sdd-design:design-system-init`. Команда створить токени (primitives, light, dark), `components.json` з кітами, README і CHANGELOG, і перевірить контраст.
2. Опублікуйте систему як окремий репозиторій із тегами версій (`v0.1.0`).
3. Підключіть її в продукт (наприклад, git submodule у `design-system/`) і вкажіть у `CLAUDE.md`:
   ```
   - Design system: design-system/components.json
   - Theme: light
   - Kit: saas-dashboard
   ```
4. `/sdd-kit:sdd F-001 --design` або `/sdd-design:prototype F-001`.

Агент **ux-designer** створює `specs/<ID>/design/screens.json`. Це екрани для кожного стану (default, empty, loading, error, success), складені з компонентів вашої системи, з AC-ID на кожному екрані. Рендерер робить із цього клікабельний `index.html`. Перевірки ловлять невідомі компоненти й варіанти, биті посилання, недосяжні екрани, AC без екрана і контраст токенів нижче AA.

<p align="center"><img src="docs/img/example-prototype.png" alt="Prototype board for the example feature" width="720"></p>

## Figma

`screens.json` і SVG-діаграми складаються в один `figma/bundle.json`. Далі є два шляхи, обидва дають однаковий результат:
- сторінка `<ID> · How it works` з діаграмами;
- сторінка `<ID> · Screens`: кожен екран як фрейм з **auto layout**, з назвами шарів за компонентами, кольорами і відступами, прив'язаними до **Figma variables** з ваших токенів, і з prototype-посиланнями між екранами.

| Шлях | Коли | Як |
|---|---|---|
| **MCP-конектор Figma** | Конектор підключено, ви дали URL файлу | Агент пише у ваш файл і, де можливо, ставить інстанси з вашої бібліотеки |
| **Плагін SDD Kit Import** | Без конектора або офлайн | Figma desktop → Plugins → Development → Import plugin from manifest → `.sdd/figma-plugin/manifest.json`, потім Build з `bundle.json` |

Якщо в `components.json` вказано ключі опублікованих компонентів бібліотеки, плагін ставить **справжні інстанси**. Інакше він малює компонент із токенів. Повторний запуск замінює лише те, що створив сам плагін. Figma тут «нижче за течією»: зміни з Figma повертаються через `screens.json` або специфікацію.

## Сумісність з іншими плагінами

Kit не забирає собі сесію і нічого не блокує в чужій роботі. Його можна ставити поруч із загальними колекціями скілів (наприклад, superpowers) чи плагінами діаграм (наприклад, diagram-design):

- **Guard має два рівні.** Жорсткі заборони діють завжди: `rm -rf /`, force push у main/master, запис у `.git/` і `~/.ssh`. Процесні рейки діють лише в роботі самого kit, тобто в агентах `sdd-kit:*` і `sdd-design:*` та в сесії, яка веде `/sdd-kit:sdd` (її id записано у `state.json`). Процесні рейки охоплюють merge, deploy, publish, `.env`, force push і обмеження ролей. Режим задається опцією плагіна `guard_mode`: `sdd` (за замовчуванням), `strict`, `hard-only` або `off`.
- **Автоформатування** після редагування працює лише в SDD-прогонах.
- **Немає примусових інструкцій на старті сесії.** SessionStart лише показує відкриті прогони, якщо вони є.
- **Скіли мають вузькі описи** («у прогоні sdd-kit…») і викликаються з префіксом `sdd-kit:`. Тому загальні TDD-, debugging- чи brainstorming-скіли інших плагінів і далі працюють поза прогоном. Усередині прогону діє порядок kit.
- **Немає залежностей** від інших плагінів чи маркетплейсів.

## Безпека: три шари

| Шар | Механізм | Що гарантує |
|---|---|---|
| 1. Інструменту немає | `tools:` в агентах, `permissions.deny`, allow/deny-списки в сніпетах MCP | Reviewer фізично не може редагувати файли; агент не бачить інструменту merge |
| 2. Хук-заборона | `hooks/guard.py` на кожен Bash/Write/Edit, два рівні | Див. розділ про сумісність; analyst, architect і ux-designer пишуть лише в `specs/` і `docs/` |
| 3. Політика в тексті | скіл `autonomy-contract` | Рівні автономії, бюджети ретраїв, умови обов'язкової паузи |

Рівня `merge`, `release` чи `deploy` немає: ці кроки завжди робить людина.

## Що в репозиторії

```
.claude-plugin/marketplace.json      каталог із 4 плагінів
plugins/sdd-kit/                     8 агентів, 18 скілів, хуки, шаблон проєкту, output style
plugins/sdd-diagrams/                скіл feature-diagrams, рушій sdd_diagrams.py, style.md
plugins/sdd-design/                  агент ux-designer, скіли prototype і design-system-init (стартер)
plugins/sdd-figma/                   скіл figma-export, build_bundle.py, figma-plugin/ (manifest, code.js, ui.html)
scripts/validate.py                  JSON, frontmatter, 34 кейси guard, діаграми, прототип, тест Figma-плагіна
THIRD_PARTY_NOTICES.md               звідки взято ідеї (MIT)
```

## Обмеження

- Повний цикл `/sdd-kit:sdd` на реальному проєкті ще не прогнано. Маніфести проходять `claude plugin validate`, тестове встановлення і `scripts/validate.py`.
- Figma-плагін перевірено тестом із суворим mock API Figma, а не в самій Figma. Шлях через MCP-конектор описано, але на реальному файлі не перевірено.
- Рушій діаграм підтримує переносну підмножину: flowchart, stateDiagram-v2, sequenceDiagram. ER, class і gantt лишаються в Mermaid і рендеряться GitHub.
- `guard.py` перевіряє команду так, як її написано. Вкладений `bash -c "…"` і скрипти він не бачить. Якщо в guard стається помилка, він пропускає дію; щоб блокувати в такому разі, додайте `"onFailure": "block"`.
- Хукам і скриптам потрібні `python3` і `bash`. На Windows використовуйте WSL або Git Bash.
- Адреси і пакети MCP-серверів у сніпетах можуть змінитися. Звіряйте їх із документацією вендора.

## Розробка

```bash
python3 scripts/validate.py
claude plugin validate .
for p in plugins/*; do claude plugin validate "$p"; done
```

Змінюючи плагін, піднімайте `version` у його `plugin.json` і в `marketplace.json`. Інакше користувачі не отримають оновлення.

## Подяки і ліцензія

Частина процедур переосмислює ідеї з [obra/superpowers](https://github.com/obra/superpowers) (MIT, © Jesse Vincent) і [diagram-design](https://github.com/cathrynlavery/diagram-design) (MIT, © Cathryn Lavery). Код не скопійовано, деталі в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

MIT © HomeProgrammer1
