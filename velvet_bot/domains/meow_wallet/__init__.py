"""Compatibility package for retired Meow wallet imports.
All implementations live in :mod:`velvet_bot.domains.auf_wallet`.
"""
from velvet_bot.domains.auf_wallet import *  # noqa: F403
from velvet_bot.domains.auf_wallet import (
    AufChargedTaskQueueService as MeowChargedTaskQueueService,
    AufEconomySettings as MeowEconomySettings,
    AufInsufficientBalance as MeowInsufficientBalance,
    AufInvoiceError as MeowInvoiceError,
    AufInvoiceStatus as MeowInvoiceStatus,
    AufPackageQuote as MeowAufPackageQuote,
    AufPriceNotConfigured as MeowPriceNotConfigured,
    AufPriceQuote as MeowPriceQuote,
    AufPricingRepository as MeowPricingRepository,
    AufPurchaseInvoice as MeowPurchaseInvoice,
    AufPurchaseRepository as MeowPurchaseRepository,
    AufPurchaseService as MeowPurchaseService,
    AufReconciliationIssue as MeowReconciliationIssue,
    AufWallet as MeowWallet,
    AufWalletAccessError as MeowWalletAccessError,
    AufWalletEntry as MeowWalletEntry,
    AufWalletError as MeowWalletError,
    AufWalletFrozen as MeowWalletFrozen,
    AufWalletOperation as MeowWalletOperation,
    AufWalletOverview as MeowWalletOverview,
    AufWalletRepository as MeowWalletRepository,
    AufWalletService as MeowWalletService,
    AufWalletStatus as MeowWalletStatus,
    build_auf_charged_task_queue_service as build_auf_charged_task_queue_service,
    quote_auf_payload as quote_meow_payload,
)
