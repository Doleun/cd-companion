"""
TeleportEngine — leitura de memória, hooks e teleport.
Extraído de position_server.py para melhor organização.
"""

import ctypes
import ctypes.wintypes
import logging
import struct

import pymem
import pymem.process

from server.memory.constants import (
    PROCESS_NAME, SAVE_DIR, HOOK_OFFSETS_FILE, HEIGHT_BOOST,
    k32, MEM_COMMIT, MEM_RESERVE, MEM_RELEASE, PAGE_EXECUTE_READWRITE, _REDACT,
)
from server.memory.hook_cache import _load_hook_offsets, _save_hook_offsets
from server.memory.reader import ReaderMixin
from server.memory.teleport import TeleportMixin
from server.memory.shared_mem import SharedMemoryMixin
from server.memory.mem_alloc import MemAllocMixin
from server.memory.cave_builder import CaveBuilderMixin

log = logging.getLogger('cd_server')


# ── TeleportEngine (position reading only) ───────────────────────────

class TeleportEngine(SharedMemoryMixin, MemAllocMixin, CaveBuilderMixin, ReaderMixin, TeleportMixin):
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

    def __init__(self, teleport_enabled: bool = True, use_shared_memory_entity: bool = True):
        self.teleport_enabled = teleport_enabled
        self.use_shared_memory_entity = use_shared_memory_entity
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
        self._hook_e_predecessor = 0  # trampoline de outro mod hookado no mesmo ponto (ex: OpenFlight)
        self._hook_e_predecessor_patch_size = 0  # 0, 5 (safetyhook), ou 7 (OpenFlight/companion)

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
        self._hook_e_predecessor = 0
        self._hook_e_predecessor_patch_size = 0
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

    def _find_phys_delta_hook(self, data, base):
        """Localiza o ponto de hook no physics delta (movaps xmm0,xmm6 / subss xmm9,xmm8)
        confirmado por addps xmm0,[r13] + movups [r13],xmm0 nos 8 bytes seguintes.
        Retorna endereço absoluto ou 0.
        Também detecta quando o ponto já foi hookado por outro mod (bytes = E9 JMP) —
        nesse caso retorna o endereço assim mesmo para que o caller detecte o predecessor."""
        confirm = self.AOB_PHYS_DELTA_CONFIRM
        hook    = self.AOB_PHYS_DELTA_HOOK
        pos = 0
        while pos < len(data) - 18:
            i = data.find(confirm, pos)
            if i == -1:
                break
            if i >= 8 and data[i - 8:i] == hook:
                return base + i - 8
            if i >= 8 and data[i - 8] == 0xE9:
                # Outro mod (ex: OpenFlight) já hookou este ponto — retorna o endereço
                # para que scan_and_hook detecte e configure o chaining.
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

        # Tenta shared memory do Freedom Flyer para entity base.
        # Se disponível, hook_a é desnecessário — o entity_base vem da shared memory.
        # Fallback: AOB scan normal para hook_a.
        if self.use_shared_memory_entity and self._read_ff_shared_entity():
            self.hook_a = 0
            log.info("Entity base via Freedom Flyer shared memory — hook_a not needed")
        else:
            if self.use_shared_memory_entity:
                log.info("Freedom Flyer shared memory not available — falling back to hook_a")
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

        # Cache tem prioridade sobre AOB scan: o módulo pode ter múltiplas ocorrências
        # do padrão, e quando o JMP da sessão anterior ainda está instalado, find()
        # pula o endereço correto e acerta uma ocorrência errada.
        if "hook_d_rva" in saved:
            rva = int(saved["hook_d_rva"])
            if 0 <= rva <= len(data) - len(self.ORIG_HOOK_D):
                chunk = data[rva:rva + len(self.ORIG_HOOK_D)]
                if chunk == self.ORIG_HOOK_D:
                    self.hook_d = base + rva
                    log.info("Map dest hook loaded from cache")
                elif chunk[:1] == b'\xE9':
                    self.hook_d = base + rva
                    log.info("Map dest hook recovered (JMP still installed from previous session)")
                else:
                    self.hook_d = 0
                    saved.pop("hook_d_rva", None)
                    _save_hook_offsets(saved)
                    log.warning("Cached map dest hook stale, cache cleared")
            else:
                self.hook_d = 0
                saved.pop("hook_d_rva", None)
                _save_hook_offsets(saved)
                log.warning("Cached map dest hook RVA out of range, cache cleared")
        else:
            idx = data.find(self.AOB_MAP)
            if idx != -1:
                self.hook_d = base + idx + self.AOB_MAP_HOOK_OFFSET
                log.info("Map dest hook found")
            else:
                # Sem cache e JMP stale: busca pelos bytes não-patchados + opcode JMP
                stale_prefix = self.AOB_MAP[:self.AOB_MAP_HOOK_OFFSET] + b'\xE9'
                idx2 = data.find(stale_prefix)
                if idx2 != -1:
                    self.hook_d = base + idx2 + self.AOB_MAP_HOOK_OFFSET
                    log.info("Map dest hook recovered via stale prefix scan")
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

        # Detectar se outro mod (ex: OpenFlight) já hookou hook_e antes do companion.
        # Lemos os bytes diretamente via pm.read_bytes (não via data[] do _read_module,
        # que pode ter zeros nessa região se o chunk falhou na leitura em massa).
        # Se o primeiro byte for E9, pode ser: (a) JMP de outro mod ativo, ou
        # (b) JMP stale do companion numa sessão anterior que crashou sem fazer detach.
        # Distinguimos tentando ler 1 byte do destino do JMP: se a página foi liberada
        # (VirtualFreeEx do detach anterior), pymem lança exceção → stale, sobreescrever.
        # Se a leitura funciona → trampoline de outro mod ativo → encadear.
        if self.hook_e and self.teleport_enabled:
            try:
                live_bytes = self.pm.read_bytes(self.hook_e, 5)
                if live_bytes[0] == 0xE9:
                    rel32 = struct.unpack_from('<i', live_bytes, 1)[0]
                    candidate = self.hook_e + 5 + rel32
                    try:
                        self.pm.read_bytes(candidate, 1)
                        self._hook_e_predecessor = candidate
                        # Detectar tamanho do patch do predecessor lendo o trampoline.
                        # safetyhook (Freedom Flyer) usa patch de 5 bytes → trampoline[0:5] == orig[0:5].
                        # OpenFlight / companion stale usam patch de 7 bytes → trampoline[0:7] == orig.
                        try:
                            tramp_header = self.pm.read_bytes(candidate, 7)
                            if tramp_header[:5] == self.ORIG_HOOK_E[:5]:
                                if tramp_header == self.ORIG_HOOK_E:
                                    self._hook_e_predecessor_patch_size = 7
                                    log.info("Existing hook detected at hook_e — will chain through predecessor trampoline (+8)")
                                else:
                                    self._hook_e_predecessor_patch_size = 5
                                    log.info("Existing hook detected at hook_e (5-byte patch, safetyhook) — will chain through predecessor trampoline (+5)")
                            else:
                                self._hook_e_predecessor_patch_size = 7
                                log.info("Existing hook detected at hook_e — will chain through predecessor trampoline (+8)")
                        except Exception:
                            self._hook_e_predecessor_patch_size = 7
                            log.info("Existing hook detected at hook_e — will chain through predecessor trampoline (+8)")
                    except Exception:
                        self._hook_e_predecessor = 0
                        log.info("Stale JMP at hook_e (previous companion session without clean detach) — will overwrite")
                else:
                    self._hook_e_predecessor = 0
            except Exception:
                self._hook_e_predecessor = 0

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

