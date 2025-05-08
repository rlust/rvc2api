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

from core_daemon.app_state import entity_id_lookup, unknown_pgns, unmapped_entries
from core_daemon.can_processing import process_can_message
from core_daemon.models import SuggestedMapping, UnknownPGNEntry


@pytest.fixture(autouse=True)
def clear_global_state():
    """Clears global dictionaries in app_state used by can_processing before each test."""
    unknown_pgns.clear()
    unmapped_entries.clear()
    entity_id_lookup.clear()
    yield


@pytest.fixture
def mock_loop():
    """Provides a mock asyncio event loop."""
    return MagicMock(spec=asyncio.AbstractEventLoop)


@pytest.fixture
def mock_decoder_map():
    """Provides a mock decoder_map (PGN to specification mapping)."""
    return {
        0x12345: {"dgn_hex": "ABC", "name": "Test PGN", "signals": []},  # Known PGN
        0x6789A: {
            "dgn_hex": "DEF",
            "name": "Another PGN",
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
    """Provides a mock device_lookup map ((DGN_HEX, INSTANCE_STR) to entity_prefix)."""
    return {
        ("DEF", "0"): "device_def_0",
        ("DEF", "default"): "device_def_default",
        ("F000", "1"): "light_switch_1",  # For light_command
    }


@pytest.fixture
def mock_status_lookup():
    """Provides a mock status_lookup map ((DGN_HEX, INSTANCE_STR) to entity_prefix)."""
    return {
        ("ABC", "1"): "device_abc_1",
        ("ABC", "default"): "device_abc_default",
    }


@pytest.fixture
def mock_pgn_hex_to_name_map():
    """Provides a mock pgn_hex_to_name_map (PGN hex string to PGN name)."""
    return {"123": "PGN_NAME_123", "1AF00": "LIGHT_COMMAND_PGN_NAME"}  # PGN for F000 DGN


@pytest.fixture
def mock_raw_device_mapping():
    """Provides a mock raw_device_mapping list used for generating suggestions."""
    return {
        "devices": [
            {"dgn_hex": "XYZ", "instance": "0", "name": "Device XYZ0", "suggested_area": "Area 1"},
            {"dgn_hex": "XYZ", "instance": "2", "name": "Device XYZ2", "suggested_area": "Area 2"},
        ]
    }


@pytest.fixture
def mock_can_msg():
    """Provides a sample can.Message object for testing."""
    return Message(arbitration_id=0x12345, data=b"\\x01\\x02\\x03", is_extended_id=True)


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.FRAME_LATENCY")
@patch("core_daemon.can_processing.LOOKUP_MISSES")
@patch("core_daemon.can_processing.SUCCESSFUL_DECODES")
@patch("core_daemon.can_processing.DECODE_ERRORS")
@patch("core_daemon.can_processing.PGN_USAGE_COUNTER")
@patch("core_daemon.can_processing.DGN_TYPE_GAUGE")
@patch("core_daemon.can_processing.GENERATOR_COMMAND_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_STATUS_1_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_STATUS_2_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_DEMAND_COMMAND_COUNTER")
def test_process_known_pgn_status_lookup_found(
    mock_gen_demand_cmd,
    mock_gen_status2,
    mock_gen_status1,
    mock_gen_cmd,
    mock_dgn_gauge,
    mock_pgn_usage,
    mock_decode_errors,
    mock_successful_decodes,
    mock_lookup_misses,
    mock_frame_latency,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
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
    mock_can_msg.arbitration_id = 0x12345  # Matches mock_decoder_map and mock_status_lookup
    mock_can_msg.data = b"\\x01"  # Some data
    decoded_data = {"signal1": 10}
    raw_data = {"instance": "1"}  # Matches mock_status_lookup
    mock_decode_payload.return_value = (decoded_data, raw_data)

    entity_id_lookup[("device_abc_1", "signal1")] = "sensor.device_abc_1_signal1"

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

    mock_frame_counter.inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x12345], mock_can_msg.data)
    mock_successful_decodes.inc.assert_called_once()
    mock_update_state.assert_called_once()
    mock_broadcast.assert_called_once()
    mock_pgn_usage.labels(
        pgn_hex="12345",
        pgn_name="Test PGN",
        entity_id="sensor.device_abc_1_signal1",
        entity_name="device_abc_1_signal1",
        device_name="device_abc_1",
    ).inc.assert_called_once()
    mock_dgn_gauge.labels(
        dgn_hex="ABC",
        entity_id="sensor.device_abc_1_signal1",
        entity_name="device_abc_1_signal1",
        device_name="device_abc_1",
    ).set.assert_called_once()
    mock_frame_latency.observe.assert_called_once()
    mock_lookup_misses.inc.assert_not_called()
    mock_decode_errors.inc.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.LOOKUP_MISSES")
def test_process_unknown_pgn(
    mock_lookup_misses,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing of a CAN message with an unknown PGN.
    Ensures the PGN is recorded in `unknown_pgns` and metrics are updated.
    """
    mock_can_msg.arbitration_id = 0xBADF00D  # Arbitrary PGN not in decoder_map
    original_time = time.time()
    with patch("time.time", return_value=original_time):
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

    mock_frame_counter.inc.assert_called_once()
    mock_lookup_misses.inc.assert_called_once()
    mock_decode_payload.assert_not_called()
    mock_update_state.assert_not_called()
    mock_broadcast.assert_not_called()

    arb_id_hex = f"{mock_can_msg.arbitration_id:X}"
    assert arb_id_hex in unknown_pgns
    assert unknown_pgns[arb_id_hex] == UnknownPGNEntry(
        arbitration_id_hex=arb_id_hex,
        first_seen_timestamp=original_time,
        last_seen_timestamp=original_time,
        count=1,
        last_data_hex=mock_can_msg.data.hex().upper(),
    )

    # Call again to check update
    new_time = time.time() + 10
    new_data = b"\\xAA"
    mock_can_msg.data = new_data
    with patch("time.time", return_value=new_time):
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
    assert unknown_pgns[arb_id_hex].count == 2
    assert unknown_pgns[arb_id_hex].last_seen_timestamp == new_time
    assert unknown_pgns[arb_id_hex].last_data_hex == new_data.hex().upper()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.DECODE_ERRORS")
def test_process_decode_error(
    mock_decode_errors,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
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
    mock_can_msg.arbitration_id = 0x12345  # Known PGN
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

    mock_frame_counter.inc.assert_called_once()
    mock_decode_payload.assert_called_once()
    mock_decode_errors.inc.assert_called_once()
    mock_update_state.assert_not_called()
    mock_broadcast.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.LOOKUP_MISSES")
def test_process_dgn_or_instance_missing(
    mock_lookup_misses,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test scenarios where DGN or instance information is missing after decoding.
    Ensures lookup misses are recorded and no state updates occur.
    """
    mock_can_msg.arbitration_id = 0x12345
    # Scenario 1: DGN missing from decoder_map entry (though schema implies it should be there)
    faulty_decoder_map = {0x12345: {"name": "Test PGN", "signals": []}}  # No dgn_hex
    mock_decode_payload.return_value = ({"s": 1}, {"instance": "1"})
    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        faulty_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_lookup_misses.inc.assert_called_once()

    # Scenario 2: Instance missing from raw_data
    mock_lookup_misses.reset_mock()
    mock_decode_payload.return_value = ({"s": 1}, {})  # No instance
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
    mock_lookup_misses.inc.assert_called_once()
    mock_update_state.assert_not_called()
    mock_broadcast.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.LOOKUP_MISSES")
def test_process_no_matching_device_unmapped_entry_created(
    mock_lookup_misses,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,  # mock_device_lookup is the original fixture
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing a message that decodes successfully but doesn't match any known device.
    Ensures an UnmappedEntryModel is created and stored, and no suggestions are made if none fit.
    """
    mock_can_msg.arbitration_id = 0x6789A  # DGN: DEF
    mock_can_msg.data = b"\\xDD"
    decoded_data = {"temp": 25}
    raw_data = {"instance": "99"}  # This instance won't be in device_lookup or status_lookup
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Create a device_lookup for this test that will not find DGN "DEF"
    # The original mock_device_lookup fixture provides:
    # {
    #     ("DEF", "0"): "device_def_0",
    #     ("DEF", "default"): "device_def_default",  <-- This would cause a match
    #     ("F000", "1"): "light_switch_1",
    # }
    # We filter out "DEF" entries to ensure no match for this test's purpose.
    device_lookup_for_this_test = {
        key: value for key, value in mock_device_lookup.items() if key[0] != "DEF"
    }
    # mock_status_lookup fixture does not contain "DEF" entries, which is correct for this test.

    original_time = time.time()
    with patch("time.time", return_value=original_time):
        process_can_message(
            mock_can_msg,
            "can0",
            mock_loop,
            mock_decoder_map,
            device_lookup_for_this_test,  # Use the filtered device_lookup
            mock_status_lookup,  # mock_status_lookup is already suitable
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,
        )

    mock_frame_counter.inc.assert_called_once()
    mock_decode_payload.assert_called_once()
    # First miss is for the specific DGN/Inst, second for default DGN/Inst in status_lookup,
    # third for specific DGN/Inst in device_lookup, fourth for default DGN/Inst in device_lookup
    assert mock_lookup_misses.inc.call_count == 1  # Simplified: one overall "no device" outcome

    unmapped_key = "DEF-99"
    assert unmapped_key in unmapped_entries
    entry = unmapped_entries[unmapped_key]
    assert entry.pgn_hex == "678"  # (0x6789A >> 8) & 0x3FFFF -> 0x678
    assert entry.pgn_name == mock_pgn_hex_to_name_map.get(
        entry.pgn_hex
    )  # Might be None if not in map
    assert entry.dgn_hex == "DEF"
    assert entry.dgn_name == "Another PGN"
    assert entry.instance == "99"
    assert entry.last_data_hex == "DD"
    assert entry.decoded_signals == decoded_data
    assert entry.first_seen_timestamp == original_time
    assert entry.last_seen_timestamp == original_time
    assert entry.count == 1
    assert entry.spec_entry == mock_decoder_map[0x6789A]
    assert entry.suggestions is None  # No suggestions for DGN "DEF" in mock_raw_device_mapping

    # Call again to check update
    new_time = time.time() + 20
    new_data = b"\\xEE"
    mock_can_msg.data = new_data
    decoded_data_updated = {"temp": 26}
    mock_decode_payload.return_value = (decoded_data_updated, raw_data)  # instance is still "99"

    with patch("time.time", return_value=new_time):
        process_can_message(
            mock_can_msg,
            "can0",
            mock_loop,
            mock_decoder_map,
            device_lookup_for_this_test,  # Use the filtered device_lookup again
            mock_status_lookup,
            mock_pgn_hex_to_name_map,
            mock_raw_device_mapping,
        )
    assert unmapped_entries[unmapped_key].count == 2
    assert unmapped_entries[unmapped_key].last_seen_timestamp == new_time
    assert unmapped_entries[unmapped_key].last_data_hex == "EE"
    assert unmapped_entries[unmapped_key].decoded_signals == decoded_data_updated

    mock_update_state.assert_not_called()
    mock_broadcast.assert_not_called()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.LOOKUP_MISSES")
def test_process_no_matching_device_with_suggestions(
    mock_lookup_misses,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing a message for an unmapped device where suggestions can be generated
    from `raw_device_mapping` based on the DGN.
    """
    # Use a DGN that has other instances in mock_raw_device_mapping
    mock_can_msg.arbitration_id = 0xABCDE  # Made up, ensure it maps to a new DGN "XYZ"
    decoder_map_with_xyz = {
        **mock_decoder_map,
        0xABCDE: {"dgn_hex": "XYZ", "name": "XYZ PGN", "signals": []},
    }
    mock_can_msg.data = b"\\xFF"
    decoded_data = {"val": 100}
    raw_data = {
        "instance": "1"
    }  # This instance "1" for DGN "XYZ" is not in mock_raw_device_mapping
    mock_decode_payload.return_value = (decoded_data, raw_data)

    process_can_message(
        mock_can_msg,
        "can0",
        mock_loop,
        decoder_map_with_xyz,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )

    unmapped_key = "XYZ-1"
    assert unmapped_key in unmapped_entries
    entry = unmapped_entries[unmapped_key]
    assert entry.suggestions is not None
    assert len(entry.suggestions) == 2
    assert (
        SuggestedMapping(instance="0", name="Device XYZ0", suggested_area="Area 1")
        in entry.suggestions
    )
    assert (
        SuggestedMapping(instance="2", name="Device XYZ2", suggested_area="Area 2")
        in entry.suggestions
    )


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_COMMAND_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_STATUS_1_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_STATUS_2_COUNTER")
@patch("core_daemon.can_processing.GENERATOR_DEMAND_COMMAND_COUNTER")
def test_special_pgn_counters(
    mock_gen_demand_cmd,
    mock_gen_status2,
    mock_gen_status1,
    mock_gen_cmd,
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test that specific counters for generator-related PGNs are incremented correctly.
    """
    # These PGNs will result in LOOKUP_MISSES for decode if not in decoder_map,
    # but their specific counters should still be incremented.
    # We add them to decoder_map to allow processing to continue far enough to check other things.
    test_decoder_map = {
        **mock_decoder_map,
        536861658: {"dgn_hex": "GENCMD", "name": "GEN_CMD", "signals": []},
        436198557: {"dgn_hex": "GENS1", "name": "GEN_S1", "signals": []},
        536861659: {"dgn_hex": "GENS2", "name": "GEN_S2", "signals": []},
        536870895: {"dgn_hex": "GENDEM", "name": "GEN_DEM", "signals": []},
    }
    # Mock decode_payload to return minimal valid structure to prevent other errors
    mock_decode_payload.return_value = ({"s": 1}, {"instance": "0"})

    msg = Message(arbitration_id=536861658, data=b"\\x01")  # GENERATOR_COMMAND
    process_can_message(
        msg,
        "can0",
        mock_loop,
        test_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_gen_cmd.inc.assert_called_once()

    msg = Message(arbitration_id=436198557, data=b"\\x01")  # GENERATOR_STATUS_1
    process_can_message(
        msg,
        "can0",
        mock_loop,
        test_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_gen_status1.inc.assert_called_once()

    msg = Message(arbitration_id=536861659, data=b"\\x01")  # GENERATOR_STATUS_2
    process_can_message(
        msg,
        "can0",
        mock_loop,
        test_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_gen_status2.inc.assert_called_once()

    msg = Message(arbitration_id=536870895, data=b"\\x01")  # GENERATOR_DEMAND_COMMAND
    process_can_message(
        msg,
        "can0",
        mock_loop,
        test_decoder_map,
        mock_device_lookup,
        mock_status_lookup,
        mock_pgn_hex_to_name_map,
        mock_raw_device_mapping,
    )
    mock_gen_demand_cmd.inc.assert_called_once()

    assert mock_frame_counter.inc.call_count == 4


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients")
@patch("core_daemon.can_processing.update_entity_state_and_history")
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
def test_process_known_pgn_device_lookup_default_found(
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test processing a known PGN where a matching entity is found via device_lookup
    using a default instance mapping when a specific instance isn't found.
    """
    mock_can_msg.arbitration_id = 0x6789A  # DGN: DEF
    mock_can_msg.data = b"\\x01"
    decoded_data = {"signal_def": 7}
    # Instance "77" is not in status_lookup directly, nor device_lookup directly
    # but "DEF", "default" is in device_lookup
    raw_data = {"instance": "77"}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # Ensure status_lookup does not have ("DEF", "77") or ("DEF", "default")
    # to force check on device_lookup
    clean_status_lookup = {k: v for k, v in mock_status_lookup.items() if k[0] != "DEF"}

    entity_id_lookup[("device_def_default", "signal_def")] = "sensor.device_def_default_signal_def"

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

    mock_frame_counter.inc.assert_called_once()
    mock_decode_payload.assert_called_once_with(mock_decoder_map[0x6789A], mock_can_msg.data)
    mock_update_state.assert_called_once()
    # Check that the correct entity_prefix ("device_def_default") was used
    args, kwargs = mock_update_state.call_args
    assert args[0] == "device_def_default"  # entity_prefix
    mock_broadcast.assert_called_once()


@patch("core_daemon.can_processing.logger", MagicMock())
@patch("core_daemon.can_processing.broadcast_to_clients", MagicMock())
@patch("core_daemon.can_processing.update_entity_state_and_history", MagicMock())
@patch("rvc_decoder.decode_payload")
@patch("core_daemon.can_processing.FRAME_COUNTER")
def test_process_entity_id_not_found_logs_warning(
    mock_frame_counter,
    mock_decode_payload,
    mock_update_state,
    mock_broadcast,
    mock_logger,
    mock_can_msg,
    mock_loop,
    mock_decoder_map,
    mock_device_lookup,
    mock_status_lookup,
    mock_pgn_hex_to_name_map,
    mock_raw_device_mapping,
):
    """
    Test that a warning is logged when a decoded signal does not have a corresponding
    entry in `entity_id_lookup`, while other signals in the same message are processed.
    """
    mock_can_msg.arbitration_id = 0x12345  # DGN: ABC, Instance: 1 (from status_lookup)
    mock_can_msg.data = b"\\x01"
    decoded_data = {
        "signal1": 10,
        "unknown_signal": 5,
    }  # unknown_signal won't be in entity_id_lookup
    raw_data = {"instance": "1"}
    mock_decode_payload.return_value = (decoded_data, raw_data)

    # entity_id_lookup has an entry for "signal1" but not for "unknown_signal"
    entity_id_lookup[("device_abc_1", "signal1")] = "sensor.device_abc_1_signal1"

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

    # update_entity_state_and_history should be called for "signal1"
    mock_update_state.assert_any_call(
        "device_abc_1",
        "sensor.device_abc_1_signal1",
        10,
        mock_decoder_map[0x12345],
        "ABC",
        "1",
        decoded_data,
        mock_can_msg.arbitration_id,
    )
    # broadcast should be called for "signal1"
    mock_broadcast.assert_any_call(
        mock_loop,
        "sensor.device_abc_1_signal1",
        10,
        "device_abc_1",
        "signal1",
        {"source": "rvc", "dgn": "ABC", "instance": "1", "pgn": mock_can_msg.arbitration_id},
    )

    # Check that a warning was logged for "unknown_signal"
    # This relies on the logger mock capturing calls.
    # We expect one call for the known signal, and one warning for the unknown.
    # The actual check for the warning message content might be too brittle.
    # For now, we check that update_state was called once (for the known signal)
    # and broadcast was called once.
    # The logic inside process_can_message iterates signals, so if one is unknown,
    # it logs and continues.
    assert mock_update_state.call_count == 1
    assert mock_broadcast.call_count == 1

    # A more specific check for the log:
    found_warning = False
    for call_args in mock_logger.warning.call_args_list:
        if "No entity_id found for signal unknown_signal" in call_args[0][0]:
            found_warning = True
            break
    assert found_warning, "Expected warning for unknown signal was not logged"
