"""Compatibility aliases for retired Meow purchase names."""

from velvet_bot.domains.auf_wallet.purchase import (
    AufInvoiceError,
    AufInvoiceStatus,
    AufPurchaseInvoice,
    AufPurchaseRepository,
    AufPurchaseService,
    AufReconciliationIssue,
)

MeowInvoiceError = AufInvoiceError
MeowInvoiceStatus = AufInvoiceStatus
MeowPurchaseInvoice = AufPurchaseInvoice
MeowPurchaseRepository = AufPurchaseRepository
MeowPurchaseService = AufPurchaseService
MeowReconciliationIssue = AufReconciliationIssue

__all__ = (
    "MeowInvoiceError", "MeowInvoiceStatus", "MeowPurchaseInvoice",
    "MeowPurchaseRepository", "MeowPurchaseService",
    "MeowReconciliationIssue",
)
