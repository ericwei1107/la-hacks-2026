import ctypes
import re
import struct
import time
import tomllib
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

EXE_NAME = "Polaris-Win64-Shipping.exe"
DEFAULT_OFFSETS = Path(__file__).resolve().parent.parent / "prep" / "offsets-3.02.02.toml"
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
LIST_MODULES_ALL = 0x03
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
PAGE_SIZE = 0x1000
SCAN_CHUNK = 16 << 20
GATE_HEALTH_READS = 30
HEALTH_FIELDS = ("health", "recoverable_limit", "max_health")
MASK64 = (1 << 64) - 1

TYPE_SIZES = {"u8": 1, "u16": 2, "u32": 4, "f32": 4, "f32x3": 12, "ptr": 8, "encoded_health": 4}
TYPE_FORMATS = {"u8": "<B", "u16": "<H", "u32": "<I", "f32": "<f", "f32x3": "<3f", "ptr": "<Q"}


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.ReadProcessMemory.restype = wintypes.BOOL
_k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_k32.Process32FirstW.restype = wintypes.BOOL
_k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_k32.Process32NextW.restype = wintypes.BOOL
_k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.K32EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
_k32.K32EnumProcessModulesEx.restype = wintypes.BOOL
_k32.K32GetModuleInformation.argtypes = [wintypes.HANDLE, wintypes.HMODULE, ctypes.POINTER(MODULEINFO), wintypes.DWORD]
_k32.K32GetModuleInformation.restype = wintypes.BOOL


def rotl64(value, bits):
    bits &= 63
    if not bits:
        return value & MASK64
    return ((value << bits) | (value >> (64 - bits))) & MASK64


def health_check_ok(value, key):
    low = value & 0x0FFFFFFF
    acc = 0
    for k in range(7):
        acc ^= rotl64(key, 4 * (k + 1)) ^ (low >> (4 * k))
    return ((acc & 0xF) or 1) == value >> 28


def decode_health(value, key):
    if not health_check_ok(value, key):
        return None
    t = value ^ 0x1D
    x = (t ^ (rotl64(key, t & 0x1F) & 0xFFFFFFE0)) & 0x0FFFFFFF
    if x & 0x08000000:
        x -= 0x10000000
    return x >> 16


def find_pid(exe_name=EXE_NAME):
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or not snap:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        more = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == exe_name.lower():
                return entry.th32ProcessID
            more = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return None


def compile_pattern(text):
    parts = text.split()
    body = b"".join(b"." if p == "??" else re.escape(bytes([int(p, 16)])) for p in parts)
    return re.compile(body, re.DOTALL), len(parts)


_CHAIN_TOKEN = re.compile(r"\s*(\[|\]|\+|S|0x[0-9A-Fa-f]+|\d+)")


def parse_chain(text):
    chains = {}
    for part in text.split(";"):
        if not part.strip():
            continue
        name, expr = part.split("=", 1)
        tokens = []
        pos = 0
        expr = expr.strip()
        while pos < len(expr):
            m = _CHAIN_TOKEN.match(expr, pos)
            if not m:
                raise ValueError(f"bad chain expression: {expr!r}")
            tokens.append(m.group(1))
            pos = m.end()
        chains[name.strip()] = tokens
    return chains


def eval_chain(tokens, static, read_ptr):
    pos = 0

    def expr():
        nonlocal pos
        value = term()
        while pos < len(tokens) and tokens[pos] == "+":
            offset = int(tokens[pos + 1], 0)
            pos += 2
            value = None if value is None else value + offset
        return value

    def term():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "S":
            return static
        if tok == "[":
            inner = expr()
            pos += 1
            return read_ptr(inner) if inner else None
        return int(tok, 0)

    return expr()


class GameProcess:
    def __init__(self, pid):
        self.pid = pid
        self.handle = _k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess failed for pid {pid}")
        self._got = ctypes.c_size_t()
        self._buffers = {}
        self.base, self.image_size = self._main_module()

    def _main_module(self):
        needed = wintypes.DWORD()
        modules = (wintypes.HMODULE * 1)()
        if not _k32.K32EnumProcessModulesEx(self.handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), LIST_MODULES_ALL):
            raise OSError(ctypes.get_last_error(), "EnumProcessModulesEx failed")
        info = MODULEINFO()
        if not _k32.K32GetModuleInformation(self.handle, modules[0], ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "GetModuleInformation failed")
        return info.lpBaseOfDll, info.SizeOfImage

    def close(self):
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None

    def read(self, address, size):
        if not address:
            return None
        buf = self._buffers.get(size)
        if buf is None:
            buf = ctypes.create_string_buffer(size)
            if size <= 0x10000:
                self._buffers[size] = buf
        if not _k32.ReadProcessMemory(self.handle, address, buf, size, ctypes.byref(self._got)) or self._got.value != size:
            return None
        return buf.raw

    def u8(self, address):
        raw = self.read(address, 1)
        return None if raw is None else raw[0]

    def u32(self, address):
        raw = self.read(address, 4)
        return None if raw is None else struct.unpack("<I", raw)[0]

    def i32(self, address):
        raw = self.read(address, 4)
        return None if raw is None else struct.unpack("<i", raw)[0]

    def ptr(self, address):
        raw = self.read(address, 8)
        if raw is None:
            return None
        return struct.unpack("<Q", raw)[0] or None

    def readable_spans(self, start, end):
        spans = []
        mbi = MEMORY_BASIC_INFORMATION()
        addr = start
        while addr < end:
            if not _k32.VirtualQueryEx(self.handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            region_end = min(mbi.BaseAddress + mbi.RegionSize, end)
            readable = mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) and mbi.Protect != 0
            if readable:
                if spans and spans[-1][1] == addr:
                    spans[-1][1] = region_end
                else:
                    spans.append([addr, region_end])
            if region_end <= addr:
                break
            addr = region_end
        return spans

    def read_tolerant(self, address, size):
        raw = self.read(address, size)
        if raw is not None:
            return raw, 0
        pieces = []
        skipped = 0
        for page in range(address, address + size, PAGE_SIZE):
            n = min(PAGE_SIZE, address + size - page)
            chunk = self.read(page, n)
            if chunk is None:
                pieces.append(b"\x00" * n)
                skipped += n
            else:
                pieces.append(chunk)
        return b"".join(pieces), skipped

    def scan(self, patterns):
        compiled = {name: compile_pattern(text) for name, text in patterns.items()}
        overlap = max(n for _, n in compiled.values()) - 1
        hits = {name: set() for name in patterns}
        skipped = 0
        for span_start, span_end in self.readable_spans(self.base, self.base + self.image_size):
            pos = span_start
            while pos < span_end:
                size = min(SCAN_CHUNK + overlap, span_end - pos)
                data, lost = self.read_tolerant(pos, size)
                skipped += lost
                for name, (regex, _) in compiled.items():
                    m = regex.search(data)
                    while m:
                        hits[name].add(pos + m.start())
                        m = regex.search(data, m.start() + 1)
                pos += SCAN_CHUNK
        return {name: sorted(found) for name, found in hits.items()}, skipped


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class GateResult:
    checks: list = field(default_factory=list)

    @property
    def ok(self):
        return bool(self.checks) and all(c.ok for c in self.checks)

    def add(self, name, ok, detail):
        self.checks.append(Check(name, ok, detail))
        return ok


@dataclass
class Snapshot:
    round_frame: int
    human_slot: int
    players: list


class Reader:
    def __init__(self, offsets_path=DEFAULT_OFFSETS):
        with open(offsets_path, "rb") as f:
            self.spec = tomllib.load(f)
        self.offsets_path = Path(offsets_path)
        self.game = self.spec["game"]
        self.patterns = self.spec["patterns"]
        self.fields = self.spec["player"]
        for name, desc in self.fields.items():
            if desc["type"] not in TYPE_SIZES:
                raise ValueError(f"unknown type {desc['type']!r} for player field {name}")
        self.block_size = max(
            max(d["offset"] + TYPE_SIZES[d["type"]], d.get("key", 0) + 8) for d in self.fields.values()
        )
        self.move_record = self.spec.get("move_record", {})
        self.move_record_size = max((d["offset"] + TYPE_SIZES[d["type"]] for d in self.move_record.values()), default=0)
        self.hit_levels = {code: name for name, code in self.spec["hit_level_codes"].items()}
        self.characters = {cid: name for name, cid in self.spec["character_ids"].items()}
        self.info_chain = parse_chain(self.patterns["player_info"]["chain"])
        self.proc = None
        self.statics = {}
        self.hits = {}
        self.version_text = None
        self.blocks = [None, None]
        self.human_slot = None
        self.human_name = None
        self.last_health = {}
        self.discarded_health = 0
        self.torn_rereads = 0

    def attach(self):
        pid = find_pid()
        if pid is None:
            raise LookupError(f"{EXE_NAME} is not running")
        self.proc = GameProcess(pid)
        return self.proc

    def close(self):
        if self.proc:
            self.proc.close()
            self.proc = None

    def pe_timestamp(self):
        lfanew = self.proc.u32(self.proc.base + 0x3C)
        if lfanew is None:
            return None
        return self.proc.u32(self.proc.base + lfanew + 8)

    def resolve_patterns(self):
        texts = {name: p["bytes"] for name, p in self.patterns.items()}
        hits, skipped = self.proc.scan(texts)
        self.hits = hits
        for name, found in hits.items():
            if len(found) == 1:
                hit = found[0]
                disp_at = self.patterns[name]["disp_at"]
                disp = self.proc.i32(hit + disp_at)
                self.statics[name] = None if disp is None else hit + disp_at + 4 + disp
        return hits, skipped

    def read_version(self):
        p = self.patterns["version"]
        raw = self.proc.read(self.statics["version"], p["buffer_len"])
        if raw is None:
            return None, None
        text = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        self.version_text = text
        stripped = text.lstrip(" ")
        return stripped.split(" ", 1)[0] if stripped else "", text

    def resolve_blocks(self):
        p = self.patterns["players"]
        parent = self.proc.ptr(self.statics["players"])
        if parent is None:
            self.blocks = [None, None]
        else:
            self.blocks = [self.proc.ptr(parent + p["p1_ptr"]), self.proc.ptr(parent + p["p2_ptr"])]
        return self.blocks

    def info_blocks(self):
        static = self.statics["player_info"]
        return {name: eval_chain(tokens, static, self.proc.ptr) for name, tokens in self.info_chain.items()}

    def resolve_human(self):
        p = self.patterns["player_info"]
        info = self.info_blocks()
        local, other = info.get("local"), info.get("other")
        local_slot = self.proc.u8(local + p["slot_byte"]) if local else None
        other_slot = self.proc.u8(other + p["slot_byte"]) if other else None
        slot = None
        if local_slot in (0, 1):
            slot = local_slot
        elif other_slot in (0, 1):
            slot = 1 - other_slot
        name = None
        if local:
            raw = self.proc.read(local + p["name"]["offset"], p["name"]["len"])
            if raw is not None:
                name = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        if slot is not None:
            self.human_slot = slot
            self.human_name = name
        return slot, local_slot, other_slot, name

    def parse_block(self, raw):
        out = {}
        for name, desc in self.fields.items():
            kind = desc["type"]
            off = desc["offset"]
            if kind == "encoded_health":
                value = struct.unpack_from("<I", raw, off)[0]
                key = struct.unpack_from("<Q", raw, desc["key"])[0]
                out[name] = decode_health(value, key)
            elif kind == "f32x3":
                out[name] = struct.unpack_from(TYPE_FORMATS[kind], raw, off)
            else:
                out[name] = struct.unpack_from(TYPE_FORMATS[kind], raw, off)[0]
        return out

    def read_block(self, block):
        raw = self.proc.read(block, self.block_size)
        return None if raw is None else self.parse_block(raw)

    def read_move_record(self, address):
        raw = self.proc.read(address, self.move_record_size) if address and self.move_record_size else None
        out = {}
        for name, desc in self.move_record.items():
            out[name] = 0 if raw is None else struct.unpack_from(TYPE_FORMATS[desc["type"]], raw, desc["offset"])[0]
        return out

    def read_player(self, index):
        block = self.blocks[index]
        state = self.read_block(block) if block else None
        if state is None:
            return None
        state.update(self.read_move_record(state.get("move_record")))
        for name in HEALTH_FIELDS:
            cache_key = (block, name)
            if state[name] is None:
                self.discarded_health += 1
                state[name] = self.last_health.get(cache_key)
            else:
                self.last_health[cache_key] = state[name]
        state["character"] = self.characters.get(state["character_id"], "unknown")
        state["hit_level_name"] = self.hit_levels.get(state["hit_level"])
        return state

    def poll_round_frame(self):
        slot = self.human_slot if self.human_slot is not None else 0
        block = self.blocks[slot]
        if not block:
            return None
        return self.proc.u32(block + self.fields["round_frame"]["offset"])

    def snapshot(self):
        self.resolve_blocks()
        self.resolve_human()
        players = [self.read_player(0), self.read_player(1)]
        if self.human_slot is None or any(p is None for p in players):
            return None
        other = 1 - self.human_slot
        if players[other]["round_frame"] != players[self.human_slot]["round_frame"]:
            self.torn_rereads += 1
            players[other] = self.read_player(other) or players[other]
        return Snapshot(players[self.human_slot]["round_frame"], self.human_slot, players)

    def gate(self, log=None):
        result = GateResult()
        emit = log or (lambda c: None)

        def add(name, ok, detail):
            result.add(name, ok, detail)
            emit(result.checks[-1])
            return ok

        if not add("python", struct.calcsize("P") == 8, f"{struct.calcsize('P') * 8}-bit Python"):
            return result
        try:
            self.attach()
        except (LookupError, OSError) as e:
            add("process", False, str(e))
            return result
        add("process", True, f"pid {self.proc.pid}, base 0x{self.proc.base:X}, opened read-only (QUERY_INFORMATION | VM_READ)")

        ts = self.pe_timestamp()
        want_ts = self.game["pe_timestamp"]
        ts_ok = add("pe_timestamp", ts == want_ts, f"0x{ts or 0:08X} (want 0x{want_ts:08X})")
        want_size = self.game["image_size"]
        size_ok = add("image_size", self.proc.image_size == want_size, f"0x{self.proc.image_size:X} (want 0x{want_size:X})")
        if not (ts_ok and size_ok):
            return result

        t0 = time.perf_counter()
        hits, skipped = self.resolve_patterns()
        scan_ms = (time.perf_counter() - t0) * 1000
        patterns_ok = True
        for name, found in hits.items():
            p = self.patterns[name]
            if len(found) != 1:
                detail = f"{len(found)} matches (want exactly 1)"
                ok = False
            else:
                hit_rva = found[0] - self.proc.base
                target = self.statics.get(name)
                target_rva = None if target is None else target - self.proc.base
                ok = hit_rva == p["hit_rva"] and (target_rva == p["target_rva"] if "target_rva" in p else target is not None)
                detail = f"1 match at +0x{hit_rva:X} (want +0x{p['hit_rva']:X}), static +0x{target_rva or 0:X}"
            patterns_ok = add(f"pattern.{name}", ok, detail) and patterns_ok
        add("scan", skipped == 0, f"{scan_ms:.0f} ms, {skipped} unreadable bytes in image")
        if not patterns_ok:
            return result

        version, text = self.read_version()
        if not add("version", version == self.game["version"], f"{version!r} from {text!r} (want {self.game['version']!r})"):
            return result

        blocks = self.resolve_blocks()
        slot_off = self.fields["slot"]["offset"]
        slots = [self.proc.u8(b + slot_off) if b else None for b in blocks]
        detail = ", ".join(f"P{i + 1} block 0x{b or 0:X} slot {s}" for i, (b, s) in enumerate(zip(blocks, slots)))
        if not add("slot_bytes", slots == [0, 1], detail + " (want 0 and 1; be in a match or practice)"):
            return result

        slot, local_slot, other_slot, name = self.resolve_human()
        detail = f"local info slot {local_slot}, other info slot {other_slot}, name {name!r}"
        if not add("human_slot", slot in (0, 1), f"human is P{(slot or 0) + 1} block; {detail}" if slot is not None else detail):
            return result

        bad = {}
        values = {}
        for _ in range(GATE_HEALTH_READS):
            for i, block in enumerate(blocks):
                state = self.read_block(block)
                for fname in HEALTH_FIELDS:
                    v = None if state is None else state[fname]
                    if v is None:
                        bad[(i, fname)] = bad.get((i, fname), 0) + 1
                    else:
                        values[(i, fname)] = v
            time.sleep(0.001)
        reads = GATE_HEALTH_READS * len(blocks) * len(HEALTH_FIELDS)
        detail = "; ".join(
            f"P{i + 1} " + "/".join(str(values.get((i, f), "?")) for f in HEALTH_FIELDS) for i in range(len(blocks))
        )
        add("health_check", not bad, f"{reads - sum(bad.values())}/{reads} valid over {GATE_HEALTH_READS} reads; health/limit/max {detail}")
        return result
