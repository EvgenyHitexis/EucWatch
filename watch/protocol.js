/* ES5, P22 Espruino 2v14. Sherman L source/owner offsets: docs/research/sherman-l-protocol.md. */
exports.create = function () {
  var buffer = [], rejected = 0;
  return {
    feed: function (raw, valid) {
      var i, total, frame, firmware, signed, crc, expected;
      for (i = 0; i < raw.length; i++) {
        buffer.push(raw[i] & 255);
        while (buffer.length >= 3) {
          if (buffer[0] !== 220 || buffer[1] !== 90 || buffer[2] !== 92) { buffer.shift(); continue; }
          if (buffer.length < 4) break;
          total = buffer[3] + 4;
          if (total !== 75 && total !== 77 && total !== 87 && total !== 99) { rejected++; buffer.shift(); continue; }
          if (buffer.length < total) break;
          frame = buffer.slice(0, total);
          crc = exports.crc(frame, total - 4);
          expected = ((frame[total-4] << 24) | (frame[total-3] << 16) | (frame[total-2] << 8) | frame[total-1]) >>> 0;
          if (crc !== expected) { rejected++; buffer.shift(); continue; }
          buffer.splice(0, total);
          firmware = frame[28] * 256 + frame[29];
          if (Math.floor(firmware / 1000) !== 6 || frame[30] !== 0) { rejected++; continue; }
          signed = frame[6] * 256 + frame[7];
          if (signed >= 32768) signed -= 65536;
          valid({ voltage_V: (frame[4] * 256 + frame[5]) / 100,
            speed_kmh: signed / 10, pwm_percent: (frame[34] * 256 + frame[35]) / 100,
            firmware: ('00' + Math.floor(firmware / 1000)).slice(-3) + '.' + Math.floor(firmware % 1000 / 100) + '.' + ('0' + firmware % 100).slice(-2) }, frame);
        }
      }
    },
    status: function () { return { retained_bytes: buffer.length, rejected_frames: rejected }; }
  };
};
exports.crc = function (bytes, length) {
  var crc = -1, i, bit;
  for (i = 0; i < length; i++) {
    crc ^= bytes[i];
    for (bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
  }
  return (crc ^ -1) >>> 0;
};
