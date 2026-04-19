"""
Générateur QR Code minimaliste en Python pur (stdlib uniquement).
Supporte les versions 1-10, mode Byte, niveau de correction M.
Génère du SVG directement.
"""

# ── Polynômes de Reed-Solomon ─────────────────────────────────────────
GF256_EXP = [0] * 512
GF256_LOG = [0] * 256

def _init_gf():
    x = 1
    for i in range(255):
        GF256_EXP[i] = x
        GF256_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF256_EXP[i] = GF256_EXP[i - 255]

_init_gf()

def gf_mul(a, b):
    if a == 0 or b == 0: return 0
    return GF256_EXP[(GF256_LOG[a] + GF256_LOG[b]) % 255]

def gf_poly_mul(p, q):
    r = [0] * (len(p) + len(q) - 1)
    for i, pi in enumerate(p):
        for j, qj in enumerate(q):
            r[i+j] ^= gf_mul(pi, qj)
    return r

def rs_generator(n):
    g = [1]
    for i in range(n):
        g = gf_poly_mul(g, [1, GF256_EXP[i]])
    return g

def rs_encode(data, n_ec):
    gen = rs_generator(n_ec)
    msg = data + [0] * n_ec
    for i in range(len(data)):
        if msg[i] == 0: continue
        coef = msg[i]
        for j in range(len(gen)):
            msg[i+j] ^= gf_mul(gen[j], coef)
    return data + msg[len(data):]

# ── Tables QR ────────────────────────────────────────────────────────
# (version, niveau M) → (modules, data_codewords, ec_codewords_per_block, blocks)
QR_PARAMS = {
    1:  (21,  16,  10, 1),
    2:  (25,  28,  16, 1),
    3:  (29,  44,  26, 1),  # ~28 bytes
    4:  (33,  64,  18, 2),  # ~40 bytes
    5:  (41,  86,  24, 2),  # ~57 bytes
    6:  (45, 108,  16, 4),  # ~67 bytes
    7:  (49, 124,  18, 4),  # ~78 bytes
    8:  (53, 154,  22, 4),  # ~97 bytes
    9:  (57, 182,  22, 5),  # ~116 bytes
    10: (61, 216,  26, 6),  # ~128 bytes (plus sûr pour les URLs longues)
}

def _choose_version(data_len):
    # Capacité en bytes mode byte niveau M (approximatif)
    caps = {1:16, 2:28, 3:44, 4:64, 5:86, 6:108, 7:124, 8:154, 9:182, 10:216}
    # Overhead : 4 (mode) + 8 (longueur) + 4 (terminateur) bits = 2 bytes
    for v in range(1, 11):
        if caps[v] >= data_len + 2:
            return v
    return 10

# ── Masques ──────────────────────────────────────────────────────────
MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]

FORMAT_INFO = [
    0x5412, 0x5125, 0x5E7C, 0x5B4B,
    0x45F9, 0x40CE, 0x4F97, 0x4AA0,
]

VERSION_INFO = {
    7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3,
}

class QRMatrix:
    def __init__(self, version):
        self.version = version
        self.n, self.data_cw, self.ec_cw, self.blocks = QR_PARAMS[version]
        self.mat = [[None]*self.n for _ in range(self.n)]
        self.func = [[False]*self.n for _ in range(self.n)]

    def _set(self, r, c, v, is_func=True):
        if 0 <= r < self.n and 0 <= c < self.n:
            self.mat[r][c] = v
            if is_func:
                self.func[r][c] = True

    def _finder(self, r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                nr, nc = r+dr, c+dc
                if not (0 <= nr < self.n and 0 <= nc < self.n): continue
                inside = (0 <= dr <= 6 and 0 <= dc <= 6)
                border = (dr in (-1,7) or dc in (-1,7))
                ring  = (dr in (1,5) and 1 <= dc <= 5) or (dc in (1,5) and 1 <= dr <= 5)
                v = inside and not border and not ring
                self._set(nr, nc, v)

    def _alignment(self):
        pos = {2:[6,18], 3:[6,22], 4:[6,26], 5:[6,30], 6:[6,34],
               7:[6,22,38], 8:[6,24,42], 9:[6,28,46], 10:[6,28,50]}
        if self.version < 2: return
        ps = pos.get(self.version, [])
        for r in ps:
            for c in ps:
                if (r == 6 and c == 6) or (r == 6 and c == ps[-1]) or (r == ps[-1] and c == 6):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        v = (abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0))
                        self._set(r+dr, c+dc, v)

    def _timing(self):
        for i in range(8, self.n-8):
            self._set(6, i, i%2 == 0)
            self._set(i, 6, i%2 == 0)

    def _dark(self):
        self._set(4*self.version+9, 8, True)

    def _format_area(self):
        # Réserve les zones de format
        for i in range(9):
            self._set(8, i, False)
            self._set(i, 8, False)
        for i in range(self.n-8, self.n):
            self._set(8, i, False)
            self._set(i, 8, False)

    def _write_format(self, mask_id):
        fi = FORMAT_INFO[mask_id]
        bits = [(fi >> i) & 1 for i in range(15)]
        # Horizontal bottom-left
        for i in range(7):
            self._set(self.n-1-i, 8, bool(bits[i]))
        # Horizontal top
        for i in range(8):
            c = 7-i if i < 7 else 8
            self._set(8, c, bool(bits[i]))
        # Vertical left
        for i in range(7):
            r = 8-i if i < 6 else 7
            self._set(r, 8, bool(bits[14-i]))
        # Vertical right
        for i in range(8):
            self._set(8, self.n-8+i, bool(bits[14-i]))

    def _write_version(self):
        if self.version < 7: return
        vi = VERSION_INFO.get(self.version, 0)
        bits = [(vi >> i) & 1 for i in range(18)]
        for i in range(6):
            for j in range(3):
                b = bits[i*3+j]
                self._set(self.n-11+j, i, bool(b))
                self._set(i, self.n-11+j, bool(b))

    def place_data(self, codewords):
        data_bits = []
        for cw in codewords:
            for i in range(7, -1, -1):
                data_bits.append((cw >> i) & 1)

        idx = 0
        col = self.n - 1
        going_up = True
        while col >= 0:
            if col == 6: col -= 1
            r_range = range(self.n-1, -1, -1) if going_up else range(self.n)
            for row in r_range:
                for dc in range(2):
                    c = col - dc
                    if self.func[row][c]: continue
                    bit = data_bits[idx] if idx < len(data_bits) else 0
                    self.mat[row][c] = bool(bit)
                    idx += 1
            going_up = not going_up
            col -= 2

    def apply_mask(self, mask_id):
        fn = MASKS[mask_id]
        for r in range(self.n):
            for c in range(self.n):
                if not self.func[r][c] and self.mat[r][c] is not None:
                    if fn(r, c):
                        self.mat[r][c] = not self.mat[r][c]

    def penalty(self):
        score = 0
        n = self.n
        m = self.mat
        # Rule 1: 5+ same in row/col
        for row in range(n):
            run = 1
            for c in range(1, n):
                if m[row][c] == m[row][c-1]: run += 1
                else:
                    if run >= 5: score += run - 2
                    run = 1
            if run >= 5: score += run - 2
        for col in range(n):
            run = 1
            for r in range(1, n):
                if m[r][col] == m[r-1][col]: run += 1
                else:
                    if run >= 5: score += run - 2
                    run = 1
            if run >= 5: score += run - 2
        # Rule 2: 2x2 blocks
        for r in range(n-1):
            for c in range(n-1):
                v = m[r][c]
                if v == m[r][c+1] == m[r+1][c] == m[r+1][c+1]:
                    score += 3
        return score

    def build(self):
        self._finder(0, 0)
        self._finder(0, self.n-7)
        self._finder(self.n-7, 0)
        self._alignment()
        self._timing()
        self._dark()
        self._format_area()
        self._write_version()

    def to_svg(self, px=10):
        n = self.n
        size = n * px
        rects = []
        for r in range(n):
            for c in range(n):
                if self.mat[r][c]:
                    rects.append(f'<rect x="{c*px}" y="{r*px}" width="{px}" height="{px}"/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{size}" height="{size}" '
                f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
                f'<rect width="{size}" height="{size}" fill="#fff"/>'
                f'<g fill="#000">{"".join(rects)}</g>'
                f'</svg>')


def encode_data(text):
    data = text.encode('utf-8')
    version = _choose_version(len(data))
    n, data_cw, ec_cw, num_blocks = QR_PARAMS[version]

    # Bitstream
    bits = []
    # Mode byte
    bits += [0,1,0,0]
    # Longueur (8 bits pour version 1-9)
    L = len(data)
    for i in range(7, -1, -1):
        bits.append((L >> i) & 1)
    # Data
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    # Terminator
    bits += [0,0,0,0]
    # Pad to byte boundary
    while len(bits) % 8:
        bits.append(0)
    # Pad codewords
    total_bits = data_cw * 8
    pad = [0b11101100, 0b00010001]
    pi = 0
    while len(bits) < total_bits:
        for i in range(7, -1, -1):
            bits.append((pad[pi] >> i) & 1)
        pi = 1 - pi

    # Bytes
    cw = [0]*data_cw
    for i in range(data_cw):
        for j in range(8):
            cw[i] = (cw[i] << 1) | bits[i*8+j]

    # Interleave blocks + RS
    block_size = data_cw // num_blocks
    blocks = [cw[i*block_size:(i+1)*block_size] for i in range(num_blocks)]
    ec_blocks = [rs_encode(b[:], ec_cw) for b in blocks]

    final = []
    # Interleave data
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                final.append(b[i])
    # Interleave EC
    for i in range(ec_cw):
        for b in ec_blocks:
            final.append(b[len(b)-ec_cw+i])

    # Remainder bits
    remainder = {2:7,3:7,4:7,5:7,6:7,7:0,8:0,9:0,10:0}
    final += [0] * remainder.get(version, 0)

    return version, final


def generate_qr_svg(text):
    version, codewords = encode_data(text)
    qr = QRMatrix(version)
    qr.build()

    # Choisit le meilleur masque
    best_mask = 0
    best_score = float('inf')
    for mask_id in range(8):
        import copy
        qr2 = copy.deepcopy(qr)
        qr2.place_data(list(codewords))
        qr2.apply_mask(mask_id)
        qr2._write_format(mask_id)
        s = qr2.penalty()
        if s < best_score:
            best_score = s
            best_mask = mask_id

    qr.place_data(list(codewords))
    qr.apply_mask(best_mask)
    qr._write_format(best_mask)
    return qr.to_svg(px=10)


import base64

def qr_svg_data_url(text: str) -> str:
    """
    Génère un QR code SVG et le retourne en data URL base64.
    Utilisable directement comme src d'une balise <img>.
    """
    svg = generate_qr_svg(text)
    b64 = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f"data:image/svg+xml;base64,{b64}"
