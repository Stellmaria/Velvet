---
name: memory-candidate
description: Выделить из завершённой инженерной задачи только устойчивые проверяемые сведения для будущей памяти.
version: 1.0.0
author: Velvet
---

# Memory candidate

Добавляй candidate только когда факт пригодится повторно, имеет source/evidence,
относится к одной scope и не является уже существующей инструкцией.

Не предлагай:

- секреты, env values, персональные данные и raw logs;
- временный branch/commit/run ID без долгосрочной ценности;
- догадку или вывод без evidence;
- то, что уже записано в SOUL, AGENTS или project notes.

Отсутствие полезных candidates представляется пустым массивом.
