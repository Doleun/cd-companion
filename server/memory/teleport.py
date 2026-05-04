import struct
import logging

log = logging.getLogger('cd_server')


class TeleportMixin:
    """Operacoes de teleport e invulnerabilidade.

    Acessa self.teleport_enabled, self.inv, self.tp, self.hook_e,
    self.xyz_addr, self.pm — todos definidos em TeleportEngine.__init__.
    """

    def set_invuln(self, on: bool):
        if not self.teleport_enabled:
            return
        if self.inv:
            try:
                self.pm.write_bytes(self.inv, b'\x01' if on else b'\x00', 1)
            except Exception:
                pass

    def teleport_to_abs(self, abs_x, abs_y, abs_z):
        if not self.teleport_enabled:
            return False, "Teleport is disabled in settings"
        if self.tp and self.hook_e and self.xyz_addr[0]:
            try:
                data = struct.pack('<ffffI', abs_x, abs_y, abs_z, 0.0, 1)
                self.pm.write_bytes(self.tp, data, len(data))
                log.info("Teleport queued: (%.1f, %.1f, %.1f)", abs_x, abs_y, abs_z)
                return True, ""
            except Exception as e:
                return False, str(e)
        return False, "Physics delta hook not installed — hook_e AOB not found for this patch"
