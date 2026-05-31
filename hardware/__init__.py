"""
hardware/ — safe bladeRF hardware abstraction layer.

Public surface:
    from hardware.bladerf_device import BladeRFConfig, BladeRFDevice
    from hardware.safety import SafetyError, HardwareConfirmation

dry_run=True is the default and only supported mode in this initial phase.
Real hardware access requires dry_run=False AND the exact confirmation string
'CONFIRM HARDWARE RUN' passed to BladeRFDevice.__init__().
"""
