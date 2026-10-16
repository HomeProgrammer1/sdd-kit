# SDD Kit: маркетплейс плагінів для Claude Code

*Spec-driven delivery for any software project (web, mobile, backend) as a Claude Code plugin.*

Плагін `sdd-kit` перетворює Claude Code на команду агентів. Команда веде фічу від ідеї до pull request за принципом **spec-driven development**: спершу специфікація, потім план, потім код. На кожному кроці стоять людські ворота. Плагін підходить для будь-якого стеку: сайту, мобільного застосунку, бекенду або їх комбінації.

## Встановлення

```text
/plugin marketplace add HomeProgrammer1/sdd-kit
/plugin install sdd-kit@sdd-marketplace
```

Те саме з терміналу: `claude plugin marketplace add HomeProgrammer1/sdd-kit`, потім `claude plugin install sdd-kit@sdd-marketplace`.

Далі в репозиторії свого проєкту:

```text
/sdd-kit:init-project            # скопіює шаблон, визначить стек, заповнить команди в CLAUDE.md
/sdd-kit:sdd "опис фічі"         # перша фіча, зупинка після специфікації
```

Якщо репозиторій приватний, встановити плагін зможуть лише ті, хто має до нього доступ у git.

## Як це працює

```
/sdd-kit:sdd "Скидання пароля через email" --level=plan
   │
   ▼  головна сесія = ОРКЕСТРАТОР: пише state.json і комітить
   1. analyst      → specs/F-001-…/spec.md (вимоги, AC-1..n у форматі Given/When/Then)
   ═══ GATE 1: людина погоджує специфікацію ═══
   2. architect    → plan.md, tasks.md, docs/adr/*.md
   ═══ GATE 2: людина погоджує план ═══
   3. для кожної задачі T-n:
        implementer (TDD, без комітів) → reviewer (тільки читає) → коміт
   4. verifier (e2e проти AC) + security-auditor
   5. handover: push гілки і DRAFT PR
   ═══ GATE 3: review і merge робить ТІЛЬКИ людина ═══
```

Агенти не передають одне одному розмову. Вони передають **файли** (`spec.md` → `plan.md` → `tasks.md`) і повертають **фіксований блок** `STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT`. Оркестратор вирішує, що робити далі, за цим полем. Стан прогону лежить у `specs/<ID>/state.json`, тому роботу можна продовжити в новій сесії.

## Команди

| Команда | Що робить |
|---|---|
| `/sdd-kit:init-project` | Одноразове налаштування проєкту |
| `/sdd-kit:sdd "опис"` | Пише тільки spec.md і зупиняється на Gate 1 (рівень `spec` за замовчуванням) |
| `/sdd-kit:sdd F-001` | Продовжує з місця зупинки |
| `/sdd-kit:sdd F-001 --level=implement` | Робить план, код, рев'ю, локальні коміти і перевірку |
| `/sdd-kit:sdd F-001 --level=push` | Те саме, плюс push гілки і draft PR |
| `/sdd-kit:sdd-status` | Показує стан усіх фіч і що чекає на вас |
| `/sdd-kit:commit`, `/sdd-kit:handover F-001` | Окремий коміт або передача на рев'ю |

## Що в репозиторії

```
.claude-plugin/marketplace.json        каталог маркетплейсу
plugins/sdd-kit/
  .claude-plugin/plugin.json           маніфест плагіна
  agents/                              7 агентів: analyst, architect, implementer, reviewer,
                                       verifier, security-auditor, debugger
  skills/                              15 скілів: оркестратор sdd, sdd-status, init-project,
                                       spec-format, plan-format, run-state, autonomy-contract,
                                       tdd, systematic-debugging, verify, commit, handover,
                                       stack-web, stack-mobile, stack-backend
  skills/init-project/template/        що копіюється в проєкт: CLAUDE.md, .claude/settings.json,
                                       .claude/rules/, statusline, specs/, docs/adr/, сніпети MCP
  hooks/hooks.json + скрипти           guard, автоформат, сповіщення, контекст при старті сесії
  output-styles/terse.md               стиль «лише код і результат»
scripts/validate.py                    перевірка структури і 16 кейсів guard
```

**Профілі стеку.** Ролі агентів однакові для будь-якого проєкту, а специфіку платформи додають скіли-профілі. `stack-web` відповідає за WCAG, Core Web Vitals і e2e у Playwright. `stack-mobile` питає про офлайн, дозволи, мінімальні версії ОС і симулятори. `stack-backend` відповідає за контракти API, міграції з rollback і спостережуваність. Новий тип проєкту додається одним файлом `skills/stack-<x>/SKILL.md`.

## Безпека: три шари

| Шар | Механізм | Що гарантує |
|---|---|---|
| 1. Інструменту немає | `tools:` в агентах, `permissions.deny`, allow/deny-списки в сніпетах MCP | Reviewer фізично не може редагувати файли, а агент не бачить інструменту merge |
| 2. Хук-заборона | `hooks/guard.py` на кожен Bash, Write і Edit | Блокує force push, push у main/master/develop, merge, `terraform apply`, `kubectl apply`, деплой, публікацію пакетів, upload у стори, запис у `.env` і ключі. Analyst і architect можуть писати тільки в `specs/` і `docs/` |
| 3. Політика в тексті | скіл `autonomy-contract` | Рівні автономії, бюджети ретраїв, умови обов'язкової паузи |

Рівня `merge`, `release` чи `deploy` немає: ці кроки завжди робить людина.

## Обмеження

- `guard.py` перевіряє команду так, як її написано. Вкладений `bash -c "…"` і скрипти, які викликає команда, він не бачить. Якщо в guard стається помилка, він пропускає дію; щоб блокувати в такому разі, додайте `"onFailure": "block"` до обробника в `hooks.json`.
- Хукам потрібні `python3` і `bash`. На Windows запускайте Claude Code через WSL або Git Bash.
- Адреси і пакети MCP-серверів у сніпетах можуть змінитися. Звірте їх із документацією вендора і закріпіть версію.
- `claude plugin validate` і тестове встановлення проходять. Повний цикл `/sdd-kit:sdd` на реальному проєкті поки не прогнано.

## Розробка

```bash
python3 scripts/validate.py
claude plugin validate .
claude plugin validate plugins/sdd-kit
```

Змінюючи плагін, піднімайте `version` у `plugins/sdd-kit/.claude-plugin/plugin.json`. Інакше користувачі не отримають оновлення через `claude plugin update`.

## Ліцензія

MIT
