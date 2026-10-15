// Pure-JS PNG crop + upscale tool (no external deps)
const fs = require('fs');
const zlib = require('zlib');

function readPNG(path) {
  const buf = fs.readFileSync(path);
  let pos = 8;
  let w = 0, h = 0, bitDepth = 0, colorType = 0, interlace = 0;
  const idat = [];
  let palette = null, trns = null;
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === 'IHDR') {
      w = data.readUInt32BE(0); h = data.readUInt32BE(4);
      bitDepth = data[8]; colorType = data[9]; interlace = data[12];
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'PLTE') palette = Buffer.from(data);
    else if (type === 'tRNS') trns = Buffer.from(data);
    else if (type === 'IEND') break;
    pos += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType];
  const bpp = Math.ceil(channels * bitDepth / 8);
  const stride = Math.ceil(w * channels * bitDepth / 8);
  const out = Buffer.alloc(w * h * bpp);
  let prev = Buffer.alloc(stride);
  let off = 0;
  for (let y = 0; y < h; y++) {
    const filter = raw[off++];
    const line = Buffer.from(raw.subarray(off, off + stride));
    off += stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? line[x - bpp] : 0;
      const b = prev[x];
      const c = x >= bpp ? prev[x - bpp] : 0;
      let v = line[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
        v += (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c);
      }
      line[x] = v & 0xff;
    }
    line.copy(out, y * stride);
    prev = line;
  }
  // expand to RGBA
  const rgba = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    let r, g, b, a = 255;
    if (colorType === 6) { r = out[i*4]; g = out[i*4+1]; b = out[i*4+2]; a = out[i*4+3]; }
    else if (colorType === 2) { r = out[i*3]; g = out[i*3+1]; b = out[i*3+2]; }
    else if (colorType === 0) { r = g = b = out[i]; }
    else if (colorType === 4) { r = g = b = out[i*2]; a = out[i*2+1]; }
    else if (colorType === 3) { const idx = out[i]; r = palette[idx*3]; g = palette[idx*3+1]; b = palette[idx*3+2]; if (trns && idx < trns.length) a = trns[idx]; }
    rgba[i*4] = r; rgba[i*4+1] = g; rgba[i*4+2] = b; rgba[i*4+3] = a;
  }
  return { w, h, rgba };
}

function writePNG(path, w, h, rgba) {
  const stride = w * 4;
  const raw = Buffer.alloc((stride + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });
  const chunks = [];
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  function chunk(type, data) {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const t = Buffer.from(type, 'ascii');
    const crcBuf = Buffer.concat([t, data]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(crcBuf) >>> 0);
    return Buffer.concat([len, t, data, crc]);
  }
  let table = null;
  function crc32(buf) {
    if (!table) {
      table = new Int32Array(256);
      for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; table[n] = c; }
    }
    let c = -1;
    for (let i = 0; i < buf.length; i++) c = table[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
    return c ^ -1;
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  chunks.push(sig, chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0)));
  fs.writeFileSync(path, Buffer.concat(chunks));
}

// args: in out cropX cropY cropW cropH scale
const [,, inPath, outPath, cx, cy, cw, ch, scale] = process.argv;
const img = readPNG(inPath);
const X = +cx, Y = +cy, W = Math.min(+cw, img.w - X), H = Math.min(+ch, img.h - Y), S = +scale || 1;
const ow = W * S, oh = H * S;
const out = Buffer.alloc(ow * oh * 4);
for (let y = 0; y < oh; y++) {
  for (let x = 0; x < ow; x++) {
    const sx = X + Math.floor(x / S), sy = Y + Math.floor(y / S);
    const si = (sy * img.w + sx) * 4, di = (y * ow + x) * 4;
    out[di] = img.rgba[si]; out[di+1] = img.rgba[si+1]; out[di+2] = img.rgba[si+2]; out[di+3] = img.rgba[si+3];
  }
}
writePNG(outPath, ow, oh, out);
console.log(`cropped ${X},${Y} ${W}x${H} scale ${S} -> ${ow}x${oh} : ${outPath}`);
