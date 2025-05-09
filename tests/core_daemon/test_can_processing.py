"""
Unit tests for the can_processing module in the core_daemon.

These tests cover the core logic of processing incoming CAN messages:
- Decoding messages using rvc_decoder.
- Mapping decoded data to entity IDs based on PGN, DGN, and instance.
- Handling known and unknown PGNs.
- Managing unmapped entries and suggesting potential mappings.
- Updating application state and broadcasting changes.
- Incrementing relevant Prometheus metrics.
- Error handling during decoding and processing.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from can import Message

# Directly import the global dictionaries to be cleared
from core_daemon.app_state import entity_id_lookup as global_entity_id_lookup
from core_daemon.app_state import unknown_pgns as global_unknown_pgns
from core_daemon.app_state import unmapped_entries as global_unmapped_entries
from core_daemon.can_processing import process_can_message
from core_daemon.models import SuggestedMapping, UnknownPGNEntry


@pytest.fixture(autouse=True)
def clear_global_state():
    """Clears global dictionaries in app_state used by can_processing before each test."""
    global_unknown_pgns.clear()
    global_unmapped_entries.clear()
    global_entity_id_lookup.clear()
    yield


@pytest.fixture
def mock_loop():
    """Provides a mock asyncio event loop."""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.is_running.return_value = True  # Assume loop is running for call_soon_threadsafe
    loop.create_task = lambda coro: coro  # Simplify task creation for tests
    return loop


@pytest.fixture
def mock_decoder_map():
    """Provides a mock decoder_map (PGN to specification mapping)."""
    return {
        0x12345: {"dgn_hex": "ABC", "name": "Test PGN ABC", "signals": []},  # Known PGN
        0x6789A: {
            "dgn_hex": "DEF",
            "name": "Test PGN DEF",
            "signals": [],
        },  # For device match
        0x1AF0001: {  # Example PGN for light
            "dgn_hex": "F000",
            "name": "LIGHT_COMMAND",
            "signals": [{"name": "LIGHT_ID", "start_bit": 0, "length": 8}],
            "type": "command",
            "pgn": 0x1AF00,
        },
    }


@pytest.fixture
def mock_device_lookup():
    """Provides a mock device_lookup map ((DGN_HEX, INSTANCE_STR) to entity_id)."""
    # This fixture was returning entity_prefix, but process_can_message expects
    # the full device configuration dictionary, similar to status_lookup.
    return {
        ("DEF", "0"): {
            "entity_id": "device_def_0",
            "device_type": "sensor",
            "friendly_name": "Device DEF 0",
        },
        ("DEF", "default"): {
            "entity_id": "device_def_default",
            "device_type": "sensor",
            "friendly_name": "Device DEF Default",
        },
        ("F000", "1"): {
            "entity_id": "light_switch_1",
            "device_type": "light",
            "friendly_name": "Light Switch 1",
        },
    }


@pytest.fixture
def mock_status_lookup():
    """Provides a mock status_lookup map ((DGN_HEX, INSTANCE_STR) to entity_id)."""
    # This fixture was returning entity_prefix, but process_can_message expects
    # the full device configuration dictionary.
    return {
        ("ABC", "1"): {
            "entity_id": "device_abc_1",
            "device_type": "thermostat",
            "friendly_name": "Device ABC 1",
        },
        ("ABC", "default"): {
            "entity_id": "device_abc_default",
            "device_type": "thermostat",
            "friendly_name": "Device ABC Default",
        },
    }


@pytest.fixture
def mock_pgn_hex_to_name_map():
    """Provides a mock pgn_hex_to_name_map (PGN hex string to PGN name)."""
    return {
        "123": "PGN_NAME_123",
        "1AF00": "LIGHT_COMMAND_PGN_NAME",
        "678": "PGN_NAME_678",  # (0x6789A >> 8) & 0x3FFFF -> 0x678
    }


@pytest.fixture
def mock_raw_device_mapping():
    """Provides a mock raw_device_mapping list used for generating suggestions."""
    return {
        "devices": [
            {
                "dgn_hex": "XYZ",
                "instance": "0",
                "name": "Device XYZ0",
                "suggested_area": "Area 1",
            },
            {
                "dgn_hex": "XYZ",
                "instance": "2",
                "name": "Device XYZ2",
                "suggested_area": "Area 2",
            },
        ]
    }


@pytest.fixture
def mock_can_msg():
    """Provides a sample can.Message object for testing."""
    return Message(arbitration_id=0x12345, data=b"\x01\x02\x03", is_extended_id=True)


# Mocks for Prometheus counters and gauges
# These are simplified. In a real setup, you might need to mock specific methods like
# `labels().inc()`
@pytest.fixture
def mock_metrics_patches():
    """Patches all Prometheus metrics used in can_processing."""
    patches = {
        "FRAME_COUNTER": patch("core_daemon.can_processing.FRAME_COUNTER", MagicMock()),
        "FRAME_LATENCY": patch("core_daemon.can_processing.FRAME_LATENCY", MagicMock()),
        "LOOKUP_MISSES": patch("core_daemon.can_processing.LOOKUP_MISSES", MagicMock()),
        "SUCCESSFUL_DECODES": patch("core_daemon.can_processing.SUCCESSFUL_DECODES", MagicMock()),
        "DECODE_ERRORS": patch("core_daemon.can_processing.DECODE_ERRORS", MagicMock()),
        "PGN_USAGE_COUNTER": patch("core_daemon.can_processing.PGN_USAGE_COUNTER", MagicMock()),
        "INST_USAGE_COUNTER": patch("core_daemon.can_processing.INST_USAGE_COUNTER", MagicMock()),
        "DGN_TYPE_GAUGE": patch("core_daemon.can_processing.DGN_TYPE_GAUGE", MagicMock()),
        "GENERATOR_COMMAND_COUNTER": patch(
            "core_daemon.can_processing.GENERATOR_COMMAND_COUNTER", MagicMock()
        ),
        "GENERATOR_STATUS_1_COUNTER": patch(
            "core_daemon.can_processing.GENERATOR_STATUS_1_COUNTER", MagicMock()
        ),
        "GENERATOR_STATUS_2_COUNTER": patch(
            "core_daemon.can_processing.GENERATOR_STATUS_2_COUNTER", MagicMock()
        ),
        "GENERATOR_DEMAND_COMMAND_COUNTER": patch(
            "core_daemon.can_processing.GENERATOR_DEMAND_COMMAND_COUNTER", MagicMock()
        ),
    }
    started_patches = {name: p.start() for name, p in patches.items()}
    yield started_patches  # Provides the dictionary of mocks to the test
    for p in started_patches.values():
        p.stop()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_known_pgn_status_lookup_found(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,  # from @patch
    mock_metrics_patches,  # from fixture
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing a known PGN where a matching entity is found via status_lookup.
    Ensures state is updated, metrics are incremented, and data is broadcast.
    """
    mock_can_msg.arbitration_id = 0x12345  # Matches mock_decoder_map["ABC"]
    mock_can_msg.data = b"\x01"
    decoded_data = {"signal1": 10, "operating_status": 1}  # operating_status for state_str
    raw_data = {"instance": "1", "operating_status": 1}  # Matches mock_status_lookup ("ABC", "1")
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Populate entity_id_lookup for the target entity
    # The entity_id comes from mock_status_lookup
    target_entity_id = mock_status_lookup[("ABC", "1")]["entity_id"]  # "device_abc_1"
    global_entity_id_lookup[target_entity_id] = {
        "friendly_name": "Friendly ABC 1",
        "suggested_area": "Living Room",
        "device_type": "thermostat",
        "capabilities": ["heat"],
        "groups": ["climate"],
    }

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )

    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x12345], mock_can_msg.data)
    # SUCCESSFUL_DECODES is called once per processed device, and once after decode
    assert mock_metrics_patches["SUCCESSFUL_DECODES"].inc.call_count == 2

    expected_payload_to_state = {
        "entity_id": target_entity_id,
        "value": decoded_data,
        "raw": raw_data,
        "state": "on",  # derived from operating_status > 0
        "timestamp": mock_update_state.call_args[0][1]["timestamp"],  # Get from actual call
        "suggested_area": "Living Room",
        "device_type": "thermostat",
        "capabilities": ["heat"],
        "friendly_name": "Friendly ABC 1",
        "groups": ["climate"],
    }
    mock_update_state.assert_called_once_with(target_entity_id, expected_payload_to_state)

    # broadcast_to_clients is called with json.dumps(payload)
    # We need to ensure the task was created and the loop was asked to run it
    assert mock_loop.call_soon_threadsafe.call_count == 1
    # The argument to call_soon_threadsafe is loop.create_task(coro_obj)
    # The coro_obj is broadcast_to_clients(json.dumps(expected_payload_to_state))
    # This is a bit tricky to assert directly without more complex mocking of create_task
    # For now, checking call_count of call_soon_threadsafe is a good indicator.

    pgn_val_hex = f"{(mock_can_msg.arbitration_id & 0x3FFFF):X}"  # 12345
    mock_metrics_patches["PGN_USAGE_COUNTER"].labels(pgn=pgn_val_hex).inc.assert_called_once()
    mock_metrics_patches["INST_USAGE_COUNTER"].labels(
        dgn="ABC", instance="1"
    ).inc.assert_called_once()
    mock_metrics_patches["DGN_TYPE_GAUGE"].labels(device_type="thermostat").set.assert_called_once()

    mock_metrics_patches["FRAME_LATENCY"].observe.assert_called_once()
    mock_metrics_patches["LOOKUP_MISSES"].inc.assert_not_called()
    mock_metrics_patches["DECODE_ERRORS"].inc.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_unknown_pgn(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing of a CAN message with an unknown PGN (not in decoder_map).
    Ensures the PGN is recorded in `global_unknown_pgns` and metrics are updated.
    """
    mock_can_msg.arbitration_id = 0xBADF00D  # Arbitrary PGN not in decoder_map
    mock_can_msg.data = b"\xde\xad\xbe\xef"
    original_time = time.time()

    with patch("time.time", return_value=original_time):
        process_can_message(
            mock_can_msg,
            "can0",
            mock_loop,
            mock_decoder_map,  # PGN 0xBADF00D is not in this map
            mock_device_lookup,
            mock_status_lookup,
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,
        )

    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()
    mock_metrics_patches["LOOKUP_MISSES"].inc.assert_called_once()  # For PGN not in decoder_map
    mock_decode_payload.assert_not_called()
    mock_update_state.assert_not_called()
    # mock_broadcast is called via loop.call_soon_threadsafe, which shouldn't be called
    mock_loop.call_soon_threadsafe.assert_not_called()

    arb_id_hex = f"{mock_can_msg.arbitration_id:X}"
    assert arb_id_hex in global_unknown_pgns
    assert global_unknown_pgns[arb_id_hex] == UnknownPGNEntry(
        arbitration_id_hex=arb_id_hex,
        first_seen_timestamp=original_time,
        last_seen_timestamp=original_time,
        count=1,
        last_data_hex=mock_can_msg.data.hex().upper(),
    )

    # Call again to check update of existing unknown PGN
    new_time = time.time() + 10
    new_data = b"\xaa\xbb"
    mock_can_msg.data = new_data
    # Reset counters that would have been incremented by the first call
    mock_metrics_patches["FRAME_COUNTER"].inc.reset_mock()
    mock_metrics_patches["LOOKUP_MISSES"].inc.reset_mock()

    with patch("time.time", return_value=new_time):
        process_can_message(
            mock_can_msg,  # Still PGN 0xBADF00D
            "can0",
            mock_loop,
            mock_decoder_map,
            mock_device_lookup,
            mock_status_lookup,
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,
        )
    assert global_unknown_pgns[arb_id_hex].count == 2
    assert global_unknown_pgns[arb_id_hex].last_seen_timestamp == new_time
    assert global_unknown_pgns[arb_id_hex].last_data_hex == new_data.hex().upper()
    mock_metrics_patches[
        "FRAME_COUNTER"
    ].inc.assert_called_once()  # Incremented for the second call
    mock_metrics_patches[
        "LOOKUP_MISSES"
    ].inc.assert_called_once()  # Incremented for the second call


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_decode_error(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test error handling when `rvc_decoder.decode_payload` raises an exception.
    Ensures the error is logged and relevant metrics (DECODE_ERRORS) are updated.
    """
    mock_can_msg.arbitration_id = 0x12345  # Known PGN from mock_decoder_map
    mock_decode_payload.side_effect = Exception("Test decode error")

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )

    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x12345], mock_can_msg.data)
    mock_metrics_patches["DECODE_ERRORS"].inc.assert_called_once()
    mock_update_state.assert_not_called()
    mock_loop.call_soon_threadsafe.assert_not_called()
    mock_logger.error.assert_called_once()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_dgn_or_instance_missing(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,  # Original fixture
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test scenarios where DGN or instance information is missing after decoding.
    Ensures lookup misses are recorded and no state updates occur.
    """
    mock_can_msg.arbitration_id = 0x12345  # PGN is in mock_decoder_map

    # Scenario 1: DGN missing from decoder_map entry (entry.get("dgn_hex") is None)
    # Create a faulty decoder map for this specific test case
    faulty_decoder_map_no_dgn = {0x12345: {"name": "Test PGN No DGN", "signals": []}}  # No dgn_hex
    mock_decode_payload.return_value = ({"s": 1}, {"instance": "1"})  # Valid decode and instance
    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        faulty_decoder_map_no_dgn,  # Use faulty map
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["LOOKUP_MISSES"].inc.assert_called_once()
    mock_update_state.assert_not_called()
    mock_loop.call_soon_threadsafe.assert_not_called()
    mock_logger.debug.assert_called_once()  # Should log about missing DGN/instance

    # Reset mocks for Scenario 2
    mock_metrics_patches["LOOKUP_MISSES"].inc.reset_mock()
    mock_update_state.reset_mock()
    mock_loop.call_soon_threadsafe.reset_mock()
    mock_logger.debug.reset_mock()
    mock_decode_payload.reset_mock()  # Reset side effect if any, and call count

    # Scenario 2: Instance missing from raw_data (raw.get("instance") is None)
    # Use the original valid mock_decoder_map
    mock_decode_payload.return_value = ({"s": 1}, {})  # No instance in raw data
    process_can_message(
        mock_can_msg,  # Still PGN 0x12345
        "can0",
        mock_loop,
        mock_decoder_map,  # Original valid map
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["LOOKUP_MISSES"].inc.assert_called_once()
    mock_update_state.assert_not_called()
    mock_loop.call_soon_threadsafe.assert_not_called()
    mock_logger.debug.assert_called_once()  # Should log about missing DGN/instance


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_no_matching_device_unmapped_entry_created(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,  # Original fixture
    mock_loop,
    mock_decoder_map,  # Original fixture
    mock_device_lookup,  # Original fixture
    mock_status_lookup,  # Original fixture
    mock_pgn_hex_to_name_map,  # Original fixture
    mock_raw_device_mapping,  # Original fixture
):
    """
    Test processing a message that decodes successfully but doesn\'t match any known device
    in status_lookup or device_lookup.
    Ensures an UnmappedEntryModel is created and stored.
    """
    mock_can_msg.arbitration_id = 0x6789A  # PGN is in mock_decoder_map, DGN: "DEF"
    mock_can_msg.data = b"\xdd"
    decoded_data = {"temp": 25, "operating_status": 0}
    # This instance "99" for DGN "DEF" won\'t be in mock_status_lookup or mock_device_lookup
    raw_data = {"instance": "99", "operating_status": 0}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Ensure the specific DGN/instance is not in the lookups for this test
    # (it shouldn\'t be based on the fixtures, but good to be explicit)
    assert ("DEF", "99") not in mock_status_lookup
    assert ("DEF", "99") not in mock_device_lookup
    # Also ensure default for "DEF" is not in status_lookup to force full miss
    clean_status_lookup = {k: v for k, v in mock_status_lookup.items() if k[0] != "DEF"}

    original_time = time.time()
    with patch("time.time", return_value=original_time):
        process_can_message(
            mock_can_msg,
            "can0",
            mock_loop,
            mock_decoder_map,
            mock_device_lookup,  # device_lookup has ("DEF", "default")
            clean_status_lookup,  # status_lookup does not have "DEF"
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,  # No suggestions for DGN "DEF"
        )

    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x6789A], mock_can_msg.data)
    # LOOKUP_MISSES is called once when no device is found after checking all lookups.
    mock_metrics_patches["LOOKUP_MISSES"].inc.assert_called_once()

    unmapped_key = "DEF-99"
    assert unmapped_key in global_unmapped_entries
    entry = global_unmapped_entries[unmapped_key]

    expected_pgn_hex = f"{(mock_can_msg.arbitration_id >> 8) & 0x3FFFF:X}".upper()  # "678"
    assert entry.pgn_hex == expected_pgn_hex
    assert entry.pgn_name == mock_pgn_hex_to_name_map.get(expected_pgn_hex)  # "PGN_NAME_678"
    assert entry.dgn_hex == "DEF"
    assert entry.dgn_name == mock_decoder_map[0x6789A]["name"]  # "Test PGN DEF"
    assert entry.instance == "99"
    assert entry.last_data_hex == mock_can_msg.data.hex().upper()  # "DD"
    assert entry.decoded_signals == decoded_data
    assert entry.first_seen_timestamp == original_time
    assert entry.last_seen_timestamp == original_time
    assert entry.count == 1
    assert entry.spec_entry == mock_decoder_map[0x6789A]
    assert entry.suggestions is None  # mock_raw_device_mapping doesn\'t have DGN "DEF"

    # Call again to check update of existing unmapped entry
    mock_metrics_patches["FRAME_COUNTER"].inc.reset_mock()
    mock_metrics_patches["LOOKUP_MISSES"].inc.reset_mock()
    mock_decode_payload.reset_mock()

    new_time = time.time() + 20
    new_data_bytes = b"\xee"
    mock_can_msg.data = new_data_bytes
    decoded_data_updated = {"temp": 26, "operating_status": 0}
    # Instance is still "99", DGN is still "DEF"
    mock_decode_payload.return_value = (decoded_data_updated, raw_data)

    with patch("time.time", return_value=new_time):
        process_can_message(
            mock_can_msg,
            "can0",
            mock_loop,
            mock_decoder_map,
            mock_device_lookup,
            clean_status_lookup,
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,
        )
    assert global_unmapped_entries[unmapped_key].count == 2
    assert global_unmapped_entries[unmapped_key].last_seen_timestamp == new_time
    assert (
        global_unmapped_entries[unmapped_key].last_data_hex == new_data_bytes.hex().upper()
    )  # "EE"
    assert global_unmapped_entries[unmapped_key].decoded_signals == decoded_data_updated

    mock_update_state.assert_not_called()  # Should not be called for unmapped entries
    mock_loop.call_soon_threadsafe.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_no_matching_device_with_suggestions(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,  # Original fixture
    mock_loop,
    mock_decoder_map,  # Original fixture
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,  # Original fixture, contains DGN "XYZ"
):
    """
    Test processing a message for an unmapped device where suggestions can be generated
    from `raw_device_mapping` based on the DGN.
    """
    # Use a PGN that maps to DGN "XYZ" for which mock_raw_device_mapping has entries
    # Add this PGN to a temporary decoder_map for this test
    pgn_for_xyz = 0xABCDE  # Made up PGN
    decoder_map_with_xyz = {
        **mock_decoder_map,
        pgn_for_xyz: {"dgn_hex": "XYZ", "name": "XYZ PGN", "signals": []},
    }
    mock_can_msg.arbitration_id = pgn_for_xyz
    mock_can_msg.data = b"\xff"
    decoded_data = {"val": 100, "operating_status": 0}
    # Instance "1" for DGN "XYZ" is NOT in mock_raw_device_mapping (which has "0" and "2")
    # so it will be unmapped, but suggestions should be generated.
    raw_data = {"instance": "1", "operating_status": 0}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        decoder_map_with_xyz,  # Use the map with DGN "XYZ"
        mock_device_lookup,  # Does not contain "XYZ"
        mock_status_lookup,  # Does not contain "XYZ"
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,  # Contains other instances for DGN "XYZ"
    )

    unmapped_key = "XYZ-1"
    assert unmapped_key in global_unmapped_entries
    entry = global_unmapped_entries[unmapped_key]
    assert entry.suggestions is not None
    assert len(entry.suggestions) == 2
    # Suggestions are from mock_raw_device_mapping for DGN "XYZ"
    expected_suggestions = [
        SuggestedMapping(instance="0", name="Device XYZ0", suggested_area="Area 1"),
        SuggestedMapping(instance="2", name="Device XYZ2", suggested_area="Area 2"),
    ]
    assert all(s in entry.suggestions for s in expected_suggestions)
    assert all(s in expected_suggestions for s in entry.suggestions)  # Check both ways

    mock_update_state.assert_not_called()
    mock_loop.call_soon_threadsafe.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_special_pgn_counters(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_loop,  # mock_can_msg is not used directly here
    mock_decoder_map,  # Original
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test that specific counters for generator-related PGNs are incremented correctly.
    These PGNs might not be fully processed if not in decoder_map or no device match,
    but their dedicated counters should still be hit early in the function.
    """
    # PGNs for special counters
    pgn_gen_cmd = 536861658
    pgn_gen_status1 = 436198557
    pgn_gen_status2 = 536861659
    pgn_gen_demand = 536870895

    # Minimal valid decode to allow processing to continue past decode stage if PGN is known
    # If PGN is unknown, it returns early, but counters are still hit.
    mock_decode_payload.return_value = ({"s": 1}, {"instance": "0", "operating_status": 0})

    # Test each special PGN
    # Case 1: PGN is in decoder_map (simulates normal processing path after counter)
    temp_decoder_map_with_gen = {
        **mock_decoder_map,
        pgn_gen_cmd: {"dgn_hex": "GENCMD", "name": "GEN_CMD", "signals": []},
    }
    msg_gen_cmd = Message(arbitration_id=pgn_gen_cmd, data=b"\x01", is_extended_id=True)
    process_can_message(
        msg_gen_cmd,
        "can0",
        mock_loop,
        temp_decoder_map_with_gen,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["GENERATOR_COMMAND_COUNTER"].inc.assert_called_once()
    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()  # Frame counter always hit

    # Case 2: PGN is NOT in decoder_map (simulates early return after counter)
    mock_metrics_patches["GENERATOR_STATUS_1_COUNTER"].inc.reset_mock()
    mock_metrics_patches["FRAME_COUNTER"].inc.reset_mock()  # Reset for this call
    msg_gen_status1 = Message(arbitration_id=pgn_gen_status1, data=b"\x01", is_extended_id=True)
    process_can_message(
        msg_gen_status1,
        "can0",
        mock_loop,
        mock_decoder_map,  # Original map, PGN not present
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["GENERATOR_STATUS_1_COUNTER"].inc.assert_called_once()
    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()

    # Test remaining PGNs (can assume they are not in the default mock_decoder_map)
    mock_metrics_patches["GENERATOR_STATUS_2_COUNTER"].inc.reset_mock()
    mock_metrics_patches["FRAME_COUNTER"].inc.reset_mock()
    msg_gen_status2 = Message(arbitration_id=pgn_gen_status2, data=b"\x01", is_extended_id=True)
    process_can_message(
        msg_gen_status2,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["GENERATOR_STATUS_2_COUNTER"].inc.assert_called_once()
    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()

    mock_metrics_patches["GENERATOR_DEMAND_COMMAND_COUNTER"].inc.reset_mock()
    mock_metrics_patches["FRAME_COUNTER"].inc.reset_mock()
    msg_gen_demand = Message(arbitration_id=pgn_gen_demand, data=b"\x01", is_extended_id=True)
    process_can_message(
        msg_gen_demand,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_metrics_patches["GENERATOR_DEMAND_COMMAND_COUNTER"].inc.assert_called_once()
    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_known_pgn_device_lookup_default_found(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_metrics_patches,
    mock_can_msg,  # Original fixture
    mock_loop,
    mock_decoder_map,  # Original fixture
    mock_device_lookup,  # Original fixture
    mock_status_lookup,  # Original fixture
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing a known PGN where a matching entity is found via device_lookup
    using a "default" instance mapping, after failing to find a specific instance in
    status_lookup and device_lookup.
    """
    mock_can_msg.arbitration_id = 0x6789A  # PGN in mock_decoder_map, DGN: "DEF"
    mock_can_msg.data = b"\x01"
    decoded_data = {"signal_def": 7, "operating_status": 1}
    # Instance "77" is not in mock_status_lookup or mock_device_lookup for DGN "DEF" specifically.
    # However, ("DEF", "default") IS in mock_device_lookup.
    raw_data = {"instance": "77", "operating_status": 1}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Ensure status_lookup does not have ("DEF", "77") or ("DEF", "default")
    # to force the check on device_lookup.
    clean_status_lookup = {k: v for k, v in mock_status_lookup.items() if k[0] != "DEF"}

    # Populate entity_id_lookup for the target entity from device_lookup["DEF", "default"]
    target_entity_id = mock_device_lookup[("DEF", "default")]["entity_id"]  # "device_def_default"
    global_entity_id_lookup[target_entity_id] = {
        "friendly_name": "Friendly DEF Default",
        "suggested_area": "Utility",
        "device_type": "sensor",
        "capabilities": [],
        "groups": ["system"],
    }

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,  # Contains ("DEF", "default")
        clean_status_lookup,  # Does not contain ("DEF", "77") or ("DEF", "default")
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )

    mock_metrics_patches["FRAME_COUNTER"].inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x6789A], mock_can_msg.data)

    expected_payload_to_state = {
        "entity_id": target_entity_id,  # "device_def_default"
        "value": decoded_data,
        "raw": raw_data,
        "state": "on",
        "timestamp": mock_update_state.call_args[0][1]["timestamp"],
        "suggested_area": "Utility",
        "device_type": "sensor",
        "capabilities": [],
        "friendly_name": "Friendly DEF Default",
        "groups": ["system"],
    }
    mock_update_state.assert_called_once_with(target_entity_id, expected_payload_to_state)
    mock_loop.call_soon_threadsafe.assert_called_once()  # For broadcast


@patch("core_daemon.can_processing.logger", MagicMock())  # Patch logger for this test
@patch("core_daemon.can_processing.broadcast_to_clients", new_callable=MagicMock)
@patch("core_daemon.can_processing.update_entity_state_and_history", new_callable=MagicMock)
@patch("rvc_decoder.decode_payload")
def test_process_entity_id_lookup_data_missing_uses_defaults(
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    # mock_logger is now patched at the function level
    logger_mock_local,  # Renamed to avoid conflict with global mock_logger fixture if any
    mock_metrics_patches,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test that when `entity_id_lookup.get(eid, {})` returns an empty dict (or missing keys),
    the payload construction uses default values as specified.
    """
    mock_can_msg.arbitration_id = 0x12345  # DGN: ABC, Instance: 1 (from mock_status_lookup)
    mock_can_msg.data = b"\x01"
    decoded_data = {"signal1": 10, "operating_status": 1}
    raw_data = {"instance": "1", "operating_status": 1}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Target entity_id from mock_status_lookup
    target_entity_id = mock_status_lookup[("ABC", "1")]["entity_id"]  # "device_abc_1"

    # Ensure global_entity_id_lookup does NOT contain target_entity_id,
    # or contains it with an empty dict, to test default value usage.
    global_entity_id_lookup.pop(target_entity_id, None)  # Remove if exists
    # OR: global_entity_id_lookup[target_entity_id] = {}

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        mock_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )

    # Check that update_entity_state_and_history was called with default values
    # for fields that would come from entity_id_lookup
    expected_payload_with_defaults = {
        "entity_id": target_entity_id,
        "value": decoded_data,
        "raw": raw_data,
        "state": "on",
        "timestamp": mock_update_state.call_args[0][1]["timestamp"],  # Get from actual call
        "suggested_area": "Unknown",  # Default
        "device_type": "unknown",  # Default
        "capabilities": [],  # Default
        "friendly_name": None,  # Default (get returns None if key missing)
        "groups": [],  # Default
    }
    mock_update_state.assert_called_once_with(target_entity_id, expected_payload_with_defaults)
    mock_loop.call_soon_threadsafe.assert_called_once()  # For broadcast
    logger_mock_local.warning.assert_not_called()
