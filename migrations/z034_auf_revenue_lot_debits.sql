-- Keep the revenue basis aligned when non-task wallet operations remove units.
-- Task reserves are handled by auf_task_charge_lot_allocations; this migration
-- covers owner manual debits and negative adjustments only.

CREATE TABLE IF NOT EXISTS auf_wallet_debit_lot_allocations (
    entry_id BIGINT NOT NULL REFERENCES auf_wallet_entries(id) ON DELETE RESTRICT,
    lot_id BIGINT NOT NULL REFERENCES auf_revenue_lots(id),
    allocated_units BIGINT NOT NULL CHECK (allocated_units > 0),
    allocated_revenue_usd NUMERIC(20, 8) NOT NULL CHECK (allocated_revenue_usd >= 0),
    basis_quality VARCHAR(16) NOT NULL
        CHECK (basis_quality IN ('actual', 'estimated', 'zero')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entry_id, lot_id)
);

CREATE OR REPLACE FUNCTION consume_auf_wallet_debit_revenue()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    lot auf_revenue_lots%ROWTYPE;
    needed BIGINT;
    take_units BIGINT;
    take_revenue NUMERIC(20, 8);
BEGIN
    IF NEW.amount_units >= 0
       OR NEW.operation_type NOT IN ('manual_debit', 'adjustment') THEN
        RETURN NEW;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM auf_wallet_debit_lot_allocations
        WHERE entry_id = NEW.id
    ) THEN
        RETURN NEW;
    END IF;

    needed := -NEW.amount_units;
    FOR lot IN
        SELECT *
        FROM auf_revenue_lots
        WHERE workspace_id = NEW.workspace_id
          AND remaining_units > 0
        ORDER BY created_at, id
        FOR UPDATE
    LOOP
        EXIT WHEN needed = 0;
        take_units := LEAST(needed, lot.remaining_units);
        IF take_units = lot.remaining_units THEN
            take_revenue := lot.remaining_revenue_usd;
        ELSE
            take_revenue := ROUND(
                lot.remaining_revenue_usd
                * take_units::NUMERIC / lot.remaining_units::NUMERIC,
                8
            );
        END IF;

        UPDATE auf_revenue_lots
        SET remaining_units = remaining_units - take_units,
            remaining_revenue_usd = remaining_revenue_usd - take_revenue
        WHERE id = lot.id;

        INSERT INTO auf_wallet_debit_lot_allocations (
            entry_id, lot_id, allocated_units,
            allocated_revenue_usd, basis_quality
        )
        VALUES (
            NEW.id, lot.id, take_units,
            take_revenue, lot.basis_quality
        );
        needed := needed - take_units;
    END LOOP;

    IF needed <> 0 THEN
        RAISE EXCEPTION
            'Auf revenue lots cover % fewer units than wallet debit % requires',
            needed, NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS auf_wallet_debit_revenue_allocation ON auf_wallet_entries;
CREATE TRIGGER auf_wallet_debit_revenue_allocation
AFTER INSERT ON auf_wallet_entries
FOR EACH ROW
EXECUTE FUNCTION consume_auf_wallet_debit_revenue();
