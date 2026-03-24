"""Fusion stub - passes contacts through unchanged.

Future: merge radar CAN data with camera detections before tracking.
Radar contacts will arrive via passive CAN RX on openTPT can_b1_1.
"""


def fuse(contacts):
    """Merge sensor sources. Currently a passthrough.

    Args:
        contacts: list of contact dicts from range estimation

    Returns:
        list of contact dicts (unchanged for now)
    """
    return contacts
