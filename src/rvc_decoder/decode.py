"""
rvc_decoder.decode

Core decoding logic for RV-C CAN frames, including loading of spec and device mapping data.
"""

import json
import logging
import os
import sys
from importlib import resources

import yaml

logger = logging.getLogger(__name__)  # Added named logger


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
    raw_int = int.from_bytes(data_bytes, byteorder="little")
    mask = (1 << length) - 1
    return (raw_int >> start_bit) & mask


def decode_payload(entry: dict, data_bytes: bytes) -> tuple[dict[str, str], dict[str, int]]:
    """
    Decode all 'signals' in a spec entry:
      - raw_values: the integer bitfields
      - decoded: human‑readable strings (with scale/offset/enum logic)

    Returns:
      tuple(decoded: dict[str,str], raw_values: dict[str,int])
    """
    decoded = {}
    raw_values = {}

    for sig in entry.get("signals", []):
        raw = get_bits(data_bytes, sig["start_bit"], sig["length"])
        raw_values[sig["name"]] = raw

        # apply scale/offset
        val = raw * sig.get("scale", 1) + sig.get("offset", 0)
        unit = sig.get("unit", "")

        # enum lookup if present
        if "enum" in sig:
            formatted = sig["enum"].get(str(raw))
            if formatted is None:
                formatted = f"UNKNOWN ({raw})"
        elif sig.get("scale", 1) != 1 or sig.get("offset", 0) != 0 or isinstance(val, float):
            formatted = f"{val:.2f}{unit}"
        else:
            formatted = f"{int(val)}{unit}"

        decoded[sig["name"]] = formatted

    return decoded, raw_values


def load_config_data(
    rvc_spec_path_override: str | None = None,  # Renamed parameter
    device_mapping_path_override: str | None = None,  # Renamed parameter
) -> tuple[
    dict[int, dict],
    dict,
    dict[tuple[str, str], dict],
    dict[tuple[str, str], dict],
    set[str],
    dict[str, dict],
    dict[str, dict],
    dict[str, str],  # Added for pgn_hex_to_name_map
]:
    """
    Load and parse:
      1. RVC spec JSON → decoder_map (PGN→spec entry, adds 'dgn_hex')
      2. device_mapping YAML →
         • device_lookup ((dgn_hex,inst)→config)
         • status_lookup ((status_dgn,inst)→config)
         • entity_id_lookup (id→config)
         • light_entity_ids (set of IDs)
         • light_command_info (id→{dgn,instance,interface})

    Uses override paths if provided and valid, otherwise falls back to bundled files.

    Args:
        rvc_spec_path_override (str | None): Optional path to an RVC specification JSON file.
                                             If None or invalid, uses the bundled default.
        device_mapping_path_override (str | None): Optional path to a device mapping YAML file.
                                                   If None or invalid, uses the bundled default.

    Returns:
      decoder_map: dict[int,dict],
      device_mapping: dict,
      device_lookup: dict[tuple[str,str],dict],
      status_lookup: dict[tuple[str,str],dict],
      light_entity_ids: set[str],
      entity_id_lookup: dict[str,dict],
      light_command_info: dict[str,dict],
      pgn_hex_to_name_map: dict[str, str]  # Added for pgn_hex_to_name_map
    """
    # --- MODIFICATION START: Path selection logic ---
    default_spec_path, default_mapping_path = _default_paths()

    # Determine final spec path
    rvc_spec_path = default_spec_path  # Default
    if rvc_spec_path_override:
        if os.path.exists(rvc_spec_path_override) and os.access(rvc_spec_path_override, os.R_OK):
            rvc_spec_path = rvc_spec_path_override
            logger.info(
                f"Using overridden RVC Spec Path: {rvc_spec_path}"
            )  # Changed to logger.info
        else:
            logger.warning(  # Changed to logger.warning
                f"Provided override path for RVC spec is missing or unreadable: "
                f"{rvc_spec_path_override}. "
                f"Attempting to use bundled default: {default_spec_path}"
            )
            logger.info(f"Using default RVC Spec Path: {rvc_spec_path}")  # Changed to logger.info
    else:
        logger.info(f"Using default RVC Spec Path: {rvc_spec_path}")  # Changed to logger.info

    # Determine final mapping path
    device_mapping_path = default_mapping_path  # Default
    if device_mapping_path_override:
        if os.path.exists(device_mapping_path_override) and os.access(
            device_mapping_path_override, os.R_OK
        ):
            device_mapping_path = device_mapping_path_override
            logger.info(
                f"Using overridden Device Mapping Path: {device_mapping_path}"
            )  # Changed to logger.info
        else:
            logger.warning(  # Changed to logger.warning
                f"Provided override path for device mapping is missing or unreadable: "
                f"{device_mapping_path_override}. "
                f"Attempting to use bundled default: {default_mapping_path}"
            )
            logger.info(
                f"Using default Device Mapping Path: {device_mapping_path}"
            )  # Changed to logger.info
    else:
        logger.info(
            f"Using default Device Mapping Path: {device_mapping_path}"
        )  # Changed to logger.info
    # --- MODIFICATION END ---

    # 1) Load spec
    if not os.path.exists(rvc_spec_path) or not os.access(rvc_spec_path, os.R_OK):
        logger.error(f"Cannot read RVC spec: {rvc_spec_path}")  # Changed to logger.error
        sys.exit(1)
    with open(rvc_spec_path) as f:
        spec_content = json.load(f)

    specs = spec_content.get("messages", [])
    decoder_map: dict[int, dict] = {}
    for entry in specs:
        sid = entry.get("id")
        if sid is None:
            logger.warning(f"Skipping spec without 'id': {entry}")  # Changed to logger.warning
            continue
        try:
            dec_id = sid if isinstance(sid, int) else int(sid, 16)
        except ValueError:
            logger.warning(f"Invalid 'id' in spec: {sid}")  # Changed to logger.warning
            continue
        entry["dgn_hex"] = f"{(dec_id >> 8) & 0x3FFFF:X}"
        decoder_map[dec_id] = entry
    logger.info(f"Loaded {len(decoder_map)} spec entries.")  # Changed to logger.info

    # Create a map from PGN hex string to PGN name for unmapped entry enrichment
    pgn_hex_to_name_map: dict[str, str] = {}
    if decoder_map:  # Check if decoder_map was successfully populated
        for spec_entry in decoder_map.values():
            pgn_val_int = spec_entry.get("pgn")
            pgn_name_str = spec_entry.get("name")
            if pgn_val_int is not None and pgn_name_str:
                current_pgn_hex_key = f"{pgn_val_int:X}".upper()
                if current_pgn_hex_key not in pgn_hex_to_name_map:
                    pgn_hex_to_name_map[current_pgn_hex_key] = pgn_name_str

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
        templates = raw_map.get("templates", {})
        device_mapping = raw_map

        for dgn_hex, instances in raw_map.items():
            if dgn_hex == "templates" or not isinstance(instances, dict):
                continue
            for inst_str, configs in instances.items():
                if not isinstance(configs, list):
                    continue
                for cfg in configs:
                    if not isinstance(cfg, dict):
                        continue
                    tmpl = cfg.pop("<<", None)
                    merged = {**templates.get(tmpl, {}), **cfg} if tmpl else cfg

                    eid = merged.get("entity_id")
                    fname = merged.get("friendly_name")
                    if eid and fname:
                        # Debug: Log merged config for each entity
                        logger.debug(f"entity_id_lookup[{eid}] = {json.dumps(merged, indent=2)}")
                        key = (dgn_hex.upper(), str(inst_str))
                        device_lookup[key] = merged
                        entity_id_lookup[eid] = merged

                        sd = merged.get("status_dgn")
                        if sd:
                            status_lookup[(sd.upper(), str(inst_str))] = merged

                        if merged.get("device_type") == "light":
                            light_entity_ids.add(eid)
                            light_command_info[eid] = {
                                "dgn": int(dgn_hex, 16),
                                "instance": int(inst_str),
                                "interface": merged.get("interface"),
                            }
        logger.info(f"Loaded {len(device_lookup)} device_lookup entries.")  # Changed to logger.info
        logger.info(f"Loaded {len(status_lookup)} status_lookup entries.")  # Changed to logger.info
        status_keys_to_log = list(status_lookup.keys())
        if len(status_keys_to_log) > 50:
            logger.info(
                f"status_lookup keys (first 50): {status_keys_to_log[:50]}"
            )  # Changed to logger.info
        else:
            logger.info(f"status_lookup keys: {status_keys_to_log}")  # Changed to logger.info
    else:
        logger.error(
            f"Device mapping file NOT FOUND: {device_mapping_path}"
        )  # Changed to logger.error

    return (
        decoder_map,
        device_mapping,
        device_lookup,
        status_lookup,
        light_entity_ids,
        entity_id_lookup,
        light_command_info,
        pgn_hex_to_name_map,  # Return the new map
    )
