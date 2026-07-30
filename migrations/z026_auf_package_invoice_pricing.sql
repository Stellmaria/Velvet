-- Apply the active fixed RUB package price to every newly created invoice.

CREATE OR REPLACE FUNCTION apply_auf_package_invoice_price()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    fixed_price NUMERIC(12, 2);
BEGIN
    SELECT price_rub INTO fixed_price
    FROM auf_package_prices
    WHERE package_auf = NEW.package_auf
      AND is_active = TRUE
      AND effective_from <= NOW()
      AND (effective_to IS NULL OR effective_to > NOW())
    LIMIT 1;

    IF fixed_price IS NOT NULL THEN
        NEW.final_local_amount := fixed_price;
        IF NEW.locked_exchange_rate > 0 THEN
            NEW.package_price_usd := ROUND(fixed_price / NEW.locked_exchange_rate, 2);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS auf_purchase_invoice_fixed_price ON auf_purchase_invoices;
CREATE TRIGGER auf_purchase_invoice_fixed_price
BEFORE INSERT ON auf_purchase_invoices
FOR EACH ROW
EXECUTE FUNCTION apply_auf_package_invoice_price();
