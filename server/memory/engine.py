"""
TeleportEngine — leitura de memória, hooks e teleport.
Extraído de position_server.py para melhor organização.
"""

import ctypes
import ctypes.wintypes
import json
import logging
import os
import struct
import sys

import pymem
import pymem.process

from shared.coord_math import (
    player_heading as _calc_player_heading,
    camera_heading as _calc_camera_heading,
)

log = logging.getLogger('cd_server')

# Quando rodando como exe compilado, oculta endereços de memória dos logs.
# Em desenvolvimento (script), exibe normalmente para debug.
_REDACT = getattr(sys, 'frozen', False)

# ── Constantes de memória ────────────────────────────────────────────

PROCESS_NAME = "CrimsonDesert.exe"
SAVE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CD_Teleport")
HOOK_OFFSETS_FILE = os.path.join(SAVE_DIR, "cd_hook_offsets.json")
HEIGHT_BOOST = 10.0

k32 = ctypes.windll.kernel32
k32.VirtualAllocEx.restype = ctypes.c_ulonglong
k32.VirtualAllocEx.argtypes = [
    ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_size_t,
    ctypes.c_ulong, ctypes.c_ulong,
]
k32.VirtualFreeEx.argtypes = [
    ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_size_t, ctypes.c_ulong,
]

MEM_COMMIT  = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40


def _load_hook_offsets():
    try:
        with open(HOOK_OFFSETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_hook_offsets(data):
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(HOOK_OFFSETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── TeleportEngine (position reading only) ───────────────────────────

class TeleportEngine:
    AOB_ENTITY = b'\x48\x83\xEC\x50\x48\x8B\xF9\x48\x8B\x91\x30\x11\x00\x00'
    AOB_POS    = b'\x0F\x11\x99\x90\x00\x00\x00'
    AOB_HEALTH = b'\x48\x8B\x46\x08\x48\x89\xF1'
    AOB_MAP    = b'\xC5\xFB\x10\x07\xC5\xFB\x11\x02\x8B\x47\x08\x89\x42\x08'
    # VEX encoding (2026-04 patch):
    #   C5 FB 10 07       vmovsd xmm0, [rdi]       ← carrega X/Y do marcador
    #   C5 FB 11 02       vmovsd [rdx], xmm0       ← escreve X/Y  ← hook em AOB+4
    #   8B 47 08          mov eax, [rdi+08]         ← carrega Z
    #   89 42 08          mov [rdx+08], eax         ← escreve Z
    AOB_MAP_HOOK_OFFSET = 4  # hook no vmovsd store, não no load
    AOB_WORLD  = b'\x0F\x5C\x1D'
    # vmovsd [rip+?],xmm0 ; mov eax,[rsp+28] ; mov [rip+?],eax
    # Localiza os 3 endereços estáticos de XYZ do player
    AOB_XYZ_PREFIX = b'\xC5\xFB\x11\x05'          # vmovsd [rip+disp32], xmm0
    AOB_XYZ_MID    = b'\x8B\x44\x24\x28\x89\x05'  # mov eax,[rsp+28] ; mov [rip+disp32],eax
    # Physics delta hook (OpenFlight technique):
    #   movaps xmm0, xmm6       ; 0F 28 C6   ← hook point (8 bytes total com próxima instrução)
    #   subss  xmm9, xmm8       ; F3 45 0F 5C C8
    # confirmado por +8: addps xmm0,[r13] + movups [r13],xmm0
    AOB_PHYS_DELTA_CONFIRM = b'\x41\x0F\x58\x45\x00\x41\x0F\x11\x45\x00'  # em hook_e+8
    AOB_PHYS_DELTA_HOOK    = b'\x0F\x28\xC6\xF3\x45\x0F\x5C\xC8'          # hook_e (8 bytes)
    # vmovss [r15+0x4A4], xmm2  (heading da camera em graus assinados -180..180)
    # instrução seguinte: vcomiss xmm9, xmm14
    AOB_CAM  = b'\xC4\xC1\x7A\x11\x97\xA4\x04\x00\x00\xC5\x78\x2F\xCE'
    HOOK_PATCH_SIZE = 7
    ORIG_HOOK_A   = b'\x48\x8B\x91\x30\x11\x00\x00'  # mov rdx,[rcx+0x1130]
    ORIG_HOOK_B   = AOB_POS
    ORIG_HOOK_C   = AOB_HEALTH
    ORIG_HOOK_D   = b'\xC5\xFB\x11\x02\x8B\x47\x08'  # vmovsd [rdx],xmm0 ; mov eax,[rdi+8]
    ORIG_HOOK_E   = b'\x0F\x28\xC6\xF3\x45\x0F\x5C'  # primeiros 7 bytes do hook_e
    ORIG_HOOK_CAM = b'\xC4\xC1\x7A\x11\x97\xA4\x04\x00\x00'  # vmovss [r15+0x4A4],xmm2  (9 bytes)

    OFF_TD      = 0x000
    OFF_INV     = 0x040
    OFF_MD      = 0x050
    OFF_TP      = 0x060  # teleport target: {tx,ty,tz,0.0f} + flag uint32 = 20 bytes
    OFF_CAM_YAW = 0x090  # float: camera heading em graus assinados (salvo por cave_cam)
    OFF_CA   = 0x100
    OFF_CB   = 0x180
    OFF_CC   = 0x200
    OFF_CD   = 0x280
    OFF_CE   = 0x300  # cave E: physics delta hook para teleport
    OFF_CF   = 0x380  # cave F: camera yaw hook
    BLOCK_SZ = 0x1000

    def __init__(self, teleport_enabled: bool = True):
        self.teleport_enabled = teleport_enabled
        self.pm = None
        self.module = None
        self.attached = False
        self.hooks_installed = False
        self.block = 0
        self.td = 0
        self.inv = 0
        self.md = 0
        self.tp = 0
        self.hook_a = 0
        self.hook_b = 0
        self.hook_c = 0
        self.hook_d = 0
        self.hook_e = 0
        self.hook_cam = 0
        self.orig_bytes = {}
        self.world_offset_addr = 0
        self.xyz_addr = (0, 0, 0)   # (x_addr, y_addr, z_addr) — estáticos globais
        self._trampolines = []
        self._far_mode = False

    def attach(self):
        if self.pm or self.attached or self.orig_bytes or self.block:
            self.detach()
        self.pm = pymem.Pymem(PROCESS_NAME)
        self.module = pymem.process.module_from_name(
            self.pm.process_handle, PROCESS_NAME)
        self.attached = True

    @property
    def status(self):
        if not self.attached:
            return "disconnected"
        if not self.hooks_installed:
            return "scanning"
        return "attached"

    @property
    def teleport_available(self):
        """Retorna True se teleport está habilitado E o hook_e está instalado."""
        return self.teleport_enabled and bool(self.hook_e)

    def _reset_runtime_state(self):
        self.block = 0
        self.td = 0
        self.inv = 0
        self.md = 0
        self.tp = 0
        self.hook_a = 0
        self.hook_b = 0
        self.hook_c = 0
        self.hook_d = 0
        self.hook_e = 0
        self.hook_cam = 0
        self.world_offset_addr = 0
        self.xyz_addr = (0, 0, 0)
        self.orig_bytes.clear()
        self._trampolines.clear()
        self._far_mode = False
        self.hooks_installed = False

    def detach(self):
        try:
            if self.orig_bytes:
                self.uninstall_hooks()
        except Exception:
            pass
        handle = self.pm.process_handle if self.pm else None
        if self.block and handle:
            k32.VirtualFreeEx(handle, self.block, 0, MEM_RELEASE)
            self.block = 0
        for tramp in self._trampolines:
            if handle:
                try:
                    k32.VirtualFreeEx(handle, tramp, 0, MEM_RELEASE)
                except Exception:
                    pass
        self._trampolines.clear()
        self._far_mode = False
        if self.pm:
            try:
                self.pm.close_process()
            except Exception:
                pass
        self.pm = None
        self.module = None
        self.attached = False
        self._reset_runtime_state()

    def _read_module(self):
        base = self.module.lpBaseOfDll
        size = self.module.SizeOfImage
        data = bytearray(size)
        CHUNK = 0x10000
        for off in range(0, size, CHUNK):
            sz = min(CHUNK, size - off)
            try:
                data[off:off + sz] = self.pm.read_bytes(base + off, sz)
            except Exception:
                pass
        return bytes(data), base

    def _canonical_orig_bytes(self, hook_addr):
        if hook_addr == self.hook_a:
            return self.ORIG_HOOK_A
        if hook_addr == self.hook_b:
            return self.ORIG_HOOK_B
        if hook_addr == self.hook_c:
            return self.ORIG_HOOK_C
        if hook_addr == self.hook_d:
            return self.ORIG_HOOK_D
        if hook_addr == self.hook_e:
            return self.ORIG_HOOK_E
        if hook_addr == self.hook_cam:
            return self.ORIG_HOOK_CAM
        return b''

    def _remember_orig_bytes(self, hook_addr):
        current = self.pm.read_bytes(hook_addr, self.HOOK_PATCH_SIZE)
        if current[:1] == b'\xE9' and current[-2:] == b'\x90\x90':
            self.orig_bytes[hook_addr] = self._canonical_orig_bytes(hook_addr)
        else:
            self.orig_bytes[hook_addr] = current

    def _find_phys_delta_hook(self, data, base):
        """Localiza o ponto de hook no physics delta (movaps xmm0,xmm6 / subss xmm9,xmm8)
        confirmado por addps xmm0,[r13] + movups [r13],xmm0 nos 8 bytes seguintes.
        Retorna endereço absoluto ou 0."""
        confirm = self.AOB_PHYS_DELTA_CONFIRM
        hook    = self.AOB_PHYS_DELTA_HOOK
        pos = 0
        while pos < len(data) - 18:
            i = data.find(confirm, pos)
            if i == -1:
                break
            if i >= 8 and data[i - 8:i] == hook:
                return base + i - 8
            pos = i + 1
        return 0

    def _find_xyz_static(self, data, base):
        """Localiza endereços estáticos de XYZ via padrão vmovsd+mov.
        Retorna (x_addr, y_addr, z_addr) ou (0,0,0) se não encontrado."""
        prefix = self.AOB_XYZ_PREFIX
        mid    = self.AOB_XYZ_MID
        pos = 0
        while pos < len(data) - 20:
            i = data.find(prefix, pos)
            if i == -1:
                break
            if data[i + 8:i + 14] == mid:
                disp_xy = struct.unpack_from('<i', data, i + 4)[0]
                xy_addr = base + i + 8 + disp_xy
                disp_z  = struct.unpack_from('<i', data, i + 14)[0]
                z_addr  = base + i + 18 + disp_z
                return xy_addr, xy_addr + 4, z_addr
            pos = i + 1
        return 0, 0, 0

    def scan_and_hook(self):
        data, base = self._read_module()
        saved = _load_hook_offsets()

        # Busca endereços estáticos XYZ (não requer hook de entidade)
        self.xyz_addr = self._find_xyz_static(data, base)
        if any(self.xyz_addr):
            if _REDACT:
                log.info("Static XYZ addresses found")
            else:
                log.info("Static XYZ found: X=%#x Y=%#x Z=%#x", *self.xyz_addr)
        else:
            log.warning("Static XYZ AOB not found — position reading will use hook fallback")

        idx = data.find(self.AOB_ENTITY)
        if idx != -1:
            self.hook_a = base + idx + 7  # pula "sub rsp,50; mov rdi,rcx" (7 bytes)
        elif "hook_a_rva" in saved:
            self.hook_a = base + int(saved["hook_a_rva"])
        elif not any(self.xyz_addr):
            raise RuntimeError("Entity hook AOB not found and no static XYZ — update required")
        else:
            self.hook_a = 0
            log.warning("Entity hook AOB not found — teleport unavailable, position via static globals")

        idx = data.find(self.AOB_POS)
        if idx != -1:
            self.hook_b = base + idx
        elif "hook_b_rva" in saved:
            self.hook_b = base + int(saved["hook_b_rva"])
        else:
            self.hook_b = 0
            log.warning("Position hook AOB not found — skipping hook_b")

        idx = data.find(self.AOB_HEALTH)
        if not self.teleport_enabled:
            self.hook_c = 0
            log.info("Teleport disabled — skipping health/invuln hook (hook_c)")
        elif idx != -1:
            self.hook_c = base + idx
        elif "hook_c_rva" in saved:
            self.hook_c = base + int(saved["hook_c_rva"])
        else:
            self.hook_c = 0
            log.warning("Health hook AOB not found — invuln unavailable")

        idx = data.find(self.AOB_MAP)
        if idx != -1:
            self.hook_d = base + idx + self.AOB_MAP_HOOK_OFFSET
            log.info("Map dest hook found")
        elif "hook_d_rva" in saved:
            self.hook_d = base + int(saved["hook_d_rva"])
            log.info("Map dest hook loaded from cache")
        else:
            # Fallback: shutdown anterior não-limpo deixou o JMP instalado e não há cache.
            # Os primeiros AOB_MAP_HOOK_OFFSET bytes nunca são patchados, então buscamos
            # esses bytes seguidos de \xE9 (JMP) para localizar o hook stale.
            stale_prefix = self.AOB_MAP[:self.AOB_MAP_HOOK_OFFSET] + b'\xE9'
            idx2 = data.find(stale_prefix)
            if idx2 != -1:
                self.hook_d = base + idx2 + self.AOB_MAP_HOOK_OFFSET
                log.info("Map dest hook recovered (JMP still installed from previous session)")
            else:
                self.hook_d = 0
                log.warning("Map dest AOB not found — map marker unavailable")

        hook_e_addr = self._find_phys_delta_hook(data, base)
        if not self.teleport_enabled:
            self.hook_e = 0
            log.info("Teleport disabled — skipping physics delta hook (hook_e)")
        elif hook_e_addr:
            self.hook_e = hook_e_addr
            log.info("Physics delta hook found — teleport via delta injection enabled")
        elif "hook_e_rva" in saved:
            self.hook_e = base + int(saved["hook_e_rva"])
            log.info("Physics delta hook loaded from cache")
        else:
            self.hook_e = 0
            log.warning("Physics delta hook not found — teleport fallback to direct write")

        idx = data.find(self.AOB_CAM)
        if idx != -1:
            self.hook_cam = base + idx
            log.info("Camera heading hook found")
        elif "hook_cam_rva" in saved:
            rva = int(saved["hook_cam_rva"])
            # Valida que os bytes no endereço cacheado ainda batem com o padrão original,
            # OU que o nosso próprio JMP patch ainda está lá (shutdown não-limpo anterior).
            # Num shutdown abrupto, uninstall_hooks() não roda e o JMP permanece em memória.
            # Na reabertura, os bytes começam com \xE9 — isso é o nosso hook, o endereço é válido.
            # Se os bytes não forem nenhum dos dois casos, o jogo foi reiniciado com layout diferente:
            # limpa o cache e força AOB scan limpo no próximo attach.
            if 0 <= rva <= len(data) - len(self.ORIG_HOOK_CAM):
                chunk = data[rva:rva + len(self.ORIG_HOOK_CAM)]
                if chunk == self.ORIG_HOOK_CAM:
                    self.hook_cam = base + rva
                    log.info("Camera heading hook loaded from cache")
                elif chunk[:1] == b'\xE9':
                    self.hook_cam = base + rva
                    log.info("Camera heading hook recovered (JMP still installed from previous session)")
                else:
                    self.hook_cam = 0
                    saved.pop("hook_cam_rva", None)
                    _save_hook_offsets(saved)
                    log.warning("Cached camera hook stale, cache cleared, will re-scan on next attach")
            else:
                self.hook_cam = 0
                saved.pop("hook_cam_rva", None)
                _save_hook_offsets(saved)
                log.warning("Cached camera hook stale, cache cleared, will re-scan on next attach")
        else:
            self.hook_cam = 0
            log.warning("Camera heading AOB not found — camera_heading unavailable")

        suffix = b'\x0F\x11\x99\x90\x00\x00\x00'
        pos = 0
        while pos < len(data) - 14:
            i = data.find(self.AOB_WORLD, pos)
            if i == -1:
                break
            if data[i + 7:i + 14] == suffix:
                disp = struct.unpack_from('<i', data, i + 3)[0]
                self.world_offset_addr = base + i + 7 + disp
                break
            pos = i + 1
        if not self.world_offset_addr and "world_offset_rva" in saved:
            self.world_offset_addr = base + int(saved["world_offset_rva"])

        self._alloc_block()
        self._install_hooks()
        save_data = {k: v for k, v in {
            "hook_a_rva":       self.hook_a   - base if self.hook_a   else None,
            "hook_b_rva":       self.hook_b   - base if self.hook_b   else None,
            "hook_c_rva":       self.hook_c   - base if self.hook_c   else None,
            "hook_d_rva":       self.hook_d   - base if self.hook_d   else None,
            "hook_e_rva":       self.hook_e   - base if self.hook_e   else None,
            "hook_cam_rva":     self.hook_cam - base if self.hook_cam else None,
            "world_offset_rva": self.world_offset_addr - base if self.world_offset_addr else None,
        }.items() if v is not None}
        _save_hook_offsets(save_data)

    def _alloc_near(self, handle, near, size):
        for offset in range(0x10000, 0x7FFF0000, 0x10000):
            for addr in [near + offset, near - offset]:
                if addr <= 0:
                    continue
                result = k32.VirtualAllocEx(
                    handle, addr, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
                if result:
                    return result
        return 0

    def _alloc_block(self):
        handle = self.pm.process_handle
        for anchor in [self.hook_a, self.hook_b, self.hook_c, self.hook_d, self.hook_e, self.hook_cam]:
            if not anchor:
                continue
            result = self._alloc_near(handle, anchor, self.BLOCK_SZ)
            if result:
                self.block = result
                self.td  = result + self.OFF_TD
                self.inv = result + self.OFF_INV
                self.md  = result + self.OFF_MD
                self.tp  = result + self.OFF_TP
                self._far_mode = False
                return
        result = k32.VirtualAllocEx(
            handle, 0, self.BLOCK_SZ, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
        if not result:
            raise RuntimeError("Could not allocate memory for code caves.")
        self.block = result
        self.td  = result + self.OFF_TD
        self.inv = result + self.OFF_INV
        self.md  = result + self.OFF_MD
        self.tp  = result + self.OFF_TP
        self._far_mode = True

    def _rel32(self, from_addr, to_addr):
        rel = to_addr - (from_addr + 5)
        if not (-0x80000000 <= rel <= 0x7FFFFFFF):
            raise RuntimeError("Cave too far for rel32 jump — try restarting the game")
        return rel

    def _jmp_patch5(self, from_addr, to_addr):
        """Patch de 5 bytes (só E9 + rel32, sem NOPs) — para instruções de 5 bytes."""
        rel = to_addr - (from_addr + 5)
        if not (-0x80000000 <= rel <= 0x7FFFFFFF):
            raise RuntimeError("Cave too far for rel32 jump — try restarting the game")
        return b'\xE9' + struct.pack('<i', rel)

    def _jmp_patch9(self, from_addr, to_addr):
        return b'\xE9' + struct.pack('<i', self._rel32(from_addr, to_addr)) + b'\x90' * 4

    def _jmp_patch(self, from_addr, to_addr):
        return b'\xE9' + struct.pack('<i', self._rel32(from_addr, to_addr)) + b'\x90\x90'

    def _abs_jmp(self, target):
        return b'\xFF\x25\x00\x00\x00\x00' + struct.pack('<Q', target)

    def _build_cave_a(self):
        # Hook em "mov rdx,[rcx+0x1130]" — rcx = entity base
        td, ret = self.td, self.hook_a + 7
        c = bytearray()
        c += b'\x50'                               # push rax  (scratch)
        c += b'\x48\xB8' + struct.pack('<Q', td)   # mov rax, td
        c += b'\x48\x89\x48\x18'                   # mov [rax+0x18], rcx  (entity base)
        c += b'\x58'                               # pop rax
        c += b'\x48\x8B\x91\x30\x11\x00\x00'      # mov rdx,[rcx+0x1130]  (original)
        c += self._abs_jmp(ret)
        return bytes(c)

    def _build_cave_b(self):
        td, ret = self.td, self.hook_b + 7
        c = bytearray()
        c += b'\x50'
        c += b'\x48\xB8' + struct.pack('<Q', td)
        c += b'\x83\x78\x10\x00'
        c += b'\x7E\x15'
        c += b'\x48\x3B\x48\x18'
        c += b'\x75\x0F'
        c += b'\x58'
        c += self._abs_jmp(ret)
        c += b'\x58'
        c += b'\x0F\x11\x99\x90\x00\x00\x00'
        c += self._abs_jmp(ret)
        return bytes(c)

    def _build_cave_c(self):
        inv, ret = self.inv, self.hook_c + 7
        c = bytearray()
        c += b'\x53'
        c += b'\x48\xBB' + struct.pack('<Q', inv)
        c += b'\x80\x3B\x01'
        c += b'\x5B'
        c += b'\x75\x0F'
        c += b'\x80\x3E\x00'
        c += b'\x75\x0A'
        c += b'\x53'
        c += b'\x48\x8B\x5E\x18'
        c += b'\x48\x89\x5E\x08'
        c += b'\x5B'
        c += b'\x48\x8B\x46\x08'
        c += b'\x48\x89\xF1'
        c += self._abs_jmp(ret)
        return bytes(c)

    def _build_cave_d(self):
        """Map destination capture cave (VEX encoding, 2026-04 patch).
        Hook em vmovsd [rdx],xmm0 — captura X/Y/Z do marcador do mapa."""
        md, ret = self.md, self.hook_d + 7
        c = bytearray()
        # Instruções originais (7 bytes substituídos pelo JMP)
        c += b'\xC5\xFB\x11\x02'                       # vmovsd [rdx], xmm0  (VEX)
        c += b'\x8B\x47\x08'                            # mov eax, [rdi+08]
        # Salva no bloco md
        c += b'\x51'                                    # push rcx
        c += b'\x48\xB9' + struct.pack('<Q', md)        # mov rcx, mapDestData
        c += b'\xC5\xFB\x11\x01'                        # vmovsd [rcx], xmm0  (VEX)
        c += b'\x89\x41\x08'                            # mov [rcx+08], eax
        c += b'\xC7\x41\x0C\x01\x00\x00\x00'           # mov dword [rcx+0C], 1  (flag)
        c += b'\x59'                                    # pop rcx
        c += self._abs_jmp(ret)
        return bytes(c)

    def _build_cave_e(self):
        """Hook no physics delta — dois modos via flag em tp_block:

        flag=1  TELEPORT: xmm0 = target_static - current_static
                addps → [r13]_new = [r13] + delta = target_r13  ✓
                (corrige o offset entre espaço [r13] e static globals)

        flag=2  MOVE: xmm0 = delta directo do tp_block
                addps → [r13]_new = [r13] + delta  (deltas são invariantes à translação)
                Usado para movimento direcional contínuo.

        tp_block layout (em self.tp):
          +0  float x    ┐ target (flag=1) ou delta (flag=2)
          +4  float y    │
          +8  float z    │
          +12 float 0.0  ┘ padding W
          +16 uint32 flag   (1=teleport, 2=move, 0=nenhum — zerado pelo hook)
          +24 16 bytes      área save/restore xmm1 (flag=1 apenas)
        """
        tp  = self.tp
        xyz = self.xyz_addr[0]   # static global X (Y=+4, Z=+8, consecutivos)
        ret = self.hook_e + 8    # retorna para addps xmm0,[r13]

        c = bytearray()

        # Instruções originais (8 bytes sobrescritos pelo JMP)
        c += b'\x0F\x28\xC6'                          # movaps xmm0, xmm6
        c += b'\xF3\x45\x0F\x5C\xC8'                  # subss  xmm9, xmm8

        # Salvar RBX (physics entity) em tp+0x28 — usado para ler forward vector
        c += b'\x50'                                   # push rax
        c += b'\x48\xB8' + struct.pack('<Q', tp)        # mov rax, tp_addr
        c += b'\x48\x89\x58\x28'                       # mov [rax+0x28], rbx  (save physics entity)

        # Verificar flag != 0
        c += b'\x83\x78\x10\x00'                       # cmp dword [rax+16], 0
        je_done_pos = len(c)
        c += b'\x74\x00'                               # je .done (placeholder)

        # Verificar flag=2 (move mode — delta directo)
        c += b'\x83\x78\x10\x02'                       # cmp dword [rax+16], 2
        je_move_pos = len(c)
        c += b'\x74\x00'                               # je .move (placeholder)

        # ── TELEPORT (flag=1): xmm0 = target_static - current_static ──
        c += b'\x0F\x11\x48\x18'                       # movups [rax+24], xmm1  (save)
        c += b'\x0F\x10\x00'                           # movups xmm0, [rax]     target
        c += b'\x51'                                   # push rcx
        c += b'\x48\xB9' + struct.pack('<Q', xyz)       # mov rcx, xyz_addr
        c += b'\x0F\x10\x09'                           # movups xmm1, [rcx]     current static
        c += b'\x59'                                   # pop rcx
        c += b'\x0F\x5C\xC1'                           # subps  xmm0, xmm1
        c += b'\x0F\x10\x48\x18'                       # movups xmm1, [rax+24]  (restore)
        jmp_clear_pos = len(c)
        c += b'\xEB\x00'                               # jmp .clear (placeholder)

        # ── MOVE (flag=2): xmm0 = delta directo ────────────────────────
        c[je_move_pos + 1] = len(c) - (je_move_pos + 2)
        c += b'\x0F\x10\x00'                           # movups xmm0, [rax]

        # ── CLEAR FLAG ──────────────────────────────────────────────────
        c[jmp_clear_pos + 1] = len(c) - (jmp_clear_pos + 2)
        c += b'\xC7\x40\x10\x00\x00\x00\x00'           # mov dword [rax+16], 0

        # ── .done ───────────────────────────────────────────────────────
        c[je_done_pos + 1] = len(c) - (je_done_pos + 2)
        c += b'\x58'                                   # pop rax
        c += self._abs_jmp(ret)
        return bytes(c)

    def _build_cave_cam(self):
        """Hook em vmovss [r15+0x4A4],xmm2 (heading da câmera em graus assinados).
        Salva xmm2 em OFF_CAM_YAW e executa instrução original.
        Patch de 9 bytes — retorna para hook_cam+9 (próxima instrução intacta)."""
        cam_yaw = self.block + self.OFF_CAM_YAW
        ret = self.hook_cam + 9
        c = bytearray()
        c += b'\x50'                                   # push rax
        c += b'\x48\xB8' + struct.pack('<Q', cam_yaw)  # mov rax, cam_yaw_addr
        c += b'\xC5\xFA\x11\x10'                       # vmovss [rax], xmm2
        c += b'\x58'                                   # pop rax
        c += self.ORIG_HOOK_CAM                        # vmovss [r15+0x4A4], xmm2
        c += self._abs_jmp(ret)
        return bytes(c)

    def _install_hooks(self):
        handle = self.pm.process_handle
        init = bytearray(64)
        struct.pack_into('<f', init, 0x30, HEIGHT_BOOST)
        self.pm.write_bytes(self.td, bytes(init), len(init))
        self.pm.write_bytes(self.inv, b'\x00', 1)
        self.pm.write_bytes(self.md, bytes(16), 16)

        # Inicializar tp_block com zeros (flag=0, sem teleport pendente)
        self.pm.write_bytes(self.tp, bytes(20), 20)

        caves = [
            (self.OFF_CA, self.hook_a,   self._build_cave_a),
            (self.OFF_CB, self.hook_b,   self._build_cave_b),
            (self.OFF_CC, self.hook_c,   self._build_cave_c),
            (self.OFF_CD, self.hook_d,   self._build_cave_d),
            (self.OFF_CE, self.hook_e,   self._build_cave_e),
            (self.OFF_CF, self.hook_cam, self._build_cave_cam),
        ]
        for off, hook_addr, builder in caves:
            if hook_addr:
                code = builder()
                self.pm.write_bytes(self.block + off, code, len(code))

        # Hooks padrão — patch de 7 bytes
        hooks7 = [
            (self.hook_a, self.block + self.OFF_CA),
            (self.hook_b, self.block + self.OFF_CB),
            (self.hook_c, self.block + self.OFF_CC),
            (self.hook_d, self.block + self.OFF_CD),
            (self.hook_e, self.block + self.OFF_CE),
        ]

        if not self._far_mode:
            for hook_addr, cave_addr in hooks7:
                if not hook_addr:
                    continue
                self._remember_orig_bytes(hook_addr)
                patch = self._jmp_patch(hook_addr, cave_addr)
                self.pm.write_bytes(hook_addr, patch, 7)
                verify = self.pm.read_bytes(hook_addr, 7)
                if verify != patch:
                    log.warning("Hook write verification FAILED at 0x%X — written=%s read=%s",
                                hook_addr, patch.hex(), verify.hex())
                else:
                    log.debug("Hook write verified at 0x%X", hook_addr)
            # Camera hook — patch de 9 bytes (instrução vmovss [r15+0x4A4],xmm2)
            if self.hook_cam:
                orig = self.pm.read_bytes(self.hook_cam, 9)
                if orig[:1] == b'\xE9':
                    orig = self.ORIG_HOOK_CAM
                self.orig_bytes[self.hook_cam] = orig
                self.pm.write_bytes(self.hook_cam,
                    self._jmp_patch9(self.hook_cam, self.block + self.OFF_CF), 9)
        else:
            for hook_addr, cave_addr in hooks7:
                if not hook_addr:
                    continue
                tramp = self._alloc_near(handle, hook_addr, 64)
                if not tramp:
                    raise RuntimeError("Could not allocate trampoline. Close other hooking tools.")
                self._trampolines.append(tramp)
                self.pm.write_bytes(tramp, self._abs_jmp(cave_addr), 14)
                self._remember_orig_bytes(hook_addr)
                self.pm.write_bytes(hook_addr, self._jmp_patch(hook_addr, tramp), 7)
            # Camera hook far mode — 9-byte jmp via trampoline
            if self.hook_cam:
                tramp = self._alloc_near(handle, self.hook_cam, 64)
                if tramp:
                    self._trampolines.append(tramp)
                    self.pm.write_bytes(tramp, self._abs_jmp(self.block + self.OFF_CF), 14)
                    orig = self.pm.read_bytes(self.hook_cam, 9)
                    if orig[:1] == b'\xE9':
                        orig = self.ORIG_HOOK_CAM
                    self.orig_bytes[self.hook_cam] = orig
                    self.pm.write_bytes(self.hook_cam,
                        self._jmp_patch9(self.hook_cam, tramp), 9)
                else:
                    log.warning("Camera hook trampoline alloc failed — camera_heading unavailable")

        self.hooks_installed = True

    def uninstall_hooks(self):
        if not self.pm or not self.orig_bytes:
            return
        for addr, orig in self.orig_bytes.items():
            try:
                self.pm.write_bytes(addr, orig, len(orig))
            except Exception:
                pass
        self.orig_bytes.clear()
        self.hooks_installed = False

    def get_player_pos(self):
        # Preferir leitura direta dos globais estáticos (não requer hook)
        x_addr, y_addr, z_addr = self.xyz_addr
        if x_addr:
            try:
                x = self.pm.read_float(x_addr)
                y = self.pm.read_float(y_addr)
                z = self.pm.read_float(z_addr)
                if x == 0.0 and y == 0.0 and z == 0.0:
                    return None
                return x, y, z
            except Exception:
                pass
        # Fallback: bloco td instalado pelo hook_a
        if not self.td:
            return None
        try:
            raw = self.pm.read_bytes(self.td + 0x20, 12)
            x, y, z = struct.unpack('<fff', raw)
            if x == 0.0 and y == 0.0 and z == 0.0:
                return None
            return x, y, z
        except Exception:
            return None

    def get_world_offsets(self):
        if not self.world_offset_addr:
            return None
        try:
            raw = self.pm.read_bytes(self.world_offset_addr, 16)
            return struct.unpack('<ffff', raw)
        except Exception:
            return None

    def get_player_abs(self):
        pos = self.get_player_pos()
        if not pos:
            return None
        off = self.get_world_offsets()
        if off:
            return pos[0] + off[0], pos[1], pos[2] + off[2]
        return pos

    def get_entity_base(self):
        if not self.td:
            return 0
        try:
            return self.pm.read_ulonglong(self.td + 0x18)
        except Exception:
            return 0

    def get_player_heading(self):
        """Retorna heading em graus via forward vector (RBX+0x80/0x88 do hook_e).
        RBX é salvo em tp+0x28 pela cave_e a cada frame do physics loop.
        Retorna None se hook_e não instalado ou vetor zero."""
        if not self.tp:
            return None
        try:
            entity = self.pm.read_ulonglong(self.tp + 0x28)
            if not entity:
                return None
            fx = self.pm.read_float(entity + 0x80)
            fz = self.pm.read_float(entity + 0x88)
            return _calc_player_heading(fx, fz)
        except Exception:
            return None

    def get_camera_heading(self):
        """Retorna (heading, raw) onde heading é o valor processado e raw é o float
        lido diretamente da cave (antes de qualquer conversão).
        Retorna (None, None) se hook não instalado ou valor ainda zerado."""
        if not self.hook_cam or not self.block:
            return None, None
        try:
            raw = self.pm.read_float(self.block + self.OFF_CAM_YAW)
            heading = _calc_camera_heading(raw)
            return heading, raw
        except Exception:
            return None, None

    def set_invuln(self, on: bool):
        if not self.teleport_enabled:
            return
        if self.inv:
            try:
                self.pm.write_bytes(self.inv, b'\x01' if on else b'\x00', 1)
            except Exception:
                pass

    def get_map_dest(self):
        """Retorna (x, y, z) do marcador de destino do mapa in-game, ou None."""
        if not self.md:
            return None
        try:
            raw = self.pm.read_bytes(self.md, 16)
            x, y, z, flag = struct.unpack('<fffI', raw)
            if flag != 1:
                return None
            return x, y, z
        except Exception:
            return None

    def teleport_to_abs(self, abs_x, abs_y, abs_z):
        if not self.teleport_enabled:
            return False, "Teleport is disabled in settings"
        # Método preferido: delta injection via hook_e (physics loop)
        # [r13] opera no mesmo espaço que os static globals e get_player_pos()
        # (coordenadas absolutas) — não subtrair world_offset aqui.
        if self.tp and self.hook_e and self.xyz_addr[0]:
            try:
                data = struct.pack('<ffffI', abs_x, abs_y, abs_z, 0.0, 1)
                self.pm.write_bytes(self.tp, data, len(data))
                log.info("Teleport queued: (%.1f, %.1f, %.1f)", abs_x, abs_y, abs_z)
                return True, ""
            except Exception as e:
                return False, str(e)

        return False, "Physics delta hook not installed — hook_e AOB not found for this patch"

