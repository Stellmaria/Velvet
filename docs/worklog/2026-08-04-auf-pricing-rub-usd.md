# VL pricing and RUB/USD invoices

Date: 2026-08-04

## Context

Velvet needed a global default markup corresponding to a 30 percent gross margin, a minimum purchase starting at 100 RUB, and package prices visible and selectable in RUB or USD.

## Changes

- Set the global default markup to 42.86 percent.
- Preserve all individual user markup overrides; they continue to take priority over the global default.
- Replace the 40 VL entry package with 20 VL for 100 RUB.
- Set active package prices to 20/100/250/500/1000/2500 VL for 100/429/1019/1890/3590/8590 RUB.
- Display RUB and USD package prices to users.
- Add RUB/USD selection for new manual invoices while retaining compatibility with old RUB callbacks.
- Derive a USD invoice from the fixed RUB package price and the locked exchange rate, then persist the exact USD amount in both invoice price fields.

## Safety and compatibility

- Existing individual markup rows are not deleted or modified.
- Existing invoices keep their stored currency and locked amounts.
- Old package callbacks without a currency suffix are interpreted as RUB.
- Wallet crediting and invoice idempotency remain unchanged.

## Validation

- Contract tests cover the package list, minimum purchase, default markup, survival of individual overrides, and the 30 percent margin floor.
- Currency tests cover normalization, callback compatibility, money formatting, UI routing, and conversion of a fixed 429 RUB package to 5.37 USD at a locked 79.85 RUB/USD rate.
- Full repository CI is required before merge.

## Rollout

After merge, production still requires the normal controlled rollout so migration `z029_auf_margin30_packages.sql` is applied and the bot process loads the currency UI changes.
