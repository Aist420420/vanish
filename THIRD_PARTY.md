# Сторонние данные и компоненты

Код Vanish распространяется по лицензии MIT (см. `LICENSE`). В проект также входят чужие данные, шрифты и библиотеки со своими лицензиями.

## Данные (`vanish/resources/`)

| Файл | Источник | Лицензия |
|---|---|---|
| `jdm_sites.json` | [JustDeleteMe](https://github.com/jdm-contrib/jdm) — ссылки и сложность удаления аккаунтов | MIT |
| `hibp_breaches.json` | [Have I Been Pwned](https://haveibeenpwned.com) — публичный каталог утечек (`/api/v3/breaches`) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `public_suffix_list.dat` | [Public Suffix List](https://publicsuffix.org), Mozilla Foundation | [MPL 2.0](https://mozilla.org/MPL/2.0/) |

Список утечек взят из Have I Been Pwned без изменений содержания: сохранены только нужные поля (название, домен, дата, число аккаунтов, типы данных). Ссылка на источник есть в интерфейсе и в README.

## Шрифты (`vanish/static/assets/`)

| Шрифт | Автор | Лицензия |
|---|---|---|
| Golos Text | Paratype | SIL Open Font License 1.1 |
| Unbounded | NaN | SIL Open Font License 1.1 |

Шрифты подключены через пакеты [Fontsource](https://fontsource.org).

## Библиотеки интерфейса

Собранный интерфейс (`vanish/static/`) включает: React и React DOM (MIT), Motion (MIT), canvas-confetti (ISC), стили Tailwind CSS (MIT). Полный список зависимостей для сборки — в `web/package.json`.

## Прочее

Vanish не связан с Google, JustDeleteMe или Have I Been Pwned. Google, Gmail и Google Takeout — товарные знаки Google LLC.
