def test_instrument_service_resolves_canonical_and_broker_symbol():
    from app.services.instruments import InstrumentService

    service = InstrumentService.with_seed_data()

    instrument = service.resolve(canonical_symbol="RB2510")
    broker = service.resolve(broker_symbol="rb2510", broker_id="ctp")

    assert instrument is not None
    assert broker is not None
    assert broker.canonical_symbol == instrument.canonical_symbol
    assert service.to_broker_symbol("RB2510", "ctp") == "rb2510"
