# Public ITCH reconstructed input extension

The original signed LOBSTER sample contract remains unchanged. Public ITCH 5.0
P messages do not disclose the resting side: their wire B value is a placeholder.
Reconstructed datasets must not turn that placeholder into a known sell trade.

For those inputs only, type-5 executions may use `direction=0`. All other event
types still require a known passive side (-1 or +1). Tables containing unknown
sides must omit optional `aggressor_side` and `signed_volume` columns. Use
`PipelineConfig(trade_signing="quote_test")` and explicit original paired
message/orderbook inputs. A known-direction run fails on unknown sides.

The original pre-event book determines the Quote Test sign. Inside-spread trades
remain unclassified. Total trade volume remains available, complete TI is null
in affected intervals, and classified TI plus classification counts/volumes stay
separate. This is the existing Quote Test output behavior, not a new imputation.

Reconstructed raw files are identified as reconstructed NASDAQ BX data, not
LOBSTER vendor downloads. Atomic U replaces remain single observations with the
new-order submission fields and `source_event_type=U` provenance; they are not
split into two observations sharing a final snapshot. Reference-price moves are
computed from actual consecutive post-event states.
