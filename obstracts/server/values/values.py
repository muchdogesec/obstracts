from typing import Callable
import logging

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

KB_TYPES = {
    "Tactic": [dict(type='x-mitre-tactic')],
    "Analytic": [dict(type='x-mitre-analytic')],
    "Detection Strategy": [dict(type='x-mitre-detection-strategy')],
    "Technique": [dict(type='attack-pattern', x_mitre_is_subtechnique=False), dict(type='attack-pattern', x_mitre_is_subtechnique=None)],
    "Sub-technique": [dict(type='attack-pattern', x_mitre_is_subtechnique=True)],
    "Mitigation": [dict(type='course-of-action')],
    "Group": [dict(type='intrusion-set')],
    "Software": [dict(type='malware'), dict(type='tool')],
    "Campaign": [dict(type='campaign')],
    "Data Source": [dict(type='x-mitre-data-source')],
    "Data Component": [dict(type='x-mitre-data-component')],
    "Asset": [dict(type='x-mitre-asset')],
}

def get_kb_type(obj):
    for form, criteria_list in KB_TYPES.items():
        for criteria in criteria_list:
            if all(obj.get(k) == v for k, v in criteria.items()):
                return form
    return None

def get_file_values(obj):
    values = {}
    for k in ["name", "mime_type"]:
        if k in obj:
            values[k] = obj[k]
    if "hashes" in obj:
        values.update({k.lower().replace("-", ""): v for k, v in obj["hashes"].items()})
    return values

def get_location_values(obj):
    values = {}
    for key in ["name", "region"]:
        if key in obj:
            values[key] = obj[key]
    for ext_ref in obj.get("external_references", []):
        source_name = ext_ref.get("source_name", "")
        if source_name in ["type", "alpha-3"]:
            values[source_name] = ext_ref['external_id']
    return values

def get_cert_values(obj):
    values = {}
    for key in ["subject", "issuer", "serial_number", 'signature_algorithm', 'validity_not_before', 'validity_not_after']:
        if key in obj:
            values[key] = obj[key]
    if 'hashes' in obj:
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

s2e_sco_map = {
    "bank-account": dict(values=["iban", "bic", "currency"]),
    "cryptocurrency-wallet": dict(values=["value"]),
    "cryptocurrency-transaction": dict(values=["value", "symbol"]),
    "payment-card": dict(values=["value", "scheme", "currency"]),
    "phone-number": dict(values=["value", "country", "provider"]),
    "user-agent": dict(values=["value"]),
}
sco_value_map = {
    # Cyber Observable Objects (SCOs)
    "artifact": dict(values=["url", "mime_type"]),
    "autonomous-system": dict(values=["number", "name"]),
    "directory": dict(values=["path"]),
    "domain-name": dict(values=["value"]),
    "email-addr": dict(values=["value", "display_name"]),
    "email-message": dict(values=["subject", "body", "message_id"]),
    "file": dict(values=get_file_values),
    "ipv4-addr": dict(values=["value"]),
    "ipv6-addr": dict(values=["value"]),
    "mac-addr": dict(values=["value"]),
    "mutex": dict(values=["name"]),
    "network-traffic": dict(values=["protocols", "src_port", "dst_port", "src_packets", "dst_packets", "src_byte_count", "dst_byte_count"]),
    "process": dict(values=["command_line", "cwd"]),
    "software": dict(values=["name", "cpe", "vendor", "version", "swid"]),
    "url": dict(values=["value"]),
    "user-account": dict(values=["display_name", "account_login", "account_type", "user_id"]),
    "windows-registry-key": dict(values=["key", "values"]),
    "x509-certificate": dict(values=get_cert_values),
    **s2e_sco_map,
}
s2e_sdo_map = {
    "weakness": dict(values=["name"]),
    "exploit": dict(values=["name", "proof_of_concept"]),
    "procedure": dict(values=["name", "context", "objective"]),
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
    "location": dict(values=get_location_values),
    "malware": dict(values=["name", "x_mitre_aliases"]),
    "malware-analysis": dict(values=["product", "version"]),
    "note": dict(values=["abstract", "content"]),
    "observed-data": dict(values=["objects"]),
    "opinion": dict(values=["explanation", "opinion"]),
    "report": dict(values=["name"]),
    "threat-actor": dict(values=["name"]),
    "tool": dict(values=["name", "tool_version", "x_mitre_aliases"]),
    "vulnerability": dict(values=["name"]),
    **s2e_sdo_map,
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


def guess_kb_data(obj: dict) -> str | None:
    """
    Determine the KnowledgeBase type of a STIX object based on its properties.

    Returns:
        - "cve" for vulnerability objects
        - "cwe" for weakness objects
        - "location" for location objects
        - "enterprise-attack", "mobile-attack", "ics-attack" based on x_mitre_domains
        - "capec", "atlas", "disarm", "sector" based on external_references source_name
        - None if not a KnowledgeBase object
    """
    obj_type = obj["type"]
    kb_name = None
    extra = {}

    # Check for CVE (vulnerability)
    match obj_type:
        case "vulnerability":
            kb_name = "cve"
        case "weakness":
            kb_name = "cwe"
        case "location":
            kb_name = "location"
    # Check for MITRE ATT&CK domains
    x_mitre_domains = obj.get("x_mitre_domains", [])
    if x_mitre_domains:
        domain = x_mitre_domains[0]
        if domain in ["enterprise-attack", "mobile-attack", "ics-attack"]:
            kb_name = domain

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
            kb_name = ttp_source_name_mapping[source_name]
    if kb_name and (kb_ids := external_id(obj)):
        extra["kb_id"] = kb_ids[0]
    if kb_name and (kb_type := get_kb_type(obj)):
        extra["kb_type"] = kb_type    
    return kb_name, extra


def extract_object_metadata(obj: dict) -> dict:
    """
    Extract key metadata from a STIX object.

    Args:
        obj: A STIX object dictionary

    Returns:
        A dictionary containing:
        - id: The STIX object ID
        - type: The STIX object type
        - knowledgebase: The source KnowledgeBase type if applicable (None otherwise)
        - values: The extracted values based on the object type
    """
    obj_id = obj["id"]
    obj_type = obj["type"]
    kb_name, kb_extra = guess_kb_data(obj)

    # Get the value configuration for this object type
    type_config = type_value_map.get(obj_type, {})
    value_keys = type_config.get("values", [])

    # Extract values using get_values function
    values = get_values(obj, value_keys) or {}

    values.update(kb_extra)
    return {
        "stix_id": obj_id,
        "type": obj_type,
        "knowledgebase": kb_name,
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
        if not metadata["values"]:
            continue
        object_values_to_create.append(
            ObjectValue(
                file_id=post_uuid,
                **metadata,
                is_dupe=False,  # will be updated later in a deduplication step
            )
        )

    # Bulk create with ignore_conflicts to handle duplicates
    if object_values_to_create:
        created = ObjectValue.objects.bulk_create(
            object_values_to_create, ignore_conflicts=True
        )
        new_dupes = ObjectValue.objects.filter(
            stix_id__in=[obj.stix_id for obj in created],
            is_dupe=False,
        ).exclude(
            file_id__in=[obj.file_id for obj in created],
        )
        new_dupes.update(is_dupe=True)
        logging.info(
            f"Created {len(created)} ObjectValue records for {len(object_values_to_create)} objects"
        )
        logging.info(f"Marked {new_dupes.count()} ObjectValue records as duplicates")
    else:
        logging.info("No ObjectValue records to create")
