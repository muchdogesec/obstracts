from stix2 import IPv4Address
from stix2extensions import BankAccount
from datetime import datetime
from typing import List, Dict, Tuple, Callable
import logging

from dogesec_commons.objects.helpers import TLP_VISIBLE_TO_ALL
from stix2arango.stix2arango.stix2arango import post_upload_hook
from obstracts.server.models import ObjectValue


def external_id(obj):
    return [
        ref.get("external_id")
        for ref in obj.get("external_references", [])
        if ref.get("external_id")
    ][:1]


def hashes(obj):
    return obj.get("hashes", {})


def get_file_values(obj):
    values = {}
    if "name" in obj:
        values["name"] = obj["name"]
    if "hashes" in obj:
        values.update({k.lower().replace("-", ""): v for k, v in obj["hashes"].items()})
    return values


def get_values(obj: dict, value_keys: list[str] | dict[str, str] | Callable):
    if isinstance(value_keys, list):
        value_keys = {key: key for key in value_keys}
    if isinstance(value_keys, dict):
        return {key: str(obj[key]) for key in value_keys.keys() if key in obj}
    elif callable(value_keys):
        return value_keys(obj)
    else:
        raise ValueError("value_keys must be a list, a dictionary, or a callable")


sco_value_map = {
    # Cyber Observable Objects (SCOs)
    "artifact": dict(values=["url", "mime_type"]),
    "autonomous-system": dict(values=["number", "name"]),
    "directory": dict(values=["path"]),
    "domain-name": dict(values=["value"]),
    "email-addr": dict(values=["value"]),
    "email-message": dict(values=["subject", "body", "message_id"]),
    "file": dict(values=get_file_values),
    "ipv4-addr": dict(values=["value"]),
    "ipv6-addr": dict(values=["value"]),
    "mac-addr": dict(values=["value"]),
    "mutex": dict(values=["name"]),
    "network-traffic": dict(values=["protocols"]),
    "process": dict(values=["command_line", "cwd"]),
    "software": dict(values=["name", "cpe", "vendor", "version"]),
    "url": dict(values=["value"]),
    "user-account": dict(values=["user_id", "account_login", "account_type"]),
    "windows-registry-key": dict(values=["key"]),
    "x509-certificate": dict(values=["subject", "issuer", "serial_number"]),
}

# mitre ATT&CK TTP types can be identified by their x_mitre_domains property or specific external references
MITRE_VALUE_MAP = {
    "x-mitre-analytic": dict(values=["name"]),
    "x-mitre-asset": dict(values=["name"]),
    "x-mitre-collection": dict(values=["name"]),
    "x-mitre-data-component": dict(values=["name"]),
    "x-mitre-data-source": dict(values=["name"]),
    "x-mitre-detection-strategy": dict(values=["name"]),
    "x-mitre-matrix": dict(values=["name"]),
    "x-mitre-tactic": dict(values=["name"]),
}

sdo_value_map = {
    # Domain Objects (SDOs)
    "attack-pattern": dict(values=["name", "aliases"]),
    "campaign": dict(values=["name", "aliases"]),
    "course-of-action": dict(values=["name"]),
    "grouping": dict(values=["name", "context"]),
    "identity": dict(values=["name"]),
    "incident": dict(values=["name"]),
    "indicator": dict(values=["name", "pattern"]),
    "infrastructure": dict(values=["name"]),
    "intrusion-set": dict(values=["name", "aliases"]),
    "location": dict(values=["name", "country", "region"]),
    "malware": dict(values=["name", "x_mitre_aliases"]),
    "malware-analysis": dict(values=["product", "version"]),
    "note": dict(values=["abstract", "content"]),
    "observed-data": dict(values=["objects"]),
    "opinion": dict(values=["explanation", "opinion"]),
    "report": dict(values=["name"]),
    "threat-actor": dict(values=["name"]),
    "tool": dict(values=["name", "tool_version", "x_mitre_aliases"]),
    "vulnerability": dict(values=["name"]),
    "weakness": dict(values=["name"]),
    **MITRE_VALUE_MAP,
}
sro_value_map = {
    # Relationship Objects (SROs)
    "relationship": dict(values=["relationship_type"]),
    "sighting": dict(values=["summary"]),
}
type_value_map = {
    **sco_value_map,
    **sdo_value_map,
    **sro_value_map,
}


def get_ttp_type(obj: dict) -> str | None:
    """
    Determine the TTP type of a STIX object based on its properties.

    Returns:
        - "cve" for vulnerability objects
        - "cwe" for weakness objects
        - "location" for location objects
        - "enterprise-attack", "mobile-attack", "ics-attack" based on x_mitre_domains
        - "capec", "atlas", "disarm", "sector" based on external_references source_name
        - None if not a TTP object
    """
    obj_type = obj["type"]
    ttp_type = None
    extra = {}

    # Check for CVE (vulnerability)
    match obj_type:
        case "vulnerability":
            ttp_type = "cve"
        case "weakness":
            ttp_type = "cwe"
        case "location":
            ttp_type = "location"
    # Check for MITRE ATT&CK domains
    x_mitre_domains = obj.get("x_mitre_domains", [])
    if x_mitre_domains:
        domain = x_mitre_domains[0]
        if domain in ["enterprise-attack", "mobile-attack", "ics-attack"]:
            ttp_type = domain

    # Check external references for other TTP types
    external_refs = obj.get("external_references", [])
    if external_refs:
        source_name = external_refs[0].get("source_name", "")

        ttp_source_name_mapping = {
            "capec": "capec",
            "mitre-atlas": "atlas",
            "DISARM": "disarm",
            "sector2stix": "sector",
        }
        if source_name in ttp_source_name_mapping:
            ttp_type = ttp_source_name_mapping[source_name]
    if ttp_type and (ttp_ids := external_id(obj)):
        extra["ttp_id"] = ttp_ids[0]
    return ttp_type, extra


def get_visibility(obj: dict) -> str:
    """
    Determine the visibility of a STIX object based on its properties.

    Returns:
        - "public" if the object is marked as public
        - "private" if the object is marked as private
        - "unknown" if visibility cannot be determined
    """
    if not obj.get("created_by_ref") or set(obj.get("object_marking_refs", [])).intersection(
        TLP_VISIBLE_TO_ALL
    ):
        return "public"
    return "private"


def extract_object_metadata(obj: dict) -> dict:
    """
    Extract key metadata from a STIX object.

    Args:
        obj: A STIX object dictionary

    Returns:
        A dictionary containing:
        - id: The STIX object ID
        - type: The STIX object type
        - ttp_type: The TTP type if applicable (None otherwise)
        - values: The extracted values based on the object type
    """
    obj_id = obj["id"]
    obj_type = obj["type"]
    ttp_type, ttp_extra = get_ttp_type(obj)

    # Get the value configuration for this object type
    type_config = type_value_map.get(obj_type, {})
    value_keys = type_config.get("values", [])

    # Extract values using get_values function
    values = get_values(obj, value_keys) or {}

    values.update(ttp_extra)
    return {
        "stix_id": obj_id,
        "type": obj_type,
        "ttp_type": ttp_type,
        "values": values,
        "modified": obj.get("modified"),
        "created": obj.get("created"),
    }


@post_upload_hook(fail_on_error=True)
def process_uploaded_objects_hook(instance, collection_name, objects, **kwargs):
    """
    Post-upload hook that processes uploaded STIX objects into the ObjectValue table.

    This hook is called after objects are uploaded to ArangoDB and extracts metadata
    from each object to store in the ObjectValue model for efficient querying.

    Args:
        instance: The Stix2Arango instance
        collection_name: The name of the collection uploaded to
        objects: List of objects that were uploaded
        **kwargs: Additional keyword arguments including inserted_ids, existing_objects
    """

    logging.info(f"Processing {len(objects)} objects for ObjectValue extraction")

    # Build list of ObjectValue instances to create
    object_values_to_create = []

    for obj in objects:
        post_uuid = obj.get("_stixify_report_id", "").replace("report--", "")
        if not post_uuid:
            logging.warning(f"Object {obj.get('id')} does not have a valid _stixify_report_id, skipping")
            continue

        metadata = extract_object_metadata(obj)
        object_values_to_create.append(
            ObjectValue(
                file_id=post_uuid,
                **metadata
            )
        )

    # Bulk create with ignore_conflicts to handle duplicates
    if object_values_to_create:
        created_count = len(
            ObjectValue.objects.bulk_create(
                object_values_to_create, ignore_conflicts=True
            )
        )
        logging.info(
            f"Created {created_count} ObjectValue records for {len(object_values_to_create)} objects"
        )
    else:
        logging.info("No ObjectValue records to create")
