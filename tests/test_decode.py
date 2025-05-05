import pytest
from rvc_decoder import get_bits, decode_payload, load_config_data

def test_get_bits_simple():
    data = bytes([0b10110010] + [0]*7)
    assert get_bits(data, 1, 3) == 0b001

def test_decode_payload_with_sample_entry():
    entry = {
        "signals": [
            {"name": "foo", "start_bit": 0, "length": 8, "scale": 1, "offset": 0}
        ]
    }
    decoded, raw = decode_payload(entry, b"\x2A" + b"\x00"*7)
    assert raw["foo"] == 0x2A
    assert decoded["foo"] == "42"

@pytest.fixture
def decoder_map():
    # no args → loads src/rvc_decoder/config/rvc.json and device_mapping.yml
    dm, *_ = load_config_data()
    return dm

def test_decoder_map_keys(decoder_map):
    # Replace with a PGN you know is in your spec
    assert 0x1FEDA in decoder_map
