# Runtime compatibility inventory

Актуальный реестр активных runtime compatibility-компонентов для issue #418.
Канонический машинно-проверяемый источник находится в
`velvet_bot/presentation/telegram/runtime_contracts.py`.

Все восемь компонентов остаются активными только до миграции consumers. Ни один из
них не признан постоянным monkeypatch-контрактом.

| Компонент | Стадия | Решение | Что меняет | Каноническая замена |
| --- | --- | --- | --- | --- |
| `ai-quality-schema` | pre-import | удалить после миграции | подменяет mapping и SQL `AIQualityRepository` | встроить deployed schema непосредственно в repository |
| `set-consistency-dashboard` | pre-import | удалить после миграции | оборачивает quality dashboard | рисовать кнопку медиасетов в canonical dashboard |
| `quality-calibration-dashboard` | pre-import | удалить после миграции | оборачивает quality dashboard | рисовать кнопку калибровки в canonical dashboard |
| `media-set-actions` | pre-import | удалить после миграции | подменяет duplicate-to-set action | вызывать canonical media-set boundary напрямую |
| `media-set-ai-discovery` | pre-import | удалить после миграции | подменяет discovery function | сделать semantic discovery canonical service |
| `media-set-ui` | pre-import | удалить после миграции | переназначает archive/public formatters | встроить set title в canonical caption formatters |
| `owner-menu-navigation` | pre-import | удалить после миграции | оборачивает keyboard factories | использовать shared navigation helper напрямую |
| `quality-calibration-report-ui` | post-import | удалить после миграции | переназначает report renderer после imports | встроить calibration block в canonical formatter |

## Порядок retirement

1. `ai-quality-schema`;
2. два dashboard wrappers;
3. `quality-calibration-report-ui`;
4. `owner-menu-navigation`;
5. `media-set-actions`;
6. `media-set-ai-discovery`;
7. `media-set-ui`.

Каждое удаление выполняется отдельным связным PR, сохраняет поведение и получает
regression test. Одновременно переносить все восемь компонентов запрещено: именно
так обычно и рождается следующий compatibility layer, только уже с более печальным
названием.
