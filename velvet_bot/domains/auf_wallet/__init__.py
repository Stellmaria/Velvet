from velvet_bot.domains.meow_wallet import (
    AUF_PACKAGES,
    AUF_SCALE,
    MeowAufPackageQuote,
    MeowChargedTaskQueueService,
    MeowEconomySettings,
    MeowInsufficientBalance,
    MeowInvoiceError,
    MeowInvoiceStatus,
    MeowPriceNotConfigured,
    MeowPriceQuote,
    MeowPricingRepository,
    MeowPurchaseInvoice,
    MeowPurchaseRepository,
    MeowPurchaseService,
    MeowReconciliationIssue,
    MeowWallet,
    MeowWalletAccessError,
    MeowWalletEntry,
    MeowWalletError,
    MeowWalletFrozen,
    MeowWalletOperation,
    MeowWalletOverview,
    MeowWalletRepository,
    MeowWalletService,
    MeowWalletStatus,
    auf_to_units,
    build_meow_charged_task_queue_service,
    format_auf_units,
    units_to_auf,
)

AufPackageQuote = MeowAufPackageQuote
AufChargedTaskQueueService = MeowChargedTaskQueueService
AufEconomySettings = MeowEconomySettings
AufInsufficientBalance = MeowInsufficientBalance
AufInvoiceError = MeowInvoiceError
AufInvoiceStatus = MeowInvoiceStatus
AufPriceNotConfigured = MeowPriceNotConfigured
AufPriceQuote = MeowPriceQuote
AufPricingRepository = MeowPricingRepository
AufPurchaseInvoice = MeowPurchaseInvoice
AufPurchaseRepository = MeowPurchaseRepository
AufPurchaseService = MeowPurchaseService
AufReconciliationIssue = MeowReconciliationIssue
AufWallet = MeowWallet
AufWalletAccessError = MeowWalletAccessError
AufWalletEntry = MeowWalletEntry
AufWalletError = MeowWalletError
AufWalletFrozen = MeowWalletFrozen
AufWalletOperation = MeowWalletOperation
AufWalletOverview = MeowWalletOverview
AufWalletRepository = MeowWalletRepository
AufWalletService = MeowWalletService
AufWalletStatus = MeowWalletStatus


def build_auf_charged_task_queue_service(*, database):
    return build_meow_charged_task_queue_service(database=database)


__all__ = (
    "AUF_PACKAGES",
    "AUF_SCALE",
    "AufPackageQuote",
    "AufChargedTaskQueueService",
    "AufEconomySettings",
    "AufInsufficientBalance",
    "AufInvoiceError",
    "AufInvoiceStatus",
    "AufPriceNotConfigured",
    "AufPriceQuote",
    "AufPricingRepository",
    "AufPurchaseInvoice",
    "AufPurchaseRepository",
    "AufPurchaseService",
    "AufReconciliationIssue",
    "AufWallet",
    "AufWalletAccessError",
    "AufWalletEntry",
    "AufWalletError",
    "AufWalletFrozen",
    "AufWalletOperation",
    "AufWalletOverview",
    "AufWalletRepository",
    "AufWalletService",
    "AufWalletStatus",
    "auf_to_units",
    "build_auf_charged_task_queue_service",
    "format_auf_units",
    "units_to_auf",
)
