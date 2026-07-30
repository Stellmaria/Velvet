"""Compatibility aliases for retired Meow purchase names."""

from velvet_bot.domains.auf_wallet.purchase import (
    AufInvoiceError,
    AufInvoiceStatus,
    AufPurchaseInvoice,
    AufPurchaseRepository,
    AufPurchaseService,
    AufReconciliationIssue,
)

AufInvoiceError = AufInvoiceError
AufInvoiceStatus = AufInvoiceStatus
AufPurchaseInvoice = AufPurchaseInvoice
AufPurchaseRepository = AufPurchaseRepository
AufPurchaseService = AufPurchaseService
AufReconciliationIssue = AufReconciliationIssue

__all__ = (
    "AufInvoiceError", "AufInvoiceStatus", "AufPurchaseInvoice",
    "AufPurchaseRepository", "AufPurchaseService",
    "AufReconciliationIssue",
)
