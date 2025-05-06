"""
rvc_decoder.decode

Core decoding logic for RV-C CAN frames, including loading of spec and device mapping data.
"""
import os
import sys
import json
import yaml
import logging
from importlib import resources


def _default_paths():
    """
    Determine default paths for the rvc spec and device mapping files bundled as package data.
    """
    # Expect config files to live under the 'config' directory in this package
    cfg_dir = resources.files(__package__) / "config"
    return (
        str(cfg_dir / "rvc.json"),
        str(cfg_dir / "device_mapping.yml"),
    )


def get_bits(data_bytes: bytes, start_bit: int, length: int) -> int:
    """
    Extract a little‑endian bitfield from an 8‑byte CAN payload.
    """
    raw_int = int.from_bytes(data_bytes, byteorder='little')
    mask = (1 << length) - 1
    return (raw_int >> start_bit) & mask


def decode_payload(entry: dict, data_bytes: bytes):
    """
    Decode all 'signals' in a spec entry:
      - raw_values: the integer bitfields
      - decoded: human‑readable strings (with scale/offset/enum logic)

    Returns:
      tuple(decoded: dict[str,str], raw_values: dict[str,int])
    """
    decoded = {}
    raw_values = {}

    for sig in entry.get('signals', []):
        raw = get_bits(data_bytes, sig['start_bit'], sig['length'])
        raw_values[sig['name']] = raw

        # apply scale/offset
        val = raw * sig.get('scale', 1) + sig.get('offset', 0)
        unit = sig.get('unit', '')

        # enum lookup if present
        if 'enum' in sig:
            formatted = sig['enum'].get(str(raw), f"UNKNOWN ({raw})")
        # floats or non‑1 scale/offset get 2‑decimals
        elif sig.get('scale', 1) != 1 or sig.get('offset', 0) != 0 or isinstance(val, float):
            formatted = f"{val:.2f}{unit}"
        else:
            formatted = f"{int(val)}{unit}"

        decoded[sig['name']] = formatted

    return decoded, raw_values


def load_config_data(
    rvc_spec_path: str | None = None,
    device_mapping_path: str | None = None,
):
    """
    Load and parse:
      1. RVC spec JSON → decoder_map (PGN→spec entry, adds 'dgn_hex')
      2. device_mapping YAML →
         • device_lookup ((dgn_hex,inst)→config)
         • status_lookup ((status_dgn,inst)→config)
         • entity_id_lookup (id→config)
         • light_entity_ids (set of IDs)
         • light_command_info (id→{dgn,instance,interface})

    If paths are not provided, defaults to bundled config files.

    Returns:
      decoder_map: dict[int,dict],
      device_mapping: dict,
      device_lookup: dict[tuple[str,str],dict],
      status_lookup: dict[tuple[str,str],dict],
      light_entity_ids: set[str],
      entity_id_lookup: dict[str,dict],
      light_command_info: dict[str,dict]
    """
    # Determine default paths if not overridden
    if rvc_spec_path is None or device_mapping_path is None:
        default_spec, default_map = _default_paths()
        rvc_spec_path = rvc_spec_path or default_spec
        device_mapping_path = device_mapping_path or default_map
    logging.info(f"Using RVC Spec Path: {rvc_spec_path}")
    logging.info(f"Using Device Mapping Path: {device_mapping_path}")

    # 1) Load spec
    if not os.path.exists(rvc_spec_path) or not os.access(rvc_spec_path, os.R_OK):
        logging.error(f"Cannot read RVC spec: {rvc_spec_path}")
        sys.exit(1)
    with open(rvc_spec_path) as f:
        spec_content = json.load(f)

    specs = spec_content.get('messages', [])
    decoder_map: dict[int, dict] = {}
    for entry in specs:
        sid = entry.get('id')
        if sid is None:
            logging.warning(f"Skipping spec without 'id': {entry}")
            continue
        try:
            dec_id = sid if isinstance(sid, int) else int(sid, 16)
        except ValueError:
            logging.warning(f"Invalid 'id' in spec: {sid}")
            continue
        entry['dgn_hex'] = f"{(dec_id >> 8) & 0x3FFFF:X}"
        decoder_map[dec_id] = entry
    logging.info(f"Loaded {len(decoder_map)} spec entries.")

    # 2) Load device mapping
    device_mapping: dict = {}
    device_lookup: dict = {}
    status_lookup: dict = {}
    entity_id_lookup: dict = {}
    light_entity_ids: set = set()
    light_command_info: dict = {}

    if os.path.exists(device_mapping_path):
        with open(device_mapping_path) as f:
            raw_map = yaml.safe_load(f) or {}
        templates = raw_map.get('templates', {})
        device_mapping = raw_map

        for dgn_hex, instances in raw_map.items():
            if dgn_hex == 'templates' or not isinstance(instances, dict):
                continue
            for inst_str, configs in instances.items():
                if not isinstance(configs, list):
                    continue
                for cfg in configs:
                    if not isinstance(cfg, dict):
                        continue
                    tmpl = cfg.pop('<<', None)
                    merged = {**templates.get(tmpl, {}), **cfg} if tmpl else cfg

                    eid = merged.get('entity_id')
                    fname = merged.get('friendly_name')
                    if eid and fname:
                        key = (dgn_hex.upper(), str(inst_str))
                        device_lookup[key] = merged
                        entity_id_lookup[eid] = merged

                        sd = merged.get('status_dgn')
                        if sd:
                            status_lookup[(sd.upper(), str(inst_str))] = merged

                        if merged.get('device_type') == 'light':
                            light_entity_ids.add(eid)
                            light_command_info[eid] = {
                                'dgn':      int(dgn_hex, 16),
                                'instance': int(inst_str),
                                'interface': merged.get('interface')
                            }
        logging.info(f"Loaded {len(device_lookup)} device_lookup entries.")
        logging.info(f"Loaded {len(status_lookup)} status_lookup entries.")
        status_keys_to_log = list(status_lookup.keys())
        if len(status_keys_to_log) > 50:
            logging.info(f"status_lookup keys (first 50): {status_keys_to_log[:50]}")
        else:
            logging.info(f"status_lookup keys: {status_keys_to_log}")
    else:
        logging.error(f"Device mapping file NOT FOUND: {device_mapping_path}")

    return (
        decoder_map,
        device_mapping,
        device_lookup,
        status_lookup,
        light_entity_ids,
        entity_id_lookup,
        light_command_info,
    )
