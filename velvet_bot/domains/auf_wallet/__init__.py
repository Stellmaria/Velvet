"""Compatibility package for retired Meow wallet imports.

All implementations live in :mod:`velvet_bot.domains.auf_wallet`.
"""

from velvet_bot.domains.auf_wallet import *  # noqa: F403
from velvet_bot.domains.auf_wallet import (
    AufChargedTaskQueueService as AufChargedTaskQueueService,
    AufEconomySettings as AufEconomySettings,
    AufInsufficientBalance as AufInsufficientBalance,
    AufInvoiceError as AufInvoiceError,
    AufInvoiceStatus as AufInvoiceStatus,
    AufPackageQuote as AufPackageQuote,
    AufPriceNotConfigured as AufPriceNotConfigured,
    AufPriceQuote as AufPriceQuote,
    AufPricingRepository as AufPricingRepository,
    AufPurchaseInvoice as AufPurchaseInvoice,
    AufPurchaseRepository as AufPurchaseRepository,
    AufPurchaseService as AufPurchaseService,
    AufReconciliationIssue as AufReconciliationIssue,
    AufWallet as AufWallet,
    AufWalletAccessError as AufWalletAccessError,
    AufWalletEntry as AufWalletEntry,
    AufWalletError as AufWalletError,
    AufWalletFrozen as AufWalletFrozen,
    AufWalletOperation as AufWalletOperation,
    AufWalletOverview as AufWalletOverview,
    AufWalletRepository as AufWalletRepository,
    AufWalletService as AufWalletService,
    AufWalletStatus as AufWalletStatus,
    build_auf_charged_task_queue_service as build_auf_charged_task_queue_service,
    quote_auf_payload as quote_auf_payload,
)
