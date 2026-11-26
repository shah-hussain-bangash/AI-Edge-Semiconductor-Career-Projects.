"""Read-only troubleshooting snapshot. Never opens USB or certifies equipment."""
from importlib.metadata import PackageNotFoundError, version
import platform
import shutil
import sys

from home_core import BOUNDARY, utc_now


def report(controller):
    state = controller.status()
    try:
        serial_version = version('pyserial')
    except PackageNotFoundError:
        serial_version = None
    try:
        free_bytes = shutil.disk_usage(controller.directory).free
    except OSError:
        free_bytes = None
    sample = state.get('last_sample') if state['fresh'] else None
    sensor_stream = bool(sample and sample['source'] == 'serial-unverified' and state['settings']['mode'] == 'sensors')
    groups = {}
    for name, channels in (
        ('ADXL345', ('acceleration_x_mps2', 'acceleration_y_mps2', 'acceleration_z_mps2')),
        ('DS18B20', ('temperature_c',)),
        ('INA219', ('bus_voltage_v', 'current_a')),
    ):
        groups[name] = 'declared-valid-unverified' if sensor_stream and all(state['live_values'][key] is not None for key in channels) else 'unavailable'
    return dict(
        format='edgeops-home-diagnostics-v1', generated_at=utc_now(),
        host=dict(system=platform.system(), os_release=platform.release(), python=platform.python_version(),
                  python_supported=sys.version_info[:2] in {(3, 12), (3, 13), (3, 14)},
                  pyserial=serial_version, dependency_matches=serial_version == '3.5',
                  free_bytes=free_bytes, recording_space_advisory='unknown' if free_bytes is None else 'low' if free_bytes < 256 * 1024 * 1024 else 'available'),
        reader=dict(mode=state['settings']['mode'], port=state['settings']['port'], state=state['state'],
                    fresh=state['fresh'], accepted=state['accepted'], rejected=state['rejected'],
                    source=sample['source'] if sample else None,
                    communication='fresh-parser-accepted-input' if sample and state['settings']['mode'] != 'demo' else 'not-demonstrated',
                    sensor_groups=groups),
        limits=dict(physical_acceptance='pending', online_portal='deferred', native_esp32_wifi=False,
                    motor_control=False, ai_inference=False,
                    note='Snapshot only. Firmware validity flags and host free space are not physical acceptance or a storage guarantee.'),
        **BOUNDARY,
    )
